import sys
import json
import time
import threading
from datetime import datetime, timedelta

from PyQt5 import QtCore, QtWidgets

# Assure-toi d'avoir installé websocket-client
# pip install websocket-client


class BinancePriceStream(QtCore.QThread):
    """Thread dédié à la connexion WebSocket Binance pour une paire donnée."""
    price_received = QtCore.pyqtSignal(float)
    error = QtCore.pyqtSignal(str)

    def __init__(self, symbol: str, parent=None):
        super().__init__(parent)
        self.symbol = symbol.lower()
        self.ws = None
        self._stop_event = threading.Event()

    def run(self):
        import websocket

        stream_name = f"{self.symbol}@trade"
        url = f"wss://stream.binance.com:9443/ws/{stream_name}"

        def on_message(ws, message):
            if self._stop_event.is_set():
                ws.close()
                return
            try:
                data = json.loads(message)
                price = float(data["p"])  # prix du trade
                self.price_received.emit(price)
            except Exception as e:
                self.error.emit(f"Parse error: {e}")

        def on_error(ws, error):
            self.error.emit(str(error))

        def on_close(ws, *args):
            # On laisse simplement fermer
            pass

        while not self._stop_event.is_set():
            try:
                self.ws = websocket.WebSocketApp(
                    url,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close
                )
                self.ws.run_forever()
            except Exception as e:
                self.error.emit(f"WebSocket exception: {e}")
                # tentative de reconnexion simple
                time.sleep(5)
            else:
                break  # sortie normale

    def stop(self):
        self._stop_event.set()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass


