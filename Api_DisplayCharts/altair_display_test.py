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

source = df.reset_index().rename(columns={"index": "Date"})

candles = alt.Chart(source).mark_rule().encode(
    x='Date:T',
    y='Low:Q',
    y2='High:Q'
).properties(title="Chandeliers + EMA12 (Altair)")

bars = alt.Chart(source).mark_bar().encode(
    x='Date:T',
    y='Open:Q',
    y2='Close:Q',
    color=alt.condition("datum.Open <= datum.Close", alt.value("green"), alt.value("red"))
)

ema_line = alt.Chart(source).mark_line(color="blue").encode(
    x='Date:T',
    y='EMA12:Q'
) 

(candles + bars + ema_line).interactive()
