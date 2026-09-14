# Implementation Plan: Excel 结构性插行与位移感知未管理区域验证

## Overview

实现语言 **Python 3.12**。共 22 个任务、6 个 Wave。**不新增数据库迁移**（磁盘最高 V153，本 spec 不加）。

交付顺序遵循 design.md §Rollout 的一条硬约束：**先补检查，再动结构**。`dimension`/`hyperlinks`/`autoFilter`/`rowBreaks` 今天不在任何 aspect 里，先动它们等于"改了没人看"（假绿）。

改动文件（全部是既有共享文件，改动一律**只加不减判据**）：

| 记号 | 路径 | 性质 |
|---|---|---|
| M1 | `backend/app/services/workpaper_sync/excel_extract.py` | 改（`_SHEET_STRUCTURE_BLOCKS` 扩充 + shift-aware digest） |
| M2 | `backend/app/services/workpaper_sync/excel_materialize.py` | 改（`RowShiftPlan` / 位移阶段 / footer 两门 / 第 4 步） |
| M3 | `backend/app/services/workpaper_sync/contracts.py` | 改（`FooterAnchorSpec.carries_total_formula`） |
| M4 | `backend/app/services/workpaper_sync/adapters/excel.py` | 改（`verify_unmanaged_regions` 透传 `row_shift`） |
| N1 | `backend/app/services/workpaper_sync/excel_row_shift.py` | 新增（位移纯函数 + 清单 + `si` 索引） |
| N2 | `backend/scripts/check/check_excel_row_insertion_readiness.py` | 新增（全量底稿可插行清册） |
| N3 | `backend/scripts/diagnose/mutate_excel_row_shift_guards.py` | 新增（变异） |
| T1 | `backend/tests/workpaper_sync/test_excel_row_shift.py` | 新增 |
| T2 | `backend/tests/workpaper_sync/test_excel_shift_aware_verification.py` | 新增 |
| T3 | `backend/tests/workpaper_sync/test_excel_row_insertion_readiness.py` | 新增 |

命令一律 Windows PowerShell、仓库根、`;` 分隔、`cwd` 参数代替 `cd`；pytest 从仓库根跑，**不跑全量** `backend/tests`（1522 个文件），按引用关系反查辐射面。

## M0 复选框对齐（2026-09-04 · A · 5 泳道分工书第 0 步）

原记 0/27，实测 **Wave 0 的 Task 2 与 Wave 1 全部（4/5/6/7/8）已在磁盘且行为可验**。
不对齐会让 B 把已交付的位移函数本体重做一遍。取证 = 真实 K11 模板上真跑，产物
`tmp_a_m0_probe_s.json` / `tmp_a_m0_probe_s3.json`。

**已勾（实测依据逐条）**：

| 任务 | 实测证据（`backend/wp_templates/K/K11 资产减值损失.xlsx` → `xl/worksheets/sheet3.xml`「审定表K11-1」） |
|---|---|
2 | `_SHEET_STRUCTURE_BLOCKS` 已 6 → **10** 项，`dimension` / `hyperlinks` / `autoFilter` / `rowBreaks` 四项在列 |
4 | `ROW_BEARING_STRUCTURES` **12** 项；差集 `HANDLED_BY_IDENTITY_RETENTION_GATE = (("table","@ref"),)` 显式登记；`assert_shift_handlers_cover_structures()` **真跑 PASS**；`scan_unlisted_row_bearing_elements` 对真实受管 sheet 返回 `()` |
5 | `RowShiftPlan(insert_at, count, style_from, table_key)` frozen；三类非法取值三个**互不相同**的 `error_code`（`…plan_count_invalid` / `…plan_range_invalid` / `…style_source_missing`）；`ShiftReport` **8** 字段；`shift(unshift(r))==r` 全域成立；`inserted_rows` 正确 |
6 | 真实位移一次：`<row>` **37 → 39**、`renumbered_rows=18`、`renumbered_cells=174`、`inserted_rows=2`；**纯函数**（同输入重复调用逐字节相同） |
7 | `shifted_refs={"mergeCell@ref":1}`、`dimension_updated=true`、`shifted_formula_text_ranges=7` |
8 | `shared_formula_groups` 解出 **6** 组：si=1 主格 `H8` / `ref=H8:H25` / **17** 成员（design 点名的那组）；footer si=3 `B26:G26`（5 成员）、si=4 `H26`（0 成员）；主格与成员可区分 |

**故意不勾**：

| 任务 | 为什么 |
|---|---|
1 | 影响面 JSON 快照与"哪些既有测试断言了 digest/coverage"的反查清单**磁盘无产物**；结论只活在会话记忆里 |
3 | Wave 0 门（既有用例逐条判"变严 vs 被破"）未留可复算证据 |
2.1 / 5.1 / 6.1 / 8.1 | T1 / T2 测试文件不存在 |
9 ~ 18 | `excel_extract` 的三个 digest 函数**无 `row_shift` 参数**；`excel_materialize` / `contracts` / `adapters/excel` 对 `row_shift` / `RowShiftPlan` / `carries_total_formula` **零 token** |
19 ~ 22 | N2 / N3 / T1~T3 均不存在 |

🔴 **`excel_row_shift.py` 在 `backend/app` / `backend/scripts` / `backend/tests` 三处引用数均为 0**
（AST import 扫描，非 grep）—— 位移函数本体虽已可用，**仍是死代码**。所以 B 的最高优先级是
Wave 4 的 Task 16 / 18 接线，不是新写位移逻辑。

