# 用户系统权限与 CRUD 完善计划

日期：2026-06-01

## 目标

把当前投资业务用户系统整理成两类清晰用户：

- 客户：只用于微信公众号端服务授权，无密码，不能登录后台 Web。
- 后台人员：只用于后台 Web 登录和运营操作，有账号密码和角色。

后台人员角色最终只保留两类：

- `admin`：主管理员，拥有全部后台权限。
- `content_operator`：内容上传发布人员，负责利率/转债内容上传、生成、发布、查看相关记录。

## 当前问题

1. 客户权限仍使用 `users.read` / `users.write`，语义不够明确，容易和后台人员混淆。
2. 后台人员已新增 `admin_users.*` 权限，但未显式写入角色权限矩阵，只靠 `admin` 的 `*` 放行。
3. 后台角色过多：`uploader`、`poster`、`technical_admin`、`readonly` 和当前业务目标不一致。
4. 客户 CRUD 不完整：只有新增/更新/停用/导入/导出，没有启用接口、明确删除语义、完整搜索。
5. 后台人员 CRUD 不完整：缺少不存在账号时的明确错误、独立重置密码权限、明确删除/停用语义。
6. 客户管理、后台人员管理缺少操作审计。

## 权限命名方案

### 客户权限

用 `customers.*` 替换旧的 `users.*`：

- `customers.read`：查看客户列表、客户详情。
- `customers.write`：新增、编辑客户。
- `customers.enable`：启用/停用客户。
- `customers.import`：导入客户 Excel。
- `customers.export`：导出客户 Excel。

兼容策略：

- 第一阶段保留 `users.read` / `users.write` 兼容映射。
- 前端和后端新代码全部改用 `customers.*`。
- 测试覆盖新旧权限兼容。

### 后台人员权限

- `admin_users.read`：查看后台人员列表。
- `admin_users.write`：新增后台人员、修改角色、启用/停用。
- `admin_users.reset_password`：重置后台人员密码。

### 内容权限

用更具体的动作权限替换粗粒度 `content.write`：

- `content.read`：查看内容和内容记录。
- `content.upload`：上传/保存草稿。
- `content.generate`：生成内容。
- `content.publish`：设为生效。
- `content.delete`：删除或归档内容。

兼容策略：

- 暂时让 `content.write` 等价于 `content.upload`。
- 后续前端按钮和后端接口逐步切到具体动作权限。

### 其他后台权限

- `records.read`：查看服务记录和上传记录。
- `records.export`：导出服务记录。
- `audits.read`：查看操作审计。
- `cache.read`：查看缓存。
- `cache.write`：清理/失效缓存。
- `config.read`：查看系统配置。
- `config.write`：修改系统配置。
- `skills.read`：查看 Skill 配置。
- `skills.write`：上传、启用、删除 Skill 版本。
- `health.read`：查看健康检查。
- `stocks.read`：查看股票字典。
- `stocks.write`：刷新股票字典。

## 角色矩阵

### admin

拥有全部权限，包括：

- `customers.*`
- `admin_users.*`
- `content.*`
- `records.*`
- `audits.read`
- `cache.*`
- `config.*`
- `skills.*`
- `health.read`
- `stocks.*`

### content_operator

拥有内容运营权限：

- `content.read`
- `content.upload`
- `content.generate`
- `content.publish`
- `records.read`
- `audits.read`

不允许：

- 管理客户。
- 管理后台人员。
- 修改系统配置。
- 操作缓存。
- 修改 Skill。
- 刷新股票字典。

## 角色迁移计划

1. 修改 `business/investment/auth_service.py` 的 `ROLE_PERMISSIONS`。
2. 新增 `content_operator` 角色。
3. 迁移现有角色：
   - `uploader` -> `content_operator`
   - `poster` -> `content_operator`
   - `technical_admin` -> `admin`，如仍需技术管理员角色需另行确认。
   - `readonly` -> `content_operator` 或停用，建议默认停用，避免只读账号继续访问后台。
4. 默认账号调整：
   - `admin / password / admin`
   - `poster1 / password / content_operator`
   - `poster2 / password / content_operator`
   - `poster3 / password / content_operator`
5. 保留旧角色识别兼容一版：
   - 登录时如果读到 `poster` 或 `uploader`，按 `content_operator` 权限处理。
   - 后台保存角色时只允许保存 `admin` 或 `content_operator`。

## 客户 CRUD 完善计划

### 后端

1. 扩展 `list_users`：
   - 支持 `keyword` 参数。
   - 匹配 `openid`、`name`、`institution`、`mobile`。
2. 新增客户启用接口：
   - `POST /api/investment/users/{openid}/enable`
3. 保留停用接口：
   - `POST /api/investment/users/{openid}/disable`
4. 明确删除语义：
   - 不做物理删除。
   - “删除客户”在页面上表现为“停用客户”。
5. 导入权限拆分：
   - 导入使用 `customers.import`。
   - 导出使用 `customers.export`。
