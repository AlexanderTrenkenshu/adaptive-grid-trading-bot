# Milestones 4-6: Trading Strategy Implementation

**Phase B Duration:** 6.5 weeks (260 hours)
**Phase B Cost:** $13,000
**Objective:** Build adaptive three-system ensemble strategy with dynamic risk management

---

# Milestone 4: Strategy Engine Skeleton & 3-System Raw Scores

**Duration:** 2 weeks (80 hours)
**Cost:** $4,000
**Objective:** Implement UP/DOWN/NEUTRAL systems with initial weight calculation

---

## Week 6: Market Data Processor & UP System

### Day 26: Market Data Processor Foundation
**Hours:** 8h
**Tasks:**
- [ ] Design data aggregation pipeline
  ```python
  class MarketDataProcessor:
      def __init__(self):
          self.ohlcv_data = {}  # {symbol: {timeframe: DataFrame}}
          self.indicators = {}   # Calculated indicators

      def on_candle_update(self, symbol, timeframe, candle):
          # Update OHLCV buffer
          # Trigger indicator recalculation
          pass
  ```

- [ ] OHLCV data management
  - Rolling windows for each timeframe (1m, 15m, 1h, 1d)
  - Keep last 500 candles per timeframe
  - Update on WebSocket `@kline` events

- [ ] Data structure for multi-timeframe access
  ```python
  # Example access pattern
  data = processor.get_ohlcv("BTCUSDT", "1m", lookback=100)
  close_prices = data['close']  # Pandas Series
  ```

**Deliverables:**
- `src/market_data/data_processor.py`
- Rolling window management
- WebSocket integration

---

### Day 27: Technical Indicators Implementation
**Hours:** 8h
**Tasks:**
- [ ] Implement required indicators (Spec Section 5.1)
  - **ATR (Average True Range)**
    ```python
    def calculate_atr(high, low, close, period=14):
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    ```

  - **EMA (Exponential Moving Average)**
    ```python
    def calculate_ema(prices, period=20):
        return prices.ewm(span=period, adjust=False).mean()
    ```

  - **Bollinger Bands**
    ```python
    def calculate_bollinger_bands(prices, period=20, std_dev=2):
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower
    ```

  - **RSI (Relative Strength Index)**
    ```python
    def calculate_rsi(prices, period=14):
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    ```

  - **SMA (Simple Moving Average)**
  - **Auto-correlation** (for NEUTRAL system)

- [ ] Indicator caching strategy
- [ ] Performance optimization (vectorized operations)

**Deliverables:**
- `src/market_data/indicators.py`
- Unit tests for each indicator
- Benchmark for calculation speed

---

### Day 28: Feature Normalization & UP System Architecture
**Hours:** 8h
**Tasks:**
- [ ] Z-score normalization implementation
  ```python
  def normalize_zscore(feature_series, window=100):
      """
      Normalize feature to Z-score over rolling window.
      Spec: Section 5.1
      """
      mean = feature_series.rolling(window=window).mean()
      std = feature_series.rolling(window=window).std()
      z_score = (feature_series - mean) / std
      return z_score.fillna(0)  # Handle NaN for initial window
  ```

- [ ] UP System class structure
  ```python
  class UPSystem:
      def __init__(self, config):
          self.config = config
          self.feature_weights = None  # Will be calculated
          self.lookback_1m = config.up_system.highs_lookback_1m
          self.lookback_15m = config.up_system.highs_lookback_15m
          self.ema_period = config.up_system.ema_period

      def calculate_features(self, market_data):
          """Calculate all 6 features for UP system"""
          pass

      def calculate_raw_score(self, features):
          """Weighted sum of normalized features"""
          pass

      def calculate_bias(self, raw_score):
          """b_up = tanh(raw_score)"""
          return np.tanh(raw_score)

      def calculate_confidence(self, raw_score):
          """Phase 1: Heuristic c_up = |raw_score| / (|raw_score| + 1)"""
          return abs(raw_score) / (abs(raw_score) + 1)
  ```

- [ ] Feature extraction framework

**Deliverables:**
- `src/strategy/up_system.py` (skeleton)
- Normalization utilities
- Feature calculation framework

---

### Day 29-30: UP System Features Implementation
**Hours:** 16h
**Tasks:**
- [ ] **F1: Higher Highs (1m)** (Spec Section 5.1.1)
  ```python
  def calculate_higher_highs_1m(close_1m, lookback=20, norm_window=100):
      max_close = close_1m.rolling(window=lookback).max()
      feature = (close_1m - max_close) / close_1m.rolling(window=norm_window).std()
      return normalize_zscore(feature, window=norm_window)
  ```

- [ ] **F2: Higher Highs (15m)**
  ```python
  def calculate_higher_highs_15m(close_15m, lookback=20, norm_window=100):
      max_close = close_15m.rolling(window=lookback).max()
      feature = (close_15m - max_close) / close_15m.rolling(window=norm_window).std()
      return normalize_zscore(feature, window=norm_window)
  ```

- [ ] **F3: Bullish Slope (EMA)**
  ```python
  def calculate_bullish_slope(close_1m, ema_period=20):
      ema = calculate_ema(close_1m, period=ema_period)
      ema_20_bars_ago = ema.shift(20)
      slope_feature = (ema / ema_20_bars_ago) - 1
      return normalize_zscore(slope_feature, window=100)
  ```

- [ ] **F4: Strong Volume**
  ```python
  def calculate_volume_feature(volume_1m, sma_period=20):
      volume_sma = volume_1m.rolling(window=sma_period).mean()
      volume_feature = (volume_1m / volume_sma) - 1
      return normalize_zscore(volume_feature, window=100)
  ```

- [ ] **F5: Funding Gradient** (Futures only)
  ```python
  def calculate_funding_gradient(funding_rate, prev_funding_rate):
      if prev_funding_rate == 0:
          return 0
      gradient = np.sign(funding_rate) * (abs(funding_rate) / abs(prev_funding_rate) - 1)
      return gradient
  ```

- [ ] **F6: Spread Penalty**
  ```python
  def calculate_spread_penalty(ask, bid):
      spread = ask - bid
      spread_mean = spread.rolling(window=20).mean()
      spread_std = spread.rolling(window=100).std()
      penalty = np.maximum((spread - spread_mean) / spread_std, 0)
      return penalty
  ```

- [ ] Integrate all features into UP system

**Deliverables:**
- Complete UP system feature calculation
- Unit tests for each feature
- End-to-end UP system test

**Testing:**
```python
# Test UP system
market_data = load_test_data("BTCUSDT", "2025-10-01", "2025-10-26")
up_system = UPSystem(config)
features = up_system.calculate_features(market_data)
raw_score = up_system.calculate_raw_score(features)
b_up = up_system.calculate_bias(raw_score)
c_up = up_system.calculate_confidence(raw_score)

assert -1 <= b_up <= 1
assert 0 <= c_up <= 1
```

