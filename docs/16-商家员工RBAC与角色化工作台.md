# 商家员工 RBAC 与角色化工作台

## 1. 实现目标

FashionAgent 保留一个统一入口 `/admin.html`，但不再使用一个拥有全部权限的 `admin` 角色。商家员工按职责使用独立账号，后端逐接口验证权限，前端只负责展示对应工作区。

当前角色：

```text
customer
customer_service
supervisor
tenant_admin
developer
```

旧 `admin` 只用于迁移兼容，迁移后会转换为 `tenant_admin`。

## 2. 权限模型

权限在 `app/core/permissions.py` 中集中定义，由 `require_permission()` 在服务端执行。

| 能力 | customer_service | supervisor | tenant_admin | developer |
|---|---:|---:|---:|---:|
| 今日待办、人工处理、订单、未解决案例 | 是 | 是 | 是 | 否 |
| 知识草稿和测试 | 是 | 是 | 是 | 仅测试 |
| 退款审核 | 否 | 是 | 是 | 否 |
| 知识审核、发布、回滚 | 否 | 是 | 是 | 否 |
| 业务质检 | 否 | 是 | 是 | 是 |
| 员工账号、角色、租户配置 | 否 | 否 | 是 | 否 |
| 人工操作审计 | 否 | 否 | 是 | 是 |
| Agent Trace、RAG、工具、记忆、安全边界、系统健康 | 否 | 否 | 否 | 是 |

关键约束：

- 开发人员不能审批退款。
- 普通客服不能发布知识库。
- 主管不能管理账号或修改租户配置。
- 租户管理员不能查看完整技术 Trace。
- 所有业务和技术数据均按 JWT 对应的 `tenant_id` 查询。
- 前端隐藏菜单不是安全边界，手动调用无权 API 仍返回 403。

## 3. 登录与身份

`POST /api/auth/login` 支持可选 `tenant_id`。用户名只要求租户内唯一；未提供租户且同名账号存在于多个租户时，登录会拒绝而不会猜测身份。

`GET /api/auth/me` 返回：

```json
{
  "id": 10,
  "username": "service_demo",
  "tenant_id": 1,
  "role": "customer_service",
  "role_label": "客服运营",
  "permissions": ["order.read", "ticket.read"],
  "home_view": "dashboard"
}
```

JWT 只表达登录时身份。每次请求仍重新读取数据库，并检查账号是否启用、租户和角色是否与 Token 一致。因此停用账号或修改角色后，旧 Token 立即失效。

## 4. 角色化前端

统一入口：

```text
/admin.html
```

导航元素使用 `data-permission` 声明展示权限，`admin-permissions.js` 根据 `/api/auth/me` 返回的权限集合控制可见性。用户手动输入无权 Hash 时显示 403 工作区。

默认首页：

- `customer_service`：今日待办。
- `supervisor`：今日待办。
- `tenant_admin`：账号管理。
- `developer`：Agent Trace。

主要工作区：

- 客服：今日待办、人工处理、订单查询、未解决案例、知识草稿。
- 主管：客服能力、退款审核、知识审核与发布、业务质检。
- 租户管理员：主管能力、账号管理、租户设置、操作审计。
- 开发人员：Agent Trace、AgentOps、记忆系统、操作审计、知识测试。

## 5. 业务质检与技术诊断分离

业务质检接口：

```text
GET /api/admin/quality-report
```

只返回：

- 用户问题。
- AI 回复。
- 是否自动解决。
- 是否转人工。
- 业务化问题说明。
- 经过字段白名单清洗的引用资料。
- 建议处理动作。

不会返回工具参数、路由置信度、RAG 分数、Chunk 标识、内部错误详情或节点步骤。

完整技术诊断只保留在：

```text
GET /api/agentops/traces
GET /api/agentops/traces/{id}
GET /api/agentops/trace-sessions/{session_id}
GET /api/agentops/rag/stats
GET /api/agentops/tools/stats
GET /api/agentops/memories/stats
GET /api/agentops/boundaries/events
GET /api/agentops/health
```

## 6. 员工账号与租户设置

账号接口：

```text
GET    /api/admin/users
POST   /api/admin/users
PATCH  /api/admin/users/{id}
POST   /api/admin/users/{id}/reset-password
```

服务端约束：

- 只能操作当前租户员工。
- 角色必须属于允许分配的员工角色。
- 不能修改自己的角色或停用自己。
- 不能停用或降级最后一个启用的 `tenant_admin`。
- 同一租户用户名重复返回 409，不同租户可以使用相同用户名。
- 密码只保存哈希。

租户设置接口：

```text
GET   /api/admin/tenant-settings
PATCH /api/admin/tenant-settings
```

当前支持商家名称、联系人和退款自动审批阈值。退款服务每次提交时读取当前租户阈值，模型不能决定退款金额或风险等级。

## 7. 人工审计

`admin_audit_event` 记录人的管理行为，与 Agent Trace 分开：

- 创建、启停、改角色、重置员工密码。
- 修改租户设置和退款阈值。
- 批准或拒绝退款。
- 审核、发布、激活或回滚知识版本。
- 查看敏感技术 Trace。

审计查询始终按租户过滤。

## 8. 数据库迁移

执行：

```powershell
D:\CondaEnvs\fashionagent\python.exe scripts\migrate_staff_roles.py --database data\fashion.db
```

迁移内容：

1. 旧 `admin` 转换为 `tenant_admin`。
2. 用户名唯一约束改为 `(tenant_id, username)`。
3. 角色字段扩展到 50 字符。
4. 创建 `admin_audit_event` 和索引。
5. 验证不存在旧 `admin`。
6. 验证每个租户至少有一个启用的 `tenant_admin`。

迁移幂等，可使用 `--verify-only` 只做结构和数据验证。

## 9. 本地种子账号

新建空数据库时，`scripts/seed_data.py` 可创建：

```text
service_demo     customer_service
supervisor_demo  supervisor
admin            tenant_admin
developer_demo   developer
```

密码分别由以下环境变量提供，不共享默认密码：

```text
SEED_SERVICE_PASSWORD
SEED_SUPERVISOR_PASSWORD
SEED_ADMIN_PASSWORD
SEED_DEVELOPER_PASSWORD
```

已有数据的数据库不会被种子脚本覆盖。可由租户管理员在“账号管理”工作区创建其他员工账号。

## 10. 测试验收

自动化测试覆盖：

- 五种身份的权限矩阵。
- 前端菜单、默认首页和无权 Hash。
- 退款审核、知识发布、账号和租户设置权限。
- 角色变化导致旧 Token 失效。
- 账号、审计、业务质检和 AgentOps 租户隔离。
- 最后管理员与自我降权保护。
- 租户退款阈值真实参与退款风险判断。
- 业务质检响应不泄露技术字段。
- 迁移幂等和租户内用户名唯一。

当前项目版本：`0.6.0`。

## 11. 当前模型边界

当前每个员工只有一个角色，适合个人项目和现阶段演示。若未来需要同一员工同时拥有多个角色，可新增 `role`、`permission`、`user_role` 和 `role_permission` 关联表；在此之前不引入复杂多角色模型。
