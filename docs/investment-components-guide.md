# 投研组件使用与编写指南

这份文档面向平台管理员，说明投研组件到底有哪些、应该怎么理解、怎么编写和上传。

## 一句话理解

投研组件就是“用户输入触发词后，平台按某种方式生成或返回投研结果”的业务模块。

不要先看代码里的 `active_prompt`、`active_script`、`passive_script`。管理员只需要按下面三类理解：

| 简单分类 | 适合做什么 | 用户能否直接触发 | 是否需要写代码 |
| --- | --- | --- | --- |
| 内容生成组件 | 利率日报、转债日报、宏观简报、策略观点图片 | 可以 | 通常不需要 |
| 脚本分析组件 | 技术分析、量化计算、调用外部数据源后输出结果 | 可以 | 需要 |
| 基础支撑组件 | 图片渲染、模板渲染、公共处理能力 | 不直接触发 | 通常需要 |

代码里的类型和管理员分类的对应关系：

| 管理员分类 | 代码类型 | 说明 |
| --- | --- | --- |
| 内容生成组件 | `active_prompt` | 依靠提示词、模板和模型生成投研内容 |
| 脚本分析组件 | `active_script` | 用户触发后执行组件包内的脚本 |
| 基础支撑组件 | `passive_script` | 被其他组件调用，不作为用户入口 |

## 目前内置组件

当前系统内置了 4 个投研组件：

| 组件 | 管理员分类 | 当前用途 | 用户输入示例 |
| --- | --- | --- | --- |
| 技术分析组件 | 脚本分析组件 | 根据股票代码或名称生成技术分析报告、图表和信号卡片 | `300502.SZ 技术分析` |
| 利率组件 | 内容生成组件 | 返回当前生效的利率投研内容图片 | `利率` |
| 转债组件 | 内容生成组件 | 返回当前生效的可转债投研内容图片 | `转债` |
| 图片生成组件 | 基础支撑组件 | 把标准投研文本渲染成图片卡片，供其他组件使用 | 无直接触发词 |

## 内容生成组件

内容生成组件是管理员最常用、最适合后台配置的类型。

它的核心是：

- 触发词：用户输入什么会命中组件。
- 提示词：模型如何把资料整理成标准投研文本。
- 模板：最终用哪种图片样式渲染。
- 生成方式：是后台提前生成，还是用户触发时即时生成。

内容生成组件有两种常见模式。

### 预生成内容组件

适合每天或定期更新的固定栏目，例如：

- 利率日报
- 转债日报
- 宏观日报
- 策略周报

特点：

- 管理员先在后台上传资料或文本。
- 系统先生成图片并设为生效内容。
- 用户输入触发词后，平台直接返回当前生效图片。
- 用户等待时间短，内容可人工检查后发布。

推荐用于正式对客栏目。

示例 `component.json`：

```json
{
  "component_key": "macro-daily",
  "label": "宏观日报组件",
  "description": "后台预生成宏观日报内容，用户输入触发词后返回当前生效图片。",
  "service_type": "unmatched",
  "match_type": "exact",
  "default_triggers": ["宏观日报"],
  "handler_type": "daily_content",
  "generation_mode": "pre_generated",
  "delivery_mode": "direct",
  "content_enabled": true,
  "output_mode": "image",
  "routable": true,
  "storage_name": "macro-daily",
  "component_type": "active_prompt",
  "prompt_key": "prompt.macro_daily",
  "renderer_component_key": "signal-card-renderer",
  "template_key": "rate"
}
```

### 即时生成内容组件

适合用户每次问题都不一样的场景，例如：

- 宏观简报
- 政策解读
- 用户粘贴一段资料后生成图片
- 临时主题投研卡片

特点：

- 用户输入触发词和具体内容。
- 系统即时调用模型生成标准文本。
- 再把标准文本渲染成图片。
- 灵活，但耗时更长，质量更依赖提示词。

示例 `component.json`：

