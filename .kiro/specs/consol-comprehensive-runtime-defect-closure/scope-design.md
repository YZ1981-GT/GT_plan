# D5 合并范围确认式建树：独立子设计

日期：2026-10-08

## 1. 目标与边界

D5 把“用户已经确认当前合并范围”从项目向导状态中独立出来。服务端保存确认事实、规范化树快照、确定性指纹、版本号和一次生成的角色批次；计算服务只消费已确认版本。现有 `consol_group_tree` 是唯一建树真源，旧 `consol_scope`、旧树接口和旧读路径继续兼容，但不会被本方案自动迁移或改写。

本轮只写代码和隔离测试，不执行真实开发库迁移、不重启现有服务、不提交或推送。真实 PG 写路径和真实集团 UAT仍需独立授权。

## 2. 输入归一化与树真源

确认请求只携带客户端看到的 `fingerprint`、`revision`，以及可选的确认备注；客户端不得提交可直接持久化的树。服务端按明确 `project_id`：

1. 加载未删除项目并校验 `report_scope=consolidated`；年度使用项目统一的 `audit_year`，旧项目按现有树服务的年度解析逻辑处理。
2. 调用 `build_group_tree`/`derive_group_tree`，不复制角色推导算法。
3. 用 `to_dict` 得到树载荷，再删除诊断中不稳定的运行信息，只保留用于确认和计算身份的规范字段；节点按树先序遍历，`position` 按遍历顺序连续编号。
4. 对字符串三码做 `strip`；上级代码等于自身企业代码视为顶层，不建立自环。三者全等只影响树形去重，不自动完成用户确认。
5. 对规范 JSON 使用固定 UTF-8、排序键、紧凑分隔符计算 SHA-256。不得把时间戳、随机 UUID、数据库行 ID 或诊断文本纳入指纹。

## 3. 持久化模型

### 3.1 `consol_scope_confirmations`

一行代表一个项目/年度/报表口径下的一次确认版本：

- `id`：UUID 主键；`project_id`、`year`、`report_scope` 是业务边界。
- `revision`：同一项目/年度/口径的单调版本，从 1 开始。
- `fingerprint`：64位小写 SHA-256；历史版本不要求指纹全局唯一，树形回退时可创建新 revision 并复用曾出现的指纹。
- `canonical_payload`：JSONB 规范树与节点摘要。
- `status`：`active` 或 `superseded`；同一边界最多一个 active。
- `confirmed_by`：确认用户；`confirmed_at`：确认时间；`created_at`/`updated_at`：审计时间。

### 3.2 `consol_scope_confirmation_nodes`

一行代表确认版本中的一个树角色快照：

- `confirmation_id` 外键、`node_key`、`role`、`kind`、`company_code`、`project_id`、`host_project_id`、`parent_node_key`、`position`。
- 唯一键为 `(confirmation_id, node_key)`；稳定身份为 `node_key`，差额节点的金额承载仍由 `host_project_id` 表达。
- 快照只保存角色投影，不创建新的 `projects` 企业或复制 TB/分录金额。

本设计选择按 `(project_id, year, report_scope, revision)` 唯一，并保证每个边界最多一个 `active`。同一 active 指纹重试幂等；历史 superseded 指纹允许再次出现，以支持树形变更后回到既有形态仍能创建新 revision。

## 4. CAS、权限与事务

预览是只读，返回当前服务端 `revision`、`fingerprint`、canonical tree、`pending_legacy` 和 `confirmed`。确认端点必须：

- 先用 `assert_project_permission(..., "edit")` 校验项目级权限；
- 直接查询 `Project.consol_lock`，锁定或项目不存在时 fail-closed；不使用资源反查型 `check_consol_lock`；
- 重新派生服务端树，校验请求 fingerprint 与服务端当前 fingerprint 相等；
- 校验 `expected_revision` 与服务端当前 revision 相等。没有当前版本时 expected revision 必须为 0；
- CAS 失败返回 409，错误码分别为 `SCOPE_FINGERPRINT_CONFLICT` 或 `SCOPE_REVISION_CONFLICT`，并返回最新预览，客户端必须重读后再确认；
- 在一个数据库事务中 flush 确认主表、节点快照和角色稳定键，router 统一 commit。service 不 commit。

相同 fingerprint 的重复确认是幂等成功；不同 fingerprint 的新确认只在 CAS 通过后生成一次新版本。并发数据库唯一约束异常不得被伪装成成功。

## 5. 角色语义

角色批次只在合并范围确认成功时生成：

- 根 `consol`、根 `consol_elim`、根 `parent` 按现有 `consol_group_tree` 角色生成；
- 有分公司时 `parent` 是母分汇总，子节点保留 `branch_elim + hq + branch`；`parent` 不重命名为 `hq`；
- `consol_elim`/`branch_elim` 是差额角色，`project_id` 可为空，使用 `host_project_id` 承载分录；
- 单体和合并企业不会因为角色快照重复创建，金额计算仍由现有 `data_leaves`、`load_calc_basis` 和合并分录口径完成；
- 每个节点的 `node_key` 在一个确认版本内唯一，并与旧树 API 使用的稳定键相同。

## 6. legacy 兼容与计算门

没有 D5 确认版本的项目仍可读取旧树接口和预览。仅当项目早于 V183 生效时间，且本项目/年度存在迁移前创建的 `consol_scope`、`consol_trial`、`consol_worksheet` 或 `consol_worksheet_data` 数据时，预览才标记 `pending_legacy=true`；新项目或缺少旧数据证据时为 `false`。系统不根据旧数据自动产生确认事实，也不修改 legacy 数据。用户仍需显式确认当前范围。

涉及金额计算的公共入口在 `load_calc_basis` 增加 active confirmation gate：当 `consol_scope_confirmations` 表存在时（即 V183 已执行），未确认或当前树指纹与 active confirmation 不一致时抛出可识别的 `SCOPE_CONFIRMATION_REQUIRED`。V183 尚未执行时表不存在，确认门透明放行以兼容旧环境。唯一兼容例外是调用方显式设置 `allow_legacy_read=true` 且通过上述 legacy 边界判定；这仅延续迁移前已有项目的数据读取，默认计算路径仍拒绝未确认项目。树预览、诊断和确认预览不经过该门。为保持单元测试和纯逻辑兼容，显式传入的纯内存 `tree` 仍只在服务端能证明确认事实后使用，不能绕过门。

## 7. 前端接入

`ConsolScopeConfigDialog` 调用 D5 preview，并展示树摘要、revision、fingerprint、legacy pending 和确认状态；用户点击显式“确认当前合并范围”时提交 fingerprint/revision。确认成功后使用服务端返回值刷新，不把 `wizard_state.completed` 或本地三码弹窗状态当作确认事实。`BasicInfoStep` 的本地 `confirmedSelfKey` 只负责输入交互，`applySaved` 不得把已保存三码标成服务端 D5 confirmed。

允许改动向导组件、项目向导和项目 API path；不修改 `ConsolidationIndex.vue`、`ConsolNoteTab.vue`、`consolidationApi.ts`。

## 8. 验证矩阵

隔离测试使用 SQLite + ASGITransport，覆盖：项目权限拒绝、合并锁拒绝、fingerprint/revision CAS 冲突、重复确认幂等、三者全等仍需显式确认、上级等于自身去重、分公司三角色形状、稳定键唯一且无双计、未确认只读预览/计算拒绝、legacy pending 兼容，以及真实生产 service 函数而非测试拷贝。
