# New Conversation Prompt: Products-As-Cache Subagent Execution

请使用 Subagent-Driven 执行计划：

`docs/superpowers/plans/2026-06-25-products-as-cache-and-schema-simplification.md`

目标：

- 让 `products` 承担当前 `cache_entries` 的运行时缓存职责。
- 新生成的可复用产物不再写入 `cache_entries`。
- 技术分析缓存命中、兼容缓存、命中次数、失效逻辑都改为基于 `products`。
- 历史展示继续只使用产品/产物模型，不回退到旧 cache/content 展示逻辑。
- 旧 `cache_entries` 数据必须先回填/保护到 `products`，确认无运行时依赖后再删除表。
- 不删除业务记录、产物、历史归档、生成结果或物理文件。
- 判断并记录字段精简策略：本轮优先删除 `cache_entries`，不要冒险把 `source_request_id/source_content_id/source_cache_key` 合并成单字段，除非计划中的测试和 review 都证明低风险。

执行要求：

- 严格按计划 task-by-task。
- 每个任务先写失败测试，再实现，再验证，再提交。
- 每个任务完成后做两轮 review：
  1. spec compliance review：是否满足计划和用户目标。
  2. code quality review：是否有 Critical/Important 问题。
- 修复 Critical/Important 问题后才能继续下一个任务。
- 每个任务一个 commit，不要把多个任务混在一个 commit。
- 不要删除业务记录、产物、历史归档或生成结果。
- 如果发现计划中某一步会导致数据丢失、UI 回退到旧逻辑、或者破坏组件产物查看，停止并先修正计划/实现。

当前关键上下文：

- 当前分支：`codex/unified-business-products`
- 之前已经完成过产品化历史展示工作，相关提交包括 `8474512e Unify archived artifacts with product history`
- `products` 已经用于历史产物展示和组件产物展示。
- `cache_entries` 仍在缓存服务和技术分析路径中存在运行时依赖。
- 目标不是简单打补丁，而是把缓存职责正确迁移到产品模型，并安全移除遗留表。

完成后请运行：

```powershell
pytest tests/test_business.py -k "product or cache or artifact_package or artifact_folder or technical_analysis" -q
pytest tests/test_business_web_ui.py -q
node --check channel/web/static/js/console.js
pytest tests/integration/test_business_postgres.py -q
git diff --check
```

如果某个测试因为 Docker/Postgres 环境不可用无法运行，请明确说明未运行原因；其他能运行的测试必须运行。

