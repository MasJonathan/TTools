import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# PARAMÈTRES GLOBAUX (facilement modifiables)
# ============================================================

file_path = "../Data/klines_INJUSDC_1m_from_2025_09_01.csv"
# file_path = "../Data/klines_INJUSDC_1m_from_2025_06_01.csv"
# file_path = "../Data/klines_INJUSDC_1m_from_2025.csv"
# file_path = "../Data/klines_INJUSDC_1m_from_beginning_to_now.csv"
DATA_FILE = file_path
PERIOD = 100
BOLL_MULTIPLIER = 2
TREND_THRESHOLD = 0.5
INITIAL_CAPITAL = 100.0
TP_RANGE_RATIO = 0.9


# ============================================================
# CLASSES
# ============================================================

class DataHandler:
    def __init__(self, file_path, period, boll_multiplier, trend_thresh):
        self.file_path = file_path
        self.period = period
        self.boll_multiplier = boll_multiplier
        self.trend_thresh = trend_thresh
        self.df = None

    def load_data(self):
        df = pd.read_csv(self.file_path)
        df["open_time"] = pd.to_datetime(df["open_time"])
        df.set_index("open_time", inplace=True)
        num_cols = ["open", "high", "low", "close", "volume"]
        df[num_cols] = df[num_cols].astype(float)
        self.df = df

    def compute_indicators(self):
        df = self.df
        df["sma"] = df["close"].rolling(window=self.period).mean()
        df["std"] = df["close"].rolling(window=self.period).std(ddof=0)
        df["upper"] = df["sma"] + self.boll_multiplier * df["std"]
        df["lower"] = df["sma"] - self.boll_multiplier * df["std"]
        df["tendency"] = df["sma"] - df["sma"].shift(1)
        df["tendency_pct"] = (df["tendency"] / df["sma"]) * 100
        df["trend"] = df.apply(self._classify_trend, axis=1)
        self.df = df

    def _classify_trend(self, row):
        if pd.isna(row["tendency_pct"]):
            return "indet"
        if row["tendency_pct"] >= self.trend_thresh:
            return "bull"
        if row["tendency_pct"] <= -self.trend_thresh:
            return "bear"
        return "flat"


class BacktestEngine:
    def __init__(self, df, initial_capital, tp_ratio):
        self.df = df
        self.initial_capital = initial_capital
        self.tp_ratio = tp_ratio
        self.wallet = initial_capital
        self.position = 0
        self.entry_price = None
        self.quantity = 0.0
        self.entry_mode = None
        self.direction = None
        self.tp_level = None
        self.sl_level = None
        self.trade_log = []
        self.equity_curve = []
        self.equity_index = []

    def run(self):
        df = self.df
        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]
            self._update_equity(row)
            if self.position == 0:
                self._check_entry(row, prev_row, i)
        return self._finalize_equity()

    def _update_equity(self, row):
        equity = self.wallet
        if self.position != 0:
            exit_price, exit_reason = self._check_exit(row)
            if exit_reason:
                pnl = (exit_price - self.entry_price) * self.quantity if self.position == 1 else (self.entry_price - exit_price) * self.quantity
                self.wallet += pnl
                self.trade_log.append({
                    "entry_price": self.entry_price,
                    "exit_price": exit_price,
                    "direction": "long" if self.position == 1 else "short",
                    "exit_type": exit_reason,
                    "pnl": pnl,
                    "wallet": self.wallet
                })
                self._reset_position()
            else:
                if self.position == 1:
                    equity = self.wallet + (row["close"] - self.entry_price) * self.quantity
                elif self.position == -1:
                    equity = self.wallet + (self.entry_price - row["close"]) * self.quantity
        self.equity_curve.append(equity)
        self.equity_index.append(row.name)

    def _check_exit(self, row):
        exit_reason = None
        exit_price = None

        # Mode range
        if self.entry_mode == "range":
            if self.position == 1:
                hit_tp = row["high"] >= self.tp_level
                hit_sl = row["low"] <= self.sl_level
            else:
                hit_tp = row["low"] <= self.tp_level
                hit_sl = row["high"] >= self.sl_level
            if hit_tp or hit_sl:
                exit_price = self.tp_level if hit_tp else self.sl_level
                exit_reason = "tp" if hit_tp else "sl"

        # Mode tendance
        elif self.entry_mode == "trend":
            trend = row["trend"]
            if self.position == 1 and row["low"] <= row["lower"]:
                exit_price = row["lower"]
                exit_reason = "sl"
            elif self.position == -1 and row["high"] >= row["upper"]:
                exit_price = row["upper"]
                exit_reason = "sl"
            elif trend == "flat":
                exit_price = row["close"]
                exit_reason = "tp_trend"

        return exit_price, exit_reason

    def _check_entry(self, row, prev_row, i):
        cross_up = (prev_row["close"] < prev_row["sma"]) and (row["close"] >= row["sma"])
        cross_down = (prev_row["close"] > prev_row["sma"]) and (row["close"] <= row["sma"])
        trend = row["trend"]

        if trend == "flat" and (cross_up or cross_down):
            tendency = row["tendency"]
            self.position = 1 if tendency >= 0 else -1
            self.direction = "long" if self.position == 1 else "short"
            self.entry_price = row["close"]
            self.quantity = self.wallet / self.entry_price
            self.entry_mode = "range"
            if self.position == 1:
                self.tp_level = self.entry_price + self.tp_ratio * (row["upper"] - self.entry_price)
                self.sl_level = row["lower"]
            else:
                self.tp_level = self.entry_price - self.tp_ratio * (self.entry_price - row["lower"])
                self.sl_level = row["upper"]

        elif trend == "bull" and cross_up:
            self.position = 1
            self.direction = "long"
            self.entry_price = row["close"]
            self.quantity = self.wallet / self.entry_price
            self.entry_mode = "trend"

        elif trend == "bear" and cross_down:
            self.position = -1
            self.direction = "short"
            self.entry_price = row["close"]
            self.quantity = self.wallet / self.entry_price
            self.entry_mode = "trend"

    def _reset_position(self):
        self.position = 0
        self.entry_price = None
        self.quantity = 0.0
        self.entry_mode = None
        self.direction = None
        self.tp_level = None
        self.sl_level = None

    def _finalize_equity(self):
        return pd.Series(self.equity_curve, index=self.equity_index)


