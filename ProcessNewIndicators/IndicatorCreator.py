import csv
import os
from datetime import datetime, timezone
import time
import threading



class TimeCounter:
	_depth = 0  # class variable to track nesting depth

	def __init__(self, message):
		self.message = message
		self.depth = TimeCounter._depth
		self.start_time = None
		self.last_display_time = 0
		self.lock = threading.Lock()

	def __enter__(self):
		TimeCounter._depth += 1
		self.start_time = time.time()
		indent = '\t' * self.depth
		print(f"{indent}{self.message}")
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		elapsed = time.time() - self.start_time
		indent_log = '\t' * (self.depth + 1)
		h, rem = divmod(elapsed, 3600)
		m, s = divmod(rem, 60)
		print(f"{indent_log}Done in {int(h)}:{int(m):02}:{int(s):02}")
		TimeCounter._depth -= 1

	def displayProgress(self, i, nMax, intervalMinBeforeNextDisplayInSecs=1):
		if intervalMinBeforeNextDisplayInSecs < 1:
			return  # do not display if interval less than 1 sec

		with self.lock:
			now = time.time()
			if now - self.last_display_time < intervalMinBeforeNextDisplayInSecs:
				return  # skip if called too soon

			self.last_display_time = now

			percentProgress = (i / nMax) * 100 if nMax > 0 else 0

			elapsed = now - self.start_time
			if i == 0:
				# avoid division by zero for estimate, display 0 remaining time
				remaining = 0
			else:
				remaining = elapsed * (nMax - i) / i

			# compute elapsed time components
			hourElapsed = int(elapsed // 3600)
			minuteElapsed = int((elapsed % 3600) // 60)
			secondElapsed = int(elapsed % 60)

			# compute remaining time components
			hourLeft = int(remaining // 3600)
			minutesLeft = int((remaining % 3600) // 60)
			secondLeft = int(remaining % 60)

			indent_msg = '\t' * self.depth
			indent_log = '\t' * (self.depth + 1)

			# The initial message is also indented
			print(f"{indent_msg}{self.message}")

			# Log display with one level deeper indentation
			print(f"{indent_log}{i} / {nMax} {percentProgress:.2f}% time {hourElapsed}:{minuteElapsed:02}:{secondElapsed:02} "
				  f"remainingTime {hourLeft}:{minutesLeft:02}:{secondLeft:02}")

class Kline:
	def __init__(self, timestamp, open_price, high_price, low_price, close_price, volume):
		self.timestamp = timestamp
		self.open = float(open_price)
		self.high = float(high_price)
		self.low = float(low_price)
		self.close = float(close_price)
		self.volume = float(volume)
		self.indicators = {}

	def add_indicator(self, name, params_and_values):
		self.indicators[name] = params_and_values

	def __repr__(self):
		return f"Kline({self.timestamp}, C:{self.close}, I:{self.indicators})"

class KlineManager:
	def __init__(self):
		self.klines = {}

	def read_klines(self, filepath):
		with open(filepath, 'r', newline='', encoding='utf-8') as f:
			reader = csv.DictReader(f)
			for row in reader:
				# Convert open_time from milliseconds to seconds for datetime
				ts = datetime.fromtimestamp(int(row['open_time']) / 1000, tz=timezone.utc)
				self.klines[ts] = Kline(
					timestamp=ts,
					open_price=row['open'],
					high_price=row['high'],
					low_price=row['low'],
					close_price=row['close'],
					volume=row['volume']
				)

	def read_indicator(self, indicator_file):
		indicator_name = os.path.splitext(os.path.basename(indicator_file))[0]
		with open(indicator_file, 'r', newline='', encoding='utf-8') as f:
			reader = csv.DictReader(f)
			for row in reader:
				ts = datetime.fromtimestamp(float(row['timestamp']), tz=timezone.utc)
				if ts in self.klines:
					values = {k: float(v) for k, v in row.items() if k != 'timestamp'}
					self.klines[ts].add_indicator(indicator_name, values)

	def read_indicators(self, indicator_files):
		for f in indicator_files:
			self.read_indicator(f)

	def add_indicator(self, indicator):
		timestamps = sorted(self.klines.keys())
		values_by_kline = indicator.calculate([self.klines[ts].close for ts in timestamps])
		for i, ts in enumerate(timestamps):
			self.klines[ts].add_indicator(indicator.name, values_by_kline[i])

	def save_indicator(self, indicator_name, out_csv):
		timestamps = sorted(self.klines.keys())
		columns = ['timestamp'] + list(next(iter(self.klines.values())).indicators[indicator_name].keys())
		with open(out_csv, 'w', newline='', encoding='utf-8') as f:
			writer = csv.DictWriter(f, fieldnames=columns)
			writer.writeheader()
			for ts in timestamps:
				row = {'timestamp': ts.timestamp()}
				row.update(self.klines[ts].indicators[indicator_name])
				writer.writerow(row)

	def preview(self, n=3):
		for k in list(self.klines.values())[-n:]:
			print(k)

class Indicator:
	def __init__(self, name, subparams):
		self.name = name
		self.subparams = subparams

	def calculate(self, close_list):
		raise NotImplementedError

class EMAIndicator(Indicator):
	def __init__(self, periods):
		super().__init__(name=f"ema{'_'.join(map(str, periods))}", subparams=[f"ema{p}" for p in periods])
		self.periods = periods

	def calculate(self, close_list):
		result = []
		emas = {p: self._compute_ema(close_list, p) for p in self.periods}
		for i in range(len(close_list)):
			result.append({f"ema{p}": emas[p][i] for p in self.periods})
		return result

	@staticmethod
	def _compute_ema(values, period):
		ema = []
		k = 2 / (period + 1)
		for i, price in enumerate(values):
			if i == 0:
				ema.append(price)
			else:
				ema.append(price * k + ema[-1] * (1 - k))
		return ema

class DiffIndicator(Indicator):
	"""
	Indicator that computes the difference between two existing indicator values on klines.
	Usage: DiffIndicator("ema", "ema6", "ema", "ema24")
	"""

	def __init__(self, ind1_name, ind1_param, ind2_name, ind2_param, name_param=None):
		if name_param is None:
			name_param = f"diff_{ind1_name}_{ind1_param}_vs_{ind2_name}_{ind2_param}"
		super().__init__(name=name_param, subparams=["diff"])
		self.ind1_name = ind1_name
		self.ind1_param = ind1_param
		self.ind2_name = ind2_name
		self.ind2_param = ind2_param
		self.klines = None  # to be set externally

	def set_klines(self, klines):
		"""Set the klines dict before calling calculate, so indicator values are accessible."""
		self.klines = klines

	def calculate(self, klines_close_values):
		if self.klines is None:
			raise ValueError("DiffIndicator requires klines to be set via set_klines() before calculate()")

		result = []
		timestamps = sorted(self.klines.keys())
		for ts in timestamps:
			kline = self.klines[ts]
			val1 = kline.indicators.get(self.ind1_name, {}).get(self.ind1_param)
			val2 = kline.indicators.get(self.ind2_name, {}).get(self.ind2_param)
			diff = None
			if val1 is not None and val2 is not None:
				diff = val1 - val2
			result.append({"diff": diff})
		return result


if __name__ == "__main__":
	with TimeCounter("Indicators..."):
		manager = KlineManager()
		
		# Use your specific file path for klines here
		with TimeCounter("Read klines..."):
			manager.read_klines("../Data/klines_INJUSDC_1m_from_beginning_to_now.csv")

		# Uncomment and list actual RSI and MACD indicator files when available
		with TimeCounter("Read indicators..."):
			manager.read_indicators(["ema6_24.csv", "diff_ema6_24.csv"])

		# Add and calculate EMA indicator with multiple periods
		if False:
			with TimeCounter("Add ema..."):
				ema_indicator = EMAIndicator([6, 24])
				manager.add_indicator(ema_indicator)

			with TimeCounter("Add ema_diff..."):
				ema_diff = DiffIndicator("ema6_24", "ema24", "ema6_24", "ema6", name_param="diff_ema6_24")
				ema_diff.set_klines(manager.klines)
				manager.add_indicator(ema_diff)

		# Save the calculated EMA indicator to CSV
		if False:
			with TimeCounter("Save ema..."):
				manager.save_indicator(ema_indicator.name, "ema6_24.csv")
			with TimeCounter("Save ema_diff..."):
				manager.save_indicator(ema_indicator.name, "diff_ema6_24.csv")

		# Preview some klines with indicators
		manager.preview()