---

### Day 31: Initial Weight Calculation (Correlation-Based)
**Hours:** 8h
**Tasks:**
- [ ] Implement rolling correlation weight initialization (Spec Section 5.1.1)
  ```python
  def calculate_initial_weights(features_df, target_returns, window=100):
      """
      Calculate feature weights based on correlation with target.

      Spec: Section 5.1.1 - "Rolling Window Correlation Analysis"

      Args:
          features_df: DataFrame with columns [F1, F2, F3, F4, F5, F6]
          target_returns: Series of forward 5-minute price returns
          window: Rolling window size (default 100)

      Returns:
          dict: {feature_name: weight}
      """
      correlations = {}

      for feature_name in features_df.columns:
          # Calculate Pearson correlation over rolling window
          corr = features_df[feature_name].rolling(window=window).corr(target_returns)
          # Use absolute value (we care about strength, not direction)
          correlations[feature_name] = abs(corr.iloc[-1])

      # Normalize to sum to 1.0
      total = sum(correlations.values())
      if total > 0:
          weights = {k: v / total for k, v in correlations.items()}
      else:
          # Fallback: equal weights
          n = len(correlations)
          weights = {k: 1.0 / n for k in correlations.keys()}

      return weights
  ```

- [ ] Target variable calculation (5-minute forward return)
  ```python
  def calculate_target_returns(close_prices, horizon_minutes=5):
      """Calculate forward return over specified horizon"""
      future_price = close_prices.shift(-horizon_minutes)
      returns = (future_price - close_prices) / close_prices
      return returns
  ```

- [ ] Weight persistence (save to strategy_state DB table)

**Deliverables:**
- Initial weight calculation implementation
- Weight persistence mechanism
- Fallback for insufficient data

---

## Week 7: DOWN & NEUTRAL Systems + Ensemble

### Day 32: DOWN System Implementation
**Hours:** 8h
**Tasks:**
- [ ] DOWN System class (mirror of UP)
  ```python
  class DOWNSystem:
      def __init__(self, config):
          self.config = config
          self.feature_weights = None

      def calculate_features(self, market_data):
          """
          Calculate DOWN features (inverted from UP):
          - F1: Lower Lows (1m)
          - F2: Lower Lows (15m)
          - F3: Bearish Slope (negative EMA slope)
          - F4: Strong Volume (same as UP)
          - F5: Funding Gradient (penalize positive funding)
          - F6: Spread Penalty (same as UP)
          """
          pass

      def calculate_raw_score(self, features):
          """Weighted sum"""
          pass

      def calculate_bias(self, raw_score):
          """b_down = tanh(raw_score)"""
          return np.tanh(raw_score)

      def calculate_confidence(self, raw_score):
          """Phase 1: Heuristic"""
          return abs(raw_score) / (abs(raw_score) + 1)
  ```

- [ ] Feature implementations:
  - **Lower Lows (1m)**: `(MIN(close, 20) - current_close) / STD(close, 100)`
  - **Lower Lows (15m)**: Same for 15m timeframe
  - **Bearish Slope**: Negative of bullish slope

- [ ] Initial weight calculation (target: negative forward return)

**Deliverables:**
- Complete DOWN system
- Unit tests
- Weight initialization

---

### Day 33: NEUTRAL System Implementation
**Hours:** 8h
**Tasks:**
- [ ] NEUTRAL System class (Spec Section 5.1.3)
  ```python
  class NEUTRALSystem:
      def __init__(self, config):
          self.config = config
          self.bollinger_period = config.neutral_system.bollinger_period
          self.rsi_period = config.neutral_system.rsi_period
          self.autocorr_lags = config.neutral_system.autocorrelation_lags

      def calculate_features(self, market_data):
          """
          F1: Bollinger Band Distance
          F2: RSI deviation from 50
          F3: Auto-correlation of returns
          F4: Trend Aversion Penalty
          """
          pass

      def calculate_raw_score(self, features):
          """Weighted sum"""
          pass

      def calculate_bias(self, raw_score):
          """b_neu = tanh(raw_score)"""
          return np.tanh(raw_score)

      def calculate_confidence(self, raw_score):
          """Phase 1: Heuristic"""
          return abs(raw_score) / (abs(raw_score) + 1)
  ```

- [ ] **F1: Bollinger Band Distance**
  ```python
  def calculate_bb_distance(close, period=20):
      upper, middle, lower = calculate_bollinger_bands(close, period=period)
      bb_distance = (close - middle) / (upper - lower)
      return normalize_zscore(bb_distance, window=100)
  ```

- [ ] **F2: RSI Feature**
  ```python
  def calculate_rsi_feature(close, period=14):
      rsi = calculate_rsi(close, period=period)
      rsi_feature = (rsi - 50) / 50  # Normalize to [-1, 1]
      return normalize_zscore(rsi_feature, window=100)
  ```

- [ ] **F3: Auto-correlation**
  ```python
  def calculate_autocorrelation(returns_1m, lags=20):
      # Calculate lag-1 autocorrelation over rolling window
      autocorr = returns_1m.rolling(window=lags).apply(
          lambda x: x.autocorr(lag=1), raw=False
      )
      return normalize_zscore(autocorr, window=100)
  ```

- [ ] **F4: Trend Aversion Penalty**
  ```python
  def calculate_trend_penalty(close_15m, ema_period=20):
      ema = calculate_ema(close_15m, period=ema_period)
      slope = (ema - ema.shift(1)) / ema.shift(1)
      penalty = abs(slope)
      return normalize_zscore(penalty, window=100)
  ```

- [ ] Initial weight calculation (target: absolute price deviation)

**Deliverables:**
- Complete NEUTRAL system
- Unit tests
- Weight initialization

---

### Day 34: Ensemble Conviction Calculation
**Hours:** 8h
**Tasks:**
- [ ] Ensemble class implementation (Spec Section 5.2)
  ```python
  class EnsembleStrategy:
      def __init__(self, up_system, down_system, neutral_system, config):
          self.up = up_system
          self.down = down_system
          self.neutral = neutral_system

          # Initial weights (equal)
          self.w1 = 0.5  # UP contribution to Long
          self.w2 = 0.5  # NEUTRAL contribution to Long
          self.v1 = 0.5  # DOWN contribution to Short
          self.v2 = 0.5  # NEUTRAL contribution to Short

      def calculate_convictions(self, market_data):
          """
          Calculate Long and Short conviction scores.
          Spec: Section 5.2
          """
          # Get system outputs
          b_up, c_up = self.up.calculate(market_data)
          b_down, c_down = self.down.calculate(market_data)
          b_neu, c_neu = self.neutral.calculate(market_data)

          # Long conviction
          L = (self.w1 * b_up * c_up) + (self.w2 * max(b_neu, 0) * c_neu)

          # Short conviction
          S = (self.v1 * (-b_down) * c_down) + (self.v2 * abs(min(b_neu, 0)) * c_neu)

          return L, S
  ```

