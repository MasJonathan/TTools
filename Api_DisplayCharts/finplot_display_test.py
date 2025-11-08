import altair as alt
import pandas as pd

import pandas as pd
import numpy as np
import mplfinance as mpf



# Pour obtenir toujours les mêmes valeurs aléatoires
np.random.seed(0)

# 60 jours de données journalières
dates = pd.date_range("2024-01-01", periods=60, freq="D")

# Prix "théorique" de base
base_price = np.cumsum(np.random.randn(len(dates))) + 100

df = pd.DataFrame(index=dates)
df["Open"] = base_price + np.random.randn(len(dates))
df["Close"] = df["Open"] + np.random.randn(len(dates))

# High = max(Open, Close) + marge aléatoire positive
rand_high = np.abs(np.random.randn(len(dates)))
df["High"] = df[["Open", "Close"]].max(axis=1) + rand_high

# Low = min(Open, Close) - marge aléatoire positive
rand_low = np.abs(np.random.randn(len(dates)))
df["Low"] = df[["Open", "Close"]].min(axis=1) - rand_low

# Volume arbitraire
df["Volume"] = np.random.randint(100, 1000, size=len(dates))

# Calcul EMA12 sur le cours de clôture
df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()

print(df.head())

import finplot as fplt

ax = fplt.create_plot("Finplot - Chandeliers + EMA12")
fplt.candlestick_ochl(df[["Open","Close","High","Low"]])
fplt.plot(df["EMA12"], color="#00aaff", legend="EMA12")
fplt.show()