```json
{
  "component_key": "macro-brief",
  "label": "宏观简报组件",
  "description": "用户发送宏观简报请求后，系统附加提示词并生成图片结果。",
  "service_type": "unmatched",
  "match_type": "prefix",
  "default_triggers": ["宏观简报"],
  "handler_type": "prompt_to_image",
  "generation_mode": "on_demand",
  "delivery_mode": "deferred",
  "content_enabled": false,
  "output_mode": "image",
  "routable": true,
  "storage_name": "macro-brief",
  "component_type": "active_prompt",
  "prompt_key": "prompt.macro_brief",
  "renderer_component_key": "signal-card-renderer",
  "template_key": "rate"
}
```

## 脚本分析组件

脚本分析组件适合“提示词不够，需要程序处理”的场景。

例如：

- 读取行情数据后计算指标。
- 调用外部接口。
- 运行量化模型。
- 生成多个文件。
- 返回文本、图片或混合结果。

脚本组件需要上传 Python 脚本。平台会把用户输入包装成 JSON，通过 stdin 传给脚本；脚本把执行结果以 JSON 输出到 stdout。

脚本输入示例：

```json
{
  "openid": "user-openid",
  "raw_input": "300502.SZ 技术分析",
  "target_text": "300502.SZ",
  "skill_key": "technical-analysis"
}
```

脚本输出示例：

```json
{
  "success": true,
  "reply_text": "这里是返回给用户的文本",
  "output_files": [],
  "detail": "可选的执行详情"
}
```

如果要返回图片或文件，把文件路径放到 `output_files`：

```json
{
  "success": true,
  "reply_text": "",
  "output_files": [
    "business_storage/outputs/example-card.png"
  ]
}
```

示例 `component.json`：

```json
{
  "component_key": "custom-analysis",
  "label": "自定义分析组件",
  "description": "用户输入触发词后执行自定义分析脚本。",
  "service_type": "unmatched",
  "match_type": "suffix",
  "default_triggers": ["自定义分析"],
  "handler_type": "script",
  "entry": "scripts/run.py",
  "output_mode": "text",
  "routable": true,
  "config_key": "skill.custom-analysis.script_path",
  "script_name": "run.py",
  "storage_name": "custom-analysis",
  "component_type": "active_script"
}
```

组件包结构：

```text
custom-analysis.zip
  component.json
  scripts/
    run.py
```

## 基础支撑组件

基础支撑组件不是给用户直接输入触发词用的，而是给其他组件调用。

当前的“图片生成组件”就是基础支撑组件。它负责把标准投研文本渲染成图片卡片。

这类组件适合放：

- 图片渲染脚本
- HTML 模板
- 公共转换脚本
- 被多个投研组件复用的能力

示例 `component.json`：

```json
{
  "component_key": "signal-card-renderer",
  "label": "图片生成组件",
  "description": "把标准投研文本渲染为信号卡片图片。",
  "service_type": "unmatched",
  "match_type": "exact",
  "default_triggers": [],
  "handler_type": "renderer",
  "entry": "scripts/render_card.py",
  "output_mode": "image",
  "routable": false,
  "config_key": "render.renderer_path",
  "script_name": "render_card.py",
  "storage_name": "signal-card-renderer",
  "copy_assets_from": "builtin/components/signal-card-renderer/assets",
  "component_type": "passive_script"
}
```

## 触发词匹配方式

`match_type` 决定用户输入如何命中组件：

| 值 | 含义 | 示例 |
| --- | --- | --- |
| `exact` | 完全等于触发词 | 用户输入 `利率` |
| `prefix` | 以触发词开头 | 用户输入 `宏观简报 今天降息怎么看` |
| `suffix` | 以触发词结尾 | 用户输入 `300502.SZ 技术分析` |

建议：

- 固定栏目用 `exact`。
- 用户输入“触发词 + 内容”的场景用 `prefix`。
- 用户输入“标的 + 触发词”的场景用 `suffix`。

## 上传方式

平台支持两种上传方式。

### 上传完整组件包

适合新增组件或完整替换组件定义。

要求：

- 文件必须是 `.zip`。
- ZIP 根目录必须包含 `component.json`。
- 旧格式 `SKILL.md` 也兼容，但不建议新组件继续使用。

