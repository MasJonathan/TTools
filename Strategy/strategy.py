import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import argparse
from dataclasses import dataclass, asdict
from typing import List, Optional
import matplotlib.dates as mdates
from typing import List

# =============================
# Data structures
# =============================

@dataclass
class Trade:
    direction: str  # 'long' or 'short'
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    qty: float
    r_multiple: float
    pnl: float
    pnl_pct: float


# =============================
# Indicator functions
# =============================

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    gain = pd.Series(gain, index=series.index)
    loss = pd.Series(loss, index=series.index)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Wilder smoothing
    avg_gain = avg_gain.shift(1).ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = avg_loss.shift(1).ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


# =============================
# Backtest core
# =============================

def load_klines_csv(path: str, timeframe: str = "1T") -> pd.DataFrame:
    """Load Binance kline CSV (1m) and resample to target timeframe.

    Expected columns (typical Binance export):
    [open_time, open, high, low, close, volume, close_time, ...]
    """
    df = pd.read_csv(path)

    # Try to infer time column and set index
    if "open_time" in df.columns:
        try:
            # Essayer de convertir comme timestamp Unix (ms)
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        except (ValueError, TypeError):
            # Sinon, essayer une conversion classique de chaînes de caractères
            df["open_time"] = pd.to_datetime(df["open_time"], errors='coerce')
        df.set_index("open_time", inplace=True)
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
    else:
        raise ValueError("Impossible de trouver une colonne de temps (open_time ou date)")

    # Ensure numeric columns
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[["open", "high", "low", "close", "volume"]].dropna()

    # Resample
    ohlc = df[["open", "high", "low", "close"]].resample(timeframe).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    })
    vol = df["volume"].resample(timeframe).sum()

    resampled = ohlc.copy()
    resampled["volume"] = vol
    resampled.dropna(inplace=True)

    return resampled


def generate_signals_1(
    df: pd.DataFrame,
    ema_fast: int = 1,
    ema_slow: int = 60,
    rsi_period: int = 5,
    rsi_pullback: float = 35.0,
    rsi_momentum: float = 35.0,
    lookback_pullback: int = 5,
) -> pd.DataFrame:
    """Ajoute EMA, RSI et signaux long / short au DataFrame."""
    df = df.copy()
    df["ema_fast"] = ema(df["close"], ema_fast)
    df["ema_slow"] = ema(df["close"], ema_slow)
    df["rsi"] = rsi(df["close"], rsi_period)

    df["trend_long"] = df["ema_fast"] > df["ema_slow"]
    df["trend_short"] = df["ema_fast"] < df["ema_slow"]

    # Pullback conditions
    df["recent_min_rsi"] = df["rsi"].rolling(window=lookback_pullback, min_periods=1).min()
    df["recent_max_rsi"] = df["rsi"].rolling(window=lookback_pullback, min_periods=1).max()

    # Entrée long : tendance haussière + pullback + reprise
    # pullback: recent_min_rsi < rsi_pullback
    # reprise: rsi crosses above rsi_momentum and close > ema_fast
    df["long_signal"] = False
    df["short_signal"] = False

    rsi_prev = df["rsi"].shift(1)

    long_cond = (
        df["trend_long"]
        & (df["recent_min_rsi"] < rsi_pullback)
        & (rsi_prev <= rsi_momentum)
        & (df["rsi"] > rsi_momentum)
        & (df["close"] > df["ema_fast"])
    )

    short_cond = (
        df["trend_short"]
        & (df["recent_max_rsi"] > (100 - rsi_pullback))
        & (rsi_prev >= rsi_momentum)
        & (df["rsi"] < rsi_momentum)
        & (df["close"] < df["ema_fast"])
    )

    df.loc[long_cond, "long_signal"] = True
    df.loc[short_cond, "short_signal"] = True

    return df


