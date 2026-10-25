# Requirements Document

受管行删物理行的多区位移联动

## Introduction

上游 spec `workpaper-sync-managed-row-convergence` 已把「受管行收敛」落地为**清空 editable 业务格**
（第十一轮真实链路 materialize 200 实证），并在 §第十一轮 **G2** 裁决里把**删物理行**这条路径
「保留但刻意不启用」，理由是删行牵动一整套行号位移联动而插行路径为此积累了专门处理，
缺其一就会让同 sheet 兄弟受管区出现空 UUID 行、被 `_scan_row_identities` 重新 mint 身份、
触发新一轮 `extra`。

本 spec 补齐那套联动，使删物理行成为**可按契约逐表开启**的收敛动作，并把上游的反向守卫
（「收敛不得产出删行计划」）替换成正向判据。

### 本 spec 的三条边界

1. **只做删行侧的位移联动与启用受控**；adopt merge 语义与刷新取数弹窗属并行 A 线
   `workpaper-sync-adopt-overwrite-and-refresh-source`，本 spec 不改
   `store_mirror.py` / `adopt_substrate_response.py` / `GtWpRenderer.vue`。
2. **不弱化任何既有 fail-closed 判据**（含 roundtrip、footer 两门、悬空引用门、传播对账）。
3. **不改 Property 28 冻结基线的被观测对象**（`_rewrite_formula_refs` 与其三个情景）。

### 现算基线（design「§ 现算基线」，实施期须复算，**禁写死**）

`plan_workbook_row_change_for_delete` 全仓命中 **0** · `_refresh_gt_sync_runtime_binding` 被重写的
`GT_*` 键 **7** 个（另 1 个只读）· 「同 sheet 多受管区」结构性爆炸面 **18** 组（17 双区 + 1 三区，
横跨 D1/D2/D3/D4/D6/D7）· 契约 `delete_policy=tombstone` **139/153** · 跨 sheet 引用 **144,154** 处。

---

## Glossary

- **Row_Deletion_Planner**：新增的删行工作簿级声明生产者 `plan_workbook_row_change_for_delete`。
- **Row_Deletion_Shift**：删行的位移载体（`RowDeletionShift`），与 `RowShiftPlan` / `CompositeRowShift`
  鸭子兼容（`shift` / `unshift` / `inserted_rows` / `count`）。
- **Row_Deletion_Change_Set**：删行的工作簿级传播声明（只暴露 `propagations`，鸭子兼容 verify）。
- **Convergence_Planner**：`excel_materialize.plan_managed_writes`，受管写入计划的唯一生产者。
- **Row_Change_Applier**：`excel_materialize.apply_plan_zip_with_report`，zip 级定点写入执行者。
- **Sibling_Table_Shrinker**：新增的同 sheet 兄弟 Excel Table `ref` 收缩器。
- **Runtime_Binding_Refresher**：`excel_materialize._refresh_gt_sync_runtime_binding`。
- **Footer_Gate_Verifier**：`excel_materialize.assert_shifted_footer_gates`。
- **Unmanaged_Region_Verifier**：`excel_extract.verify_unmanaged_regions` / `unmanaged_region_digest`。
- **Identity_Scanner**：`excel_extract._scan_row_identities`（空 UUID 行按 `delete_policy` 处置）。
- **Contract_Parser**：`contracts.py` 的 `_parse_table` / `parse_contract`。
- **Zero_Regression_Baseline**：Property 28 的冻结基线
  （`backend/tests/workpaper_sync/data/workbook_row_change_zero_regression_baseline.json`）。
- **stale 行**：substrate 上有物理行与身份、但 store 本次 projection 未声明的受管行。
- **orphan 身份**：store 声明、但 substrate 上没有物理行的受管行身份（触发动态插行）。
- **`row_convergence`**：新增的契约级逐表开关，取值 `clear`（默认）/ `delete`。
- **裸引用**：公式文本里不带 sheet 前缀的 A1 引用（如 `SUM(B7:B25)`），属所在 sheet 自己。
- **声明（declaration）**：写盘**之前**冻结的位移/传播描述；与「观测值」相对。

---

## Requirements

### Requirement 1: 删行必须产出工作簿级位移声明

