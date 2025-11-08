import os
import time
import hmac
import json
import hashlib
import threading
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class BinanceClient:
    BASE_URL = "https://api.binance.com"
    WEIGHT_LIMIT_1M = 1200
    SAFETY_MARGIN = 50  # security margin before hitting the limit

    def __init__(self, api_key: str, api_secret: str):
        if not api_key or not api_secret:
            raise RuntimeError(
                "Missing API keys in environment variables 'binance_api' and/or 'binance_secret'"
            )
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})
        self.time_offset_ms = 0
        self._sync_time()

    def _sync_time(self):
        try:
            url = self.BASE_URL + "/api/v3/time"
            resp = self.session.get(url, timeout=5)
            resp.raise_for_status()
            server_time = int(resp.json().get("serverTime"))
            local_time = int(time.time() * 1000)
            self.time_offset_ms = server_time - local_time
        except Exception:
            self.time_offset_ms = 0

    def _sign_params(self, params: dict) -> dict:
        if params is None:
            params = {}
        params = dict(params)
        ts = int(time.time() * 1000 + self.time_offset_ms)
        params["timestamp"] = ts
        if "recvWindow" not in params:
            params["recvWindow"] = 60000
        query_string = urlencode(params, doseq=True)
        signature = hmac.new(
            self.api_secret, query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _handle_rate_limits(self, headers: dict):
        used_weight = headers.get("X-MBX-USED-WEIGHT-1M") or headers.get(
            "x-mbx-used-weight-1m", "0"
        )
        try:
            used_weight = int(used_weight)
        except ValueError:
            used_weight = 0

        if used_weight >= self.WEIGHT_LIMIT_1M - self.SAFETY_MARGIN:
            time.sleep(60)

    def _send_request(self, method: str, path: str, params=None, signed: bool = False):
        if params is None:
            params = {}
        url = self.BASE_URL + path
        orig_params = dict(params)

        if signed:
            params = self._sign_params(orig_params)

        while True:
            if method.upper() == "GET":
                response = self.session.get(url, params=params, timeout=15)
            else:
                raise ValueError("Only GET is implemented")

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    retry_after = int(retry_after)
                except (TypeError, ValueError):
                    retry_after = 60
                time.sleep(retry_after)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as e:
                extra = ""
                try:
                    err = response.json()
                    if err.get("code") == -1021:
                        self._sync_time()
                    extra = f" (Binance code {err.get('code')}, msg: {err.get('msg')})"
                except Exception:
                    extra = f" (body: {response.text})"
                raise requests.HTTPError(str(e) + extra) from e

            self._handle_rate_limits(response.headers)
            return response.json(), response.headers

    def get_account_snapshot(
        self,
        account_type: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 30,
    ) -> dict:
        params = {
            "type": account_type.upper(),
            "startTime": start_time_ms,
            "endTime": end_time_ms,
            "limit": limit,
        }
        data, _ = self._send_request(
            "GET", "/sapi/v1/accountSnapshot", params=params, signed=True
        )
        return data

    def get_daily_klines(
        self,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
    ):
        params = {
            "symbol": symbol.upper(),
            "interval": "1d",
            "startTime": start_time_ms,
            "endTime": end_time_ms,
        }
        data, _ = self._send_request(
            "GET", "/api/v3/klines", params=params, signed=False
        )
        return data

    def get_btc_daily_prices(
        self, target_currency: str, start_date, end_date
    ) -> dict:
        target_currency = target_currency.upper()
        start_time_ms = int(
            datetime.combine(start_date, datetime.min.time()).timestamp() * 1000
        )
        end_time_ms = int(
            datetime.combine(end_date + timedelta(days=1), datetime.min.time()).timestamp()
            * 1000
        )

        symbol = f"BTC{target_currency}"
        invert = False
        prices = {}

        try:
            klines = self.get_daily_klines(symbol, start_time_ms, end_time_ms)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                symbol = f"{target_currency}BTC"
                invert = True
                klines = self.get_daily_klines(symbol, start_time_ms, end_time_ms)
            else:
                raise

        for k in klines:
            open_time_ms = int(k[0])
            close_price = float(k[4])
            date = datetime.utcfromtimestamp(open_time_ms / 1000.0).date()
            if invert:
                if close_price != 0:
                    close_price = 1.0 / close_price
                else:
                    close_price = 0.0
            prices[date] = close_price

        return prices


class SnapshotManager:
    def __init__(self, client: BinanceClient):
        self.client = client

    def fetch_snapshots(self, start_date, end_date, account_types, progress_callback=None):
        all_rows = []
        for account_type in account_types:
            current_start = start_date
            while current_start <= end_date:
                current_end = min(current_start + timedelta(days=29), end_date)
                start_ms = int(
                    datetime.combine(
                        current_start, datetime.min.time()
                    ).timestamp()
                    * 1000
                )
                end_ms = int(
                    datetime.combine(
                        current_end + timedelta(days=1), datetime.min.time()
                    ).timestamp()
                    * 1000
                )

                data = self.client.get_account_snapshot(
                    account_type, start_ms, end_ms, limit=30
                )

                for vo in data.get("snapshotVos", []):
                    row = {
                        "account_type": account_type.upper(),
                        "updateTime": vo.get("updateTime"),
                        "data": vo.get("data", {}),
                    }
                    all_rows.append(row)

                if progress_callback is not None:
                    progress_callback()

                current_start = current_end + timedelta(days=1)

        return all_rows

    @staticmethod
    def _extract_btc_components(account_type: str, data: dict):
        account_type = account_type.upper()
        asset = liability = net = None

        if account_type == "SPOT":
            asset = float(data.get("totalAssetOfBtc", 0.0))
            liability = float(data.get("totalLiabilityOfBtc", 0.0)) if "totalLiabilityOfBtc" in data else 0.0
            if "totalNetAssetOfBtc" in data:
                net = float(data.get("totalNetAssetOfBtc", 0.0))
            else:
                net = asset - liability
        elif account_type == "MARGIN":
            asset = float(data.get("totalAssetOfBtc", 0.0))
            liability = float(data.get("totalLiabilityOfBtc", 0.0))
            if "totalNetAssetOfBtc" in data:
                net = float(data.get("totalNetAssetOfBtc", 0.0))
            else:
                net = asset - liability
        elif account_type == "FUTURES":
            # adapter ici si besoin pour les futures
            asset = float(data.get("totalAssetOfBtc", 0.0)) if "totalAssetOfBtc" in data else None
            liability = float(data.get("totalLiabilityOfBtc", 0.0)) if "totalLiabilityOfBtc" in data else None
            net = float(data.get("totalNetAssetOfBtc", 0.0)) if "totalNetAssetOfBtc" in data else None

        return asset, liability, net

    def build_dataframe(
        self, raw_rows, start_date, end_date, target_currency: str
    ) -> pd.DataFrame:
        if not raw_rows:
            return pd.DataFrame(
                columns=[
                    "date",
                    "account_type",
                    "totalAssetOfBtc",
                    "totalLiabilityOfBtc",
                    "totalNetAssetOfBtc",
                    "totalAssetInCurrency",
                    "totalLiabilityInCurrency",
                    "totalNetAssetInCurrency",
                    "dailyNetAssetChangeInCurrency",
                    "target_currency",
                    "raw_data",
                ]
            )

        records = []
        for row in raw_rows:
            update_ms = row.get("updateTime")
            if update_ms is None:
                continue
            update_dt = datetime.utcfromtimestamp(update_ms / 1000.0)
            date = update_dt.date()
            data = row.get("data", {})
            account_type = row.get("account_type", "").upper()

            asset_btc, liability_btc, net_btc = self._extract_btc_components(account_type, data)

            records.append(
                {
                    "date": date,
                    "account_type": account_type,
                    "totalAssetOfBtc": asset_btc,
                    "totalLiabilityOfBtc": liability_btc,
                    "totalNetAssetOfBtc": net_btc,
                    "raw_data": json.dumps(data),
                }
            )

        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame(
                columns=[
                    "date",
                    "account_type",
                    "totalAssetOfBtc",
                    "totalLiabilityOfBtc",
                    "totalNetAssetOfBtc",
                    "totalAssetInCurrency",
                    "totalLiabilityInCurrency",
                    "totalNetAssetInCurrency",
                    "dailyNetAssetChangeInCurrency",
                    "target_currency",
                    "raw_data",
                ]
            )

        df.sort_values(["account_type", "date"], inplace=True)
        df.reset_index(drop=True, inplace=True)

        btc_prices = self.client.get_btc_daily_prices(
            target_currency, start_date, end_date
        )

        def get_rate_for_date(d):
            if not btc_prices:
                return None
            current = d
            while current >= start_date:
                if current in btc_prices:
                    return btc_prices[current]
                current -= timedelta(days=1)
            return None

        df["target_currency"] = target_currency.upper()
        df["btc_to_target"] = df["date"].apply(get_rate_for_date)

        def conv(x, rate):
            if x is None or pd.isna(x) or rate is None or pd.isna(rate):
                return None
            return float(x) * float(rate)

        df["totalAssetInCurrency"] = [
            conv(a, r) for a, r in zip(df["totalAssetOfBtc"], df["btc_to_target"])
        ]
        df["totalLiabilityInCurrency"] = [
            conv(l, r) for l, r in zip(df["totalLiabilityOfBtc"], df["btc_to_target"])
        ]
        df["totalNetAssetInCurrency"] = [
            conv(n, r) for n, r in zip(df["totalNetAssetOfBtc"], df["btc_to_target"])
        ]

        df["dailyNetAssetChangeInCurrency"] = (
            df.groupby("account_type")["totalNetAssetInCurrency"].diff()
        )

        return df[
            [
                "date",
                "account_type",
                "totalAssetOfBtc",
                "totalLiabilityOfBtc",
                "totalNetAssetOfBtc",
                "totalAssetInCurrency",
                "totalLiabilityInCurrency",
                "totalNetAssetInCurrency",
                "dailyNetAssetChangeInCurrency",
                "target_currency",
                "raw_data",
            ]
        ]


class SnapshotApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Binance Daily Snapshots Downloader")
        self.geometry("1200x650")

        api_key = os.getenv("binance_api")
        api_secret = os.getenv("binance_secret")

        self.client = BinanceClient(api_key, api_secret)
        self.manager = SnapshotManager(self.client)
        self.df = None

        self._create_widgets()

    def _create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        params_frame = ttk.LabelFrame(main_frame, text="Paramètres")
        params_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(params_frame, text="Date début (YYYY-MM-DD) *").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=2
        )
        self.start_date_var = tk.StringVar()
        ttk.Entry(params_frame, textvariable=self.start_date_var, width=15).grid(
            row=0, column=1, sticky=tk.W, padx=5, pady=2
        )

        ttk.Label(params_frame, text="Date fin (YYYY-MM-DD)").grid(
            row=0, column=2, sticky=tk.W, padx=5, pady=2
        )
        self.end_date_var = tk.StringVar()
        ttk.Entry(params_frame, textvariable=self.end_date_var, width=15).grid(
            row=0, column=3, sticky=tk.W, padx=5, pady=2
        )

        accounts_frame = ttk.LabelFrame(params_frame, text="Types de comptes")
        accounts_frame.grid(row=1, column=0, columnspan=4, sticky=tk.W, padx=5, pady=5)

        self.spot_var = tk.BooleanVar(value=True)
        self.margin_var = tk.BooleanVar(value=True)
        self.futures_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            accounts_frame, text="Spot", variable=self.spot_var
        ).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(
            accounts_frame, text="Margin", variable=self.margin_var
        ).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(
            accounts_frame, text="Futures", variable=self.futures_var
        ).pack(side=tk.LEFT, padx=5)

        ttk.Label(params_frame, text="Devise de sortie").grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=2
        )
        self.currency_var = tk.StringVar(value="USDC")
        ttk.Entry(params_frame, textvariable=self.currency_var, width=10).grid(
            row=2, column=1, sticky=tk.W, padx=5, pady=2
        )
        ttk.Label(
            params_frame, text="(ex: USDC, BTC, EUR ou autre)"
        ).grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=5, pady=2)

        buttons_frame = ttk.Frame(params_frame)
        buttons_frame.grid(row=3, column=0, columnspan=4, sticky=tk.W, padx=5, pady=5)

        self.download_button = ttk.Button(
            buttons_frame, text="Télécharger snapshots", command=self.on_download
        )
        self.download_button.pack(side=tk.LEFT, padx=5)

        # Bouton conservé si on veut ré-exporter manuellement
        self.export_button = ttk.Button(
            buttons_frame, text="Exporter CSV", command=self.on_export
        )
        self.export_button.pack(side=tk.LEFT, padx=5)

        self.status_var = tk.StringVar(value="")
        ttk.Label(main_frame, textvariable=self.status_var).pack(
            fill=tk.X, padx=5, pady=5
        )

        self.progress = ttk.Progressbar(
            main_frame, orient="horizontal", mode="determinate", maximum=100
        )
        self.progress.pack(fill=tk.X, padx=5, pady=5)

        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = (
            "date",
            "account_type",
            "totalAssetOfBtc",
            "totalLiabilityOfBtc",
            "totalNetAssetOfBtc",
            "totalAssetInCurrency",
            "totalLiabilityInCurrency",
            "totalNetAssetInCurrency",
            "dailyNetAssetChangeInCurrency",
        )
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=20
        )
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=130, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        hsb = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

    def set_status(self, text: str):
        self.status_var.set(text)
        self.update_idletasks()

    def _update_progress(self, percent, step, total_steps):
        self.progress["value"] = percent
        self.status_var.set(
            f"Téléchargement en cours... ({step}/{total_steps})"
        )
        self.update_idletasks()

    def on_download(self):
        start_str = self.start_date_var.get().strip()
        end_str = self.end_date_var.get().strip()
        currency = self.currency_var.get().strip().upper() or "USDC"

        if not start_str:
            messagebox.showerror("Erreur", "La date de début est obligatoire.")
            return

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Erreur", "Format de date de début invalide.")
            return

        if end_str:
            try:
                end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            except ValueError:
                messagebox.showerror("Erreur", "Format de date de fin invalide.")
                return
        else:
            end_date = datetime.utcnow().date()

        if end_date < start_date:
            messagebox.showerror(
                "Erreur", "La date de fin doit être >= à la date de début."
            )
            return

        account_types = []
        if self.spot_var.get():
            account_types.append("SPOT")
        if self.margin_var.get():
            account_types.append("MARGIN")
        if self.futures_var.get():
            account_types.append("FUTURES")

        if not account_types:
            messagebox.showerror(
                "Erreur", "Sélectionnez au moins un type de compte."
            )
            return

        self.download_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.set_status("Téléchargement en cours...")

        thread = threading.Thread(
            target=self._download_worker,
            args=(start_date, end_date, account_types, currency),
            daemon=True,
        )
        thread.start()

    def _download_worker(self, start_date, end_date, account_types, currency):
        days = (end_date - start_date).days + 1
        calls_per_account = (days + 29) // 30
        total_steps = max(1, calls_per_account * len(account_types))
        steps_done = 0

        def progress_callback():
            nonlocal steps_done
            steps_done += 1
            pct = steps_done / total_steps * 100.0
            self.after(
                0,
                lambda p=pct, s=steps_done, t=total_steps: self._update_progress(
                    p, s, t
                ),
            )

        try:
            raw_rows = self.manager.fetch_snapshots(
                start_date, end_date, account_types, progress_callback=progress_callback
            )
            df = self.manager.build_dataframe(
                raw_rows, start_date, end_date, currency
            )
            self.df = df
            self.after(0, self._update_treeview)
            self.after(0, self._auto_export_csv)
            self.after(0, lambda: self.set_status("Téléchargement terminé."))
            self.after(0, lambda: self.progress.config(value=100))
        except Exception as e:
            self.after(
                0,
                lambda: messagebox.showerror(
                    "Erreur",
                    f"Erreur lors du téléchargement des snapshots:\n{e}",
                ),
            )
            self.after(0, lambda: self.set_status("Erreur."))
            self.after(0, lambda: self.progress.config(value=0))
        finally:
            self.after(
                0, lambda: self.download_button.config(state=tk.NORMAL)
            )
            self.after(
                0, lambda: self.export_button.config(state=tk.NORMAL)
            )

    def _update_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if self.df is None or self.df.empty:
            return

        for _, row in self.df.iterrows():
            def fmt(x, digits=8):
                if pd.isna(x) or x is None:
                    return ""
                if isinstance(x, float):
                    return f"{x:.{digits}f}"
                return str(x)

            self.tree.insert(
                "",
                tk.END,
                values=(
                    str(row["date"]),
                    row["account_type"],
                    fmt(row["totalAssetOfBtc"]),
                    fmt(row["totalLiabilityOfBtc"]),
                    fmt(row["totalNetAssetOfBtc"]),
                    fmt(row["totalAssetInCurrency"], 4),
                    fmt(row["totalLiabilityInCurrency"], 4),
                    fmt(row["totalNetAssetInCurrency"], 4),
                    fmt(row["dailyNetAssetChangeInCurrency"], 4),
                ),
            )

    def _auto_export_csv(self):
        if self.df is None or self.df.empty:
            return

        default_name = f"snapshots_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Enregistrer le fichier CSV",
        )
        if not filepath:
            return

        try:
            self.df.to_csv(filepath, index=False)
            messagebox.showinfo(
                "Succès", f"Export CSV terminé :\n{filepath}"
            )
        except Exception as e:
            messagebox.showerror(
                "Erreur", f"Erreur lors de l'export CSV:\n{e}"
            )

    def on_export(self):
        # réutilise l'export automatique mais déclenché manuellement
        self._auto_export_csv()


if __name__ == "__main__":
    app = SnapshotApp()
    app.mainloop()
