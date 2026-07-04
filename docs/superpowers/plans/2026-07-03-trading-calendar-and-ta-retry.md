# Trading Calendar and Technical Analysis Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure technical analysis only accepts fresh market data dates and retries AI/card generation up to three times before failing.

**Architecture:** Add a focused trading-calendar module under `business/market` that builds a local calendar from Baostock, Tushare, or AkShare on a configured schedule. `MarketDateResolver` validates provider dates against the expected latest trading date and discards stale providers. `run_technical_analysis` keeps the expensive market report generation once, then retries AI normalization and rendering up to the configured maximum.

**Tech Stack:** Python, pytest, existing investment config service, Baostock/Tushare/AkShare optional adapters.

---

### Task 1: Trading Calendar Tests and Module

**Files:**
- Create: `business/market/trading_calendar.py`
- Modify: `tests/test_business.py`
- Modify: `business/config/config_service.py`
- Modify: `config.py`
- Modify: `config-template.json`

- [ ] Write failing tests for local calendar expected-date calculation, stale provider rejection, and config defaults.
- [ ] Implement local calendar cache, provider loading, fixed refresh-time checks, and max lag trading-day validation.
- [ ] Expose config keys for enabled flag, source order, refresh time, cache days, and max allowed lag trading days.

### Task 2: Resolver Integration

**Files:**
- Modify: `business/content/market_date_resolver.py`
- Modify: `tests/test_business.py`

- [ ] Write a failing resolver test where AKShare returns `2020-12-25`, Tushare returns `2026-07-02`, and the resolver chooses Tushare.
- [ ] Filter every provider date through `TradingCalendar.accept_market_date`.
- [ ] Keep explicit requested dates untouched.

### Task 3: System Config Page

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `channel/web/web_channel.py`

- [ ] Add trading-calendar settings to the existing cache-update panel.
- [ ] Save settings through the existing config API.
- [ ] Add refresh action for rebuilding the local calendar.

### Task 4: Technical Analysis Retry

**Files:**
- Modify: `business/content/technical_analysis.py`
- Modify: `business/audit/ai_generation.py`
- Modify: `tests/test_business.py`

- [ ] Write failing tests for AI invalid JSON retry, refusal text retry, and renderer retry.
- [ ] Retry AI normalization/rendering up to `technical_analysis.generation_max_attempts`, default `3`.
- [ ] Validate technical-analysis standard text before rendering so refusal text cannot become an image-generation failure.

### Task 5: Verification

**Files:**
- Run tests only.

- [ ] Run focused pytest tests for trading calendar, market date resolver, and technical-analysis retry.
- [ ] Run `git diff --check`.
