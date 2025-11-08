# pip install pandas numpy

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


import plotly.graph_objects as go

fig = go.Figure()

# Chandeliers
fig.add_trace(
    go.Candlestick(
        x=df.index,
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        name="Cours",
        # Vous pouvez personnaliser les couleurs :
        increasing_line_color="green",
        decreasing_line_color="red",
        increasing_fillcolor="green",
        decreasing_fillcolor="red",
    )
)

# EMA12
fig.add_trace(
    go.Scatter(
        x=df.index,
        y=df["EMA12"],
        mode="lines",
        name="EMA12",
        line=dict(width=1.5)
    )
)

fig.update_layout(
    title="Chandeliers + EMA12 (Plotly)",
    xaxis_title="Date",
    yaxis_title="Prix",
    xaxis_rangeslider_visible=False,  # retire le range slider si vous ne le souhaitez pas
    template="plotly_white",
    width=1000,
    height=500,
)

fig.show()
