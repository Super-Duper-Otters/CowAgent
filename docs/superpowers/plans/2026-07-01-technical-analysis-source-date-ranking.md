# Technical Analysis Source Date Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** During the configurable cache update window, choose the newest available market data source for technical analysis and cache invalidation instead of accepting the first successful source.

**Architecture:** Keep normal generation fast outside the configured probe window. Inside the configured window, compare candidate data sources by latest data date, use the freshest valid source for market-date resolution and generated reports, and only mark technical-analysis products stale when a source date is newer than the product market date.

**Tech Stack:** Python, pytest, AkShare/Tushare/BaoStock adapters, existing web-config backed cache policy.

---

### Task 1: Tests for Source Date Ranking and Product Freshness

**Files:**
- Modify: `tests/test_business.py`
- Modify: `tests/test_technical_analysis_skill_v02.py`

- [ ] **Step 1: Add a failing resolver test**

Add a test showing `MarketDateResolver` checks multiple A-share providers during the cache update window and returns the newest date instead of the first successful date.

- [ ] **Step 2: Add a failing cache display test**

Add a test showing a technical-analysis product with `business_date=2026-06-30` remains display-active on `2026-07-01 15:30` when the data-source probe latest date is also `2026-06-30`.

- [ ] **Step 3: Add a failing script-source test**

Add a test showing `analyze_universal.load_data_with_fallbacks()` chooses Tushare over AKShare during the configured probe window when Tushare has a newer latest `date`, even if AKShare has enough rows.

### Task 2: Resolver and Cache Policy

**Files:**
- Modify: `business/content/market_date_resolver.py`
- Modify: `business/cache/cache_policy.py`

- [ ] **Step 1: Expose configured probe-window checks**

Add a public helper that determines whether a datetime is inside the configured cache-update probe window.

- [ ] **Step 2: Rank resolver candidates in the probe window**

Change `MarketDateResolver` so that inside the configured window it evaluates all applicable providers, sorts successful candidates by `market_date` descending, and returns the newest.

- [ ] **Step 3: Keep normal behavior outside the probe window**

Outside the configured window, preserve first-success provider order for low latency.

- [ ] **Step 4: Remove system-date staleness for market symbols**

For recognized market symbols, `technical_analysis_cache_expired_after_close()` should invalidate only when `latest_market_date_from_probe_symbols()` returns a date greater than the product/cache market date. It should not compare market date to the system date.

### Task 3: Technical Analysis Script Source Selection

**Files:**
- Modify: `builtin/components/technical-analysis/scripts/analyze_universal.py`
- Modify: `business/content/technical_analysis.py`

- [ ] **Step 1: Pass probe-window config into the script**

When invoking the script, pass the configured probe start/end values through environment variables.

- [ ] **Step 2: Rank script data sources in the probe window**

Inside the script, when current Beijing time is inside the configured window, collect each valid source with at least 60 rows, compute latest `date`, and return the source with the newest date.

- [ ] **Step 3: Preserve fallback order outside the window**

Outside the configured window, keep the current AKShare -> Tushare -> BaoStock first-success behavior.

### Task 4: Verification

**Files:**
- Run tests only.

- [ ] **Step 1: Run focused business tests**

Run `py -m pytest tests/test_business.py -k "market_date_resolver or cache_policy or product_artifact_package_dates_use_analysis_date or web_cache_update" -q`.

- [ ] **Step 2: Run technical-analysis script tests**

Run `py -m pytest tests/test_technical_analysis_skill_v02.py -q`.

- [ ] **Step 3: Check git diff**

Run `git diff --check` and `git status --short`.
