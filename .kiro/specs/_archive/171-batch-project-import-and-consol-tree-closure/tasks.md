# 任务：批量建项与合并企业树导入收口

需求见 requirements.md，设计见 design.md。按交付单元执行；完成项必须有代码和通过证据，浏览器写入只使用【测试】项目。

- [x] 0. 现状、设计与基线
  - [x] 0.1 追踪平台/合并三处入口、五个 API、模板/解析/建项/自动根/树/链接链路，区分空白模板回导与现有树回导
  - [x] 0.2 浏览器只读复现原样模板 4 行可导入、确认按钮首屏外；核对事务、权限、重复键、多年度和测试缺口
  - [x] 0.3 完成 requirements/design/tasks；确认只复用一套内核，迁移号实施时动态取
  - [x] 0.4 登记 INDEX；基线：后端 58 passed / 16.90s，前端 7 passed / 1.88s（既有 Vue 未 stub warning）

- [x] 1. P0 正确性与安全
  - [x] 1.1 拆出工作簿协议：数据 sheet 零示例、示例独立、四类下拉、版本/表头/整数年度/文件膨胀限制、openpyxl 离事件循环
  - [x] 1.2 预校验重复键改 `(code,year,scope)`，一次预取 DB，库存覆盖后构树；循环/重复/构树异常阻断
  - [x] 1.3 修导入事务：legacy 逐行 SAVEPOINT、计划 apply 整批原子；失败回执零假成功，自动根按 `(ultimate,year)`
  - [x] 1.4 batch create 仅 admin/partner/manager；选中项目导出全集合 readonly 鉴权；错误不泄露内部异常
  - [x] 1.5 manager 新建项目同事务挂经理委派与 edit 成员；新根同样处理，复用根团队不动

- [x] 2. 单次上传计划与性能
  - [x] 2.1 动态分配 V220/R220；新增计划 ORM、状态/幂等键/过期/JSONB/索引三层一致，临时 schema PG 正反向通过并已由 MigrationRunner 应用
  - [x] 2.2 实现 canonical request/hash、DB 动作分类、summary、最终树预览和错误工作簿
  - [x] 2.3 新增 validate/apply/status/errors API；生产 UI 确认只传 validation_id + idempotency_key，旧 import 走安全兼容路径
  - [x] 2.4 apply 锁计划、受影响年度项目锁、关系全集 CAS，整批原子创建/更新/自动根/成员/链接/回执；响应丢失重放
  - [x] 2.5 批量预取、延迟 ORM flush 和新项目经理批量初始化消除逐行往返；真 PG 回滚基准 500 行：admin 计划/执行 324.8/344.9ms，manager 353.9/521.9ms

- [x] 3. 现有树导出与关系回导
  - [x] 3.1 安全保留选中项目导出；新增合并根当前树导出，服务端推导成员并逐项目鉴权
  - [x] 3.2 模板追加 action/project_id/base_hash；现有行只许更新三码关系，新行可创建，跳过显式可见
  - [x] 3.3 扩展集团关系单一入口支持显式 parent/ultimate/relation、counterpart 同步和延迟年度链接重算
  - [x] 3.4 批量关系更新写 ORM + wizard_state + 审计；企业级双口径 CAS、年度全集锁、最终图循环/冲突、归档与无权 fail-closed

- [x] 4. 前端体验
  - [x] 4.1 BatchImportDialog 增加 project/consolidation mode；合并模式提供新模板和当前树导出
  - [x] 4.2 改 80vh 步骤式弹窗、固定操作栏、两级展开、summary 与异常/改动标签，窄屏 CSS 收口
  - [x] 4.3 上传一次、计划确认/轮询/幂等恢复；失败保留文件和预览，支持错误 Excel，展示真实中文错误
  - [x] 4.4 平台、左栏与合并入口刷新正确；合并成功可进入新根，未选根时不误导

- [x] 5. 自动化验证
  - [x] 5.1 后端模板/解析/动作/多年度/原子回滚/成员/幂等/CAS 测试；故障注入发生在真实 production 路径下一层 flush
  - [x] 5.2 TestClient 角色矩阵、混合授权 ID、计划归属、归档与响应信封；PG 迁移/回滚/唯一约束
  - [x] 5.3 前端 mode/步骤/上传一次/错误恢复/固定 footer/TreeV2 测试，scoped vue-tsc、ESLint 与相关回归
  - [x] 5.4 关键反向断言覆盖：改表头、空模板、同键异载荷、flush 中断、关系 CAS、隐藏 counterpart 变化、网络丢响应均在预期断言打红；相关选集全绿无需 HEAD 失败归因

- [x] 6. 浏览器与收尾
  - [x] 6.1 原样新模板 0 行、错误模板中文提示、500 行预览性能与桌面/390px 弹窗走查
  - [x] 6.2 【测试】集团完成导出→改关系→预览差异→应用→树刷新→幂等重放；恢复原关系并清理新建项目
  - [x] 6.3 对账 DB 项目/成员/委派/计划/审计和临时文件；更新验收记录、INDEX 与记忆，诚实登记外部依赖

## 验收记录

### 收尾轮（2026-11-15）—— 补齐任务 6 并修复 4 处未接线缺口

**基线复跑先暴露 4 处真实缺口**（`bb29a49f6` 已入库 `batch_project_status_lock` 服务与对应测试，但 `routers/batch_project.py` 从未接线；4 例红 / 113 passed）：

