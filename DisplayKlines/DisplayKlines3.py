import math
import base64
import io

import pandas as pd
import plotly.graph_objs as go
import dash
from dash import html, dcc, Input, Output, State

# =========================
#  Config timeframes
# =========================

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

# =========================
#  Normalisation colonnes
# =========================

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


# =========================
#  Moteur d'indicateurs
# =========================

INDICATORS_REGISTRY = {}


def register_indicator(name):
    def decorator(func):
        INDICATORS_REGISTRY[name] = func
        return func
    return decorator


@register_indicator("ema")
def indicator_ema(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    period = params.get("period", 50)
    col_out = params.get("col_out", f"ema_{period}")
    df[col_out] = df["close"].ewm(span=period, adjust=False).mean()
    return df


@register_indicator("rsi")
def indicator_rsi(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    period = params.get("period", 14)
    col_out = params.get("col_out", f"rsi_{period}")

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    df[col_out] = 100 - (100 / (1 + rs))
    return df


def apply_indicators(df: pd.DataFrame, config: list[dict]) -> pd.DataFrame:
    df = df.copy()
    for item in config:
        name = item["name"]
        params = item.get("params", {})
        func = INDICATORS_REGISTRY.get(name)
        if func is None:
            continue
        df = func(df, params)
    return df


# Exemple de config d'indicateurs (à terme: piloté par l'UI)
DEFAULT_INDICATORS_CONFIG = [
    {"name": "ema", "params": {"period": 5, "col_out": "ema_5"}},
    {"name": "ema", "params": {"period": 50, "col_out": "ema_50"}},
    {"name": "ema", "params": {"period": 200, "col_out": "ema_200"}},
    # {"name": "rsi", "params": {"period": 14, "col_out": "rsi_14"}},  # ex: à afficher dans un subplot plus tard
]

# =========================
#  Stockage global (côté serveur)
# =========================

df_global = None              # klines brutes (index = datetime)
detected_tf_global = None     # timeframe détectée
resample_cache = {}           # cache { timeframe: df_resampled }


def reset_global():
    global df_global, detected_tf_global, resample_cache
    df_global = None
    detected_tf_global = None
    resample_cache = {}


def get_resampled_df(target_tf: str) -> pd.DataFrame:
    """Renvoie le dataframe resamplé, en utilisant un cache côté serveur."""
    global df_global, resample_cache
    if df_global is None:
        return None
    if target_tf in resample_cache:
        return resample_cache[target_tf]
    df_tf = resample_klines(df_global, target_tf)
    resample_cache[target_tf] = df_tf
    return df_tf


# =========================
#  App Dash
# =========================

app = dash.Dash(__name__)

app.layout = html.Div(
    style={"fontFamily": "Arial", "padding": "10px"},
    children=[
        html.H2("📈 Kline Viewer Binance - Plotly / Dash"),

        dcc.Upload(
            id="upload-data",
            children=html.Div([
                "Glisse-dépose un fichier ou ",
                html.A("clique pour sélectionner un CSV")
            ]),
            style={
                "width": "100%",
                "height": "60px",
                "lineHeight": "60px",
                "borderWidth": "1px",
                "borderStyle": "dashed",
                "borderRadius": "5px",
                "textAlign": "center",
                "marginBottom": "10px",
            },
            multiple=False,
        ),

        html.Div(id="file-info", style={"marginBottom": "10px"}),

        html.Div(
            style={"display": "flex", "gap": "20px", "marginBottom": "10px"},
            children=[
                html.Div(
                    style={"minWidth": "200px"},
                    children=[
                        html.Label("Timeframe d'affichage"),
                        dcc.Dropdown(
                            id="tf-dropdown",
                            options=[{"label": tf, "value": tf} for tf in TIMEFRAME_ORDER],
                            value="1h",
                            clearable=False,
                        ),
                    ],
                ),
                html.Div(
                    style={"minWidth": "200px"},
                    children=[
                        html.Label("Bougies par page"),
                        dcc.Input(
                            id="page-size",
                            type="number",
                            min=50,
                            step=50,
                            value=500,
                            style={"width": "100%"},
                        ),
                    ],
                ),
                html.Div(
                    style={"flex": 1},
                    children=[
                        html.Label("Page"),
                        dcc.Slider(
                            id="page-slider",
                            min=1,
                            max=1,
                            step=1,
                            value=1,
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                    ],
                ),
            ],
        ),

        html.Div(id="pagination-info", style={"marginBottom": "10px"}),

        dcc.Graph(
            id="kline-graph",
            style={"height": "70vh"},
            figure=go.Figure(),
        ),

        dcc.Store(id="meta-store"),
    ],
)

# =========================
#  Callbacks
# =========================


@app.callback(
    Output("file-info", "children"),
    Output("meta-store", "data"),
    Input("upload-data", "contents"),
    State("upload-data", "filename"),
)
def load_file(contents, filename):
    reset_global()

    if contents is None:
        return "Aucun fichier chargé.", {}

    content_type, content_string = contents.split(",")

    try:
        decoded = base64.b64decode(content_string)
        df_raw = pd.read_csv(io.StringIO(decoded.decode("utf-8")))

        df_norm = normalize_columns(df_raw)
        time_col = find_time_column(df_norm)
        df = to_datetime_index(df_norm, time_col)

        if df.empty:
            return "Erreur: impossible de parser les dates (DataFrame vide).", {}

        global df_global, detected_tf_global
        df_global = df
        detected_tf_global = detect_timeframe(df)

        start = df.index[0]
        end = df.index[-1]
        n = len(df)

        tf_text = detected_tf_global if detected_tf_global is not None else "Inconnue"

        info = html.Div([
            html.Div(f"Fichier: {filename}"),
            html.Div(f"Bougies: {n}"),
            html.Div(f"Timeframe détectée: {tf_text}"),
            html.Div(f"Période: {start} → {end}"),
        ])

        meta = {
            "n_candles": int(n),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "detected_tf": detected_tf_global,
        }

        return info, meta

    except Exception as e:
        return f"Erreur lors du chargement: {e}", {}


@app.callback(
    Output("page-slider", "max"),
    Output("page-slider", "value"),
    Output("pagination-info", "children"),
    Input("meta-store", "data"),
    Input("page-size", "value"),
    Input("tf-dropdown", "value"),
)
def update_pagination(meta, page_size, tf_display):
    if not meta or df_global is None:
        return 1, 1, "Aucun fichier / aucune donnée."

    try:
        if page_size is None or page_size <= 0:
            page_size = 500

        df_tf = get_resampled_df(tf_display)
        if df_tf is None or df_tf.empty:
            return 1, 1, "Aucune donnée après resampling."

        n_candles = len(df_tf)
        num_pages = max(1, math.ceil(n_candles / page_size))

        start = df_tf.index[0].strftime("%Y-%m-%d %H:%M:%S")
        end = df_tf.index[-1].strftime("%Y-%m-%d %H:%M:%S")

        info = (
            f"Bougies (après resampling {tf_display}): {n_candles} | "
            f"Période: {start} → {end} | "
            f"Pages: {num_pages}"
        )

        return num_pages, num_pages, info

    except Exception as e:
        return 1, 1, f"Erreur pagination: {e}"


@app.callback(
    Output("kline-graph", "figure"),
    Input("meta-store", "data"),
    Input("tf-dropdown", "value"),
    Input("page-size", "value"),
    Input("page-slider", "value"),
)
def update_graph(meta, tf_display, page_size, page):
    if not meta or df_global is None:
        return go.Figure()

    try:
        if page_size is None or page_size <= 0:
            page_size = 500
        if page is None or page < 1:
            page = 1

        df_tf = get_resampled_df(tf_display)
        if df_tf is None or df_tf.empty:
            return go.Figure()

        # Application des indicateurs sur le DF resamplé
        df_tf = apply_indicators(df_tf, DEFAULT_INDICATORS_CONFIG)

        n_candles = len(df_tf)
        num_pages = max(1, math.ceil(n_candles / page_size))
        if page > num_pages:
            page = num_pages

        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, n_candles)
        page_df = df_tf.iloc[start_idx:end_idx].copy()

        for col in ["open", "high", "low", "close"]:
            page_df[col] = pd.to_numeric(page_df[col], errors="coerce")
        page_df = page_df.dropna(subset=["open", "high", "low", "close"])

        fig = go.Figure()

        fig.add_trace(
            go.Candlestick(
                x=page_df.index,
                open=page_df["open"],
                high=page_df["high"],
                low=page_df["low"],
                close=page_df["close"],
                name="Prix",
            )
        )

        # Ajout des courbes d'indicateurs de type "prix" (EMA, etc.)
        indicator_cols = [cfg["params"].get("col_out", f"{cfg['name']}_{cfg['params'].get('period', '')}")
                          for cfg in DEFAULT_INDICATORS_CONFIG]

        for col in indicator_cols:
            if col in page_df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=page_df.index,
                        y=page_df[col],
                        name=col,
                        mode="lines",
                    )
                )

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Prix",
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=30, b=30),
        )

        return fig

    except Exception as e:
        fig = go.Figure()
        fig.update_layout(title=f"Erreur lors de l'affichage: {e}")
        return fig


if __name__ == "__main__":
    app.run(debug=True)