推荐结构：

```text
my-component.zip
  component.json
  scripts/      # 脚本组件需要
  assets/       # 可选
  references/   # 可选
```

### 上传脚本版本

适合只更新已有脚本组件的代码。

要求：

- 文件可以是 `.py` 或 `.zip`。
- `.py` 文件名必须等于组件声明的 `script_name`。
- `.zip` 内必须能找到对应脚本。

例如：

- 技术分析组件必须上传 `analyze_universal.py` 或包含它的 ZIP。
- 图片生成组件必须上传 `render_card.py` 或包含它的 ZIP。

## 是否符合通用 Skill

投研组件和通用 Skill 有关系，但不是完全相同的东西。

共同点：

- 都可以有描述文件。
- 都可以带脚本、资源、参考资料。
- 都可以打包上传。

不同点：

| 对比项 | 投研组件 | 通用 Skill |
| --- | --- | --- |
| 主要用途 | 投研业务入口、触发词、生成图片、业务记录 | 给 Agent 增加通用能力和工作流程 |
| 触发方式 | 用户消息命中 `default_triggers` | Agent 根据 Skill 描述自行选择 |
| 配置核心 | `component.json` | `SKILL.md` |
| 是否进入投研后台 | 是 | 否 |
| 是否接入投研记录、权限、内容发布 | 是 | 否 |

结论：

- 新投研业务组件应优先写 `component.json`，按投研组件格式上传。
- 旧的带 `investment` frontmatter 的 `SKILL.md` 包还能上传，系统会转换为组件定义。
- 普通通用 Skill 不能直接当成投研组件使用，除非它包含投研组件需要的 `investment` 配置或被改写为 `component.json` 包。

兼容旧 `SKILL.md` 的最小示例：

```markdown
---
name: macro-analysis
description: 宏观分析投研组件
investment:
  label: 宏观分析
  routable: true
  service_type: unmatched
  match_type: exact
  triggers:
    - 宏观
  handler_type: script
  entry: scripts/macro_analysis.py
  output_mode: text
---

# Macro Analysis
```

虽然兼容这种写法，但新组件建议使用 `component.json`，更直接，也更符合当前投研组件后台。

## 管理员该怎么选择

如果管理员只是新增一个业务栏目，优先选内容生成组件：

- 每天更新、人工确认后对客：用预生成内容组件。
- 用户每次输入不同问题：用即时生成内容组件。

如果管理员需要接入数据、跑模型或做复杂计算，选脚本分析组件。

如果管理员要改图片样式、模板或公共渲染能力，才考虑基础支撑组件。

## 推荐编写流程

1. 先确定组件属于哪一类：内容生成、脚本分析、基础支撑。
2. 确定用户如何触发：`exact`、`prefix`、`suffix`。
3. 编写 `component.json`。
4. 如果是脚本组件，补充 `scripts/xxx.py`。
5. 打成 ZIP，确保 `component.json` 位于 ZIP 根目录。
6. 在后台上传组件包。
7. 配置触发词、提示词和启用状态。
8. 用测试账号实际发送触发词验证结果。

## 固定分类值

有些字段不是随便写字符串，而是当前系统只识别几个固定值。管理员最容易填错的是下面这些。

### `component_type`

这是组件的大类。当前只建议使用 3 个值：

| 值 | 管理员理解 | 什么时候用 |
| --- | --- | --- |
| `active_prompt` | 内容生成组件 | 不写代码，靠提示词、模型、模板生成内容 |
| `active_script` | 脚本分析组件 | 用户触发后执行 Python 脚本 |
| `passive_script` | 基础支撑组件 | 不给用户直接触发，供其他组件调用 |

判断标准：

- 有用户触发词，而且不写脚本：用 `active_prompt`。
- 有用户触发词，而且要运行脚本：用 `active_script`。
- 没有用户触发词，是内部能力：用 `passive_script`。

### `handler_type`

这是组件命中后具体怎么执行。当前常用值：

