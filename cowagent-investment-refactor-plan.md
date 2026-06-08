# CowAgent 投研旁路逻辑回收改造计划

> **目标**：不再把 investment 作为一套新增业务系统挂在 CowAgent 外侧，而是把投研识别、AI 调用、渲染、缓存、配置、权限、记录、公众号回复等能力回收到 CowAgent 原有主链路中，完成对 CowAgent 的彻底业务化改造。

## 一、当前问题

当前投研能力主要集中在 `business/investment`，并在公众号、Web、测试中被直接调用。这形成了一条绕开 CowAgent 原有 `Channel -> Bridge -> Bot/Agent -> Reply` 主流程的旁路。

典型旁路包括：

- `business/investment/ai_generation.py` 自己封装 AI prompt、messages、图片 OCR、重试和模型配置解析。
- `business/investment/router.py` 自己完成业务识别、权限、请求记录、任务去重、缓存写入和回复组装。
- `channel/wechatmp/wechatmp_channel.py` 直接 import `business.investment.message_handler`。
- `channel/wechatmp/passive_reply.py`、`active_reply.py` 直接 import `business.investment.router`、`constants`、`records`、`user_service`。
- `channel/web/web_channel.py` 中包含大量 investment 专属后台接口和页面逻辑。
- `business/investment/cache_service.py`、`config_service.py`、`reply_config.py` 形成独立缓存、配置和文案体系。

改造方向不是继续新增业务层，而是把这些逻辑合并回 CowAgent 原有主链路。

## 二、目标架构

改造后的消息链路：

```text
用户消息
  -> Channel 统一构造 Context
  -> ChatChannel._generate_reply()
  -> Channel.build_reply_content()
  -> Bridge / Agent / Business Intent Router
  -> CowAgent 内置业务处理器
      -> 权限校验
      -> 业务执行：技术分析 / 利率 / 转债
      -> 统一模型调用
      -> 统一渲染
      -> 统一缓存和记录
  -> Reply(TEXT / IMAGE / FILE)
  -> Channel 发送
```

核心原则：

- Channel 只处理渠道协议，不直接 import 投研业务。
- AI 调用统一走 CowAgent `models` / `Bot` / `call_with_tools` 能力。
- 投研业务识别进入 CowAgent 主消息处理链，不再由 investment router 独立处理。
- 技术分析、利率、转债作为 CowAgent 内置业务能力，而不是外挂业务包。
- 配置、缓存、记录、健康检查统一纳入 CowAgent 原有体系。

## 三、需要回收的旁路逻辑

### 1. AI 调用旁路

当前文件：

- `business/investment/ai_generation.py`

当前问题：

- 自己读取模型配置。
- 自己构造 OpenAI-compatible messages。
- 自己处理图片 base64。
- 自己做 transient retry。
- 直接调用 `models.openai.openai_http_client.get_default_client().chat_completions()`。

改造目标：

- 删除 investment 专属模型适配器。
- 把标准投研文本生成迁入 CowAgent 模型层或业务 handler。
- 技术分析、利率、转债都通过统一非会话模型调用接口生成文本。
- 优先复用现有 Bot 的 `call_with_tools(messages, stream=False, **kwargs)`。

### 2. 业务入口旁路

当前文件：

- `business/investment/router.py`
- `business/investment/message_handler.py`

当前问题：

- investment router 是投研业务总入口，绕开 CowAgent 的主回复构建流程。
- 公众号和 Web 直接调用 investment router。

改造目标：

- 将 `parse_route()` 迁入 CowAgent 主消息链中的业务意图识别。
- 将 `handle_text_message()` 的编排逻辑迁入 CowAgent business handler。
- 删除 channel 对 `business.investment.router/message_handler` 的直接依赖。

### 3. 业务注册旁路

当前文件：

- `business/investment/business_registry.py`
- `business/investment/business_definitions.py`
- `business/investment/skill_registry.py`
- `business/investment/skill_runner.py`
- `business/investment/skill_versions.py`

当前问题：

- 投研业务维护了单独的 Skill 定义、触发词、启停、版本和运行体系。

改造目标：

