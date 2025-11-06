import math
import sys
from pathlib import Path

import pandas as pd
import matplotlib.dates as mdates
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt5 import QtWidgets, QtCore

# --- Config timeframes Binance -> millisecondes / règles pandas ---

TIMEFRAME_MS = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "3d": 3 * 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
    "1M": 30 * 24 * 60 * 60_000,  # approx
}

TIMEFRAME_ORDER = [
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
]

TIMEFRAME_TO_PANDAS_RULE = {
    "1m": "1T",
    "3m": "3T",
    "5m": "5T",
    "15m": "15T",
    "30m": "30T",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6H",
    "8h": "8H",
    "12h": "12H",
    "1d": "1D",
    "3d": "3D",
    "1w": "1W",
    "1M": "1M",
}

# --- Utilitaires colonnes / chargement ---

COLUMN_ALIASES = {
    # temps d'ouverture
    "open_time": "open_time",
    "Open time": "open_time",
    "openTime": "open_time",
    # OHLC
    "open": "open",
    "Open": "open",
    "high": "high",
    "High": "high",
    "low": "low",
    "Low": "low",
    "close": "close",
    "Close": "close",
    # volume
    "volume": "volume",
    "Volume": "volume",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for c in df.columns:
        mapping[c] = COLUMN_ALIASES.get(c, c)
    df = df.rename(columns=mapping)
    return df


def find_time_column(df: pd.DataFrame) -> str:
    for c in ["open_time", "Open time", "openTime"]:
        if c in df.columns:
            return c
    return df.columns[0]


def to_datetime_index(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    s = df[time_col]

    if pd.api.types.is_datetime64_any_dtype(s):
        dt = pd.to_datetime(s)
    else:
        if pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s):
            dt = pd.to_datetime(s.astype("int64"), unit="ms")
        else:
            dt = pd.to_datetime(s, errors="coerce")

    df = df.copy()
    df["datetime"] = dt
    df = df.dropna(subset=["datetime"])
    df = df.set_index("datetime")
    df = df.sort_index()
    return df


def detect_timeframe(df: pd.DataFrame):
    if df.index.size < 3:
        return None
    diffs = df.index.to_series().diff().dropna()
    if diffs.empty:
        return None

    mode_delta = diffs.value_counts().idxmax()
    delta_ms = mode_delta / pd.Timedelta(milliseconds=1)

    best_tf = None
    best_diff = None
    for tf, ms in TIMEFRAME_MS.items():
        d = abs(ms - delta_ms)
        if best_diff is None or d < best_diff:
            best_diff = d
            best_tf = tf

    if best_diff is not None and best_diff > 0.2 * TIMEFRAME_MS.get(best_tf, 1):
        return None

    return best_tf


def resample_klines(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    rule = TIMEFRAME_TO_PANDAS_RULE[target_tf]

    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            raise ValueError(
                f"Colonne '{col}' manquante. Vérifie le format de ton CSV."
            )

    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in df.columns:
        agg_dict["volume"] = "sum"

    resampled = df.resample(rule).agg(agg_dict).dropna()
    return resampled


# --- Canvas Matplotlib pour PyQt ---

class CandlestickCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(10, 6))
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_candles(self, df_page: pd.DataFrame):
        self.ax.clear()

        if df_page is None or df_page.empty:
            self.ax.set_title("Aucune donnée")
            self.draw()
            return

        # Assure que les colonnes sont numériques
        for col in ["open", "high", "low", "close"]:
            df_page[col] = pd.to_numeric(df_page[col], errors="coerce")
        df_page = df_page.dropna(subset=["open", "high", "low", "close"])

        if df_page.empty:
            self.ax.set_title("Données invalides pour OHLC")
            self.draw()
            return

        dates = mdates.date2num(df_page.index.to_pydatetime())
        opens = df_page["open"].values
        highs = df_page["high"].values
        lows = df_page["low"].values
        closes = df_page["close"].values

        width = 0.6  # largeur des bougies
        for d, o, h, l, c in zip(dates, opens, highs, lows, closes):
            color = "green" if c >= o else "red"
            # mèche
            self.ax.vlines(d, l, h, color=color, linewidth=1)
            # corps
            lower = min(o, c)
            height = abs(c - o) if abs(c - o) > 1e-12 else 1e-12
            rect = self.ax.bar(d, height, width, bottom=lower, color=color, align="center")

        self.ax.xaxis_date()
        self.ax.set_xlabel("Temps")
        self.ax.set_ylabel("Prix")
        self.ax.grid(True, linestyle="--", alpha=0.3)
        self.fig.autofmt_xdate()
        self.draw()


# --- Fenêtre principale ---

class KlineViewer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Kline Viewer - Binance CSV (PyQt)")
        self.resize(1200, 800)

        self.df_raw = None
        self.df = None
        self.df_tf = None
        self.detected_tf = None
        self.total_candles = 0
        self.num_pages = 1

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_layout = QtWidgets.QVBoxLayout(central)

        # --- Zone contrôles haut ---

        controls_layout = QtWidgets.QGridLayout()

        self.btn_load = QtWidgets.QPushButton("Charger CSV...")
        self.lbl_file = QtWidgets.QLabel("Aucun fichier chargé")

        self.combo_tf = QtWidgets.QComboBox()
        self.combo_tf.setEnabled(False)

        self.spin_page_size = QtWidgets.QSpinBox()
        self.spin_page_size.setRange(50, 10000)
        self.spin_page_size.setSingleStep(50)
        self.spin_page_size.setValue(500)

        self.spin_page = QtWidgets.QSpinBox()
        self.spin_page.setRange(1, 1)
        self.spin_page.setValue(1)
        self.spin_page.setEnabled(False)

        controls_layout.addWidget(self.btn_load, 0, 0)
        controls_layout.addWidget(self.lbl_file, 0, 1, 1, 3)

        controls_layout.addWidget(QtWidgets.QLabel("Timeframe affichage :"), 1, 0)
        controls_layout.addWidget(self.combo_tf, 1, 1)

        controls_layout.addWidget(QtWidgets.QLabel("Bougies / page :"), 1, 2)
        controls_layout.addWidget(self.spin_page_size, 1, 3)

        controls_layout.addWidget(QtWidgets.QLabel("Page :"), 2, 0)
        controls_layout.addWidget(self.spin_page, 2, 1)

        main_layout.addLayout(controls_layout)

        # --- Canvas graphique ---

        self.canvas = CandlestickCanvas(self)
        main_layout.addWidget(self.canvas, stretch=1)

        # --- Infos bas ---

        self.lbl_info = QtWidgets.QLabel("Charge un fichier CSV pour commencer.")
        main_layout.addWidget(self.lbl_info)

        # --- Connexions ---

        self.btn_load.clicked.connect(self.load_csv)
        self.combo_tf.currentTextChanged.connect(self.on_timeframe_changed)
        self.spin_page_size.valueChanged.connect(self.on_page_settings_changed)
        self.spin_page.valueChanged.connect(self.on_page_settings_changed)

    # --- Logic ---

    def load_csv(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choisir un fichier CSV de klines",
            str(Path.cwd()),
            "Fichiers CSV (*.csv);;Tous les fichiers (*.*)",
        )
        if not file_path:
            return

        try:
            self.lbl_file.setText(f"Chargement : {file_path}")
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

            df_raw = pd.read_csv(file_path)
            df_raw = normalize_columns(df_raw)
            time_col = find_time_column(df_raw)
            df = to_datetime_index(df_raw, time_col)

            if df.empty:
                raise ValueError("Impossible de parser les dates, DataFrame vide.")

            self.df_raw = df_raw
            self.df = df

            self.detected_tf = detect_timeframe(df)
            self.setup_timeframes()
            self.update_resampled()
            self.update_plot()

            self.lbl_file.setText(f"Fichier : {file_path}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Erreur de chargement", f"Erreur lors du chargement du CSV :\n{e}"
            )
            self.lbl_file.setText("Erreur de chargement")
            self.df = None
            self.df_tf = None
            self.canvas.plot_candles(None)
            self.lbl_info.setText("Impossible de charger le fichier.")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def setup_timeframes(self):
        self.combo_tf.blockSignals(True)
        self.combo_tf.clear()

        if self.detected_tf in TIMEFRAME_ORDER:
            base_idx = TIMEFRAME_ORDER.index(self.detected_tf)
            available_tfs = TIMEFRAME_ORDER[base_idx:]
        else:
            available_tfs = TIMEFRAME_ORDER

        for tf in available_tfs:
            self.combo_tf.addItem(tf)

        self.combo_tf.setEnabled(True)
        self.combo_tf.setCurrentIndex(0)
        self.combo_tf.blockSignals(False)

    def update_resampled(self):
        if self.df is None:
            return

        selected_tf = self.combo_tf.currentText()
        if not selected_tf:
            return

        if self.detected_tf is not None and selected_tf == self.detected_tf:
            df_tf = self.df.copy()
        else:
            df_tf = resample_klines(self.df, selected_tf)

        self.df_tf = df_tf
        self.total_candles = len(df_tf)
        page_size = self.spin_page_size.value()

        self.num_pages = max(1, math.ceil(self.total_candles / page_size))
        self.spin_page.blockSignals(True)
        self.spin_page.setRange(1, self.num_pages)
        self.spin_page.setValue(self.num_pages)  # dernière page = plus récent
        self.spin_page.setEnabled(True)
        self.spin_page.blockSignals(False)

    def on_timeframe_changed(self, _):
        if self.df is None:
            return
        try:
            self.update_resampled()
            self.update_plot()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Erreur", f"Erreur lors du changement de timeframe :\n{e}"
            )

    def on_page_settings_changed(self, _):
        if self.df_tf is None:
            return
        try:
            # Recalcule nb de pages si on change la taille
            page_size = self.spin_page_size.value()
            self.num_pages = max(1, math.ceil(self.total_candles / page_size))
            self.spin_page.blockSignals(True)
            current_page = self.spin_page.value()
            self.spin_page.setRange(1, self.num_pages)
            if current_page > self.num_pages:
                self.spin_page.setValue(self.num_pages)
            self.spin_page.blockSignals(False)

            self.update_plot()
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Erreur", f"Erreur lors de la mise à jour de la page :\n{e}"
            )

    def update_plot(self):
        if self.df_tf is None or self.df_tf.empty:
            self.canvas.plot_candles(None)
            self.lbl_info.setText("Aucune donnée à afficher.")
            return

        page_size = self.spin_page_size.value()
        page = self.spin_page.value()

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_df = self.df_tf.iloc[start_idx:end_idx]

        self.canvas.plot_candles(page_df)

        selected_tf = self.combo_tf.currentText()
        start_str = self.df_tf.index[0].strftime("%Y-%m-%d %H:%M:%S")
        end_str = self.df_tf.index[-1].strftime("%Y-%m-%d %H:%M:%S")
        info = (
            f"Bougies totales: {self.total_candles} | Timeframe: {selected_tf} | "
            f"Période: {start_str} → {end_str} | "
            f"Page {page}/{self.num_pages} "
            f"({start_idx + 1}–{min(end_idx, self.total_candles)})"
        )
        self.lbl_info.setText(info)


def main():
    app = QtWidgets.QApplication(sys.argv)
    viewer = KlineViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