| 值 | 含义 | 常见搭配 |
| --- | --- | --- |
| `daily_content` | 后台先生成内容，用户触发后返回当前生效内容 | `active_prompt` |
| `prompt_to_image` | 用户触发时即时调用模型生成文本，再渲染图片 | `active_prompt` |
| `script` | 用户触发后执行组件包里的 Python 脚本 | `active_script` |
| `renderer` | 渲染器组件，负责把文本转图片 | `passive_script` |
| `builtin_technical_analysis` | 内置技术分析链路 | 系统内置组件使用，不建议自定义组件使用 |

管理员新增组件时，通常只在前三个里选：`daily_content`、`prompt_to_image`、`script`。

### `match_type`

这是触发词匹配方式。当前支持 3 个值：

| 值 | 含义 | 示例 |
| --- | --- | --- |
| `exact` | 用户输入必须完全等于触发词 | `利率` |
| `prefix` | 用户输入以触发词开头 | `宏观简报 今天怎么看` |
| `suffix` | 用户输入以触发词结尾 | `300502.SZ 技术分析` |

### `service_type`

这是业务服务类型，用于权限、记录、缓存和部分默认模板逻辑。

当前代码里明确识别这些值：

| 值 | 含义 | 建议 |
| --- | --- | --- |
| `technical_analysis` | 技术分析 | 只给技术分析类组件用 |
| `rate` | 利率 | 只给利率栏目用 |
| `convertible_bond` | 可转债 | 只给转债栏目用 |
| `unmatched` | 未归入内置服务的新组件 | 新增自定义组件优先用这个 |
| `all` | 全部权限用 | 不建议组件里使用 |
| `unauthorized_request` | 无权限请求 | 不建议组件里使用 |

注意：如果写了系统不认识的 `service_type`，当前会被归一化为 `unmatched`。所以新增宏观、策略、政策类组件，建议直接写 `unmatched`，再依靠 `component_key` 区分模块。

### `generation_mode`

这是给后台展示和理解用的生成方式。常用值：

| 值 | 含义 | 常见搭配 |
| --- | --- | --- |
| `pre_generated` | 后台预生成 | `daily_content` |
| `on_demand` | 用户触发时生成 | `prompt_to_image`、脚本类组件 |

不填时，系统会根据 `handler_type` 推断。

### `delivery_mode`

这是给后台展示和理解用的交付方式。常用值：

| 值 | 含义 | 常见搭配 |
| --- | --- | --- |
| `direct` | 直接返回已有结果 | `daily_content` |
| `deferred` | 生成后再通知或返回 | `prompt_to_image`、技术分析 |

不填时，系统会根据 `handler_type` 推断。

### `output_mode`

这是组件预期输出类型。当前常见值：

| 值 | 含义 | 常见场景 |
| --- | --- | --- |
| `text` | 返回文本 | 测试组件、纯文本脚本组件 |
| `image` | 返回单张图片 | 内容生成组件、渲染器 |
| `images` | 返回多张图片 | 技术分析这类有信号卡、图表等多个文件的组件 |
| `mixed` | 文本和文件都有可能 | 兼容旧组件或不确定输出形态 |

### `template_key`

这是图片模板选择。当前渲染服务识别这些值：

| 值 | 使用模板 |
| --- | --- |
| `technical_analysis` 或 `ta` | 技术分析卡片模板 |
| `rate` | 利率卡片模板 |
| `convertible_bond`、`convertible-bond` 或 `cb` | 可转债卡片模板 |

新增内容生成组件如果暂时没有自己的模板，可以先复用 `rate` 或 `convertible_bond`。如果不填，系统会尝试按 `service_type` 选择默认模板；但自定义组件通常是 `unmatched`，因此建议明确填写 `template_key`。

## `component.json` 字段说明

### 基础信息字段

| 字段 | 是否建议填写 | 含义 |
| --- | --- | --- |
| `component_key` | 必填 | 组件唯一标识。只能使用字母、数字、点、下划线、短横线，且必须以字母或数字开头。示例：`macro-daily` |
| `label` | 必填 | 后台展示名称。示例：`宏观日报组件` |
| `description` | 建议填写 | 组件说明，方便后台识别和后续维护 |
| `storage_name` | 建议填写 | 运行期存储目录名。通常和 `component_key` 保持一致 |