- [ ] System weight adaptation (weekly, placeholder for Milestone 6)
  ```python
  def update_system_weights(self, trade_history):
      """
      Weekly system weight update via Softmax.
      Spec: Section 5.2 - "Adaptive Weighting (Weekly)"

      To be fully implemented in Milestone 6.
      """
      # Calculate PnL attribution per system
      up_pnl = sum([t.realized_pnl for t in trade_history if t.system == 'UP'])
      down_pnl = sum([t.realized_pnl for t in trade_history if t.system == 'DOWN'])
      neutral_pnl = sum([t.realized_pnl for t in trade_history if t.system == 'NEUTRAL'])

      # Softmax transformation
      pnl_scores = np.array([up_pnl, neutral_pnl])  # For Long conviction
      weights = softmax(pnl_scores)
      self.w1, self.w2 = np.clip(weights, 0.2, 0.8)  # Constrain

      # Repeat for Short conviction
      # ... (similar logic for v1, v2)
  ```

**Deliverables:**
- Ensemble strategy class
- Conviction calculation
- Weight adaptation skeleton

---

### Day 35: Integration & Main Event Loop
**Hours:** 8h
**Tasks:**
- [ ] Main strategy engine orchestration
  ```python
  class StrategyEngine:
      def __init__(self, config):
          self.market_data = MarketDataProcessor()
          self.ensemble = EnsembleStrategy(
              UPSystem(config),
              DOWNSystem(config),
              NEUTRALSystem(config),
              config
          )

      def on_candle_close_1m(self, symbol, candle):
          """
          Main event loop trigger: called every 1m candle close.
          Spec: Section 5.5 - "Core Trading Algorithm"
          """
          # Update market data
          self.market_data.on_candle_update(symbol, "1m", candle)

          # Calculate convictions
          L, S = self.ensemble.calculate_convictions(
              self.market_data.get_data(symbol)
          )

          # Log for monitoring
          logger.info(f"{symbol} | L={L:.3f}, S={S:.3f}")

          # Signal generation (placeholder for Milestone 5)
          # if L > threshold:
          #     self.place_long_order(...)
  ```

- [ ] Connect to WebSocket kline events
- [ ] Strategy state persistence (save convictions)

**Deliverables:**
- Main strategy engine
- Event loop integration
- Logging of conviction scores

---

### Days 36-40: Testing & KPI Validation
**Hours:** 40h
**Tasks:**
- [ ] **KPI 4.1: All 6 values logged every 1m**
  ```bash
  # Run bot for 24 hours
  python src/main.py --config config/testnet.json

  # Verify logs
  cat logs/bot_2025-10-27.log | jq 'select(.event_type == "STRATEGY_UPDATE")'
  # Expected output (every 1 minute):
  # {"timestamp": "...", "event_type": "STRATEGY_UPDATE", "symbol": "BTCUSDT",
  #  "b_up": 0.42, "c_up": 0.68, "b_down": -0.23, "c_down": 0.51,
  #  "b_neu": 0.15, "c_neu": 0.62}
  ```

- [ ] **KPI 4.2: b_up increases during price pump**
  ```python
  # Simulate 5% price pump
  # Inject test data: steady uptrend over 30 minutes

  results = []
  for i, candle in enumerate(test_candles):
      strategy.on_candle_close_1m("BTCUSDT", candle)
      L, S = strategy.get_convictions()
      b_up = strategy.ensemble.up.last_bias
      results.append({"time": i, "b_up": b_up, "price": candle.close})

  # Verify b_up trend
  assert results[-1]['b_up'] > results[0]['b_up'] + 0.3  # Significant increase
  ```

- [ ] **KPI 4.3: Long conviction formula verified**
  ```python
  # Manual calculation check
  b_up, c_up = 0.5, 0.7
  b_neu, c_neu = 0.2, 0.6
  w1, w2 = 0.5, 0.5

  expected_L = (w1 * b_up * c_up) + (w2 * max(b_neu, 0) * c_neu)
  actual_L = strategy.ensemble.calculate_convictions(data)[0]

  assert abs(expected_L - actual_L) < 0.001
  ```

- [ ] **KPI 4.4: 24-hour run without crashes**
  ```bash
  # Start 24-hour run
  nohup python src/main.py > run_m4.log 2>&1 &

  # Monitor for crashes
  # Expected: No unhandled exceptions, continuous log output
  ```

- [ ] Unit test suite for all systems
- [ ] Integration tests for ensemble
- [ ] Performance benchmarking (strategy calculations < 100ms per candle)

**Deliverables:**
- KPI validation report
- Test suite
- 24-hour run log
- Bug fixes

---

## Milestone 4 Module Structure

```
src/
├── market_data/
│   ├── __init__.py
│   ├── data_processor.py    # OHLCV aggregation
│   ├── indicators.py         # ATR, EMA, BB, RSI, etc.
│   └── normalizer.py         # Z-score normalization
├── strategy/
│   ├── __init__.py
│   ├── strategy_engine.py    # Main orchestrator
│   ├── up_system.py          # UP system
│   ├── down_system.py        # DOWN system
│   ├── neutral_system.py     # NEUTRAL system
│   ├── ensemble.py           # Ensemble conviction calculation
│   └── feature_utils.py      # Shared feature calculation utils
└── main.py                   # Updated with strategy integration

tests/
├── unit/
│   ├── test_indicators.py
│   ├── test_up_system.py
│   ├── test_down_system.py
│   ├── test_neutral_system.py
│   └── test_ensemble.py
└── integration/
    └── test_strategy_engine.py
```

---

## Milestone 4 Testing Checklist

### Unit Tests
- [ ] Each indicator calculation
- [ ] Feature normalization
- [ ] UP system features (F1-F6)
- [ ] DOWN system features
- [ ] NEUTRAL system features
- [ ] Initial weight calculation
- [ ] Conviction formula

### Integration Tests
- [ ] Full UP system with real market data
- [ ] Full DOWN system with real market data
- [ ] Full NEUTRAL system with real market data
- [ ] Ensemble conviction calculation
- [ ] Strategy engine event loop

### System Tests
- [ ] 24-hour Testnet run
- [ ] Conviction scores logged every 1m
- [ ] No crashes or memory leaks

### KPI Validation
- [ ] KPI 4.1: All 6 values logged
- [ ] KPI 4.2: b_up increases during pump
- [ ] KPI 4.3: Formula verified
- [ ] KPI 4.4: 24h run stable

---

