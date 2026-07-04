# Market Data Provider Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize asset classification and provider-specific symbol/API mapping so technical-analysis cache probing and generation use the same market-data semantics.

**Architecture:** Add a business-layer canonical adapter for target classification and provider symbol conversion. Keep the skill script independently runnable by extracting a small script-local adapter with the same behavior. Market-date resolution and cache policy consume the business adapter; the script consumes the script-local adapter.

**Tech Stack:** Python dataclasses, pytest, AkShare/Tushare/BaoStock SDK wrappers, existing technical-analysis script.

---

### Task 1: Business Canonical Adapter

**Files:**
- Create: `business/market/__init__.py`
- Create: `business/market/provider_adapter.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write tests for `classify_asset_target()`**

Cover A share, CSI index, SH/SZ index, ETF, HK, US, convertible bond, and treasury futures.

- [ ] **Step 2: Write tests for provider symbols**

Assert `931250.CSI` maps to Tushare `931250.CSI`, AKShare `sh931250`, BaoStock `sh.931250`; assert `510300.SH` maps to ETF formats; assert unsupported providers return an empty symbol.

- [ ] **Step 3: Implement adapter dataclass and helpers**

Add `AssetTarget`, `classify_asset_target()`, `to_akshare_symbol()`, `to_tushare_symbol()`, `to_baostock_symbol()`, and `provider_capabilities()`.

### Task 2: Business Integration

**Files:**
- Modify: `business/content/market_date_resolver.py`
- Modify: `business/cache/cache_policy.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Replace local symbol parsing in `MarketDateResolver`**

Use `classify_asset_target()` and provider symbol helpers for all provider calls.

- [ ] **Step 2: Replace `cache_policy.market_from_symbol()` internals**

Delegate to the canonical adapter while preserving the public return aliases currently used by tests/UI.

- [ ] **Step 3: Add resolver tests for CSI and unsupported provider behavior**

Ensure `.CSI` uses Tushare `index_daily` semantics and AKShare `sh` prefix mapping.

### Task 3: Skill Script Adapter

**Files:**
- Modify: `builtin/components/technical-analysis/scripts/analyze_universal.py`
- Modify: `tests/test_technical_analysis_skill_v02.py`

- [ ] **Step 1: Extract script-local adapter helpers**

Keep the script standalone, but consolidate `_bare_code`, `_prefixed_code`, `_baostock_symbol`, and provider API decisions behind a small group of helper functions.

- [ ] **Step 2: Route Tushare by asset type**

Use `index_daily` for indexes and `daily` for A shares; keep existing fallback order outside the probe window.

- [ ] **Step 3: Expand script tests**

Cover `.CSI`, ETF, HK, US, convertible bond, and futures dynamic config mappings.

### Task 4: Verification

**Files:** no code edits.

- [ ] **Step 1: Run adapter and resolver tests**

Run `py -m pytest tests/test_business.py -k "provider_adapter or market_date_resolver or cache_policy" -q`.

- [ ] **Step 2: Run script tests**

Run `py -m pytest tests/test_technical_analysis_skill_v02.py -q`.

- [ ] **Step 3: Run real smoke probes where credentials are available**

Probe `600519.SH`, `931250.CSI`, `510300.SH`, `00700.HK`, `AAPL.US`, and `T0`; record source/date/row count.

- [ ] **Step 4: Run `git diff --check`**