class Plotter:
    def __init__(self, df, equity_series, trades):
        self.df = df
        self.equity_series = equity_series
        self.trades = trades

    def plot(self):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

        # Prix + bandes
        ax1.plot(self.df.index, self.df["close"], label="Close", color="blue", linewidth=1)
        ax1.plot(self.df.index, self.df["sma"], linestyle="--", label="SMA", color="orange")
        ax1.plot(self.df.index, self.df["upper"], linestyle=":", label="Upper", color="gray")
        ax1.plot(self.df.index, self.df["lower"], linestyle=":", label="Lower", color="gray")

        # Tracés d'entrées et de sorties
        long_entries_x, long_entries_y = [], []
        short_entries_x, short_entries_y = [], []
        tp_x, tp_y, sl_x, sl_y = [], [], [], []

        for t in self.trades:
            entry_x = self.df.index[self.df["close"] == t["entry_price"]].tolist()
            if not entry_x:
                continue
            entry_time = entry_x[0]
            if t["direction"] == "long":
                long_entries_x.append(entry_time)
                long_entries_y.append(t["entry_price"])
            else:
                short_entries_x.append(entry_time)
                short_entries_y.append(t["entry_price"])

            if t["exit_type"] in ["tp", "tp_trend"]:
                tp_x.append(entry_time)
                tp_y.append(t["exit_price"])
            elif t["exit_type"] == "sl":
                sl_x.append(entry_time)
                sl_y.append(t["exit_price"])

        # Ajout des symboles sur le graphique
        ax1.scatter(long_entries_x, long_entries_y, marker="^", s=80, color="green", label="▲ Entry Long")
        ax1.scatter(short_entries_x, short_entries_y, marker="v", s=80, color="red", label="▼ Entry Short")
        ax1.scatter(tp_x, tp_y, marker="o", s=80, color="blue", label="● Take Profit")
        ax1.scatter(sl_x, sl_y, marker="x", s=80, color="black", label="✖ Stop Loss")

        ax1.set_ylabel("Prix")
        ax1.legend(loc="upper left")
        ax1.set_title("Backtest - Entrées et sorties (symboles simplifiés)")

        # Équity curve
        ax2.plot(self.equity_series.index, self.equity_series.values, color="purple")
        ax2.set_ylabel("Valeur du portefeuille (USDC)")
        ax2.set_xlabel("Date")
        ax2.set_title("Évolution du portefeuille")

        plt.tight_layout()
        plt.show()


# ============================================================
# EXÉCUTION DU PROGRAMME
# ============================================================

if __name__ == "__main__":
    data = DataHandler(DATA_FILE, PERIOD, BOLL_MULTIPLIER, TREND_THRESHOLD)
    data.load_data()
    data.compute_indicators()

    bt = BacktestEngine(data.df, INITIAL_CAPITAL, TP_RANGE_RATIO)
    equity = bt.run()

    print("Capital initial :", INITIAL_CAPITAL)
    print("Capital final   :", bt.wallet)
    if bt.trade_log:
        df_trades = pd.DataFrame(bt.trade_log)
        print("Nombre de trades :", len(df_trades))
        print("Taux de réussite :", (df_trades[df_trades["pnl"] > 0].shape[0] / len(df_trades)) * 100, "%")

    plot = Plotter(data.df, equity, bt.trade_log)
    plot.plot()