- 技术分析、利率、转债注册到 CowAgent 原有 Skill/Tool/Plugin 体系。
- 触发词配置进入 CowAgent 配置体系。
- `signal-card-renderer` 作为 CowAgent 内部渲染工具，而不是 investment 专属 Skill。

### 4. 技术分析业务旁路

当前文件：

- `business/investment/technical_analysis.py`
- `business/investment/stock_resolver.py`
- `business/investment/market_date_resolver.py`
- `business/investment/executors/technical_analysis_executor.py`

当前问题：

- 技术分析自己完成标的解析、交易日解析、脚本执行、AI 整理、渲染、缓存。
- 入口由 investment router 管理。

改造目标：

- 技术分析成为 CowAgent 内置业务 handler。
- AI 整理走统一模型调用。
- 渲染走 CowAgent 渲染工具。
- 结果通过统一 `Reply` 和文件产物机制返回。

### 5. 内容型业务旁路

当前文件：

- `business/investment/daily_content.py`
- `business/investment/executors/daily_content_executor.py`

当前问题：

- 利率/转债的草稿、源文件、生成、生效、过期和读取当前生效内容都在 investment 内部。

改造目标：

- 将利率/转债改为 CowAgent 内容型业务。
- 内容生成走统一模型调用。
- 内容发布、生效、过期纳入 CowAgent 管理台和记录体系。

### 6. 渲染旁路

当前文件：

- `business/investment/render_service.py`

当前问题：

- investment 单独调用 `skills/signal-card-renderer/scripts/render_card.py`。

改造目标：

- 渲染能力迁为 CowAgent 内置工具或 Skill。
- 投研业务只调用统一渲染接口，不直接维护 investment render service。

### 7. 缓存和记录旁路

当前文件：

- `business/investment/cache_service.py`
- `business/investment/business_cache.py`
- `business/investment/cache_policy.py`
- `business/investment/records.py`
- `business/investment/business_records.py`
- `business/investment/job_service.py`

当前问题：

- 业务缓存、请求记录、产物记录、任务去重都在 investment 内部。

改造目标：

- 缓存改为 CowAgent 通用业务结果缓存。
- 请求记录改为 CowAgent 通用业务记录。
- `investment_request_id`、`investment_service_type` 等字段迁为 `business_request_id`、`business_service_type`。
- 任务去重接入 CowAgent 通用任务/会话控制。

### 8. 配置和回复文案旁路

当前文件：

- `business/investment/config_service.py`
- `business/investment/reply_config.py`
- `business/investment/constants.py`

当前问题：

- investment 单独维护配置读写、敏感字段脱敏、回复文案 fallback。

改造目标：

- 统一使用 CowAgent `config.py` / `conf()` / Web 配置管理。
- 回复文案进入 CowAgent 通用配置。
- 错误码和服务类型迁入通用业务枚举。

### 9. 健康检查旁路

当前文件：

- `business/investment/health.py`

当前问题：

- investment 单独做模型、依赖、字体、股票字典、渲染、技术分析 smoke check。

改造目标：

- 合并进 CowAgent 管理台健康检查。
- 投研检查作为 CowAgent health 子项。

### 10. 渠道层 investment 依赖

当前文件：

- `channel/wechatmp/wechatmp_channel.py`
- `channel/wechatmp/passive_reply.py`
- `channel/wechatmp/active_reply.py`
- `channel/web/web_channel.py`

当前问题：

- 渠道层直接 import investment。
- 公众号层承担业务识别、权限预检、运行中判断、业务回复文案。

改造目标：

- 渠道层只处理协议、被动回复缓存、媒体上传。
- 业务判断、权限、任务状态全部交给 CowAgent 主业务层。

## 四、分阶段执行计划

### 阶段 0：建立基线和迁移清单

目标：确保现有行为可测试、可回退。

步骤：

1. 运行当前测试：

```powershell
pytest tests/test_investment_business.py -q
pytest tests/test_wechatmp_investment_reply.py -q
pytest tests/test_wechatmp_chain_check.py -q
pytest tests/test_web_model_config_sync.py -q
```

2. 搜索所有 investment 入口：

