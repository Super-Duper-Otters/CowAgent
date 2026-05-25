# 股票字典自动刷新与中文名解析完善计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. 每个实现块由独立子agent负责，主会话在每块完成后做规格符合性 review 和代码质量 review，再进入下一块。

**Goal:** 用本地 SQLite 股票字典替换静态股票名映射，并支持 AKShare/Tushare 刷新、Web 配置、未命中补救和定时脚本，让用户可以稳定使用中文股票名触发技术分析。

**Architecture:** 股票名称解析独立为 `business.investment.stock_resolver`；`technical_analysis.py` 只负责输入解析、调用 Skill、AI 摘要和渲染。股票字典存放在投资业务库 `investment_stock_symbols`，由 AKShare 免费数据和可选 Tushare token 数据刷新。

**Tech Stack:** Python 3.12, SQLite, AKShare, optional Tushare, web.py, pytest, mypy, ruff, existing `business.investment` service patterns.

---

## Runtime Behavior

- `300502.SZ 技术分析`：直接识别标准代码，不依赖字典。
- `300502 技术分析`：按首位补后缀，`6` 开头为 `.SH`，其他为 `.SZ`。
- `新易盛 技术分析`：先查本地字典；唯一命中则继续；未命中时同步触发一次字典刷新再查；仍未命中返回“未找到对应标的，请检查股票代码或改用标准股票代码。”；多结果返回“股票名称匹配到多个标的，请改用股票代码。”。
- 数字代码成功但本地字典无记录时，不阻塞技术分析；后续刷新脚本补齐名称映射。
- 字典刷新失败时保留旧数据，不清空本地表。

## Subagent Blocks

### Subagent 1: Storage and Core Resolver

**Owned files:** `business/investment/storage.py`, `business/investment/stock_resolver.py`, `business/investment/technical_analysis.py`, `tests/test_investment_business.py`

**Requirements:**
- 新增表 `investment_stock_symbols`：
  - `code text not null`
  - `name text not null`
  - `market text not null`
  - `ts_code text`
  - `source text not null`
  - `updated_at text not null`
- 新增唯一索引 `idx_investment_stock_symbols_code` on `code`。
- 新增索引 `idx_investment_stock_symbols_name` on `name`。
- 新增索引 `idx_investment_stock_symbols_updated` on `updated_at`。
- 新建 `stock_resolver.py`，实现：
  - `resolve_stock(target: str, auto_refresh_on_miss: bool = True) -> tuple[str | None, ErrorCode | None]`
  - `refresh_stock_symbols(rows: list[dict[str, str]], source: str = "") -> int`
  - `list_stock_symbols(name: str = "", limit: int = 20) -> list[dict[str, str]]`
  - `stock_dictionary_stats() -> dict[str, object]`
- 代码规范：
  - 标准代码支持 `000001.SZ` / `600519.SH`。
  - 裸 6 位代码支持自动补市场后缀。
  - 中文名仅做精确匹配。
  - 未命中返回 `ErrorCode.STOCK_NOT_FOUND`。
  - 多命中返回 `ErrorCode.STOCK_AMBIGUOUS`。
  - `refresh_stock_symbols` 使用 upsert，不删除旧行。
- `technical_analysis.py` 改为调用 `stock_resolver.resolve_stock`，移除静态 `STOCK_NAME_MAP` 作为主路径。

**Tests:**
- 表结构初始化。
- `300502` -> `300502.SZ`。
- `600519` -> `600519.SH`。
- `新易盛` 唯一命中。
- 未知中文名返回 `STOCK_NOT_FOUND`。
- 重名中文名返回 `STOCK_AMBIGUOUS`。
- `technical_analysis.run_technical_analysis` 使用新 resolver。

### Subagent 2: Data Provider Refresh and Tushare Token

**Owned files:** `business/investment/stock_resolver.py`, `business/investment/config_service.py`, `tests/test_investment_business.py`

**Requirements:**
- 实现 `refresh_from_akshare() -> int`：
  - 调用 `akshare.stock_info_a_code_name()`。
  - 兼容列名 `code/name` 和中文列名 `代码/名称`。
  - 规范化为 `300502.SZ` / `600519.SH`。
  - source 为 `akshare`。