def generate_signals(
    df: pd.DataFrame,
    ema_fast: int = 1,
    ema_slow: int = 30,

    rsi_period: int = 5,
    rsi_pullback: float = 35.0,
    rsi_momentum: float = 35.0,
    lookback_pullback: int = 5,

    pct_increase: float = 1.0,  # pourcentage minimal d’augmentation de l’EMA fast
    period_increase: int = 5,   # nombre de périodes sur lesquelles mesurer l’augmentation
) -> pd.DataFrame:
    """Détecte un changement de tendance basé sur croisement EMA et hausse de l’EMA rapide."""
    df = df.copy()

    # Calcul des moyennes mobiles exponentielles
    df["ema_fast"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=ema_slow, adjust=False).mean()

    # Croisement EMA fast / slow
    df["ema_fast_prev"] = df["ema_fast"].shift(1)
    df["ema_slow_prev"] = df["ema_slow"].shift(1)
    df["cross_up"] = (df["ema_fast_prev"] <= df["ema_slow_prev"]) & (df["ema_fast"] > df["ema_slow"])
    df["cross_down"] = (df["ema_fast_prev"] >= df["ema_slow_prev"]) & (df["ema_fast"] < df["ema_slow"])

    # Variation relative de l’EMA rapide sur la période donnée
    df["ema_fast_prevN"] = df["ema_fast"].shift(period_increase)
    df["ema_fast_change_pct"] = (df["ema_fast"] - df["ema_fast_prevN"]) / df["ema_fast_prevN"] * 100

    # Conditions d'inversion haussière et baissière
    df["long_signal"] = df["cross_up"] & (df["ema_fast_change_pct"] >= pct_increase)
    df["short_signal"] = df["cross_down"] & (df["ema_fast_change_pct"] <= -pct_increase)

    return df


def backtest_strategy(
    df: pd.DataFrame,
    starting_balance: float = 100.0,
    fixed_qty: Optional[float] = None,       # nouvelle option : taille fixe
    take_profit_pct: Optional[float] = 1.5, # nouvelle option : take gain %
    stop_loss_pct: Optional[float] = 0.75,   # nouvelle option : stop loss %
    risk_per_trade: float = 0.01,
    fee_rate: float = 0.001,
    max_open_trades: int = 1,
) -> (List[Trade], pd.DataFrame):
    """Backtest séquentiel avec options pour take profit et stop loss en % ou par ratio."""

    trades: List[Trade] = []
    balance = starting_balance
    equity_curve = []

    in_trade = False
    trade_direction = None
    entry_price = stop_loss = take_profit = entry_time = None
    qty = 0.0

    for i in range(1, len(df)):
        row_prev = df.iloc[i - 1]
        row = df.iloc[i]
        time = df.index[i]

        high = row["high"]
        low = row["low"]
        o = row["open"]

        equity_curve.append({"time": time, "equity": balance})

        if not in_trade:
            if row_prev["long_signal"]:
                trade_direction = "long"
                entry_price = o
                entry_time = time

                # Définition du stop loss et TP
                if stop_loss_pct is not None and take_profit_pct is not None:
                    stop_loss = entry_price * (1 - stop_loss_pct / 100)
                    take_profit = entry_price * (1 + take_profit_pct / 100)
                else:
                    stop_loss = row_prev["low"]
                    risk_per_unit = entry_price - stop_loss
                    take_profit = entry_price + 2 * risk_per_unit

                # Définition de la quantité
                if fixed_qty is not None:
                    qty = fixed_qty
                else:
                    risk_amount = balance * risk_per_trade
                    qty = risk_amount / (entry_price - stop_loss)

                in_trade = True

            elif row_prev["short_signal"]:
                trade_direction = "short"
                entry_price = o
                entry_time = time

                if stop_loss_pct is not None and take_profit_pct is not None:
                    stop_loss = entry_price * (1 + stop_loss_pct / 100)
                    take_profit = entry_price * (1 - take_profit_pct / 100)
                else:
                    stop_loss = row_prev["high"]
                    risk_per_unit = stop_loss - entry_price
                    take_profit = entry_price - 2 * risk_per_unit

                if fixed_qty is not None:
                    qty = fixed_qty
                else:
                    risk_amount = balance * risk_per_trade
                    qty = risk_amount / (stop_loss - entry_price)

                in_trade = True

        else:
            exit_price = None
            exit_time = time

            if trade_direction == "long":
                hit_sl = low <= stop_loss
                hit_tp = high >= take_profit
            else:
                hit_sl = high >= stop_loss
                hit_tp = low <= take_profit

            if hit_sl or hit_tp:
                exit_price = stop_loss if hit_sl else take_profit
                gross_pnl = (exit_price - entry_price) * qty if trade_direction == "long" else (entry_price - exit_price) * qty
                fees = (entry_price * qty + exit_price * qty) * fee_rate
                net_pnl = gross_pnl - fees
                pnl_pct = net_pnl / balance
                balance += net_pnl

                if trade_direction == "long":
                    risk_per_unit = entry_price - stop_loss
                else:
                    risk_per_unit = stop_loss - entry_price

                r_multiple = net_pnl / (risk_per_unit * qty) if risk_per_unit > 0 else 0

                trades.append(Trade(
                    direction=trade_direction,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    qty=qty,
                    r_multiple=r_multiple,
                    pnl=net_pnl,
                    pnl_pct=pnl_pct,
                ))

                in_trade = False

    equity_df = pd.DataFrame(equity_curve).set_index("time")
    return trades, equity_df