## Milestone 4 Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Indicator calculation errors | Invalid signals | Extensive unit tests, benchmark against TA-Lib |
| Insufficient historical data | Weight initialization fails | Fallback to equal weights |
| Slow calculation speed | Missed candles | Vectorization, caching, profiling |
| Feature correlation too weak | Poor initial weights | Manual review, adjust lookback windows |

---

## Milestone 4 Approval Criteria

✅ All 4 KPIs passed
✅ Unit test coverage > 80%
✅ 24-hour run completed without crashes
✅ Conviction scores make intuitive sense (up during pumps, down during dumps)
✅ Initial weight calculation working

**Sign-off Required By:** Client Stakeholder
**Next Milestone Start:** Upon written approval

---

# Milestone 5: Dynamic Parameters, Order Management & Conviction Filter

**Duration:** 1.5 weeks (60 hours)
**Cost:** $3,000
**Objective:** Implement adaptive order sizing, spacing, TP/SL, and conviction-based filtering

---

## Week 8: Dynamic Parameter Calculations

### Day 41: Volatility & Imbalance Factors
**Hours:** 8h
**Tasks:**
- [ ] Volatility factor calculation (Spec Section 5.4)
  ```python
  def calculate_volatility_factor(market_data):
      """
      volatility_factor = ATR(14)[1h] / ATR(14)[1h]_SMA(100)
      """
      atr_1h = market_data.get_indicator("ATR", timeframe="1h", period=14)
      atr_sma = atr_1h.rolling(window=100).mean()
      volatility_factor = atr_1h / atr_sma
      return volatility_factor.iloc[-1]
  ```

- [ ] Imbalance calculation
  ```python
  def calculate_imbalance(L, S):
      """imbalance = max(L - S, 0)"""
      return max(L - S, 0)
  ```

- [ ] Integration with strategy engine

**Deliverables:**
- Volatility and imbalance calculation
- Unit tests

---

### Day 42-43: Dynamic Order Size & Grid Spacing
**Hours:** 16h
**Tasks:**
- [ ] Dynamic order size (Spec Section 5.4)
  ```python
  def calculate_dynamic_order_size(
      base_order_size, L, imbalance, volatility_factor,
      size_mult=0.8, imb_mult=0.4, vol_mult=0.6
  ):
      """
      long_size = base_order_size * (1 + size_mult * L + imb_mult * imbalance) /
                  (1 + vol_mult * volatility_factor)

      Clamped: [0.25 * base, 3.0 * base]
      """
      numerator = 1 + size_mult * L + imb_mult * imbalance
      denominator = 1 + vol_mult * volatility_factor
      long_size = base_order_size * (numerator / denominator)

      # Clamp
      min_size = 0.25 * base_order_size
      max_size = 3.0 * base_order_size
      return np.clip(long_size, min_size, max_size)
  ```

- [ ] Dynamic grid spacing (Spec Section 5.4)
  ```python
  def calculate_dynamic_spacing(
      baseline_spacing, L, imbalance, volatility_factor, ATR,
      vol_mult=0.6, spacing_clamp_min=0.4, spacing_clamp_max=2.5
  ):
      """
      long_spacing = baseline_spacing * (1 + vol_mult * volatility_factor) /
                     (1 + 0.5 * L + 0.4 * imbalance)

      Clamped: [spacing_clamp_min * ATR, spacing_clamp_max * ATR]
      """
      numerator = baseline_spacing * (1 + vol_mult * volatility_factor)
      denominator = 1 + 0.5 * L + 0.4 * imbalance
      long_spacing = numerator / denominator

      # Clamp
      min_spacing = spacing_clamp_min * ATR
      max_spacing = spacing_clamp_max * ATR
      return np.clip(long_spacing, min_spacing, max_spacing)
  ```

- [ ] Baseline spacing calculation
  ```python
  baseline_spacing = baseline_spacing_multiplier * ATR(14)[1h]
  # Default baseline_spacing_multiplier = 0.75
  ```

- [ ] Short-side calculations (mirror logic)

**Deliverables:**
- Dynamic sizing functions
- Dynamic spacing functions
- Unit tests with various conviction/volatility combinations

---

### Day 44-46: Dynamic Take-Profit & Stop-Loss
**Hours:** 24h
**Tasks:**
- [ ] **Initial TP calculation** (Spec Section 5.4.1)
  ```python
  def calculate_initial_tp(entry_price, long_spacing, L_open, tp_conviction_mult=0.2):
      """
      initial_tp_distance = long_spacing * (1 + tp_conviction_mult * L_open)
      initial_tp_price = entry_price + initial_tp_distance
      """
      tp_distance = long_spacing * (1 + tp_conviction_mult * L_open)
      tp_price = entry_price + tp_distance
      return tp_price, tp_distance
  ```

- [ ] **TP trailing logic** (every 1m candle)
  ```python
  class TakeProfitManager:
      def __init__(self, position):
          self.position = position
          self.L_open = position.L_at_entry
          self.L_peak = position.L_at_entry
          self.current_tp_price = position.initial_tp_price

      def update(self, L_current, long_spacing_current):
          """
          Trailing: If L_current > L_previous, raise TP
          Fading: If L_current < 0.5 * L_peak (last 10 min), tighten TP
          """
          # Trailing logic
          if L_current > self.L_previous:
              new_tp_distance = long_spacing_current * (1 + tp_conviction_mult * L_current)
              new_tp_price = self.position.entry_price + new_tp_distance

              # Only move TP up (for longs)
              if new_tp_price > self.current_tp_price:
                  self.current_tp_price = new_tp_price
                  self.modify_tp_order(new_tp_price)

          # Fading trend logic
          if L_current < 0.5 * self.L_peak:
              tightened_distance = long_spacing_current * (1 + tp_conviction_mult * L_current) * tp_reduction_factor_level_1
              new_tp_price = self.position.entry_price + tightened_distance

              if new_tp_price > self.current_tp_price:
                  self.current_tp_price = new_tp_price
                  self.modify_tp_order(new_tp_price)

          # Enforce cap
          max_tp_distance = tp_cap_multiplier * self.position.initial_tp_distance
          capped_tp_price = self.position.entry_price + max_tp_distance
          self.current_tp_price = min(self.current_tp_price, capped_tp_price)

          self.L_previous = L_current
  ```

- [ ] **Dynamic stop-loss trigger** (Spec Section 5.4.2)
  ```python
  class StopLossManager:
      def __init__(self, position):
          self.position = position
          self.L_open = position.L_at_entry  # For longs
          self.S_open = position.S_at_entry  # For shorts

      def check_trigger(self, L_current, S_current):
          """
          For long positions:
            Trigger if S_current > 0.6 AND L_current < 0.5 * L_open

          For short positions:
            Trigger if L_current > 0.6 AND S_current < 0.5 * S_open
          """
          if self.position.side == "LONG":
              if S_current > stop_loss_short_conviction_threshold and L_current < 0.5 * self.L_open:
                  return True
          else:  # SHORT
              if L_current > stop_loss_long_conviction_threshold and S_current < 0.5 * self.S_open:
                  return True
          return False

      def execute_stop_loss(self):
          """Place LIMIT order at market price to close position"""
          market_price = get_current_market_price(self.position.symbol)

          oms.submit_order(
              symbol=self.position.symbol,
              side="SELL" if self.position.side == "LONG" else "BUY",
              type="LIMIT",
              quantity=self.position.size,
              price=market_price,  # LIMIT at market for immediate fill
              reason="STOP_LOSS"
          )
  ```

