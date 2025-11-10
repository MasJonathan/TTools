import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ============================================================
# 1. Chargement des données
# ============================================================

file_path = "../Data/klines_INJUSDC_1m_from_2025_06_01.csv"
file_path = "../Data/klines_INJUSDC_1m_from_2025.csv"
file_path = "../Data/klines_INJUSDC_1m_from_beginning_to_now.csv"

df = pd.read_csv(file_path)

# Conversion du temps et définition de l'index
df["open_time"] = pd.to_datetime(df["open_time"])
df.set_index("open_time", inplace=True)

# Conversion des colonnes numériques
num_cols = ["open", "high", "low", "close", "volume"]
df[num_cols] = df[num_cols].astype(float)

# ============================================================
# 2. Indicateurs : Bollinger + tendance
# ============================================================

period = 100

df["sma20"] = df["close"].rolling(window=period).mean()
df["std20"] = df["close"].rolling(window=period).std(ddof=0)

df["upper"] = df["sma20"] + 2 * df["std20"]
df["lower"] = df["sma20"] - 2 * df["std20"]

# Tendance : différence de SMA20
df["tendency"] = df["sma20"] - df["sma20"].shift(1)
df["tendency_pct"] = df["tendency"] / df["sma20"] * 100

def classify_trend(row):
    if pd.isna(row["tendency_pct"]):
        return "indet"
    if row["tendency_pct"] >= 0.3:
        return "bull"     # tendance haussière
    if row["tendency_pct"] <= -0.3:
        return "bear"     # tendance baissière
    return "flat"         # tendance latérale

df["trend"] = df.apply(classify_trend, axis=1)

# ============================================================
# 3. Backtest de la stratégie
# ============================================================

initial_capital = 1000.0
wallet = initial_capital  # capital réalisé
equity_curve = []         # capital mark-to-market (avec position ouverte)
equity_index = []

position = 0             # 0 = flat, +1 = long, -1 = short
entry_price = None
quantity = 0.0
entry_idx = None
entry_time = None
entry_mode = None        # "range" ou "trend"
direction = None         # "long" ou "short"
tp_level = None
sl_level = None

trade_log = []

for i in range(1, len(df)):
    row = df.iloc[i]
    prev_row = df.iloc[i - 1]
    
    close = row["close"]
    prev_close = prev_row["close"]
    
    mid = row["sma20"]
    prev_mid = prev_row["sma20"]
    
    upper = row["upper"]
    lower = row["lower"]
    
    trend_now = row["trend"]
    
    # ================================================
    # 3.1 Gestion des sorties (si une position est ouverte)
    # ================================================
    equity = wallet  # valeur par défaut si pas de position
    
    if position != 0 and not np.isnan(mid) and not np.isnan(upper) and not np.isnan(lower):
        exit_reason = None
        exit_price = None
        
        if entry_mode == "range":
            # Mode range : TP / SL prédéfinis sur bandes
            if position == 1:
                # Long : TP vers upper, SL sur lower
                hit_tp = (row["high"] >= tp_level)
                hit_sl = (row["low"] <= sl_level)
                
                # Si les deux sont touchés la même bougie, on suppose TP en premier
                if hit_tp and hit_sl:
                    exit_price = tp_level
                    exit_reason = "tp"
                elif hit_tp:
                    exit_price = tp_level
                    exit_reason = "tp"
                elif hit_sl:
                    exit_price = sl_level
                    exit_reason = "sl"
            
            elif position == -1:
                # Short : TP vers lower, SL sur upper
                hit_tp = (row["low"] <= tp_level)
                hit_sl = (row["high"] >= sl_level)
                
                if hit_tp and hit_sl:
                    exit_price = tp_level
                    exit_reason = "tp"
                elif hit_tp:
                    exit_price = tp_level
                    exit_reason = "tp"
                elif hit_sl:
                    exit_price = sl_level
                    exit_reason = "sl"
        
        elif entry_mode == "trend":
            # Mode tendance : SL sur bande opposée, TP lorsque tendance redevient neutre (flat)
            if position == 1:
                hit_sl = (row["low"] <= lower)
            else:
                hit_sl = (row["high"] >= upper)
            
            if hit_sl:
                exit_reason = "sl"
                exit_price = lower if position == 1 else upper
            elif trend_now == "flat":
                exit_reason = "tp_trend"
                exit_price = close
        
        # Exécution de la sortie si condition remplie
        if exit_reason is not None:
            if position == 1:
                pnl = (exit_price - entry_price) * quantity
            else:
                pnl = (entry_price - exit_price) * quantity
            
            wallet += pnl
            equity = wallet  # après clôture, equity = wallet (plus de position)
            
            trade_log.append({
                "entry_time": entry_time,
                "exit_time": row.name,
                "entry_idx": entry_idx,
                "exit_idx": i,
                "direction": "long" if position == 1 else "short",
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "exit_type": exit_reason,
                "wallet": wallet
            })
            
            # Réinitialisation de la position
            position = 0
            quantity = 0.0
            entry_price = None
            entry_mode = None
            direction = None
            tp_level = None
            sl_level = None
        
        else:
            # Pas de sortie : mark-to-market de la position
            if position == 1:
                equity = wallet + (close - entry_price) * quantity
            elif position == -1:
                equity = wallet + (entry_price - close) * quantity
    
    # Si pas de position (ou après sortie), equity = wallet
    if position == 0:
        equity = wallet
    
    equity_curve.append(equity)
    equity_index.append(row.name)
    
    # ================================================
    # 3.2 Gestion des entrées (uniquement si flat)
    # ================================================
    if position == 0 and not np.isnan(mid) and not np.isnan(prev_mid):
        # Détection de croisement de la bande médiane
        cross_up = (prev_close < prev_mid) and (close >= mid)
        cross_down = (prev_close > prev_mid) and (close <= mid)
        
        # ---- Cas tendance latérale : on trade la médiane dans un range ----
        if trend_now == "flat" and (cross_up or cross_down):
            # Direction choisie avec la tendency (si positive : long, sinon short)
            t = row["tendency"]
            if t >= 0:
                position = 1
                direction = "long"
            else:
                position = -1
                direction = "short"
            
            entry_price = close
            quantity = wallet / entry_price  # full equity, sans levier
            
            entry_idx = i
            entry_time = row.name
            entry_mode = "range"
            
            if position == 1:
                # Long : TP à 75% de la distance vers la bande haute, SL sur la bande basse
                tp_level = entry_price + 0.75 * (upper - entry_price)
                sl_level = lower
            else:
                # Short : TP à 75% de la distance vers la bande basse, SL sur la bande haute
                tp_level = entry_price - 0.75 * (entry_price - lower)
                sl_level = upper
        
        # ---- Cas tendance haussière : on ne prend que des longs ----
        elif trend_now == "bull" and cross_up:
            position = 1
            direction = "long"
            entry_price = close
            quantity = wallet / entry_price
            
            entry_idx = i
            entry_time = row.name
            entry_mode = "trend"
            
            tp_level = None
            sl_level = None
        
        # ---- Cas tendance baissière : on ne prend que des shorts ----
        elif trend_now == "bear" and cross_down:
            position = -1
            direction = "short"
            entry_price = close
            quantity = wallet / entry_price
            
            entry_idx = i
            entry_time = row.name
            entry_mode = "trend"
            
            tp_level = None
            sl_level = None

