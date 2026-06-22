# 投研组件通用框架最小改造计划

## 目标

新增一条清晰、可控的能力：

```text
管理员上传标准 Skill ZIP
-> 平台识别包内容
-> 管理员通过表单补齐组件配置
-> 平台生成投研组件
-> 主动组件产生默认输出
-> 默认输出可直接返回，或交给一个被动组件处理后返回
```

这不是重构整个投研系统，而是给现有系统增加“标准 Skill 包导入为投研组件”的能力。

## 明确不做

为了避免项目复杂化，第一阶段明确不做：

- 不做任意 DAG。
- 不做拖拽式工作流编辑器。
- 不支持多个被动组件串联。
- 不支持条件分支、循环、并行。
- 不重写现有技术分析链路。
- 不重写利率、转债内容生产链路。
- 不全量迁移 `service_type`。
- 不要求管理员手写复杂 `component.json`。
- 不把通用 Skill 系统和投研组件系统合并。

第一阶段只做：

```text
一个主动组件
-> 一个默认输出
-> 可选一个被动组件
```

## 名词边界

| 名词 | 含义 |
| --- | --- |
| Skill 包 | 管理员上传的原始 ZIP，通常包含 `SKILL.md`、`README.md`、`scripts/`、`assets/`、`references/` |
| 投研组件 | 平台可管理、可触发或可调用的业务组件 |
| 主动组件 | 用户输入触发词后可以直接调用的组件 |
| 被动组件 | 不直接被用户触发，只能被主动组件调用的组件 |
| 默认输出 | 主动组件执行后的主要结果，可以直接返回，也可以交给被动组件 |
| 执行器 | 平台内部执行组件的代码，例如命令行脚本执行器 |

`service_type` 保留为旧系统兼容字段。新增自定义组件优先使用 `component_key` 作为业务身份。

## 当前项目基础

当前项目已经具备这些基础：

- 有 `business/business_registry.py` 管理组件定义。
- 有 `business/component_service.py` 管理组件列表和设置。
- 有 `business/skill_versions.py` 管理脚本版本上传、解压、激活。
- 有 `technical-analysis` 主动组件。
- 有 `signal-card-renderer` 被动渲染组件。
- 有技术分析专用链路，可以作为新模型的验证样板。
- 有 Web 控制台组件页面，可以扩展导入对话框。

当前不足：

- 管理员上传的标准 Skill ZIP 不能直接变成组件。
- `技术分析v0.2.zip` 这类包没有 `component.json`。
- 技术分析链路是专用写死逻辑。
- 被动组件存在，但还没有通用调用协议。
- 主动组件默认输出没有统一模型。

## 最小设计

### 主动组件

主动组件必须有：

- 组件名称
- 组件 key
- 触发词
- 匹配方式
- 入口脚本或提示词配置
- 默认输出

默认输出可以是：

- `text`
- `markdown`
- `image`
- `file`
- `files`

第一期优先支持：

```text
命令行脚本 -> 文件输出
```

### 被动组件

被动组件必须有：

- 组件名称
- 组件 key
- 入口脚本
- 输入类型
- 输出类型

第一期只支持：

```text
文本或 Markdown -> 命令行脚本 -> 图片
```

典型组件：

```text
signal-card-renderer
```

### 一层后处理

主动组件执行后：

```text
默认输出
```

可以直接返回：

```text
默认输出 -> 用户
```

也可以交给一个被动组件：

```text
默认输出 -> 被动组件 -> 用户
```

第一期不支持更多层。

## 技术分析样板

管理员上传的 `技术分析v0.2.zip` 是标准 Skill 风格算法包。

它的真实形态：

```text
技术分析v0.2.zip
  技术分析v0.2/
    SKILL.md
    README.md
    scripts/
      analyze_universal.py
      chart_helpers.py
      indicators_lib.py
      indicator_query.py
      signal_scanner.py
    assets/
    references/
```

它的执行方式：

```bash
python scripts/analyze_universal.py --symbol {target_text} --output {work_dir}
```

它的输出：

```text
*技术分析报告*.md
*_TA_*.png
```

平台应允许管理员通过表单把它配置成：

```text
主动组件：技术分析
触发方式：后缀匹配
触发词：技术分析
入口脚本：scripts/analyze_universal.py
命令模板：python {entry} --symbol {target_text} --output {work_dir}
默认输出：Markdown 报告
可选返回：Markdown 报告、主图
可选后处理：把 Markdown 报告交给 signal-card-renderer，输出信号卡图片
```

