import sys
import os
import math
import time
import csv
from collections import deque
from datetime import datetime

import requests
from PyQt5 import QtCore, QtWidgets


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

# Interval -> milliseconds
INTERVAL_MS = {
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
    "1M": 30 * 24 * 60 * 60_000,  # approximation
}

# Limites "safe" estimées pour ne pas saturer la rate limit
MAX_REQ_PER_MINUTE = 1100  # sous la limite officielle 1200/min pour klines
KLINES_LIMIT = 1000        # max klines par requête


class KlineDownloader(QtCore.QObject):
    progress_changed = QtCore.pyqtSignal(int)         # 0–100 %
    log_message = QtCore.pyqtSignal(str)
    stats_updated = QtCore.pyqtSignal(int, int)       # (req_last_min, total_req)
    download_finished = QtCore.pyqtSignal()
    download_error = QtCore.pyqtSignal(str)

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.params = params
        self._abort = False

        # stats
        self.request_times = deque()
        self.total_requests = 0

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self._run_internal()
        except Exception as e:
            self.download_error.emit(f"Erreur : {e}")
        finally:
            self.download_finished.emit()

    def abort(self):
        self._abort = True

    def _run_internal(self):
        symbol = self.params["symbol"]
        interval = self.params["interval"]
        use_cache = self.params["use_cache"]
        output_dir = self.params["output_dir"]
        since_beginning = self.params["since_beginning"]
        until_now = self.params["until_now"]
        start_dt = self.params["start_dt"]
        end_dt = self.params["end_dt"]

        if interval not in INTERVAL_MS:
            raise ValueError(f"Intervalle non supporté : {interval}")

        interval_ms = INTERVAL_MS[interval]

        # Détermination de start_ms et end_ms
        now_dt = datetime.utcnow()
        if since_beginning:
            # on part d'une date très ancienne (janvier 2017, avant lancement Binance)
            start_dt_effective = datetime(2017, 1, 1)
        else:
            start_dt_effective = start_dt

        if until_now:
            end_dt_effective = now_dt
        else:
            end_dt_effective = end_dt

        start_ms = int(start_dt_effective.timestamp() * 1000)
        end_ms = int(end_dt_effective.timestamp() * 1000)

        if end_ms <= start_ms:
            raise ValueError("La date de fin doit être postérieure à la date de début.")

        # Construction du nom de fichier
        start_str = start_dt_effective.strftime("%Y%m%d_%H%M%S") if not since_beginning else "from_beginning"
        end_str = end_dt_effective.strftime("%Y%m%d_%H%M%S") if not until_now else "to_now"
        filename = f"klines_{symbol}_{interval}_{start_str}_{end_str}.csv"
        filepath = os.path.join(output_dir, filename)

        # Gestion du cache
        file_exists = os.path.isfile(filepath)
        new_file = True
        if use_cache and file_exists:
            # On lit la dernière ligne pour reprendre à partir de là
            self.log_message.emit("Fichier existant détecté, utilisation comme cache…")
            last_open_time = self._get_last_open_time_from_file(filepath)
            if last_open_time is not None:
                # on reprend juste après la dernière bougie
                start_ms = max(start_ms, last_open_time + interval_ms)
                new_file = False
                self.log_message.emit(
                    f"Reprise à partir de {datetime.utcfromtimestamp(start_ms/1000).isoformat()} (UTC)"
                )

        # Estimation du nombre de requêtes
        total_candles_est = max(1, math.ceil((end_ms - start_ms) / interval_ms))
        total_requests_est = max(1, math.ceil(total_candles_est / KLINES_LIMIT))

        self.log_message.emit(f"Symbol : {symbol}, intervalle : {interval}")
        self.log_message.emit(
            f"Fenêtre temporelle : {datetime.utcfromtimestamp(start_ms/1000)} -> "
            f"{datetime.utcfromtimestamp(end_ms/1000)} (UTC)"
        )
        self.log_message.emit(
            f"Estimation : ~{total_candles_est} bougies, ~{total_requests_est} requêtes."
        )
        self.log_message.emit(f"Fichier de sortie : {filepath}")

        # Ouverture du fichier
        if new_file:
            f = open(filepath, "w", newline="", encoding="utf-8")
            writer = csv.writer(f)
            writer.writerow([
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume",
                "ignore",
            ])
        else:
            f = open(filepath, "a", newline="", encoding="utf-8")
            writer = csv.writer(f)

        with f:
            current_start = start_ms
            requests_done = 0

            while current_start < end_ms and not self._abort:
                # Rate limit "maison"
                self._respect_rate_limit()

                params = {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": KLINES_LIMIT,
                    "startTime": current_start,
                    "endTime": end_ms,
                }

                resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=15)
                self._register_request()

                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Erreur HTTP {resp.status_code} : {resp.text}"
                    )

                data = resp.json()
                if not data:
                    self.log_message.emit("Plus aucune donnée renvoyée, téléchargement terminé.")
                    break

                # Écriture dans le fichier
                for k in data:
                    writer.writerow(k)

                f.flush()
                os.fsync(f.fileno())

                last_open_time = data[-1][0]
                current_start = last_open_time + interval_ms
                requests_done += 1

                # Mise à jour progrès
                done_ratio = (current_start - start_ms) / (end_ms - start_ms)
                done_ratio = max(0.0, min(1.0, done_ratio))
                self.progress_changed.emit(int(done_ratio * 100))

                self.log_message.emit(
                    f"Batch #{requests_done} : {len(data)} bougies, "
                    f"dernière bougie : {datetime.utcfromtimestamp(last_open_time/1000)} (UTC)"
                )

                if current_start >= end_ms:
                    self.log_message.emit("Téléchargement terminé (toutes les données ont été récupérées).")
                    break

            if self._abort:
                self.log_message.emit("Téléchargement interrompu par l'utilisateur.")

    def _get_last_open_time_from_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) <= 1:
                return None
            last_line = lines[-1].strip()
            if not last_line:
                return None
            parts = last_line.split(",")
            return int(parts[0])
        except Exception as e:
            self.log_message.emit(f"Impossible de lire le cache existant : {e}")
            return None

    def _respect_rate_limit(self):
        now = time.time()
        # purger les entrées trop anciennes (> 60s)
        while self.request_times and (now - self.request_times[0] > 60):
            self.request_times.popleft()

        if len(self.request_times) >= MAX_REQ_PER_MINUTE:
            sleep_for = 60 - (now - self.request_times[0]) + 0.1
            if sleep_for > 0:
                self.log_message.emit(
                    f"Rate limit proche, pause de {sleep_for:.1f} s pour éviter le blacklist."
                )
                time.sleep(sleep_for)

    def _register_request(self):
        now = time.time()
        self.request_times.append(now)
        self.total_requests += 1

        # nettoyage
        while self.request_times and (now - self.request_times[0] > 60):
            self.request_times.popleft()

        self.stats_updated.emit(len(self.request_times), self.total_requests)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Téléchargeur de klines Binance")
        self.resize(900, 600)

        self.worker_thread = None
        self.worker = None

        self._build_ui()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_layout = QtWidgets.QVBoxLayout(central)

        # Zone paramètres
        form = QtWidgets.QFormLayout()

        self.symbol_edit = QtWidgets.QLineEdit("BTCUSDT")
        form.addRow("Pair (ex: BTCUSDT) :", self.symbol_edit)

        self.interval_combo = QtWidgets.QComboBox()
        self.interval_combo.addItems(list(INTERVAL_MS.keys()))
        self.interval_combo.setCurrentText("1h")
        form.addRow("Timeframe :", self.interval_combo)

        # Dates
        now = QtCore.QDateTime.currentDateTimeUtc()
        one_month_ago = now.addMonths(-1)

        self.since_beginning_cb = QtWidgets.QCheckBox("Depuis le début de la crypto")
        self.until_now_cb = QtWidgets.QCheckBox("Jusqu'à maintenant")

        self.start_dt_edit = QtWidgets.QDateTimeEdit(one_month_ago)
        self.start_dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_dt_edit.setCalendarPopup(True)

        self.end_dt_edit = QtWidgets.QDateTimeEdit(now)
        self.end_dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_dt_edit.setCalendarPopup(True)

        date_layout = QtWidgets.QGridLayout()
        date_layout.addWidget(QtWidgets.QLabel("Date de début (UTC) :"), 0, 0)
        date_layout.addWidget(self.start_dt_edit, 0, 1)
        date_layout.addWidget(self.since_beginning_cb, 0, 2)

        date_layout.addWidget(QtWidgets.QLabel("Date de fin (UTC) :"), 1, 0)
        date_layout.addWidget(self.end_dt_edit, 1, 1)
        date_layout.addWidget(self.until_now_cb, 1, 2)

        form.addRow(date_layout)

        # Dossier de sortie
        out_layout = QtWidgets.QHBoxLayout()
        self.output_dir_edit = QtWidgets.QLineEdit(os.getcwd())
        browse_btn = QtWidgets.QPushButton("Parcourir…")
        browse_btn.clicked.connect(self.browse_output_dir)
        out_layout.addWidget(self.output_dir_edit)
        out_layout.addWidget(browse_btn)
        form.addRow("Dossier de sortie :", out_layout)

        # Cache
        self.use_cache_cb = QtWidgets.QCheckBox("Utiliser le fichier existant comme cache")
        self.use_cache_cb.setChecked(True)
        form.addRow(self.use_cache_cb)

        main_layout.addLayout(form)

        # Boutons & barre de progression
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Démarrer le téléchargement")
        self.stop_btn = QtWidgets.QPushButton("Arrêter")
        self.stop_btn.setEnabled(False)

        self.start_btn.clicked.connect(self.start_download)
        self.stop_btn.clicked.connect(self.stop_download)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # Stats rate limit
        stats_layout = QtWidgets.QHBoxLayout()
        self.req_min_label = QtWidgets.QLabel("Requêtes (60s) : 0")
        self.req_total_label = QtWidgets.QLabel("Requêtes totales : 0")
        self.rate_hint_label = QtWidgets.QLabel(
            f"Limite estimée : {MAX_REQ_PER_MINUTE} req/min (safe)"
        )
        stats_layout.addWidget(self.req_min_label)
        stats_layout.addWidget(self.req_total_label)
        stats_layout.addStretch()
        stats_layout.addWidget(self.rate_hint_label)
        main_layout.addLayout(stats_layout)

        # Log
        self.log_edit = QtWidgets.QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        main_layout.addWidget(self.log_edit)

        # Connexions pour activer/désactiver dates
        self.since_beginning_cb.toggled.connect(self._update_date_inputs)
        self.until_now_cb.toggled.connect(self._update_date_inputs)
        self._update_date_inputs()

    def _update_date_inputs(self):
        self.start_dt_edit.setEnabled(not self.since_beginning_cb.isChecked())
        self.end_dt_edit.setEnabled(not self.until_now_cb.isChecked())

    def browse_output_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de sortie", self.output_dir_edit.text()
        )
        if d:
            self.output_dir_edit.setText(d)

    def start_download(self):
        if self.worker_thread is not None:
            QtWidgets.QMessageBox.warning(self, "Téléchargement en cours", "Un téléchargement est déjà en cours.")
            return

        symbol = self.symbol_edit.text().strip()
        if not symbol:
            QtWidgets.QMessageBox.warning(self, "Erreur", "Veuillez saisir une pair de trading.")
            return

        interval = self.interval_combo.currentText()
        output_dir = self.output_dir_edit.text().strip() or os.getcwd()

        if not os.path.isdir(output_dir):
            QtWidgets.QMessageBox.warning(self, "Erreur", "Le dossier de sortie n'existe pas.")
            return

        params = {
            "symbol": symbol,
            "interval": interval,
            "use_cache": self.use_cache_cb.isChecked(),
            "output_dir": output_dir,
            "since_beginning": self.since_beginning_cb.isChecked(),
            "until_now": self.until_now_cb.isChecked(),
            "start_dt": self.start_dt_edit.dateTime().toUTC().toPyDateTime(),
            "end_dt": self.end_dt_edit.dateTime().toUTC().toPyDateTime(),
        }

        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self.req_min_label.setText("Requêtes (60s) : 0")
        self.req_total_label.setText("Requêtes totales : 0")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.worker_thread = QtCore.QThread()
        self.worker = KlineDownloader(params)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.log_message.connect(self.append_log)
        self.worker.stats_updated.connect(self.update_stats)
        self.worker.download_error.connect(self.on_error)
        self.worker.download_finished.connect(self.on_finished)

        # Nettoyage thread
        self.worker.download_finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_thread)

        self.worker_thread.start()

    def stop_download(self):
        if self.worker is not None:
            self.worker.abort()
            self.append_log("Demande d'arrêt envoyée…")

    def _cleanup_thread(self):
        self.worker_thread.wait()
        self.worker_thread = None
        self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    @QtCore.pyqtSlot(str)
    def append_log(self, text):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self.log_edit.appendPlainText(f"[{ts} UTC] {text}")

    @QtCore.pyqtSlot(int, int)
    def update_stats(self, req_last_min, total_req):
        self.req_min_label.setText(f"Requêtes (60s) : {req_last_min}")
        self.req_total_label.setText(f"Requêtes totales : {total_req}")

    @QtCore.pyqtSlot(str)
    def on_error(self, msg):
        self.append_log(msg)
        QtWidgets.QMessageBox.critical(self, "Erreur", msg)

    @QtCore.pyqtSlot()
    def on_finished(self):
        self.append_log("Téléchargement terminé.")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def closeEvent(self, event):
        if self.worker is not None:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Quitter",
                "Un téléchargement est en cours. Voulez-vous vraiment quitter ?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.No:
                event.ignore()
                return
            self.worker.abort()
            time.sleep(0.2)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
