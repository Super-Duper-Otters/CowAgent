# 投研组件产品模型改造计划

## 背景

当前投研组件体系已经具备这些基础：

- 组件注册与匹配：`business/business_registry.py`
- 组件列表与配置：`business/component_service.py`
- ZIP 上传与版本目录：`business/skill_versions.py`
- 新增 Skill ZIP 导入预览与命令脚本组件创建：`business/component_import_service.py`
- 命令行脚本执行器：`business/executors/command_script_executor.py`
- Web 控制台组件页：`channel/web/static/js/console.js`

现有改造已经跑通了第一版闭环：

```text
标准 Skill ZIP
-> 预览
-> 表单创建主动/被动脚本组件
-> 命令行执行
-> 默认输出直接返回
-> 可选一个被动组件后处理
```

但当前模型仍有两个不足：

1. ZIP 导入和手动创建提示词组件尚未形成统一产品模型。
2. 无脚本 Skill ZIP 只能预览，不能稳定创建为可运行组件。

本计划目标是把组件系统整理为清晰、可维护、基础功能够用的产品模型，避免继续打补丁式扩展。

## 目标模型

组件系统按两个维度组织。

### 组件创建方式

```text
1. 从 ZIP 创建
2. 手动创建提示词组件
```

### 组件能力类型

```text
1. 主动脚本组件 active_script
2. 被动脚本组件 passive_script
3. 主动提示词组件 active_prompt
```

核心原则：

```text
创建方式负责“怎么生成 component.json”
能力类型负责“运行时怎么执行”
```

不要按“ZIP 组件”和“提示词组件”各自做一套运行系统。最终都落到统一 `component.json`，运行时仍然走：

```text
business_registry
-> router
-> module_dispatcher
```

## 明确不做

第一版不做以下内容：

- 不做 DAG。
- 不做工作流编辑器。
- 不做多被动组件串联。
- 不做被动提示词组件。
- 不做条件分支、循环、并行。
- 不做参数 schema 自动推导。
- 不做复杂输出规则可视化编辑器。
- 不重写旧 `technical-analysis`、`rate`、`convertible-bond`、`signal-card-renderer` 链路。

## 推荐 component.json 结构

### 主动脚本组件

```json
{
  "component_key": "active-ta-sample",
  "label": "技术分析测试组件",
  "creation_method": "zip",
  "component_type": "active_script",
  "handler_type": "command_script",
  "routable": true,
  "match_type": "suffix",
  "default_triggers": ["技术分析"],
  "entry": "active-ta-sample/scripts/analyze_universal.py",
  "execution": {
    "command": ["python", "{entry}", "--symbol", "{target_text}", "--output", "{work_dir}"],
    "outputs": {
      "report": {"type": "markdown", "pattern": "*技术分析报告*.md"},
      "main_chart": {"type": "image", "pattern": "*_TA_*.png"}
    },
    "default_output": "report"
  },
  "postprocess": {
    "enabled": false,
    "component_key": "",
    "input": "report",
    "output": "signal_card"
  },
  "reply": {"outputs": ["report"]},
  "archive": {"outputs": ["report", "main_chart"]}
}
```

### 被动脚本组件

```json
{
  "component_key": "signal-card-renderer-sample",
  "label": "信号卡渲染测试组件",
  "creation_method": "zip",
  "component_type": "passive_script",
  "handler_type": "command_script",
  "routable": false,
  "entry": "passive-card-renderer-sample/scripts/render_card.py",
  "execution": {
    "command": ["python", "{entry}", "--text", "{input_text}", "--output", "{output_file}"],
    "outputs": {
      "image": {"type": "image", "pattern": "*.png"}
    },
    "default_output": ""
  },
  "reply": {"outputs": ["image"]},
  "archive": {"outputs": ["image"]}
}
```

### 主动提示词组件

