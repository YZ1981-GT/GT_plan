# 实施计划：平台数据联动契约、穿透与 stale 统一

## 任务总览

> 本节保留主任务索引；实际排期和执行以“详细落地拆解”为准。

- [ ] 1. LinkageContract 类型定义
  - [ ] 1.1 后端新建 `linkage_contract.py`
  - [ ] 1.2 前端新建 `linkageContract.ts`
  - [ ] 1.3 定义 source/target/status/confidence 枚举
  - [ ] 1.4 单元测试：schema 序列化与字段完整性
  - _Requirements: 1.1, 1.2_

- [ ] 2. LinkageFacade 服务
  - [ ] 2.1 新建 `linkage_facade_service.py`
  - [ ] 2.2 包装底稿、报表、附注、附件、AI 内容来源
  - [ ] 2.3 包装 stale 与 conflict 状态
  - [ ] 2.4 API：`GET /api/projects/{pid}/linkage/contracts`
  - _Requirements: 1.2, 4.1_

- [ ] 3. 路由解析统一
  - [ ] 3.1 前端新增 `resolveLinkageRoute`
  - [ ] 3.2 wp_code 统一解析为 wp_id
  - [ ] 3.3 替换 `useCrossModuleRefs` 等手写路径
  - [ ] 3.4 测试：wp_code 深链直接进入底稿编辑器
  - _Requirements: 1.3, 2.3, 6.3_

- [ ] 4. 统一穿透面板
  - [ ] 4.1 新建 `LinkageTraceDrawer.vue`
  - [ ] 4.2 展示来源、口径、状态、下游影响
  - [ ] 4.3 接入试算表、报表、底稿、附注高频入口
  - [ ] 4.4 视觉验收：current/stale/conflict/manual_override 显示清晰
  - _Requirements: 2.1, 2.2_

- [ ] 5. stale 三层一致
  - [ ] 5.1 梳理现有 stale 字段和事件处理器
  - [ ] 5.2 将静默 `pass` 改为 degraded 记录
  - [ ] 5.3 前端统一 stale badge 数据源
  - [ ] 5.4 集成测试：上游变化后 badge 更新
  - _Requirements: 3.1, 3.2, 3.3, 6.2_

- [ ] 6. 冲突调解联动
  - [ ] 6.1 LinkageContract 增加 conflict id
  - [ ] 6.2 穿透面板增加“去调解”入口
  - [ ] 6.3 冲突解决后刷新 linkage 状态
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 7. 签发一致性清单
  - [ ] 7.1 新建 `signoff_checklist_service.py`
  - [ ] 7.2 合伙人签发页展示一致性清单
  - [ ] 7.3 stale/conflict 阻断签发或要求确认
  - [ ] 7.4 测试：关键链路异常时不可直接签发
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 8. 验收
  - [ ]* pytest linkage/stale 相关测试通过
  - [ ]* Vitest 路由解析与穿透面板测试通过
  - [ ]* 手工 UAT：四表 → 底稿 → 附注 → 报告链路可追溯

---

## 详细落地拆解（执行以本节为准）

### P0-MVP：一周内最小可交付

- [ ] MVP-1. 前后端 `LinkageContract` 类型定义一致
- [ ] MVP-2. `wp_code` → `wp_id` route resolver 可用
- [ ] MVP-3. stale 更新失败不再静默吞错，写入 degraded 记录
- [ ] MVP-4. 试算表金额 → 底稿目标的单向 LinkageContract 可返回
- [ ] MVP-5. 测试文件落地：
  - `backend/tests/test_linkage_contract_schema.py`
  - `backend/tests/test_linkage_route_resolver.py`
  - `backend/tests/test_stale_degraded_contract.py`
  - `audit-platform/frontend/src/__tests__/resolveLinkageRoute.spec.ts`

### P0：LinkageContract 与 stale 最小闭环

- [ ] P0-1. 现状盘点
  - [ ] P0-1.1 梳理 trace/linkage/stale 相关 router、service、composable 调用方
  - [ ] P0-1.2 盘点手写路由跳转：`wp_code`、`report row`、`note_section`
  - [ ] P0-1.3 盘点 stale 静默 `pass` / 吞异常位置
  - [ ] P0-1.4 输出 `docs/reference/linkage-current-inventory.md`
  - _Requirements: 1.1, 3.3_