```powershell
rg -n "business\.investment|handle_text_message|parse_route|investment_request_id|investment_service_type" .
```

3. 建立迁移对照：

| 当前 investment 能力 | 目标 CowAgent 位置 |
| --- | --- |
| `router.parse_route` | CowAgent 主业务意图识别 |
| `router.handle_text_message` | CowAgent business handler |
| `ai_generation.generate_standard_text` | CowAgent 统一模型调用 |
| `render_service.render_card` | CowAgent 渲染工具 |
| `cache_service` | CowAgent 通用业务缓存 |
| `records` | CowAgent 通用业务记录 |
| `reply_config` | CowAgent 通用回复文案配置 |
| `health.run_health_checks` | CowAgent 管理台健康检查 |

完成标准：

- 当前测试结果已记录。
- 所有 `business.investment` 调用点已列出。
- 后续每阶段只迁一类能力。

### 阶段 1：统一 AI 调用

目标：消灭 investment 独立模型适配器。

步骤：

1. 在 CowAgent 模型层确认统一调用接口。

优先使用：

- `Bridge().get_bot("chat")`
- Bot 的 `call_with_tools(messages, tools=None, stream=False, **kwargs)`

2. 把 `ai_generation.py` 中这些逻辑迁出：

- `AIGenerationRequest`
- `AIGenerationResult`
- `ExistingModelAdapter`
- `BridgeModelAdapter`
- `_global_model_config`
- `generate_standard_text`
- `generate_technical_analysis_text`
- `generate_rate_text`
- `generate_convertible_bond_text`

3. 将 prompt 和文本标准化保留为业务 prompt/formatter，不再负责 HTTP 调用。

4. 修改技术分析和 daily content 调用点，让它们调用 CowAgent 统一模型接口。

当前调用点：

- `business/investment/technical_analysis.py`
- `business/investment/daily_content.py`

完成标准：

- `business/investment/ai_generation.py` 不再直接调用 `get_default_client().chat_completions()`。
- 技术分析、利率、转债生成仍可用。
- 模型配置仍从 CowAgent 全局配置读取。

### 阶段 2：统一业务路由入口

目标：删除 channel 到 investment router 的直接调用。

步骤：

1. 在 CowAgent 主消息链加入业务意图识别。

主链路位置：

- `channel/chat_channel.py`
- `channel/channel.py`
- `bridge/bridge.py`

2. 把 `business/investment/router.py::parse_route()` 迁入 CowAgent 主业务识别。

3. 把 `business/investment/router.py::handle_text_message()` 拆成通用 business handler。

4. 修改 `WechatMPChannel._generate_reply()`：

当前：

```python
from business.investment.message_handler import handle_inbound_message
business_reply = handle_inbound_message(openid, context.content)
```

目标：

```python
return super()._generate_reply(context, reply)
```

业务处理由 CowAgent 主链完成。

完成标准：

- `channel/wechatmp/wechatmp_channel.py` 不再 import `business.investment.message_handler`。
- 普通聊天继续走原 CowAgent 聊天。
- “利率”“转债”“300502.SZ 技术分析”仍能返回业务结果。

### 阶段 3：统一业务和 Skill 注册

目标：删除 investment 专属业务注册体系。

步骤：

1. 将内置业务注册到 CowAgent 原有 Skill/Tool/Plugin 体系。

业务项：

- 技术分析
- 利率
- 转债
- 图片渲染工具

2. 迁移触发词配置。

当前配置：

- `skill.technical-analysis.triggers`
- `skill.rate.triggers`
- `skill.convertible-bond.triggers`

目标：

- 使用 CowAgent 通用业务配置或技能配置。

3. 替换调用点：

- `business_registry.match_business`
- `skill_registry.match_investment_skill`
- `router.parse_route`

完成标准：

- 业务匹配不依赖 `business/investment/skill_registry.py`。
- 启用、禁用、触发词修改仍可用。
- 上传 Skill 版本逻辑迁入 CowAgent 管理能力或明确废弃。

### 阶段 4：回收技术分析流程

目标：技术分析成为 CowAgent 内置业务。

步骤：

1. 保留技术分析核心算法和脚本调用，但移除 investment 入口身份。

