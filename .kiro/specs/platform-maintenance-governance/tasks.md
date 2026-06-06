# 实施计划：平台治理、维护账本与工程卡点

## 任务总览

> 本节保留主任务索引；实际排期和执行以“详细落地拆解”为准。该 spec 建议最先启动。

- [ ] 1. 四本账初始化
  - [ ] 1.1 新建 API 契约账
  - [ ] 1.2 新建组件账
  - [ ] 1.3 新建数据口径账
  - [ ] 1.4 新建质量账
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 2. 自动规模快照
  - [ ] 2.1 新建 `backend/scripts/analyze/snapshot_scale.py`
  - [ ] 2.2 统计 routers/services/models/views/components/composables/migrations/tests
  - [ ] 2.3 写入文档标记区块
  - [ ] 2.4 CI 检查快照是否过期
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. PR 治理卡点
  - [ ] 3.1 新增 PR checklist 模板
  - [ ] 3.2 检查新增页面是否声明全局组件
  - [ ] 3.3 检查新增金额字段是否声明 Decimal 方式
  - [ ] 3.4 检查新增路由是否配权限和错误码
  - [ ] 3.5 检查 AI 与穿透功能是否接入治理契约
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 4. 超大文件与重复模块治理
  - [ ] 4.1 扩展 `check_hotspot_files`
  - [ ] 4.2 建立 composable 注册表
  - [ ] 4.3 建立 service 同族能力注册表
  - [ ] 4.4 建立公式引擎族盘点 ADR
  - [ ] 4.5 CI 提示新增重复能力
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 5. SQL 列契约
  - [ ] 5.1 新建 `check_sql_column_contract.py`
  - [ ] 5.2 扫描 ORM 列引用
  - [ ] 5.3 扫描裸 SQL 列引用
  - [ ] 5.4 与 ORM/migration 列集合比对
  - [ ] 5.5 CI 接入
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 6. 上线 smoke checklist
  - [ ] 6.1 新建 `docs/deployment/platform-smoke-checklist.md`
  - [ ] 6.2 编写 OnlyOffice/WOPI、Redis、Postgres、Worker、SSE 检查项
  - [ ] 6.3 增加 degraded 状态总览
  - [ ] 6.4 增加备份恢复演练记录模板
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 7. 验收
  - [ ]* 本地运行所有新增 check 脚本
  - [ ]* CI 能在新增裸路由/不存在列/规模快照过期时 fail
  - [ ]* 文档账本可被新人按路径找到并使用

---

## 详细落地拆解（执行以本节为准）

### P0-MVP：三天内最小可交付

- [ ] MVP-1. 四本账骨架文件创建完成
- [ ] MVP-2. `snapshot_scale.py` 可输出 JSON，不要求自动写回
- [ ] MVP-3. `check_sql_column_contract.py` 先 report 模式运行，不接 CI fail
- [ ] MVP-4. PR checklist 增加全局治理项
- [ ] MVP-5. 本地 smoke checklist 覆盖 backend/frontend/OnlyOffice/WOPI/Postgres/Redis
- [ ] MVP-6. 测试文件落地：
  - `backend/tests/scripts/test_snapshot_scale.py`
  - `backend/tests/scripts/test_check_sql_column_contract.py`
  - **验收标准**：后端 pytest mock DB in-memory 可跑；前端 vitest mock API shallow mount；核心 Property 对应 case 必须覆盖

### P0：账本、快照、SQL 契约、smoke 最小闭环

- [ ] P0-1. 四本账骨架
  - [ ] P0-1.1 新建 `docs/reference/api-contract-ledger.md`
  - [ ] P0-1.2 新建 `docs/frontend/component-ledger.md`
  - [ ] P0-1.3 新建 `docs/reference/data-semantics-ledger.md`
  - [ ] P0-1.4 新建 `docs/operations/quality-ledger.md`
  - [ ] P0-1.5 每本账先登记 10 条高频对象作为样例
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] P0-2. 自动规模快照
  - [ ] P0-2.1 新建 `backend/scripts/analyze/snapshot_scale.py`
  - [ ] P0-2.2 统计 routers/services/models/migrations/tests
  - [ ] P0-2.3 统计 views/components/composables
  - [ ] P0-2.4 输出 JSON + Markdown 表
  - [ ] P0-2.5 写入 `docs/architecture/scale-snapshot.md`
  - [ ] P0-2.6 测试：同一提交重复运行输出一致
  - _Requirements: 2.1, 2.2_