### 路由和触发字段

| 字段 | 是否建议填写 | 含义 |
| --- | --- | --- |
| `routable` | 必填 | 是否允许用户消息直接触发。主动组件写 `true`，基础支撑组件写 `false` |
| `default_triggers` | 主动组件必填 | 默认触发词数组。后台后续可以改触发词 |
| `match_type` | 必填 | 触发词匹配方式：`exact`、`prefix`、`suffix` |
| `service_type` | 建议填写 | 业务服务类型。新增自定义组件通常写 `unmatched` |

`default_triggers` 示例：

```json
{
  "default_triggers": ["宏观日报", "宏观观点"]
}
```

### 组件分类和执行字段

| 字段 | 是否建议填写 | 含义 |
| --- | --- | --- |
| `component_type` | 必填 | 组件大类：`active_prompt`、`active_script`、`passive_script` |
| `handler_type` | 必填 | 命中组件后怎么执行：`daily_content`、`prompt_to_image`、`script`、`renderer` |
| `generation_mode` | 可选 | 生成方式：`pre_generated` 或 `on_demand`。不填会按 `handler_type` 推断 |
| `delivery_mode` | 可选 | 交付方式：`direct` 或 `deferred`。不填会按 `handler_type` 推断 |
| `content_enabled` | 内容栏目建议填写 | 是否在后台内容生产页面展示这个组件。预生成内容组件写 `true`，即时生成组件通常写 `false` |
| `output_mode` | 建议填写 | 预期输出类型：`text`、`image`、`images`、`mixed` |

常见组合：

| 目标 | `component_type` | `handler_type` | `content_enabled` |
| --- | --- | --- | --- |
| 后台预生成日报 | `active_prompt` | `daily_content` | `true` |
| 用户即时生成图片 | `active_prompt` | `prompt_to_image` | `false` |
| 用户触发脚本分析 | `active_script` | `script` | `false` |
| 内部图片渲染器 | `passive_script` | `renderer` | `false` |

### 提示词和模板字段

| 字段 | 是否建议填写 | 含义 |
| --- | --- | --- |
| `prompt_key` | 内容生成组件建议填写 | 提示词保存到配置表里的键。后台编辑提示词时会使用它 |
| `renderer_component_key` | 图片生成组件建议填写 | 指定使用哪个渲染组件，当前通常写 `signal-card-renderer` |
| `template_key` | 图片生成组件建议填写 | 指定图片模板：`technical_analysis`、`rate`、`convertible_bond` 等 |

`prompt_key` 建议命名规则：

```text
prompt.<component_key>
```

例如：

```json
{
  "component_key": "macro-daily",
  "prompt_key": "prompt.macro_daily"
}
```

### 脚本和版本字段

这些字段只对脚本组件重要。

| 字段 | 是否建议填写 | 含义 |
| --- | --- | --- |
| `entry` | 脚本组件必填 | 组件包内的脚本入口路径。示例：`scripts/run.py` |
| `script_name` | 脚本组件必填 | 入口脚本文件名。示例：`run.py` |
| `config_key` | 版本化脚本必填 | 当前生效脚本路径保存到哪个配置键。上传新版本后，系统会把新脚本路径写到这里 |
| `copy_assets_from` | 可选 | 创建新脚本版本时，从内置目录复制资源到版本目录。当前内置图片生成组件使用它 |

`config_key` 建议命名规则：

```text
skill.<component_key>.script_path
```

例如：

```json
{
  "component_key": "custom-analysis",
  "config_key": "skill.custom-analysis.script_path"
}
```

内置组件为了兼容历史配置，使用了一些已有键，例如：

| 组件 | `config_key` |
| --- | --- |
| 技术分析组件 | `technical_analysis.skill_path` |
| 图片生成组件 | `render.renderer_path` |

新组件不需要沿用这些历史键。