🔴 **`excel_row_shift.py` 在 git 里是 `??` 未跟踪**；`excel_extract.py` 是 `M` 未提交。
丢工作树即 Wave 0 + Wave 1 全部蒸发。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 0,
      "name": "先补检查：让四类结构能红",
      "tasks": ["1", "2", "2.1", "3"],
      "depends_on": [],
      "rationale": "在 verifier 补齐 `_SHEET_STRUCTURE_BLOCKS` 之前动结构，改了也没人看 = 假绿。Task 1 只读取证影响面、Task 2 只让四类结构进入检查（不动位移逻辑）、Task 3 逐条核对既有用例是「判据变严」还是「判据被破」"
    },
    {
      "wave": 1,
      "name": "纯函数：清单 / 位移 / si 索引",
      "tasks": ["4", "5", "5.1", "6", "6.1", "7", "8", "8.1"],
      "depends_on": [0],
      "rationale": "位移必须是零写入面的纯函数，且在写格之前完成。清单（Task 4）先立，才能让「出现清单外携带行号的元素」fail closed；si 索引（Task 8）是共享公式扩张的前置"
    },
    {
      "wave": 2,
      "name": "shift-aware 归一化与 verifier 接线",
      "tasks": ["9", "10", "10.1", "11"],
      "depends_on": [1],
      "rationale": "验证器要用**声明**位移量归一化，故依赖 Wave 1 的 `RowShiftPlan`。Task 11 的零位移逐字节不变判据必须先绿，才证明这层是加法而非行为翻转"
    },
    {
      "wave": 3,
      "name": "footer 两门 / 共享公式扩张 / 契约字段",
      "tasks": ["12", "13", "14", "15"],
      "depends_on": [2],
      "rationale": "footer 两门要用位移后区间求值，故依赖归一化已就位；共享公式扩张依赖 Wave 1 的 si 索引；契约字段 `carries_total_formula` 是纯增量，不改任何既有契约 JSON"
    },
    {
      "wave": 4,
      "name": "计划接线与残余分支",
      "tasks": ["16", "17", "18"],
      "depends_on": [3],
      "rationale": "接线放最后：6.2 算位移计划必须排在 footer 两门之前（两门要用位移后区间），而两门在 Wave 3 才位移感知。残余 `RowSetDivergenceError` 分支必须保留并强化，不得为接线放宽"
    },
    {
      "wave": 5,
      "name": "全量清册 / 变异 / 真实环境",
      "tasks": ["19", "20", "21", "22"],
      "depends_on": [4],
      "rationale": "清册要登记真实状态，需等能力落地才知哪些 blocked；变异检验要在全部判据到位后做；收口核查产物入库，防「spec 全绿 ≠ 产物已入库」"
    }
  ],
  "dependencies": {
    "1": [], "2": ["1"], "2.1": ["2"], "3": ["1", "2", "2.1"],
    "4": [], "5": ["4"], "5.1": ["5"], "6": ["4", "5"], "6.1": ["6"],
    "7": ["5", "6"], "8": ["6", "7"], "8.1": ["8"],
    "9": ["3", "5"], "10": ["9"], "10.1": ["10"], "11": ["9", "10", "10.1"],
    "12": ["5", "11"], "13": ["6", "12"], "14": ["13"], "15": ["14"],
    "16": ["7", "11", "12", "15"], "17": ["16"], "18": ["16", "17"],
    "19": ["18"], "20": ["18", "19"], "21": ["20"], "22": ["20", "21"]
  },
  "gates": {
    "structure_blocks_first": ["1", "2", "2.1", "3"],
    "pure_functions": ["5", "5.1", "6", "6.1", "7", "8", "8.1"],
    "verifier": ["9", "10", "10.1", "11"],
    "footer_and_formula": ["12", "13", "14", "15"],
    "plan_wiring": ["16", "17", "18"],
    "closure": ["19", "20", "21", "22"]
  }
}
```

依赖图中每个依赖必须指向更早 Wave 或同 Wave 更小任务号。

## Tasks

### Wave 0：先补检查 —— 让四类结构能红

- [x] 1. 实测 `_SHEET_STRUCTURE_BLOCKS` 扩充的影响面（只读）
  - 扫真实模板：K11 / H1 / D2 / G7 / B60 的受管 sheet 是否含 `dimension` / `hyperlinks` / `autoFilter` / `rowBreaks`，逐项计数落 JSON
  - 反查引用关系：哪些既有测试断言了 `managed_sheet_structure` 的具体 digest 值或 coverage 计数
  - 本任务**一行代码不改**，只产出影响面快照，作为 Task 2 的前置判据
  - 若 K11 一项都不含 ⇒ Property 2 需另造 fixture（design.md §Open Gates 第 2 项），在此裁决
  - _Requirements: 1.3, 9.2, 9.5_
  - **实测结果**（落 `excel_extract.py` 的 `_SHEET_STRUCTURE_BLOCKS` 注释表，5 个权威模板 × 4 项，
    受管 sheet 逐个由 `_parse_workbook_xml` 定位、不按 sheet 号猜）：

    | 模板 | 受管 sheet | part | dimension | hyperlinks | autoFilter | rowBreaks |
    |---|---|---|---:|---:|---:|---:|
    | K11 | 审定表K11-1 | sheet3.xml | 1 | 1 | 0 | 0 |
    | B60 | B60-1工时预算与控制表 | sheet2.xml | 1 | 1 | 0 | 0 |
    | D2 | 明细表D2-2 | sheet8.xml | 1 | 1 | 0 | 0 |
    | H1 | 减少检查表H1-8 | sheet12.xml | 1 | 1 | 0 | 0 |
    | G7 | 附注披露信息（国企） | sheet5.xml | 1 | 0 | 0 | 0 |

  - 🔴 **首版把 K11 一行记错过两处，已复测更正**：受管 sheet 是 `审定表K11-1`（sheet3），
    首版记成 sheet4（那是「附注披露信息（上市公司）」，不是受管 sheet）；`hyperlinks`
    实测为 1 而首版记成 0。⇒ **定位受管 sheet 必须走 `_parse_workbook_xml`，不得按 sheet 号推**
  - **Open Gate 2 裁决**：`dimension`（5/5）与 `hyperlinks`（4/5，G7 除外）可直接用真实模板
    做非空验证；**`autoFilter` / `rowBreaks` 全库为 0**，其判据必须用真实模板的 **zip 级注入变体**，
    手搓最小 xlsx 会让判据在空集上恒真
  - **辐射面**（按引用关系现算，非写死目录）：断言具体 coverage 数值的既有用例恰一处
    = `test_task42_h1_grouped_dynamic_pilot` 的 `"managed_sheet_structure": 4` → 6（H1 = 4 + dimension + hyperlinks）；
    其余引用方（`test_task37` / `test_task38` / `test_task40` / `test_task41` / `test_task43`）断言的是
    「aspect 名集合」或「各项 coverage > 0」，扩充只增不减 ⇒ 不受影响

- [x] 2. 扩充 `_SHEET_STRUCTURE_BLOCKS` 并让四类结构可红 (M1)
  - 往 `_SHEET_STRUCTURE_BLOCKS` 加 `dimension` / `hyperlinks` / `autoFilter` / `rowBreaks`
  - **不得**同时改任何位移逻辑：本任务只让它们"进入检查"，动它们是 Wave 1 的事
  - 逐项写反向自检：真实模板上改动该结构一处 ⇒ `managed_sheet_structure` aspect 必须打红
  - K11 不含某项时用**真实模板的合法变体**（zip 级注入该元素）作 fixture，不手搓最小 xlsx（那会让判据空转）
  - 验证 Property 2
  - _Requirements: 1.3, 1.4_
  - **注入位置不可随手挑**：`CT_Worksheet` 是有序 sequence。K11 受管 sheet 实测顶层顺序
    `sheetPr → dimension → sheetViews → sheetFormatPr → cols → sheetData → mergeCells →
    phoneticPr → hyperlinks → printOptions → pageMargins → pageSetup → headerFooter`
    ⇒ `autoFilter` 插 `<mergeCells` 前、`dataValidations`/`conditionalFormatting` 插
    `<hyperlinks` 前、`rowBreaks` 插 `</worksheet>` 前。插错位置产出的是**非法**变体，
    而 `ET.iterparse` 不校验顺序 ⇒ digest 判据照样"通过"

- [x]* 2.1 属性测试：四类结构各自能红 (T2)
  - **Property 2: `_SHEET_STRUCTURE_BLOCKS` 覆盖四类新结构且各自能红**
  - **Validates: Requirements 1.3, 1.4**
  - 四类各一例：注入/改动一处 ⇒ 断言 `first_difference` 含 `managed_sheet_structure`
  - 反向自检：把某一项从 `_SHEET_STRUCTURE_BLOCKS` 里删掉 ⇒ 对应用例必须变绿（证明判据不是恒真）
  - 🔴 **实施中纠正的一处分母错误**：首版拿「原始六项的个数」当基线覆盖数下限，实测
    `found=5 < 6` 直接打红。原因是 `dataValidations` / `conditionalFormatting` /
    `sheetProtection` 在 K11 受管 sheet 上**一个都没有** —— 「十项清单」不等于「某张 sheet
    上有十项」。已改为把真实存在集写死：`{sheetPr, cols, mergeCells, dimension, hyperlinks}` = 5

- [x] 3. 关闭 Wave 0 门：既有用例逐条核对
  - 按 Task 1 的影响面清单逐条跑受影响测试，判定每处红是"判据变严"还是"判据被破"
  - "判据变严"的用例更新期望值并写明理由；"判据被破"的立即回退本 Wave 改动重新设计
  - 断言 `backend/wp_templates/` 零字节改动
  - 验证 Property 25
  - _Requirements: 9.1, 9.2, 9.3, 9.5_
  - **实测**：辐射面六个文件 **708 passed / 0 failed**。唯一需要更新期望值的是
    `test_task42_h1_grouped_dynamic_pilot` 的 `"managed_sheet_structure": 4 → 6`
    （H1 受管 sheet 实测含 `dimension` 1 个 + `hyperlinks` 1 个）⇒ 判据**变严**，非判据被破
  - **`backend/wp_templates/` 零字节改动**：`TEMPLATE_SHA` 在 T1/T2 与 `test_task38` 三处
    各自断言；探针另做过一次 `TEMPLATE.read_bytes() == raw` 自证
  - 归因核查：工作树里同时被改的 `test_task45_pilot_legacy_deletion.py`（Vue composable
    字段契约）与 `test_task54_l_cycle_migration.py`（`_strip_docstrings` +
    `excel_sheet_visibility`）**均非本 spec 改动**，属并发会话，未碰

### Wave 1：纯函数 —— 清单 / 位移 / si 索引

- [x] 4. 建位移敏感清单与双向锁 (N1)
  - 定义 `ROW_BEARING_STRUCTURES` 模块常量（12 项，见 design.md §Data Model）
  - `table@ref` 标注为"由 identity 保留门承接"，与本函数处理集的差集**显式登记**
  - 实现 `assert_shift_handlers_cover_structures()`：AST 扫本模块，清单里每项（除差集）必须有对应处理分支；函数里的分支必须在清单里
  - 实现 `scan_unlisted_row_bearing_elements(xml)`：受管 sheet 上出现清单外携带行号的元素即 fail closed 并指出 tag
  - AST 扫描**不得**用 `strip_comments`（会剥掉三引号内嵌 SQL/XML 文本块）
  - 验证 Property 1
  - _Requirements: 1.1, 1.2, 1.5, 1.6_

- [x] 5. 建 `RowShiftPlan` 与 `ShiftReport` (N1)
  - frozen dataclass，`__post_init__` 调 `assert_no_mutation_surface` + 校验 `count > 0` / `insert_at >= 1` / `style_from >= 1`
  - 派生 `shift(row)` / `unshift(row)` / `inserted_rows`
  - `ShiftReport` 逐阶段计数（7 个字段），供守卫断言"分支真执行了"而非"没报错"
  - 各非法取值抛**独立可分辨**的错误：`RowShiftPlanInvalidError` 子类型分 count / 越界 / 样式行三种
  - 验证 Property 4
  - _Requirements: 2.1, 2.2, 2.5, 3.6_

- [x]* 5.1 属性测试：计划的零写入面与非法取值 (T1)
  - **Property 4: `RowShiftPlan` 零写入面且非法取值各抛独立错误**
  - **Validates: Requirements 2.2, 2.5, 3.6**
  - 塞 session/repository 形态对象 ⇒ 必抛；`count<=0` / 插入点越界 / 样式行缺失三例的 `error_code` 两两不同
  - hypothesis 生成合法取值，断言 `shift(unshift(r)) == r` 对 `r >= insert_at + count` 成立

- [x] 6. 实现 `shift_sheet_rows` 阶段 A/B（行重编号与插入） (N1)
  - 阶段 A：`<row r>` 与 `<c r>` **自底向上**重编号（自顶向下会让刚改过的行与原始行不可区分）
  - 阶段 B：插入 `count` 个新 `<row>`，每列 `s=` 取自 `style_from` 行同列；不写任何业务值
  - 保持 `<row>` 升序、无重复 `r`
  - 纯函数：不碰磁盘、不改入参、同输入重复调用逐字节相同
  - 验证 Property 6、Property 7、Property 8
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.7_

- [x]* 6.1 属性测试：重编号与样式继承 (T1)
  - **Property 6: 位移是纯函数**
  - **Validates: Requirements 3.1**
  - **Property 7: 插入点以下行号恰增 count，其余不变，升序无重复**
  - **Validates: Requirements 3.3, 3.7**
  - **Property 8: 新插入行样式与来源行同列相等且无业务值**
  - **Validates: Requirements 3.4, 3.5**
  - Property 7 用真实 K11 模板字节，hypothesis 生成 `insert_at` / `count`，逐行核对
  - Property 8 的反向自检：把样式继承改成 `style=""` ⇒ 本条必须打红

- [x] 7. 实现 `shift_sheet_rows` 阶段 C/D/F（ref/sqref/dimension 平移） (N1)
  - 阶段 C：`mergeCell@ref` / `dataValidation@sqref` / `conditionalFormatting@sqref`
  - 阶段 D：`hyperlink@ref` / `autoFilter@ref` / `brk@id`
  - 阶段 F：`dimension@ref` 末行不小于实际最大行号
  - `sqref` 可含多个空格分隔的区间，逐区间处理
  - 验证 Property 9
  - _Requirements: 1.1, 3.8_
  - 🔴 **本任务在真实模板上是空集，判据必须靠 zip 级注入变体**：K11 受管 sheet 实测
    `dataValidation` / `conditionalFormatting` / `autoFilter` / `rowBreaks` **全为 0**，
    `hyperlink` 只有 1 个且在插入点**之上**（`J3`，不会位移）。⇒ 只用真实模板验证时
    阶段 C/D 的五条分支**全部不可达**，代码删掉照样绿。T2 用注入变体各走一次，
    并对 `hyperlink` / `autoFilter` 额外造「挪到插入点之下」的对照例
  - 🔴 **实施中发现并修掉两处真实生产缺陷（全库 351 份 xlsx / 2722 张 sheet 实测）**：

    | 标签 | 命中文件 | 元素数 | 含 A1 引用 | 首版登记 | 后果 |
    |---|---:|---:|---:|---|---|
    | `<cfRule><formula>` | **34/351** | 552 | **72** | 两张清单都没有 | 34 份模板 `scan_unlisted_row_bearing_elements` 整体 fail closed，位移功能在它们上不可用 |
    | `<dataValidation><formula1>` | **232/351** | 1081 | **108** | 误登记进 `_ROW_AGNOSTIC_TAGS` | 位移后取值来源仍指向旧行，**静默错行** |
    | `<dataValidation><formula2>` | 4/351 | 13 | 0 | 同上 | 同类 |

    实测样例是真区间：`$Q$36:$Q$40` / `$B$35:$B$41` / `$R$8:$R$91`。
    修法：三者移入 `ROW_BEARING_STRUCTURES`（清单 12 → **15** 项）+ 新增阶段 C2
    `_shift_element_text`（走 `_rewrite_formula_refs` 唯一入口，不新造 A1 改写）
  - 🔴 **连带补的第三处**：`<cfRule><formula>` 里引号是 **XML 实体**形态
    （权威模板实测 `A8=&quot;&quot;`）。`&quot;` 后紧跟的字符是 `;`，而 `;` **不在**
    `_LEFT_BOUNDARY_BLOCK` 里 ⇒ `&quot;K30&quot;` 里的 `K30` 会被当坐标位移。
    已加 `_ENTITY_LITERAL_RE` 识别实体字面量；该修正对 `<f>` 单元格公式同样生效
  - ⚠ **`autoFilter@ref` 末行恰等于 `insert_at-1` 时刻意不扩张**（K11 的 `A7:N25` + 插入点 26）：
    筛选区间语义由用户设定，不由受管行区间决定，扩张它等于替审计师改筛选范围
    （design.md 拒绝方案第 8 条同源）。此行为已写成判据钉住，将来要改必须是有意的

- [x] 8. 建 `si` → (主格, ref) 索引层 (N1)
  - 解析 `<f t="shared" ref="..." si="N">`（主格）与 `<f t="shared" si="N"/>`（成员）
  - 当前代码只判 `ref` 含不含冒号、从不解析 `si`；本任务补上该索引
  - 提供 `shared_formula_groups(xml) -> Mapping[int, SharedFormulaGroup]`，含主格坐标、`ref`、成员坐标集
  - 对真实 K11 模板断言：`H8:H25` si=1 与 footer si=3 都被正确解析，主格与成员可区分
  - 验证 Property 10
  - _Requirements: 4.1_

- [x]* 8.1 属性测试：si 索引对真实模板正确 (T1)
  - **Property 10: `si` 索引对真实模板解析正确且主格成员可区分**
  - **Validates: Requirements 4.1**
  - 断言 K11 的两组 si 都命中，成员集合非空，主格恰一个
  - 反向自检：把主格判据改成"任何带 si 的都是主格" ⇒ 本条必须打红

### Wave 2：shift-aware 归一化与 verifier 接线

- [x] 9. 给 digest 加 `row_shift` 归一化 (M1)
  - `_managed_sheet_cell_digest(..., row_shift=None)`：非受管格的 `r` 按 `plan.unshift` 归一化后再喂 hash
  - `_sheet_structure_digest(..., row_shift=None)`：结构块里携带行号的属性归一化后再序列化
  - 新插入行的格**排除**在非受管集合之外（它们属受管区域）
  - `row_shift=None` 时行为逐字节不变（纯增量）
  - 归一化只作用于比对，**不改动任何 artifact 字节**
  - 验证 Property 17、Property 19
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7_
  - 🔴 **实施中补的第一条：AC 6.2 说的是「行号」，不只是 `r` 属性。** 位移同时会改**公式文本**
    里的 A1 行号（K11 实测：非受管格 `C28` 的 `C26-C27`→`C28-C29`、`H26` 的 `G26-D26`→`G28-D28`）。
    只归一化 `r` 时这些格必判漂移 ⇒ Property 17 根本不可能成立。已一并归一化公式文本，
    走 `excel_row_shift.remap_a1_rows` 唯一入口（跨 sheet 引用 / 带数字函数名 / 字符串字面量
    三类不会被误改；列标不动，所以「B 列改成 C 列」照旧判漂移）
  - 🔴 **第二条：归一化用的三张表由 `ROW_BEARING_STRUCTURES` 派生，不在 verifier 侧手抄。**
    手抄第二份的两个方向都很贵：漏一项 ⇒ 那类结构位移不被归一化（假红）；多一项 ⇒ 真实漂移
    被抹平（假绿）。落法 = `excel_row_shift` 里 `_derive_structure_tables()` +
    `assert_structure_normalization_covers_structures()`（**import 期自检**：清单每项恰好落进
    「A1 属性 / 裸行号属性 / 元素文本 / 已委派」四桶之一）。实测派生结果：
    6 个 A1 属性 + 1 个裸行号属性（`brk@id`）+ 3 个文本标签 + 5 个已委派 = 15 项
  - 🔴 **第三条：判「verifier 没抄第二份」用对象身份而非内容相等。**
    `X.STRUCTURE_ROW_BEARING_ATTRS is RS.STRUCTURE_ROW_BEARING_ATTRS` —— 内容相等型判据
    挡不住「有人抄了一份、两份暂时还一样」
  - **import 方向合法性已实测**：`excel_row_shift` 不在 `FORBIDDEN_DOWNSTREAM_MODULES`
    （那条禁的是 materializer / rematerializer / adapters.excel 三个**写入侧**模块），
    `assert_no_materializer_dependency()` 现读返回 `()`

- [x] 10. `unmanaged_region_digest` 与 `verify_unmanaged_regions` 透传 `row_shift` (M1, M4)
  - 两个函数各加可选 `row_shift`，透传到两个 digest 函数
  - `adapters/excel.py` 的 `ExcelAdapter.verify_unmanaged_regions` 同步透传
  - 实测位移量与声明不符时判不等价（用"声明插 2 行、实际插 3 行"的 fixture）
  - 验证 Property 20
  - _Requirements: 6.1, 6.9_
  - 🔴 **归一化只给 after 侧**：before 侧本来就是位移前口径，**两侧都归一化 = 什么都没归一化**，
    且会让「声明了插行却根本没插」静默通过（变异 M13 守这一条）
  - `adapters/excel.py` 的 `row_shift` 标 `Any` 而不是 import `RowShiftPlan`：本层只转手，
    不用那个类型的任何成员，标死类型只是给该模块多加一条 import 边
  - Property 20 用 **5 组「实测 × 声明」不匹配组合**（3×2 / 2×3 / 1×2 / 5×2 / 2×1）+
    「根本没插行却声明插 2 行」一条反面例。每组先断言「声明==实测那一支是通的」，
    否则后面的不等价说明不了任何事

- [x]* 10.1 属性测试：归一化不放宽无关判据 (T2)
  - **Property 17: 与计划一致的插行使全部 aspect 判等价**
  - **Validates: Requirements 6.1, 6.2, 6.3, 6.5**
  - **Property 18: 归一化不放宽与行位移无关的判据**
  - **Validates: Requirements 6.6, 6.8**
  - **Property 20: 声明位移量与实测不符时判不等价**
  - **Validates: Requirements 6.9**
  - Property 18 五例：改已有 sharedStrings 条目、改 protected_parts、改跨 sheet 部件、改非受管格的 `v`、改非受管格的 `s` —— 全部仍须判不等价
  - 🔴 **五例必须叠加在「已按计划位移」的 after 之上**，不能只在未位移的 artifact 上测：
    后者归一化根本没被激活，证明不了「归一化没放宽」。实际做了 **6 例**（加一例
    「非受管公式的**列标**被改」：`C28-C29`→`D28-D29` 归一化后分别是 `C26-C27` 与 `D26-D27`，
    仍不等 —— 这一例最能说明归一化只动行号；另一例「结构块里改合并区**列跨度**」
    `E32:F32`→`E32:G32`，行号完全按计划、只有列变了）

- [x] 11. 关闭 Wave 2 门：零位移路径逐字节不变
  - `row_shift=None` 下跑既有 Task 37 / Task 38 全部用例，逐条通过
  - 断言 artifact 字节不变（不是 digest 值不变 —— digest 因 Wave 0 扩充而变化是预期的）
  - 验证 Property 3、Property 19
  - _Requirements: 2.3, 6.4, 6.7, 9.2_
  - **实测 1033 passed / 0 failed**（Task 13 / 37 / 38 / 40 / 41 / 42 / 43 + 本 spec 的 T1/T2）
  - Property 3 的判据落在「**省略该参数** 与 **显式传 None** 产出逐字节相同的 digest」——
    这是「加法而非行为翻转」的最直接形态
  - Property 19 的判据落在**盘上事实**：跑完两轮归一化 digest + verify 后，
    before/after 两份 artifact 的 sha256 各自不变；另加「同一份字节两次归一化 digest 相同」
    （否则 verifier 会随机假红）
  - 🔴 **分母断言从「`shared_strings_prefix` 为 0 是事实」改成「八个 aspect 全部 > 0」**：
    首版照抄了 H1 的结论，而这份 instrumented K11 上 sharedStrings 实测非空
    （instrumentation 与 `patch_cells` 写入的文本进了它）。照抄别的 entry 的分母事实是个坑

### Wave 3：footer 两门 / 共享公式扩张 / 契约字段

- [x] 12. `assert_footer_anchor_stable` 改为位移感知 (M2)
  - 加可选 `row_shift`；判据由「实测 == 冻结」改为「实测 == 冻结 + count」
  - `row_shift=None` 时判据逐字相同
  - 失败消息**同时**给出实测行、冻结行、预期位移三个数值
  - 返回值语义不变（`None` 表示契约无 footer 声明）
  - 验证 Property 21
  - _Requirements: 7.1, 7.2, 7.3, 7.6_
  - 🔴 **判据写成 `plan.shift(frozen)` 而不是 `frozen + plan.count`**：footer 落在插入点
    **之上**时插行不该动它，无条件加 `count` 会把「本来就不该动」的场合判成漂移。
    `plan.shift` 自带这个边界；写成加法就要在调用侧再写一遍 `if`（写两遍就会漂移）。
    变异 M16 专守这一条
  - 冻结值非数字形态时 fail closed（位移感知要拿它做算术，不得当成「随便什么都行」继续）
  - 🔴 **纠正一处曾写错的冻结事实**：K11 的 footer anchor marker 与合计公式**同在 26 行**
    （现读 `GT_FOOTER_ROW = 26`）。首版按 `test_task37.FOOTER_ROW = 27` 推断 anchor 在 27 行，
    8 条用例连带打红 —— 27 行只是一个恰好没有公式的标签行，不是 anchor。
    ⇒ **冻结事实一律现读 `read_runtime_binding_pairs`，不从别的常量名推**

- [x] 13. 实现共享公式的位移与区间扩张 (N1)
  - 主格在插入点之上且区间跨过插入点 ⇒ `ref` 末行与公式文本内对应区间末行同时 +count
  - 主格在插入点之下 ⇒ `ref` 首末行整体 +count
  - **只**对契约声明 `carries_total_formula` 的 footer 行做扩张；受管区域之外的组只位移
  - 主格 `ref` 改写后同组成员跨度与主格不一致 ⇒ fail closed
  - 主格**永不**被替换成字面量（`SharedFormulaMasterWriteError` 的既有禁令保留）
  - 验证 Property 11、Property 13、Property 14
  - _Requirements: 4.2, 4.3, 4.6, 4.7, 4.8_
  - 🔴 **实施中补的一条裁决（真实模板探针实测，design.md 未覆盖的第三种形态）**：
    「**新插入行不加入任何既有共享公式组**，退化为按 fill-down 从主格文本翻译出的独立公式。」
    - 形态：K11 的 si=1 `ref=H8:H25`（主格 H8 文本 `G8-D8`，纵向 18 行一组）、si=2 `ref=I8:I25`。
      追加插行时 `insert_at=26`，`ref` 两端都 < 26 ⇒ 上面两条位移规则**都碰不到它**
    - 首版实现把新行做成 `<f t="shared" si="1"/>` 成员并在注释里声称「主格 ref 已在阶段 A/E 扩到
      覆盖新行」—— 该声称为假（阶段 E 只计数不改字节），真实模板实测产出
      **4 个孤儿成员**（H26/H27 属 si=1 但落在 `ref=H8:H25` 之外，I26/I27 同理）
    - **不改成"扩张 si=1 的 ref"**：Requirement 4.6 把扩张限定在契约声明 `carries_total_formula`
      的 footer 行；si=1 是**逐行**公式不是合计，无门扩张它 = 替审计师改公式（design.md 拒绝方案第 8 条）
    - 退化为独立公式后 Requirement 4.8 照旧成立（主格根本没被碰），Property 14 的成员跨度判据也成立
    - 新增 `SharedFormulaOrientationError`：样式来源行上的成员属**横向**组（主格在另一列，
      如 K11 的 si=3 `B26:G26`）时 fail closed —— 继承它需要**列**平移，本 spec 只做行位移
  - 🔴 **第二条**：`ShiftReport.extended_shared_formulas` 必须是**实测**扩张处数
    （「扩张版 vs 纯位移版」逐格比出来），不得按「主格行号 ∈ total_rows」推算。
    实测差异：K11 合计行 26 上 `SUM(B7:B25)→SUM(B7:B27)` 是真扩张（1 处），
    而 si=4 的 `G26-D26→G28-D28` 只是纯位移；按声明推会报 2，把纯位移误记成扩张 ⇒ 报告本身成了假绿帮凶
  - 🔴 **第三条（已登记的已知限制，非本 spec 解）**：新行的跨 sheet 相对引用**不平移**
    （`'明细表K11-2'!F29` 逐字照抄）。Excel 填充柄**会**平移它，本模块不跟随的理由是 R12.4
    排除跨 sheet 联动 ⇒ 交 `excel-workbook-wide-row-change-propagation`。
    代价：K11 受管区 B..G 列新行会指向与样式来源行**相同的源格**（重复取数，看着"有值"）。
    **Task 16 接线时必须把这一条作为 entry 级可插行性判据** —— 受管列上存在跨 sheet 相对引用的
    entry，在传播能力落地前只能登记为 `blocked`，不得照插（Task 19 清册需要一个对应的封闭结算词）

- [x] 14. 扩 `FooterAnchorSpec` 解析 `carries_total_formula` (M3)
  - `FooterAnchorSpec` 加字段，默认 `False`（纯增量：未声明的契约行为逐字不变）
  - `_parse_footer_anchor` 解析它；字段名不违反 CS-12 对 `row` / `row_index` / `row_number` 的禁令
  - 为真但 footer 行一处公式都没有 ⇒ fail closed
  - **不**改任何既有契约 JSON（那会改 canonical digest）；改契约是后续 entry 迁移的事
  - 验证 Property 15、Property 16
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - 🔴 **Wave 2 收口时实测发现并登记的一条耦合，必须在本任务落地**：
    - 形态：合计行的**扩张**（`SUM(B7:B25)`→`SUM(B7:B27)`，AC 4.4）**不可能**被
      `plan.unshift` 还原 —— 那正是它的语义（合计范围真的变大了，不是被推下去了）。
      `unshift(27) == 27`（27 < `insert_at + count` = 28），归一化后仍是 `SUM(B7:B27)`
    - 而 K11 的合计格 `B26` 实测**不在** `_managed_coordinates` 里（契约在 26/27/28 行只覆盖到
      `B27`）⇒ 扩张会让 `managed_sheet_unmanaged_cells` 判漂移
    - **正解**：AC 4.6 说扩张只作用于「契约声明的 footer 行」。一个引擎会合法改写的格，按定义
      就该在契约管辖之内 ⇒ **契约必须用一个 `formula` 模式字段覆盖该合计格**。
      若声明了 `carries_total_formula` 却没有字段覆盖该格，本任务应 **fail closed**
    - **不得**改成「让 verifier 反向推断扩张量」：那等于让被检查对象自己声明自己合法
      （design.md 拒绝方案第 3 条）
    - 该耦合已在 T2 的 `TestTotalFormulaExtensionCouplingIsRegistered` 里**钉成两条可执行判据**
      （一条断言「判漂移」、一条断言根因「`B26` 非受管」）。本任务落地后两条都会先红，
      指向确切的下一步 —— 那时把它们改成断言等价并删掉登记说明

- [x] 15. `assert_footer_formula_covers_managed_rows` 用位移后区间求值 (M2)
  - 加可选 `row_shift`，用 `region.last_row + count` 求值
  - 合计区间已按 Task 13 扩张 ⇒ 通过；未扩张 ⇒ 仍报 `FooterFormulaRangeError`
  - 返回值语义不变（空元组表示本次未检查任何坐标）
  - 改 raise 文本与模块 docstring 第四节第 2 条：从"共享公式主格不得在此处被改写"改成"只允许按预期位移扩张区间"
  - 验证 Property 12、Property 22
  - _Requirements: 4.4, 4.5, 7.4, 7.5, 7.6_
  - 另加 `carries_total_formula: bool = False` 参数承接 AC 5.4 的 fail-closed（声明为真但该行
    一处带公式文本的格都没有 ⇒ 抛）。**由调用方从契约读出后显式传入**，不在本函数里现查契约 ——
    函数的输入保持显式可测
  - 🔴 **位移后区间由「声明」位移量派生，不从 diff 观测**：观测值等于让被检查对象自己声明
    自己合法（design.md 拒绝方案第 3 条）
  - **两条判据必须成对才证明位移量真的进了算式**：
    ① 扩张后的产物**不**告知 `row_shift` ⇒ 用旧区间求值 ⇒ 照样通过（`test_extension_alone_is_not_enough_without_the_shift_aware_region`）
    ② 未扩张 + 告知 `row_shift` ⇒ 必须报「合计漏算」
    只有 ② 时，一个忽略 `row_shift` 的实现会让 ② 变绿

### Wave 4：计划接线与残余分支

- [x] 16. `plan_managed_writes` 接线位移计划 (M2)
  - 新增步骤 6.2：由 orphan 身份数算 `RowShiftPlan`（`insert_at` = 最后一个既有数据行 +1，`count` = orphan 数，`style_from` = 最后一个既有数据行）
  - 6.2 **必须**排在 footer 两门之前：两门要用位移后区间求值
  - 6.3 按 `count` 重构受管区域，footer 与合计判据一律用新区间
  - 插入行数 == orphan 数，两者不等即拒绝
  - `MaterializePlan` 新增 `row_shift` 字段并进 `as_dict()`
  - 验证 Property 5
  - _Requirements: 2.1, 2.4, 2.6, 2.7_
  - **生产代码已交付**（2026-09-04）：`excel_row_shift` 至此不再是死代码 —— `excel_extract`
    与 `excel_materialize` 两处真实消费。辐射面 **1371 passed / 0 failed**
  - **三组测试已补齐**（T4 = `backend/tests/workpaper_sync/test_excel_row_insertion_wiring.py`，
    27 例）：① Property 5（插入行数恰等于 orphan 数，参数化 1/2/3/5）② 六类拒绝理由**收集
    实际诊断码后双向等值 + 断言基数**（不是每类各测一遍 —— 后者在两类被合并成同一个码时
    全部仍绿）③ 成功路径端到端（插行执行 → Table ref 增长 → 合计扩张 → openpyxl 可打开 →
    `structure_fingerprint` 零 errors → 反读时新行带着自己的 identity 回来且 `minted_by_row` 为空）
  - 🔴 **补了第七条实现缺口：新插入行的 row identity 没人写进隐藏 UUID 列。**
    不写的后果不是「少一列数据」而是**身份丢失** —— 反读时那几行 UUID 列为空，
    `_scan_row_identities` 按 `delete_policy=tombstone` 给它**重新 mint 一个新 ID**，
    症状是「反读不等值」而真因是「插行时没写身份」，两者相距很远
  - 🔴 **成功路径只能用契约变体演示**（`insertable_contract_payload()`）：去掉 `k11_footer`
    静态表（其 `tb_amount` 在 `B27` ⇒ 第五类拒绝）+ 声明 `carries_total_formula`
    （解除第六类拒绝）。这不是为了让测试变绿而放宽 —— 它刻画的正是「什么样的契约形态
    才允许插行」，也就是 Task 19 清册要量化的东西
  - 🔴 **实施中纠正的接线错误（H1 实测当场打红）**：首版把 `row_shift` 传给了**计划期**的
    footer 两门，而计划期跑在 **substrate（尚未位移）**上 —— 于是判据期待位移后的行号，
    而 substrate 上 marker 当然还在冻结行。正解是**分两相**：
    - 计划期（substrate，位移前）→ 判「实测 == 冻结」「合计覆盖当前区间」
    - apply 后（staged，位移后）→ 判「实测 == 冻结 + 声明位移」「合计覆盖位移后区间」，
      落在新增的 `assert_shifted_footer_gates()`，调用点在 `os.replace` **之前**（Property 9：判据不过即零产物）
    ⇒ design.md 的「6.2 必须排在 footer 两门之前」这条**只对 apply 后那一相成立**；
    计划期的两门不用位移后区间。6.2 仍需早于字段写入（orphan→行号映射要先建立）
  - 🔴 **第五类拒绝理由（design.md 未覆盖，实测发现）**：契约声明的**静态行**落在插入点及
    其之下 ⇒ `contract_static_row_below_insertion`。插行把那些格整体推下去，而 Task 37 的
    extract 仍按契约 `cell.static_row` 反读固定行号 ⇒ 在旧行号上读到一个**新插入的空行**
    （静默取空值）。**实测 K11 契约的 `k11_footer/tb_amount` 在 `B27`、插入点是 26
    ⇒ K11 在读侧跟随落地之前不可安全插行**。解除条件 = extract 侧静态行定位也变成位移感知
  - 🔴 **第六类拒绝理由**：插行会让 footer 合计漏算，而契约没声明 `carries_total_formula`
    ⇒ `contract_total_formula_not_extendable`。判据形态是「拿位移后区间预演一次」：
    substrate 上覆盖不到位移后末行且契约未授权扩张 ⇒ 照插会产出一张**合计漏算**的审计底稿。
    契约声明了扩张时该报错是预期的（扩张在 apply 阶段发生），吞掉并交 apply 后那一相复核
    —— 不吞的话「声明扩张」这条路径永远走不通。**实测 H1 命中此条**（`SUM(I13:I27)` 不会扩张）
  - 🔴 **每条拒绝消息都必须带 orphan 身份清单**（AC 8.2「在消息中给出具体拒绝原因」）：
    拒绝的起因是「这几个身份没有物理行」。首版漏了，`test_task42` 的既有守卫（按身份名
    匹配消息）当场打红

- [x] 17. 保留并强化残余 `RowSetDivergenceError` 分支 (M2)
  - `RowSetDivergenceError` 与其 `error_code` 保留在 `FAILURE_KINDS`
  - 四类不可安全执行情形各自可达、两两可分辨：清单外位移敏感元素、样式来源行缺失、共享公式组跨度不一致、插入点越界
  - 实测确认既有变异锚点指向的守卫仍可被打红（**不看退出码**，比对失败测试名差集）
  - 更新模块 docstring 第四节第 1 条：从"不做结构性插行"改成"插行需显式计划 + shift-aware 验证；算不出安全计划仍 fail closed"
  - 验证 Property 23、Property 24
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - **实际是六类**（design.md 声明四类，实施中实测补两类）：清单外位移敏感元素 /
    样式来源行缺失 / 共享公式组横向不可 fill-down / 插入点越界 /
    **契约静态行落在插入点及其之下** / **合计公式不会扩张而契约未授权**。
    另有两条载体级：`excel_row_shift_table_part_missing` / `excel_row_shift_table_ref_not_grown` /
    `excel_row_shift_strategy_conflict`（与 openpyxl 全量重写叠加）
  - 🔴 **判据形态是「收集全部实际抛出的诊断码，与声明集合双向等值 + 断言基数」**，
    不是「每类各测一遍」：后者在两类被合并成同一个码时**全部仍绿**（本仓库已实测踩过三次）
  - 🔴 **每条拒绝消息都必须带 orphan 身份清单**（AC 8.2）—— 拒绝的起因是「这几个身份没有
    物理行」。首版漏了，`test_task42` 的既有守卫（按身份名匹配消息）当场打红
  - `RowSetDivergenceError` 与其 `error_code` 仍在 `FAILURE_KINDS`（AC 8.1，有判据断言）

- [x] 18. `apply_plan_zip` 接线位移阶段 (M2)
  - 位移阶段排**最先**：`shift_sheet_rows` → 合计扩张 → `_patch_sheet_xml`
  - 位移必须在任何 `_cell_view` 求值之前完成（`plan_managed_writes` 里算坐标用的是位移后行号）
  - 位移计划为空时代码路径与本 spec 之前逐字节相同
  - `ShiftReport` 进 `ExcelMaterializeOutcome.as_dict()`
  - 验证 Property 3
  - _Requirements: 2.3, 3.2_
  - **生产代码已交付**：`apply_plan_zip` 保持 `-> bytes` 签名（既有调用点与守卫逐字不变），
    新增 `apply_plan_zip_with_report() -> tuple[bytes, ShiftReport | None]` 作为完整形态，
    前者委派给后者。`ShiftReport` 经 `ExcelMaterializeOutcome.shift_report` 进 `as_dict()`
  - 🔴 **实施中补的一条必要动作（design.md 未覆盖）**：位移后必须把受管 **Excel Table 的
    `ref` 行区间**一起长上去（`_grow_managed_table_ref`）。不长的话新行落在 Table 之外，
    反读时 `resolve_managed_region` 仍返回旧区间 ⇒ **新行根本不进 projection，静默丢数据**。
    这不是未管理区域漂移：`_classify_parts` 把 `xl/tables/**` 整类排除，
    `assert_identity_inventory_retained` 也明确「行区间随插删行变化属合法」
  - 🔴 **Table part 名不得假设成 `tableN.xml`**：H1 的注入产物实测叫 `tableGtRowId.xml`。
    首版按 `table\d+\.xml` 匹配，于是在 H1 上定位不到、把「Table 名对不上」误报成「part 缺失」
  - 🔴 **openpyxl 全量重写与结构性插行不得叠加**：策略选中 openpyxl 且本次要插行时
    fail closed（`excel_row_shift_strategy_conflict`）。openpyxl 实测在 K11 上丢 18 个 zip
    部件、摊平 12 个共享公式组 —— 与位移混用会让「位移正确」与「重写毁坏」互相掩盖
  - 🔴 **Table ref 的增长条件首版写反了**：`A7:N25` 的末行恰是 `insert_at - 1`
    （追加插行的形态 = `insert_at` 恒等于最后一个数据行 +1），首版写成「末行在插入点之上
    就不动」⇒ **每一次真实插行都撞「ref 一处都没长」**。正解：`tail_row >= insert_at - 1`
    时 `+count` —— 「被推下去」（`>= insert_at`）与「追加插行要长上去」（`== insert_at - 1`）
    是同一个算式
  - 🔴 **计划期的逐字段判据必须对着位移后的 XML 求值**：`formula` 模式要求该格已有公式，
    而新插入行在 substrate 上**不存在** ⇒ 拿 substrate 求 `_cell_view` 会报「H27 没有公式」，
    那是**问错了 artifact**，不是契约漂移。干跑位移的产物一并返回给计划期用（不浪费）
  - **Property 3 已落判据**：同一个零位移计划下 `apply_plan_zip` 与
    `apply_plan_zip_with_report` 产出逐字节相同的字节、报告为 `None`、Table part 零字节改动

### Wave 5：全量清册 / 变异 / 真实环境

- [x] 19. 建全量底稿可插行清册 (N2)
  - 逐 entry 现算：HTML store 行数 / 模板骨架行数 / 是否需要插行 / 插行是否可安全执行
  - 封闭结算词表：`no_insertion_needed` / `insertion_safe` / `blocked_unlisted_structure` / `blocked_style_source_missing` / `blocked_shared_formula` / `blocked_out_of_range` / `blocked_no_contract`
  - 由真实库与真实模板现算，**不得手填**；`--json` 落盘（脚本内 `Path.write_text(encoding="utf-8")`，不用 PowerShell 重定向）
  - 必须覆盖 D2（729 行，真实超出骨架）与一个零增长 entry（回归对照）
  - 不可插行的 entry 各给判据编号与解除条件
  - 实测 D2 的 729 行 × 39 列是否撞 `SyncLimits` 预算（design.md §Open Gates 第 3 项）
  - 验证 Property 27、Property 28
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  - 交付 `backend/scripts/check/check_excel_row_insertion_readiness.py` + T3（21 例）
  - 🔴 **词表实际是 9 格**（design.md 声明 7 格）：补了实施中实测发现的
    `blocked_static_row_below_insertion` / `blocked_total_formula_not_extendable`。
    少这两格，清册会把「引擎明确拒绝」错报成 `insertion_safe` —— **会让人以为可以上线**的假绿
  - **4 个已发布契约的实测结论**：`b60` / `g7` = `insertion_safe`，
    `d2` / `h1` = `blocked_total_formula_not_extendable`（合计区间不会扩张而契约未授权）
  - 🔴 **实施中捞出一处本脚本自己的假绿**：首版手写了第二份 marker 定位（三载体
    sharedString/inlineStr/str），结果在 H1 / B60 / G7 上**一个都找不到** —— 那三份模板
    既无 `sharedStrings.xml`，中文又以**数字字符引用**（`&#21512;&#35745;`）存在 inline `<t>` 里，
    而生产侧早有 `_decode_numeric_char_refs`。找不到之后清册走进「无 footer ⇒ 无合计漏算
    问题」那一支，把 3 个 entry 全报成 `insertion_safe`。
    ⇒ 改为直接调生产的 `M._find_marker_row`，并对「契约声明了 footer 却定位不到」**fail closed**。
    T3 里 `test_marker_location_reuses_the_production_finder` 按**函数身份**钉住这一点
  - 交叉验证：清册与 `excel_materialize` 两套独立实现在 H1 上给出同一结论
  - 未做：`--rows` 取真实库行数（结构性结论不依赖库，已可离线复现）；
    D2 的 729×39 是否撞 `SyncLimits` 预算仍是 Open Gate

- [~] 20. 建变异脚本并收敛为全 RED (N3) —— **清单已交付 E，文件归 E**
  - 六条变异各带 `id` / `path` / `anchor` / `new` / `want`（预期打红的**具体测试**）/ `why`（所守的假绿形态）：
    1. 删掉 `apply_plan_zip` 里的位移阶段调用 → 守"插行未执行却假装成功"
    2. 把 `unshift` 改成恒等 → 守"归一化没生效 ⇒ 插行必判漂移"
    3. 把 footer anchor 判据的 `+ count` 去掉 → 守"位移感知失效"
    4. 从位移函数里删掉 `mergeCell@ref` 处理 → 守"清单项漏处理"
    5. 删掉残余 `RowSetDivergenceError` 分支 → 守"不安全的插行被静默放行"
    6. 把新插入行样式继承改成 `style=""` → 守"新行无样式"
  - 四态判读 RED / GREEN / ANCHOR-MISS / WRONG-TEST，**不以退出码代替判读**；WRONG-TEST 比对失败测试名差集
  - 锚点命中次数必须恰为 1；锚点不含 `\n`（CRLF 下跨行锚点必 MISS）；CRLF 归一后再匹配；还原后 sha256 自证
  - 提供 `--check-anchors` 只读入口
  - 测试调用走 `subprocess.run([...])` **不经 shell**；加"passed < N 即中止"自检
  - 验证 Property 30
  - _Requirements: 11.1, 11.2, 11.3_
  - 🔴 **归属冲突，按分工书 §2 执行**：§2 把 `backend/scripts/diagnose/mutate_*.py` 判给 **E**
    （判据治理），B 行的文件面只有五个生产文件。本条把 N3 写成 B 的产物与 §2 冲突。
    ⇒ **B 提供清单与预期态，E 写文件并统一四态判读标准。**
    交接件：`docs/operations/excel-row-insertion-mutation-handoff.md`
  - **清单已实测验证：28 条全 RED**（不是六条 —— 实施中随交付面增长到 28），
    四个被变异文件还原后 sha256 自证一致。基线 `137 passed`，`passed < 137` 即中止
  - 🔴 **两条四态判读的实测教训（已写进交接件）**：
    ① **`errors` 必须计入「红」**：变异写出语法错误/导入失败时 pytest 报 `N error` 而非
       `N failed`，只数 `failed` 会把「模块根本没跑起来」判成 GREEN（M28 首轮实测误判）
    ② **mutation 本身必须语法合法**：否则打红的原因是「语法错」而不是「守卫抓到行为变化」，
       WRONG-TEST 与 RED 就分不开
  - 🔴 **变异检验捞出一处真缺陷（M28）**：它首轮 GREEN，暴露出「T4 只调
    `apply_plan_zip_with_report`，从未走完整 `materialize_projection`」⇒
    `assert_shifted_footer_gates` 的调用点**一次都没被执行**，两个新参数在生产链路上是
    零消费的死参数（= 假绿第①源）。补 `TestMaterializeProjectionRunsTheWholeChain` 后转 RED
  - ⚠ 遗留给 E：`--check-anchors` 独立子命令；M15/M28 的锚点含 `\n`（B 用 CRLF 归一后匹配
    解决，E 若坚持无 `\n` 锚点需改「单行锚点 + 命中次数断言」两段式）

- [x] 21. 插行产物的真实可打开性验证 (T1)
  - 插行产物通过 `validate_ooxml_artifact` 与 `structure_fingerprint`（`errors` 必须为空）
  - 能被 openpyxl 加载，受管区域行数等于预期
  - 真实 Excel / OnlyOffice 9.4 打开验证；环境不可得则标 UNVERIFIABLE 并保持未验收，**不得用 fixture 冒充**
  - 验证 Property 29
  - _Requirements: 11.4, 11.5, 11.8_
  - 交付 `backend/tests/workpaper_sync/test_excel_row_insertion_openability.py`（12 例，三层判据）
  - ✅ **第三层是真实验证，不是 UNVERIFIABLE**：容器 `audit-onlyoffice` 实测
    `onlyoffice-documentserver 9.4.0-129`，文档引擎 `x2t` 版本 `9.4.0.129`
    （`FileConverter/bin/x2t` —— 编辑器打开 xlsx 时走的就是它）
  - 🔴 **实测出 `x2t` 退出码的能力边界，并把它钉成判据**（不是写在注释里）：

    | 损坏形态 | rc | 产物大小 |
    |---|---:|---:|
    | 原始模板（对照） | 0 | 130,367 |
    | 删掉整个 `sheet4.xml` | 0 | 123,384 |
    | sheet part 换成垃圾字节 | 0 | 123,384 |
    | `workbook.xml` 换成垃圾 | 0 | **1,299** |
    | 只砍 `</sheetData>` | 0 | 130,256 |
    | 删掉 `[Content_Types].xml` | **89** | 0 |
    | 根本不是 zip | **89** | 0 |

    ⇒ 退出码只对**容器级**损坏敏感；sheet 内容坏了它跳过那张表继续、仍报 0。
    **所以本层判据是「rc=0 **且** 产物大小 >= 对照的 80%」**（`workbook.xml` 坏时产物
    塌到 1.3 KB，正是量级判据抓住的形态）
  - 🔴 **反向自检首轮打红，捞出真问题**：我原本用「砍 `</sheetData>`」当反向用例，
    实测 x2t 对它返回 0 ⇒ 那条断言失败，暴露出「正面结论其实什么都没证明」。
    改用实测确认会被拒的两种容器级损坏（rc=89），并**另加一条判据把「sheet 级损坏被容忍」
    这个能力边界本身钉住** —— x2t 将来变严格时它会红，提示更新能力表并加强结论
  - **诚实表述**：本层证明「OnlyOffice 9.4 引擎能把产物当成完整工作簿解析出来」，
    **不是**「编辑器里所见即所愿」—— 后者需人工在真实编辑器里看，本层不冒充它

- [x] 22. 收口：范围边界与产物入库
  - 结构缺席判据：无结构性删行实现、无外部关系许可放宽、无 H1 契约改动、无跨 sheet 联动改写、`openpyxl_roundtrip` 可达性判据不变、无新增 `backend/migrations/V*.sql`
  - 断言已发布 definition 与 bundle 未被原地改写；契约 canonical payload 若有变更，须走
    `template → instrumentation → contract → bundle → representation` 发布链（AC 5.5）
  - **测试纪律判据（此前无任何任务引用，是悬空 AC）**：
    - 现读本 spec 全部属性测试文件，断言每条 `@settings` 的 `max_examples >= 100`（AC 11.6）；
      判据落在 AST 取值而非字符串存在 —— 改成 50 必须打红
    - 断言测试是从**仓库根**跑 pytest，且辐射面由「对本 spec 交付物的实际引用关系」现算得出
      （不是写死目录、不是全量 `backend/tests`）（AC 11.7）；现算辐射面与 CI 声明的文件清单逐项相等
  - 逐产物 `git status --porcelain -- <path>`，见 `??` 即 `git add`（"spec 全绿 ≠ 产物已入库"）
  - 清理本次会话的 `tmp_*` / `_wip_*` 诊断产物（按 mtime 判归属，并发会话在用的不动）
  - 验证 Property 26、Property 31
  - _Requirements: 5.5, 9.4, 11.6, 11.7, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_
  - 交付 `backend/tests/workpaper_sync/test_excel_row_insertion_scope_closure.py`（24 例 + 1 诚实 skip）
  - 🔴 **结构缺席判据全部按「归因」判，不用全局等值型**：仓库当前多泳道并行（git 索引里
    同时有 B 与 D 两条泳道的产物，D 还落了 `V154` 迁移）。全局判据（「一个新迁移都没有」）
    会被 D 的 `V154` 打成假红。⇒ 判据形态统一为「**在本 spec 声明的五个交付文件里**，
    某类东西必须缺席」
  - 🔴 **本文件自己被自己的判据打红两次，两次都是子串型判据的锅**：
    ① `externalLink` —— 生产侧本来就有只读的部件分类表
       （`"external_link": re.compile(r"^xl/externalLinks/")`），那是**识别**外部链接用的，
       与「放宽许可」正好相反。改判**放宽动作**本身（允许类开关 / 跳过检查 / 写入该目录）
    ② `os.getcwd()` —— 本条自己的 docstring 里写着这几个字（用来说明什么形态不行）。
       改判 **AST**：注释与文档字符串不是代码，判据必须能区分
    ⇒ 同一教训两次：**判据要落在语义（AST / 行为）上，不落在字符出现**
  - AC 11.6（`max_examples >= 100`）在本 spec 上**无载体** ⇒ 诚实 skip 而非假绿：
    本 spec 的属性测试形态是「实测 fixture + 参数化」，不用 hypothesis。
    判据仍在把关 —— 一旦有人引入 `@settings`，它自动开始生效
  - AC 11.7 辐射面**现算**：按「哪些测试文件引用了本 spec 的交付模块」算，并断言
    `现算辐射面 < 全量`（否则「现算」等于「跑全部」，该 AC 落空）

## Notes

### 🔴 下游 spec 的共改文件（本 spec Wave 4 收口前不得并行开工）

`excel-workbook-wide-row-change-propagation`（工作簿级行变更传播）会改本 spec 的三个交付文件：

| 文件 | 本 spec | 下游 spec |
|---|---|---|
| `excel_row_shift.py` | N1 新建（位移纯函数 + 清单 + si 索引） | 改 `_rewrite_formula_refs` 加 `propagate_sheets` |
| `excel_materialize.py` | Task 16 改 `plan_managed_writes` | Task 21 再改 `plan_managed_writes` 接工作簿级计划 |
| `excel_extract.py` | Task 9 / 10 加 `row_shift` 归一化 | Task 19 改为按**声明传播量**归一化 |

关系是「后者建立在前者之上」—— 工作簿级计划把本 spec 的单 sheet 位移作为其受管 sheet 分量。
下游 spec 的 Task 101 会现读本 spec 的 tasks.md，断言 Wave 4（Task 16 / 17 / 18）均为 `[x]`
才允许其 Wave 2 起开工。**本 spec Wave 4 完成时应同步通知下游方**，避免两边并行改同一文件
互相回退（这在本仓库是已发生过的事故形态，不是理论风险）。

另：本 spec R12.1（结构性删行）与 R12.4（跨 sheet 联动改写）两条排除项已由该下游 spec 承接，
不再是无人负责的缺口。

### 判据与纪律

- 标 `*` 的子任务为测试任务，可为快速 MVP 跳过；顶层任务不标 `*`。
- 每条属性测试用 `hypothesis`，`max_examples` ≥100，并以 `**Feature: excel-structural-row-insertion-and-shift-aware-verification, Property N: <标题>**` 标签回指 design.md。
- **每写完一条守卫必做变异检验**（改一字看是否变红）。没打红 = 守卫有缺陷，不是代码没问题。
- 判据一律落在行为 / 结构 / 真实执行，**不得**落在"字符串是否存在"。
- 判磁盘一律 `python -c "open(p,encoding='utf-8').read()"`（读文件工具对刚改的文件可能返回陈旧版本）。
- PowerShell 管道会把中文腌成乱码 ⇒ 用 `Out-File -Encoding utf8` 再 `Get-Content -Encoding utf8` 读回。
- 改共享文件前 grep 其他 active spec 是否也在改它（并发会话会互相回退）。
- design.md §Open Gates 的三项在实施中确认：`_SHEET_STRUCTURE_BLOCKS` 扩充影响面（Task 1）、K11 是否含四类结构（Task 1）、D2 的 729 行是否撞预算（Task 19）。任一不成立即按该节应对调整，**不绕开**。

---

## 🔴 A 提请 B 承接：BP-21 受管区末行的「……」排版占位行（2026-09-04）

> 提请方 = A（L1 首版发布泳道）。**本节故意不带复选框**，以免改动你的任务分母与 waves JSON
> —— 请你自行决定编号并并入合适的 Wave（建议 Wave 1，它是纯派生规则、不依赖位移逻辑）。
> 用 `fs_append` 追加而非改写全文，避免与你在途编辑互相覆盖。
>
> **自包含交接件**：`docs/operations/bp-21-managed-region-typography-row-handoff.md`
> 分工书上下文：`docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md` §11.3

### 为什么找你

改动点在 `backend/app/services/workpaper_sync/excel_extract.py` 的
`resolve_managed_region` —— 你的独占文件，A 不动它（协作规则 1）。

### 一句话

受管区行范围是**派生**的（`anchor` + `header_rows` → 首行，footer 锚点「合计」→ 末行）。
派生规则「表头与合计之间都是数据行」把中文审计模板的**续行省略号行**一并吞进受管区，于是
首版发布试图把 `……` 当业务数据写回 `integer` 字段：

```
EditableCellWriteError
  受管格 A27（disposal_check_rows/{row_uuid}/seq）的值 '……' 无法按 integer 规范化
```

### 它挡着两个 entry，不只 H1

| entry | 受管区（现读你的 `resolve_managed_region`） | 区内占位行 |
|---|---|---|
H1 | `A13..27`（15 行，`table_ref=A13:AB27`） | 🔴 **A27** |
D2 | `A13..25`（13 行，`table_ref=A13:AN25`） | 🔴 **A25** |
G7 | `A79..83`（5 行） | ✅ 干净 —— 所以只有它发出去了 |
B60 | — | ⊘ `unverifiable_ooxml_gate` |

**D2 那一行请注意**：你 Wave 4 接完插行后，D2 会撞上同一处。

### 为什么是平台级规则而不是逐契约排除

全模板库实测（349 份 xlsx / 2602 张 sheet，0 失败，1.4 秒）：
「`……` 行紧跟合计/小计/总计行」**170 处 / 37 份模板 / 35 个 wp_code**；纯省略号格 **842** 个。
逐契约写 `excluded_rows` 等于要写 170 条声明、每份新契约都得记得写 —— 必然遗漏。

契约体系对 `……` 的**列**方向已有先例：`h1.disposal_check` 的 `review.excluded_columns`
排除了 X 列（理由「模板的扩展占位列（表头文本恰为 `……`），没有业务语义」）。
缺的只是**行**方向的对应物 —— 4 份 pilot 契约里声明了行级排除的是 **0/4**。

### 请做的改动

`resolve_managed_region` 派生 `last_row` 时，从末行往上剔除「该行在受管区**首列**上的取值是
纯排版省略号」的行。口径：含至少一个 U+2026，且除 `U+2026` / `.` / `。` / 空格外无其它字符。

预期：H1 `13..27` → `13..26`；D2 `13..25` → `13..24`；G7 `79..83` 不变。

### 🔴 两件要你裁决（A 无法代判）

1. **收缩 `last_row` 后 `table_ref` 与 `row_uuids` 仍覆盖旧区间**。实测 H1
   `table_ref=A13:AB27`、`identity_inventory.row_uuids` 含 13..27 共 **15** 项。收缩 region
   而不动这两处会不会触发既有 identity 断言（`assert_identity_inventory_usable` /
   `IdentityRetentionError` / `RowIdentityWriteError`）？三条候选处置见交接件 §4。
2. **与你的位移计划相容性**：Task 16 算 `RowShiftPlan` 时 `insert_at` 取「最后一个既有数据行
   +1」。区间末行从 27 变 26 后，新行会插在 `……` 行**之前** —— 这正是业务上想要的（续行占位符
   应留在数据行之后）。请确认 Task 16 用的是**收缩后**的区间。

### 验收判据（已入库，别重造）

```
python backend/scripts/check/check_managed_region_typography_rows.py --expect-managed-region-hits 0
```

* 判据落在 **§B 逐 pilot 受管区扫描**，它现读你的 `resolve_managed_region` **真实返回值**
  （不是照 anchor/header_rows 再推一份副本 —— 副本会让「修了也不变绿」）。
* 🔴 **不要**用 §A 的全库清册数（170）当验收：那个数恒定不变，模板里的 `……` 行还在，
  变的只是它是否落进受管区。首版脚本写的就是这个错，已更正。
* 落地前基线：退出码 **1**，区内占位行 **2 行**，实扫分母 3 个（B60 因 OOXML 门剔除且剔除数
  已写出）。落地后应为退出码 **0**。
* 零数据库、1.4 秒、可挂 CI。

**还要一条反向自检**：把你的剔除条件短路（`if False and …`），断言 §B 重新打红且打红的正是
H1 与 D2 那两条。没打红 = 守卫有缺陷，不是代码没问题。

### A 已做完、你不必重做

裁决与全库取证 · 验收判据脚本 · 首版链上另外四处缺陷（已用 G7 验证：`projection_contract`
lane 首版 representation 已落库，10/10 全链、幂等已验）。**H1 现在只剩 BP-21 这一处**，
它一变绿 H1 的首版就能发。

若你判定不宜在本 spec 内承接，回复即可 —— 退路是 A 在 P spec 加契约裁决任务走
`template → instrumentation → contract → bundle → representation` 完整发布链（重，且 H1
bundle 现为 approved）。

### 🔴🔴 时序告警：Task 16 若先于 BP-21 落地，`RowShiftPlan` 会算错（A 追加于 2026-09-04 18:45）

看到你正在写 Task 16（`excel_materialize.py` 18:41 仍在增长）。**这一条会直接影响你现在写的
那段代码**，所以单列出来。

Task 16 的算法是「`insert_at` = 最后一个既有数据行 +1，`style_from` = 最后一个既有数据行」。
在受管区**未收缩**的现状下，「最后一个既有数据行」恰恰是那个 `……` 排版占位行：

| entry | 受管区（现读你的 `resolve_managed_region`） | 末行内容 | 于是算出 |
|---|---|---|---|
H1 | `A13..27` | **A27 = `……`** | `style_from=27`（**从省略号行抄样式**）、`insert_at=28`（**= 合计行**） |
D2 | `A13..25` | **A25 = `……`** | `style_from=25`、`insert_at=26`（**= 合计行**） |

两处后果都错，且都不会报错：

1. **新插入行的样式继承自排版占位行**。你 Task 6 的阶段 B 是「每列 `s=` 取自 `style_from`
   行同列」；`……` 行的样式（H1 实测 `s="110"`）是给占位符用的，不是数据行样式。
   Property 8「新插入行样式与来源行同列相等」会**通过** —— 因为它比的就是 `style_from` 行，
   而 `style_from` 本身选错了。判据在这里帮不了你。
2. **新行插在「……」之后**，也就是在「以下省略」之后又接了一堆数据行 —— 业务上讲不通。
   正确位置是插在最后一条真实数据行之后、`……` 之前。

⇒ **建议顺序：BP-21 的区间收缩先落，Task 16 再基于收缩后的区间算计划。** 收缩后 H1 得
`style_from=26`（A26=14，真实数据行）、`insert_at=27`（`……` 行原位，新行插在它前面）；
D2 得 `style_from=24` / `insert_at=25`。

如果你已经把 Task 16 写完了，也不必回退 —— 只要 BP-21 落地后 `resolve_managed_region` 返回
收缩后的区间，Task 16 的算法**自动**取到对的行（它读的是 region，不是写死的行号）。
需要确认的只有一条：**Task 16 里的「最后一个既有数据行」是从 `region.last_row` 派生的，
不是从 `table_ref` 或 `identity_inventory.row_uuids` 派生的** —— 后两者仍覆盖旧区间
（H1 `table_ref=A13:AB27` / `row_uuids` 含 15 项），从它们派生会绕过 BP-21 的收缩。

顺带一条可加的判据（比「样式相等」强）：断言 `style_from` 行在受管区首列上的取值**不是**
纯排版省略号。这条现在应打红（H1/D2 各一处），BP-21 落地后转绿 —— 与
`check_managed_region_typography_rows.py --expect-managed-region-hits 0` 同源。
