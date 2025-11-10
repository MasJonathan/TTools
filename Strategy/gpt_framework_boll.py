import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from dataclasses import dataclass
from typing import Optional, Literal, List
from abc import ABC, abstractmethod

import time

# ============================================================
# CONFIGURATION
# ============================================================

# DATA_FILE = "../Data/klines_INJUSDC_1m_from_2025_08_01.csv"
# DATA_FILE = "../Data/klines_INJUSDC_1m_from_2025_09_01.csv"
DATA_FILE = "../Data/klines_BTCUSDC_1m_from_2025_06_to_now.csv"
PERIOD = 100
BOLL_MULTIPLIER = 2
TREND_THRESHOLD = 0.3
INITIAL_CAPITAL = 100.0
TP_RANGE_RATIO = 0.75
SL_RANGE_RATIO = 1.1
MIN_TP_DISTANCE_PCT = 0.75  # distance minimale TP/entrée en %

# Nouveaux paramètres
TRADING_FEE_RATE = 0.001      # 0.1% par transaction (entrée / sortie) si 0.001
HOURLY_FUNDING_RATE = 0.0     # 0.01% par heure sur le notionnel si 0.0001
LEVERAGE = 1.0                # Effet de levier

Direction = Literal["long", "short"]


# ============================================================
# DATA & INDICATEURS
# ============================================================

class MarketData:
    """Encapsule le DataFrame de marché et le calcul des indicateurs."""

    def __init__(self, file_path: str, period: int, boll_multiplier: float, trend_thresh: float) -> None:
        self.file_path = file_path
        self.period = period
        self.boll_multiplier = boll_multiplier
        self.trend_thresh = trend_thresh
        self._df: Optional[pd.DataFrame] = None

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            raise ValueError("Les données ne sont pas encore chargées.")
        return self._df

    def load(self) -> None:
        df = pd.read_csv(self.file_path)
        df["open_time"] = pd.to_datetime(df["open_time"])
        df.set_index("open_time", inplace=True)
        num_cols = ["open", "high", "low", "close", "volume"]
        df[num_cols] = df[num_cols].astype(float)
        self._df = df

    def add_indicators(self) -> None:
        df = self.df
        df["sma"] = df["close"].rolling(window=self.period).mean()
        df["std"] = df["close"].rolling(window=self.period).std(ddof=0)
        df["upper"] = df["sma"] + self.boll_multiplier * df["std"]
        df["lower"] = df["sma"] - self.boll_multiplier * df["std"]
        df["tendency"] = df["sma"] - df["sma"].shift(1)
        df["tendency_pct"] = (df["tendency"] / df["sma"]) * 100
        df["trend"] = df["tendency_pct"].apply(self._classify_trend)

    def _classify_trend(self, tendency_pct: float) -> str:
        if pd.isna(tendency_pct):
            return "indet"
        if tendency_pct >= self.trend_thresh:
            return "bull"
        if tendency_pct <= -self.trend_thresh:
            return "bear"
        return "flat"


# ============================================================
# DOMAIN MODEL (Positions / Trades)
# ============================================================

@dataclass
class Position:
    entry_index: int
    entry_time: pd.Timestamp
    direction: Direction
    entry_price: float
    quantity: float
    mode: str  # "range" ou "trend"
    tp_level: Optional[float] = None
    sl_level: Optional[float] = None
    leverage: float = 1.0
    last_funding_time: Optional[pd.Timestamp] = None
    entry_fee: float = 0.0
    accumulated_funding: float = 0.0


@dataclass
class Trade:
    # Informations de base du trade
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    direction: Direction
    exit_type: str

    # Infos supplémentaires pour l’export
    quantity: float
    tp_level: Optional[float]
    sl_level: Optional[float]

    # Résultats financiers
    pnl: float           # PnL net (après tous les frais) en USD
    wallet_after: float  # Valeur du wallet après clôture du trade
    trading_fees: float  # Frais de transaction pour ce trade (entrée + sortie)
    funding_fees: float  # Frais de financement pour ce trade


# ============================================================
# STRATÉGIE (interface + implémentation)
# ============================================================

