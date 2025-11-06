#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
binance_transactions_viewer.py

- Récupère les transactions (trades) spot et/ou margin depuis l'API Binance.
- Utilise les variables d'environnement :
    - binance_api
    - binance_secret
- Interface Tkinter pour choisir :
    - Date de début / fin (au format YYYY-MM-DD, optionnel)
    - Type de compte : Spot / Margin
    - Type d'ordre (MARKET / LIMIT / etc, si dispo)
- Sauvegarde automatiquement les résultats en CSV.
- Affiche les résultats dans un tableau (Treeview).
"""

import os
import time
import csv
import hmac
import hashlib
import threading
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
import tkinter as tk
from tkinter import ttk, messagebox

BINANCE_BASE_URL = "https://api.binance.com"


# ====================== BINANCE CLIENT ======================

class BinanceClient:
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")

    # ----------------- HTTP helpers -----------------

    def _signed_get(self, path: str, params: dict | None = None):
        if params is None:
            params = {}
        params = dict(params)  # copy
        params["timestamp"] = int(time.time() * 1000)
        params.setdefault("recvWindow", 60000)

        query = urlencode(params, doseq=True)
        signature = hmac.new(self.api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
        query_with_sig = f"{query}&signature={signature}"

        headers = {"X-MBX-APIKEY": self.api_key}
        url = f"{BINANCE_BASE_URL}{path}?{query_with_sig}"

        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} - {resp.text}")
        return resp.json()

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

    # ----------------- Symbol helpers -----------------

    def get_exchange_symbols(self, permissions: list[str] | None = None) -> list[dict]:
        """
        Récupère tous les symboles filtrés par permissions (ex: ["SPOT"], ["MARGIN"]).
        Retourne la liste brute des objets symbol.
        """
        params = {}
        if permissions:
            # permissions peut être un seul string ou une liste
            if len(permissions) == 1:
                params["permissions"] = permissions[0]
            else:
                # ex: ["SPOT","MARGIN"] -> JSON dans l'URL
                params["permissions"] = "[" + ",".join(f'"{p}"' for p in permissions) + "]"

        data = self._public_get("/api/v3/exchangeInfo", params)
        return data.get("symbols", [])

    def get_account_balances(self) -> dict[str, float]:
        """
        Balances spot par asset -> float (free + locked).
        """
        data = self._signed_get("/api/v3/account")
        balances = {}
        for b in data.get("balances", []):
            asset = b["asset"]
            total = float(b["free"]) + float(b["locked"])
            balances[asset] = total
        return balances

    def get_margin_assets(self) -> dict[str, float]:
        """
        Balances margin par asset -> float (free + borrowed + interest).
        """
        data = self._signed_get("/sapi/v1/margin/account")
        assets = {}
        for a in data.get("userAssets", []):
            asset = a["asset"]
            total = float(a["free"]) + float(a["borrowed"]) + float(a["interest"])
            assets[asset] = total
        return assets

    def guess_spot_symbols_for_user(self) -> list[str]:
        """
        Essaie de deviner les symboles spot pertinents pour l'utilisateur :
        - Récupère les assets non nuls du compte.
        - Garde les symboles SPOT dont le baseAsset ou quoteAsset est dans ces assets.
        NB: Ce n'est pas parfait, mais c'est plus léger que de scanner 100% des symboles.
        """
        balances = self.get_account_balances()
        held_assets = {a for a, v in balances.items() if v > 0}

        symbols_info = self.get_exchange_symbols(["SPOT"])
        result = []
        for s in symbols_info:
            if not s.get("status") == "TRADING":
                continue
            base = s["baseAsset"]
            quote = s["quoteAsset"]
            if base in held_assets or quote in held_assets:
                result.append(s["symbol"])
        return sorted(set(result))

    def guess_margin_symbols_for_user(self) -> list[str]:
        """
        Idem que pour spot mais pour les pairs MARGIN.
        """
        margin_assets = self.get_margin_assets()
        held_assets = {a for a, v in margin_assets.items() if v > 0}

        # symbols avec permission MARGIN
        symbols_info = self.get_exchange_symbols(["MARGIN"])
        result = []
        for s in symbols_info:
            if not s.get("status") == "TRADING":
                continue
            base = s["baseAsset"]
            quote = s["quoteAsset"]
            if base in held_assets or quote in held_assets:
                result.append(s["symbol"])
        return sorted(set(result))

    # ----------------- Trades & Orders -----------------

    def get_spot_trades_for_symbol(self, symbol: str, start_ms: int | None, end_ms: int | None):
        """
        Récupère les trades spot pour un symbol donné, dans une fenêtre de temps.
        Version simple, sans pagination avancée (limité à 1000 résultats).
        """
        params = {"symbol": symbol, "limit": 1000}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return self._signed_get("/api/v3/myTrades", params)

    def get_margin_trades_for_symbol(self, symbol: str, start_ms: int | None, end_ms: int | None):
        """
        Récupère les trades margin pour un symbol donné, dans une fenêtre de temps.
        Version simple, sans pagination avancée (limité à 1000 résultats).
        """
        params = {"symbol": symbol, "limit": 1000}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return self._signed_get("/sapi/v1/margin/myTrades", params)

    def get_spot_orders_for_symbol(self, symbol: str, start_ms: int | None, end_ms: int | None):
        """
        Récupère les orders spot pour un symbol (pour retrouver le type d'ordre).
        Limité à 1000 résultats sur la période.
        """
        params = {"symbol": symbol, "limit": 1000}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return self._signed_get("/api/v3/allOrders", params)

    def get_margin_orders_for_symbol(self, symbol: str, start_ms: int | None, end_ms: int | None):
        """
        Récupère les orders margin pour un symbol (pour retrouver le type d'ordre).
        Limité à 1000 résultats sur la période.
        """
        params = {"symbol": symbol, "limit": 1000}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return self._signed_get("/sapi/v1/margin/allOrders", params)


# ====================== APPLICATION TKINTER ======================

class BinanceTransactionsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Binance - Transactions (Spot / Margin)")
        self.geometry("1200x700")

        # Binance client
        api_key = os.environ.get("binance_api")
        api_secret = os.environ.get("binance_secret")
        if not api_key or not api_secret:
            messagebox.showerror(
                "Erreur clés API",
                "Les variables d'environnement 'binance_api' et 'binance_secret' doivent être définies."
            )
        self.client = BinanceClient(api_key, api_secret) if api_key and api_secret else None

        # UI state
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.include_spot_var = tk.BooleanVar(value=True)
        self.include_margin_var = tk.BooleanVar(value=True)
        self.order_type_var = tk.StringVar(value="ALL")

        self.status_var = tk.StringVar(value="Prêt.")
        self.trades_data = []  # liste de dict

        self._build_ui()

    # ----------------- UI layout -----------------

    def _build_ui(self):
        # Frame des contrôles
        controls = ttk.Frame(self, padding=10)
        controls.pack(side=tk.TOP, fill=tk.X)

        # Dates
        ttk.Label(controls, text="Date début (YYYY-MM-DD) :").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.start_date_var, width=12).grid(row=0, column=1, padx=5)

        ttk.Label(controls, text="Date fin (YYYY-MM-DD) :").grid(row=0, column=2, sticky="w")
        ttk.Entry(controls, textvariable=self.end_date_var, width=12).grid(row=0, column=3, padx=5)

        # Types de compte
        ttk.Checkbutton(controls, text="Spot", variable=self.include_spot_var).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Checkbutton(controls, text="Margin", variable=self.include_margin_var).grid(row=1, column=1, sticky="w", pady=5)

        # Type d'ordre
        ttk.Label(controls, text="Type d'ordre :").grid(row=1, column=2, sticky="e")
        order_type_combo = ttk.Combobox(
            controls,
            textvariable=self.order_type_var,
            values=[
                "ALL",
                "LIMIT",
                "MARKET",
                "STOP_LOSS",
                "STOP_LOSS_LIMIT",
                "TAKE_PROFIT",
                "TAKE_PROFIT_LIMIT",
                "LIMIT_MAKER",
                "OCO",
                "OTHER",
            ],
            state="readonly",
            width=18,
        )
        order_type_combo.grid(row=1, column=3, sticky="w", padx=5)

        # Bouton de récupération
        fetch_button = ttk.Button(controls, text="Récupérer transactions", command=self.on_fetch_clicked)
        fetch_button.grid(row=0, column=4, rowspan=2, padx=10, pady=5, sticky="ns")

        # Frame tableau
        table_frame = ttk.Frame(self, padding=5)
        table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = (
            "account_type",
            "symbol",
            "order_type",
            "side",
            "price",
            "qty",
            "quote_qty",
            "commission",
            "commission_asset",
            "time",
        )

        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        headings = {
            "account_type": "Compte",
            "symbol": "Symbole",
            "order_type": "Type ordre",
            "side": "Side",
            "price": "Prix",
            "qty": "Qte",
            "quote_qty": "Qte quote",
            "commission": "Commission",
            "commission_asset": "Comm. Asset",
            "time": "Date/Heure",
        }
        widths = {
            "account_type": 80,
            "symbol": 90,
            "order_type": 110,
            "side": 60,
            "price": 90,
            "qty": 90,
            "quote_qty": 100,
            "commission": 90,
            "commission_asset": 100,
            "time": 160,
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

    # ----------------- Actions -----------------

    def on_fetch_clicked(self):
        if self.client is None:
            messagebox.showerror("Erreur", "Client Binance non initialisé (clés API manquantes).")
            return

        if not (self.include_spot_var.get() or self.include_margin_var.get()):
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins un type de compte (Spot ou Margin).")
            return

        # Lancer la récupération dans un thread pour ne pas bloquer l'UI
        thread = threading.Thread(target=self._fetch_transactions_thread, daemon=True)
        thread.start()

    def _parse_date(self, s: str, default_start: bool) -> int | None:
        """
        Convertit 'YYYY-MM-DD' en timestamp ms.
        Si s est vide -> None.
        default_start :
            - True  -> time 00:00:00
            - False -> time 23:59:59
        """
        s = s.strip()
        if not s:
            return None
        try:
            d = datetime.strptime(s, "%Y-%m-%d")
            if default_start:
                dt = datetime(d.year, d.month, d.day, 0, 0, 0)
            else:
                dt = datetime(d.year, d.month, d.day, 23, 59, 59)
            return int(dt.timestamp() * 1000)
        except ValueError:
            raise ValueError(f"Date invalide : {s} (format attendu YYYY-MM-DD)")

    def _fetch_transactions_thread(self):
        try:
            self.status_var.set("Récupération des transactions en cours...")
            self._clear_table()
            self.trades_data = []

            # Dates
            start_ms = self._parse_date(self.start_date_var.get(), default_start=True)
            end_ms = self._parse_date(self.end_date_var.get(), default_start=False)

            if start_ms and end_ms and start_ms > end_ms:
                messagebox.showerror("Erreur", "La date de début est après la date de fin.")
                self.status_var.set("Erreur de dates.")
                return

            include_spot = self.include_spot_var.get()
            include_margin = self.include_margin_var.get()
            order_type_filter = self.order_type_var.get()

            # -------- SPOT --------
            if include_spot:
                self.status_var.set("Récupération des symboles SPOT...")
                self.update_idletasks()
                spot_symbols = self.client.guess_spot_symbols_for_user()

                self.status_var.set(f"SPOT: {len(spot_symbols)} symboles à scanner...")
                self.update_idletasks()

                spot_trades = []
                spot_orders_by_symbol = {}

                # 1) trades
                for i, sym in enumerate(spot_symbols, start=1):
                    self.status_var.set(f"SPOT: {i}/{len(spot_symbols)} - {sym}")
                    self.update_idletasks()
                    try:
                        trades = self.client.get_spot_trades_for_symbol(sym, start_ms, end_ms)
                    except Exception as e:
                        # On ignore les erreurs de symbole sans historique
                        print(f"Erreur trades spot {sym}: {e}")
                        continue
                    if trades:
                        spot_trades.extend((sym, t) for t in trades)

                # 2) orders (pour type d'ordre)
                # On ne cherche les orders que pour les symboles qui ont des trades
                symbols_with_trades = sorted({sym for sym, _ in spot_trades})
                for i, sym in enumerate(symbols_with_trades, start=1):
                    self.status_var.set(f"SPOT Orders: {i}/{len(symbols_with_trades)} - {sym}")
                    self.update_idletasks()
                    try:
                        orders = self.client.get_spot_orders_for_symbol(sym, start_ms, end_ms)
                    except Exception as e:
                        print(f"Erreur orders spot {sym}: {e}")
                        continue
                    spot_orders_by_symbol[sym] = orders

                self._append_trades("SPOT", spot_trades, spot_orders_by_symbol, order_type_filter)

            # -------- MARGIN --------
            if include_margin:
                self.status_var.set("Récupération des symboles MARGIN...")
                self.update_idletasks()
                margin_symbols = self.client.guess_margin_symbols_for_user()

                self.status_var.set(f"MARGIN: {len(margin_symbols)} symboles à scanner...")
                self.update_idletasks()

                margin_trades = []
                margin_orders_by_symbol = {}

                for i, sym in enumerate(margin_symbols, start=1):
                    self.status_var.set(f"MARGIN: {i}/{len(margin_symbols)} - {sym}")
                    self.update_idletasks()
                    try:
                        trades = self.client.get_margin_trades_for_symbol(sym, start_ms, end_ms)
                    except Exception as e:
                        print(f"Erreur trades margin {sym}: {e}")
                        continue
                    if trades:
                        margin_trades.extend((sym, t) for t in trades)

                symbols_with_trades = sorted({sym for sym, _ in margin_trades})
                for i, sym in enumerate(symbols_with_trades, start=1):
                    self.status_var.set(f"MARGIN Orders: {i}/{len(symbols_with_trades)} - {sym}")
                    self.update_idletasks()
                    try:
                        orders = self.client.get_margin_orders_for_symbol(sym, start_ms, end_ms)
                    except Exception as e:
                        print(f"Erreur orders margin {sym}: {e}")
                        continue
                    margin_orders_by_symbol[sym] = orders

                self._append_trades("MARGIN", margin_trades, margin_orders_by_symbol, order_type_filter)

            # Tri global par date
            self.trades_data.sort(key=lambda x: x["time"])

            # Affichage dans la table
            self._populate_table_from_trades()

            # Sauvegarde CSV
            filename = self._save_to_csv()
            self.status_var.set(f"Terminé. {len(self.trades_data)} transactions. Fichier : {filename}")

        except Exception as e:
            messagebox.showerror("Erreur", str(e))
            self.status_var.set("Erreur lors de la récupération des transactions.")

    # ----------------- Traitement & filtrage -----------------

    def _append_trades(self, account_type: str, trades_with_sym, orders_by_symbol, order_type_filter: str):
        """
        Ajoute les trades à self.trades_data avec fusion des info d'orders (type d'ordre).
        trades_with_sym : liste de tuples (symbol, trade_dict)
        orders_by_symbol : dict symbol -> liste orders
        order_type_filter : "ALL" ou nom d'un type d'ordre
        """
        # Map (symbol, orderId) -> type
        order_type_map = {}
        for sym, orders in orders_by_symbol.items():
            for o in orders:
                order_id = o.get("orderId")
                if order_id is None:
                    continue
                t = o.get("type", "OTHER")
                order_type_map[(sym, order_id)] = t

        for sym, t in trades_with_sym:
            order_id = t.get("orderId")
            o_type = order_type_map.get((sym, order_id), "UNKNOWN")

            # filtre type d'ordre (si voulu)
            if order_type_filter != "ALL":
                if o_type == "UNKNOWN":
                    continue
                if o_type != order_type_filter:
                    continue

            ts = t.get("time")
            dt = datetime.fromtimestamp(ts / 1000.0) if ts else None

            side = "BUY" if t.get("isBuyer") else "SELL"

            row = {
                "account_type": account_type,
                "symbol": sym,
                "order_type": o_type,
                "side": side,
                "price": t.get("price"),
                "qty": t.get("qty"),
                "quote_qty": t.get("quoteQty", ""),
                "commission": t.get("commission"),
                "commission_asset": t.get("commissionAsset"),
                "time": dt,
            }
            self.trades_data.append(row)

    # ----------------- Table & CSV -----------------

    def _clear_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _populate_table_from_trades(self):
        self._clear_table()
        for row in self.trades_data:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["account_type"],
                    row["symbol"],
                    row["order_type"],
                    row["side"],
                    row["price"],
                    row["qty"],
                    row["quote_qty"],
                    row["commission"],
                    row["commission_asset"],
                    row["time"].strftime("%Y-%m-%d %H:%M:%S") if row["time"] else "",
                ),
            )

    def _save_to_csv(self) -> str:
        if not self.trades_data:
            return "aucun_resultat.csv"

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"binance_transactions_{ts}.csv"

        fieldnames = [
            "account_type",
            "symbol",
            "order_type",
            "side",
            "price",
            "qty",
            "quote_qty",
            "commission",
            "commission_asset",
            "time",
        ]

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.trades_data:
                r = dict(row)
                r["time"] = r["time"].strftime("%Y-%m-%d %H:%M:%S") if r["time"] else ""
                writer.writerow(r)

        return filename


# ====================== MAIN ======================

def main():
    app = BinanceTransactionsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
