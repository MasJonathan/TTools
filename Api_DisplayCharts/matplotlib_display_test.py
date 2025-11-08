import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import matplotlib.dates as mdates

# Données simulées
dates = pd.date_range("2024-01-01", periods=20)
open_ = np.random.rand(20) * 10 + 100
close = open_ + np.random.randn(20)
high = np.maximum(open_, close) + np.random.rand(20)
low = np.minimum(open_, close) - np.random.rand(20)

# EMA12
ema12 = pd.Series(close).ewm(span=12, adjust=False).mean()

fig, ax = plt.subplots(figsize=(10,5))

# Chandeliers "maison"
for i, d in enumerate(dates):
    color = "green" if close[i] >= open_[i] else "red"
    ax.plot([d, d], [low[i], high[i]], color="black", linewidth=1)
    ax.plot([d, d], [open_[i], close[i]], color=color, linewidth=5)

# EMA12
ax.plot(dates, ema12, label="EMA12", color="blue")

ax.xaxis.set_major_formatter(mdates.DateFormatter("%d-%b"))
ax.set_title("Chandeliers + EMA12 (Matplotlib)")
ax.legend()
plt.tight_layout()
plt.show()
