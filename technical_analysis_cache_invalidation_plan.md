# 技术分析收盘后缓存软失效实施计划

## 目标

技术分析用户侧继续保持“股票 + 技术分析”即可使用；系统内部仍使用最新行情日期做缓存边界。新增北京时间 A 股交易时段后的缓存软失效机制，避免当天盘中生成的技术分析缓存，在收盘后继续被命中。

## 设计口径

- 用户不需要输入行情日期。
- 行情日期仍是系统内部字段，用于缓存、记录、导出和追溯。
- 最新数据仍以行情源返回的最新日线日期为准。
- 不强制要求数据源闭盘立刻有新数据。
- 默认按北京时间 `15:30` 作为技术分析缓存软失效检查点。
- 只处理技术分析缓存，不影响利率、转债、后台上传内容。
- 不改核心缓存写入/命中函数：
  - `find_cache_entry*`
  - `increment_cache_hit`
  - `write_cache_entry`
- 在技术分析业务层判断缓存是否还能使用；需要失效时调用独立封装，不把交易时间逻辑塞进通用缓存服务。

## 缓存失效规则

1. 当前时间使用 `Asia/Shanghai`。
2. 如果当前北京时间早于 `15:30`，正常使用缓存。
3. 如果当前北京时间大于等于 `15:30`：
   - 仅检查 `service_type = technical_analysis` 的缓存。
   - 如果缓存的 `market_date` 等于北京时间当天日期；
   - 且缓存创建/更新时间早于当天 `15:30`；
   - 则标记为失效，下一次用户查询重新走行情源和分析流程。
4. 如果行情源收盘后仍只返回上一个交易日，则继续按上一个交易日缓存工作，不强行用自然日生成缓存。
5. 周末和节假日不单独判断交易日历，避免过度严格。

## 子任务分配

### Agent 1：交易时段策略与单元测试

负责文件：

- `business/investment/market_session.py` 或 `business/investment/cache_policy.py`
- `tests/test_investment_business.py`

任务：

- 新增北京时间工具函数。
- 定义默认收盘后软失效时间：`15:30`。
- 提供函数，例如：
  - `beijing_now()`
  - `technical_analysis_cache_expired_after_close(market_date, updated_at, now=None)`
- 写单测覆盖：
  - `15:29` 不失效。
  - `15:30` 后，当日且早于 cutoff 的缓存失效。
  - 非当日 `market_date` 不失效。
  - 当日但 cutoff 后新写入缓存不失效。
  - UTC/本地时区混用时按北京时间判断。

### Agent 2：技术分析缓存读取链路接入

负责文件：

- `business/investment/technical_analysis.py`
- 必要时少量修改 `business/investment/cache_service.py`

任务：

- 在技术分析业务层拿到缓存后，先经过 Agent 1 的策略判断。
- 如果缓存应失效：
  - 标记该缓存 inactive 或调用现有失效封装；
  - 本次按缓存未命中继续生成。
- 不能修改通用缓存命中、写入、hit_count 增加逻辑。
- 确认兼容缓存分支也经过同样判断。
- 写测试覆盖：
  - 盘中缓存命中。
  - 收盘后盘中当日缓存不命中并重跑。
  - 收盘后上一交易日缓存仍可命中。
  - 文件缺失失效逻辑仍然正常。

### Agent 3：配置与可维护性

负责文件：

- `config-template.json`
- `config.py` 或现有配置读取位置
- `doc` 或 `docs` 中对应运维说明

任务：

- 增加可配置项，默认值为 `15:30`，例如：
  - `investment.technical_analysis.cache_close_invalidate_time`
- 如果配置缺失，使用默认值。
- 配置非法时回退默认值，不影响用户查询。
- 写测试覆盖配置缺失、合法、非法三种情况。
- 文档说明：
  - 这是北京时间。
  - 不是交易日历校验。
  - 数据源延迟时不会强制切换自然日。

### Agent 4：公众号链路与回归测试

负责文件：

