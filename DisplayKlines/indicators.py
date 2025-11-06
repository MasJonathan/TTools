# indicators.py
import pandas as pd

# ----- REGISTRE D'INDICATEURS -----

INDICATORS_REGISTRY = {}

def register_indicator(name):
    def decorator(func):
        INDICATORS_REGISTRY[name] = func
        return func
    return decorator

# ----- EXEMPLES D'INDICATEURS -----

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

# ----- FONCTION GLOBALE -----

def apply_indicators(df: pd.DataFrame, config: list[dict]) -> pd.DataFrame:
    """
    config = [
      {"name": "ema", "params": {"period": 50, "col_out": "ema_50"}},
      {"name": "rsi", "params": {"period": 14}},
    ]
    """
    df = df.copy()
    for item in config:
        name = item["name"]
        params = item.get("params", {})
        func = INDICATORS_REGISTRY.get(name)
        if func is None:
            continue
        df = func(df, params)
    return df