```json
{
  "component_key": "macro-commentary",
  "label": "宏观点评",
  "creation_method": "manual_prompt",
  "component_type": "active_prompt",
  "handler_type": "prompt_component",
  "routable": true,
  "match_type": "suffix",
  "default_triggers": ["宏观点评"],
  "prompt": {
    "template": "请基于用户输入生成一段投研风格宏观点评：{target_text}",
    "output_type": "markdown"
  },
  "reply": {"outputs": ["text"]},
  "archive": {"outputs": ["text"]}
}
```

## 后端改造计划

### 阶段 1：固化组件模型

目标：让后端清楚区分创建方式和能力类型。

改造文件：

- `business/business_registry.py`
- `business/component_service.py`
- `business/component_import_service.py`

任务：

1. `BusinessDefinition` 增加并透传：
   - `creation_method`
   - `prompt`
   - 已有 `execution`
   - 已有 `postprocess`
   - 已有 `reply`
   - 已有 `archive`
2. `read_component_definition()` 读取这些字段。
3. `list_components()` 返回这些字段，供前端配置弹窗使用。
4. `component_service` 按组件类型开放配置：
   - `command_script` 允许运行期组件编辑执行配置。
   - `prompt_component` 允许运行期组件编辑提示词配置。
   - 内置旧组件不允许通过运行期 manifest 编辑入口误改。

验收：

- 旧组件列表正常。
- 运行期脚本组件仍可编辑执行配置。
- 运行期提示词组件能出现在组件列表。
- 内置组件不会被误编辑 manifest。

### 阶段 2：ZIP 创建能力策略化

目标：ZIP 创建入口统一，但内部按能力类型分策略。

改造文件：

- `business/component_import_service.py`

建议结构：

```python
def preview_skill_zip(...):
    ...

def detect_import_kind(preview):
    ...

def create_component_from_import(import_id, form, ...):
    if form["component_type"] in {"active_script", "passive_script"}:
        return create_command_script_component(...)
    if form["component_type"] == "active_prompt":
        return create_prompt_component_from_zip(...)
    raise ValueError(...)
```

ZIP 创建支持：

```text
1. ZIP 有 scripts/*.py -> active_script
2. ZIP 有 scripts/*.py -> passive_script
3. ZIP 无 scripts/*.py -> active_prompt
```

无脚本 ZIP 的处理：

```text
读取 SKILL.md / README.md
-> 提取名称、描述、正文摘要
-> 带入提示词组件表单
-> 管理员补 key、触发词、提示词
-> 创建 active_prompt
```

不要为无脚本 ZIP 单独做执行器。

验收：

- `active-ta-sample.zip` 可创建主动脚本组件。
- `passive-card-renderer-sample.zip` 可创建被动脚本组件。
- `prompt-only-no-script-sample.zip` 可创建主动提示词组件。
- 未预览 ZIP 不能进入创建配置。
- 不再默认填 `technical-analysis`。

### 阶段 3：手动创建提示词组件

目标：不需要 ZIP，管理员直接创建主动提示词组件。

新增服务函数：

```text
business/component_service.py
  create_prompt_component(...)
```

建议 API：

```text
POST /api/investment/components/prompt
```

请求字段：

```json
{
  "component_key": "macro-commentary",
  "label": "宏观点评",
  "match_type": "suffix",
  "default_triggers": ["宏观点评"],
  "prompt": {
    "template": "请生成宏观点评：{target_text}",
    "output_type": "markdown"
  },
  "enabled": true
}
```

生成：

```text
business_storage/components/<component_key>/component.json
```

不需要版本目录。

验收：

- 后台可创建提示词组件。
- 组件出现在组件列表。
- 能编辑触发词和提示词。
- 内置组件不受影响。

### 阶段 4：提示词组件运行器

目标：让 `active_prompt + prompt_component` 能被用户触发并返回文本/Markdown。

改造文件：

- `business/module_dispatcher.py`
- 新增 `business/executors/prompt_component_executor.py`

运行流程：

```text
用户输入命中 active_prompt
-> 解析 target_text
-> 渲染 prompt.template
-> 调用项目现有 AI 生成能力
-> 返回 text/markdown
-> 写请求记录
```