- 实现 `get_tushare_token(masked: bool = False) -> str`：
  - 优先 `get_config("tushare.token")`。
  - 其次环境变量 `TUSHARE_TOKEN`。
  - 最后 `~/.tushare_token`。
  - masked=True 时脱敏。
- 实现 `refresh_from_tushare() -> int`：
  - token 缺失时抛出明确异常 `tushare token not configured`。
  - 调用 `ts.pro_api(token).stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,exchange")`。
  - source 为 `tushare`。
- 实现 `refresh_from_auto() -> dict[str, object]`：
  - 先跑 AKShare。
  - 如果 Tushare token 存在，再跑 Tushare。
  - 返回每个 source 的 count/error，不因单个 source 失败删除旧字典。
- `config_service.CONFIG_FALLBACK_KEYS` 增加 `tushare.token` -> `tushare_token`。
- `tushare.token` 作为敏感配置，非 admin/technical_admin 不可修改，前端读取必须脱敏。

**Tests:**
- AKShare DataFrame 正确规范化并入库。
- Tushare token 读取优先级：后台配置 > env > 文件。
- Tushare token 缺失返回明确错误。
- Tushare DataFrame 正确规范化并入库。
- `get_config("tushare.token", masked=True)` 脱敏。

### Subagent 3: Refresh Script and Scheduling Docs

**Owned files:** `scripts/refresh_investment_stocks.py`, `docs/superpowers/plans/2026-05-25-stock-resolver-refresh-plan.md`, `tests/test_investment_business.py`

**Requirements:**
- 新增脚本 `scripts/refresh_investment_stocks.py`。
- CLI 参数：
  - `--source auto|akshare|tushare`，默认 `auto`。
  - `--json` 可选，输出机器可读 JSON。
- 退出码：
  - 至少一个数据源成功时为 `0`。
  - 所有数据源失败时为 `1`。
- 输出包含 source、count、error、db_path。
- 在本计划文档增加 Windows Task Scheduler 示例：
  - `py scripts/refresh_investment_stocks.py --source auto`
  - 建议每天 08:30 执行。

**Tests:**
- 用 monkeypatch 调用脚本 main，验证 source 分派。
- 验证 all-failed 时退出码为 1。
- 验证 --json 输出包含 source/count/error。

**已实施脚本/定时任务命令:**
- 手动刷新（默认 auto）：`py scripts/refresh_investment_stocks.py`
- 指定数据源：`py scripts/refresh_investment_stocks.py --source auto|akshare|tushare`
- 定时任务日志建议使用 JSON：`py scripts/refresh_investment_stocks.py --source auto --json`
- Windows Task Scheduler 建议每天 08:30 执行，操作为：
  - Program/script: `py`
  - Add arguments: `scripts/refresh_investment_stocks.py --source auto --json`
  - Start in: 仓库根目录，例如 `C:\Users\Administrator\Documents\GitHub\CowAgent`
- 命令行创建示例：
  `schtasks /Create /SC DAILY /ST 08:30 /TN "CowAgent Investment Stock Refresh" /TR "py scripts\refresh_investment_stocks.py --source auto --json" /F`

### Subagent 4: Web API and UI

**Owned files:** `channel/web/web_channel.py`, `channel/web/static/js/console.js`, `tests/test_investment_business.py`

**Requirements:**
- 新增 Web API：
  - `POST /api/investment/stocks/refresh`
    - body: `{"source": "auto" | "akshare" | "tushare"}`
    - 返回：`{"status":"success","result":...}`
  - `GET /api/investment/stocks?name=新易盛&limit=20`
    - 返回：`{"status":"success","stocks":[...],"stats":...}`
- 投资系统配置页增加：
  - `tushare.token` 配置项，脱敏展示。
  - 股票字典状态：数量、最近更新时间、最近来源。
  - 刷新按钮：auto / AKShare / Tushare。
  - 查询框：输入中文名后展示匹配代码。
- API 和 UI 不明文展示 token。

**Tests:**
- GET stocks 返回本地匹配和 stats。
- POST refresh 调用指定 source 并返回成功 payload。
- config API 读取 `tushare.token` 为脱敏值。
- `node --check channel/web/static/js/console.js` 通过。