class Strategy(ABC):
    """Interface de stratégie : le moteur de backtest ne connaît que cette API."""

    @abstractmethod
    def generate_entry(
        self,
        i: int,
        row: pd.Series,
        prev_row: pd.Series,
        wallet: float,
    ) -> Optional[Position]:
        """Décide si une position doit être ouverte sur cette bougie."""
        ...

    @abstractmethod
    def check_exit(
        self,
        i: int,
        row: pd.Series,
        position: Position,
    ) -> tuple[Optional[float], Optional[str]]:
        """Décide si la position doit être clôturée sur cette bougie.
        Retourne (exit_price, exit_reason) ou (None, None)."""
        ...


class RangeTrendStrategy(Strategy):
    """Stratégie range / trend avec levier et filtre de variance minimale."""

    def __init__(
        self,
        tp_range_ratio: float,
        sl_range_ratio: float,
        min_tp_distance_pct: float,
        leverage: float,
    ) -> None:
        self.tp_range_ratio = tp_range_ratio
        self.sl_range_ratio = sl_range_ratio
        self.min_tp_distance_pct = min_tp_distance_pct
        self.leverage = leverage

    def generate_entry(
        self,
        i: int,
        row: pd.Series,
        prev_row: pd.Series,
        wallet: float,
    ) -> Optional[Position]:

        cross_up = (prev_row["close"] < prev_row["sma"]) and (row["close"] >= row["sma"])
        cross_down = (prev_row["close"] > prev_row["sma"]) and (row["close"] <= row["sma"])
        trend = row["trend"]

        # Pas assez d'historique ou NaN indicateurs
        if pd.isna(row["sma"]) or pd.isna(prev_row["sma"]):
            return None

        # Position sizing simple : all-in sur la marge, avec levier
        if wallet <= 0:
            return None

        notional = wallet * self.leverage
        qty = notional / row["close"]

        # Mode range
        if trend == "flat" and (cross_up or cross_down):
            tendency = row["tendency"]
            direction: Direction = "long" if tendency >= 0 else "short"
            mode = "range"

            if direction == "long":
                tp_level = row["close"] + self.tp_range_ratio * (row["upper"] - row["close"])
                sl_level = row["close"] - self.sl_range_ratio * (row["close"] - row["lower"])
            else:
                tp_level = row["close"] - self.tp_range_ratio * (row["close"] - row["lower"])
                sl_level = row["close"] + self.sl_range_ratio * (row["upper"] - row["close"])

            # Filtre de variance minimale en % entre entrée et TP
            expected_move_pct = abs(tp_level - row["close"]) / row["close"] * 100.0
            if expected_move_pct < self.min_tp_distance_pct:
                return None

            return Position(
                entry_index=i,
                entry_time=row.name,
                direction=direction,
                entry_price=row["close"],
                quantity=qty,
                mode=mode,
                tp_level=tp_level,
                sl_level=sl_level,
                leverage=self.leverage,
                last_funding_time=row.name,
            )

        # Mode tendance
        if trend == "bull" and cross_up:
            return Position(
                entry_index=i,
                entry_time=row.name,
                direction="long",
                entry_price=row["close"],
                quantity=qty,
                mode="trend",
                leverage=self.leverage,
                last_funding_time=row.name,
            )

        if trend == "bear" and cross_down:
            return Position(
                entry_index=i,
                entry_time=row.name,
                direction="short",
                entry_price=row["close"],
                quantity=qty,
                mode="trend",
                leverage=self.leverage,
                last_funding_time=row.name,
            )

        return None

    def check_exit(
        self,
        i: int,
        row: pd.Series,
        position: Position,
    ) -> tuple[Optional[float], Optional[str]]:

        # Mode range : TP/SL définis à l'entrée
        if position.mode == "range":
            if position.direction == "long":
                hit_tp = row["high"] >= position.tp_level
                hit_sl = row["low"] <= position.sl_level
            else:  # short
                hit_tp = row["low"] <= position.tp_level
                hit_sl = row["high"] >= position.sl_level

            if hit_tp or hit_sl:
                exit_price = position.tp_level if hit_tp else position.sl_level
                exit_reason = "tp" if hit_tp else "sl"
                return exit_price, exit_reason

        # Mode trend : SL sur les bandes + sortie si trend devient flat
        else:
            trend = row["trend"]
            if position.direction == "long" and row["low"] <= row["lower"]:
                return float(row["lower"]), "sl"
            if position.direction == "short" and row["high"] >= row["upper"]:
                return float(row["upper"]), "sl"
            if trend == "flat":
                return float(row["close"]), "tp_trend"

        return None, None