# =============================
# Stats & plots
# =============================


def compute_stats(trades: List[Trade], starting_balance: float, equity_df: pd.DataFrame):
    if not trades:
        return {"message": "Aucun trade exécuté"}

    pnl_list = np.array([t.pnl for t in trades])
    r_list = np.array([t.r_multiple for t in trades])

    wins = pnl_list[pnl_list > 0]
    losses = pnl_list[pnl_list <= 0]

    win_rate = len(wins) / len(trades) if trades else 0.0
    avg_r = r_list.mean() if len(r_list) > 0 else 0.0

    # Max drawdown sur l'equity
    eq = equity_df["equity"].values
    peak = np.maximum.accumulate(eq)
    drawdown = (eq - peak) / peak
    max_dd = drawdown.min() if len(drawdown) > 0 else 0.0

    stats = {
        "trades": len(trades),
        "win_rate": win_rate,
        "avg_r": avg_r,
        "total_pnl": pnl_list.sum(),
        "final_balance": equity_df["equity"].iloc[-1],
        "return_pct": (equity_df["equity"].iloc[-1] / starting_balance) - 1,
        "max_drawdown_pct": max_dd,
    }

    return stats


def plot_results(df: pd.DataFrame, trades: List[Trade], equity_df: pd.DataFrame, title_suffix: str = ""):
    fig, ax = plt.subplots(figsize=(14, 7))

    # Courbes principales
    x_prices = mdates.date2num(df.index.to_pydatetime())
    ax.plot(x_prices, df["close"].values, label="Close")
    ax.plot(x_prices, df["ema_fast"].values, label="EMA fast")
    ax.plot(x_prices, df["ema_slow"].values, label="EMA slow")

    # Choisissez ici la courbe sur laquelle le point doit être EXACTEMENT posé
    curve_for_marker = "close"      # ou "ema_fast" / "ema_slow"
    curve_values = df[curve_for_marker].values

    def align_index(ts):
        ts = pd.to_datetime(ts)
        pos = df.index.get_indexer([ts], method="nearest")[0]
        return pos

    longs  = [t for t in trades if t.direction == "long"]
    shorts = [t for t in trades if t.direction == "short"]

    long_pos = [align_index(t.entry_time) for t in longs]
    short_pos = [align_index(t.entry_time) for t in shorts]

    # Coordonnées X/Y EXACTES sur la courbe choisie
    long_x_on_curve  = [x_prices[i] for i in long_pos]
    long_y_on_curve  = [curve_values[i] for i in long_pos]

    short_x_on_curve = [x_prices[i] for i in short_pos]
    short_y_on_curve = [curve_values[i] for i in short_pos]

    # Triangles : on garde éventuellement le prix réel d'entrée si vous le souhaitez
    long_entry_prices  = [t.entry_price for t in longs]
    short_entry_prices = [t.entry_price for t in shorts]

    price_range = df["close"].max() - df["close"].min()
    offset = price_range * 0.01

    # Triangles légèrement décalés en vertical
    ax.scatter(long_x_on_curve,
               [p + offset for p in long_entry_prices],
               marker="^", s=80, color="green", zorder=3, label="Long entry")

    ax.scatter(short_x_on_curve,
               [p - offset for p in short_entry_prices],
               marker="v", s=80, color="red",   zorder=3, label="Short entry")

    # MARQUEURS EXACTS : point creux posé directement sur la courbe
    ax.plot(long_x_on_curve, long_y_on_curve,
            linestyle="None", marker="o", markersize=9,
            markerfacecolor="none", markeredgecolor="green",
            markeredgewidth=1.5, zorder=4, label="Long exact")

    ax.plot(short_x_on_curve, short_y_on_curve,
            linestyle="None", marker="o", markersize=9,
            markerfacecolor="none", markeredgecolor="red",
            markeredgewidth=1.5, zorder=4, label="Short exact")

    # Formatage temps
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %H:%M"))

    ax.set_title(f"INJUSDC prix + signaux {title_suffix}")
    ax.set_xlabel("Temps")
    ax.set_ylabel("Prix")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    # Figure equity
    fig2, ax2 = plt.subplots(figsize=(14, 4))
    x_equity = mdates.date2num(equity_df.index.to_pydatetime())
    ax2.plot(x_equity, equity_df["equity"].values, label="Equity")
    ax2.xaxis_date()
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d %H:%M"))
    ax2.set_title(f"Courbe d'equity {title_suffix}")
    ax2.set_xlabel("Temps")
    ax2.set_ylabel("Balance")
    ax2.legend()
    fig2.autofmt_xdate()
    fig2.tight_layout()

    plt.show()