- [ ] TP/SL order modification via OMS
- [ ] Integration with position tracking

**Deliverables:**
- TP manager with trailing logic
- SL manager with conviction decay trigger
- OMS integration for TP/SL order modification

---

## Week 9: Order Re-centering & Conviction Filter

### Day 47: Order Re-centering System
**Hours:** 8h
**Tasks:**
- [ ] Re-centering logic (Spec Section 5.2.4)
  ```python
  class OrderRecentering:
      def __init__(self, oms, config):
          self.oms = oms
          self.threshold_multiplier = 4.0  # 4 * ATR away triggers recentering

      def check_and_recenter(self, symbol, current_market_price, current_atr):
          """
          Called every 1m candle close.
          Checks all open limit orders and recenters if needed.
          """
          open_orders = self.oms.get_open_orders(symbol)
          threshold = self.threshold_multiplier * current_atr

          for order in open_orders:
              distance = abs(order.price - current_market_price)

              if distance > threshold:
                  # Calculate new price
                  new_price = self.calculate_new_price(
                      order, current_market_price, current_spacing, threshold
                  )

                  # Attempt to modify
                  try:
                      self.oms.modify_order(symbol, order.order_id, new_price, order.quantity)
                      logger.info(f"Recentered order {order.order_id} from {order.price} to {new_price}")
                  except ModifyOrderException as e:
                      # Fallback: cancel + replace
                      logger.warning(f"Modify failed for {order.order_id}, canceling...")
                      self.oms.cancel_order(symbol, order.order_id)
                      # Order will be replaced in next grid maintenance cycle

      def calculate_new_price(self, order, market_price, spacing, threshold):
          """
          New price = market_price ± (n * spacing)
          where n is smallest integer such that new_price is within threshold
          """
          if order.side == "BUY":
              # BUY orders below market
              n = math.ceil((market_price - threshold) / spacing)
              new_price = market_price - (n * spacing)
          else:  # SELL
              # SELL orders above market
              n = math.ceil((threshold - market_price) / spacing)
              new_price = market_price + (n * spacing)

          return new_price
  ```

- [ ] Integration with main strategy loop
- [ ] Modify vs cancel+replace decision logic

**Deliverables:**
- Order re-centering system
- Integration with OMS
- Unit tests

---

### Day 48: Proximity-Based Conviction Cancellation
**Hours:** 8h
**Tasks:**
- [ ] Proximity check (Spec Section 5.5.3)
  ```python
  class ProximityConvictionCancellation:
      def __init__(self, oms, strategy, config):
          self.oms = oms
          self.strategy = strategy
          self.proximity_threshold = 1.0  # 1.0 * ATR

      def check_and_cancel(self, symbol, market_price, current_atr, L, S):
          """
          If market price within 1.0 * ATR of an order:
            - Cancel BUY order if S >= L
            - Cancel SELL order if L >= S
          """
          open_orders = self.oms.get_open_orders(symbol)
          proximity = self.proximity_threshold * current_atr

          for order in open_orders:
              distance = abs(order.price - market_price)

              if distance <= proximity:
                  # Check conviction
                  if order.side == "BUY" and S >= L:
                      logger.info(f"Canceling BUY order {order.order_id} due to conviction flip (S >= L)")
                      self.oms.cancel_order(symbol, order.order_id)

                  elif order.side == "SELL" and L >= S:
                      logger.info(f"Canceling SELL order {order.order_id} due to conviction flip (L >= S)")
                      self.oms.cancel_order(symbol, order.order_id)
  ```

- [ ] Integration with strategy engine

**Deliverables:**
- Proximity-based cancellation system
- Integration tests

---

### Day 49: Conviction-Based Entry Filter
**Hours:** 8h
**Tasks:**
- [ ] Percentile calculation (Spec Section 5.3.1)
  ```python
  class ConvictionFilter:
      def __init__(self, config):
          self.percentile_threshold = config.strategy.conviction_filter.percentile_threshold  # 80
          self.lookback_period = config.strategy.conviction_filter.lookback_period  # 1440 (24h)
          self.initial_fallback = config.strategy.conviction_filter.initial_fallback  # 0.7

          self.conviction_history = []  # Rolling buffer

      def update(self, L, S):
          """Store conviction scores"""
          self.conviction_history.append({"L": L, "S": S, "timestamp": datetime.utcnow()})

          # Keep only last lookback_period
          if len(self.conviction_history) > self.lookback_period:
              self.conviction_history = self.conviction_history[-self.lookback_period:]

      def get_min_entry_conviction(self, direction="LONG"):
          """
          Calculate dynamic threshold: Nth percentile of recent scores
          """
          if len(self.conviction_history) < self.lookback_period:
              # Insufficient data: use fallback
              return self.initial_fallback

          # Extract relevant conviction scores
          if direction == "LONG":
              scores = [h["L"] for h in self.conviction_history]
          else:  # SHORT
              scores = [h["S"] for h in self.conviction_history]

          # Calculate percentile
          threshold = np.percentile(scores, self.percentile_threshold)
          return threshold

      def should_enter_trade(self, L, S, direction="LONG"):
          """
          Entry rule: conviction must exceed dynamic threshold
          """
          threshold = self.get_min_entry_conviction(direction)

          if direction == "LONG":
              return L >= threshold
          else:  # SHORT
              return S >= threshold
  ```

- [ ] Integration with order placement logic

**Deliverables:**
- Conviction filter implementation
- Entry filtering in strategy engine

---

### Days 50-52: Integration & KPI Validation
**Hours:** 20h (rest of week 9.5)
**Tasks:**
- [ ] **KPI 5.1: TP LIMIT order fills**
  ```python
  # Test:
  # 1. Open long position with TP at +2%
  # 2. Simulate price rise to +2.5%
  # 3. Verify TP order filled
  # 4. Check TRADE_CLOSED log with exit_reason: "TP"
  ```

- [ ] **KPI 5.2: Order modification when >4x ATR away**
  ```python
  # Test:
  # 1. Place LIMIT BUY order at current_price - 10%
  # 2. Wait for market to move (or simulate)
  # 3. When distance > 4 * ATR, verify modify_order called
  # 4. Check log for ORDER_MODIFIED event
  ```

