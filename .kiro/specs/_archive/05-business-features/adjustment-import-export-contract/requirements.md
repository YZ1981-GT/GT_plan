# Requirements Document

## Introduction

调整分录的导入导出目前有三条互不相通的通道（中央富模板导入、中央汇总导出、各底稿调整 tab 导入导出），其中存在两类会**静默吃掉或重复计入数据**的确定性缺陷，以及 7 张底稿调整 tab 的**存储契约漂移**（后端 `_SPECS` 的 `item_id`/字段键与前端持久化键不一致 → 导入写进孤儿键，前端读不到、用户看不到、也不报错）。

本 spec 的目标是把"导入导出契约"收敛为一处可核查、有守卫的真源：中央通道消除静默丢行/重复追加、让导出的汇总可以改完导回；底稿通道逐 sheet 对齐三方键（后端 spec ↔ 前端持久化 ↔ 行模型字段），并用契约守卫测试锁定防止再次漂移。

按波交付：中央 4 项确定性缺陷（Wave 0）独立可发布先落地；底稿契约对齐分波跟进；`K12-3` 存储结构决策单独成波。全程 additive 零回归——不改导出模板的列集合（保持已填模板仍可导入）、不改 `syncToCentral`（底稿→中央 `sync-from-workpaper` 幂等链路）、不改 `recalc` 试算表聚合口径。

### 已核实的现状基线（实现时以代码为准，不得凭本节记忆）

- 中央导入分发 `_dispatch_import` 签名含 `mode: str`，但 `adjustments` 分支调用 `_import_adjustments(rows, project_id, y, user, db)` **不传 mode**，`_import_adjustments` 签名亦无 mode 形参。
- `_is_example_row` 判定为 `match_count >= max(2, len(matchable_pairs) * 0.6)`，作用于**前 6 行**；调整分录模板可比示例字段 5 个 → 阈值 3。
- `_write_adj_sheet`（`GET /adjustments/export-summary`）列头为 `编号/摘要/科目编码/科目名称/借方金额/贷方金额/来源`，**无「类型」列**；类型信息只隐含在 sheet 名 `AJE审计调整`/`RJE重分类`，而解析器不读 sheet 名。
- 底稿侧键现状（后端 `item_id` → 前端实际持久化键）：`K3-3-rows→K3-3-adj-entries`、`K4-3-rows→K4-3-adj-entries`、`K7-3-rows→K7-3-adj-entries`、`K8-3-rows→K8-3-adj-entries`、`K5-3-rows→K5-3-entries`、`K12-3-rows`(JSON 数组)→前端 per-field `K12-3-entry-{n}-{field}`；`_K2_SPECS` **无 `K2-3` 条目**而前端存 `K2-3-adj-entries`。
- 真正无漂移（本 spec 不动）：`K9-3`（spec 显式 `storage_field="remark"`）、`K11-3`（router 级 `storage_field="remark"`）、`K13-3`（spec 显式）。
- **Task 1.1 characterization 修正的误判**：`K1-4`、`K6-3`、`I5-3`、`I6-3` 的 `item_id` 正确但**未声明 `storage_field`** → 取工厂默认 `conclusion`，而前端（`useK1Adjustment`/`K6TabAdjustment`/`useI5Adjustment`/`useI6Adjustment`）读写 `remark` → 属第三种 Orphan_Key（item_id 对但写错列），纳入本 spec 对齐范围。

## Glossary