**User Story:** 作为平台维护者，我要让删物理行与插行走同一条「声明 → 执行 → 验证」链路，
这样删行造成的合法位移才不会被验证器判成未管理区域漂移，也不会被 apply 与 verify 各自推断出两种口径。

#### Acceptance Criteria

1. THE Row_Deletion_Planner SHALL 由 substrate 的 zip entries 与被删行号集合产出 Row_Deletion_Change_Set
2. WHEN 工作簿里没有任何指向受管 sheet 的引用 THEN THE Row_Deletion_Planner SHALL 返回空声明标记，
   且 THE Row_Change_Applier SHALL 产出与不产声明时逐字节相同的字节
3. WHEN 全部指向受管 sheet 的引用都位于被删行之上 THEN THE Row_Deletion_Planner SHALL 返回空声明标记
4. THE Row_Deletion_Planner SHALL 用与 Row_Change_Applier 相同的引用改写入口生成每条声明的改后文本
5. THE Row_Deletion_Change_Set SHALL 只暴露传播条目集合，不声明单一的起点与行数标量
6. WHERE 被删行号集合不连续，THE Row_Deletion_Planner SHALL 为每条传播条目按「该引用之上被删行数」
   各自计算行号增量
7. THE Row_Deletion_Planner SHALL 对每一个极大连续被删段调用既有悬空引用检测
8. IF 任一引用会因删行变成 `#REF!` AND 契约未显式放行 THEN THE Row_Deletion_Planner SHALL 在写盘之前
   抛 `DanglingReferenceError` 并携带完整清单
9. THE Row_Deletion_Planner SHALL 调用既有业务键解析取得被删行的留痕键
10. IF 任一被删行既无行身份也无稳定序号 THEN THE Row_Deletion_Planner SHALL 抛 `MissingRowIdentityError`
11. THE Convergence_Planner SHALL 在产出删行计划时同时产出 Row_Deletion_Shift 与 Row_Deletion_Change_Set
12. THE Row_Deletion_Shift SHALL 对被删行返回空值而不是行号，使「这一行没了」在类型上不可忽略
13. THE Row_Deletion_Shift 的新增行集合 SHALL 恒为空集合

---

### Requirement 2: 同 sheet 兄弟受管区的 Table `ref` 必须随删行收缩

**User Story:** 作为审计助理，我在主营区删掉一行后，同一张表下方的「其他」区不应该多出一行空白身份行，
也不应该因此被系统当成我新增的行。

#### 现状（已现读确认）

`_shrink_managed_table_ref` 只改计划里的那一个 Table part，且首行一律不动；
`_shift_sibling_table_refs` 全仓生产调用 **1** 处，位于 `_grow_managed_table_ref` 末尾（插行侧）。

#### Acceptance Criteria

1. WHEN 删行发生 THEN THE Sibling_Table_Shrinker SHALL 对同一 sheet 上除本区之外的每个 Excel Table
   按「该行之上被删行数」收缩其 `ref` 的**首行与末行**
2. THE Sibling_Table_Shrinker SHALL 只改 `ref` 的行分量，列跨度逐字保留
3. THE Sibling_Table_Shrinker SHALL 走 worksheet rels 取同 sheet 的 Table part 清单
4. WHERE 兄弟 Table 完全位于被删行之上，THE Sibling_Table_Shrinker SHALL 不改动其 `ref` 且不报错
5. WHEN 兄弟 `ref` 已收缩 THEN THE Identity_Scanner SHALL 不为该兄弟区 mint 任何新行身份
6. THE Sibling_Table_Shrinker SHALL 与 `_shift_sibling_table_refs` 共用同一个 `ref` 匹配形态，
   不引入第二份 `ref` 解析
7. THE 判据 SHALL 覆盖设计「§ 现算基线」B8 现算出的每一组「同 sheet 多受管区」结构
8. THE 判据 SHALL 包含变异反证：短路兄弟收缩后，AC 5 的断言打红

---

### Requirement 3: `_GT_SYNC` runtime binding 必须按删行重冻结

**User Story:** 作为平台维护者，我要让「这次删行成功了、下次点在线编辑却 500」这条时间错位的故障
不再可能发生。

#### 现状（已现读确认）