- [ ] **KPI 5.3: Entry skipped when conviction below 90th percentile**
  ```python
  # Test:
  # 1. Set conviction_filter.percentile_threshold = 90
  # 2. Generate low conviction signal (L = 0.55)
  # 3. Verify no order placed
  # 4. Check log for "Entry skipped: conviction below threshold"
  ```

- [ ] **KPI 5.4: Drawdown at -7% reduces order size & TP**
  ```python
  # Test:
  # 1. Manually set drawdown to -7%
  # 2. Trigger DRAWDOWN_BREACH event
  # 3. Verify base_order_size *= 0.5
  # 4. Verify tp_distance *= 0.7
  # 5. Check next order placed uses reduced size
  ```

- [ ] Integration testing with full strategy
- [ ] Performance testing (order management overhead < 50ms)

**Deliverables:**
- KPI validation report
- Integration tests
- Bug fixes

---

## Milestone 5 Approval Criteria

✅ All 4 KPIs passed
✅ TP/SL orders modify correctly based on conviction changes
✅ Order re-centering prevents stale orders
✅ Conviction filter reduces noise trades
✅ Drawdown response tested

**Sign-off Required By:** Client Stakeholder
**Next Milestone Start:** Upon written approval

---

# Milestone 6: Drawdown Brakes, Adaptive Learning & Final Integration

**Duration:** 2 weeks (80 hours)
**Cost:** $4,000
**Objective:** Complete adaptive learning, full risk brakes, and end-to-end integration

---

## Week 10: Drawdown Brakes & Adaptive Learning

### Day 53-54: Three-Level Drawdown Brakes
**Hours:** 16h
**Tasks:**
- [ ] Drawdown calculation (Spec Section 5.5.4)
  ```python
  class DrawdownManager:
      def __init__(self, risk_manager, strategy, config):
          self.risk_manager = risk_manager
          self.strategy = strategy
          self.config = config
          self.peak_equity = 0
          self.breached_levels = set()

      def update(self, current_equity):
          """Called on every equity update"""
          # Update peak
          if current_equity > self.peak_equity * 1.01:
              self.peak_equity = current_equity
              self.breached_levels.clear()

          # Calculate drawdown
          drawdown = (self.peak_equity - current_equity) / self.peak_equity

          # Check levels
          if drawdown >= 0.05 and -0.05 not in self.breached_levels:
              self.apply_level_1_brakes()
              self.breached_levels.add(-0.05)

          if drawdown >= 0.10 and -0.10 not in self.breached_levels:
              self.apply_level_2_brakes()
              self.breached_levels.add(-0.10)

          if drawdown >= 0.15 and -0.15 not in self.breached_levels:
              self.apply_level_3_brakes()
              self.breached_levels.add(-0.15)

          # Recovery logic
          if drawdown < 0.05 and len(self.breached_levels) > 0:
              self.revert_brakes()
  ```

- [ ] **Level 1 (-5% drawdown)**
  ```python
  def apply_level_1_brakes(self):
      """
      1. Reduce base_order_size by 50%
      2. Tighten TP distance by 30%
      """
      self.strategy.base_order_size *= 0.5
      self.strategy.tp_reduction_factor = tp_reduction_factor_level_1  # 0.7

      # Update all open TP orders
      for position in self.strategy.open_positions:
          position.tp_manager.recalculate_with_factor(0.7)

      logger.warning("Level 1 drawdown brake applied: -5%")
  ```

- [ ] **Level 2 (-10% drawdown)**
  ```python
  def apply_level_2_brakes(self):
      """
      1. Reduce base_leverage by 40%
      2. Raise conviction_percentile_threshold to 70
      """
      self.strategy.base_leverage *= 0.6

      # Update exchange leverage
      for symbol in self.config.symbols:
          self.exchange_gateway.set_leverage(symbol, self.strategy.base_leverage)

      # Tighten conviction filter
      self.strategy.conviction_filter.percentile_threshold = 70

      logger.warning("Level 2 drawdown brake applied: -10%")
  ```

- [ ] **Level 3 (-15% drawdown - Safe Mode)**
  ```python
  def apply_level_3_brakes(self):
      """
      1. Raise conviction_percentile_threshold to 85
      2. Further reduce leverage by 50%
      3. Hard conviction gate: L or S > 0.8
      4. Aggressive TP: 0.5 * initial_tp_distance
      """
      self.strategy.conviction_filter.percentile_threshold = 85
      self.strategy.base_leverage *= 0.5

      # Update exchange leverage
      for symbol in self.config.symbols:
          self.exchange_gateway.set_leverage(symbol, self.strategy.base_leverage)

      # Set hard conviction gate
      self.strategy.safe_mode_conviction_threshold = 0.8

      # Aggressive TP for all open positions
      for position in self.strategy.open_positions:
          position.tp_manager.set_emergency_tp(0.5)

      logger.critical("Level 3 drawdown brake applied: -15% (SAFE MODE)")
  ```

- [ ] Recovery logic (revert parameters when drawdown improves)

**Deliverables:**
- Complete drawdown brake system
- Integration with risk manager
- Recovery logic

---

### Day 55: Weekly Feature Weight Adaptation
**Hours:** 8h
**Tasks:**
- [ ] Performance attribution (Spec Section 5.1.1 - Adaptive Learning)
  ```python
  class FeatureWeightAdapter:
      def __init__(self, system, config):
          self.system = system  # UP, DOWN, or NEUTRAL
          self.config = config
          self.trade_history = []

      def record_trade(self, trade, feature_values_at_entry):
          """Record trade with feature snapshot"""
          self.trade_history.append({
              "trade": trade,
              "features": feature_values_at_entry
          })

      def update_weights_weekly(self):
          """
          Called every 7 days.
          Recalculate weights based on performance attribution.
          """
          if len(self.trade_history) < 10:
              logger.info("Insufficient trades for weight adaptation")
              return

          # Calculate feature scores
          feature_scores = {}
          for feature_name in self.system.features:
              score = 0
              total_feature_strength = 0

              for record in self.trade_history[-100:]:  # Last 100 trades
                  feature_value = record["features"][feature_name]
                  trade_pnl = record["trade"].realized_pnl

                  # Attribution formula (Spec Section 5.1.1)
                  score += abs(feature_value) * np.sign(feature_value) * trade_pnl
                  total_feature_strength += abs(feature_value)

              if total_feature_strength > 0:
                  feature_scores[feature_name] = score / total_feature_strength
              else:
                  feature_scores[feature_name] = 0

          # Softmax transformation
          scores = np.array(list(feature_scores.values()))
          T = 1.0  # Temperature
          exp_scores = np.exp(scores / T)
          new_weights = exp_scores / np.sum(exp_scores)

          # Apply bounds [0.1, 0.6]
          new_weights = np.clip(new_weights, 0.1, 0.6)
          new_weights /= np.sum(new_weights)  # Renormalize

          # Update system weights
          for i, feature_name in enumerate(feature_scores.keys()):
              self.system.feature_weights[feature_name] = new_weights[i]

          logger.info(f"Updated {self.system.name} feature weights: {self.system.feature_weights}")
  ```