# ============================================================
# 4. Préparation des données pour les graphiques
# ============================================================

equity_series = pd.Series(equity_curve, index=equity_index)

# Points d'entrée / sortie
long_entries_x = []
long_entries_y = []
short_entries_x = []
short_entries_y = []

tp_x = []
tp_y = []
sl_x = []
sl_y = []
tp_trend_x = []
tp_trend_y = []

for trade in trade_log:
    e_idx = trade["entry_idx"]
    x_entry = df.index[e_idx]
    y_entry = df["close"].iloc[e_idx]
    
    if trade["direction"] == "long":
        long_entries_x.append(x_entry)
        long_entries_y.append(y_entry)
    else:
        short_entries_x.append(x_entry)
        short_entries_y.append(y_entry)
    
    x_exit = trade["exit_time"]
    y_exit = trade["exit_price"]
    
    if trade["exit_type"] == "sl":
        sl_x.append(x_exit)
        sl_y.append(y_exit)
    elif trade["exit_type"] == "tp":
        tp_x.append(x_exit)
        tp_y.append(y_exit)
    elif trade["exit_type"] == "tp_trend":
        tp_trend_x.append(x_exit)
        tp_trend_y.append(y_exit)

# ============================================================
# 5. Graphiques : prix + signaux et évolution du portefeuille
# ============================================================

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

# --- Graphique 1 : prix + bandes de Bollinger + signaux ---
ax1.plot(df.index, df["close"], label="Close")
ax1.plot(df.index, df["sma20"], linestyle="--", label="SMA20")
ax1.plot(df.index, df["upper"], linestyle=":", label="Upper band")
ax1.plot(df.index, df["lower"], linestyle=":", label="Lower band")

# Entrées
ax1.scatter(long_entries_x, long_entries_y, marker="^", s=60, label="Entrée long")
ax1.scatter(short_entries_x, short_entries_y, marker="v", s=60, label="Entrée short")

# Sorties TP / SL
ax1.scatter(tp_x, tp_y, marker="o", s=60, label="TP (range)")
ax1.scatter(tp_trend_x, tp_trend_y, marker="o", s=60, label="TP (tendance)")
ax1.scatter(sl_x, sl_y, marker="x", s=60, label="SL")

ax1.set_ylabel("Prix INJ/USDC")
ax1.legend(loc="upper left")
ax1.set_title("Backtest Bollinger Bands : prix et signaux de trading")

# --- Graphique 2 : évolution du portefeuille ---
ax2.plot(equity_series.index, equity_series.values)
ax2.set_ylabel("Valeur du portefeuille (USDC)")
ax2.set_xlabel("Date")
ax2.set_title("Évolution de la valeur du portefeuille")

plt.tight_layout()
plt.show()

# ============================================================
# 6. Quelques statistiques de base
# ============================================================

trades_df = pd.DataFrame(trade_log)

print("Capital initial :", initial_capital)
print("Capital final   :", wallet)
if len(trades_df) > 0:
    print("Nombre de trades :", len(trades_df))
    print("PNL total        :", trades_df["pnl"].sum())
    print("PNL moyen / trade:", trades_df["pnl"].mean())
    print("Taux de réussite :", (trades_df[trades_df["pnl"] > 0].shape[0] / len(trades_df)) * 100, "%")
else:
    print("Aucun trade généré par la stratégie sur la période.")