核心能力：

- 股票解析
- 交易日解析
- 技术分析脚本执行
- Markdown 报告读取
- AI 标准卡片文本生成
- 信号卡渲染
- 主图和报告产物记录

2. 把 `technical_analysis.py` 中缓存上下文、业务结果、错误码改成通用 business 类型。

3. 把技术分析结果返回统一 `Reply`：

- 图片结果：`ReplyType.IMAGE_URL`
- 文本失败：`ReplyType.TEXT`
- 产物 metadata：通用 business metadata

完成标准：

- 技术分析从所有渠道都经 CowAgent 主链路触发。
- 不再由 investment router 调用。
- 缓存命中、生成失败、股票未找到、图片渲染失败等行为保持。

### 阶段 5：回收利率/转债内容流程

目标：利率和转债成为 CowAgent 内容型业务。

步骤：

1. 将 `daily_content.py` 的内容生命周期迁入 CowAgent 管理能力：

- 草稿
- 源文件
- AI 生成
- 生成失败
- 生效
- 过期
- 当前生效内容读取

2. 生成过程改用统一模型调用。

3. 渲染过程改用统一渲染工具。

4. 查询“利率”“转债”时，从 CowAgent 内容管理读取当前生效内容。

完成标准：

- 后台仍可上传资料、生成图片、设置生效。
- 用户仍可通过关键词取当前图片。
- 不再由 `business/investment/daily_content.py` 作为独立业务服务对外暴露。

### 阶段 6：统一缓存、记录和任务

目标：删除 investment 独立缓存和请求记录体系。

步骤：

1. 将 `cache_service.py` 能力迁为通用业务缓存：

- `build_cache_key`
- `version_fingerprint`
- `find_cache_entry`
- `find_latest_cache_entry`
- `write_cache_entry`
- `invalidate_cache_entry`
- `list_generated_history_page`

2. 将 `records.py` / `business_records.py` 迁为通用业务记录：

- 请求创建
- 成功/失败标记
- 输出文件记录
- 投递 warning
- 分页查询

3. 将 `job_service.py` 迁为通用业务任务去重：

- 同一用户同一业务同一 cache key 只跑一个任务。
- 未完成时返回运行中提示。

4. 替换 metadata 命名：

当前：

- `investment_request_id`
- `investment_service_type`
- `investment_source_type`
- `investment_source_id`

目标：

- `business_request_id`
- `business_service_type`
- `business_source_type`
- `business_source_id`

完成标准：

- 公众号被动回复缓存仍能按业务结果取图。
- 技术分析重复请求仍提示运行中。
- 业务历史和缓存历史仍可查。

### 阶段 7：统一配置和回复文案

目标：删除 investment 配置孤岛。

步骤：

1. 将 `config_service.py` 的能力并入 CowAgent 配置管理：

- 读取配置
- 保存配置
- 批量保存
- 敏感字段脱敏
- 权限限制

2. 将 `reply_config.py` 的文案并入 CowAgent 通用回复配置。

3. 将 `constants.py` 中通用业务枚举迁出：

- 服务类型
- 状态
- 错误码
- 用户错误提示

完成标准：

- Web 修改 prompt、模型、回复文案时，只写 CowAgent 一套配置。
- 不再出现“全局模型配置”和“investment 模型配置”两套别名。
- 测试中不再需要 `business.investment.config_service`。

### 阶段 8：回收公众号主动/被动回复逻辑

目标：公众号模块不再承担投研业务判断。

步骤：

1. 修改 `channel/wechatmp/passive_reply.py`：

迁出或删除：

- `_investment_route`
- `_is_investment_command`
- `_investment_ack_text`
- `_investment_permission_prompt`
- `_investment_user_access_prompt`
- `_cached_investment_permission_prompt`

2. 修改 `channel/wechatmp/active_reply.py`：

迁出或删除：

- `_running_investment_job`
- `_investment_permission_prompt`
- investment route precheck

3. 保留公众号协议能力：

- 被动回复 5 秒限制。
- 回复“1”取图。
- media cache。
- 图片上传。
- 微信错误处理。

