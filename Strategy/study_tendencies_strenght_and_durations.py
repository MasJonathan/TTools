import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# --- Chargement des données ---
file_path = "../Data/klines_INJUSDC_1m_from_2025_06_01.csv"
df = pd.read_csv(file_path, parse_dates=["open_time"])
df["close"] = df["close"].astype(float)

# --- Calcul SMA et Bandes de Bollinger ---
period = 20
df["SMA"] = df["close"].rolling(window=period).mean()
df["STD"] = df["close"].rolling(window=period).std()
df["Bollinger_High"] = df["SMA"] + 2 * df["STD"]
df["Bollinger_Low"] = df["SMA"] - 2 * df["STD"]

# --- Détection de la tendance SMA ---
df["SMA_diff"] = df["SMA"].diff()
df["trend_dir"] = np.sign(df["SMA_diff"])  # 1 = hausse, -1 = baisse, 0 = stable

# --- Regroupement par tendances continues ---
df["trend_group"] = (df["trend_dir"] != df["trend_dir"].shift()).cumsum()

trend_stats = (
    df.groupby("trend_group")
    .agg(
        direction=("trend_dir", "first"),
        duration=("trend_dir", "count"),
        intensity=("SMA_diff", lambda x: abs(x.sum()))
    )
    .query("direction != 0")
)

# --- Graphiques ---
plt.figure(figsize=(10,5))
plt.hist(trend_stats["duration"], bins=30, edgecolor='black')
plt.title("Distribution des durées de tendances")
plt.xlabel("Durée (nombre de périodes consécutives)")
plt.ylabel("Fréquence")
plt.show()

plt.figure(figsize=(10,5))
plt.hist(trend_stats["intensity"], bins=30, edgecolor='black')
plt.title("Distribution des intensités de variations SMA")
plt.xlabel("Intensité absolue (variation du SMA)")
plt.ylabel("Fréquence")
plt.show()
