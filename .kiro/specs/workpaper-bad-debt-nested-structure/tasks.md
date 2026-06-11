# Implementation Plan: 坏账准备明细表嵌套子表结构

## Overview

本实施计划将 D2-3 坏账准备明细表嵌套子表设计转化为增量编码任务。按 Phase 推进：基础设施（V070 迁移 + ORM + DTO）→ AutoSumEngine 纯计算 → NestedTableService CRUD → 预填 + AJE → 公式引擎集成 → 序列化 → API 路由 → 前端 Univer → 收尾。

铁律遵循：
- **三层一致**：V070 DDL + ORM（`BadDebtDetailRow` 继承 `TimestampMixin`）+ service 同步，配 R070 回滚 + 契约测试
- **service 只 flush 不 commit**，router 层统一 commit
- 新 router 必在 `backend/app/router_registry/workpaper.py` 数据组注册
- `ProvisionMethod` 用 `VARCHAR(30)` + 应用层枚举（不建 PG enum type）
- 12 条 correctness property 全部作为必做 PBT 子任务，`hypothesis max_examples=5`

## Tasks

- [ ] 1. 基础设施：V070 迁移 + ORM 模型 + DTO（三层一致）
  - [ ] 1.1 编写 V070 迁移 DDL 与 R070 回滚
    - 创建 `backend/migrations/V070__bad_debt_detail_rows.sql`：`CREATE TABLE IF NOT EXISTS bad_debt_detail_rows`，含 id(UUID PK)、wp_index_id(FK→wp_index ON DELETE CASCADE)、parent_row_id(self-FK ON DELETE CASCADE, nullable)、provision_method VARCHAR(30) nullable、sort_order INT NOT NULL DEFAULT 0、row_label VARCHAR(200) NOT NULL、amount_b ~ amount_n（13 个 NUMERIC(18,2) nullable）、version INT NOT NULL DEFAULT 1
    - 因 ORM 继承 `TimestampMixin`，DDL 必须显式写 `created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
    - 创建索引 `ix_bad_debt_rows_wp_index`、`ix_bad_debt_rows_parent`，及唯一偏索引 `uq_bad_debt_provision_method ON (wp_index_id, provision_method) WHERE provision_method IS NOT NULL`
    - 所有 CREATE/ALTER 用 `IF NOT EXISTS`；编写配对回滚 `backend/migrations/R070__bad_debt_detail_rows.sql`（DROP TABLE/INDEX）
    - _Requirements: 8.1, 1.3, 2.6_

  - [ ] 1.2 实现 `BadDebtDetailRow` ORM 模型 + `ProvisionMethod` 枚举
    - 在 `backend/app/models/` 新增模型文件，`BadDebtDetailRow(Base, TimestampMixin)`，字段与 V070 DDL 列一一对应（13 金额列 `Mapped[Decimal | None]` Numeric(18,2)、version、sort_order、row_label、provision_method String(30)）
    - 定义 `ProvisionMethod(str, Enum)`（INDIVIDUAL/CREDIT_RISK_AGING/CREDIT_RISK_OTHER/OTHER）+ `PROVISION_METHOD_LABELS` 中文映射
    - 配置 self-referential relationship：`children`（cascade="all, delete-orphan", order_by=sort_order）、`parent`（remote_side）；加 `is_parent`/`is_child` property
    - _Requirements: 1.1, 1.2, 2.1, 2.6, 8.1_

  - [ ] 1.3 定义 Pydantic DTO/Schema
    - 在 `backend/app/schemas/` 新增：`RowAmounts`（13 金额列值对象）、`CreateParentRowDTO`、`CreateChildRowDTO`、`UpdateRowDTO`（含 version 乐观锁必传）、`ChildRowResponse`、`ParentRowResponse`、`SummaryRowResponse`、`BadDebtTreeResponse`、`BalanceCheck`
    - DTO 金额字段加 NUMERIC(18,2) 精度约束（max_digits=18, decimal_places=2）
    - _Requirements: 2.2, 2.3, 8.1, 8.2, 10.3_

  - [ ]* 1.4 编写 V070 三层一致契约测试
    - **Property 9: 层级完整性**（部分）— 验证 V070 DDL 列集合 == ORM `Mapped` 列集合
    - 复用现有契约测试模式（test_raw_sql_column_contract 风格），断言 bad_debt_detail_rows 表列与 ORM 零 drift（含 created_at/updated_at）
    - _Requirements: 8.1_

- [ ] 2. AutoSumEngine 纯计算模块
  - [ ] 2.1 实现 `AutoSumEngine` 三级汇总 + 平衡校验
    - 创建 `backend/app/services/bad_debt_auto_sum.py`，无 DB 依赖，接收行数据列表返回汇总
    - `AMOUNT_COLUMNS` = amount_b ~ amount_n（13 列）；`sum_children`（父=子合计）、`sum_parents`（合计=父合计）逐列独立 Decimal 求和，保留两位小数
    - `validate_balance_formula` 计算 `expected_n = E + F + G - H - I - J + L + M`，`is_balanced = |expected_n - actual_n| < 0.01`，返回 `BalanceCheck`
    - 处理 None 混合（视作 0 参与求和，但全 None 列返回 None）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 10.3_

  - [ ]* 2.2 PBT：父行汇总等于子行合计
    - **Property 1: 父行汇总等于子行合计**
    - **Validates: Requirements 3.1, 3.3**
    - hypothesis `st_child_rows()`，`@settings(max_examples=5, deadline=None)`

  - [ ]* 2.3 PBT：合计行等于所有父行合计
    - **Property 2: 合计行等于所有父行合计**
    - **Validates: Requirements 3.2, 3.3**
    - hypothesis `st_parent_rows()`，max_examples=5

  - [ ]* 2.4 PBT：平衡公式不变量
    - **Property 3: 平衡公式不变量**
    - **Validates: Requirements 3.4**
    - hypothesis `st_row_amounts()`，max_examples=5

  - [ ]* 2.5 PBT：Decimal 精度保持
    - **Property 4: Decimal 精度保持**
    - **Validates: Requirements 3.6, 10.3**
    - hypothesis `st_decimals()`，验证求和结果恰好两位小数、无 float 漂移，max_examples=5

  - [ ]* 2.6 AutoSumEngine 单元测试（边界）
    - 空子行 / 单子行 / 负数金额 / None 混合 / Parent 无 Child 允许直接编辑（不强制清零）
    - _Requirements: 3.5_

- [ ] 3. NestedTableService CRUD + 层级管理
  - [ ] 3.1 实现 `NestedTableService` 构造与 `get_tree`
    - 创建 `backend/app/services/bad_debt_nested_table_service.py`，`__init__(self, db: AsyncSession)`
    - `get_tree(wp_index_id)` 返回树形结构（Parent 嵌套 children 数组）+ Summary（调用 AutoSumEngine 汇总）+ balance_check
    - service 只 flush 不 commit
    - _Requirements: 2.1, 8.2, 8.3_

  - [ ] 3.2 实现 `create_parent_row` / `create_child_row`
    - `create_parent_row`：要求指定 provision_method，依赖唯一偏索引拦截同 sheet 重复（捕获 IntegrityError → ValueError）
    - `create_child_row`：插入到指定 parent 子行末尾，分配 sort_order 严格大于现有子行最大值；触发父行汇总重算
    - _Requirements: 1.2, 1.3, 2.4, 2.6, 3.1_

  - [ ] 3.3 实现 `update_row`（乐观锁）/ `delete_row`（级联）
    - `update_row`：校验传入 version 与当前一致，不一致抛冲突（→ 409）；更新后重算父→合计；父行有子行时拒绝直接编辑金额列（→ 400）
    - `delete_row`：删除子行后重算父汇总；删除父行级联删子行（ORM cascade）；拒绝删除最后一个父行（→ 400 至少保留一个计提类别）
    - _Requirements: 2.5, 6.7, 8.4, 8.5, 10.5_

  - [ ] 3.4 实现 `validate_integrity` 完整性校验
    - 校验每个 Child_Row 的 parent_row_id 指向同一 wp_index_id 下有效 Parent_Row（无孤儿）
    - 校验金额精度不超 NUMERIC(18,2)；父行显示值与子行合计不一致时标记校验错误并提供"重新汇总"动作标识
    - _Requirements: 10.2, 10.3, 10.4_

  - [ ]* 3.5 PBT：枚举唯一性
    - **Property 5: 枚举唯一性**
    - **Validates: Requirements 1.3, 2.6**
    - hypothesis `st_provision_methods()`，max_examples=5（需 PG 真库或 in-process session）

  - [ ]* 3.6 PBT：层级完整性
    - **Property 9: 层级完整性**
    - **Validates: Requirements 2.6, 10.4**
    - hypothesis `st_nested_tree()`，max_examples=5

  - [ ]* 3.7 PBT：级联删除
    - **Property 10: 级联删除**
    - **Validates: Requirements 8.4**
    - hypothesis `st_nested_tree()`，删父行后验证无子行残留，max_examples=5

  - [ ]* 3.8 PBT：乐观锁冲突检测
    - **Property 11: 乐观锁冲突检测**
    - **Validates: Requirements 8.5**
    - hypothesis `st_concurrent_updates()`，相同起始 version 的第二次更新被拒（409），max_examples=5

  - [ ]* 3.9 PBT：子行新增排序单调
    - **Property 12: 子行新增排序单调**
    - **Validates: Requirements 2.4**
    - hypothesis `st_child_sequence()`，每个新子行 sort_order 严格大于现有所有，max_examples=5

- [ ] 4. Checkpoint - 基础数据层与汇总校验
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. 试算表辅助预填 PrefillService
  - [ ] 5.1 实现 `BadDebtPrefillService.prefill_summary`
    - 创建 `backend/app/services/bad_debt_prefill_service.py`，`__init__(self, db)`
    - 从 `TrialBalanceService` 查科目 1231：opening_balance → Summary_Row 期初未审数(B)、unadjusted_amount → 期末未审数(K)
    - 仅在目标单元格为 None 时预填，已有值不覆盖；TB 无 1231 时跳过不报错（no-op）
    - 返回 `PrefillResult`，含来源标注字符串"试算表 1231 坏账准备"
    - service 只 flush 不 commit
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 5.2 PBT：预填仅空值
    - **Property 6: 预填仅空值**
    - **Validates: Requirements 4.3**
    - hypothesis `st_cell_states()`，验证仅 None 单元格被填、有值单元格不变，max_examples=5

  - [ ]* 5.3 PrefillService 单元测试
    - 1231 缺失（跳过）/ 已有值不覆盖 / 正常预填带来源标注
    - _Requirements: 4.4, 4.5_

- [ ] 6. 调整分录联动 AjeGenerator
  - [ ] 6.1 实现 `BadDebtAjeGenerator.generate_suggestion`
    - 创建 `backend/app/services/bad_debt_aje_generator.py`，`__init__(self, db)`
    - 计算 Summary_Row 期末审定数(N) - 期末未审数(K) 差额；零差额返回 None（不生成）
    - 审定数 > 未审数（补提）：借 资产减值损失/信用减值损失，贷 坏账准备 1231；审定数 < 未审数（冲回）：方向相反；金额 = |差额|
    - 生成建议含摘要说明，标记为 suggested 状态（确认后才由 AdjustmentService 写正式表）；重算时覆盖旧建议
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.2 PBT：AJE 方向正确性
    - **Property 7: AJE 方向正确性**
    - **Validates: Requirements 5.2, 5.3, 5.4**
    - hypothesis `st_amount_pairs()`，验证方向与金额绝对值，max_examples=5

  - [ ]* 6.3 AjeGenerator 单元测试
    - 零差额（不生成）/ 补提 / 冲回 / 用户修改后覆盖旧建议
    - _Requirements: 5.5, 5.6_

- [ ] 7. 序列化 / 反序列化
  - [ ] 7.1 实现 `NestedTableService.serialize` / `deserialize`
    - `serialize(wp_index_id)`：输出完整嵌套结构 JSON（父行、子行、排序、provision_method、13 金额列）
    - `deserialize(wp_index_id, payload)`：从 JSON 恢复到数据库；缺必要字段或层级关系无效时返回详细 ValidationError 列表（不静默忽略）
    - service 只 flush 不 commit
    - _Requirements: 11.1, 11.2, 11.4_

  - [ ]* 7.2 PBT：序列化 Round-Trip
    - **Property 8: 序列化 Round-Trip**
    - **Validates: Requirements 11.1, 11.2, 11.3**
    - hypothesis `st_nested_tree()`，serialize→deserialize 语义等价（父子、排序、枚举、金额一致），max_examples=5

  - [ ]* 7.3 Serializer 单元测试
    - 缺字段 / 层级断裂的 deserialize 返回 ValidationError 列表
    - _Requirements: 11.4_

- [ ] 8. 公式引擎集成
  - [ ] 8.1 扩展 FormulaEngine WP 函数寻址 D2-3
    - 在现有 `WPExecutor.execute` 扩展：`=WP('D2','坏账准备明细表D2-3','本期计提合计')` → Summary_Row.amount_f；同理 本期转回合计/核销合计/期末余额
    - 支持父行级引用：`=WP('D2','坏账准备明细表D2-3','单项评估计提.期末审定数')` → 对应 provision_method 父行 amount_n
    - 将 Summary_Row 关键汇总值注册为可引用地址；数据变更时触发下游公式重算
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 8.2 公式集成单元测试
    - 合计级引用 / 父行级引用 / 地址变更触发依赖重算
    - _Requirements: 9.2, 9.3, 9.4_

- [ ] 9. Checkpoint - 服务层全链路（预填/AJE/序列化/公式）
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. API 路由 + router_registry 注册
  - [ ] 10.1 实现 `bad_debt_rows` router 全部端点
    - 创建 `backend/app/routers/bad_debt_rows.py`，前缀 `/api/workpapers/{wp_id}/bad-debt-rows`
    - 端点：GET 树 / POST parents / POST {parent_id}/children / PUT {row_id} / DELETE {row_id} / GET provision-methods / POST prefill / GET aje-suggestion / POST serialize / POST deserialize
    - 编排 NestedTableService/Prefill/Aje/Serializer；**router 层统一 commit**；错误映射 409/400/422/200(no-op)
    - GET provision-methods 返回枚举值 + 中文显示名（来自 PROVISION_METHOD_LABELS）
    - _Requirements: 1.4, 8.2, 8.3, 8.5, 10.5_

  - [ ] 10.2 在 router_registry/workpaper.py 数据组注册
    - 在 `backend/app/router_registry/workpaper.py` 「数据」组注册新 router（否则前端 404）
    - 注意注册顺序：静态路径端点（如 provision-methods/prefill/aje-suggestion/serialize/deserialize）须先于 `{row_id}` 通配端点，避免通配截获静态路径
    - _Requirements: 8.2_

  - [ ]* 10.3 API 契约/集成测试（in-process ASGI httpx）
    - 用 `httpx.ASGITransport(app=app)` 直调全部端点，覆盖 200/409/422/400 状态码
    - 全链路：建父行→建子行→编辑→Auto-SUM→预填→生成 AJE→序列化 round-trip
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

- [ ] 11. 前端 Univer 嵌套编辑器
  - [ ] 11.1 实现 `GtBadDebtSheet.vue` 层级渲染
    - 创建 `audit-platform/frontend/src/views/workpaper/components/GtBadDebtSheet.vue`
    - 按层级渲染：Parent_Row 加粗、Child_Row 缩进显示"其中：{项目名}"、Summary_Row 合计
    - 展开/折叠图标切换子行可见性；汇总列（Summary 与含子行 Parent 的金额列）只读保护
    - UI 全中文化 + GT 紫令牌（styles/gt-tokens.css）；预填来源 tooltip
    - _Requirements: 6.1, 6.2, 6.6, 6.7_

  - [ ] 11.2 实现右键菜单与增删子行交互
    - 右键 Parent_Row：上下文菜单"新增子行"；右键 Child_Row："删除子行"/"在上方插入"/"在下方插入"
    - 执行增删调用后端 API 持久化并刷新汇总显示
    - 原生 fetch 须手动解 `{code,message,data}` 信封；下载/认证资源走 downloadFile（禁 window.open）
    - _Requirements: 6.3, 6.4, 6.5_

  - [ ] 11.3 前端 router 联通验证
    - 用 Playwright 实测：打开 D2-3 底稿 → 渲染层级 → 展开折叠 → 右键新增/删除子行 → 汇总刷新 → 预填 tooltip
    - 验证前端调用命中已注册后端路由（无 404/307），信封正确解包
    - _Requirements: 6.5, 8.2_

  - [ ]* 11.4 前端组件单元测试（vitest）
    - 层级渲染 / 展折切换 / 只读保护 / 右键菜单项 / 信封解包
    - _Requirements: 6.1, 6.2, 6.6, 6.7_

- [ ] 12. 致同 D2-3 模板对齐与导出
  - [ ] 12.1 实现 Export_Engine 14 列模板导出
    - 按致同模板 14 列结构输出 xlsx：A(项目名) B~N（13 金额列），表头区 R1-R9 元信息 + 表头行 R10-R11
    - 行顺序：表头 → 单项评估计提父行 → 子行 → 信用风险组合计提父行 → 子行 → 合计行
    - Child_Row 空金额列输出空值（非零）；"其中"子行 A 列前加两个空格缩进
    - useExcelIO.exportTemplate 的 existingData 须等宽 pad（多子表用 applyStyles: false）
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [ ]* 12.2 导出单元测试
    - 14 列顺序 / 空值非零 / 缩进格式 / 元信息保留
    - _Requirements: 7.1, 7.3, 7.5_

- [ ] 13. 数据校验完整性集成（Summary 与 TB 比对）
  - [ ] 13.1 接入 Summary_Row 期末审定数与 TB 1231 audited_amount 比对
    - 在 `validate_integrity` 或 get_tree 校验链中加：Summary_Row 期末审定数(N) vs TB 科目 1231 audited_amount，不等标记差异提示
    - _Requirements: 10.1_

  - [ ]* 13.2 校验集成单元测试
    - N 等于/不等于 TB audited_amount 两种场景
    - _Requirements: 10.1_

- [ ] 14. Final Checkpoint - 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标 `*` 的子任务为可选（测试类），执行实施时按用户偏好"可选任务也要做完（除非明确跳过）"处理
- 顶层任务不带 `*`；测试均为子任务，不设独立测试顶层任务
- 12 条 correctness property 已全部映射到必做 PBT 子任务（P1~P4→任务2、P5/P9/P10/P11/P12→任务3、P6→任务5、P7→任务6、P8→任务7）
- 所有 PBT 使用 `hypothesis @settings(max_examples=5, deadline=None)`
- 三层一致：V070 DDL（任务1.1）+ ORM（任务1.2）+ service（任务3）+ R070 回滚 + 契约测试（任务1.4）
- service 只 flush 不 commit，router 统一 commit（任务10.1）
- 新 router 必在 router_registry/workpaper.py 数据组注册（任务10.2）
- 前端 router 联通验证（任务11.3）用 Playwright 实测
