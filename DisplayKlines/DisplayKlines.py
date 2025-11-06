import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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


def detect_timeframe(df: pd.DataFrame) -> str | None:
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


# --- UI Streamlit ---

st.set_page_config(
    page_title="Kline Viewer Binance",
    layout="wide",
)

st.title("📈 Kline Viewer - Binance CSV")

st.sidebar.header("⚙️ Paramètres")

uploaded_file = st.sidebar.file_uploader(
    "Choisis un fichier CSV de klines",
    type=["csv"],
)

page_size = st.sidebar.number_input(
    "Bougies par page",
    min_value=50,
    max_value=5000,
    value=500,
    step=50,
)

show_table = st.sidebar.checkbox("Afficher le tableau sous le graphique", value=True)

if uploaded_file is None:
    st.info("Charge un fichier CSV de klines (export Binance ou équivalent).")
    st.stop()

with st.spinner("Chargement du fichier..."):
    df_raw = pd.read_csv(uploaded_file)

df_raw = normalize_columns(df_raw)
time_col = find_time_column(df_raw)
df = to_datetime_index(df_raw, time_col)

if df.empty:
    st.error("Impossible de parser les dates. Vérifie le format de ton CSV.")
    st.stop()

detected_tf = detect_timeframe(df)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Nombre de bougies", len(df))
with col2:
    if detected_tf is not None:
        st.metric("Timeframe détecté", detected_tf)
    else:
        st.metric("Timeframe détecté", "Inconnu")
with col3:
    st.metric(
        "Période couverte",
        f"{df.index[0].strftime('%Y-%m-%d %H:%M:%S')} → {df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}",
    )

if detected_tf in TIMEFRAME_ORDER:
    base_idx = TIMEFRAME_ORDER.index(detected_tf)
    available_tfs = TIMEFRAME_ORDER[base_idx:]
else:
    available_tfs = TIMEFRAME_ORDER

selected_tf = st.sidebar.selectbox(
    "Timeframe d'affichage",
    options=available_tfs,
    index=0,
)

if detected_tf is not None and selected_tf == detected_tf:
    df_tf = df.copy()
else:
    with st.spinner(f"Rééchantillonnage en {selected_tf}..."):
        df_tf = resample_klines(df, selected_tf)

total_candles = len(df_tf)
num_pages = max(1, math.ceil(total_candles / page_size))

page = st.sidebar.slider(
    "Page",
    min_value=1,
    max_value=num_pages,
    value=num_pages,
)

start_idx = (page - 1) * page_size
end_idx = start_idx + page_size
page_df = df_tf.iloc[start_idx:end_idx]

st.caption(
    f"Affichage {start_idx + 1}–{min(end_idx, total_candles)} / {total_candles} bougies "
    f"({selected_tf}), page {page}/{num_pages}"
)

fig = go.Figure(
    data=[
        go.Candlestick(
            x=page_df.index,
            open=page_df["open"],
            high=page_df["high"],
            low=page_df["low"],
            close=page_df["close"],
            name="Prix",
        )
    ]
)

fig.update_layout(
    xaxis_title="Date",
    yaxis_title="Prix",
    xaxis_rangeslider_visible=False,
    margin=dict(l=10, r=10, t=30, b=30),
)

st.plotly_chart(fig, use_container_width=True)

if show_table:
    st.subheader("Données (page courante)")
    st.dataframe(page_df)

# --- Hook pour futurs indicateurs techniques ---
# Tu pourras ici ajouter facilement des indicateurs (EMA, RSI, etc.)
# en les calculant sur df_tf ou page_df puis :
#  - soit les afficher dans le chart (courbes supplémentaires),
#  - soit les ajouter comme colonnes à page_df pour inspection dans le tableau.