# ============================================================
# MOTEUR DE BACKTEST
# ============================================================

class BacktestEngine:
    """Moteur générique de backtest."""

    def __init__(
        self,
        data: pd.DataFrame,
        initial_capital: float,
        strategy: Strategy,
        trading_fee_rate: float,
        hourly_funding_rate: float,
    ) -> None:
        self.data = data
        self.initial_capital = initial_capital
        self.strategy = strategy
        self.trading_fee_rate = trading_fee_rate
        self.hourly_funding_rate = hourly_funding_rate

        self.wallet: float = initial_capital
        self.current_position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.equity_index: List[pd.Timestamp] = []

        self.total_trading_fees: float = 0.0
        self.total_funding_fees: float = 0.0

    def run(self) -> pd.Series:
        df = self.data

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]

            # Frais de financement sur la période précédente -> actuelle
            if self.current_position is not None:
                self._apply_funding_fee(row.name, row["close"])

            # Mark-to-market après financement
            equity = self._compute_mark_to_market(row)

            # Gestion des sorties
            if self.current_position is not None:
                exit_price, exit_reason = self.strategy.check_exit(i, row, self.current_position)
                if exit_reason is not None and exit_price is not None:
                    self._close_position(row.name, exit_price, exit_reason)
                    # Après clôture, equity = wallet cash
                    equity = self.wallet

            # Gestion des entrées
            if self.current_position is None:
                new_pos = self.strategy.generate_entry(i, row, prev_row, self.wallet)
                if new_pos is not None:
                    self._open_position(new_pos)

            # Enregistrement de l'equity à cette bougie
            self.equity_curve.append(equity)
            self.equity_index.append(row.name)

        return pd.Series(self.equity_curve, index=self.equity_index)

    def _compute_mark_to_market(self, row: pd.Series) -> float:
        """Calcule la valeur du portefeuille en mark-to-market."""
        if self.current_position is None:
            return self.wallet

        pos = self.current_position
        if pos.direction == "long":
            unrealized = (row["close"] - pos.entry_price) * pos.quantity
        else:
            unrealized = (pos.entry_price - row["close"]) * pos.quantity

        return self.wallet + unrealized

    def _open_position(self, position: Position) -> None:
        """Ouverture de position avec prélèvement des frais de transaction d'entrée."""
        notional = abs(position.quantity) * position.entry_price
        fee = notional * self.trading_fee_rate

        self.wallet -= fee
        self.total_trading_fees += fee

        position.entry_fee = fee
        position.last_funding_time = position.entry_time

        self.current_position = position

    def _close_position(self, exit_time: pd.Timestamp, exit_price: float, reason: str) -> None:
        pos = self.current_position
        if pos is None:
            return

        # PnL brut
        if pos.direction == "long":
            gross_pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            gross_pnl = (pos.entry_price - exit_price) * pos.quantity

        # Frais de sortie
        notional_exit = abs(pos.quantity) * exit_price
        exit_fee = notional_exit * self.trading_fee_rate

        trade_trading_fees = pos.entry_fee + exit_fee
        trade_funding_fees = pos.accumulated_funding

        self.total_trading_fees += exit_fee

        # entry_fee et funding déjà prélevés; on ajoute PnL brut puis on retire les frais de sortie
        self.wallet += gross_pnl
        self.wallet -= exit_fee

        net_pnl = gross_pnl - trade_trading_fees - trade_funding_fees

        trade = Trade(
            entry_time=pos.entry_time,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            direction=pos.direction,
            exit_type=reason,
            quantity=pos.quantity,
            tp_level=pos.tp_level,
            sl_level=pos.sl_level,
            pnl=net_pnl,
            wallet_after=self.wallet,
            trading_fees=trade_trading_fees,
            funding_fees=trade_funding_fees,
        )
        self.trades.append(trade)

        self.current_position = None

    def _apply_funding_fee(self, current_time: pd.Timestamp, current_price: float) -> None:
        """Applique un coût de financement proportionnel au notionnel et au temps de détention."""
        pos = self.current_position
        if pos is None or pos.last_funding_time is None:
            return

        dt = (current_time - pos.last_funding_time).total_seconds() / 3600.0
        if dt <= 0:
            return

        notional = abs(pos.quantity) * current_price
        fee = notional * self.hourly_funding_rate * dt

        self.wallet -= fee
        self.total_funding_fees += fee
        pos.accumulated_funding += fee

        pos.last_funding_time = current_time


