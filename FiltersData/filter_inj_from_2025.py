import pandas as pd

# Charger le fichier CSV
df = pd.read_csv("../Data/klines_INJUSDC_1m_from_beginning_to_now.csv")

# Supposons que votre colonne de date s'appelle 'open_time' ou similaire et est au format timestamp ou string
# Adapter le nom de la colonne si nécessaire
# Si la colonne est en timestamp (millisecondes), convertir en datetime
if df['open_time'].dtype in ['int64', 'float64']:
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
else:
    df['open_time'] = pd.to_datetime(df['open_time'])

# Filtrer les lignes depuis 2025
df_2025 = df[df['open_time'] >= '2025-01-01']

# Exporter le résultat
df_2025.to_csv("../Data/klines_INJUSDC_1m_from_2025.csv", index=False)
