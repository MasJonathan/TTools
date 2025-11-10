import os
import csv
from datetime import datetime
from dateutil import parser  # nécessite: pip install python-dateutil


class Kline:
    def __init__(self, open_time, open_price, high_price, low_price, close_price, volume):
        self.open_time = self._parse_time(open_time)
        self.open_price = float(open_price)
        self.high_price = float(high_price)
        self.low_price = float(low_price)
        self.close_price = float(close_price)
        self.volume = float(volume)

    def _parse_time(self, time_value):
        """Conversion robuste inspirée de pandas.to_datetime"""
        s = str(time_value).strip().rstrip("eE")

        # Étape 1 : essai direct comme timestamp Unix
        try:
            num = float(s)
            # Si timestamp trop grand, on suppose des millisecondes
            if num > 1e12:
                num /= 1000
            return datetime.utcfromtimestamp(num)
        except (ValueError, TypeError):
            pass

        # Étape 2 : essai avec plusieurs formats standards
        known_formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%d-%m-%Y %H:%M:%S"
        ]
        for fmt in known_formats:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue

        # Étape 3 : fallback avec dateutil (gère les cas complexes)
        try:
            parsed = parser.parse(s, fuzzy=True)
            return parsed
        except Exception:
            raise ValueError(f"Impossible d’interpréter la date : {time_value}")

    def __repr__(self):
        return f"Kline({self.open_time}, O:{self.open_price}, H:{self.high_price}, L:{self.low_price}, C:{self.close_price}, V:{self.volume})"


class KlineReader:
    def __init__(self, filepath):
        self.filepath = filepath

    def read_klines(self):
        klines = []
        with open(self.filepath, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            # Lis la première ligne pour détecter un header (par exemple présence de textes non numériques)
            first_line = next(reader, None)
            if first_line and any(not cell.replace('.', '', 1).isdigit() for cell in first_line[:6]):
                # C’est probablement un header, on l’ignore et continue la lecture normale
                pass
            else:
                # Ce n’est pas un header, on traite cette ligne comme une donnée
                if first_line and len(first_line) >= 6:
                    klines.append(Kline(*first_line[:6]))

            for row in reader:
                if not row or len(row) < 6:
                    continue
                klines.append(Kline(*row[:6]))
        return klines



def avg(klines, i, nLookBack):
	iStart = i - nLookBack
	if iStart < 0:
		iStart = 0

	p = [klines[j].close_price for j in range(iStart, i)]
	return sum(p) / len(p)
		

klines = KlineReader("../Data/klines_INJUSDC_1m_from_2025_06_01.csv").read_klines()
# print(klines[-5:])

for kline in klines:
	# detecter si c'est un bon moment pour entrer en position
	# si la tendance est haussière à plusieurs échelles de temps parier à la hausse