class CryptoTickerWidget(QtWidgets.QWidget):
    """Widget très fin en hauteur, sans bordure OS, pour suivre une paire crypto."""

    def __init__(self):
        super().__init__()
        self.price_stream = None
        self.current_price = None
        self.position_open_time = None  # datetime à partir de laquelle la position est considérée ouverte
        self.always_on_top = True
        self.drag_position = None

        # Historique de prix pour la tendance
        self.price_history = []  # liste de tuples (datetime, price)
        self.trend_timeframes = {
            "3m": 3 * 60,
            "5m": 5 * 60,
            "15m": 15 * 60,
            "1h": 60 * 60,
            "4h": 4 * 60 * 60,
            "1d": 24 * 60 * 60,
        }
        self.current_trend_tf = "3m"
        self.trend_timeframe_seconds = self.trend_timeframes[self.current_trend_tf]

        self.init_ui()
        self.init_window_flags()
        self.start_price_stream(self.symbol_box.currentText())

    def init_window_flags(self):
        flags = (
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setWindowFlags(flags)
        self.setFixedHeight(30)  # très fin
        self.always_on_top = True

    def init_ui(self):
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # Sélection de paire
        self.symbol_box = QtWidgets.QComboBox()
        self.symbol_box.setEditable(True)
        self.symbol_box.addItems(["BTCUSDC", "ETHUSDC", "INJUSDC", "BNBUSDC"])
        self.symbol_box.setFixedWidth(90)
        self.symbol_box.setToolTip("Paire Binance (ex: BTCUSDC)")
        layout.addWidget(self.symbol_box)

        # Prix actuel
        self.price_label = QtWidgets.QLabel("—")
        self.price_label.setMinimumWidth(70)
        self.price_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.price_label)

        # Direction (Long / Short)
        self.direction_box = QtWidgets.QComboBox()
        self.direction_box.addItems(["Long", "Short"])
        self.direction_box.setFixedWidth(60)
        layout.addWidget(self.direction_box)

        # Prix d'entrée
        self.entry_edit = QtWidgets.QLineEdit()
        self.entry_edit.setPlaceholderText("Entry")
        self.entry_edit.setFixedWidth(70)
        self.entry_edit.setToolTip("Prix d'entrée")
        layout.addWidget(self.entry_edit)

        # Prix de sortie cible
        self.exit_edit = QtWidgets.QLineEdit()
        self.exit_edit.setPlaceholderText("Exit")
        self.exit_edit.setFixedWidth(70)
        self.exit_edit.setToolTip("Prix de sortie cible")
        layout.addWidget(self.exit_edit)

        # Levier
        self.leverage_edit = QtWidgets.QLineEdit()
        self.leverage_edit.setPlaceholderText("Lev")
        self.leverage_edit.setFixedWidth(40)
        self.leverage_edit.setText("5")
        self.leverage_edit.setToolTip("Levier (ex: 5)")
        layout.addWidget(self.leverage_edit)

        # PnL maintenant (%)
        self.pnl_now_label = QtWidgets.QLabel("Now: —")
        self.pnl_now_label.setMinimumWidth(80)
        layout.addWidget(self.pnl_now_label)

        # PnL à la sortie cible (%)
        self.pnl_target_label = QtWidgets.QLabel("Target: —")
        self.pnl_target_label.setMinimumWidth(100)
        layout.addWidget(self.pnl_target_label)

        self.setLayout(layout)

        # Connexions des signaux
        self.symbol_box.currentTextChanged.connect(self.change_symbol)
        self.direction_box.currentIndexChanged.connect(self.update_pnl)
        self.entry_edit.textChanged.connect(self.on_entry_changed)
        self.exit_edit.textChanged.connect(self.update_pnl)
        self.leverage_edit.textChanged.connect(self.update_pnl)

    # -------------------
    # Gestion WebSocket
    # -------------------

    def start_price_stream(self, symbol: str):
        if self.price_stream is not None:
            self.price_stream.price_received.disconnect(self.on_price)
            self.price_stream.error.disconnect(self.on_stream_error)
            self.price_stream.stop()
            self.price_stream.wait()
            self.price_stream = None

        self.current_price = None
        self.price_history.clear()
        self.price_label.setText("…")
        self.price_label.setStyleSheet("")

        self.price_stream = BinancePriceStream(symbol)
        self.price_stream.price_received.connect(self.on_price)
        self.price_stream.error.connect(self.on_stream_error)
        self.price_stream.start()

    def change_symbol(self, symbol: str):
        if not symbol:
            return
        self.start_price_stream(symbol)

    @QtCore.pyqtSlot(float)
    def on_price(self, price: float):
        self.current_price = price
        self.price_label.setText(f"{price:.4f}")

        # Mise à jour de l'historique de prix pour la tendance
        now = datetime.utcnow()
        self.price_history.append((now, price))

        # Nettoyage de l'historique en fonction de la timeframe courante
        cutoff = now - timedelta(seconds=self.trend_timeframe_seconds)
        self.price_history = [
            (t, p) for (t, p) in self.price_history if t >= cutoff
        ]

        # Mise à jour de la couleur du prix selon la tendance
        self.update_price_color()

        # Recalcul du PnL
        self.update_pnl()

    @QtCore.pyqtSlot(str)
    def on_stream_error(self, msg: str):
        # En production, on pourrait logguer cela proprement
        self.price_label.setText("ERR")
        self.price_label.setStyleSheet("color: rgb(200, 0, 0);")

    # -------------------
    # Gestion couleur du prix (tendance)
    # -------------------

    def update_price_color(self):
        """
        Met le prix en vert s'il est supérieur au prix de référence
        (début de la fenêtre de timeframe choisie), rouge s'il est inférieur.
        """
        if self.current_price is None or not self.price_history:
            self.price_label.setStyleSheet("")
            return

        # Le premier élément de l'historique est le plus ancien encore dans la fenêtre
        baseline_price = self.price_history[0][1]

        if self.current_price > baseline_price:
            # Tendance haussière sur la période
            self.price_label.setStyleSheet("color: rgb(0, 170, 0);")
        elif self.current_price < baseline_price:
            # Tendance baissière
            self.price_label.setStyleSheet("color: rgb(200, 0, 0);")
        else:
            # Neutre
            self.price_label.setStyleSheet("")

    # -------------------
    # Calculs de PnL
    # -------------------

    def parse_float(self, text: str):
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    def on_entry_changed(self):
        """Quand le prix d'entrée change, on considère que la position est 'ouverte' maintenant."""
        entry = self.parse_float(self.entry_edit.text())
        if entry is not None:
            self.position_open_time = datetime.utcnow()
        self.update_pnl()

    def compute_fees_pct(self) -> float:
        """
        Calcule les frais totaux en pourcentage :
        - 0.1 % à l'ouverture
        - 0.1 % à la fermeture
        - 0.01 % par heure où la position est ouverte
        """
        base_fees = 0.1 + 0.1  # 0.1% open + 0.1% close = 0.2%
        hourly_fee = 0.01

        if self.position_open_time is None:
            hours_open = 0.0
        else:
            delta = datetime.utcnow() - self.position_open_time
            hours_open = max(delta.total_seconds() / 3600.0, 0.0)

        time_fees = hours_open * hourly_fee
        return base_fees + time_fees

    def set_pnl_label_color(self, label: QtWidgets.QLabel, pnl_value):
        """Applique la couleur verte/rouge en fonction du signe du PnL."""
        if pnl_value is None:
            label.setStyleSheet("")
            return

        try:
            v = float(pnl_value)
        except (TypeError, ValueError):
            label.setStyleSheet("")
            return

        if v > 0:
            label.setStyleSheet("color: rgb(0, 170, 0);")
        elif v < 0:
            label.setStyleSheet("color: rgb(200, 0, 0);")
        else:
            label.setStyleSheet("")

    def clear_pnl_labels(self):
        self.pnl_now_label.setText("Now: —")
        self.pnl_now_label.setStyleSheet("")
        self.pnl_target_label.setText("Target: —")
        self.pnl_target_label.setStyleSheet("")

    def update_pnl(self):
        if self.current_price is None:
            self.clear_pnl_labels()
            return

        entry = self.parse_float(self.entry_edit.text())
        if entry is None or entry <= 0:
            self.clear_pnl_labels()
            return

        leverage = self.parse_float(self.leverage_edit.text())
        if leverage is None or leverage <= 0:
            leverage = 1.0

        exit_price = self.parse_float(self.exit_edit.text())

        direction = 1.0 if self.direction_box.currentText().lower() == "long" else -1.0

        fees_pct = self.compute_fees_pct()  # en %

        # PnL si on sort maintenant
        price_change_now = direction * (self.current_price - entry) / entry
        pnl_now_pct = price_change_now * leverage * 100.0 - fees_pct

        self.pnl_now_label.setText(f"Now: {pnl_now_pct:+.2f}%")
        self.set_pnl_label_color(self.pnl_now_label, pnl_now_pct)

        # PnL si on sort au prix cible (utilise la même durée pour les frais, pour simplifier)
        if exit_price is not None and exit_price > 0:
            price_change_target = direction * (exit_price - entry) / entry
            pnl_target_pct = price_change_target * leverage * 100.0 - fees_pct
            self.pnl_target_label.setText(f"Target: {pnl_target_pct:+.2f}%")
            self.set_pnl_label_color(self.pnl_target_label, pnl_target_pct)
        else:
            self.pnl_target_label.setText("Target: —")
            self.pnl_target_label.setStyleSheet("")

    # -------------------
    # Contexte / clic droit
    # -------------------

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)

        always_on_top_action = menu.addAction("SetAlwaysOnTop")
        always_on_top_action.setCheckable(True)
        always_on_top_action.setChecked(self.always_on_top)

        # Sous-menu pour la timeframe de tendance
        timeframe_menu = menu.addMenu("Timeframe tendance")
        timeframe_actions = {}

        for tf in ["3m", "5m", "15m", "1h", "4h", "1d"]:
            act = timeframe_menu.addAction(tf)
            act.setCheckable(True)
            if tf == self.current_trend_tf:
                act.setChecked(True)
            timeframe_actions[act] = tf

        menu.addSeparator()
        quit_action = menu.addAction("Quitter")

        action = menu.exec_(event.globalPos())

        if action == always_on_top_action:
            self.set_always_on_top(always_on_top_action.isChecked())
        elif action == quit_action:
            QtWidgets.qApp.quit()
        elif action in timeframe_actions:
            chosen_tf = timeframe_actions[action]
            self.set_trend_timeframe(chosen_tf)

    def set_trend_timeframe(self, timeframe_key: str):
        """Modifie la timeframe utilisée pour déterminer si le prix est haussier ou baissier."""
        if timeframe_key not in self.trend_timeframes:
            return
        self.current_trend_tf = timeframe_key
        self.trend_timeframe_seconds = self.trend_timeframes[timeframe_key]

        # On nettoie l'historique immédiatement pour s'adapter à la nouvelle fenêtre
        if self.price_history:
            now = datetime.utcnow()
            cutoff = now - timedelta(seconds=self.trend_timeframe_seconds)
            self.price_history = [
                (t, p) for (t, p) in self.price_history if t >= cutoff
            ]

        # Recalcul de la couleur du prix en fonction de la nouvelle timeframe
        self.update_price_color()

    def set_always_on_top(self, enabled: bool):
        flags = self.windowFlags()
        if enabled:
            flags |= QtCore.Qt.WindowStaysOnTopHint
        else:
            flags &= ~QtCore.Qt.WindowStaysOnTopHint

        self.always_on_top = enabled
        self.setWindowFlags(flags)
        self.show()

    # -------------------
    # Déplacement de la fenêtre (drag)
    # -------------------

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    # -------------------
    # Nettoyage
    # -------------------

    def closeEvent(self, event):
        if self.price_stream is not None:
            self.price_stream.stop()
            self.price_stream.wait(2000)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)

    widget = CryptoTickerWidget()
    widget.setWindowTitle("Crypto Ticker")
    widget.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
