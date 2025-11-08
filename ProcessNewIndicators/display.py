import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
from datetime import datetime, timedelta
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import pandas as pd
import IndicatorCreator as ic  # your provided module
import numpy as np


class KlineVisualizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kline and Indicator Visualizer")

        self.manager = ic.KlineManager()

        # GUI elements
        frame = tk.Frame(root)
        frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        tk.Button(frame, text="Load Klines CSV", command=self.load_klines).pack(side=tk.LEFT)
        tk.Button(frame, text="Add Indicator CSV", command=self.add_indicator).pack(side=tk.LEFT)

        tk.Label(frame, text="Timeframe (min):").pack(side=tk.LEFT, padx=(20,0))
        self.timeframe_var = tk.IntVar(value=1)
        tk.Entry(frame, textvariable=self.timeframe_var, width=5).pack(side=tk.LEFT)

        tk.Label(frame, text="Candles each side:").pack(side=tk.LEFT, padx=(20,0))
        self.candles_var = tk.IntVar(value=50)
        tk.Entry(frame, textvariable=self.candles_var, width=5).pack(side=tk.LEFT)

        tk.Label(frame, text="Center DateTime (YYYY-MM-DD HH:MM):").pack(side=tk.LEFT, padx=(20,0))
        self.center_dt_var = tk.StringVar()
        tk.Entry(frame, textvariable=self.center_dt_var, width=20).pack(side=tk.LEFT)

        tk.Button(frame, text="Plot", command=self.plot).pack(side=tk.LEFT, padx=(10,0))

        # Matplotlib figure
        self.fig, self.ax = plt.subplots()
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)

    def load_klines(self):
        file_path = filedialog.askopenfilename(title="Select Klines CSV")
        if file_path:
            try:
                self.manager.read_klines(file_path)
                messagebox.showinfo("Klines Loaded", f"Loaded klines from {file_path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def add_indicator(self):
        file_path = filedialog.askopenfilename(title="Select Indicator CSV")
        if file_path:
            try:
                self.manager.read_indicator(file_path)
                messagebox.showinfo("Indicator Loaded", f"Loaded indicator from {file_path}")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def aggregate_klines(self, timeframe_min):
        # Aggregate klines and indicators to new timeframe
        if not self.manager.klines:
            return None, None

        df = pd.DataFrame([{
            'timestamp': ts,
            'open': k.open,
            'high': k.high,
            'low': k.low,
            'close': k.close,
            'volume': k.volume,
            **{f"{ind}_{param}": val for ind_k in k.indicators.values() for param, val in ind_k.items()}
        } for ts, k in self.manager.klines.items()])

        df.set_index('timestamp', inplace=True)
        df = df.sort_index()

        # Resample by timeframe_min ("timeframe_min" is in minutes)
        rule = f"{timeframe_min}T"
        agg_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
        }
        # For indicators, aggregate by mean if numeric
        for col in df.columns:
            if col not in agg_dict:
                agg_dict[col] = 'mean'

        df_agg = df.resample(rule).agg(agg_dict).dropna()
        return df_agg

    def plot(self):
        timeframe = self.timeframe_var.get()
        try:
            center_dt = datetime.strptime(self.center_dt_var.get(), "%Y-%m-%d %H:%M")
        except Exception:
            messagebox.showerror("Error", "Center datetime format invalid. Use YYYY-MM-DD HH:MM")
            return

        n_candles_each_side = self.candles_var.get()

        df_agg = self.aggregate_klines(timeframe)
        if df_agg is None or df_agg.empty:
            messagebox.showwarning("No Data", "No klines loaded")
            return

        # Extract slice around center_dt +/- n candles
        # find nearest index to center_dt
        idx_list = df_agg.index.to_list()
        center_idx = min(range(len(idx_list)), key=lambda i: abs(idx_list[i] - center_dt))

        start_idx = max(0, center_idx - n_candles_each_side)
        end_idx = min(len(idx_list)-1, center_idx + n_candles_each_side)
        df_slice = df_agg.iloc[start_idx:end_idx+1]

        self.ax.clear()

        # Plot candlesticks manually
        for i, (ts, row) in enumerate(df_slice.iterrows()):
            color = 'green' if row['close'] >= row['open'] else 'red'
            self.ax.plot([i, i], [row['low'], row['high']], color='black')  # wick
            self.ax.add_patch(plt.Rectangle((i-0.3, min(row['open'], row['close'])),
                                            0.6,
                                            abs(row['close']-row['open']),
                                            color=color))
        self.ax.set_xticks(range(len(df_slice)))
        self.ax.set_xticklabels([ts.strftime("%m-%d %H:%M") for ts in df_slice.index], rotation=45, ha='right')

        # Plot indicator lines - one line per param of each indicator
        indicator_cols = [c for c in df_slice.columns if c not in ['open', 'high', 'low', 'close', 'volume']]
        grouped = {}
        for col in indicator_cols:
            # e.g. "ema6_24_ema6" -> group by indicator prefix (before last underscore)
            # or simpler: split at last underscore
            parts = col.rsplit('_', 1)
            grp = parts[0]
            if grp not in grouped:
                grouped[grp] = []
            grouped[grp].append(col)

        colors = plt.cm.get_cmap('tab10')
        color_idx = 0
        for grp, cols in grouped.items():
            for col in cols:
                y = df_slice[col].values
                # Handle missing values by interpolation or masking
                if all(pd.isna(y)):
                    continue
                y = pd.Series(y).interpolate().fillna(method='bfill').fillna(method='ffill').values
                self.ax.plot(range(len(df_slice)), y, label=col, color=colors(color_idx))
            color_idx = (color_idx + 1) % 10

        self.ax.legend(loc='upper left', fontsize='small')
        self.ax.set_title(f"Klines & Indicators around {center_dt.strftime('%Y-%m-%d %H:%M')}, timeframe {timeframe}m")
        self.ax.grid(True)
        self.fig.tight_layout()
        self.canvas.draw()


if __name__ == "__main__":
    root = tk.Tk()
    app = KlineVisualizerApp(root)
    root.mainloop()