Runtime_Binding_Refresher 是 insert-only（函数首行取 `plan.row_shift` 并断言非空）；
函数体内 **8** 个 `GT_*` 键里 **7** 个被重写、1 个（`GT_ROW_UUID_COLUMN`）只读。

#### Acceptance Criteria

1. WHEN 删行发生 THEN THE Runtime_Binding_Refresher SHALL 按 Row_Deletion_Shift 重冻结那 7 个键
2. THE Runtime_Binding_Refresher SHALL 对本 sheet 的每个 per-template footer 键（含同 sheet 兄弟区的）
   各自按其行号与被删行的关系重冻结
3. THE Runtime_Binding_Refresher SHALL 不改动不同 sheet 的 per-template footer 键
4. THE Runtime_Binding_Refresher SHALL 复用既有的「worksheet rels → 兄弟 Table displayName →
   `_GT_SYNC` 平行清册」推导取得同 sheet 的 template_id 集合，不引入第二份推导
5. THE Runtime_Binding_Refresher SHALL 逐字保留未受删行影响的键
6. WHEN 删行后再次物化同一 entry THEN THE Convergence_Planner 的计划期 footer 门 SHALL 通过
7. THE 判据 SHALL 包含变异反证：去掉 per-template footer 键的重冻结后，AC 6 打红并抛
   `FooterAnchorDriftError`

---

### Requirement 4: definedName 与跨 sheet 公式必须按声明位移

**User Story:** 作为审计合伙人，我要确保底稿上任何一处跨表取数在别的表删行之后仍然指向同一笔业务数据，
而不是静默指向隔壁那一行。

#### Acceptance Criteria

1. WHEN Row_Deletion_Change_Set 非空 THEN THE Row_Change_Applier SHALL 按其声明逐条改写引用侧 sheet
   与 `xl/workbook.xml`
2. THE Row_Change_Applier SHALL 按声明逐条替换，不在 apply 期重新扫描工作簿
3. IF 声明点名的部件不在 substrate zip 里 THEN THE Row_Change_Applier SHALL 抛 `PropagationDriftError`
4. IF 实际改动处数与声明处数不等 THEN THE Row_Change_Applier SHALL 抛 `PropagationDriftError`
5. WHEN 删行完成 THEN `GT_FOOTER_ANCHOR_*` 与 `_xlnm.Print_Area` 里指向被删行之下的行号 SHALL 各自
   减去其上方被删行数
6. WHEN 删行完成 THEN 指向受管 sheet 且位于被删行之上的引用 SHALL 逐字不变
7. WHEN 删行完成 THEN 跨越被删区间的区间引用 SHALL 收缩其覆盖范围
8. THE 判据 SHALL 包含变异反证：从声明里移除 `xl/workbook.xml` 的条目后，
   THE Unmanaged_Region_Verifier 判 `adapter_unmanaged_region_drift`

---

### Requirement 5: 受管 sheet 自身的裸引用必须随删行平移

**User Story:** 作为审计助理，我删掉明细区一行后，合计格不应该把 footer 自己算进去，也不应该多算一行。

#### 待实证（design「§ 风险与未验证项」R1）

本条的缺口是**代码现读推断**（`shrink_sheet_rows` 只改 `<row r=>` / `<c r=>` 属性与 `<dimension>`；
`propagate_reference_side` 是 `qualified_only=True`），**未实测**。实施第一步须先探针实证；
若证伪则本 Requirement 降级为「已有产物」并更正设计。

#### Acceptance Criteria

1. WHEN 删行发生 THEN THE Row_Change_Applier SHALL 平移受管 sheet 内指向被删行之下的裸引用
2. THE Row_Change_Applier SHALL 走既有的唯一 A1 重映射入口执行该平移，不新写一份行号改写器
3. THE Row_Change_Applier SHALL 不复用插行的 `shift_sheet_rows` 执行删行侧平移
4. WHERE 契约声明该 footer 携带合计公式，THE Row_Change_Applier SHALL 把合计区间末行收缩到
   删行后的受管区末行
5. WHERE 契约未声明该 footer 携带合计公式，THE Row_Change_Applier SHALL 不改写该 footer 的任何公式
6. WHEN 删行完成 THEN 合计公式的区间 SHALL NOT 覆盖 footer 自身所在行
7. THE 判据 SHALL 包含变异反证：跳过该平移后，AC 6 打红