第一版只支持：

```text
prompt -> text/markdown
```

不支持图片输出，不支持后处理。

验收：

- 创建“宏观点评”组件。
- 输入 `新能源 宏观点评`。
- 返回文本/Markdown。
- 请求记录包含 `module_key`。

### 阶段 5：前端创建 UI 重构

目标：组件创建 UI 清晰，不混用概念。

组件页按钮：

```text
[从 ZIP 创建组件]
[手动创建提示词组件]
```

ZIP 创建流程：

```text
上传 ZIP
-> 预览包内容
-> 选择能力类型
   - 主动脚本组件
   - 被动脚本组件
   - 主动提示词组件
-> 填表
-> 预览 component.json
-> 创建
```

手动提示词组件流程：

```text
填写组件名称/key/触发词/提示词
-> 预览配置
-> 创建
```

配置弹窗规则：

- 脚本组件显示执行配置。
- 提示词组件显示提示词配置。
- 被动组件不显示触发词。
- 字段说明统一使用圆形 `i` tooltip。
- 未预览 ZIP 前不能编辑 ZIP 创建配置。

验收：

- 无脚本 ZIP 不显示命令模板字段。
- 手动提示词组件不需要 ZIP。
- 创建后配置弹窗能编辑创建时的关键字段。

## 测试计划

新增或补充测试：

### 后端

- ZIP 主动脚本组件创建。
- ZIP 被动脚本组件创建。
- ZIP 无脚本创建主动提示词组件。
- 手动创建主动提示词组件。
- 提示词组件命中路由并返回文本。
- 提示词组件请求记录包含 `module_key`。
- 内置组件拒绝运行期 manifest 编辑。
- 旧 `technical-analysis`、`rate`、`convertible-bond`、`signal-card-renderer` 兼容。

### 前端

- 组件页有两个创建入口：
  - 从 ZIP 创建组件
  - 手动创建提示词组件
- ZIP 未预览前不能编辑配置。
- 无脚本 ZIP 显示主动提示词组件配置。
- 提示词组件创建表单不出现 ZIP 字段。
- 配置弹窗按组件类型显示不同字段。
- tooltip 使用可见浮层，不依赖浏览器原生 title。

## 推荐实施顺序

1. 后端模型字段补齐。
2. 后端创建提示词组件服务。
3. 后端提示词组件执行器。
4. ZIP 无脚本创建 active_prompt。
5. 前端拆分两个创建入口。
6. 前端配置弹窗按类型重构。
7. 全量针对性回归测试。

## 子 Agent 分工建议

可以使用子 agent，但主 agent 必须统一架构决策。

### 子 Agent 1：后端组件模型和创建服务

负责：

- `business_registry.py`
- `component_service.py`
- `component_import_service.py`
- 相关后端测试

边界：

- 不改前端。
- 不改旧业务 handler。
- 不引入新数据库表。

### 子 Agent 2：提示词组件执行器

负责：

- `prompt_component_executor.py`
- `module_dispatcher.py` 接入
- 路由与记录测试

边界：

- 第一版只返回 text/markdown。
- 不支持图片。
- 不支持后处理。

### 子 Agent 3：前端组件创建 UI

负责：

- `channel/web/static/js/console.js`
- `channel/web/static/css/console.css`
- 前端静态测试

边界：

- 只做两个创建入口。
- 不做工作流编辑器。
- 不做 DAG。

## 完成标准

以下场景全部通过才算完成：

1. 从 ZIP 创建主动脚本组件并执行。
2. 从 ZIP 创建被动脚本组件并作为后处理使用。
3. 从无脚本 ZIP 创建主动提示词组件。
4. 手动创建主动提示词组件。
5. 创建后可编辑组件关键配置。
6. 旧组件链路不受影响。
7. UI 不再默认填 `technical-analysis`。
8. 未预览 ZIP 前不能创建 ZIP 组件。
9. 无 DAG、无工作流编辑器、无多层编排。