完成标准：

- `channel/wechatmp` 不再 import `business.investment`。
- 公众号业务提示由 CowAgent 主业务层生成。
- 被动回复缓存行为保持。

### 阶段 9：回收 Web 管理台

目标：Web 页面不再是 investment 专区。

步骤：

1. 将 investment 管理接口迁成 CowAgent 通用业务接口。

包含：

- 用户权限
- 业务记录
- 缓存管理
- 内容管理
- Skill 版本
- 配置
- 健康检查

2. 替换前端命名：

当前：

- `investment-*`
- `investment_config`
- `investment_content`
- `investment_records`

目标：

- `business-*`
- `business_config`
- `business_content`
- `business_records`

3. 旧 API 可短期保留兼容转发，最终删除。

完成标准：

- Web 管理台功能保持。
- 前端和后端接口不再大量出现 investment 专属命名。
- 普通聊天、业务查询、配置管理都走 CowAgent 主体系。

### 阶段 10：删除 investment 旁路包

目标：完成彻底回收。

可删除或改为空兼容的文件：

- `business/investment/ai_generation.py`
- `business/investment/router.py`
- `business/investment/message_handler.py`
- `business/investment/business_registry.py`
- `business/investment/business_definitions.py`
- `business/investment/business_cache.py`
- `business/investment/config_service.py`
- `business/investment/reply_config.py`
- 已迁移完成的 `skill_*` facade
- 已迁移完成的 `executors/*`

谨慎处理：

- 数据库 schema 和 migrations 可先保留，后续单独做数据表重命名或兼容视图。
- 技术分析脚本和 `signal-card-renderer` 可继续保留在 `skills/`，但不再作为 investment 旁路服务。

完成标准：

- `rg -n "business\.investment" channel bridge models agent` 没有业务调用。
- `rg -n "investment_request_id|investment_service_type"` 没有运行时依赖。
- 所有业务入口经 CowAgent 主链路。

## 五、推荐执行顺序

按以下顺序执行，避免一次性替换导致公众号不可用：

1. 阶段 0：建立基线。
2. 阶段 1：统一 AI 调用。
3. 阶段 2：统一业务路由入口。
4. 阶段 3：统一业务和 Skill 注册。
5. 阶段 4：回收技术分析。
6. 阶段 5：回收利率/转债。
7. 阶段 6：统一缓存、记录和任务。
8. 阶段 7：统一配置和文案。
9. 阶段 8：回收公众号主动/被动回复。
10. 阶段 9：回收 Web 管理台。
11. 阶段 10：删除 investment 旁路包。

## 六、风险点

- 公众号被动回复有 5 秒限制，技术分析不能简单同步阻塞。
- 技术分析已有缓存命中和任务去重，迁移时不能丢。
- 当前测试大量直接 import `business.investment.*`，迁移阶段要同步改测试。
- Web 管理台 investment 逻辑很多，建议最后迁。
- 不建议把所有逻辑硬塞进一个旧文件；目标是回到 CowAgent 原架构，而不是制造新的巨型文件。

## 七、最终验收标准

最终应满足：

- `channel/*` 不再直接 import `business.investment`。
- AI 生成不再由 `business/investment/ai_generation.py` 独立调用模型。
- 投研业务不再由 `business/investment/router.py` 作为总入口。
- 技术分析、利率、转债从 CowAgent 原消息链路触发。
- AI 调用统一走 CowAgent Bot/model 层。
- 回复统一使用 CowAgent `Reply`。
- 配置统一走 CowAgent 配置管理。
- 缓存和记录使用通用 business metadata。
- Web 管理台不再使用 investment 专属命名。
- 旧 investment 模块只剩数据迁移兼容，或完全删除。

## 八、新对话执行提示词

可以在新对话中直接使用：

```text
请按根目录 cowagent-investment-refactor-plan.md 执行改造。
先从阶段 0 建立基线开始，然后进入阶段 1 统一 AI 调用。
每个阶段完成后先运行相关测试并汇报，不要一次性跨多个阶段修改。
目标是不再新增旁路系统，而是把 investment 逻辑回收到 CowAgent 原有主链路。
```