---

### Requirement 6: 验证器必须能表达删行造成的合法位移

**User Story:** 作为平台维护者，我要让删行产物通过未管理区域比对，同时保持「声明之外的任何改动仍判漂移」。

#### Acceptance Criteria

1. THE Row_Deletion_Shift SHALL 提供与既有位移载体同名的反向映射，供 Unmanaged_Region_Verifier
   对受管 sheet 做归一化
2. WHEN 归一化入参为 Row_Deletion_Shift THEN THE Unmanaged_Region_Verifier SHALL 判删行产物与
   删行前产物在 `managed_sheet_unmanaged_cells` 与 `managed_sheet_structure` 两个方面等价
3. THE Unmanaged_Region_Verifier SHALL 只对 after 侧做归一化
4. WHERE 受管 sheet 的合计区间因删行而收缩，THE Unmanaged_Region_Verifier SHALL 按声明的被删行数
   还原该收缩
5. THE 判据 SHALL 包含变异反证：不传 Row_Deletion_Shift 时，AC 2 判漂移
6. THE 判据 SHALL 显式断言 Row_Deletion_Shift 的新增行集合为空集合
7. IF 归一化后仍存在声明之外的字节差异 THEN THE Unmanaged_Region_Verifier SHALL 判漂移

---

### Requirement 7: 删行后必须在同一次物化内复核 footer 两门

**User Story:** 作为平台维护者，我要让位移算错在**本次**就暴露，而不是等到下一次物化时才以别的症状出现。

#### Acceptance Criteria

1. WHEN 本次计划含删行 THEN THE Footer_Gate_Verifier SHALL 在写盘之前于 staged 产物上复核 footer 锚点
2. THE Footer_Gate_Verifier SHALL 用「冻结值 − 声明的被删行数」作为 footer 锚点的预期行号
3. IF footer 锚点实测行号与预期不等 THEN THE Footer_Gate_Verifier SHALL 抛 `FooterAnchorDriftError`
   且本次物化 SHALL NOT 产出任何文件
4. WHEN 本次计划含删行 THEN THE Footer_Gate_Verifier SHALL 用删行后的受管区末行复核合计区间覆盖
5. THE 判据 SHALL 用 Footer_Gate_Verifier 的返回值断言它真的执行过，而不是用「没有抛错」

---

### Requirement 8: 启用受控 —— 契约逐表声明，默认逐字节零回归

**User Story:** 作为平台维护者，我要能一张表一张表地开启删行，并且在开启之前证明既有行为一个字节都没变。

#### Acceptance Criteria

1. THE Contract_Parser SHALL 接受可选的表级 `row_convergence` 键，取值为 `clear` 或 `delete`
2. WHERE 契约未声明 `row_convergence`，THE Contract_Parser SHALL 取 `clear`
3. IF 契约声明 `row_convergence=delete` 却未声明行身份或删除策略 THEN THE Contract_Parser SHALL
   抛 `ContractSchemaError`
4. WHILE 某表的 `row_convergence` 为 `clear`，THE Convergence_Planner SHALL 走清空分支
5. THE 判据 SHALL 断言全部既有契约文件解析后 `row_convergence` 均为 `clear`（分母现算，禁写死）
6. THE 判据 SHALL 断言：同一 substrate 与同一 projection 在本 spec 前后经 Row_Change_Applier
   产出的字节 sha256 相等
7. THE 判据 SHALL 用 AST 断言删行计划的产出被 `row_convergence` 门控
8. THE 判据 SHALL 包含变异反证：把门控条件改成恒真后，AC 6 打红

---

### Requirement 9: 删与插共存时降级回清空，而不是拒绝

**User Story:** 作为审计助理，我在一次保存里既删了几行又加了几行时，在线编辑仍然要能打开。

#### 依据

上游在 Row_Change_Applier 里对「删与插同时要求」抛
`[convergence_delete_with_insert_unsupported]`，理由是插入点按删行前行号算会错位。
该拦截至今**从未在生产触发**（删行分支未启用）。启用删行后若照原样保留，
会把当前能用（走清空分支）的 entry 打成 500。

#### Acceptance Criteria