- `channel/wechatmp/passive_reply.py`
- `channel/wechatmp/wechatmp_channel.py`
- `tests/test_wechatmp_investment_reply.py`

任务：

- 确认公众号用户侧文案不引导用户输入行情日期。
- 确认仍返回两个图：信号卡 + 技术分析主图。
- 确认 Markdown 报告继续只做后台留存。
- 回归测试：
  - 权限正常用户技术分析请求。
  - 缓存命中后用户回复 `1` 拉图。
  - 收盘后缓存失效重跑时仍返回“正在运行”。
  - 无权限请求仍记录为 `unauthorized_request`。

### Agent 5：最终集成审查

任务：

- 检查是否误改了禁止触碰的核心函数：
  - `find_cache_entry*`
  - `increment_cache_hit`
  - `write_cache_entry`
- 检查权限点未变：
  - `records.read`
  - `records.export`
  - `cache.read`
  - `cache.write`
- 检查导出不受分页影响。
- 跑测试：
  - `py -m pytest tests\test_investment_business.py -k "technical_analysis and cache" -q`
  - `py -m pytest tests\test_wechatmp_investment_reply.py -k "technical_analysis or permission or passive" -q`
- 如有必要再跑业务记录相关测试。

## 新对话提示词

```text
仓库：C:\Users\Administrator\Documents\GitHub\CowAgent

请继续实现“技术分析收盘后缓存软失效”修改。

计划文件：
C:\Users\Administrator\Documents\GitHub\CowAgent\technical_analysis_cache_invalidation_plan.md

请先读取并严格按照这个计划文件执行，必要时只做同目标下的小幅调整。

业务背景：
- 用户在公众号输入“股票代码/股票名称 + 技术分析”。
- 用户不需要输入行情日期。
- 系统内部使用行情源返回的最新日线日期作为 market_date，用于缓存、记录、导出和追溯。
- 用户侧技术分析最终只返回两个图：信号卡片 PNG + 技术分析主图。
- Markdown 报告只做后台留存，不返回给用户。

本次目标：
- 按北京时间处理 A 股收盘后的技术分析缓存软失效。
- 默认在北京时间 15:30 后检查并失效“当天 market_date 且在 15:30 前生成/更新”的 technical_analysis 缓存。
- 不要过度严格，不要强制交易日历校验；数据源收盘后未更新时，继续以行情源实际返回的最新交易日为准。
- 周末/节假日不要按自然日强制失效。
- 只影响 technical_analysis 缓存，不影响利率、转债、后台上传内容。

必须注意：
- 不要改缓存核心逻辑：
  - find_cache_entry*
  - increment_cache_hit
  - write_cache_entry
- 不要改权限点：
  - records.read
  - records.export
  - cache.read/cache.write
- 不要改导出分页逻辑。
- 当前工作区可能有未提交改动，不要 git reset，不要 revert 用户改动。

建议使用子 agent 分工：
1. Agent 1：新增北京时间/A股收盘后缓存策略模块和单元测试。
2. Agent 2：把策略接入 business/investment/technical_analysis.py 的缓存读取链路。
3. Agent 3：增加可配置项，默认 15:30，并补文档。
4. Agent 4：回归公众号用户侧链路，确认仍返回两个图，MD 只留存。
5. Agent 5：最终审查禁止改动项、权限点、导出逻辑，并跑测试。

重点文件：
- business/investment/technical_analysis.py
- business/investment/cache_service.py
- business/investment/market_date_resolver.py
- business/investment/records.py
- channel/wechatmp/passive_reply.py
- channel/wechatmp/wechatmp_channel.py
- tests/test_investment_business.py
- tests/test_wechatmp_investment_reply.py
- config-template.json
- config.py

验证命令：
- py -m pytest tests\test_investment_business.py -k "technical_analysis and cache" -q
- py -m pytest tests\test_wechatmp_investment_reply.py -k "technical_analysis or permission or passive" -q

请先读取现有代码和最近提交，制定任务清单，然后按子 agent 分块实施、测试、提交。
```
