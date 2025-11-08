#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import hmac
import hashlib
import threading
from datetime import datetime
from urllib.parse import urlencode
import csv

import requests
import tkinter as tk
from tkinter import ttk, messagebox

BINANCE_BASE_URL = "https://api.binance.com"


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")

        # Gestion du quota SAPI
        # /sapi/v1/accountSnapshot a un coût important (~2400 par appel)
        self.sapi_limit_per_minute = 12000     # approximation de la limite IP/minute
        self.snapshot_weight = 2400            # poids estimé d'un appel accountSnapshot
        self.sapi_used_weight_1m = None        # dernière valeur lue dans les headers

    # ---------- Quota ----------

    def _update_sapi_weight_from_headers(self, headers):
        """
        Met à jour self.sapi_used_weight_1m à partir des headers Binance.
        On prend X-SAPI-USED-IP-WEIGHT-1M ou X-SAPI-USED-UID-WEIGHT-1M si présent.
        """
        val = headers.get("X-SAPI-USED-IP-WEIGHT-1M")
        if val is None:
            val = headers.get("X-SAPI-USED-UID-WEIGHT-1M")
        if val is not None:
            try:
                self.sapi_used_weight_1m = int(val)
            except ValueError:
                # On ignore si ce n'est pas un entier
                pass

    def get_last_quota_info(self):
        """Retourne (used_weight, limit) pour affichage dans l’UI."""
        return self.sapi_used_weight_1m, self.sapi_limit_per_minute

    # ---------- Requêtes HTTP ----------

    def _public_get(self, path: str, params: dict | None = None):
        params = params or {}
        query = urlencode(params, doseq=True)
        url = f"{BINANCE_BASE_URL}{path}"
        if query:
            url += f"?{query}"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} - {resp.text}")
        return resp.json()

    def _signed_get_sapi(self, path: str, params: dict | None = None):
        """
        Envoie une requête signée sur /sapi.
        Gère les erreurs 429 (trop de requêtes) en attendant 60s avant de réessayer.
        """
        if params is None:
            params = {}
        params = dict(params)

        while True:
            params["timestamp"] = int(time.time() * 1000)
            params.setdefault("recvWindow", 60000)

            query = urlencode(params, doseq=True)
            signature = hmac.new(self.api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
            query_with_sig = f"{query}&signature={signature}"

            headers = {"X-MBX-APIKEY": self.api_key}
            url = f"{BINANCE_BASE_URL}{path}?{query_with_sig}"

            resp = requests.get(url, headers=headers, timeout=30)

            # Mise à jour du quota d'après les headers
            self._update_sapi_weight_from_headers(resp.headers)

            if resp.status_code == 429:
                # Trop de requêtes : on attend une minute avant de réessayer
                time.sleep(60)
                continue

            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code} - {resp.text}")

            return resp.json()

    # ---------- Récupération des snapshots journaliers ----------

    def get_account_snapshots(self, account_type: str, start_ms: int, end_ms: int):
        """
        Récupère tous les snapshots entre start_ms et end_ms (inclus),
        en chunkant par 30 jours (limite API).
        Utilise les quotas SAPI pour éviter de dépasser la limite :
        si le quota restant est < snapshot_weight, on attend 60s avant la requête suivante.
        """
        results = []
        MS_PER_DAY = 24 * 3600 * 1000
        MAX_DAYS = 30

        current_start = start_ms
        while current_start <= end_ms:
            # Avant d'envoyer la requête, on vérifie si on a assez de quota
            if self.sapi_used_weight_1m is not None:
                remaining = self.sapi_limit_per_minute - self.sapi_used_weight_1m
                # Si on n'a plus de marge pour un nouvel appel snapshot, on attend 60s
                if remaining < self.snapshot_weight:
                    time.sleep(60)

            current_end = min(current_start + MAX_DAYS * MS_PER_DAY - 1, end_ms)

            params = {
                "type": account_type.upper(),  # SPOT / MARGIN / FUTURES
                "startTime": current_start,
                "endTime": current_end,
                "limit": 30,  # max 30 snapshots
            }

            data = self._signed_get_sapi("/sapi/v1/accountSnapshot", params)
            vos = data.get("snapshotVos", [])
            results.extend(vos)

            current_start = current_end + 1

        # Déduplication par (updateTime, type)
        seen = set()
        unique_results = []
        for s in results:
            ut = s.get("updateTime")
            key = (ut, s.get("type"))
            if key not in seen:
                seen.add(key)
                unique_results.append(s)

        # Tri par date
        unique_results.sort(key=lambda x: x.get("updateTime", 0))
        return unique_results

    # ---------- Conversion BTC -> devise de sortie ----------

    def _find_btc_pair(self, quote_asset: str):
        """
        Trouve une paire pour convertir BTC vers quote_asset.
        Essaie d'abord BTC<QUOTE>, puis <QUOTE>BTC (avec inversion du prix).
        Retourne (symbol, invert) où invert=True signifie qu'il faut prendre 1/price.
        """
        quote = quote_asset.upper()
        candidates = [(f"BTC{quote}", False), (f"{quote}BTC", True)]
        for symbol, invert in candidates:
            try:
                self._public_get("/api/v3/exchangeInfo", {"symbol": symbol})
                return symbol, invert
            except RuntimeError:
                continue
        raise RuntimeError(f"Impossible de trouver une paire pour BTC/{quote_asset} sur Binance.")

    def get_btc_conversion_map(self, output_asset: str, datetimes: list[datetime]) -> dict:
        """
        Retourne un dict {date -> prix_de_1_BTC_dans_output_asset}
        pour toutes les dates présentes dans datetimes (datetime.date).
        Utilise les klines journaliers de Binance.
        """
        output = output_asset.upper()

        # Si on sort en BTC, 1 BTC = 1 BTC
        unique_dates = sorted({dt.date() for dt in datetimes if dt is not None})
        if not unique_dates:
            return {}

        if output == "BTC":
            return {d: 1.0 for d in unique_dates}

        symbol, invert = self._find_btc_pair(output)

        # On récupère les klines journaliers entre la 1ère et la dernière date
        first_date = unique_dates[0]
        last_date = unique_dates[-1]

        start_dt = datetime(first_date.year, first_date.month, first_date.day, 0, 0, 0)
        end_dt = datetime(last_date.year, last_date.month, last_date.day, 23, 59, 59)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        price_by_date = {}
        MS_PER_DAY = 24 * 3600 * 1000
        cur_start = start_ms

        while True:
            params = {
                "symbol": symbol,
                "interval": "1d",
                "startTime": cur_start,
                "limit": 1000,
            }
            klines = self._public_get("/api/v3/klines", params)
            if not klines:
                break

            for k in klines:
                open_time_ms = k[0]
                close_price = float(k[4])
                d = datetime.fromtimestamp(open_time_ms / 1000.0).date()
                if d > last_date:
                    break
                price = 1.0 / close_price if invert else close_price
                price_by_date[d] = price

            last_open_ms = klines[-1][0]
            if last_open_ms >= end_ms or len(klines) < 1000:
                break
            cur_start = last_open_ms + MS_PER_DAY

        # On ne garde que les dates qui nous intéressent
        return {d: price_by_date.get(d) for d in unique_dates}


class SnapshotViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Binance - Snapshots journaliers (Spot / Margin / Futures)")
        self.geometry("1200x650")

        # Récupération des clés API via variables d'environnement
        api_key = os.environ.get("binance_api")
        api_secret = os.environ.get("binance_secret")
        if not api_key or not api_secret:
            messagebox.showerror(
                "Erreur clés API",
                "Les variables d'environnement 'binance_api' et 'binance_secret' doivent être définies."
            )
            self.client = None
        else:
            self.client = BinanceClient(api_key, api_secret)

        # Etat UI
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.spot_var = tk.BooleanVar(value=True)
        self.margin_var = tk.BooleanVar(value=True)
        self.futures_var = tk.BooleanVar(value=False)
        self.output_currency_var = tk.StringVar(value="USDC")  # devise de sortie
        self.status_var = tk.StringVar(value="Prêt.")
        self.snapshots_data = []

        self._build_ui()

    # ---------- Construction de l’interface ----------

    def _build_ui(self):
        controls = ttk.Frame(self, padding=10)
        controls.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(controls, text="Date début (YYYY-MM-DD):").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.start_date_var, width=12).grid(row=0, column=1, padx=5)

        ttk.Label(controls, text="Date fin (YYYY-MM-DD, vide = aujourd'hui):").grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self.end_date_var, width=16).grid(row=0, column=3, padx=5)

        ttk.Checkbutton(controls, text="Spot", variable=self.spot_var).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Checkbutton(controls, text="Margin", variable=self.margin_var).grid(row=1, column=1, sticky="w", pady=5)
        ttk.Checkbutton(controls, text="Futures", variable=self.futures_var).grid(row=1, column=2, sticky="w", pady=5)

        ttk.Label(controls, text="Devise de sortie :").grid(row=1, column=3, sticky="e")
        output_combo = ttk.Combobox(
            controls,
            textvariable=self.output_currency_var,
            values=["USDC", "BTC", "EUR"],
            state="normal",  # éditable pour ajouter d'autres devises (USDT, BUSD, etc.)
            width=10,
        )
        output_combo.grid(row=1, column=4, sticky="w", padx=5)

        ttk.Button(controls, text="Récupérer snapshots", command=self.on_fetch_clicked).grid(
            row=0, column=5, rowspan=2, padx=10, pady=5, sticky="ns"
        )

        # Tableau
        table_frame = ttk.Frame(self, padding=5)
        table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = (
            "account_type",
            "date",
            "time",
            "totalNetAssetOfBtc",
            "output_currency",
            "value_converted",
            "daily_gain",
            "extra",
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        headings = {
            "account_type": "Compte",
            "date": "Date",
            "time": "Heure",
            "totalNetAssetOfBtc": "totalNetAssetOfBtc",
            "output_currency": "Devise",
            "value_converted": "Valeur convertie",
            "daily_gain": "Gain quotidien",
            "extra": "Infos supp.",
        }

        widths = {
            "account_type": 80,
            "date": 90,
            "time": 90,
            "totalNetAssetOfBtc": 140,
            "output_currency": 70,
            "value_converted": 120,
            "daily_gain": 120,
            "extra": 300,
        }

        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="center")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # Barre de statut
        status_bar = ttk.Frame(self, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(status_bar, textvariable=self.status_var, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ---------- Utilitaires ----------

    def _parse_date(self, s: str, default_start: bool) -> int | None:
        """
        Convertit 'YYYY-MM-DD' en timestamp ms.
        default_start:
            True  -> 00:00:00
            False -> 23:59:59
        Retourne None si la chaîne est vide.
        """
        s = s.strip()
        if not s:
            return None
        d = datetime.strptime(s, "%Y-%m-%d")
        if default_start:
            dt = datetime(d.year, d.month, d.day, 0, 0, 0)
        else:
            dt = datetime(d.year, d.month, d.day, 23, 59, 59)
        return int(dt.timestamp() * 1000)

    # ---------- Actions UI ----------

    def on_fetch_clicked(self):
        if self.client is None:
            messagebox.showerror("Erreur", "Client Binance non initialisé (clés API manquantes).")
            return

        if not (self.spot_var.get() or self.margin_var.get() or self.futures_var.get()):
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins un type de compte.")
            return

        thread = threading.Thread(target=self._fetch_snapshots_thread, daemon=True)
        thread.start()

    def _fetch_snapshots_thread(self):
        try:
            self.status_var.set("Récupération des snapshots en cours...")
            self._clear_table()
            self.snapshots_data = []

            start_ms = self._parse_date(self.start_date_var.get(), default_start=True)
            end_ms = self._parse_date(self.end_date_var.get(), default_start=False)

            # Date début obligatoire
            if start_ms is None:
                messagebox.showerror("Erreur", "Merci de renseigner une date de début.")
                self.status_var.set("Erreur: date de début manquante.")
                return

            # Si date de fin non renseignée -> jusqu'à maintenant
            if end_ms is None:
                end_ms = int(time.time() * 1000)

            if start_ms > end_ms:
                messagebox.showerror("Erreur", "La date de début est après la date de fin.")
                self.status_var.set("Erreur: intervalle de dates invalide.")
                return

            types = []
            if self.spot_var.get():
                types.append("SPOT")
            if self.margin_var.get():
                types.append("MARGIN")
            if self.futures_var.get():
                types.append("FUTURES")

            for idx, acc_type in enumerate(types, start=1):
                self.status_var.set(f"[{idx}/{len(types)}] Récupération {acc_type}...")
                self.update_idletasks()

                snapshots = self.client.get_account_snapshots(acc_type, start_ms, end_ms)

                for s in snapshots:
                    ut = s.get("updateTime")
                    dt = datetime.fromtimestamp(ut / 1000.0) if ut else None
                    data = s.get("data", {}) or {}

                    totalAssetOfBtc = data.get("totalAssetOfBtc", "")
                    totalLiabilityOfBtc = data.get("totalLiabilityOfBtc", "")
                    totalNetAssetOfBtc = data.get("totalNetAssetOfBtc", "")

                    extra_info = ""

                    if acc_type == "SPOT":
                        balances = data.get("balances", [])
                        extra_info = f"Nb assets: {len(balances)}"
                    elif acc_type == "MARGIN":
                        balances = data.get("userAssets", [])
                        extra_info = f"Nb userAssets: {len(balances)}"
                    elif acc_type == "FUTURES":
                        assets = data.get("assets", [])
                        extra_info = f"Nb assets futures: {len(assets)}"

                    row = {
                        "account_type": acc_type,
                        "datetime": dt,
                        "totalAssetOfBtc": totalAssetOfBtc,
                        "totalLiabilityOfBtc": totalLiabilityOfBtc,
                        "totalNetAssetOfBtc": totalNetAssetOfBtc,
                        "extra": extra_info,
                        "output_currency": None,
                        "value_converted": None,
                        "daily_gain": None,
                    }
                    self.snapshots_data.append(row)

                # Affichage du quota utilisé
                used, limit = self.client.get_last_quota_info()
                if used is not None and limit is not None:
                    self.status_var.set(
                        f"[{idx}/{len(types)}] {acc_type}: {len(snapshots)} snapshots récupérés. "
                        f"Quota utilisé (1m): {used}/{limit}."
                    )
                else:
                    self.status_var.set(
                        f"[{idx}/{len(types)}] {acc_type}: {len(snapshots)} snapshots récupérés."
                    )
                self.update_idletasks()

            # Tri global par date
            self.snapshots_data.sort(key=lambda r: r["datetime"] or datetime.min)

            # Conversion dans la devise de sortie + calcul des gains quotidiens
            output_asset = (self.output_currency_var.get() or "USDC").strip().upper()
            self._compute_converted_values_and_gains(output_asset)

            # Affichage + export CSV
            self._populate_table()
            filename = self._save_to_csv()
            self.status_var.set(
                f"Terminé. {len(self.snapshots_data)} lignes exportées dans '{filename}'."
            )

        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            self.status_var.set("Erreur lors de la récupération des snapshots.")

    def _compute_converted_values_and_gains(self, output_asset: str):
        """
        Remplit pour chaque ligne :
        - output_currency
        - value_converted (valeur nette en devise choisie)
        - daily_gain (variation par compte, jour après jour)
        """
        output = output_asset.upper()
        datetimes = [r["datetime"] for r in self.snapshots_data if r["datetime"] is not None]
        if not datetimes:
            for r in self.snapshots_data:
                r["output_currency"] = output
                r["value_converted"] = None
                r["daily_gain"] = None
            return

        conv_map = self.client.get_btc_conversion_map(output, datetimes)

        # Conversion de la valeur nette BTC -> devise
        for r in self.snapshots_data:
            r["output_currency"] = output
            dt = r["datetime"]
            net_str = r.get("totalNetAssetOfBtc") or ""
            if dt is None or not net_str:
                r["value_converted"] = None
                continue
            try:
                net_btc = float(net_str)
            except ValueError:
                r["value_converted"] = None
                continue

            price = conv_map.get(dt.date())
            if price is None:
                r["value_converted"] = None
                continue

            r["value_converted"] = net_btc * price

        # Calcul des gains quotidiens par type de compte
        last_val_by_account: dict[str, float] = {}
        for r in self.snapshots_data:
            acc = r["account_type"]
            val = r.get("value_converted")
            if val is None:
                r["daily_gain"] = None
                continue

            if acc not in last_val_by_account:
                r["daily_gain"] = None
                last_val_by_account[acc] = val
            else:
                prev = last_val_by_account[acc]
                r["daily_gain"] = val - prev
                last_val_by_account[acc] = val

    # ---------- Table + CSV ----------

    def _clear_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _populate_table(self):
        self._clear_table()
        for row in self.snapshots_data:
            dt = row["datetime"]
            date_str = dt.strftime("%Y-%m-%d") if dt else ""
            time_str = dt.strftime("%H:%M:%S") if dt else ""

            val = row.get("value_converted")
            gain = row.get("daily_gain")

            val_str = f"{val:.2f}" if isinstance(val, (int, float)) else ""
            gain_str = f"{gain:.2f}" if isinstance(gain, (int, float)) else ""

            self.tree.insert(
                "",
                "end",
                values=(
                    row["account_type"],
                    date_str,
                    time_str,
                    row["totalNetAssetOfBtc"],
                    row["output_currency"],
                    val_str,
                    gain_str,
                    row["extra"],
                ),
            )

    def _save_to_csv(self) -> str:
        if not self.snapshots_data:
            return "snapshots_vide.csv"

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"binance_snapshots_{ts}.csv"

        fieldnames = [
            "account_type",
            "date",
            "time",
            "totalAssetOfBtc",
            "totalLiabilityOfBtc",
            "totalNetAssetOfBtc",
            "output_currency",
            "value_converted",
            "daily_gain",
            "extra",
        ]

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.snapshots_data:
                dt = row["datetime"]
                date_str = dt.strftime("%Y-%m-%d") if dt else ""
                time_str = dt.strftime("%H:%M:%S") if dt else ""
                val = row.get("value_converted")
                gain = row.get("daily_gain")
                val_str = f"{val:.8f}" if isinstance(val, (int, float)) else ""
                gain_str = f"{gain:.8f}" if isinstance(gain, (int, float)) else ""

                writer.writerow({
                    "account_type": row["account_type"],
                    "date": date_str,
                    "time": time_str,
                    "totalAssetOfBtc": row["totalAssetOfBtc"],
                    "totalLiabilityOfBtc": row["totalLiabilityOfBtc"],
                    "totalNetAssetOfBtc": row["totalNetAssetOfBtc"],
                    "output_currency": row["output_currency"],
                    "value_converted": val_str,
                    "daily_gain": gain_str,
                    "extra": row["extra"],
                })

        return filename


def main():
    app = SnapshotViewerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
