# Codebase Concerns

**Analysis Date:** 2026-05-04

## Scanner Logic Issues

### Issue: Momentum-Based Ranking Ignores Profitability

**Problem:** The scanner in `scanner.py` and `core/live_scanner.py` ranks stocks purely by momentum indicators without considering historical profitability from backtests.

**Files:** 
- `scanner.py` (lines 313-357)
- `core/live_scanner.py` (lines 103-121)

**Impact:** 
- RVNL ranks #1 in scanner but is only "Medium" in backtest
- IDFCFIRSTB appears in scanner results despite being a losing stock ("Bad")
- Scanner shows stocks with weak momentum (0.07% change) like IDFCFIRSTB

**Current Behavior:**
```python
# scanner.py lines 335-348 - Only momentum-based scoring
if change_pct > 2:
    score += 4
elif change_pct > 1:
    score += 3
elif change_pct > 0.5:
    score += 2
elif change_pct > 0:
    score += 1
```

**Evidence from User Backtest Results:**
| Stock | Scanner Rank | Backtest Result | Change % |
|-------|--------------|-----------------|----------|
| RVNL | #1 (Score 10) | Medium | 0.97% |
| SUZLON | #2 (Score 8) | Good | 0.42% |
| IDFCFIRSTB | #3 (Score 7) | Bad | 0.07% |
| IREDA | #4 (Score 7) | Best | 0.31% |
| IRFC | #5 (Score 7) | Good | 0.48% |

**Recommended Fix Approach (Two-Step Architecture):**

The scanner should NOT mix quality + momentum in one score. Instead:

**STEP 1: FILTER by Stock Quality (Data-Driven)**
- Before any scoring, filter out losing stocks based on backtest expectancy
- **DO NOT hardcode stock lists** - use dynamic data instead
- **Add robustness improvements:**

```python
# In scanner __init__ (load once, cache for all ticks)
self.performance = self._load_performance()  # Cache, not every tick

def _load_performance(self):
    """Load cached performance data."""
    path = "data/backtest_results.json"
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

# Filter logic per stock
perf = self.performance.get(symbol)

# IMPROVEMENT 1: Handle missing data (strict vs loose)
if not perf:
    continue  # Strict: skip unknown stocks
    # OR: pass  # Loose: allow exploration of new stocks

# IMPROVEMENT 2: Require minimum sample size
if perf.get("trades", 0) < 20:
    continue  # Don't trust expectancy from <20 trades

# Core filter: negative expectancy
if perf.get("expectancy", 0) <= 0:
    continue  # Skip losing stocks
```

