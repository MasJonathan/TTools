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


from bokeh.plotting import figure, show
from bokeh.io import output_notebook
from bokeh.models import ColumnDataSource

# Pour afficher directement dans un notebook Jupyter
output_notebook()

source = ColumnDataSource(df.reset_index().rename(columns={"index": "Date"}))

# Largeur des chandeliers (en millisecondes)
# ici ~ 12 heures pour des données journalières
w = 12 * 60 * 60 * 1000  

p = figure(
    x_axis_type="datetime",
    width=1000,
    height=500,
    title="Chandeliers + EMA12 (Bokeh)",
    toolbar_location="right"
)

# Détermine les bougies haussières / baissières
inc = df["Close"] >= df["Open"]
dec = df["Close"] < df["Open"]

# Mèches (High-Low)
p.segment(
    x0="Date",
    y0="Low",
    x1="Date",
    y1="High",
    source=source,
    line_width=1
)

# Bougies haussières (vertes)
p.vbar(
    x=df.index[inc],
    width=w,
    bottom=df["Open"][inc],
    top=df["Close"][inc],
    fill_color="green",
    line_color="green",
    alpha=0.7,
    legend_label="Haussier"
)

# Bougies baissières (rouges)
p.vbar(
    x=df.index[dec],
    width=w,
    bottom=df["Open"][dec],
    top=df["Close"][dec],
    fill_color="red",
    line_color="red",
    alpha=0.7,
    legend_label="Baissier"
)

# Courbe EMA12
p.line(
    x=df.index,
    y=df["EMA12"],
    line_width=2,
    legend_label="EMA12"
)

p.xaxis.axis_label = "Date"
p.yaxis.axis_label = "Prix"

p.legend.location = "top_left"

show(p)
