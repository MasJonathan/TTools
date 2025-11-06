import os
import time
import hmac
import hashlib
import math
import requests
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, getcontext
from statistics import mean, median, pstdev
from collections import defaultdict
from typing import List, Dict, Optional, Tuple

getcontext().prec = 28  # précision globale pour Decimal


# ==========================
# 1. Configuration & client Binance Margin
# ==========================

@dataclass
class BinanceMarginConfig:
    api_key: str
    api_secret: str
    base_url: str = "https://api.binance.com"
    recv_window: int = 5_000


class BinanceMarginRequestError(Exception):
    """Erreur générique pour les requêtes Binance Margin."""
    pass


class BinanceMarginClient:
    """
    Client orienté objet pour les appels API Margin (Spot + levier).
    Encapsule signature et gestion des endpoints SAPI.
    """

    def __init__(self, config: BinanceMarginConfig):
        self.config = config

    def _sign(self, query_string: str) -> str:
        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _send_signed(self, method: str, path: str, params: Dict) -> dict:
        params = dict(params) if params else {}
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self.config.recv_window

        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = self._sign(query_string)
        query_string = f"{query_string}&signature={signature}"

        url = f"{self.config.base_url}{path}?{query_string}"

        headers = {"X-MBX-APIKEY": self.config.api_key}

        resp = requests.request(method, url, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise BinanceMarginRequestError(
                f"HTTP {resp.status_code} - {resp.text}"
            )
        data = resp.json()
        if isinstance(data, dict) and data.get("code") not in (None, 0):
            raise BinanceMarginRequestError(str(data))
        return data

    # ---------- Trades Margin ----------

    def get_margin_trades(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        is_isolated: bool = False,
        limit: int = 1000,
    ) -> List[dict]:
        """
        Récupère les trades Margin pour un symbole.
        GET /sapi/v1/margin/myTrades

        Remarque : on pagine simplement via fromId. Pour un historique
        très long, il peut être nécessaire de restreindre startTime/endTime.
        """
        path = "/sapi/v1/margin/myTrades"
        all_trades = []
        from_id = None

        while True:
            params = {
                "symbol": symbol,
                "limit": limit,
                "isIsolated": "TRUE" if is_isolated else "FALSE",
            }
            if start_time is not None:
                params["startTime"] = start_time
            if end_time is not None:
                params["endTime"] = end_time
            if from_id is not None:
                params["fromId"] = from_id

            data = self._send_signed("GET", path, params)

            if not data:
                break

            all_trades.extend(data)
            last_id = data[-1]["id"]
            from_id = last_id + 1

            if len(data) < limit:
                break

        return all_trades

    # ---------- Ordres Margin (incl. LIMIT / MARKET / OCO) ----------

    def get_margin_orders(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        is_isolated: bool = False,
        limit: int = 1000,
    ) -> List[dict]:
        """
        Récupère les ordres Margin pour un symbole.
        GET /sapi/v1/margin/allOrders

        Ces ordres incluent :
        - LIMIT, MARKET, STOP_LOSS_LIMIT, TAKE_PROFIT_LIMIT, etc.
        - les ordres OCO via orderListId
        """
        path = "/sapi/v1/margin/allOrders"
        all_orders = []
        order_id = None

        while True:
            params = {
                "symbol": symbol,
                "limit": limit,
                "isIsolated": "TRUE" if is_isolated else "FALSE",
            }
            if start_time is not None:
                params["startTime"] = start_time
            if end_time is not None:
                params["endTime"] = end_time
            if order_id is not None:
                params["orderId"] = order_id

            data = self._send_signed("GET", path, params)

            if not data:
                break

            all_orders.extend(data)
            last_oid = data[-1]["orderId"]
            order_id = last_oid + 1

            if len(data) < limit:
                break

        return all_orders


# ==========================
# 2. Modèles métier : Trade, Order, Lot
# ==========================

@dataclass
class MarginTrade:
    symbol: str
    id: int
    order_id: int
    price: Decimal
    qty: Decimal
    quote_qty: Decimal
    commission: Decimal
    commission_asset: str
    is_buyer: bool
    time: int

    # Champs calculés ensuite
    realized_pnl: Decimal = Decimal("0")
    order_type: str = "UNKNOWN"   # LIMIT / MARKET / STOP_LOSS_LIMIT / ...
    order_group: str = "SIMPLE"   # SIMPLE / OCO

    @classmethod
    def from_api_dict(cls, data: dict) -> "MarginTrade":
        return cls(
            symbol=data["symbol"],
            id=int(data["id"]),
            order_id=int(data["orderId"]),
            price=Decimal(data["price"]),
            qty=Decimal(data["qty"]),
            quote_qty=Decimal(data.get("quoteQty", "0")),
            commission=Decimal(data.get("commission", "0")),
            commission_asset=data.get("commissionAsset", ""),
            is_buyer=bool(data["isBuyer"]),
            time=int(data["time"]),
        )

    @property
    def side_str(self) -> str:
        return "BUY" if self.is_buyer else "SELL"

    @property
    def datetime(self) -> datetime:
        return datetime.utcfromtimestamp(self.time / 1000)


@dataclass
class MarginOrder:
    symbol: str
    order_id: int
    client_order_id: str
    side: str
    type: str
    status: str
    time_in_force: str
    orig_qty: Decimal
    executed_qty: Decimal
    price: Decimal
    cummulative_quote_qty: Decimal
    update_time: int
    order_list_id: int  # -1 si non OCO

    @classmethod
    def from_api_dict(cls, data: dict) -> "MarginOrder":
        return cls(
            symbol=data["symbol"],
            order_id=int(data["orderId"]),
            client_order_id=data.get("clientOrderId", ""),
            side=data.get("side", ""),
            type=data.get("type", ""),
            status=data.get("status", ""),
            time_in_force=data.get("timeInForce", ""),
            orig_qty=Decimal(data.get("origQty", "0")),
            executed_qty=Decimal(data.get("executedQty", "0")),
            price=Decimal(data.get("price", "0")),
            cummulative_quote_qty=Decimal(data.get("cummulativeQuoteQty", "0")),
            update_time=int(data.get("updateTime", data.get("time", 0))),
            order_list_id=int(data.get("orderListId", -1)),
        )

    @property
    def is_oco(self) -> bool:
        return self.order_list_id not in (None, -1)


@dataclass
class PositionLot:
    """
    Lot ouvert en base sur un symbole.
    qty > 0 => position long, qty < 0 => position short.
    """
    qty: Decimal
    price: Decimal


# ==========================
# 3. Analyse PnL (avec corrélation trades / ordres)
# ==========================

class MarginPnLAnalyzer:
    """
    Analyse du PnL réalisé sur un compte Margin :
    - Reconstitution FIFO (multi-symboles, long & short)
    - Agrégation par symbole
    - Agrégation par type d’ordre (LIMIT / MARKET / OCO, etc.)
    - Statistiques globales (PnL total, win rate, max drawdown, Sharpe approx.)
    """

    def __init__(
        self,
        trades: List[MarginTrade],
        orders_by_key: Dict[Tuple[str, int], MarginOrder],
        quote_asset_by_symbol: Dict[str, str],
    ):
        self.trades = sorted(trades, key=lambda t: t.time)
        self.orders_by_key = orders_by_key
        self.quote_asset_by_symbol = quote_asset_by_symbol

        self.symbol_pnl: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        self.trade_pnl: List[Tuple[MarginTrade, Decimal]] = []
        self.equity_curve: List[Tuple[datetime, Decimal]] = []

    # ---------- Calcul PnL FIFO ----------

    def _apply_fifo_for_symbol(self, symbol: str, symbol_trades: List[MarginTrade]) -> None:
        lots: List[PositionLot] = []
        total_pnl = Decimal("0")
        quote_asset = self.quote_asset_by_symbol.get(symbol)

        for trade in symbol_trades:
            # BUY => qty positive, SELL => qty négative
            signed_qty = trade.qty if trade.is_buyer else -trade.qty
            remaining = signed_qty
            trade_realized_pnl = Decimal("0")

            # On ferme d'abord les positions existantes si elles sont de sens opposé
            while (
                lots
                and remaining != 0
                and (
                    (lots[0].qty > 0 and remaining < 0) or
                    (lots[0].qty < 0 and remaining > 0)
                )
            ):
                lot = lots[0]
                lot_sign = 1 if lot.qty > 0 else -1
                rem_sign = 1 if remaining > 0 else -1

                # quantité qui va être matchée (en absolu)
                match_qty = min(abs(lot.qty), abs(remaining))
                match_qty_signed_lot = Decimal(match_qty) * lot_sign
                match_qty_signed_rem = Decimal(match_qty) * rem_sign

                # PnL sur cette portion
                if lot.qty > 0 and remaining < 0:
                    # fermeture d'un lot long (on vend)
                    pnl_piece = (trade.price - lot.price) * Decimal(match_qty)
                elif lot.qty < 0 and remaining > 0:
                    # fermeture d'un lot short (on rachète)
                    pnl_piece = (lot.price - trade.price) * Decimal(match_qty)
                else:
                    pnl_piece = Decimal("0")

                trade_realized_pnl += pnl_piece

                # ✅ Mise à jour CORRECTE des quantités
                lot.qty = lot.qty - match_qty_signed_lot      # on diminue le lot
                remaining = remaining - match_qty_signed_rem  # on diminue la quantité restante

                # si le lot est totalement clos, on le retire
                if lot.qty == 0:
                    lots.pop(0)

            # Toute quantité restante ouvre un nouveau lot (long ou short)
            if remaining != 0:
                lots.append(PositionLot(qty=remaining, price=trade.price))

            # Frais (si commission dans l’asset de cotation)
            fee = Decimal("0")
            if quote_asset is not None and trade.commission_asset == quote_asset:
                fee = trade.commission

            trade_realized_pnl -= fee

            trade.realized_pnl = trade_realized_pnl
            total_pnl += trade_realized_pnl
            self.trade_pnl.append((trade, trade_realized_pnl))

        self.symbol_pnl[symbol] = total_pnl

    def compute_realized_pnl(self) -> None:
        # Groupement par symbole
        trades_by_symbol: Dict[str, List[MarginTrade]] = defaultdict(list)
        for t in self.trades:
            trades_by_symbol[t.symbol].append(t)

        # FIFO par symbole
        for symbol, symbol_trades in trades_by_symbol.items():
            self._apply_fifo_for_symbol(symbol, symbol_trades)

        # Construction de la courbe d’equity
        cumulative = Decimal("0")
        for trade, pnl in sorted(self.trade_pnl, key=lambda x: x[0].time):
            cumulative += pnl
            self.equity_curve.append((trade.datetime, cumulative))

        # Après calcul de PnL, on lie les infos d'ordre (type, OCO, etc.)
        self._attach_order_metadata()

    # ---------- Métadonnées d’ordres ----------

    def _attach_order_metadata(self) -> None:
        for trade, _ in self.trade_pnl:
            key = (trade.symbol, trade.order_id)
            order = self.orders_by_key.get(key)
            if order is None:
                continue
            trade.order_type = order.type or "UNKNOWN"
            trade.order_group = "OCO" if order.is_oco else "SIMPLE"

    # ---------- Statistiques globales ----------

    @property
    def total_pnl(self) -> Decimal:
        return sum(self.symbol_pnl.values(), Decimal("0"))

    def trade_pnl_values(self) -> List[Decimal]:
        return [p for _, p in self.trade_pnl]

    def win_loss_stats(self) -> Tuple[int, int, Decimal]:
        wins = [p for p in self.trade_pnl_values() if p > 0]
        losses = [p for p in self.trade_pnl_values() if p < 0]
        n_win = len(wins)
        n_loss = len(losses)
        n_trades = len(self.trade_pnl)
        win_rate = (
            Decimal(n_win) / Decimal(n_trades) * Decimal("100")
            if n_trades > 0 else Decimal("0")
        )
        return n_win, n_loss, win_rate

    def payoff_ratio(self) -> Optional[Decimal]:
        wins = [p for p in self.trade_pnl_values() if p > 0]
        losses = [p for p in self.trade_pnl_values() if p < 0]
        if not wins or not losses:
            return None
        avg_gain = mean(wins)
        avg_loss = mean(losses)
        if avg_loss == 0:
            return None
        return Decimal(avg_gain) / abs(Decimal(avg_loss))

    def max_drawdown(self) -> Decimal:
        if not self.equity_curve:
            return Decimal("0")
        peak = self.equity_curve[0][1]
        max_dd = Decimal("0")
        for _, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = equity - peak
            if dd < max_dd:
                max_dd = dd
        return max_dd

    def daily_stats(self) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        if not self.trade_pnl:
            return None, None, None

        pnl_by_day: Dict[datetime, Decimal] = defaultdict(lambda: Decimal("0"))
        for trade, pnl in self.trade_pnl:
            day = trade.datetime.date()
            pnl_by_day[day] += pnl

        daily_values = list(pnl_by_day.values())
        if len(daily_values) == 0:
            return None, None, None
        if len(daily_values) == 1:
            return daily_values[0], None, None

        daily_floats = [float(v) for v in daily_values]
        mu = mean(daily_floats)
        sigma = pstdev(daily_floats)
        sharpe = None
        if sigma > 0:
            sharpe = mu / sigma * math.sqrt(365)

        return (
            Decimal(str(mu)),
            Decimal(str(sigma)),
            Decimal(str(sharpe)) if sharpe is not None else None,
        )

    def order_type_pnl_stats(self) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
        """
        Retourne :
        - PnL par type d’ordre (LIMIT, MARKET, STOP_LOSS_LIMIT, etc.)
        - PnL par groupe (SIMPLE vs OCO)
        """
        pnl_by_type: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        pnl_by_group: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        for trade, pnl in self.trade_pnl:
            t_type = trade.order_type or "UNKNOWN"
            t_group = trade.order_group or "SIMPLE"
            pnl_by_type[t_type] += pnl
            pnl_by_group[t_group] += pnl

        return pnl_by_type, pnl_by_group

    # ---------- Synthèse texte ----------

    def summary_text(self) -> str:
        n_trades = len(self.trade_pnl)
        pnl_values = self.trade_pnl_values()

        total_pnl = self.total_pnl
        pnl_avg = Decimal("0")
        pnl_med = Decimal("0")

        if pnl_values:
            pnl_avg = Decimal(str(mean([float(p) for p in pnl_values])))
            pnl_med = median(pnl_values)

        n_win, n_loss, win_rate = self.win_loss_stats()
        payoff = self.payoff_ratio()
        max_dd = self.max_drawdown()
        mean_daily, vol_daily, sharpe = self.daily_stats()
        pnl_by_type, pnl_by_group = self.order_type_pnl_stats()

        lines = []
        lines.append("=== Synthèse PnL (Compte Margin, avec levier) ===")
        lines.append(f"Nombre total de trades analysés : {n_trades}")
        lines.append("")
        lines.append("Performance globale :")
        lines.append(f"  - PnL total réalisé              : {total_pnl:.8f}")
        lines.append(f"  - PnL moyen par trade            : {pnl_avg:.8f}")
        lines.append(f"  - PnL médian par trade           : {pnl_med:.8f}")
        lines.append("")
        lines.append("Statistiques de win rate :")
        lines.append(f"  - Trades gagnants                : {n_win}")
        lines.append(f"  - Trades perdants                : {n_loss}")
        lines.append(f"  - Taux de réussite               : {win_rate:.2f} %")
        if payoff is not None:
            lines.append(f"  - Payoff ratio gain/perte moyenne: {payoff:.3f}")
        else:
            lines.append("  - Payoff ratio                   : non défini (pas assez de données)")

        lines.append("")
        lines.append("Risque :")
        lines.append(f"  - Drawdown maximal (equity)      : {max_dd:.8f}")
        if mean_daily is not None:
            lines.append(f"  - PnL moyen quotidien            : {mean_daily:.8f}")
        if vol_daily is not None:
            lines.append(f"  - Volatilité quotidienne (PnL)   : {vol_daily:.8f}")
        if sharpe is not None:
            lines.append(f"  - Ratio de Sharpe (approx.)      : {sharpe:.3f}")
        else:
            lines.append("  - Ratio de Sharpe                : non calculable")

        lines.append("")
        lines.append("PnL par symbole :")
        for symbol, pnl in sorted(self.symbol_pnl.items()):
            lines.append(f"  - {symbol} : {pnl:.8f}")

        lines.append("")
        lines.append("PnL par type d’ordre :")
        for t_type, pnl in sorted(pnl_by_type.items()):
            lines.append(f"  - {t_type:18s} : {pnl:.8f}")

        lines.append("")
        lines.append("PnL par groupe d’ordres (OCO vs simples) :")
        for grp, pnl in sorted(pnl_by_group.items()):
            lines.append(f"  - {grp:18s} : {pnl:.8f}")

        return "\n".join(lines)


# ==========================
# 4. Exemple d’utilisation pour INJUSDC
# ==========================

if __name__ == "__main__":
    # Récupération des clés depuis les variables d’environnement
    api_key = (
        os.getenv("binance_api")
        or os.getenv("BINANCE_API")
    )
    api_secret = (
        os.getenv("binance_secret")
        or os.getenv("BINANCE_SECRET")
    )

    if not api_key or not api_secret:
        raise RuntimeError(
            "Clés API non trouvées. "
            "Définir les variables d’environnement binance_api / binance_secret."
        )

    cfg = BinanceMarginConfig(api_key=api_key, api_secret=api_secret)
    client = BinanceMarginClient(cfg)

    # Tu peux adapter cette liste si tu trades d’autres paires
    symbols = ["INJUSDC"]

    # Mapping symbole -> asset de cotation (pour les frais)
    quote_asset_by_symbol = {
        "INJUSDC": "USDC",
    }

    # Période d’analyse : ici complète (start_time/end_time = None).
    # Tu peux mettre des timestamps en ms si besoin de restreindre.
    start_time = None
    end_time = None
    is_isolated = False  # mettre True si tu trades sur compte Margin isolé

    all_trades: List[MarginTrade] = []
    all_orders: List[MarginOrder] = []

    for sym in symbols:
        print(f"Récupération des trades Margin pour {sym}...")
        raw_trades = client.get_margin_trades(
            symbol=sym,
            start_time=start_time,
            end_time=end_time,
            is_isolated=is_isolated,
        )
        trades = [MarginTrade.from_api_dict(t) for t in raw_trades]
        all_trades.extend(trades)

        print(f"Récupération des ordres Margin pour {sym}...")
        raw_orders = client.get_margin_orders(
            symbol=sym,
            start_time=start_time,
            end_time=end_time,
            is_isolated=is_isolated,
        )
        orders = [MarginOrder.from_api_dict(o) for o in raw_orders]
        all_orders.extend(orders)

    # Indexation des ordres par (symbol, order_id) pour corrélation avec les trades
    orders_by_key: Dict[Tuple[str, int], MarginOrder] = {
        (o.symbol, o.order_id): o for o in all_orders
    }

    analyzer = MarginPnLAnalyzer(
        trades=all_trades,
        orders_by_key=orders_by_key,
        quote_asset_by_symbol=quote_asset_by_symbol,
    )
    analyzer.compute_realized_pnl()
    report = analyzer.summary_text()

    print()
    print(report)
