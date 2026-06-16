# 投研组件存储结构

投研组件分为两类目录：

- `builtin/components/<component_key>`：项目随代码和镜像发布的内置默认组件。镜像更新会更新这里的默认实现。
- `investment/components/<component_key>`：运行期上传或更新的组件。每个组件包含一个 `component.json` 和 `versions/<version_id>` 目录。

运行期组件目录示例：

```text
investment/
  components/
    technical-analysis/
      component.json
      versions/
        skill-20260616000000-xxxxxxxx/
          manifest.json
          scripts/
            analyze_universal.py
          assets/
          references/
```

`component.json` 描述组件的触发词、入口、处理类型和版本配置键；`versions/<version_id>` 保存一次完整上传包。当前生效版本通过配置表里的 `config_key` 指向版本目录内的入口脚本。

上传规则：

- 新上传的完整组件包会写入 `investment/components/<component_key>/versions/<version_id>`。
- 旧 `SKILL.md` 包仍可上传，系统会自动转换出 `component.json`。
- 版本列表只读取 `investment/components/<component_key>/versions`，不再扫描旧 `investment/skills` 目录。

服务器部署要求：

- Docker 或服务器部署时，应把应用数据目录中的 `investment/` 挂载为持久卷。
- 更新镜像只会替换代码内置的 `builtin/components`，不会覆盖持久卷里的 `investment/components`。
- 若不挂载持久卷，运行期上传的组件、版本和配置会随容器重建丢失。