### Subagent 5: Auto Refresh on Miss and Health

**Owned files:** `business/investment/stock_resolver.py`, `business/investment/health.py`, `channel/web/static/js/console.js`, `tests/test_investment_business.py`

**Requirements:**
- 中文名本地未命中时，如果 `auto_refresh_on_miss=True`：
  - 同步调用 `refresh_from_auto()` 一次。
  - 再查本地字典。
  - 仍未命中返回 `STOCK_NOT_FOUND`。
  - 刷新异常只进入 detail/log，不让异常穿透到用户侧。
- 数字代码不触发刷新。
- 健康检查增加 `stock_dictionary`：
  - 表存在。
  - row_count。
  - latest_updated_at。
  - latest_source。
  - tushare_token_configured。
  - row_count 为 0 时 `ok=False`。
- Web 健康页面展示新增 health item。
- 历史 `generating` 悬挂记录只展示当前状态，不参与 resolver 成败判断。

**Tests:**
- 未命中中文名触发一次 refresh，并在刷新后命中。
- refresh 失败后仍返回 `STOCK_NOT_FOUND`，不抛异常。
- 数字代码不触发 refresh。
- health 在字典为空时失败，刷新后通过。

### Subagent 6: Final Integration and E2E

**Owned files:** integration-only unless a defect is found; if defects are found, return to owning subagent block for fix.

**Requirements:**
- 执行完整质量门禁：
  - `py -m pytest`
  - `py -m mypy business tests`
  - `py -m ruff check .`
  - `node --check channel/web/static/js/console.js`
- 用真实 AKShare 执行一次刷新：
  - `py scripts/refresh_investment_stocks.py --source akshare --json`
  - 验证 row_count > 0。
- 验证业务场景：
  - `新易盛 技术分析` 可以返回信号卡和主图。
  - `贵州茅台 技术分析` 可以完成股票名解析；若行情/模型失败，必须记录真实失败 detail，不能误报解析失败。
  - 未知股票名返回指定业务提示。
  - 构造重名记录后返回歧义提示。
  - `300502 技术分析` 仍可直接运行。
- 更新计划文件中的执行结果摘要。

---

## Review Rules

- 每个子agent必须先写失败测试，再写实现。
- 每个子agent返回后，主会话检查：
  - 规格符合性：是否满足本块所有 Requirements。
  - 代码质量：是否保持现有风格、无敏感信息泄漏、无不必要重构。
- 不允许多个实现子agent并行写同一文件。
- 子agent不能回滚其他人已做的改动。
- 若某块发现前一块缺陷，回到原 owning block 修复后再继续。

## Final Acceptance

- 中文股票名不再依赖静态小表。
- AKShare 可刷新本地股票字典且不需要 token。
- Tushare token 可在 Web 后台配置并脱敏展示。
- 中文名未命中时会刷新一次字典再判断。
- 数字代码路径不受字典刷新失败影响。
- Web 后台可刷新、查询、查看字典健康状态。
- 完整质量门禁通过。

## Subagent 6 Execution Summary

- 质量门禁（2026-05-25）：`py -m pytest` 113 passed；`py -m mypy business tests` passed；`py -m ruff check .` passed；`node --check channel/web/static/js/console.js` passed。
- 真实 AKShare 刷新：`py scripts/refresh_investment_stocks.py --source akshare --json` 成功，写入 5522 条，DB 为 `C:\Users\Administrator\Documents\GitHub\CowAgent\investment\investment.db`。
- 本地 resolver 验证：`新易盛 -> 300502.SZ`，`贵州茅台 -> 600519.SH`，`未知股票名 -> stock_not_found`，`300502 -> 300502.SZ`，`600519 -> 600519.SH`，`300502.SZ -> 300502.SZ`。
- 歧义验证使用临时 DB，不污染主库：两条 `重名测试` 返回 `stock_ambiguous`。
- 健康检查抽查：股票字典表存在，数量 5522，最近来源 `akshare`；当前环境未配置 Tushare token，`tushare_token` health item 为 `unconfigured`。