- [ ] P0-3. SQL 列契约
  - **⚠️ 注意**：仓库已有 `test_raw_sql_schema_contract.py`（表级）+ `test_raw_sql_column_contract.py`（列级 sqlglot），先确认覆盖范围再决定是否新建或扩展
  - [ ] P0-3.1 新建 `backend/scripts/check/check_sql_column_contract.py`
  - [ ] P0-3.2 收集 ORM mapped columns
  - [ ] P0-3.3 扫描 `select(Model.column)` 与 `Model.column`
  - [ ] P0-3.4 扫描裸 SQL 中常见 `alias.column`
  - [ ] P0-3.5 支持白名单文件 `backend/scripts/check/sql_column_contract_allowlist.json`
  - [ ] P0-3.6 首轮只 report 不 fail，生成 baseline
  - [ ] P0-3.7 第二轮切 CI fail 新增不存在列
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] P0-4. PR checklist
  - [ ] P0-4.1 新建或更新 `.github/pull_request_template.md`
  - [ ] P0-4.2 加入全局组件、Decimal、枚举、权限、AI、LinkageContract 检查项
  - [ ] P0-4.3 加入跨 spec 接口冻结检查项："如果本 PR 依赖跨 spec 共享原子（ProjectContext/PermissionMatrix/LinkageContract/EvidenceRef/useEditStateMachine），确认该原子已 merge main 且测试绿"
  - [ ] P0-4.4 在 `docs/operations/git-workflow.md` 引用
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] P0-5. 上线 smoke checklist
  - [ ] P0-5.1 新建 `docs/deployment/platform-smoke-checklist.md`
  - [ ] P0-5.2 本地开发检查：backend、frontend、OnlyOffice/WOPI、Redis、Postgres
  - [ ] P0-5.3 试点部署检查：migration、workers、SSE、degraded 状态
  - [ ] P0-5.4 生产部署检查：备份、恢复演练、容量、日志、告警
  - _Requirements: 6.1, 6.2, 6.3_

### P1：热点文件与重复模块治理

- [ ] P1-1. 超大文件 baseline
  - [ ] P1-1.1 扩展 `check_hotspot_files.py`
  - [ ] P1-1.2 建立 Vue 文件行数 baseline
  - [ ] P1-1.3 建立 Python service 行数 baseline
  - [ ] P1-1.4 对 `LedgerPenetration`、`DisclosureEditor`、`TrialBalance`、`ReportView` 标记专项治理
  - _Requirements: 4.1_

- [ ] P1-2. composable 注册表
  - [ ] P1-2.1 新建 `docs/frontend/composable-ledger.md`
  - [ ] P1-2.2 记录职责、调用方、是否 deprecated
  - [ ] P1-2.3 标记自动保存、编辑锁、表格、stale 等同族
  - [ ] P1-2.4 新增 composable PR 必须更新注册表
  - _Requirements: 4.2, 4.3_

- [ ] P1-3. service 同族能力注册表
  - [ ] P1-3.1 新建 `docs/architecture/service-capability-ledger.md`
  - [ ] P1-3.2 标记 formula、knowledge、linkage、stale、export 等同族服务
  - [ ] P1-3.3 新增 service PR 必须说明复用/替代关系
  - _Requirements: 4.2, 4.3_

- [ ] P1-4. 公式引擎族 ADR
  - [ ] P1-4.1 盘点 `formula_engine`、`report_engine`、`formula_parser`、`formula_unified` 等调用方
  - [ ] P1-4.2 diff 支持函数集和 DSL 语义
  - [ ] P1-4.3 形成 ADR：统一主引擎与迁移路线
  - _Requirements: 4.2_

### P2：CI 强化与运营化

- [ ] P2-1. CI 集成
  - [ ] P2-1.1 将规模快照检查接入 CI
  - [ ] P2-1.2 将 SQL 列契约接入 CI
  - [ ] P2-1.3 将新增裸组件/重复能力检查接入 CI
  - [ ] P2-1.4 所有新增检查先 warning 两周，再 fail 新增违规
  - [ ] P2-1.5 历史债务只走 baseline，不阻塞当期 PR
  - _Requirements: 2.3, 3.1, 4.3, 5.3_

- [ ] P2-2. 容量与备份演练
  - [ ] P2-2.1 增加容量规划模板
  - [ ] P2-2.2 增加备份恢复演练记录模板
  - [ ] P2-2.3 记录 Postgres、Redis、文件存储、OnlyOffice 依赖恢复步骤
  - _Requirements: 6.2_

### 验收与回归

- [ ] UAT-1 新人能根据四本账找到 API、组件、数据口径、测试范围
- [ ] UAT-2 新增不存在列引用时检查脚本能报错
- [ ] UAT-3 smoke checklist 可完成本地和试点环境检查
- [ ] CI-1 `snapshot_scale.py` 输出稳定
- [ ] CI-2 `check_sql_column_contract.py` baseline 生成成功
- [ ] CI-3 PR checklist 出现在新 PR 模板中
