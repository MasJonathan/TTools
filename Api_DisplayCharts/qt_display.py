# qt_display.py

import sys
from pathlib import Path

import pandas as pd

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QSlider, QLabel
)
from PyQt5.QtCore import Qt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import mplfinance as mpf


# ---------------------------------------------------------------------
#  Paramètres : chemin du fichier et taille de la fenêtre (nb de bougies)
# ---------------------------------------------------------------------
CSV_PATH = Path("../Data/klines_INJUSDC_1m_from_beginning_to_now.csv")
WINDOW_SIZE = 1000  # nombre de bougies affichées dans la fenêtre


# =====================================================================
#                 Source de données : lecture par chunks
# =====================================================================
class KlinesDataSource:
    """
    Lit un gros fichier de klines par fenêtre (chunks), et gère
    automatiquement deux formats pour la colonne open_time :
        - epoch en millisecondes : 1703750400000
        - string datetime       : 2025-01-01 00:00:00
    """

    def __init__(self, csv_path: Path, window_size: int = 1000):
        self.csv_path = csv_path
        self.window_size = window_size

        if not self.csv_path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {self.csv_path}")

        self.total_rows = self._count_rows()
        print(f"Total de lignes de données (hors en-tête) : {self.total_rows}")

    def _count_rows(self) -> int:
        """Compte les lignes de données (sans l'en-tête)."""
        with self.csv_path.open("r", encoding="utf-8") as f:
            # -1 pour exclure la ligne d'en-tête
            return sum(1 for _ in f) - 1

    # ---------- Conversion spécifique à nos deux formats ----------
    def _parse_open_time(self, s: pd.Series) -> pd.Series:
        """
        Convertit la série 'open_time' en datetime, en gérant uniquement
        les deux formats suivants :
            1) Epoch ms  (ex : 1703750400000)
            2) String    (ex : "2025-01-01 00:00:00")
        """
        # On force d'abord en string
        s_str = s.astype(str)

        # Tentative : est-ce que ce sont essentiellement des nombres ?
        s_num = pd.to_numeric(s_str, errors="coerce")
        numeric_ratio = s_num.notna().mean()

        if numeric_ratio > 0.9:
            # On considère que c'est de l'epoch en millisecondes
            # (c'est le format de votre second screenshot)
            dt = pd.to_datetime(s_num, unit="ms")
            return dt

        # Sinon, on considère que c'est une chaîne "YYYY-MM-DD HH:MM:SS"
        # (format de votre premier screenshot)
        try:
            dt = pd.to_datetime(
                s_str,
                format="%Y-%m-%d %H:%M:%S",
                errors="raise",
            )
        except Exception as exc:
            raise ValueError(
                "La colonne 'open_time' n'est ni en epoch ms ni en "
                "string au format 'YYYY-MM-DD HH:MM:SS'."
            ) from exc

        return dt

    # ---------- Lecture d'une fenêtre de données ----------
    def load_window(self, start_row: int) -> pd.DataFrame:
        """
        Charge une fenêtre de données à partir d'une ligne de début.
        Retourne un DataFrame indexé par Date, avec colonnes :
        Open, High, Low, Close, Volume, EMA12.
        """
        if start_row < 0:
            start_row = 0
        if start_row > max(0, self.total_rows - self.window_size):
            start_row = max(0, self.total_rows - self.window_size)

        nrows = self.window_size
        # On saute les lignes de données avant start_row (en gardant l'en-tête)
        skip = range(1, start_row + 1)

        # Lecture brute : open_time en texte, le reste en numérique
        df = pd.read_csv(
            self.csv_path,
            skiprows=skip,
            nrows=nrows,
            usecols=["open_time", "open", "high", "low", "close", "volume"],
            dtype={"open_time": str},  # très important pour la détection de format
        )

        if df.empty:
            return df

        # Conversion de open_time → datetime (2 formats possibles)
        df["open_time"] = self._parse_open_time(df["open_time"])

        # Renommage pour mplfinance
        df.rename(
            columns={
                "open_time": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            },
            inplace=True,
        )

        # Index temporel
        df.set_index("Date", inplace=True)

        # EMA12 sur le cours de clôture (sur la fenêtre courante)
        df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()

        return df


# =====================================================================
#                     Widget d'affichage des chandeliers
# =====================================================================
class CandleWidget(QWidget):
    """
    Widget PyQt contenant une figure Matplotlib/mplfinance
    pour afficher les chandeliers, le volume et l'EMA12.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.fig = mpf.figure(style="yahoo", figsize=(10, 6))
        self.canvas = FigureCanvas(self.fig)

        layout = QVBoxLayout(self)
        layout.addWidget(self.canvas)

        self.ax_price = self.fig.add_subplot(2, 1, 1)
        self.ax_vol = self.fig.add_subplot(2, 1, 2, sharex=self.ax_price)

    def update_data(self, df: pd.DataFrame) -> None:
        """Met à jour le graphique avec un nouveau DataFrame."""
        self.ax_price.clear()
        self.ax_vol.clear()

        if df.empty:
            self.canvas.draw()
            return

        addplots = []
        if "EMA12" in df.columns:
            addplots.append(
                mpf.make_addplot(df["EMA12"], ax=self.ax_price, color="blue")
            )

        mpf.plot(
            df,
            type="candle",
            ax=self.ax_price,
            volume=self.ax_vol,
            addplot=addplots if addplots else None,
            datetime_format="%Y-%m-%d %H:%M",
            xrotation=15,
            show_nontrading=False,
        )

        self.canvas.draw()


# =====================================================================
#                      Fenêtre principale avec slider
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self, csv_path: Path):
        super().__init__()

        self.data_source = KlinesDataSource(csv_path, window_size=WINDOW_SIZE)

        central = QWidget()
        self.setCentralWidget(central)

        self.candle_widget = CandleWidget()

        # Slider pour naviguer dans le fichier
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(
            max(0, self.data_source.total_rows - self.data_source.window_size)
        )
        # Position initiale : fin du fichier (les bougies les plus récentes)
        self.slider.setValue(
            max(0, self.data_source.total_rows - self.data_source.window_size)
        )
        self.slider.valueChanged.connect(self.on_slider_changed)

        # Label d'information
        self.label_position = QLabel()
        self.label_position.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(central)
        layout.addWidget(self.candle_widget)
        layout.addWidget(self.label_position)
        layout.addWidget(self.slider)

        self.setWindowTitle("INJUSDC 1m – navigation par chunks")
        self.resize(1400, 800)

        # Chargement initial
        self.current_start_row = self.slider.value()
        self.load_and_display(self.current_start_row)

    def on_slider_changed(self, value: int) -> None:
        self.current_start_row = value
        self.load_and_display(value)

    def load_and_display(self, start_row: int) -> None:
        df = self.data_source.load_window(start_row)
        self.candle_widget.update_data(df)

        if not df.empty:
            start_time = df.index[0]
            end_time = df.index[-1]
            self.label_position.setText(
                f"Lignes {start_row} à {start_row + len(df) - 1}  |  "
                f"{start_time} → {end_time}"
            )
        else:
            self.label_position.setText("Aucune donnée chargée.")


# =====================================================================
#                               Lancement
# =====================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    try:
        window = MainWindow(CSV_PATH)
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"Erreur : {e}")
        sys.exit(1)