- [ ] Integration with strategy engine (weekly task)

**Deliverables:**
- Feature weight adaptation
- Weekly update scheduler

---

### Day 56: Weekly System Weight Adaptation
**Hours:** 8h
**Tasks:**
- [ ] System PnL attribution (Spec Section 5.2 - Adaptive Weighting)
  ```python
  class SystemWeightAdapter:
      def __init__(self, ensemble, config):
          self.ensemble = ensemble
          self.config = config

      def update_weights_weekly(self, trade_history):
          """
          Recalculate system weights (w1, w2, v1, v2) based on PnL.
          """
          # Attribute PnL to systems
          up_pnl = sum([t.realized_pnl for t in trade_history if t.system == 'UP'])
          neutral_pnl_long = sum([t.realized_pnl for t in trade_history if t.system == 'NEUTRAL' and t.side == 'LONG'])
          neutral_pnl_short = sum([t.realized_pnl for t in trade_history if t.system == 'NEUTRAL' and t.side == 'SHORT'])
          down_pnl = sum([t.realized_pnl for t in trade_history if t.system == 'DOWN'])

          # Softmax for Long conviction weights (w1, w2)
          long_scores = np.array([up_pnl, neutral_pnl_long])
          w_exp = np.exp(long_scores)
          w_new = w_exp / np.sum(w_exp)
          w_new = np.clip(w_new, 0.2, 0.8)  # Constrain
          self.ensemble.w1, self.ensemble.w2 = w_new

          # Softmax for Short conviction weights (v1, v2)
          short_scores = np.array([down_pnl, neutral_pnl_short])
          v_exp = np.exp(short_scores)
          v_new = v_exp / np.sum(v_exp)
          v_new = np.clip(v_new, 0.2, 0.8)
          self.ensemble.v1, self.ensemble.v2 = v_new

          logger.info(f"Updated system weights: w1={self.ensemble.w1:.2f}, w2={self.ensemble.w2:.2f}, v1={self.ensemble.v1:.2f}, v2={self.ensemble.v2:.2f}")
  ```

- [ ] Integration with weekly scheduler

**Deliverables:**
- System weight adaptation
- Logging of weight updates

---

### Day 57: Performance-Calibrated Confidence
**Hours:** 8h
**Tasks:**
- [ ] Binned hit rate tracking (Spec Section 5.1.1 - Phase 2 Confidence)
  ```python
  class ConfidenceCalibrator:
      def __init__(self, system, bin_width=1.0, bin_range=(-5, 5), rolling_window=200):
          self.system = system
          self.bin_width = bin_width
          self.bin_range = bin_range
          self.rolling_window = rolling_window

          # Create bins
          self.bins = {}
          for b in np.arange(bin_range[0], bin_range[1], bin_width):
              self.bins[b] = {
                  "total_trades": deque(maxlen=rolling_window),
                  "profitable_trades": deque(maxlen=rolling_window)
              }

      def record_trade(self, raw_score_at_entry, trade_profitable):
          """Record trade outcome for the bin corresponding to raw_score"""
          bin_key = self.find_bin(raw_score_at_entry)

          self.bins[bin_key]["total_trades"].append(1)
          if trade_profitable:
              self.bins[bin_key]["profitable_trades"].append(1)
          else:
              self.bins[bin_key]["profitable_trades"].append(0)

      def calculate_confidence(self, raw_score):
          """
          Phase 2: Performance-calibrated confidence.
          Use empirical hit rate from binned history.
          """
          if len(self.system.trade_history) < 100:
              # Fallback to Phase 1 heuristic
              return abs(raw_score) / (abs(raw_score) + 1)

          bin_key = self.find_bin(raw_score)
          bin_data = self.bins.get(bin_key)

          if not bin_data or len(bin_data["total_trades"]) == 0:
              # No data for this bin, fallback
              return abs(raw_score) / (abs(raw_score) + 1)

          # Laplace smoothing
          total = len(bin_data["total_trades"])
          profitable = sum(bin_data["profitable_trades"])
          confidence = (profitable + 1) / (total + 2)

          return confidence

      def find_bin(self, raw_score):
          """Find bin for given raw_score"""
          for bin_key in sorted(self.bins.keys()):
              if raw_score < bin_key + self.bin_width:
                  return bin_key
          # Out of range, use edge bin
          return max(self.bins.keys())
  ```

- [ ] Integration with UP/DOWN/NEUTRAL systems
- [ ] Transition from Phase 1 to Phase 2 (after 100 trades)

**Deliverables:**
- Confidence calibration system
- Phase 1/2 transition logic

---

## Week 11: CME Gap, Weekend Volatility & Final Integration

### Day 58: CME Gap Detection & Influence
**Hours:** 8h
**Tasks:**
- [ ] CME gap detection (Spec Section 5.5.5)
  ```python
  class CMEGapHandler:
      def __init__(self, config):
          self.config = config
          self.cme_gap_enabled = config.strategy.cme_gap_enabled
          self.max_age_days = config.strategy.cme_gap_max_age_days  # 21
          self.influence_max = config.strategy.cme_gap_influence_max  # 0.1

          self.unfilled_gaps = []  # List of gaps

      def detect_gap(self, friday_close_price, sunday_open_price):
          """
          Called on Sunday 23:00 UTC.
          Detect gap if |price_diff| > 0.5% of price.
          """
          gap_size = sunday_open_price - friday_close_price
          gap_pct = abs(gap_size) / friday_close_price

          if gap_pct > 0.005:  # 0.5%
              self.unfilled_gaps.append({
                  "gap_price": friday_close_price,
                  "gap_size": gap_size,
                  "detected_at": datetime.utcnow(),
                  "filled": False
              })
              logger.info(f"CME gap detected: ${gap_size:.2f} at ${friday_close_price}")

      def calculate_influence(self, current_price, current_atr):
          """
          If price within 1.5 * ATR of an unfilled gap (≤21 days old):
            gap_influence = influence_max * (1.0 - days_since_gap / 21) * sign(gap)
          """
          total_influence = 0

          for gap in self.unfilled_gaps:
              if gap["filled"]:
                  continue

              # Check age
              age_days = (datetime.utcnow() - gap["detected_at"]).days
              if age_days > self.max_age_days:
                  gap["filled"] = True  # Expire
                  continue

              # Check proximity
              distance = abs(current_price - gap["gap_price"])
              if distance <= 1.5 * current_atr:
                  # Calculate influence
                  decay_factor = 1.0 - (age_days / self.max_age_days)
                  influence = self.influence_max * decay_factor * np.sign(gap["gap_size"])
                  total_influence += influence

                  # Check if gap filled
                  if np.sign(current_price - gap["gap_price"]) == np.sign(gap["gap_size"]):
                      gap["filled"] = True
                      logger.info(f"CME gap filled at ${current_price}")

          return total_influence
  ```