- [ ] P0-2. LinkageContract schema
  - [ ] P0-2.1 后端新建 `backend/app/schemas/linkage_contract.py`
  - [ ] P0-2.2 定义 source_type / target_type / status / confidence 枚举
  - [ ] P0-2.3 前端新建 `src/types/linkageContract.ts`
  - [ ] P0-2.4 增加 JSON schema 示例 `docs/reference/linkage-contract.schema.json`
  - [ ] P0-2.5 pytest + Vitest：字段完整性和枚举一致性
  - _Requirements: 1.1, 6.1_

- [ ] P0-3. 路由解析器
  - [ ] P0-3.1 后端 API：`POST /api/projects/{pid}/linkage/resolve-route`
  - [ ] P0-3.2 支持 workpaper: wp_id / wp_code 两种输入
  - [ ] P0-3.3 支持 report row_code、note section/table/cell
  - [ ] P0-3.4 前端 `resolveLinkageRoute(contract)`
  - [ ] P0-3.5 测试：wp_code 可直接解析到 WorkpaperEditor
  - _Requirements: 1.3, 2.3, 6.3_

- [ ] P0-4. stale 非静默治理
  - [ ] P0-4.1 定位 `event_handlers.py` 中 stale 静默吞错
  - [ ] P0-4.2 新增 degraded 记录服务或复用 `event_cascade_health`
  - [ ] P0-4.3 stale 字段缺失时返回 degraded，不再静默成功
  - [ ] P0-4.4 pytest：模拟字段缺失，断言产生 degraded 记录
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] P0-5. 四表→底稿→附注最小链路
  - [ ] P0-5.1 为试算表金额生成 LinkageContract
  - [ ] P0-5.2 为底稿审定表金额生成 LinkageContract
  - [ ] P0-5.3 为附注单元格生成 LinkageContract
  - [ ] P0-5.4 UAT：从 TB 金额穿透到底稿，再到附注
  - _Requirements: 1.2, 2.1, 2.2_

### P1：统一穿透面板与冲突联动

- [ ] P1-1. LinkageFacade
  - [ ] P1-1.1 新建 `backend/app/services/linkage_facade_service.py`
  - [ ] P1-1.2 包装 `linkage_service`、`wp_note_linkage_service`、`report_trace_service`
  - [ ] P1-1.3 包装 conflict 与 stale 状态
  - [ ] P1-1.4 增加旧 trace API 与新 facade 差异对账日志
  - [ ] P1-1.5 API：`GET /api/projects/{pid}/linkage/trace`
  - _Requirements: 1.2, 4.1_

- [ ] P1-2. LinkageTraceDrawer
  - [ ] P1-2.1 新建 `components/common/LinkageTraceDrawer.vue`
  - [ ] P1-2.2 展示来源、口径、金额、状态、影响范围
  - [ ] P1-2.3 支持跳转与复制引用
  - [ ] P1-2.4 试算表、报表、底稿、附注各接一个入口
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] P1-3. 冲突调解联动
  - [ ] P1-3.1 LinkageContract 增加 `conflict_id`
  - [ ] P1-3.2 穿透面板展示 conflict badge
  - [ ] P1-3.3 跳转 `ConflictResolutionPanel`
  - [ ] P1-3.4 冲突解决后刷新 LinkageContract 状态
  - _Requirements: 4.1, 4.2, 4.3_

### P2：签发一致性清单

- [ ] P2-1. 签发清单服务
  - [ ] P2-1.1 新建 `signoff_checklist_service.py`
  - [ ] P2-1.2 检查四表、调整、底稿、附注、报告正文、AI 内容
  - [ ] P2-1.3 输出 blocking/warning/info 三类结果
  - [ ] P2-1.4 每个结果带 LinkageContract 或 route
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] P2-2. 合伙人签发页接入
  - [ ] P2-2.1 签发页显示一致性清单
  - [ ] P2-2.2 blocking 项阻断签发
  - [ ] P2-2.3 warning 项允许合伙人显式确认
  - [ ] P2-2.4 确认动作记录审计日志
  - _Requirements: 5.1, 5.2, 5.3_

### 验收与回归

- [ ] UAT-1 助理：TB 金额 → 底稿 → 附注穿透成功
- [ ] UAT-2 经理：调整分录批准后，相关报表/附注 stale 状态更新
- [ ] UAT-3 QC：从穿透面板进入冲突调解并解决
- [ ] UAT-4 合伙人：签发页显示 stale 阻断项并可跳转
- [ ] CI-1 LinkageContract schema pytest / Vitest 全绿
- [ ] CI-2 stale degraded 测试通过
- [ ] CI-3 route resolver 测试覆盖 wp_code/report/note
- [ ] CI-4 旧 trace API 与 LinkageFacade 对账无阻断差异