6. 查询和保存权限改为：
   - 列表：`customers.read`
   - 保存：`customers.write`
   - 启停：`customers.enable`

### 前端

1. 客户面板增加搜索框：
   - OpenID / 姓名 / 机构 / 手机号。
2. 用户列表增加手机号列。
3. 停用客户后显示“启用”按钮。
4. 按钮权限改为：
   - 保存：`customers.write`
   - 导入：`customers.import`
   - 导出：`customers.export`
   - 启停：`customers.enable`

### 测试

1. `content_operator` 无法访问客户管理 API。
2. `admin` 可新增、编辑、启用、停用客户。
3. 客户搜索能按 OpenID、姓名、机构、手机号命中。
4. 停用客户不能使用微信端服务。
5. 启用客户恢复微信端服务权限。

## 后台人员 CRUD 完善计划

### 后端

1. 后台人员列表：
   - `GET /api/investment/admin-users`
   - 权限：`admin_users.read`
2. 新增/更新后台人员：
   - `POST /api/investment/admin-users`
   - 权限：`admin_users.write`
   - 只允许角色：`admin`、`content_operator`
3. 启用/停用后台人员：
   - `POST /api/investment/admin-users/{username}/status/{enable|disable}`
   - 权限：`admin_users.write`
4. 重置密码：
   - `POST /api/investment/admin-users/{username}/password`
   - 权限：`admin_users.reset_password`
5. 错误处理：
   - 不存在的账号返回错误，不返回成功。
   - 禁止停用最后一个启用的 `admin`。
   - 禁止把最后一个启用的 `admin` 改成 `content_operator`。
6. 删除语义：
   - 不做物理删除。
   - 删除操作等同停用。

### 前端

1. 后台人员面板只对 `admin` 可见。
2. 角色下拉只保留：
   - 主管理员
   - 内容上传发布
3. 后台人员列表显示：
   - 账号
   - 角色
   - 状态
   - 最近登录
   - 操作
4. 操作按钮：
   - 编辑角色
   - 启用/停用
   - 重置密码

### 测试

1. `content_operator` 无法访问后台人员列表。
2. `admin` 可创建 `content_operator`。
3. `admin` 可重置密码。
4. 不存在账号启停/重置密码返回错误。
5. 最后一个启用 `admin` 不能被停用或降级。
6. API 响应不返回 `password_hash`。

## 后台页面权限计划

### 页面权限

- 用户管理：`customers.read` 或 `admin_users.read`
- 利率内容：`content.read`
- 转债内容：`content.read`
- 业务记录：`records.read`
- 投资 Skill：`skills.read`
- 系统配置：`config.read` 或 `stocks.read`
- 健康检查：`health.read`

### 按钮权限

- 客户保存：`customers.write`
- 客户导入：`customers.import`
- 客户导出：`customers.export`
- 客户启停：`customers.enable`
- 后台人员保存：`admin_users.write`
- 后台人员重置密码：`admin_users.reset_password`
- 内容保存草稿：`content.upload`
- 内容生成：`content.generate`
- 内容设为生效：`content.publish`
- 记录导出：`records.export`
- 缓存清理：`cache.write`
- 配置保存：`config.write`
- Skill 修改：`skills.write`
- 股票字典刷新：`stocks.write`

## 审计补齐计划

新增审计动作：

- `customer.create`
- `customer.update`
- `customer.enable`
- `customer.disable`
- `customer.import`
- `customer.export`
- `admin_user.create`
- `admin_user.update_role`
- `admin_user.enable`
- `admin_user.disable`
- `admin_user.reset_password`

审计记录内容：

- 操作人
- 动作
- 目标类型
- 目标 ID
- 关键字段变化摘要
- 操作时间

敏感信息规则：

- 不记录密码明文。
- 不记录密码 hash。
- 手机号可保留完整值或后续按展示需要脱敏。

## 实施顺序

1. 调整权限矩阵和角色兼容。
2. 更新默认账号迁移角色。
3. 改后端 API 权限名，并保留旧权限兼容。
4. 完善客户搜索、启用接口和软删除语义。
5. 完善后台人员错误处理、重置密码独立权限、最后管理员保护。
6. 更新前端页面和按钮权限。
7. 补操作审计。
8. 补测试并跑用户系统相关回归。

## 验收标准

1. 客户不能登录后台 Web。
2. 后台人员不能自动获得微信端客户服务权限。
3. `content_operator` 只能访问内容、记录、审计相关功能。
4. `content_operator` 不能管理客户、后台人员、配置、缓存、Skill、股票字典。
5. `admin` 可以完成客户和后台人员全部管理动作。
6. 最后一个启用 `admin` 不能被停用或降级。
7. 客户搜索支持 OpenID、姓名、机构、手机号。
8. 客户停用后微信端服务被拒绝，启用后恢复。
9. 后台人员 API 不返回密码 hash。
10. 客户和后台人员关键管理动作均写入审计。