**Important Tradeoffs:**
- **Strict filter** = safe but slow adaptation (won't discover new good stocks)
- **Loose filter** = adaptive but risky (might trade on unreliable data)

Expected `data/backtest_results.json` format:
```json
{
  "IREDA-EQ": { "expectancy": 2.1, "trades": 45 },
  "IRFC-EQ": { "expectancy": 1.5, "trades": 32 },
  "SUZLON-EQ": { "expectancy": 1.2, "trades": 28 },
  "IDFCFIRSTB-EQ": { "expectancy": -0.5, "trades": 50 }
}
```

**IMPROVEMENT 3: Make threshold configurable**
```python
# config/settings.py
MIN_MOMENTUM_THRESHOLD = 0.2  # Configurable, not hardcoded
MIN_EXPECTANCY = 0  # Minimum positive expectancy
MIN_TRADES = 20  # Minimum trades for reliability
```

> **Why configurable?** Market conditions change — thresholds should adapt without code changes.

**STEP 2: FILTER by Momentum Threshold**
- After quality filter, require minimum momentum:

```python
# Filter out weak movers
if change_pct < 0.2:
    continue
```

**STEP 3: RANK by Momentum (Unchanged)**
- Keep current scoring logic for ranking filtered stocks

**CORRECT Output:**
```
IREDA   | Score 9 | +0.31%
IRFC    | Score 8 | +0.48%
SUZLON  | Score 8 | +0.42%

No IDFCFIRSTB (expectancy <= 0) ❌
No RVNL blindly at top ✅
```

**IMPORTANT: DO NOT mix performance into score**
- ❌ Avoid: `score += performance_bonus`
- ❌ Avoid: weighted formulas
- ❌ Avoid: ML-style scoring
- Reason: Overfitting risk, system becomes static

### Issue: No Connection Between Scanner and Backtest

**Problem:** The backtest system (`backtest.py`) runs independently and produces profitability metrics, but these are not used by the scanner to adjust rankings.

**Files:**
- `scanner.py`
- `backtest.py`
- `core/live_scanner.py`

**Impact:** Scanner cannot leverage historical backtest performance to improve stock selection

**Fix Approach:**
1. Create `data/backtest_results.json` with expectancy per stock
2. Scanner reads performance data (STEP 1: QUALITY FILTER)
3. Backtest runs periodically to update stock quality ratings
4. Scanner uses only momentum for ranking (STEP 2: RANK)

**Implementation Priority Order:**

| Priority | Action | Files to Modify |
|----------|--------|-----------------|
| 🔴 DO NOW | Add momentum threshold (0.2%) from settings | `scanner.py` line 422, `core/live_scanner.py` line 129 |
| 🟡 DO TODAY | Create `data/backtest_results.json` with expectancy + trades | New file |
| 🟢 NEXT | Load & cache performance data in scanner init | `scanner.py`, `core/live_scanner.py` |
| 🟡 DO TODAY | Add min_trades filter (>= 20) | Same as above |
| 🟡 LATER | Refactor duplicate scanner logic | After quality filter working |

**Final Implementation Flow:**
```
FOR each stock in WATCHLIST:
    ↓
1. Check performance data (expectancy > 0, trades >= 20)
    ↓ (fail → skip)
2. Check momentum (change_pct >= MIN_MOMENTUM_THRESHOLD)
    ↓ (fail → skip)
3. Compute momentum score
    ↓
4. Add to results
    ↓
SORT by score (descending)
```

### Issue: Weak Momentum Threshold Too Low

**Problem:** Scanner accepts stocks with change_pct as low as 0.07% (IDFCFIRSTB), which indicates very weak momentum.

**Files:**
- `scanner.py` (line 422 - filter only checks `change_pct > 0`)
- `core/live_scanner.py` (line 129 - same weak filter)

**Current Filter:**
```python
if result["score"] >= 7 and result["change_pct"] > 0:  # Only checks > 0
```

**Fix Approach (STEP 2 - MOMENTUM FILTER):**
Add momentum threshold as part of filtering phase:
```python
# After quality filter, require minimum momentum
if result["change_pct"] < 0.2:
    continue  # Filter out weak movers
```

**Why 0.2%?**
- IDFCFIRSTB has 0.07% change - too weak
- SUZLON has 0.42% change - acceptable
- This threshold filters noise while keeping signal

## Architecture Concerns

### Issue: Duplicate Scanner Logic

**Problem:** Scanner logic is duplicated in two places with slight differences:
- `scanner.py` - standalone scanner using yfinance
- `core/live_scanner.py` - live scanner using Shoonya broker

**Files:**
- `scanner.py` (lines 35-402)
- `core/live_scanner.py` (lines 28-176)

**Impact:** 
- Maintenance burden - fixes need to be applied in two places
- Inconsistent behavior between modes
- Different scoring weights between the two implementations

**Fix Approach:**
- Extract common scanner logic into `core/scanner_base.py` or similar
- Have both scanners inherit from common base class

### Issue: Watchlist Defined in Multiple Places

**Problem:** Stock watchlist is defined in multiple locations with slight variations:
- `scanner.py` lines 12-29: WATCHLIST (without -EQ suffix)
- `core/live_scanner.py` line 32: uses `settings.WATCHLIST` (with -EQ suffix)
- `scanner_worker.py` lines 28-41: WATCHLIST (without -EQ suffix)
- `config/settings.py` lines 116-133: WATCHLIST (with -EQ suffix)

**Impact:** Potential for confusion and inconsistent scanning

**Fix Approach:**
- Consolidate to single source: `config/settings.py`
- Remove duplicate WATCHLIST definitions from other files

## Testing Gaps

### Issue: No Integration Tests for Scanner

**Problem:** Scanner is tested manually by running and viewing output. No automated tests verify:
- Correct ranking behavior
- Backtest result integration
- Filter thresholds

**Files:**
- `scanner.py` - no test file
- `scanner_worker.py` - no test file

**Fix Approach:**
- Add unit tests for `scan_stock()` function
- Add integration tests that verify scanner + backtest integration

---

## Key Insight

**Scanner = Eligibility Filter** (not prediction engine)

The scanner's job is to SELECT which stocks are eligible for the strategy - not to predict which will profit. The strategy (`ema_rsi_scalper.py`) makes the actual trading decision.

**Before:** Momentum-driven system
**After:** Quality-filtered momentum system

> Don't make your scanner smarter — make it selective

---

*Concerns audit: 2026-05-04*