## 图片渲染样板

图片渲染组件是被动组件，不是主动组件。

它应表达为：

```text
被动组件：图片渲染
入口脚本：scripts/render_card.py
输入：文本或 Markdown
输出：PNG
调用方式：python {entry} --text {input_text} --output {output_file}
```

它不配置触发词，不参与用户消息路由，只出现在主动组件“后处理组件”选择框中。

## 推荐配置结构

继续兼容现有 `component.json` 字段，新增少量结构化字段，不推翻旧模型。

主动命令行组件示例：

```json
{
  "component_key": "technical-analysis",
  "label": "技术分析组件",
  "description": "根据标的生成技术分析报告和图表。",
  "component_type": "active_script",
  "handler_type": "command_script",
  "match_type": "suffix",
  "default_triggers": ["技术分析"],
  "routable": true,
  "entry": "技术分析v0.2/scripts/analyze_universal.py",
  "script_name": "analyze_universal.py",
  "storage_name": "technical-analysis",
  "config_key": "skill.technical-analysis.script_path",
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
    "output": "processed"
  },
  "reply": {
    "outputs": ["report", "main_chart"]
  },
  "archive": {
    "outputs": ["report", "main_chart"]
  }
}
```

启用图片渲染时：

```json
{
  "postprocess": {
    "enabled": true,
    "component_key": "signal-card-renderer",
    "input": "report",
    "output": "signal_card"
  },
  "reply": {
    "outputs": ["signal_card", "main_chart"]
  },
  "archive": {
    "outputs": ["signal_card", "main_chart", "report"]
  }
}
```

## 后台表单

第一期表单只做固定模板，不做自由编排。

### 导入预览

上传 ZIP 后展示：

- Skill 名称
- Skill 描述
- 根目录
- 可选入口脚本列表
- README / SKILL.md 摘要

### 主动脚本组件表单

字段：

- 组件名称
- 组件 key
- 触发词
- 匹配方式：精确、前缀、后缀
- 入口脚本
- 命令模板
- 默认输出名称
- 默认输出类型
- 默认输出匹配规则
- 附加输出匹配规则
- 返回哪些输出
- 是否连接被动组件
- 被动组件选择

### 被动脚本组件表单

字段：

- 组件名称
- 组件 key
- 入口脚本
- 输入类型
- 输出类型
- 命令模板

第一期只支持命令行脚本。

## 后端任务拆解

### 任务 1：Skill ZIP 导入预览

新增：

```text
business/component_import_service.py
```

功能：

- 接收 ZIP bytes。
- 解压到临时导入目录。
- 支持 ZIP 内有单层根目录。
- 查找 `SKILL.md`，不要求在 ZIP 根目录。
- 查找 `README.md`。
- 扫描 `scripts/*.py`。
- 返回导入预览。

建议 API：

```text
POST /api/investment/component-imports/preview
```

返回示例：

```json
{
  "status": "success",
  "import": {
    "import_id": "import-xxx",
    "root_dir": "技术分析v0.2",
    "skill_name": "ta-pattern",
    "description": "...",
    "scripts": [
      "技术分析v0.2/scripts/analyze_universal.py",
      "技术分析v0.2/scripts/indicator_query.py"
    ]
  }
}
```

验收：

- `技术分析v0.2.zip` 可识别。
- 能找到 `SKILL.md`。
- 能找到 `scripts/analyze_universal.py`。
- 拒绝路径逃逸 ZIP。

### 任务 2：从导入结果创建组件

功能：

- 接收导入 ID 和表单配置。
- 生成 `component.json`。
- 移动导入内容到正式版本目录。
- 写 `manifest.json`。
- 让组件出现在投研组件列表。

建议 API：

```text
POST /api/investment/component-imports/{import_id}/create
```

验收：

- 能从 `技术分析v0.2.zip` 创建 `technical-analysis` 运行期组件。
- `business_storage/components/<component_key>/component.json` 存在。
- `versions/<version_id>/manifest.json` 存在。
- 组件列表能看到新组件。

### 任务 3：命令行脚本执行器

新增：

```text
business/executors/command_script_executor.py
```

功能：

- 渲染命令模板。
- 支持变量：
  - `{entry}`
  - `{raw_input}`
  - `{target_text}`
  - `{openid}`
  - `{work_dir}`
- 创建工作目录。
- 执行命令。
- 按 glob 收集输出文件。
- 返回标准结果。