| 术语 | 含义 |
|------|------|
| 中央通道 | 中央调整分录模块的导入导出：`GET /adjustments/export-template`（富模板）、`GET /adjustments/export-summary`（已有数据汇总）、`POST /api/import-templates/adjustments/import` |
| 底稿通道 | 各循环调整 tab 的导入导出：`POST /{cycle}/export-template`、`/export-data`、`/import-data`，数据驱动同一 `_SPECS` |
| Import_Mode | 中央导入的写入语义，`append`（追加）/ `overwrite`（覆盖本年度同类分录） |
| Example_Row | 模板内置示例行；导入解析时应被跳过，不计入 imported/failed |
| Sheet_Spec | 底稿通道后端每个 sheet 的导入导出定义（`_SPECS[sheet]` 的 `item_id`/`storage_field`/`headers`/`field_keys`） |
| Storage_Key | 前端调整 tab 实际持久化到 `checklist_responses` 的 `item_id` |
| Three_Way_Key_Match | 后端 Sheet_Spec 的 `item_id`/`field_keys` ↔ 前端 Storage_Key ↔ 前端行模型字段名 三者逐字一致 |
| Orphan_Key | 导入写入了前端从不读取的 `item_id`（键漂移的后果），表现为"导入返回 200 且计数正常，但底稿看不到数据" |
| Round_Trip | 导出模板/数据 → 填写/修改 → 导入 → 前端界面回显同值 的完整闭环验证 |
| Contract_Guard | 断言 Three_Way_Key_Match 与中央必填列集合不漂移的自动化测试 |

## Requirements

### Requirement 1: 中央导入覆盖模式真实生效

**User Story:** 作为审计助理，我重复上传同一份填好的调整分录模板时，选择"覆盖"应替换上次导入的结果而不是成倍追加，避免调整额被重复计入试算表。

#### Acceptance Criteria

1. WHEN 中央导入以 `mode=overwrite` 提交 THEN 系统 SHALL 把 Import_Mode 传递到调整分录导入实现，并在写入新分录前使本项目本年度**由中央导入产生的**分录失效（软删），使重复上传同一文件不产生重复分录组。
2. WHEN 中央导入以 `mode=append` 提交 THEN 系统 SHALL 保持当前行为逐字节不变（仅追加，不触碰既有分录）。
3. WHERE 覆盖范围判定 THE 系统 SHALL 只覆盖 `origin` 为手工/中央导入的分录，且 SHALL NOT 覆盖 `origin='workpaper'`（底稿同步而来）或已审批（approved）的分录。
4. IF 存在活跃协作（`adjustment_collaboration` 活跃状态）的分录组 THEN 系统 SHALL 跳过该组并在返回结果中计入 `skipped`，且 SHALL 在响应中给出可读原因。
5. WHEN 覆盖执行完毕 THEN 系统 SHALL 在返回结果中区分 `imported`/`skipped`/`failed` 三个计数，且 `skipped` 反映真实跳过数（不得恒为 0）。
6. WHEN 覆盖导致既有分录失效 THEN 系统 SHALL 触发与手工删除同一条试算表重算链路，使 `trial_balance` 不残留被覆盖分录的影响。

### Requirement 2: 示例行判定不得吞掉真实数据

**User Story:** 作为审计助理，我直接在模板示例行的位置上覆盖填写第一笔真实分录时，这一行必须被正常导入，而不是被当成示例静默丢弃。

#### Acceptance Criteria

1. WHEN 数据行与模板 Example_Row 仅部分字段相同（例如编号仍为 `AJE-001`、类型为 `AJE`、科目恰好与示例相同）THEN 系统 SHALL 将其视为真实数据行并正常导入。
2. WHEN 数据行与模板 Example_Row 的**全部可比字段逐字段相等** THEN 系统 SHALL 将其识别为 Example_Row 并跳过，且 SHALL NOT 计入 `failed`。
3. WHERE 存在被跳过的 Example_Row THE 系统 SHALL 在返回结果中以独立口径可见（计入 `skipped` 或独立字段），使用户不会把"被跳过"误解为"已导入"。
4. IF 用户提交的文件不含任何 Example_Row THEN 系统 SHALL 不因示例判定而丢弃任何行。
5. WHEN 判定逻辑被修改 THEN 系统 SHALL 保持"模板内置示例行仍被正确跳过"这一既有行为（不得因收紧判定而让示例行变成脏数据）。

### Requirement 3: 导出汇总可回流（导出→修改→导回）