# ============================================================
# PLOTTER
# ============================================================

class Plotter:
    def __init__(self, df: pd.DataFrame, equity_series: pd.Series, trades: List[Trade]) -> None:
        self.df = df
        self.equity_series = equity_series
        self.trades = trades

    def plot(self) -> None:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

        ax1.plot(self.df.index, self.df["close"], label="Close", color="blue", linewidth=1)
        ax1.plot(self.df.index, self.df["sma"], linestyle="--", label="SMA", color="orange")
        ax1.plot(self.df.index, self.df["upper"], linestyle=":", label="Upper", color="gray")
        ax1.plot(self.df.index, self.df["lower"], linestyle=":", label="Lower", color="gray")

        long_entries_x, long_entries_y = [], []
        short_entries_x, short_entries_y = [], []
        tp_x, tp_y, sl_x, sl_y = [], [], [], []

        for t in self.trades:
            if t.direction == "long":
                long_entries_x.append(t.entry_time)
                long_entries_y.append(t.entry_price)
            else:
                short_entries_x.append(t.entry_time)
                short_entries_y.append(t.entry_price)

            if t.exit_type in ["tp", "tp_trend"]:
                tp_x.append(t.exit_time)
                tp_y.append(t.exit_price)
            elif t.exit_type == "sl":
                sl_x.append(t.exit_time)
                sl_y.append(t.exit_price)

        ax1.scatter(long_entries_x, long_entries_y, marker="^", s=80, color="green", label="▲ Entry Long")
        ax1.scatter(short_entries_x, short_entries_y, marker="v", s=80, color="red", label="▼ Entry Short")
        ax1.scatter(tp_x, tp_y, marker="o", s=80, color="blue", label="● Take Profit")
        ax1.scatter(sl_x, sl_y, marker="x", s=80, color="black", label="✖ Stop Loss")

        ax1.set_ylabel("Prix")
        ax1.legend(loc="upper left")
        ax1.set_title("Backtest - Entrées et sorties (avec frais & levier)")

        ax2.plot(self.equity_series.index, self.equity_series.values, color="purple")
        ax2.set_ylabel("Valeur du portefeuille (USDC)")
        ax2.set_xlabel("Date")
        ax2.set_title("Évolution du portefeuille")

        plt.tight_layout()
        plt.show()


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    t_start = time.time()

    data = MarketData(DATA_FILE, PERIOD, BOLL_MULTIPLIER, TREND_THRESHOLD)
    data.load()
    data.add_indicators()

    strategy = RangeTrendStrategy(
        tp_range_ratio=TP_RANGE_RATIO,
        sl_range_ratio=SL_RANGE_RATIO,
        min_tp_distance_pct=MIN_TP_DISTANCE_PCT,
        leverage=LEVERAGE,
    )

    engine = BacktestEngine(
        data=data.df,
        initial_capital=INITIAL_CAPITAL,
        strategy=strategy,
        trading_fee_rate=TRADING_FEE_RATE,
        hourly_funding_rate=HOURLY_FUNDING_RATE,
    )

    equity = engine.run()

    # print("Capital initial :", INITIAL_CAPITAL)
    # print("Capital final   :", engine.wallet)
    # print("Frais de transaction totaux :", engine.total_trading_fees)
    # print("Frais de funding totaux     :", engine.total_funding_fees)

    if engine.trades:
        trades_df = pd.DataFrame([t.__dict__ for t in engine.trades])


        trades_df.insert(0, "index", range(len(trades_df)))
        trades_df["date"] = trades_df["entry_time"]
        trades_df["amount_usd"] = trades_df["entry_price"].abs() * trades_df["quantity"].abs()
        trades_df["executed_level"] = trades_df["exit_type"].map({"tp": "tp", "tp_trend": "tp", "sl": "sl"}).fillna(trades_df["exit_type"])
        trades_df["pnl_pct"] = np.where(trades_df["amount_usd"] != 0, trades_df["pnl"] / trades_df["amount_usd"] * 100.0, 0.0)


        cols_order = [
        "index", "date", "direction", "amount_usd", "entry_price", "exit_price", "tp_level", "sl_level",
        "executed_level", "pnl", "pnl_pct", "wallet_after", "trading_fees", "funding_fees",
        "entry_time", "exit_time", "quantity", "exit_type"
        ]
        trades_df = trades_df[[c for c in cols_order if c in trades_df.columns]]


        csv_path = "executed_orders.csv"
        trades_df.to_csv(csv_path, index=False)


        # ==============================
        # COMPTE RENDU DÉTAILLÉ (.TXT)
        # ==============================


        nb_trades = len(trades_df)
        win_trades = trades_df[trades_df["pnl"] > 0]
        loss_trades = trades_df[trades_df["pnl"] <= 0]


        win_rate = (len(win_trades) / nb_trades) * 100 if nb_trades > 0 else 0
        avg_win = win_trades["pnl_pct"].mean() if not win_trades.empty else 0
        avg_loss = loss_trades["pnl_pct"].mean() if not loss_trades.empty else 0
        best_trade = trades_df.loc[trades_df["pnl_pct"].idxmax()] if not trades_df.empty else None
        worst_trade = trades_df.loc[trades_df["pnl_pct"].idxmin()] if not trades_df.empty else None


        report_lines = []
        report_lines.append("===== RAPPORT DE BACKTEST {pd.Timestamp.now()} =====")
        report_lines.append("")
        report_lines.append(f"Wallet : {INITIAL_CAPITAL:.2f}$ -> {engine.wallet:.2f}$")
        report_lines.append(f"Trades : {nb_trades}")
        report_lines.append(f"WinRate : {win_rate:.2f}%")
        report_lines.append("")
        report_lines.append(f"Avg win  (%) : {avg_win:.2f}")
        report_lines.append(f"Avg loss (%) : {avg_loss:.2f}")
        report_lines.append("")
        report_lines.append(f"Total fees : {engine.total_trading_fees:.4f} USDT")
        report_lines.append(f"Total leverage fees : {engine.total_funding_fees:.4f} USDT")
        report_lines.append("")

        if best_trade is not None:
            report_lines.append("--- Meilleur Trade ---")
            report_lines.append(f"\t{best_trade['entry_time']} Entrée : {best_trade['entry_price']:.4f} {best_trade['direction']}, Sortie : {best_trade['exit_price']:.4f} {best_trade['executed_level']} PnL : {best_trade['pnl']:.2f} USDT ({best_trade['pnl_pct']:.2f}%)")
        if worst_trade is not None:
            report_lines.append("--- Pire Trade ---")
            report_lines.append(f"\t{worst_trade['entry_time']} Entrée : {worst_trade['entry_price']:.4f} {worst_trade['direction']}, Sortie : {worst_trade['exit_price']:.4f} {worst_trade['executed_level']} PnL : {worst_trade['pnl']:.2f} USDT ({worst_trade['pnl_pct']:.2f}%)")
        
        report_lines.append("")
        report_lines.append("===== FIN DU RAPPORT =====")


        report_path = "backtest_report.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            s = "\n".join(report_lines)
            f.write(s)
            print(s)


        print(f"\nCompte rendu exporté dans : {report_path}")
    print(f"Done in {time.time() - t_start:.2f} s")
    plotter = Plotter(data.df, equity, engine.trades)
    plotter.plot()


if __name__ == "__main__":
    main()