| # | 缺口 | 修法（`backend/app/routers/batch_project.py`） |
|---|---|---|
| 1 | `GET /batch-imports/{id}` 无有界锁等待，apply 持锁期间可能读到旧 `validated` 快照 | 接 `with_status_lock_timeout`（PG `lock_timeout` 1.5s），超时转 503 `BATCH_PLAN_STATUS_BUSY` + `Retry-After: 1` |
| 2 | 陈旧计划（权限/库存/基线变化）抛 409 但不落失败态，客户端无法凭 status 恢复 | `is_stale_plan_error(exc)` 时调 `mark_plan_failed` 持久化 `failure_error_code` |
| 3 | `db.commit()` 确认丢失报 500，客户端误以为零写入 | commit 异常单独捕获 → 503 `BATCH_PLAN_RESULT_UNKNOWN`，由 status 读真实终态 |
| 4 | `IntegrityError` 只返回字符串 detail，无 `error_code` | 统一 409 + `detail={"error_code": "BATCH_PLAN_STALE", "message": ...}` |

验证：后端选集 **117 passed**（原 113 + 4，零新增失败）、PG `test_batch_project_status_lock_pg` + `test_batch_project_migration_pg` **3 passed**、前端 `BatchImportDialog.spec.ts` + `batchProjectImport.spec.ts` **22 passed**。

**6.1 模板与上传边界**（API 实测 + 浏览器走查）

| 场景 | 实测结果 |
|---|---|
| 模板结构 | sheets = 数据 / 填写示例 / 说明事项 / `_GT_OPTIONS` / `_GT_META`；数据 sheet `A1:M501` 仅表头，**数据行 0**；示例 4 行在独立 sheet；`_GT_META` 版本 2 + mode |
| 原样模板上传 | 200 但 `valid=false`，`summary.error=1`，中文提示「数据 sheet 没有可导入的项目，请填写后重新上传」，**不创建任何项目** |
| 改表头 | 400「模板表头已被修改或列顺序不正确，请重新下载模板」 |
| 小数年度 `2025.1` | 200 `valid=false`，行内「审计年度必须为4位整数，不能包含小数」 |
| 500 行（合法 USCC） | **0.301s**，`valid=true`，`create=500 / error=0`，`tree_preview` 1 组 |
| 390×844 窄屏 | 弹窗 96vw、footer 固定可见、主体独立滚动；步骤条按任务 4.2 设计在 ≤680px 隐藏 |
| console | 无本 spec 相关 error；仅 `GtStatusTag` 的 `type` prop 警告（基线既有，与批量建项无关） |

**6.2 【测试】集团全链路**（年度 2096，全部经平台路径）

1. `gt-closure-6201`（project 模式）：2 个单户 + `auto_root=1` → apply 200，`created_count=2 / auto_root_count=1`，自动根 `91119999000000001W（自动创建合并项目）` 出现在 `/api/projects/tree?year=2096`；重复 apply 同计划返回 `idempotent=true`。
2. 合并根导出 `GET /api/projects/{root}/group-import-template`：3 行，含 `project_id` / `action=更新集团关系` / `base_hash`。
3. 改子公司 A 的 parent 为 B → consolidation validate：`update=1 / unchanged=2 / error=0`，预览树含 A 与 B。
4. apply `gt-closure-6202` → `updated_count=1`；树刷新后 **B 的 children 含 A**；重复 apply `idempotent=true`。
5. 不改关系再导出 validate：`unchanged=3 / error=0`（基线摘要 CAS 正确，未误报陈旧）。
6. 恢复原关系 `gt-closure-6204`（A parent → root）：`updated=1`，树核对 root children = [A, B]、B children 为空。

**6.3 对账与清理**

- 项目：3 个新建项目（2 单户 + 1 自动根）经 `DELETE /api/projects/{id}` 全部 `deleted: true`；DB 复核 `audit_year=2096` 本次 3 行 `is_deleted=t`。
- 审计：`app_audit_log` 两条 `project.group_relationship.batch_change`，`details` 含完整 `before` / `after` / `synced`。
- 计划：`project_batch_import_plans` 本次 `applied` 3 条（`6201` / `6202` / `6204`）保留为审计轨迹；`invalid` / `validated` 若干条来自本次边界探测与既有 E2E 残留，按设计保留不删。
- 临时文件：仓库根 `tmp_batch_import_closure/` 已整体删除（探针、模板、500 行文件、导出件）。

**范围外登记（未改）**

- `GtStatusTag` 在 `ProjectTreeNode` 收到空字符串 `type`，触发 Vue prop 校验警告（基线既有，属项目状态标签，非批量建项）。
- `project_batch_import_plans` 无自动清理任务：`validated` 计划过期后仅状态读为 `expired`，行仍留库；如需按 TTL 物理清理应另立 spec。

**外部依赖（如实登记）**

- 6.2 的浏览器交互走查在 API 层完成全链路（导出/校验/应用/树/幂等），**弹窗内的拖拽上传与错误 Excel 下载按钮点击**未在浏览器内逐点复测（已由前端 22 例单测 + 6.1 的弹窗结构走查覆盖）；如需完全 UI 级复测需在有真实【测试】集团的可写环境重跑。
- 500 行**确认提交**性能沿用任务 2.5 的真 PG 基准（admin 计划/执行 324.8/344.9ms，manager 353.9/521.9ms）；本轮补测的是校验段 0.301s，未重复压测 apply 段。