**User Story:** 作为现场经理，我导出现有调整分录汇总、在 Excel 里改完金额或摘要后直接导回，而不需要手工把数据搬进另一份空模板。

#### Acceptance Criteria

1. WHEN 系统导出调整分录汇总 THEN 导出文件 SHALL 包含导入校验所需的全部必填列（含「类型」列），使该文件可被中央导入直接接受。
2. WHEN 导入文件缺少「类型」列但 sheet 名可判别调整类型（如 `AJE审计调整`/`RJE重分类`）THEN 系统 SHALL 从 sheet 名兜底推断类型，而不是直接以"缺少必填列"拒绝整表。
3. IF sheet 名与「类型」列同时存在且不一致 THEN 系统 SHALL 以列值为准，并 SHALL 在响应中提示该行存在类型来源冲突。
4. WHEN 导出汇总被原样导回（未做任何修改）且 `mode=overwrite` THEN 系统 SHALL 使中央分录集合在业务上等价于导出前（不产生重复、不丢失分录）。
5. WHERE 导出列集合发生变化 THE 系统 SHALL 保持既有富模板（`export-template`）列集合不变，使用户手上已填好的旧模板仍可导入。

### Requirement 4: 模板下载入口统一为项目感知富模板

**User Story:** 作为审计助理，无论我从工具栏还是从导入弹窗里下载模板，拿到的都应是带项目科目库和科目下拉的那一份，避免手打科目名出错。

#### Acceptance Criteria

1. WHEN 用户在导入弹窗内点击下载模板 THEN 系统 SHALL 提供与工具栏一致的项目感知富模板（含项目科目库 sheet、科目下拉、编码/名称联动）。
2. WHERE 项目上下文缺失（未选定项目）THE 系统 SHALL 降级提供通用裸模板，并明确提示"无科目下拉，请核对科目编码/名称"。
3. WHEN 用户使用任一入口下载的模板填写并导入 THEN 系统 SHALL 均能接受（两种模板的必填列集合保持互相兼容）。

### Requirement 5: 底稿调整 tab 导入导出契约三方对齐

**User Story:** 作为审计助理，我在某个循环的调整分录页导出模板、填好导入后，界面必须显示我刚导入的分录，而不是"提示成功但表里还是空的"。

#### Acceptance Criteria

1. WHEN 任一已注册的调整 sheet 执行导入 THEN 系统 SHALL 把数据写入前端实际读取的 Storage_Key，使导入后界面刷新即可回显（不得产生 Orphan_Key）。
2. WHERE 后端 Sheet_Spec 与前端存在字段名差异 THE 系统 SHALL 通过显式字段映射使导出列、导入解析、前端行模型三者语义一一对应，且 SHALL NOT 丢弃用户在模板中填写的任何有效列。
3. WHEN 某调整 sheet 的行模型含前端使用而后端 Sheet_Spec 缺失的字段（如分录编号、对方科目）THEN 系统 SHALL 在导出模板中提供对应列并在导入时写回该字段。
4. WHEN 某调整 sheet 的金额字段命名与前端不一致 THEN 系统 SHALL 对齐金额字段，使导入后的借贷金额在界面与借贷平衡校验中正确参与计算。
5. WHEN 用户对尚未注册导入导出的调整 sheet 点击导入导出 THEN 系统 SHALL 提供该 sheet 的 Sheet_Spec 使其可用，或 SHALL 明确告知不支持（不得以"不支持的 sheet"报错的形式暴露注册遗漏）。
6. WHEN 契约对齐完成 THEN 每张受影响 sheet SHALL 通过一次 Round_Trip 验证（导出→填→导入→界面回显同值），且 SHALL NOT 以"接口返回 200"替代回显验证。
7. WHERE 已核实无漂移的 sheet THE 系统 SHALL 保持其导入导出行为逐字节不变。

### Requirement 6: K12-3 存储结构收敛

**User Story:** 作为开发者，我需要 K12-3 的前后端采用同一种存储结构，避免导入写 JSON 数组而前端读 per-field 键这类结构级不匹配。