# =============================
# Main
# =============================


def main():
    parser = argparse.ArgumentParser(description="Backtest stratégie tendance + momentum sur INJUSDC")
    parser.add_argument(
        "--file",
        type=str,
        default="../Data/klines_INJUSDC_1m_from_2025_06_01.csv",
        help="Chemin vers le CSV de klines 1m",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="3T",
        help="Timeframe de resampling pandas (ex: 15T, 1H, 4H)",
    )
    parser.add_argument("--starting_balance", type=float, default=100.0)
    parser.add_argument("--risk", type=float, default=0.05, help="Risque par trade (fraction du capital)")

    args = parser.parse_args()

    print("Chargement des données...")
    df = load_klines_csv(args.file, timeframe=args.timeframe)

    print("Calcul des indicateurs et signaux...")
    df_sig = generate_signals(df)

    print("Lancement du backtest...")
    trades, equity_df = backtest_strategy(
        df_sig,
        starting_balance=args.starting_balance,
        risk_per_trade=args.risk,
    )

    print(f"Nombre de trades exécutés : {len(trades)}")

    stats = compute_stats(trades, args.starting_balance, equity_df)

    print("\n===== STATISTIQUES =====")
    if "message" in stats:
        print(stats["message"])
        return

    print(f"Trades totaux       : {stats['trades']}")
    print(f"Winrate             : {stats['win_rate']*100:.2f}%")
    print(f"R moyen             : {stats['avg_r']:.3f}")
    print(f"PnL total           : {stats['total_pnl']:.2f}")
    print(f"Balance finale      : {stats['final_balance']:.2f}")
    print(f"Performance         : {stats['return_pct']*100:.2f}%")
    print(f"Max drawdown        : {stats['max_drawdown_pct']*100:.2f}%")

    print("\nAffichage des graphiques...")
    plot_results(df_sig, trades, equity_df, title_suffix=f"({args.timeframe})")


if __name__ == "__main__":
    main()