1. WHILE 本次计划同时存在 stale 行与 orphan 身份，THE Convergence_Planner SHALL 选择清空分支
2. WHEN 因共存而降级 THEN THE Convergence_Planner SHALL 在计划的可读摘要里记录降级原因
3. THE Convergence_Planner SHALL NOT 在删行前行号口径上重算插入点
4. THE Row_Change_Applier SHALL 保留既有的共存拦截作为纵深防御
5. THE 判据 SHALL 断言 Convergence_Planner 的分流覆盖「stale 有无 × orphan 有无 × 容量是否归零 ×
   契约是否开启」的全部组合，使 AC 4 的拦截不可达
6. WHEN 删行分支因任何原因被降级 THEN THE 降级原因 SHALL 可被判据读取，
   使「删行已上线但从未真正执行」不能静默成立

---

### Requirement 10: Property 28 冻结基线不得静默变化

**User Story:** 作为平台维护者，我要确保补删行不会顺手改掉那份冻结了 351 份模板行为的基线。

#### Acceptance Criteria

1. THE 实现 SHALL NOT 修改 `_rewrite_formula_refs`、`translate_formula_rows` 与
   Zero_Regression_Baseline 的情景定义
2. THE 删行侧的反向行号映射 SHALL 通过调用方传入的重映射实参实现
3. THE 判据 SHALL 断言 Zero_Regression_Baseline 文件的 sha256 与本 spec 交付时的现算值相等
4. THE 该判据 SHALL 在失败文案里说明「若是有意重生成，改期望值并在提交说明里逐处论证合法性」
5. THE 实现 SHALL NOT 向 Zero_Regression_Baseline 增加删行情景
6. IF 实施期发现必须修改 `_rewrite_formula_refs` THEN THE 实施 SHALL 停止并按范围变更处理

---

### Requirement 11: G2 实测症状必须有可复现的沿链判据

**User Story:** 作为平台维护者，我要能证明「other 区出 uuid 空行并被重新 mint 身份」这条链真的被断开了，
而不是各环判据各自绿而链条仍通。

#### Acceptance Criteria

1. THE 判据 SHALL 用合成的同 sheet 双区工作簿复现该症状链，不依赖 live 数据也不造假业务数据
2. THE 判据 SHALL 逐环断言：兄弟 `ref` 的值、区间尾行 UUID 是否为空、是否 mint 出新身份、
   以及生产口径下的 `extra` 计数
3. WHILE 兄弟收缩被短路，THE 判据 SHALL 在上述每一环都打红
4. THE 判据 SHALL 用生产的受管字段过滤口径计算 `extra`，不自造裸差集
5. THE 判据 SHALL 用进程内替换制造「修复前」态，不改动磁盘上的生产文件

---

### Requirement 12: 上游反向守卫替换为正向判据

**User Story:** 作为平台维护者，我要让「收敛不得产出删行计划」这条看门狗在前提反转后被**正确替换**，
而不是被删掉。

#### Acceptance Criteria

1. WHEN 本 spec 的联动全部落地 THEN THE 反向断言「收敛不得产出删行计划」SHALL 被移除
2. THE 移除 SHALL 与三条正向断言同一次提交：删行计划必须同时携带两份声明、
   必须落在契约门控之内、apply 必须依次经过五个位移动作
3. THE 正向断言 SHALL 用实测计数判断各动作真的执行过，而不是用「没有抛错」
4. THE 判据 SHALL 保留既有的「清空分支仍是默认分支」断言
5. THE 判据 SHALL NOT 加「`shrink_sheet_rows` 必须有生产消费方」这类死代码守卫的原始形态，
   因为该能力现算已有 2 个生产消费方，该守卫会恒真

---

## 非目标（明确排除）

1. **不解除删与插共存的删行支持**（Requirement 9 只改处置方式，不实现「删后重算插入点」）。
2. **不改 adopt 的 merge 语义**、不实现刷新取数来源弹窗（A 线范围）。
3. **不弱化任何既有 fail-closed 判据**。
4. **不改权威模板**（`backend/wp_templates/`）。
5. **不 hack live 数据、不造假业务数据。**
6. **不改 Property 28 的被观测对象与情景集合。**
7. **不把 `excel_extract_identity_carrier_missing` 的 500 → domain error 分类问题纳入**
   （归档 README 已移交平台总纲）。