#### Acceptance Criteria

1. WHEN 确定 K12-3 存储结构 THEN 系统 SHALL 收敛为单一结构（前端迁 JSON 数组 或 后端写 per-field 键），且 SHALL 在设计阶段明确选定其一并说明理由。
2. WHEN 结构收敛实施 THEN 系统 SHALL 保证既有已保存数据可读（迁移或双读兼容），且 SHALL NOT 丢失用户已录入的分录。
3. WHEN 收敛完成 THEN K12-3 SHALL 满足 Requirement 5 的全部验收标准（含 Round_Trip 回显）。

### Requirement 7: 契约守卫防再次漂移

**User Story:** 作为开发者，我希望下次有人改动某个调整 sheet 的存储键或中央模板列时，CI 立刻失败，而不是等用户报"导入没反应"。

#### Acceptance Criteria

1. WHEN 运行契约守卫 THEN 系统 SHALL 断言全部已注册调整 sheet 满足 Three_Way_Key_Match，任一不一致即失败并指出具体 sheet 与字段。
2. WHEN 运行契约守卫 THEN 系统 SHALL 断言中央导入的必填列集合与富模板、汇总导出三者互相兼容（导出产物可被导入接受）。
3. WHERE 新增调整 sheet 的导入导出 THE 守卫 SHALL 自动纳入校验（以注册表为遍历源，不靠逐条硬编码清单）。
4. IF 某 sheet 被有意排除（如结构特殊、暂不支持导入）THEN 守卫 SHALL 要求其登记在显式豁免清单中并附原因，使遗漏与豁免可区分。

### Requirement 8: 零回归与增量可回退

**User Story:** 作为业务合伙人，我需要这次修复不改变既有正确路径的结果，任一波出问题都能单独回退。

#### Acceptance Criteria

1. WHEN 未使用新增能力 THEN 既有中央导入（`append`）、富模板导出、各无漂移 sheet 的导入导出 SHALL 与改动前逐字节等价。
2. WHERE 底稿→中央同步链路 THE 系统 SHALL 保持 `syncToCentral` / `sync-from-workpaper` 的幂等 `source_ref`、`origin='workpaper'`、协作锁行为不变。
3. WHERE 试算表口径 THE 系统 SHALL 保持 `recalc` 从分录头表聚合、`origin='workpaper'` 过滤消双计的行为不变。
4. WHEN 分波交付 THEN 中央 4 项修复 SHALL 可独立发布并独立回退，不依赖底稿契约对齐波次完成。
5. WHEN 每波结束 THEN 系统 SHALL 通过该波涉及模块的既有测试全量回归，且 SHALL NOT 以放宽断言/跳过用例的方式取得通过。

### Requirement 9: 正确性属性化可测

**User Story:** 作为开发者，我需要把上述关键规则表达为可自动验证的属性，避免只靠一次手工点测。

#### Acceptance Criteria

1. WHEN 编写测试 THEN 系统 SHALL 覆盖属性：覆盖模式幂等（同一文件以 overwrite 导入 N 次结果与 1 次等价）。
2. WHEN 编写测试 THEN 系统 SHALL 覆盖属性：示例行判定单调（仅全字段相等才跳过；任一可比字段不同即为数据行）。
3. WHEN 编写测试 THEN 系统 SHALL 覆盖属性：导出→导入闭环保真（汇总导出产物可被导入解析，类型/金额/科目不失真）。
4. WHEN 编写测试 THEN 系统 SHALL 覆盖属性：无 Orphan_Key（对注册表内每张 sheet，导入写入键 ∈ 前端读取键集合）。
5. WHEN 编写测试 THEN 系统 SHALL 覆盖属性：字段完备（导出模板列集合 ⊇ 前端行模型的用户可填字段）。
6. WHEN 编写测试 THEN 系统 SHALL 覆盖属性：覆盖范围安全（overwrite 不触碰 workpaper-origin / approved / 活跃协作分录）。
