# 记录系统精简表名与字段计划

> 本计划以“记录可复盘、表结构清晰、迁移可回滚”为目标。第一阶段只执行物理表名去 `investment_` 前缀，保持字段和业务行为不变；字段精简在第二阶段单独迁移。

## 当前数据库

业务库默认连接 `cowagent_investment`。连接优先级：

1. 环境变量 `COWAGENT_INVESTMENT_DATABASE_URL`
2. `config.json` 的 `investment_database_url`
3. 默认 `postgresql+psycopg://cowagent:cowagent@127.0.0.1:55432/cowagent_investment`

后台看到的 `cowagent_test_*` 是测试 schema，不是业务库。测试异常中断时可能残留，可在确认没有测试运行后清理。

## 目标表名

| 当前表名 | 第一阶段目标表名 | 职责 |
| --- | --- | --- |
| `investment_users` | `customers` | 公众号客户与权限 |
| `investment_admin_users` | `admins` | 后台人员 |
| `investment_admin_sessions` | `admin_sessions` | 后台登录会话 |
| `investment_request_records` | `request_records` | 公众号请求主记录 |
| `investment_daily_contents` | `content_records` | 利率/转债内容版本 |
| `investment_output_files` | `artifacts` | 输入、输出、中间产物文件 |
| `investment_cache_entries` | `cache_entries` | 技术分析和内容产物缓存 |
| `investment_configs` | `configs` | 运行配置 |
| `investment_operation_audits` | `operation_audits` | 后台操作流水 |
| `investment_stock_symbols` | `stock_symbols` | 股票字典 |

## 目标字段名

第二阶段再做字段精简，避免和表重命名混在同一批风险过大。

| 当前字段 | 目标字段 | 适用表 |
| --- | --- | --- |
| `service_type` | `service` | `request_records`, `content_records`, `cache_entries`, `artifacts` |
| `output_files` | `outputs` | `request_records`, `cache_entries` |
| `source_files` | `sources` | `content_records` |
| `source_text` | `input_text` | `content_records` |
| `generated_text` | `output_text` | `content_records` |
| `output_image` | `output_image_path` | `content_records` |
| `created_by_admin_id` | `created_by_id` | `customers`, `content_records` |
| `created_by_username` | `created_by` | `customers`, `content_records` |
| `updated_by_admin_id` | `updated_by_id` | `customers`, `configs`, `content_records` |
| `updated_by_username` | `updated_by` | `customers`, `configs`, `content_records` |
| `published_by_admin_id` | `published_by_id` | `content_records` |
| `published_by_username` | `published_by` | `content_records` |
| `operator_admin_id` | `operator_id` | `operation_audits` |
| `operator_username` | `operator_name` | `operation_audits` |
| `operator_role` | `operator_role` | 保留 |
| `operation_category` | `category` | `operation_audits` |
| `result_status` | `result` | `operation_audits` |
| `error_message` | `error` | `request_records`, `content_records`, `operation_audits` |

## 记录系统新增表

### `request_events`

用于把公众号多轮流程归并到同一个 `request_id`。

字段建议：

`event_id, request_id, openid, channel, event_type, message_type, content, media_id, file_path, source_type, source_id, result, error, created_at`

事件类型：

`request_received, permission_denied, generation_started, generation_success, generation_failed, pending_prompt_sent, customer_confirm, customer_cancel, customer_other_reply, reply_text_sent, reply_image_sent, delivery_success, delivery_failed, cache_hit, cache_invalidated`

### `generation_records`

用于记录后台人员每一次调用利率/转债生成服务。

字段建议：

`generation_id, content_id, service, operator_id, operator_name, operator_role, input_text, sources, result, error_code, error, output_text, outputs, elapsed_ms, created_at, updated_at`

## 操作流水分类

`operation_audits.category` 固定为：

`customer, admin, skill, content, generation, config, cache, stock, export, health, system`

配置和 skill 修改必须记录脱敏后的 `before_state` 和 `after_state`。

## 第一阶段执行内容

1. 修改 SQLAlchemy metadata 的物理表名和索引名。
2. 保留现有 Python 变量名作为兼容别名，降低改动面。
3. 增加 Alembic 迁移，把旧表 rename 到新表。
4. 更新表名相关测试断言。
5. 跑 schema 与核心业务测试，确认行为不变。

## 第二阶段执行内容

1. 新增 `request_events`。
2. 接入公众号请求、等待、确认、取消、图片返回、交付失败事件。
3. 新增 `generation_records`。
4. 接入后台利率/转债生成接口。
5. 给配置和 skill 审计补 `before_state` / `after_state`。
6. 做字段精简迁移，并同步导出、Web API、测试。