不做：

- 不支持 shell 字符串执行。
- 不支持管理员任意拼 shell。
- 不支持网络权限控制。
- 不支持复杂变量表达式。

验收：

- 可执行 `analyze_universal.py --symbol {target_text} --output {work_dir}`。
- 能收集 Markdown 报告。
- 能收集主图。
- 缺少默认输出时返回错误。

### 任务 4：主动组件默认输出直接返回

功能：

- 路由命中新组件后，调用命令行执行器。
- 按 `reply.outputs` 返回结果。
- 按 `archive.outputs` 归档结果。

验收：

- `300502.SZ 技术分析` 可通过新通用组件执行。
- 不连接被动组件时，可返回 Markdown 报告或主图。
- 请求记录包含 `component_key/module_key`。

### 任务 5：一层被动组件后处理

功能：

- 支持主动组件配置一个被动组件。
- 读取主动组件默认输出文本。
- 调用被动组件命令。
- 把被动组件输出加入结果。

第一期只支持：

```text
markdown/text -> signal-card-renderer -> image
```

验收：

- 技术分析报告可传给 `signal-card-renderer`。
- 生成信号卡图片。
- 可返回 `signal_card + main_chart`。
- 报告仍归档。

### 任务 6：前端导入对话框

功能：

- 在投研组件页面增加“导入 Skill 创建组件”。
- 上传 ZIP 后展示导入预览。
- 选择主动/被动组件模板。
- 填写表单。
- 预览生成配置。
- 提交创建组件。

验收：

- 管理员能通过 UI 完成 `技术分析v0.2.zip` 导入。
- 表单字段数量可控。
- 不出现 DAG、节点、工作流等复杂概念。

## 兼容策略

保留现有能力：

- 原 `technical-analysis` 内置链路继续可用。
- 原技术分析脚本版本上传继续可用。
- 原 `signal-card-renderer` 版本上传继续可用。
- 原利率、转债逻辑继续可用。

新逻辑触发条件：

```text
组件有 execution 配置
-> 走新通用运行器
否则
-> 走旧 handler_type 逻辑
```

这样不会一次性改动全部旧业务。

## 数据存储

继续使用现有组件目录：

```text
business_storage/
  components/
    <component_key>/
      component.json
      versions/
        <version_id>/
          manifest.json
          <uploaded skill files>
```

新增临时导入目录：

```text
business_storage/
  component_imports/
    <import_id>/
      source.zip
      extracted/
      preview.json
```

导入创建成功后：

- 正式版本目录保存 Skill 文件。
- 组件根目录保存生成后的 `component.json`。
- 临时导入目录可以删除或定期清理。

## 验收标准

### 技术分析 ZIP 导入

给定 `技术分析v0.2.zip`：

- 可以上传预览。
- 可以识别 `SKILL.md`。
- 可以识别 `scripts/analyze_universal.py`。
- 可以通过表单创建主动组件。
- 可以执行命令行脚本。
- 可以收集 Markdown 报告和主图。
- 可以直接返回默认输出。
- 可以选择连接图片渲染被动组件。
- 可以生成并返回信号卡。

### 被动组件

给定图片渲染组件：

- 只能创建为被动组件。
- 不显示触发词配置。
- 不参与用户消息路由。
- 可被主动组件选择。
- 接收文本或 Markdown。
- 输出 PNG。

### 兼容

这些旧功能必须继续通过：

- `300502.SZ 技术分析`
- `利率`
- `转债`
- 技术分析脚本版本上传
- 图片生成组件版本上传

## 实施建议

建议按以下顺序开发：

1. Skill ZIP 导入预览。
2. 从导入结果生成组件。
3. 命令行脚本执行器。
4. 主动组件默认输出直接返回。
5. 一层被动组件后处理。
6. 前端导入对话框完善。

每一步都要有测试，不要等全部做完再验收。

## 结论

这个方案是增量修改，不是全量重构。

它只新增一个清晰能力：

```text
标准 Skill 包 -> 平台表单配置 -> 投研组件
```

它保留现有业务链路，不强行迁移 `service_type`，不引入任意 DAG，也不要求管理员理解复杂执行图。

第一期只需要把 `技术分析v0.2.zip` 跑通：

```text
命令行分析脚本
-> Markdown 默认输出
-> 可直接返回
-> 可选接图片渲染被动组件
```

这条路径足够验证通用框架，也不会把项目复杂度拉高。