- [ ] Integration with NEUTRAL system (add to b_neu)

**Deliverables:**
- CME gap handler
- Integration with NEUTRAL system

---

### Day 59: Weekend Volatility Regime
**Hours:** 8h
**Tasks:**
- [ ] Weekend regime detection (Spec Section 5.5.5)
  ```python
  class WeekendVolatilityHandler:
      def __init__(self, config):
          self.config = config
          self.atr_threshold = config.strategy.weekend_atr_threshold  # 0.4

      def is_weekend_regime(self, current_atr_1h, weekly_avg_atr_1h):
          """
          Detect low-volatility weekend regime:
            current_atr_1h < 0.4 * weekly_avg_atr_1h
          """
          return current_atr_1h < self.atr_threshold * weekly_avg_atr_1h

      def apply_adjustments(self, strategy):
          """
          If weekend regime detected:
            1. Raise min_entry_conviction to 0.8
            2. Reduce max_orders_per_symbol to 25%
            3. Widen grid_spacing to 2.0 * ATR
          """
          strategy.min_entry_conviction = 0.8
          strategy.max_orders_per_symbol = int(strategy.max_orders_per_symbol * 0.25)
          strategy.spacing_multiplier = 2.0

          logger.info("Weekend volatility regime detected: adjustments applied")
  ```

- [ ] Integration with strategy engine (check every 1h)

**Deliverables:**
- Weekend volatility handler
- Strategy adjustments

---

### Day 60-65: End-to-End Integration & Testing
**Hours:** 48h
**Tasks:**
- [ ] Full system integration
  - Connect all modules (Milestones 1-6)
  - Verify event flow: WebSocket → Strategy → OMS → Exchange
  - Test state persistence across restarts

- [ ] 72-hour Testnet validation run
  ```bash
  # Configuration for full integration test
  {
    "exchange": {"testnet": true, "market_type": "futures"},
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "portfolio": {"leverage_cap": 5.0, ...},
    "strategy": {
      # All parameters from spec
    }
  }

  # Start run
  nohup python src/main.py --config config/testnet_72h.json > run_m6.log 2>&1 &
  ```

- [ ] Monitoring & metrics collection
  - Trades per hour
  - Conviction distribution
  - Order modification rate
  - TP/SL hit rate
  - Drawdown responses
  - Weight updates

- [ ] Performance profiling
  - Strategy calculation time per candle
  - Memory usage over 72 hours
  - Database growth rate
  - Log file size

- [ ] **KPI 6.1 Validation: -12% drawdown response**
  ```python
  # Test:
  # 1. Manually trigger -12% drawdown
  # 2. Verify max_orders_per_symbol reduced by 50%
  # 3. Verify base_leverage reduced to 3x (from 5x, after -10% already reduced to 3x, then *0.5)
  # 4. Check Binance UI shows leverage = 1.5x
  # 5. Verify logs show "Level 2 drawdown brake applied"
  ```

- [ ] **KPI 6.2 Validation: Feature weights updated after 7 days**
  ```python
  # After 7 days of trading:
  # 1. Query strategy_state table
  # 2. Check feature_weights for UP system
  # 3. Verify values have changed from initial correlation-based weights
  # 4. Check log for "Updated UP feature weights" message
  ```

- [ ] **KPI 6.3 Validation: System weights updated after 7 days**
  ```python
  # After 7 days:
  # 1. Check ensemble system weights (w1, w2, v1, v2)
  # 2. Verify they've changed from initial 0.5, 0.5
  # 3. Verify constrained between 0.2 and 0.8
  # 4. Check log for "Weekly Weight Update" message
  ```

- [ ] **KPI 6.4 Validation: 72h run stability**
  ```bash
  # After 72-hour run:
  # 1. Check bot still running (no crashes)
  # 2. Review logs for ERROR or CRITICAL events
  # 3. Verify no critical errors
  # 4. Check memory usage hasn't grown excessively
  # 5. Verify database size reasonable
  ```

- [ ] Bug fixes and optimizations

**Deliverables:**
- Complete integrated system
- 72-hour validation report
- Performance metrics
- KPI validation report

---

### Days 66-70: Documentation & Handover
**Hours:** 32h
**Tasks:**
- [ ] **README.md** - Quick start guide
- [ ] **SETUP.md** - Installation instructions
  - Python environment setup
  - Dependencies installation
  - Binance API key setup
  - Database initialization
  - First run guide

- [ ] **CONFIG.md** - Configuration reference
  - All 50+ parameters explained
  - Example configurations (conservative, aggressive, balanced)
  - Tuning guide

- [ ] **RUNBOOK.md** - Operations guide
  - Starting the bot
  - Monitoring the bot
  - Graceful shutdown
  - Troubleshooting common issues
  - Log analysis
  - State recovery

- [ ] **ARCHITECTURE.md** - System design
  - Module overview with diagrams
  - Data flow diagrams
  - Sequence diagrams for key operations
  - Extension points for future development

- [ ] **API.md** - Module interfaces
  - Public API for each module
  - Usage examples
  - Integration guide for new modules

- [ ] Code cleanup
  - Remove debug code
  - Standardize formatting (black/autopep8)
  - Add missing docstrings
  - Update type hints

- [ ] Final code review
- [ ] Handover session with client

**Deliverables:**
- Complete documentation suite
- Clean, production-ready codebase
- Handover training

---

## Milestone 6 Approval Criteria

✅ All 4 KPIs passed
✅ 72-hour run completed without critical errors
✅ Adaptive learning demonstrated (weights changed)
✅ Drawdown brakes functional at all 3 levels
✅ Complete documentation delivered
✅ Code is clean and maintainable

**Sign-off Required By:** Client Stakeholder
**Project Status:** COMPLETE

---

## Final Deliverables Checklist

### Code
- [x] Complete source code (all milestones)
- [x] Unit tests (>80% coverage)
- [x] Integration tests
- [x] System tests (48h + 72h runs)

### Documentation
- [ ] README.md
- [ ] SETUP.md
- [ ] CONFIG.md
- [ ] RUNBOOK.md
- [ ] ARCHITECTURE.md
- [ ] API.md
- [ ] CHANGELOG.md

### Validation
- [ ] 48-hour log (Milestone 3)
- [ ] 72-hour log (Milestone 6)
- [ ] All KPI reports (Milestones 1-6)
- [ ] Performance metrics

### Deployment
- [ ] config.json template
- [ ] requirements.txt
- [ ] Database schema (schema.sql)
- [ ] Startup scripts (run.sh, run.bat)

---

**Last Updated:** 2025-10-02
**Status:** Planning Complete
