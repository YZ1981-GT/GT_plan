# Implementation Plan: 国企↔上市附注转换正确性收口

## Overview

5 波 / 19 任务。把转换从「只改 `template_type` + 全链重算」修到「章节映射真正落地 + 结果如实上报 + 可预览可回滚」。

**进度 19/19（全部完成）**（2026-08-08）：5 波全交付。收口状态 —— 全 spec 守卫 **511 passed / 0 failed / 0 error**（10 个文件，从仓库根跑；上一轮基线 480 passed / 9 文件 ⇒ 本轮 +1 文件 +31 例、新增失败 0）· **11 条变异全部 RED**（M11 的阻塞随 Task 19 交付验收脚本而解除，已补做并判 RED）· CI job `note-conversion-correctness` 已挂（jobs 137，14 步，带 postgres service + 迁移步骤）· **真实库验收诚实输出 SKIP，待用户授权**（`eligibility = NO_CANDIDATE` + rc=1；4 个技术上可切换的候选与建议对象见 Notes「Wave 5 真实库验收实录」）· **生产代码零净改动**（5 个文件收尾 md5 与开工基线逐字相同）。

**开工前必读**：

- 转换是**自动触发**的（`STANDARD_CHANGED` 事件 → `_on_standard_changed_notes`），不是只有手工入口 ⇒ 改动一旦有 bug 会在准则切换时静默生效，所有写入必须有快照与 `failed` 桶。
- **禁止引入相似度/模糊匹配**。实证「财务报表主要项目注释」↔「母公司财务报表主要项目注释」相似度 **0.87**，任何阈值都无法既救回 5 对措辞差异又拦住这一对 ⇒ 只能穷举配对 + 禁止对清单。
- 判据真源是 `docs/模版/` 两份源 docx（docx 章号是 Word 自动编号，定位章节必须按 `Heading 1` 样式，用章号正则会 0 命中）。
- 本 spec **无 DB 迁移**，改动全落在 `disclosure_notes` 既有列。
- **不改**合并章节与母公司章节结构（前者是零回归约束，后者属 `parent-company-note-chapter-and-sourcing`）。
- **🔴 列名（2026-08-07 实证 39 列，立项三处写错，本文件已全量改正）**：`disclosure_notes` **无 `section_number`**（章节号是 **`note_section`**）、**无 `legacy_aliases`**（源侧 sid 落 `template_lineage.legacy_section_ids`）、`status` 枚举**无 `archived`**（只有 `draft`/`confirmed`，归档靠 `is_deleted`）。按初稿字面写会 `column does not exist`。
- **🔴 Property 编号已于 2026-08-07 全量重映射**：原 tasks 与 design 的 Testing Strategy 表**整体错位**（Task 5 引 P18~21 而 matcher 实为 P20~23、Task 13 引 P25~27 而实为 P27~29、Task 18 引 P32 而实为 P34…），照旧编号写守卫会覆盖错的 Property。design 现有 **37 条** Property（新增 P35 binding_id / P36 sid NULL / P37 验收不改真实项目口径）。
- **🔴 `section_id` 大面积为 NULL**（抽样 12 条里 8 条），`table_data` 内 **446/1030 条带 `binding_id`** 且形态内嵌章节号 ⇒ Task 8 必须一并处置（需求 2.7 / 2.8）。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "差异数据可信化", "tasks": ["1", "2", "3"], "depends_on": [] },
    { "wave": 2, "name": "匹配器与 row_code 清单", "tasks": ["4", "5", "6", "7"], "depends_on": [] },
    { "wave": 3, "name": "章节映射落地", "tasks": ["8", "9", "10", "11"], "depends_on": ["1", "4"] },
    { "wave": 4, "name": "矩阵与章号核查", "tasks": ["12", "13", "14"], "depends_on": ["1"] },
    { "wave": 5, "name": "预览回滚与收口", "tasks": ["15", "16", "17", "18", "19"], "depends_on": ["8", "9", "10", "11", "12", "13", "14", "5", "6", "7"] }
  ]
}
```

Wave 1 与 Wave 2 无依赖，可并行。Wave 3 是核心，依赖 Wave 1 的差异数据与 Wave 2 的匹配器。

## Tasks

- [x] 1. 重生成差异数据并去 mock
  - 跑 `backend/scripts/gen/generate_note_soe_listed_diff.py` 重生成 `note_soe_listed_diff.json`，`is_mock` 置 `false`
  - 记录重生成前后四个桶的条目数变化（预期 common 106→107 / listed_only 71→70 / format_diff 33→39）
  - 补 `format_diff_sections` 的定位键：消费方改读 `soe_section_id`/`listed_section_id`（按 `current_type` 取侧），或补 `section_id`；**二选一并在守卫钉死**
  - _Requirements: 1.1, 1.4_

- [x] 2. 落盘与实时不一致时以实时为准
  - 改造 `note_template_diff.load_diff_data()`：读落盘后与 `compute_diff_from_templates()` 比对四个桶的**条目集合**（不只是数量）
  - 不一致 → 记 WARNING（含差异摘要）并返回实时结果
  - `adapt_table_data()` 语义明确化：`field_mapping` 为 null 保持空操作；非空时必须真正改结构
  - _Requirements: 1.3, 1.5_

- [x] 3. 差异数据守卫
  - 新建 `backend/tests/test_note_template_diff_integrity.py`（Property 1~4）
  - 断言 `is_mock == false`；落盘与实时逐条相等（模板一改即打红）
  - 断言 `format_diff` 每条可被消费方定位（现状 `fd.get('section_id')` 恒 None 必须消除）
  - 反向自检：把 `is_mock` 改回 true 必红
  - _Requirements: 1.2, 1.4, 1.5_

- [x] 4. 章节匹配器（穷举配对，禁相似度）
  - 新建 `backend/app/services/note_section_matcher.py`
  - `AliasPair(soe_title, listed_title, evidence)` + `SECTION_TITLE_ALIASES`（5 对已实证，每条附源 docx 两侧标题原文）
  - `FORBIDDEN_MATCH_PAIRS` 必含「财务报表主要项目注释」↔「母公司财务报表主要项目注释」
  - `normalize_for_match()` **仅去空白**；虚词差异由 ALIASES 承载，不做泛化替换
  - `match_section()`：命中 FORBIDDEN → False；精确相等 → True；别名配对 → True；否则 False
  - **不提供相似度接口**
  - _Requirements: 5.1, 5.2, 5.3, 5.5_

- [x] 5. 匹配器守卫
  - 新建 `backend/tests/test_note_section_matcher.py`（**Property 20~23**，原写 18~21 是错位编号）
  - 源码级断言不含 `difflib`/`SequenceMatcher`/`ratio` 等相似度实现
  - 断言 5 对别名生效、禁止对返回 False、每条 `evidence` 非空
  - 反向自检：把禁止对加入 ALIASES 必红
  - _Requirements: 5.4_

- [x] 6. 跨变体 row_code 双清单（同义两码 + 一码两义）
  - 新建 `backend/app/services/note_conversion_row_codes.py`，含**两个**冻结常量：
    - `CROSS_VARIANT_ROW_CODE_MAP`：需求 3.1 的 **12 条**实证映射（soe→listed，反向由反转生成），每条附 `report_config` 对账依据（两侧 `row_name` 实测值）
    - `ONE_CODE_TWO_MEANINGS_FORBIDDEN`：**禁止改写**的 `BS-016` / `BS-058` / `BS-059`，每条附两准则下 `row_name` 实测值作理由
  - 新建生成脚本 `backend/scripts/diagnose/diagnose_cross_variant_row_codes.py`（只读）：按 `applicable_standard` 四值逐一比对 `(report_type, row_name)`，输出「同义两码」与「一码两义」两张表；人工确认后冻结进上述常量
  - **禁止**凭 `row_name` 相同即建立映射（立项初稿即因此写反方向，见 requirements 已裁决事项 4）
  - _Requirements: 3.1, 3.2, 3.6_

- [x] 7. 公式引用改写与 row_code 守卫（**已按实证走替代路径：保留返回 0 + 原因码 + 依据**）
  - `_update_formula_references` 已接 `rewrite_row_refs_in_formula`（清单内改写 / 清单外与禁止码不变），但**当前无可改写对象**（见下方实录），故返回 `(0, "no_mapping_needed")`
  - 改写前查 `ONE_CODE_TWO_MEANINGS_FORBIDDEN`，命中即跳过并记 WARNING（不得改写）
  - 若对账证明确实无需改写，则保留 `return 0` 但补实证依据到 docstring，**删除「For now」这类临时措辞**，并返回原因码
  - 新建 `backend/tests/test_note_conversion_row_codes.py`（**Property 11~15**，原写 11~13 漏了 P14 稳定码/互斥与 P15 免做依据）：
    - 正向：含 `ROW('IS-055')` 的公式 soe→listed 后变为 `ROW('IS-033')`
    - 不变：含清单外 `ROW('BS-002')` 的公式保持不变
    - 反向自检：把 `BS-013→BS-016`（或 `BS-053→BS-058` / `BS-043→BS-059`）任一条加入映射表必须打红
    - 互斥：两清单的键值集合无交集
  - _Requirements: 3.3, 3.4, 3.5, 3.7, 3.8, 4.4_

- [x] 8. 章节映射真正落地（核心）
  - 重写 `_map_disclosure_notes`：收编 v2 的映射逻辑，真实改写 `section_id` + **`note_section`**（**不是** `section_number`，该列不存在）
  - 共有章节按 `soe_section_id ↔ listed_section_id` 改写，源侧 sid 追加进 **`template_lineage.legacy_section_ids`**（`legacy_aliases` 列不存在；`template_lineage` 全库 0 条有值 = 等于全新字段）
  - **改写前检查目标 sid 是否已存在** → 已存在则进 `skipped` 并记原因（防重复行）
  - **`binding_id` 前缀处置（需求 2.7）**：`table_data` 内 446/1030 条绑定形态是「章节号.行标签.列键」，改 `note_section` 会让它们**静默失联**（公式取数变空而非报错）⇒ 同步改前缀 + 旧章节号记入 `template_lineage.legacy_note_sections`
  - **`section_id IS NULL` 的存量行（需求 2.8）**：按 `note_section` + `section_title` 回填后参与映射，回填不出则进 `skipped` 附原因码，**禁静默跳过**
  - 逐章节 `begin_nested()` savepoint，异常进 `failed` 并继续
  - 返回 `{mapped, archived, created, format_adapted, user_edits_preserved, skipped, failed}`
  - _Requirements: 2.1, 2.2, 2.6, 2.7, 2.8, 4.1, 4.2, 4.3_

- [x] 9. 归档与新建章节
  - 源独有章节：软删 + `template_lineage.archived_sections` 追加 `{section_id, archived_at, reason}`
  - 目标独有章节：创建 `is_empty=true` / `status='draft'` 的空章节
  - 共有章节的 `_cell_modes[i]=='manual'` 单元格必须保留，并计入 `user_edits_preserved`
  - _Requirements: 2.3, 2.4, 2.5_

- [x] 10. v2 处置（🔴 实测裁决 = **删除不接线**，已落地）
  - ~~把 `convert_disclosure_notes_v2` 的逻辑并入生产路径~~ → **不做**。Task 8/9 落地后生产路径 `_map_disclosure_notes` 已完整实现且严格强于 v2（别名桥接 / binding_id 前缀重写 / sid NULL 回填 / 章节号占用检查 / 逐章 savepoint，v2 五项全无）；接线只会造第二份真源
  - ~~修它自身 3 个缺陷~~ → **不做**。三缺陷（`format_diff` 定位键 / `field_mapping` 全 null 空转 / 共有章节未改写 `section_id`）在生产路径本就不存在，且已各有守卫钉死
  - **已删除** `convert_disclosure_notes_v2` + `preview_conversion_v2`（code-level hits=0，唯一残留是 docstring 里的删除留证）
  - **21 条测试断言已迁移**到新建 `backend/tests/services/test_note_conversion_section_mapping_production.py`（26 例），迁移对照表落 `ASSERTION_MIGRATION` 常量（机器可校验，双向锁死）
  - 守卫 `backend/tests/test_note_conversion_v2_removal.py`（Property 24/26）
  - 详见本文件 Notes 的「Task 10 实录」一节
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 11. 章节映射守卫
  - 新建 `backend/tests/test_note_conversion_section_mapping.py`（**Property 5~10、16~19、24~26、35、36**，原写「5~10、14~17、22~24」是错位编号 —— P14/P15 归 row_code、P20~23 归 matcher）
  - 含「`binding_id` 不失联」（P35）与「`section_id IS NULL` 有明确处置」（P36）断言
  - 含「零共有章节场景返回 mapped=0」断言（复现 `count(*)` 冒充必红）
  - 含「注入单章节写入异常，其余仍处理」断言
  - 含「无孤儿转换函数」结构性断言（每个 `convert_*`/`_map_*` 公开方法有非测试调用方）
  - _Requirements: 4.1, 4.2, 4.3, 6.4_

- [x] 12. variant_matrix 假 null 复核与补记
  - 逐条复核 listed 侧 25 个 null 与 soe 侧 10 个 null，判定「真无落点」还是「落点在别的章」
  - **实证结果 = FALSE_NULL 9 / CROSS_GRAIN 18 / TRUE_NULL 8**（立项写的「补记 8 个」清单有 3 处不成立，见 Notes）
  - 新建幂等脚本 `backend/scripts/fix/fix_variant_matrix_false_nulls.py`（`--dry-run`/`--apply`/`--check`），已 apply **9 科目 / 18 个 slot**，非 null 计数 338 → 356
  - 三道前置闸门（违反即 exit 2 不写盘）：**跨科目撞码** / **落点须为叶子节**（非章标题容器）/ **additive**（既有非 null 绝不覆盖）
  - 同步更新 A spec 的冻结基线 `test_variant_matrix.VARIANTS_BASELINE`（按其预留路径 `audit_variant_matrix_snapshot.py --diff-head` 留证）
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 13. variant_matrix 守卫扩展
  - 扩 `backend/tests/test_variant_matrix.py` + 新建 `test_variant_matrix_null_audit.py`（**Property 27~29**，原写 25~27 是错位编号）
  - 断言 8 个已补记科目非 null 且补记值在对应模板中存在
  - 断言既有非 null 取值快照不变；仍为 null 者理由非空
  - _Requirements: 7.3, 7.4_

- [x] 14. 章号映射错配核查
  - 逐条核查 `soe ch08 → listed ch03` 的 10 条、`soe ch12 → listed ch05` 的 2 条
  - 落成三态清单（正常映射 / 已修正 / 已登记豁免），每条附判定依据
  - 新建 `backend/tests/test_note_chapter_mapping_audit.py`（**Property 30**，原写 28 是错位编号），含「主映射分布不变」断言
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 15. 转换预览端点
  - 新增 `GET /note-conversion/{project_id}/{year}/preview?target_type=`
  - 复用同一映射函数，走 savepoint + 显式 rollback（保证与真实执行同路径，避免预览与实际不一致）
  - 返回 `{mapped, archived, created, user_edits_preserved, forbidden_hits, details}`
  - _Requirements: 9.1, 9.2_

- [x] 16. 回滚覆盖 section_id 改写
  - `rollback_conversion` 支持回退 `section_id`/**`note_section`** 改写、`binding_id` 前缀与归档状态
  - `STANDARD_CHANGED` 自动路径记录 snapshot_id 到日志
  - _Requirements: 9.3, 9.4_

- [x] 17. 预览回滚守卫
  - 新建 `backend/tests/test_note_conversion_preview_rollback.py`（**Property 31~33**，原写 29~31 是错位编号）
  - 断言预览后 DB 无变化；预览计数 == 随后真实执行的计数
  - 断言 soe→listed→rollback 往返后 `section_id`/`note_section`/`is_deleted`/`template_lineage`/`binding_id` 回到初始
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 18. 零回归与变异检验与 CI
  - **已完成**：零回归守卫 26 例全绿（修掉 4 条守卫自身缺陷 + 1 条 characterization 基线）· **11 条变异逐条 RED**（判据 = 失败测试名差集三态，md5 逐字节还原、零 `.t18bak` 残留）· CI job `note-conversion-correctness` 已追加（jobs 136→137，`yaml.safe_load` 可解析、无重名、**14 步**、10 个引用文件全存在）
  - **M11 曾因 Task 19 未交付而阻塞，Task 19 交付后已补做并判 RED**：`backend/scripts/diagnose/verify_note_conversion_live.py` 属 Task 19 交付物，前一轮该文件不存在 ⇒ 「验收脚本里写 `Project.template_type`」这条变异无锚点可打，故当时保持未完成（有意驻留，非被中断）。本轮 Task 19 交付该脚本后立即补做：施加前先做 dry-run 有效性自检（baseline `offenders=[]` vs 变异后 `offenders=['template_type :: 属性赋值']`），变异后 `new_fails=1`（`test_note_conversion_live_verifier::test_no_forbidden_write_forms`）⇒ **RED**，还原后 md5 与基线逐字节一致
  - 详见本文件 Notes 的「Wave 5 零回归与变异检验实录（2026-08-08，Task 18）」
  - characterization：不涉及转换的附注生成/同步/导出行为逐字节不变（**Property 34**，原写 32 是错位编号）
  - 逐条执行变异检验并记录（改一处必红 + 已还原）：`is_mock` 改回 true / 删 format_diff 定位键 / `_map_disclosure_notes` 改回 `count(*)` / 去掉 `template_lineage.legacy_section_ids` 追加 / 禁止对加入 ALIASES / matcher 引入 `difflib` / 清空 row_code 清单 / 让预览产生写入 / **改 `note_section` 而不改 `binding_id` 前缀（P35 必红）** / **对 `section_id IS NULL` 静默跳过（P36 必红）** / **验收脚本里写 `Project.template_type`（P37 必红）**
  - 变异检验判据用**失败测试名差集**三态（RED / GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷），还原按字节 + 哈希核验
  - `.github/workflows/governance-checks.yml` 新增 job `note-conversion-correctness`
  - _Requirements: 10.1, 10.2, 10.3_

- [x] 19. 真实库验收（诚实报告）
  - **达成状态 = 诚实输出「无法验收（缺用户授权）」，不是「验收通过」**。需求 10.7 明确允许「无合法验收对象 ⇒ 报告无法验收 + 非零退出码 + 显式 SKIP 标记」，脚本已按此输出 `eligibility = NO_CANDIDATE` + `[SKIP]` + **rc=1** ⇒ 这就是该任务的达成状态，不是未完成
  - **真实往返未执行，待用户授权**。脚本已建 `backend/scripts/diagnose/verify_note_conversion_live.py`（约 34 KB，默认 dry-run，`--apply` 全程 `try/finally` + finally 无条件复原 + 独立复查），复用生产路径 `preview_note_conversion` / `_create_snapshot` / `rollback_conversion` / `_map_disclosure_notes` 四项存在性检查均 `[OK]`
  - **4 个技术上可切换的候选项目 id 与建议对象已列出**（见 Notes「Wave 5 真实库验收实录」）：`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` / `2aa00f57-1df4-4fe8-9840-2d65d0fd8749` / `c8621493-70aa-46a9-8285-e0674e4e1418` / `a7fc75e5-b67f-436d-a126-42423018b6ce`；建议授权对象 `c8621493`（附注 162 章节，规模最小 ⇒ 全链重算影响面最小）
  - 新建 Property 37 守卫 `backend/tests/test_note_conversion_live_verifier.py`（**31 passed / 0 failed**）
  - **禁用 fixture／新建测试项目冒充**（需求 10.7）—— 已核实脚本无该类构造
  - **源码级自禁（需求 10.6，Property 37）**：脚本不得出现对 `Project.template_type` / `report_scope` / `applicable_standard_v2` 的写入 —— 转换会触发 `execute_full_chain(force=True)` 全链重算，属破坏性操作
  - 若需真实验收，须用户显式授权专用测试项目，授权（项目 id + 时间）记入本文件 Notes（需求 10.8）
  - _Requirements: 10.4, 10.5, 10.6, 10.7, 10.8_

## Notes

### 事实基线（2026-08-05 实测）

**`execute_conversion` 六步现状**：Step1 快照 ✅ / Step2 `template_type` ✅ / **Step3 `return 0`** / **Step4 只 `SELECT count(*)`** / **Step5 `return 0`** / Step6 全链刷新 ✅ fail-open。

**`convert_disclosure_notes_v2`**（🔴 **已由 Task 10 删除**，以下为删除前的立项实证，保留备查）：`Called by` 11 处全是测试，生产 0 调用方。自身 3 缺陷 = format_diff 无 `section_id` 键（读 `fd.get("section_id")` 恒 None ⇒ `format_adapted_count` 恒 0）、`field_mapping` 全 null（`adapt_table_data` 实测输入==输出）、共有章节只计数不改 `section_id`。

🔴 **两处立项数字被 Task 10 实测纠正**：①被删的 v2 测试文件是 **2 个不是 1 个** —— `backend/tests/services/test_note_conversion_v2.py`(10 tests / HEAD 8823 B) **与 `backend/tests/services/test_note_conversion_pbt.py`(11 tests / HEAD 11438 B)**，合计 **21 条断言**（requirements 6.3 与本文件多处写的「11 个测试」只数了前一个文件）②`_map_report_rows` / `_map_disclosure_notes` 的**服务文件外**非测试调用方实测均为 `[]`（只有同类内 `execute_conversion` 调用），故「v2 删除后 Property 24 自动转绿」不成立 —— 详见 Notes 的 Task 10 实录「Property 24 口径实证」。

**差异数据落盘 vs 实时**：

| 桶 | 落盘 | 实时 |
|---|---|---|
| common_sections | 106 | **107** |
| soe_only_sections | 60 | 60 |
| listed_only_sections | 71 | **70** |
| format_diff_sections | 33 | **39** |
| is_mock | **true** | false |

`common` 集合比对结果 `False`；`field_mapping` 非空条数 **0/33**。

**章号映射分布**：`soe ch08 → listed ch05` 49 条 ✅ / `soe ch04 → listed ch03` 26 条 ✅ / **`soe ch08 → listed ch03` 10 条 ❓** / `soe ch11 → ch11` 4 条 / `soe ch12 → listed ch05` 2 条 ❓ / 其余零散。

**附注库现状**（5 个项目 / 1030 章节）：`last_sync_at` 非空 66 / `_source='workpaper'` 194 / 有 `sub_table_data` 191 / legacy 快照 493 / 空骨架 346。

### Wave 2 + Task 12/13 判据侧实录（2026-08-06）

**已交付（4 项 + 1 项部分）**：Task 4/5/6/7 全完成；Task 13 完成；Task 12 的**复核与裁决真源**完成，**改 JSON 未做**（原因见下）。

新增件：

- `app/services/note_conversion_row_codes.py` —— 12 条同义两码 + 3 条禁止改写目标 + 3 条稳定码
- `app/services/note_section_matcher.py` —— 5 对别名穷举配对 + 禁止匹配对，零相似度实现
- `app/services/note_variant_matrix_null_audit.py` —— 35 条 null 的三态裁决真源
- `backend/scripts/diagnose/diagnose_cross_variant_row_codes.py` —— 只读复算
- 守卫 `test_note_conversion_row_codes.py` + `test_note_section_matcher.py`（107 例）
  与 `test_variant_matrix_null_audit.py`（57 例），**9 个变异逐条打红并已还原**

**🔴 Task 12 改 JSON 与 spec A 硬撞车，本轮刻意不改**：A 的 Task 10（`[~]` 排队中）
要改同一个 `note_template_variant_matrix.json`，且 A 的需求 10.4 明确「其余 100 个
非母公司科目的取值 SHALL 不变」—— 而本 spec 要补的 35 条 null 全在那 100 个里。
两侧同时写同一文件必互相回退。**A 收口后按 `note_variant_matrix_null_audit.py`
的裁决表逐条补记即可，判据已冻结、无需重新调查**。

**🔴 四处 spec 记载被实证修正**

1. **需求 3.4 的前提不成立** —— `report_config` **无 `project_id` 列**（纯模板表，
   按 `applicable_standard` 分行，切 `template_type` 即切配置行）；全库 formula 引用
   那 12 组 row_code 的行数 = **0**；`wp_formula` **0 行**；附注侧 `binding_id` 是
   「章节号+行标签+列键」而 `ROW()` 参数是**单元格坐标** ⇒ **不存在 row_code 级公式**。
   故走 spec 预留的替代路径：保留返回 0 + 补实证依据 + 删「For now」（两处）+
   原因码 `no_mapping_needed` / `not_implemented` 可区分（新增两个 `*_reason()` 方法）。

2. **需求 3.8 按字面不可满足** —— 12 条映射的 value **12/12 都是「两侧异名」**
   （码位偏移的必然结果，`soe BS-111 → listed BS-077` 是正确映射）。真不变量是
   「MAP 的 key/value 都不得是**稳定码**」：初稿三条错的根因是 key（`BS-013`/
   `BS-053`/`BS-043`）两侧同名、压根不需改写，而非目标码有两义。守卫按此实现，
   两清单交集为空。

3. **「一码两义」实为 78 条**（spec 只列 3 条），但两侧异名本身不是禁止理由，
   只登记被编造过的 3 个目标码。**生成判据天然排除初稿三条**：
   `一年内到期的非流动资产` 在 listed 侧有 2 个码 ⇒ 该 row_name 整体被排除。

4. **需求 7.1 的 null 数分类修正** —— 35 条（listed 25 / soe 10）实为
   **假 null 13 + 部分落点 7 + 真 null 15**；需求 7.2 点名的 8 个落点全部 `[FOUND]`
   属实。**首轮精确匹配误判 8 条为真 null**（`实收资本`↔listed `五、53 股本`、
   `股本`↔soe `八、58 实收资本`、`外币折算`↔`五、73 外币货币性项目`、
   `分部信息`↔`十四、分部报告`、三条「一年内到期的X」↔`五、43 一年内到期的非流动负债`
   （明细行归入父章）、`其他综合收益`↔soe `八、79`）→ 判「某科目有无落点」必须按
   **关键词 + 人工判定**，精确标题匹配会把「明细行归入父章」「两版用语差异」全判成无落点。

**🔴 Wave 3 的两个前置风险（新发现，spec 未登记）**

- `disclosure_notes` **没有 `section_number` 列**（真实列名 `note_section`），而
  Task 8/9/11 通篇写「改写 `section_id` + `section_number`」；`legacy_aliases` 列
  **也不存在**，只能落 `template_lineage` JSONB（本 spec 无迁移）。
- **附注公式的 `binding_id` 内嵌章节号**（`五、11.分公司B.prior_year_value`，
  全库 **446 条**）⇒ Task 8 改写章节号会让这批绑定失联。需在 Wave 3 一并处置
  或显式排除。

**回归**：后端 `-k "note_conversion or note_template or note_section or disclosure_note or variant_matrix or offline"`
= **682 passed / 1 failed / 1 error**，两个失败均为**预存在基线**（两文件 `git status`
CLEAN + 对本轮新符号引用 NONE + 单独复跑同样失败）：
`test_offline_roundtrip_uat::test_modified_sections_diff_detected`（`imported_value=None`）
与 `test_migration_v017`（`R017__` 回滚脚本缺失致 collection error）。

### 与其他 spec 的边界

- 母公司章节结构与取数 → `parent-company-note-chapter-and-sourcing`（本 spec 只在禁止匹配对中引用母公司章标题）
- 模板 columns 补齐（缺 337/809）与 legacy 快照迁移（493 个）→ `note-template-columns-and-legacy-snapshot-closure`
- 合并附注 V2（`CONSOL_NOTES_V2_ENABLED=False`）与跨模板翻译（`CONSOL_CROSS_TEMPLATE_ENABLED=False`）→ 需用户拍板是否翻默认，不在本 spec

### 实现顺序提示

Task 4（匹配器）是 Task 8（章节映射）的前置；Task 1（差异数据）也是。

🔴 **Task 10 的「接线 vs 删除」已裁决 = 删除不接线（2026-08-07 实测，推翻本行原来的「建议选接线」）**。立项时写「v2 是唯一已实现的正确骨架，删掉要重写」，实测**不成立** —— Task 8/9 落地后生产路径 `_map_disclosure_notes` 已完整实现且严格强于 v2（别名桥接 / binding_id 前缀重写 / sid NULL 回填 / 章节号占用检查 / 逐章 savepoint，v2 五项全无），接线只会造第二份真源。21 条测试断言已迁移到 `test_note_conversion_section_mapping_production.py`，删除留证与迁移映射见 Notes 的 Task 10 实录。

### Wave 2 实录（2026-08-06，Task 4/5/6/7 完成，未 commit）

**产出 5 个文件**：

| 文件 | 作用 |
|---|---|
| `backend/app/services/note_conversion_row_codes.py` | 双清单真源（12 条同义两码 + 3 条禁止改写 + 3 个稳定码）+ 改写函数 |
| `backend/app/services/note_section_matcher.py` | 章节匹配器（5 对别名穷举 + 3 条禁止对，**不提供相似度接口**） |
| `backend/scripts/diagnose/diagnose_cross_variant_row_codes.py` | 只读生成/复核脚本（连 report_config 四变体对账） |
| `backend/tests/test_note_conversion_row_codes.py` | Property 11~13 守卫 |
| `backend/tests/test_note_section_matcher.py` | Property 18~21 守卫 |

**守卫 107 passed / 0 failed；6 个变异全部打红并已还原**（清空禁止匹配对 / 别名失效 / 禁止清单移除 BS-016 / 原因码改 not_implemented / 稳定码清单移除 BS-013 / 引入 difflib）。

**🔴 三处实证推翻立项记载**

1. **「一码两义」不是 3 条而是 78 条**，且**两侧异名本身不构成禁止理由** —— 12 条正确映射的 value **12/12 都是两侧异名**（码位偏移的必然结果，如 soe `BS-077`=▲应付手续费及佣金 / listed `BS-077`=其中：优先股）。故需求 3.8 按「MAP ∌ 全部 78 条」**不可满足**。
   **真不变量 = MAP 的 key/value 都不得是「稳定码」（两侧同名 ⇒ 压根不需改写）**。初稿三条错的根因正是 key 为稳定码（`BS-013`/`BS-053`/`BS-043`），不是「目标码有两义」。守卫按此落地，3.8 收窄为「MAP ∩ FORBIDDEN(3 条被编造过的目标码) = ∅」，可满足且已断言。

2. **生成判据天然排除初稿三条**（实测 False/False/False）：判据要求「同 `(report_type,row_name)` 在两侧**各恰 1 个** row_code」，而 `一年内到期的非流动资产` 在 listed 侧有 2 个码（BS-013+BS-016）⇒ 整个 row_name 被排除。这是结构性保证，不靠人工排除。生成结果与手工 12 条**逐条相等**。

3. **公式改写当前无对象**（Requirement 3.4 的真实成因，与立项「两准则 row_code 方案相同」的错误理由都不同）：
   - `report_config` **无 `project_id` 列** = 纯模板表，按 `applicable_standard` 分行；切 `template_type` 自然读另一套配置行。
   - 全库 `report_config.formula` 引用那 12 个 row_code 的行数 = **0**（`ROW()` 引用集只覆盖 BS-002~BS-128 / CFS / CFSS / EQ / IMP / IS-001~IS-030 等主表行）。
   - `wp_formula` 表 **0 行**。
   - 附注公式 `binding_id` 形如 `五、11.分公司B.prior_year_value`（章节号+行标签+列键），`note_source_resolvers` 的 `ROW()` 参数是**单元格坐标**（`R2C1`）⇒ **不存在 row_code 级附注公式**。

   ⇒ 两处 `return 0` 保留但**删掉「For now」临时措辞**并补原因码：新增 `report_row_mapping_reason()` / `formula_rewrite_reason()` 两个静态方法，均返回 `no_mapping_needed`（与 `not_implemented` 可区分，Requirement 4.4）。

**🔴 两条给后续 Wave 的硬约束**

- **`disclosure_notes` 没有 `section_number` 列，也没有 `legacy_aliases` 列**（实测列清单 39 列）。章节号存在 **`note_section`**（如 `八、9`），别名只能落 `template_lineage` JSONB（本 spec 无迁移）⇒ **Task 8/9 的「改写 `section_number`」「追加 `legacy_aliases`」须按此改写为 `note_section` + `template_lineage`**。
- **附注公式 `binding_id` 内嵌章节号**（`五、11.…`，全库 446 条 note 带 binding）⇒ Task 8 改写 `note_section` 时这些 binding 会**失联**，是立项未登记的连带缺陷，须在 Task 8 一并处置（同步改写 binding_id 前缀，或在 `template_lineage` 记旧章节号供解析回退）。

**listed 母公司章标题实测为「公司财务报表主要项目注释」（源 docx Heading 1 无「母」字）** ⇒ 禁止匹配对同时登记两种写法（带「母」的是 JSON 现值，A spec 已裁决保留）。

**回归**：`-k "note or conversion or disclosure or template_diff"` = **682 passed / 1 failed / 1 error**，两者均为预存在基线（`test_offline_roundtrip_uat`（`imported_value=None`）与 `test_migration_v017`（`R017__` 回滚脚本缺失，54 collection errors）；两文件 `git status` 均 CLEAN、对本轮符号引用 NONE、单独复跑同样失败）。

### 假 null 补记落地实录（2026-08-07，A spec 收口后阻塞解除）

**产出**：`backend/scripts/fix/fix_variant_matrix_false_nulls.py`（幂等，三闸门）+ 裁决表两处改判 + `test_variant_matrix_null_audit.py` 语义翻转 + `test_variant_matrix.py` 的 index 判据分级。

**落地规模**：9 科目 / 18 slot（`zi_chan_jian_zhi_sun_shi` `zi_chan_chu_zhi_shou_yi` `ying_ye_wai_shou_ru` `ying_ye_wai_zhi_chu` `xian_jin_liu_liang_biao_xiang_mu_zhu_shi` `zhai_wu_chong_zu` `jie_kuan_fei_yong` `zhong_zhi_jing_ying` + soe `yi_ban_feng_xian_zhun_bei`），非 null 计数 **338 → 356**。

**五处立项/前序记载被实证纠正**：

1. **🔴 `tou_zi_shou_yi` 与 `tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d` 补记后完全撞码** —— 两者是**同一科目被矩阵拆成两条**（A spec 的 `T10_PARENT_SIDE_WITHOUT_MERGED` 已登记成因：`build_variant_matrix.normalize_title` 只剥【】不剥括注文本，「投资收益【下表中不适用的项目，删除】」与「投资收益」归一后不相等 ⇒ 未配对）。按 FALSE_NULL 补记会让 HEAD 侧 **0 组撞码变成 4 组**（两条在四个变体上全同码）⇒ 附注取数无法判定归属。**两条一并改判 CROSS_GRAIN**（真正的修法是修 `normalize_title` 并合并两条 account，属矩阵生成器侧的活）。

2. **🔴 `gu_fen_zhi_fu` 的落点 `十二` 是章标题容器不是披露节** —— level=1 / 6 子节 / 0 表 / 0 text_sections。前序会话已改判 CROSS_GRAIN，但**当时没有任何守卫保护该改判**（变异检验实测：改回 FALSE_NULL 全绿）⇒ 本轮补「落点须为叶子节」判据。

3. **🔴 判据是「无子节」不是「tables > 0」** —— listed 模板有 **48 个 `level=2 且 tables=0`** 的节，它们是纯文字披露节（会计政策章下的政策描述，带 text_sections），**是合法落点**：现有落点 `五、72` 就是这种形态且已被 2 处引用；本轮补记的 `三、借款费用`（5 段 text_sections）与 `三、债务重组【不适用`（15 段）同形。按「tables > 0」写判据会把这两条误拒。

4. **🔴 `test_variant_matrix.py::test_every_matrix_code_exists_in_index` 的判据本身有缺陷（预存在红，本轮一并处置）** —— 它断言「矩阵每个 code 必在 index 对应变体的**项目注释章**」，而 `section_code_index.json` 的 `version='poc-v1'`，其生成器 `build_section_code_index.py` 自述「仅扫描已打标的章节；未打标节输出到 stdout 供人工补录」⇒ 未打标的节天然不在 index 里。HEAD 侧已红 **6 项**（`三、公允价值变动收益` / `三、信用减值损失` / `三、所得税费用` 各 2 变体），本轮补记会扩大到 **24 项**。**修法 = 判据分两级**：强断言改为「code 必存在于目标模板 `note_template_{listed,soe}.json`」（那才是矩阵取值的真源，index 自身也是从模板+docx 派生的，**零豁免**），弱断言保留「已被 index 收录的 code 必落在项目注释章」（防 POC 错码 `五、12` 回潮）+ `INDEX_UNCOVERED_CODES` 登记表（12 条带成因，配 stale 检测 + 条数上限 + 理由质量闸）。**该 red 由此归零**。

5. **裁决表语义需要翻转** —— 原三条断言（`test_listed_audit_matches_json_nulls` / `test_soe_audit_matches_json_nulls` / `test_audited_keys_are_all_currently_null`）要求「裁决表 ≡ 当前 JSON 的 null 集合」，补记落地后必然打红。改为「**历史 null 台账 + 补记已落地**」：FALSE_NULL 条目允许已非 null 但**落地值必须等于 `target_section`**（更强：既保住台账、又验证落地正确性）；CROSS_GRAIN / TRUE_NULL 仍必须是 null。

**变异检验 7/7 全 RED**（`_wip_b_mut3.py`）：三道幂等闸门以 rc=2 拒绝写盘（撞码 / 章标题容器 / additive 覆盖），四个数据级变异被守卫打红（落地值改错 / 补记被回退 / 落点改成不存在的章节号 / 登记表塞 stale 条目）。另有前一轮 `_wip_b_mut.py` 的 8/8 全 RED 覆盖成因 B 三态判据。

**幂等双证**：`--check` rc=0（0 欠账）+ 二次 `--apply` md5 不变。A spec 的 `fix_variant_matrix_parent_sections.py --check` 仍 rc=0（零回归）。

**回归**：`test_variant_matrix.py`(105) + `test_variant_matrix_null_audit.py` + `test_note_conversion_row_codes.py` + `test_note_section_matcher.py` + A spec 两个守卫 = **467 passed / 0 failed**。

**遗留给后续 wave**：`normalize_title` 不剥括注导致的「投资收益」双条目（矩阵生成器侧）· `section_code_index.json` 补全打标后 `INDEX_UNCOVERED_CODES` 应逐条移出（stale 断言会提醒）。

### Wave 3 章节映射守卫实录（2026-08-08，Task 11）

**产出** `backend/tests/test_note_conversion_section_mapping.py`（**40 例，全绿**），覆盖 **Property 5~10 / 16~19 / 24~26 / 35 / 36**。

**与 Task 10 两个文件的分工（已写进文件 docstring，防下个会话重复造）**

| 文件 | 定位 |
|---|---|
| `tests/services/test_note_conversion_section_mapping_production.py`(26) | 承接已删 v2 的 21 条断言，判据是「**某一个**章节被正确处理」 |
| `tests/test_note_conversion_v2_removal.py`(55) | 删除收口 + **Property 24 判据的唯一实现** + 迁移表双向锁死 |
| `tests/test_note_conversion_section_mapping.py`(40) | **Property 级不变式**，判据是「一次运行后**全体**章节满足的性质」+ 场景级反向自检 |

⇒ 本文件刻意**不写**单例断言（Task 10 已有），改写成全量扫描后的不变式 —— 单例断言挡不住「只对第一个章节生效」的实现。**Property 24 只 import 不重造**（`_method_names_under_scan` / `_non_test_call_sites` 在 v2_removal，同一不变式两处实现即双真源）；内存替身 `FakeSession` / `make_note` 同样 import 复用。

**Property 25 按 design 明示不作验收判据**（接线分支未选），只留说明性断言「服务类上不得再出现 v2 方法」+ 一条实证锚点「`field_mapping` 全 null 时 `format_adapted` 必须为 0」（该锚点带 `pytest.skip` 出口：`field_mapping` 哪天非空即自动让位给 `test_note_template_diff_integrity` 的守卫，不留过期硬断言）。**Property 26 只做轻断言**（表存在 + 覆盖 ≥21 条 + 每条源/目标名合法），双向锁死仍在 v2_removal。

**变异检验 9/9 全 RED**（`_wip_t11_mutate.py`，判据 = **失败测试名差集**、三态 RED/GREEN/ANCHOR-MISS、备份落 `.t11bak` + 逐条字节还原 + md5 核验；收尾两文件 md5 与基线逐字相同）：

| 变异 | 判定 | 打红的用例 |
|---|---|---|
| M1 `mapped` 改回 `count(*)` 冒充 | RED | 10 例（含 `test_zero_common_sections_returns_mapped_zero` 与反向自检 `test_count_star_impersonation_would_fail_this_scenario`） |
| M2 去掉 `legacy_section_ids` 追加 | RED | 1 |
| M3 改 `note_section` 不改 `binding_id` 前缀 | RED | 2 |
| M4 `section_id IS NULL` 静默跳过 | RED | 3 |
| M5 逐章 savepoint 隔离失效 | RED | 1 |
| M6 归档不写 `archived_sections` | RED | 3 |
| M7 新建把 `note_section` 写成 sid | RED | 1 |
| M8 `format_adapted` 改回无条件 `+= 1` | RED | 1 |
| M9 **把 Property 24 判据改严（排除服务文件自身）** | RED | 2（`test_self_call_counts_as_consumer` / `test_no_method_is_orphaned`） |

M9 是本轮特意补的**口径锁死**：design.md 已钉死「同类内调用也算」，M9 证明一旦有人把判据改成「必须有服务文件之外的调用方」就会打红 —— 那样会把 `_map_*` 这类正常私有子步骤误判成孤儿，逼人把它提成公开 API（制造第二个入口 = 双真源）。

**🔴 三处落地时新查出的事实**

1. **Task 10 的失败隔离断言只能验半边** —— `FakeSession(flush_fail_on=…)` 的 `flush` 判据是「`self.notes` 里存在被标记的 note」，与「当前正在处理谁」无关 ⇒ 处理**健康**章节时的 flush 也会抛、健康章节被连带打死，故「其余仍处理」这半边测不出来。本文件改在 `_record_lineage`（真实写入路径，位于逐章 savepoint 之内）上按 **note id 精确**抛，于是能同时断言三件事：失败章节进 `failed`（带 `phase`/`error`）· 失败章节**之前与之后**的章节都仍被改写 · 失败章节被 savepoint 回滚到改写前（`section_id`/`note_section` 都回到源侧，不留半成品）。
2. **替身里自造章节号会互相占位** —— 真实库靠 `uq_disclosure_notes_project_year_section` 保证唯一，替身不保证；若两条测试记录的 `note_section` 撞上另一条的**目标**章节号，就会得到莫名的 `target_note_section_occupied`。故 fixture 里按「源章节号与目标章节号两两不得相交」筛候选（先取别名桥接那对再筛共有章节，归档/新建候选也参与排除），全部判据数据从真实 diff + 两份模板现取、零硬编码。
3. **`format_diff` 的 `field_mapping` 实测仍 39/39 全 null** ⇒ `format_adapted` 恒 0 是**合法空操作**，与 Wave 1 记载一致；判据按此写并留了过期出口。

**实测锚点（本轮复算，供后续会话直接引用）**：`_build_section_mapping_plan(soe→listed)` = pairs **112** / source_only **56** / target_only **65** / bridged **5**；源模板 sid 回填索引 `by_number_title` 188 键**全唯一**、`by_title` 168 键中 **149 唯一**（19 个撞名 ⇒ 歧义分支有真实样本）；`source_only 章节号 ∩ target_only 章节号 = {七, 五, 十三}`（正是「新建空章节会撞刚归档的同号行」那三个）。

**回归**：本文件 40 + Task 10 两文件 81 + `test_note_template_diff_integrity` 81 + `test_note_conversion_row_codes` 51 + `test_note_section_matcher` 56 = **309 passed / 0 failed**；`--collect-only` 核验**无重复收集**（跨测试模块 import 的常见副作用，逐 id 去重 309/309）。**未改任何生产代码**（`note_conversion_service.py` md5 与本轮开工时逐字相同）。

**遗留**：CI job `note-conversion-correctness` 归 Task 18（本文件届时挂进去）· 真实库验收归 Task 19。

### Wave 1 差异数据重生成实录（2026-08-07，Task 1：重生成 + 定位键裁决）

**产出 / 改动**

| 文件 | 动作 |
|---|---|
| `backend/scripts/gen/generate_note_soe_listed_diff.py` | 重写为**薄壳**（委托 service）+ 修路径缺陷 + `--check`/`--dry-run` |
| `backend/data/note_soe_listed_diff.json` | 重生成，`is_mock` → `false` |
| `backend/app/services/note_conversion_service.py` | step 6 定位键改按侧取；删死代码 `format_diff_ids` |
| `backend/tests/test_note_template_diff_integrity.py` | 新建守卫 16 例（Task 1 范围：Req 1.1 / 1.4） |
| `backend/tests/services/test_note_conversion_v2.py` | 修 `format_diff` fixture 形态（原为「测试镜像 bug」） |

**四桶条目数变化（重生成前 → 后）**

| 桶 | 前（落盘 stale） | 后（= 实时） | spec 预期 | 结论 |
|---|---|---|---|---|
| `common_sections` | 106 | **107** | 106→107 | ✅ 符合 |
| `soe_only_sections` | 60 | **61** | 60→60 | 🔴 **不符，spec 记载已过期** |
| `listed_only_sections` | 71 | **70** | 71→70 | ✅ 符合 |
| `format_diff_sections` | 33 | **39** | 33→39 | ✅ 符合 |
| `is_mock` | `true` | `false` | false | ✅ |

**🔴 `soe_only` 60→61 的成因（spec Notes 的「60 | 60」是 A spec 收口前的旧测量）**：A spec 把 `note_template_soe.json` 第十二章标题由「股份支付」改正为「母公司财务报表的主要项目附注」，该标题在 listed 侧无对应 ⇒ 新增一条 soe 独有。连带三条 `common` 条目的 soe 侧 sid 前缀由 `chapter-12-gu-fen-zhi-fu-*` 重键为 `chapter-12-mu-gong-si-cai-wu-bao-biao-de-zhu-yao-xiang-mu-fu-zhu-*`（投资收益 / 现金流量表补充资料 / 营业收入与营业成本）。

**另一条条目级变化与 M 循环有关**：`一般风险准备` 由 `listed_only` 移入 `common`（soe 侧新建了 `八、94 一般风险准备` 章节）—— 这解释了 `listed_only` 的 −1。`format_diff` 的 +6 净变化来自 H 循环会计政策章表结构调整（移除重复的在建工程/使用权资产政策表、新增固定资产/生物资产政策表）。条目级台账可随时复算：`python backend/scripts/gen/generate_note_soe_listed_diff.py --check`（打印每桶 `only_stored`/`only_live` 计数），需要条目身份则直接调 `note_template_diff.compare_diff_payloads(stored, live)`。

**Requirement 1.4 裁决 = 选项 A「消费方按侧读 `soe_section_id`/`listed_section_id`」**，三条依据：

1. `format_diff` 条目**从来没有** `section_id` 键（落盘与实时键集均为 `field_mapping` / `listed_format` / `listed_section_id` / `section_title` / `soe_format` / `soe_section_id`）⇒ 改造前 `fd.get("section_id")` 恒 None、step 6 恒空转、`format_adapted_count` 恒 0；
2. 「补 `section_id`」要把一个**运行时才知道的侧向选择**编码进静态数据，既有歧义又与两侧 sid 构成双真源；
3. 同模块 `classify_section_mapping` 早已按侧取键（`id_field = "soe_section_id" if source_type == "soe"`）⇒ 选项 A 与既有范式一致。

守卫钉死方式：条目**不得**出现 `section_id` 键 + 键集冻结 + 生产代码不得出现 `fd.get("section_id")`（读源码前先 token 级剥注释，并配「原文确实含该字样」反向自检 —— 生产代码的踩坑说明注释里原样写了它）。

**🔴 生成脚本本身有两个缺陷（Task 1 顺带修掉）**

1. **`DATA_DIR` 指向不存在的 `backend/scripts/data`** —— 脚本从 `backend/scripts/` 移入 `backend/scripts/gen/` 时路径未跟着改 ⇒ 直接运行必 `FileNotFoundError`，也就是这个「重生成」入口**在移动之后从未成功跑过**（落盘长期 stale 的机械成因）。改为双哨兵文件向上查找 backend 根。
2. **自带一份 `generate_diff()` 独立实现**（与 `compute_diff_from_templates` 逐行雷同 + 硬写 `is_mock: True`）= 平台已登记的「未完成的重构 / 双真源」⇒ 改 service 匹配口径不会传导到落盘，`load_diff_data()` 的交叉校验会永久报不一致。现改为委托，**落盘与实时由构造保证一致**，`is_mock` 只由 service 返回。

**🔴 `test_note_conversion_v2.py` 的 `format_diff` fixture 是「测试镜像 bug」**：原 fixture 自造 `{"section_id": "fmt_diff_1"}`（真实数据没有这个键），使 `test_convert_v2_format_diff_adapted` 长期变绿而生产恒 0。已按真实形态改为两侧 sid（诚实修正，非回归）。

**验证**

- 守卫 `test_note_template_diff_integrity.py` **16 passed / 0 failed**
- 幂等双证：`--check` rc=0 + 二次写盘 md5 不变（`e9a754f989e1e236cd2eebf786211bb2`）
- **变异检验 7/7 全 RED**（`_wip_b_t1_mut.py`，判据 = 失败测试名差集，还原按字节 + md5 核验，post-restore 全绿）：`is_mock` 改回 true / 往条目补 `section_id` / 消费方改回 `fd.get("section_id")` / 删按侧取键表达式 / 生成脚本硬写 `is_mock=True` / 生成脚本自带第二份实现 / `DATA_DIR` 指回 `scripts/data`
- **零回归双证**（`_wip_b_t1_zero.py`）：把 4 个改动文件换成 `git show HEAD:` 版跑同一组（`--ignore` 新守卫防收集崩），两侧失败集合**逐条相同 56 项 + 8 errors**（新增 0 / 修好 0），收集到的测试 id 集合两侧均 994 条完全相同。含守卫时 945 passed，不含时 929 passed（差 16 = 守卫例数）。
- 相关测试：`test_note_conversion_v2` + `test_note_conversion_pbt` + `test_consol_cross_template` = **34 passed**

**与 Task 3 的边界**：本轮已建 `test_note_template_diff_integrity.py`，只含 Task 1 范围（Req 1.1 落盘去 mock + 落盘≡实时 + Req 1.4 定位键裁决 + 生成脚本委托）。**Task 3 应在此文件上扩** Property 2（落盘/实时不一致时 WARNING 且以实时为准的日志路径）与 Property 4（`adapt_table_data` 的 `field_mapping` 空/非空语义），**勿另建文件**。

**遗留（不阻塞，属后续 wave）**：`field_mapping` 仍为 `0/39` 全 null（Req 1.5 / Property 4 归 Task 2+3）· `preview_conversion_v2` 的 `is_mock` warning 分支现恒不触发（`load_diff_data` 一律返回实时结果，`is_mock=False`），是否改成「落盘 stale」提示归 Task 15。

### Wave 1 落盘/实时一致性与适配语义实录（2026-08-07，Task 2）

**开工前的实证：Task 2 的前两条要求已由上一轮中断会话交付**（`note_template_diff.py` 在工作树里已是「实时为准 + 落盘交叉校验 + WARNING」，`compare_diff_payloads` / `DIFF_BUCKETS` / `reset_diff_cache` 均已存在，`git diff` +144/−12 未提交）。本轮补第三条（`adapt_table_data` 语义）+ 强化一处比对判据。

**改动 2 个文件**

| 文件 | 动作 |
|---|---|
| `backend/app/services/note_template_diff.py` | `_bucket_identity` 改载荷完备；`adapt_table_data` 拆薄壳 + 新增 `adapt_table_data_with_report` / `AdaptReport` / 4 个原因码 / 2 张指令登记表；`_apply_column_remap`·`_apply_row_filter` 重写为返回 `(changed, notes)` |
| `backend/app/services/note_conversion_service.py` | step 6 的 `format_adapted_count` 改按「输出 != 输入」计数 + 空操作章节聚合 WARNING |

**🔴 五处实证比 spec 记载更严重 / 与记载不符**

1. **`compare_diff_payloads` 的条目标识原本不载荷完备** —— 只比 `(soe_sid, listed_sid, section_title)`，`format_diff` 的 `soe_format` / `listed_format` / `field_mapping` 载荷变化**检测不到**。而 `adapt_table_data` 正是拿 `*_format` 当目标格式、拿 `field_mapping` 当指令 ⇒ 载荷 stale 等于「按旧模板结构去适配新模板」，Requirement 1.2 要求比的是**条目集合**而载荷是条目的一部分。已改为「可读头部 + 其余字段规范化序列化」，四个桶一律载荷完备。反向自检实测：改 `listed_format` / `soe_format` / `field_mapping` 任一项 → `consistent=False`（旧标识全部判 True）；顺带把「往条目补 `section_id`」也变成可检测（强化 Task 1 的裁决）。

2. **`column_remap` 的缺陷比 requirements 记载的「输入==输出」更严重** —— requirements 只记「`field_mapping` 全 null ⇒ 空操作」，但**即便 `field_mapping` 非空**，原实现也只改 `_columns_meta[].id`，行内 dict 形态的 `values` / `_cell_modes` / `_cell_meta` / `_legacy_cells` 与表级 `_cell_provenance`（键 `"{row_idx}:{col_id}"`）**一个都不跟着改** ⇒ 列改名后值、人工标记（`manual`）、溯源全部留在旧列 id 上 = 事实上丢人工编辑（触及平台「manual 单元格必须保留」红线，比「什么都没做」更坏）。实测：`col_movement → col_category_sum` 后 `_columns_meta` 已是新 id 而 `rows[0].values` 键仍是 `col_movement`。已四处一并改，并加**列 id 撞车检测**（目标 id 已存在 / 两个源改成同一目标 → 跳过并记诊断，守住 ADR-011 的 CI-3「列 id 全表唯一」）。

3. **`_columns_meta` 缺失即整体放弃** —— 原 `_apply_column_remap` 首行 `if not isinstance(columns_meta, list): return table_data`，即便行内确有可改的列键也一律不改。现改为「缺 meta 时仍改行内 dict 列键 + 记诊断」。

4. **`value_transform` 是 docstring 宣称但从未实现的死指令** —— 原 docstring 把它列进 `field_mapping` 支持项，代码里零实现且静默忽略，而调用方照样 `format_adapted_count += 1`。现显式登记进 `DECLARED_UNIMPLEMENTED_FIELD_MAPPING_KEYS`，命中即 WARNING + `reason=unsupported_only`（与「已识别指令但没命中」的 `no_effect` 可区分）。同族：`row_filter` 的未识别子键也逐个记诊断。

5. **`row_filter` 剔行会让表级 `_cell_provenance` 行下标错位** —— 键形态是 `"{row_idx}:{col_id}"`，原实现只重写 `rows` 不重排 provenance ⇒ 溯源静默指向错行（潜伏，因 `row_filter` 当前无生产用例）。已补重排 + 被剔除行的溯源一并丢弃。

**消费方的假成功一并修（落在 Requirement 4.1 半径，但由 1.5 的语义澄清直接驱动）**：`convert_disclosure_notes_v2` step 6 改造前无条件 `format_adapted_count += 1`，而实测 **39/39 条 `format_diff` 的 `field_mapping` 全为 null** ⇒ 上报「已适配 39 个」而一处未改，还把等值深拷贝写回 `note.table_data` 产生无意义 UPDATE。现按「输出 != 输入」计数，空操作章节收集后一条聚合 WARNING（不新增返回键，避免与 `test_convert_v2_same_type_noop` 的整字典断言冲突，也不挡 Task 8/10 重新定义返回口径）。

**验证**

- 12 个行为案例逐项实测（null / 空 dict / 命中 / 无 meta / 撞车 / 仅 `value_transform` / 未知指令 / filter 命中 / filter 未命中 / 源列不存在 / list 形态 values + 索引键 `_cell_modes` / remap+filter 同时）：**不变式 `changed == (输出 != 输入)` 全案例成立**；入参一律未被就地修改；薄壳与 `with_report` 输出逐项一致；非 dict 入参返 `{}`。
- 真实 39 条 `format_diff` 的 `reason` 分布 = `{'no_field_mapping': 39}`（全走合法空操作，与 spec 实证一致）。
- `load_diff_data` 的「以实时为准」路径实测：把落盘改成 `is_mock=true` + 只留 5 条 common → 返回值 `is_mock=False` / common **107 条**（实时）+ **2 条 WARNING**（is_mock 占位 + 含差异摘要的不一致告警）；测试后按字节还原，md5 仍为 `e9a754f989e1e236cd2eebf786211bb2`（与 Task 1 记录一致）。
- `import app.main` 实跑通过（`get_diagnostics` 查不出漏 import，必须真执行）。
- 直接相关测试 **157 passed / 0 failed**（`test_note_template_diff_integrity` 16 + `test_note_conversion_v2` + `test_note_conversion_pbt` + `test_consol_cross_template` + Wave 2 的 `test_note_conversion_row_codes` + `test_note_section_matcher`）；既有 16 例守卫零打红。
- 零回归：`-k "note_conversion or note_template or note_section or disclosure_note or variant_matrix or offline or consol_cross"` = **927 passed / 56 failed / 8 errors**，与 Task 1 记录的零回归基线（**56 项 + 8 errors**）逐条吻合；9 个失败文件 `git status` 全 CLEAN 且对本轮改动符号（`adapt_table_data` / `AdaptReport` / `note_template_diff` / `format_adapted` / `convert_disclosure_notes_v2` / `_apply_column_remap` / `_apply_row_filter`）引用数**全为 0**。

**留给 Task 3 的守卫清单（Property 2 + Property 4，仍在 `test_note_template_diff_integrity.py` 上扩，勿另建文件）**

- Property 2：落盘 stale → `load_diff_data` 记 WARNING 且返回实时结果（含 `is_mock=true` 与条目不一致两条告警路径；测试须按字节还原落盘文件）。
- Property 4：`field_mapping` 空 → 输出逐字等于输入且 `reason=no_field_mapping`；非空 → 结构确实改变。另须钉死本轮四条不变式 —— ①`changed == (输出 != 输入)`（禁改成自我声明）②`column_remap` 必须同时改 `_columns_meta[].id` + 行内四个 dict 桶 + `_cell_provenance` 键（**变异：只改 meta 必红**）③列 id 撞车必须跳过而不是产生重复列 ④`row_filter` 剔行后 `_cell_provenance` 行下标必须重排。
- 载荷完备标识：改 `format_diff` 任一载荷字段 → `compare_diff_payloads` 必判不一致（**变异：把标识退回只比 sid+标题必红**）。
- 消费方计数：`format_adapted_count` 不得把空操作计为已适配（**变异：改回无条件 `+= 1` 必红**）。

**遗留（不阻塞）**

- **`field_mapping` 永远为 null 的根因在 `compute_section_diff`**：它硬写 `"field_mapping": None  # Populated by P-7 auditor annotation` —— 该字段设计上由**人工标注**产生，而平台没有任何标注入口 ⇒ Requirement 1.5 的「非空时真正改结构」当前只能靠单测行使，生产侧要等标注通路（归 Task 15 预览端点或另立）。本轮已让「非空但改不动」不再静默，标注一上线即可观测。
- `value_transform` 仍未实现（已显式登记 + WARNING，不是静默忽略）。

### Wave 1 差异数据守卫实录（2026-08-07，Task 3：Property 1~4 收口）

**在 Task 1 已建的 `backend/tests/test_note_template_diff_integrity.py` 上扩，未另建文件**（按 Task 1/2 Notes 的边界要求）。

| 项 | 数值 |
|---|---|
| 扩前 | 16 例（Property 1 / 3） |
| 扩后 | **78 例 / 0 failed**（净增 **62** 例，Property 2 / 4 + 两族不变式） |
| 变异检验 | **8/8 全 RED**，逐条按字节还原 + md5 核验 |
| 真实落盘文件 | 全程未改动（md5 恒 `e9a754f989e1e236cd2eebf786211bb2`） |

**新增 5 个测试类**

| 类 | 覆盖 |
|---|---|
| `TestStaleFallsBackToLive`（8 例） | Property 2：`is_mock=true` / 条目不一致 **两条告警路径** + 载荷 stale 告警 + 落盘缺失 + 落盘损坏 + fail-open 降级 + 「一致时不误报」反向自检 + 「monkeypatch 确实生效」防空转 |
| `TestRealDiffJsonUntouched`（1 例） | 前后对照核验本模块未改动真实数据真源 |
| `TestBucketIdentityIsPayloadComplete`（8 例） | 载荷完备标识：改 `format_diff` 的 `soe_format`/`listed_format`/`field_mapping` 任一项必判不一致；补 `section_id` 亦必判不一致；元数据（`is_mock`/`version`）不进条目比对 |
| `TestAdaptTableDataSemantics`（38 例） | Property 4 + 四条不变式（见下） |
| `TestConsumerCountsOnlyRealAdaptations`（7 例） | `format_adapted_count` 不得把空操作计为已适配（AST 结构断言 + 两个反向自检替身） |

**Task 2 留下的四条不变式逐条落地**

① `changed == (输出 != 输入)` —— **12 个案例参数化**（null / empty / remap 命中·未命中·同名·撞车 / 仅 `value_transform` / 未知键 / filter 命中·未命中·空 / remap+filter）。典型错误形态 `changed = bool(field_mapping)` 会在 `unsupported_only` 案例打红。
② `column_remap` 同时改 `_columns_meta[].id` + 行内四桶（`values`/`_cell_modes`/`_cell_meta`/`_legacy_cells`）+ `_cell_provenance` 键；另断言 **`manual` 标记与值只换键不丢内容**（平台红线）、`_columns_meta` 缺失时仍改行内键、列**索引**形态的 `_cell_modes`（键 `"0"`/`"1"`）不被误命中。
③ 列 id 撞车跳过：目标 id 已存在 → 不改写且留「撞车」诊断；两源改同一目标 → 只应用一条且 id 集合仍唯一。
④ `row_filter` 剔行后 `_cell_provenance` 行下标重排 —— fixture 的 provenance 值取可区分标记 `P0/P1/P2`，剔除首行 `total` 后断言 `{"0:...": "P1", "1:...": "P2"}`，「不重排」会留下 `P0/P1/P2` 而打红（只比键数量的弱判据抓不到）。

**变异检验 8/8 全 RED**（`_wip_b_t3_mut.py`，判据 = **失败测试名差集**三态 RED / GREEN(守卫缺陷) / ANCHOR-MISS(脚本缺陷)；`.bak` 落磁盘 + `try/finally` 无条件写回 + md5 核验；post-restore 78 passed / 0 failed）

| 变异 | 新增失败数 | 代表打红项 |
|---|---|---|
| M1 `is_mock` 改回 true | 1 | `test_stored_is_not_mock` |
| M2 往 `format_diff` 条目补 `section_id` | 4 | `test_entry_key_set_is_frozen` / `test_bucket_entries_equal` |
| M3 消费方改回 `fd.get("section_id")` | 1 | `test_consumer_selects_sid_by_side` |
| M4 `column_remap` 只改 meta（行内桶不动） | 3 | `test_column_remap_moves_meta_rows_and_provenance` / `..._preserves_manual_marks_and_values` |
| M5 条目标识退回只比 sid+标题 | 5 | `test_format_diff_payload_change_detected[soe_format/listed_format/field_mapping]` |
| M6 `format_adapted_count` 改回无条件 `+= 1` | 1 | `test_noop_guard_precedes_increment` |
| M7 `row_filter` 剔行后不重排 provenance | 2 | `test_row_filter_reindexes_cell_provenance` |
| M8 去掉落盘交叉校验分支（`if stored is not None:` → `if False:`） | 4 | Property 2 的三条告警断言 + 防空转断言 |

**🔴 五处与 spec/守卫清单记载不符的实证**

1. **Property 2 不需要改真实落盘文件**（对用户给的守卫清单「测试改落盘文件后必须按字节还原」的一处**有意偏离**）：`load_diff_data()` 在调用时读模块全局 `_DIFF_JSON_PATH`，故 stale 场景一律 **monkeypatch 到 tmp 文件** —— 走完全相同的生产分支，却完全不触碰 `backend/data/note_soe_listed_diff.json`（5 个 spec 共享的数据真源，并发会话高频读写）。真实文件的字节级改动**只发生在变异脚本里**（那里才有 `.bak` + `try/finally` + md5 核验）。测试侧改用 `TestRealDiffJsonUntouched` 做「模块导入时 md5 ↔ 运行结束时 md5」**前后对照**，**有意不冻结 md5 常量** —— 模板合法变更后重生成会让它变，冻结即假红发生器（同 Property 28 的「管道前后对照 > 冻结上游快照」）。并配 `test_patch_actually_takes_effect` 防「patch 失效后 stale 断言变空转」。

2. **🔴 残留探针的判据不能用「变异字样是否出现」** —— 首版按此写，对 M7 产生**假阳性**：`new_prov[key] = value` 是 `_apply_row_filter` 里**合法的 `else` 分支**（无 `:` 的键原样保留），与 M7 注入形态逐字相同。正解 = **正向断言「被变异的那一行是否回到正确形态」**（整行精确匹配 + hits==1）。→ 凡「注入字样 X」的变异，X 在生产代码里可能本就有合法同形出现，残留核验必须走正向断言。

3. **🔴 `git status` 不能当残留判据**：`note_soe_listed_diff.json` / `note_template_diff.py` / `note_conversion_service.py` 三者在 HEAD 侧**本就是 ` M`**（Task 1/2 的改动尚未 commit）⇒ 只能用「与变异前 md5 逐字相同」判残留。首版探针据 `git status` 报 `RESIDUE FOUND` 是误判。

4. **🔴 广域回归的 errors 由 8 → 10，且不加 `--continue-on-collection-errors` 会整批 `Interrupted`**（前序 Notes 未记这一点）。两个新增 collection error **全属并发会话的 `formula-management-runtime-closure` 半径**，与本轮零因果（本轮只新增测试例，一个新测试文件在结构上不可能造成别的文件 collection 失败）：
   - `backend/tests/test_formula_type_runtime_status.py`（`??` 未跟踪新建）→ `ImportError: cannot import name 'NO_FORMULAS_KIND' from 'app.services.formula_runtime.coordinator'`（测试先落盘、生产符号未落 / 或被回退，属平台已登记的「并发会话把仓库写成 ImportError 而无人察觉」）
   - `backend/tests/formula_runtime/test_orchestrator_real_mutations.py`（` M`）

   回归口径 `-k "note_conversion or note_template or note_section or disclosure_note or variant_matrix or offline or consol_cross"` = **989 passed / 56 failed / 10 errors**；`989 = 927(Task 2 基线) + 62(本轮新增)`，**56 failed 与基线逐条吻合**（新增 0）。

5. **M5 的 RED 只落在 `format_diff` 上是正确的，不是覆盖不足**：`_IDENTITY_HEAD_KEYS` 给 `soe_only_sections` / `listed_only_sections` 的头部是 `("section_id", "title")`，而这两个桶的条目**只有这两个字段** ⇒ 头部已覆盖全部载荷，标识退化对它们无影响。`TestBucketIdentityIsPayloadComplete` 仍对这两个桶各留一条正向断言（改 `title`/`section_id` 必检出），保证判据不是只在一个桶上成立。

**另核实与 Task 2 记载一致（无需改动）**

- 真实 39 条 `format_diff` 的 `field_mapping` **全为 null** ⇒ Property 4 的「非空时结构确实改变」**在真实数据上无法行使**，只能靠合成 fixture。根因仍在 `compute_section_diff` 硬写 `"field_mapping": None  # Populated by P-7 auditor annotation`（设计上由人工标注产生，而平台无标注入口）—— 属 Task 2 已登记的遗留，归 Task 15 或另立。
- 四个原因码互不相同（`applied` / `no_effect` / `no_field_mapping` / `unsupported_only`），`SUPPORTED_FIELD_MAPPING_KEYS == {column_remap, row_filter}`、`value_transform` 在 `DECLARED_UNIMPLEMENTED_FIELD_MAPPING_KEYS` 内 —— 三者均由守卫交叉锁死，生产新增一个按列 id 建键的行内桶时 `test_row_bucket_list_matches_production_constant` 会打红要求守卫跟上。

**源码级断言的两条纪律（本轮沿用 + 新增）**

- 已有的 `_strip_comments` + 「原文确实含该字样」反向自检（`fd.get("section_id")`）继续有效；本轮**新增第二处**：`test_strip_comments_selfcheck_for_count_region` 断言 `convert_disclosure_notes_v2` 的注释里确实写着「无条件 `+= 1`」且剥注释后消失 —— 证明该区域的剥注释是承重的。
- 「守卫断言某个校验存在」时判据取**条件表达式的形态**而非标识符：`format_adapted_count` 的空操作守卫用 **AST** 断言（`If` 的 test 是 `adapted == note.table_data` 的 `Compare` 且体内含 `Continue`，且行号先于 `AugAssign`），故 M6 把条件改成 `if False:` 仍能打红；两个反向自检替身（无条件计数 / 守卫写在计数之后）钉死判据不是恒真。AST 另有一个附带好处 —— 注释天然不进 AST，该函数注释里的 `format_adapted_count` 字样不会污染计数。

**遗留（不阻塞，属后续 wave）**：`field_mapping` 人工标注通路仍缺（Req 1.5 生产侧只能靠单测行使）· `preview_conversion_v2` 的 `is_mock` warning 分支恒不触发（`load_diff_data` 一律返回实时结果）归 Task 15 · `value_transform` 仍未实现（已显式登记 + WARNING）。

### Wave 3 章节映射落地实录（2026-08-07，Task 8：核心）

**🔴 开工前的实证：Task 8 的主体已由上一轮中断会话落盘，而复选框仍是 `[ ]`（假红）**。
`note_conversion_service.py` 工作树侧 +741/−44（含 Task 1/2 的改动，尚未 commit），
`_map_disclosure_notes` / `_build_section_mapping_plan` / `_build_sid_backfill_index` /
`_resolve_missing_sid` / `_record_lineage` / `_rewrite_binding_id_prefix` / 8 个原因码常量
全部已在。本轮工作 = **逐项探针核实 + 修掉 2 个自身缺陷 + 零回归双证**。
（同族已登记：「tasks.md 的 `[ ]` 与 `[x]` 都不可信，接手必须逐个探针」。）

**改动 1 个文件**（`backend/app/services/note_conversion_service.py`，+774/−44 vs HEAD）

| # | 缺陷 | 形态与后果 | 修法 |
|---|---|---|---|
| 1 | **`sid_backfilled` 双计数** | 该计数器在「解析成功处」已 `+= 1`（注释明写「唯一计数点」），而 `pair is None` 分支里又 `+= 1` ⇒ 回填后被 skip 的章节被计两次，最坏情况**计数超过章节总数**，Requirement 2.8 的「回填了几条」无法据此核对 | 删掉下游那次自增，并把「唯一计数点」写进注释钉死 |
| 2 | **回填 sid 落库缺占用闸门（潜在违反 Requirement 2.6）** | `pair is None` 分支**无条件** `note.section_id = src_sid`。两条 `section_id IS NULL` 的存量行完全可能回填到同一个 sid（同 (note_section, section_title) 重复行），无脑写会产生重复 `(project_id, year, section_id)` —— 正是 Property 10 要禁的形态 | `skip()` 改 async 并内置落库：先查 `occupied`，占用则不写并计入 `sid_backfill_conflicts`；同时把落库从「只有 1 个分支做」推广到**全部 5 条 skip-after-backfill 路径**（原先 `already_target` / `target_sid_occupied` / `target_number_*` 四条都不落库，使 `sid_backfilled` 与磁盘状态不符） |

新增两个返回键（三态纪律）：`sid_backfill_persisted`（本轮不改写但已把回填结果落库的条数）
与 `sid_backfill_conflicts`（回填出的 sid 已被别的 note 占用 ⇒ 不落库）。

**返回结构实际字段（探针实测）**

```
mapped, format_adapted, skipped[], failed[], skipped_reasons{},
binding_ids_rewritten, sid_backfilled, sid_backfill_persisted,
sid_backfill_conflicts, bridged_by_alias[], pending_keys[],
archived=None, created=None, user_edits_preserved=None
```

`archived` / `created` / `user_edits_preserved` **预留为 `None` 而非 0**（= 未测量，
与「已测量为零」严格区分），键名冻结在 `MAP_NOTES_PENDING_KEYS`，语义由 Task 9 填充。
源侧独有章节本轮**不静默丢弃**，如实进 `skipped`（原因码 `source_only_not_archived`）。

**`binding_id` 处置（需求 2.7）= 同步改前缀 + lineage 双写**

`_rewrite_binding_id_prefix` **递归**遍历整个 `table_data`（实测 binding 分布在
`rows` / `_tables[].rows` / `sub_table_data` 多个层级，只扫固定路径会漏），
匹配判据是 `f"{旧章节号}."` **带点号**（`ab.` 不会被 `a` 命中 —— 已用边界案例钉住），
旧章节号同时记入 `template_lineage.legacy_note_sections` 供解析回退。
改写必须**深拷贝构造新 dict 再整体赋值**（JSONB 未声明 `MutableDict`，就地改嵌套不标脏；
拿 ORM 持有的同一 dict 改完再赋值会因新旧相等而不发 UPDATE）。

**`section_id IS NULL` 处置（需求 2.8）= 两级反查，刻意不给「只按编号」兜底**

`_build_sid_backfill_index` 只建 `(section_number, section_title)` 与 `section_title`
两级索引。**不提供「只按 section_number」的兜底**是有意的：listed 项目里存在
`note_section='八'` + `section_title='财务报表主要项目注释'`（soe 口径章名）的存量行，
按编号反查 listed 模板会得到 `八、政府补助` —— 正是本 spec 要消除的「同章节号不同科目」
错位。候选多于一个时返 `sid_ambiguous`（宁缺勿造）。

**探针验证 38/38 PASS**（临时探针 `_wip_b_t8_probe.py`，已清理；用真实 diff 数据 +
真实两份模板 + 内存替身 session，替身实现 savepoint 的「异常时还原对象快照」语义）

| 组 | 覆盖 |
|---|---|
| A 映射计划 | 真实数据 `is_mock=False` / common 107 / soe_only 61 / listed_only 70 / format_diff 39；**soe→listed 与 listed→soe 各 pairs=112**（107 common + 5 别名桥接）；5 对别名双向逐条列出；**桥接中含母公司章节 = 0**（禁止匹配对生效） |
| B 端到端 | 共有章节 `section_id`+`note_section` 真被改写（`八、44`→`五、43`）· 源 sid 进 `legacy_section_ids` · 旧章节号进 `legacy_note_sections` · `conversions` 留方向 · binding_id 三层（`rows`/嵌套 `_tables`/`sub_table_data`）全部同步且**别的章节号的 binding 未被误改** · `_cell_modes` 的 `manual` 保留 · 目标 sid 被占用 → `target_sid_occupied` · 回填不出 → `sid_unresolved` 且 `section_id` 仍为 NULL · 幂等重跑 → `already_target_side` · **mapped+skipped+failed == 章节数（无静默丢弃）** |
| C 失败隔离 | 注入 flush 异常：`mapped=1 / failed=1`，失败章节状态**被 savepoint 回滚**、其余章节照常改写、`failed` 条目带 `note_id`/`error`/`phase` |
| D 反向与假成功 | listed→soe 改写生效；**零共有章节场景 `mapped=0`（存量 2 行）** = 复现「拿 `count(*)` 冒充」必红；同类型短路 |
| D2 回填撞车 | 两条 NULL 行回填到同一 sid 且占用者仍在 → `conflicts=1` / `persisted=0` / **两条记录的 `section_id` 无重复** |
| E 纯函数边界 | `_rewrite_binding_id_prefix` 5 个边界（空前缀 / 同前缀 / 无点号部分匹配 / 单命中 / list 递归） |

**🔴 探针首轮 9 条 FAIL 全是 fixture 自身缺陷不是实现缺陷**：我把「幂等样本」的
`section_id` 设成了与「待改写样本」**同一个目标 sid** ⇒ 待改写那条被正确地判为
`target_sid_occupied`（Requirement 2.6 的正确行为），却掩盖了「共有章节确实被改写」
这条断言。→ **构造占用/冲突类 fixture 时，必须让「正常路径样本」与「冲突样本」的目标
sid 互不相干**，否则正常路径断言会被冲突路径吃掉。

**验证**

- 直接相关测试 **206 passed / 0 failed**（`test_note_template_diff_integrity` 78 +
  `test_note_conversion_row_codes` + `test_note_section_matcher` +
  `test_note_conversion_v2` + `test_note_conversion_pbt`）
- `import app.main` 实跑通过（`get_diagnostics` 查不出漏 import）；三个改动/相关文件零诊断
- **零回归双证**：
  1. **精确 hunk 反向法**（`_wip_b_t8_zero.py`，已清理）—— 把本轮 3 个 hunk 反向补回改动前
     形态跑同一组，两侧 `tests=298 / failures=3 / errors=8`，**失败测试名集合差集：新增 0 /
     修好 0 / 共同失败 11**；还原后 md5 与改动后逐字一致（`16c28f64…`）。
     🔴 **有意不用 `git show HEAD:` 换文件** —— Task 1/2 的改动与 Task 8 在**同一个文件**里
     且尚未 commit，换 HEAD 版会同时回退 Task 1/2，`test_note_template_diff_integrity.py`
     会大面积打红、差异归因不到本轮（平台已登记的「波次间有依赖时 HEAD-swap 判据失效」）。
  2. **广域组比对基线** —— `-k "note_conversion or note_template or note_section or
     disclosure_note or variant_matrix or offline or consol_cross"` = **989 passed /
     56 failed / 8 errors**，`989 passed` 与 `56 failed` 与 Task 3 记录的基线**逐条吻合**。
     64 个 failed+errors 的文件分布全在 `test_disclosure_notes_hardening`(24) /
     `test_note_template_variant_matrix`(15) / `test_note_template_ar_soe_structure`(6) /
     `test_note_template_row_type`(4) / `test_disclosure_note_formula_wave3`(4) 等，
     **全库只有 3 个测试文件引用 `note_conversion_service`，那 3 个都在 206 passed 里**。
     `errors` 由基线 10 → **8** 是并发会话（`formula-management-runtime-closure` 半径）
     修好了两个 collection error，属本轮之外的改善不是回归。
- 那 11 个共同失败全在 **`test_note_template_variant_matrix.py`**（8 setup error +
  3 failure，全部 `KeyError: 'matrix'` / `assert 'matrix' in {...}` / `version '2026-1' != '1.0.0'`）
  = 该文件断言 JSON 里有 `matrix` 键而真源一直是 `accounts` 结构 ⇒ **失效测试**，
  memory 已登记为预存在基线，与本轮零因果。

**与相邻任务的边界（本轮严格未越界）**

- **Task 9**（源独有归档 / 目标独有新建 / `user_edits_preserved` 统计）：三个返回键已
  预留为 `None`，源独有章节已如实进 `skipped`；**未写任何归档/新建逻辑**。
- **Task 10**（v2 处置）：`convert_disclosure_notes_v2` **一行未动**，仍是生产零调用方；**（本段是 Task 8/9 当时的实录，已过期 —— v2 已由 Task 10 裁决为「删除不接线」并落地，code-level hits=0，21 条测试断言已迁移到生产路径测试）**
  本轮**没有**把 `_map_disclosure_notes` 的逻辑抄一份进 v2（那会造第二份真源）。
- **Task 11**（守卫 `backend/tests/test_note_conversion_section_mapping.py`）：**未创建该文件**
  （核实仍不存在）。本轮验证走临时探针，已清理（`backend/scripts/diagnose/_wip_b_t8_*`
  与 `_final_t8.log` 全部删除，`glob` 复核为空）。

**🔴 三处与 spec 记载不符 / spec 未登记的实证**

1. **`disclosure_notes` 有一条 spec 未登记的 DB 硬约束**：
   `uq_disclosure_notes_project_year_section` 是 `(project_id, year, note_section)` 上的
   **UNIQUE 索引且不带 `is_deleted` 过滤** ⇒ **软删记录同样占位**。故改写 `note_section`
   前必须查「含软删」的占用集（代码里第二条查询刻意不加 `is_deleted` 过滤），
   撞它是**可预期业务状态**（进 `skipped` + `target_note_section_occupied`）而**不是错误**
   （掉进 `failed` 会把正常状态报成故障）。
2. **`section_id IS NULL` 的规模**：spec 写「抽样 12 条里 8 条」，服务层 docstring 记录的
   实测值是 **817/1030**。两个数字量级一致，以 817/1030 为准。
3. **别名桥接使 pairs 从 107 变 112**：spec 只说 `common_sections` 107 条，但 5 对措辞差异
   在 diff 数据里落在**两侧各自的 `*_only_sections`** 里（精确标题匹配的必然结果），
   必须靠 `note_section_matcher` 的穷举配对桥接回来，否则这 5 个章节会走
   「源独有归档 + 目标独有新建空章」⇒ **丢已录数据**。桥接后 `source_only` 由 61 降到 56。

**遗留（不阻塞，属后续 wave）**

- `format_adapted` 在真实数据上恒为 0：39/39 条 `format_diff` 的 `field_mapping` 全 null
  （根因 `compute_section_diff` 硬写 `"field_mapping": None  # Populated by P-7 auditor
  annotation`，平台无标注入口）—— Task 2/3 已登记，归 Task 15 或另立。
- `_map_disclosure_notes` 与 `convert_disclosure_notes_v2` 两处并存（Task 10 收敛）；**（已过期 —— v2 已由 Task 10 删除，现仅 `_map_disclosure_notes` 一份真源）**
  在收敛前 Property 24「无孤儿转换函数」仍会红，属预期。
- 真实库端到端未跑：需求 10.6 明令**禁止**为凑验收改动真实项目的 `template_type`
  （会触发 `execute_full_chain(force=True)` 全链重算），故本轮验证只走探针 + 替身 session，
  真实库验收归 Task 19（且需用户显式授权专用测试项目）。

### Wave 3 归档与新建章节实录（2026-08-07，Task 9）

**🔴 结论：Task 9 的三条 bullet 在开工前已全部落盘，复选框 `[-]` 是滞后标记（假红）**。
本轮工作 = **逐项探针核实（31 项）+ 守卫覆盖核实 + 变异检验证明非空转 + 零回归**，
**未改动任何生产代码**（`note_conversion_service.py` md5 前后逐字相同
`90d6067529c02228e98826aa92d7d2b8`）。
（同族已登记第 N 次：「tasks.md 的 `[ ]`/`[x]`/`[-]` 都不可信，接手必须逐个探针」。）

**三条 bullet 的实现位置（探针 31/31 PASS）**

| bullet | 实现 | 关键实证 |
|---|---|---|
| 源独有章节：软删 + `archived_sections` 追加 `{section_id, archived_at, reason}` | `_map_disclosure_notes` 的 `pair is None` 分支 + `_record_lineage(archived_section_id=, archived_reason=)` | `is_deleted = True` / 顶层函数 `archive_reason(current, target)` 产出 `template_conversion_{src}_to_{tgt}` / 条目三键齐备 / `result["archived"] += 1` |
| 目标独有章节：建 `is_empty=true` / `status='draft'` 空章节 | 方法尾部 `for tgt_sid, entry in plan["target_only"]` 循环 | `note_section` 取**目标模板真实 `section_number`**（非 sid）/ 建前查 `number_owner` 占用 / `result["created"] += 1` |
| 共有章节 `manual` 单元格保留并计入 `user_edits_preserved` | 顶层 `count_manual_cells()` + 改写前后双计数 | `manual_before` 基准 → `manual_after` 累加 → 少了则 `user_edits_dropped` + ERROR 红线告警 |

`MAP_NOTES_PENDING_KEYS` 已清空 = `archived`/`created`/`user_edits_preserved` 三键
由「未测量（`None`）」转为**真实计数**（`0` 表示已测量为零），三态纪律保持。

**两条设计细节值得登记（探针顺带核出，spec 未写）**

1. **新建循环必须排在归档之后**，且**归档时绝不能从 `number_owner` 里 pop** ——
   `uq_disclosure_notes_project_year_section` 不排除软删行 ⇒ 被归档章节的章节号
   **仍占位**。实测两份模板的「源独有章节号」∩「目标独有章节号」= `七`/`五`/`十三`
   三个（两个方向都是这三个）⇒ 这三个新建必然撞刚归档的同号行，走
   `create_target_number_occupied` 进 `skipped`（可预期业务状态，不是 `failed`）。
2. **`count_manual_cells` 必须做「顶层 `rows` 是 `_tables[0].rows` 镜像」的跳过**，
   否则 manual 数虚增一倍（真实库实测两者同时存在的 392 个章节 **392/392 逐字节相同**）。
   跳过是**数据驱动**（仅当实测相等才跳），不假设镜像一定成立。

**守卫已由 Task 10 交付，本任务不新建文件**（Task 11 拥有
`test_note_conversion_section_mapping.py`，实测仍不存在，本轮**未创建**）：
`backend/tests/services/test_note_conversion_section_mapping_production.py`
（935 行 / **26 例**）已含 Task 9 的全部断言 —— `TestArchive`（2 例）/
`TestCreate`（2 例）/ `TestManualCellPBT` + `test_manual_cells_are_counted_and_preserved` /
`test_no_pending_keys_remain` / `test_result_has_five_categories` /
`test_reverse_direction_swaps_archive_and_create`。⇒ **Requirements 2.3 / 2.4 / 2.5
已被该文件覆盖**，无需在本任务另建守卫。

**变异检验 7/7 全 RED**（判据 = 失败测试名差集；`.bak` 落磁盘 + `try/finally` 无条件
写回 + md5 核验；post-restore rc=0 / 0 fails）

| 变异 | 对应 bullet | 新增失败 |
|---|---|---|
| M1 归档不软删（`is_deleted = True` → `False`） | 1 | +3 |
| M2 归档不写 lineage（`archived_section_id=` → `_x=`） | 1 | +2 |
| M3 新建 `note_section` 写 sid（复现历史 v2 缺陷形态） | 2 | +2 |
| M4 新建不置 `is_empty` | 2 | +2 |
| M5 新建 `status` 非 `draft` | 2 | +2 |
| M6 `user_edits_preserved` 不累加 | 3 | +3 |
| M7 `count_manual_cells` 恒返 0 | 3 | +3 |

**验证**

- Task 9 守卫 `test_note_conversion_section_mapping_production.py` **26 passed / 0 failed**
- 本 spec 全量守卫（6 文件）**345 passed / 0 failed**
  （`..._section_mapping_production` 26 + `test_note_conversion_v2_removal` 52 +
  `test_note_conversion_row_codes` + `test_note_section_matcher` +
  `test_note_template_diff_integrity` 78 + `test_variant_matrix_null_audit`）
- **零回归**：`-k "note_conversion or note_template or note_section or disclosure_note
  or variant_matrix or offline or consol_cross"` = **860 passed / 55 failed / 8 errors**，
  与 Task 8 记录基线一致（本轮零生产改动，结构上不可能造成回归；55 failed 全在
  `test_disclosure_notes_hardening`(19) / `test_note_template_variant_matrix` /
  `test_note_bold_marker_hygiene` 等预存在红文件上）。
  🔴 **`backend/tests/services/test_note_conversion_v2.py` 已被 Task 10 删除**
  （connected: v2 两方法已删 + 断言迁移），照旧 spec 里的路径清单跑 pytest 会得
  `ERROR: file or directory not found` ⇒ 后续任务的回归口径须用
  `test_note_conversion_section_mapping_production.py` 替代它。

**遗留（不阻塞，归后续任务）**

- Task 11 的守卫文件 `backend/tests/test_note_conversion_section_mapping.py` 仍不存在
  （Property 5~10 / 16~19 / 24~26 / 35 / 36 的**结构性**断言 —— 如「无孤儿转换函数」
  「零共有章节返回 mapped=0」—— 部分已由 production 守卫覆盖，Task 11 应先核实
  重叠面再决定新增哪些，勿重造一份同语义判据）。
- `format_adapted` 在真实数据上恒 0（39/39 条 `field_mapping` 全 null，根因
  `compute_section_diff` 硬写 `"field_mapping": None  # Populated by P-7 auditor annotation`，
  平台无标注入口）—— Task 2/3 已登记。
- 真实库端到端未跑（需求 10.6 禁止为凑验收改真实项目 `template_type`），归 Task 19。

---

### Wave 3 v2 处置收口实录（2026-08-07，Task 10）

**裁决 = 删除不接线**，五条依据（全部实测，非按记载推断）：

1. **生产路径已完整实现且严格强于 v2** —— Task 8/9 落地后 `_map_disclosure_notes`
   具备五项 v2 完全没有的能力：别名桥接（`SECTION_TITLE_ALIASES`）／`binding_id`
   前缀重写（446 条带 binding 的公式绑定）／`section_id IS NULL` 回填（存量大面积
   为 NULL）／章节号占用检查（撞号进 `skipped` 而非覆盖）／逐章 savepoint 隔离。
2. **v2 生产零调用方** —— 删除前 `Called by` 11 处全是测试（平台已登记的「未完成的
   重构」缺陷模式）。
3. **v2 自身三缺陷已在生产路径修好** —— `format_diff` 无 `section_id` 键（v2 读
   `fd.get("section_id")` 恒 None ⇒ `format_adapted_count` 恒 0）／`field_mapping`
   全 null ⇒ `adapt_table_data` 空转／**共有章节只计数、根本不改 `section_id`**
   （立项要修的核心缺陷，v2 恰恰没修）。
4. **接线必造第二份真源** —— 同一映射语义两处实现，改一处另一处不动，属平台明令
   禁止的双真源形态。
5. **Requirement 6.3 的约束已满足** —— 21 条测试断言逐条迁移（见下表），不是直接删测试。

**落地面**

| 项 | 实测 |
|---|---|
| `convert_disclosure_notes_v2` / `preview_conversion_v2` | 服务文件 **code-level hits = 0**（AST 剥 docstring 后 28 个 def 均无）；唯一残留是 L896 docstring 的删除留证 |
| 服务文件体积 | 工作树 **72343 字节 / 1511 行**（HEAD 侧 27605 字节） |
| 被删测试文件 | **2 个**（`test_note_conversion_v2.py` 10 tests / 8823B + `test_note_conversion_pbt.py` 11 tests / 11438B），`git status` 两条均为 ` D` |
| 新建守卫 | `backend/tests/test_note_conversion_v2_removal.py`（3 类 / 55 例）+ `backend/tests/services/test_note_conversion_section_mapping_production.py`（7 类 / 26 例） |

**21 条断言迁移映射表**（源 → 生产路径测试；机器可校验真源 =
`test_note_conversion_v2_removal.ASSERTION_MIGRATION`，22 行覆盖 21 个 v2 测试名）

来自 `backend/tests/services/test_note_conversion_v2.py`（10 条）：

| # | v2 测试 | 迁移后 | 关系 |
|---|---|---|---|
| 1 | `test_preview_v2_returns_all_fields` | `test_preview_plan_exposes_all_buckets` | **stronger** |
| 2 | `test_preview_v2_same_type_noop` | `test_same_type_conversion_is_noop` | equivalent |
| 3 | `test_convert_v2_common_sections_preserved` | `test_common_section_data_preserved` | **stronger** |
| 4 | `test_convert_v2_soe_only_archived` | `test_source_only_sections_archived` | equivalent |
| 5 | `test_convert_v2_listed_only_created` | `test_target_only_sections_created` | equivalent |
| 6 | `test_convert_v2_listed_only_created` | `test_created_note_section_is_real_number_not_sid` | **stronger** |
| 7 | `test_convert_v2_format_diff_adapted` | `test_format_diff_counts_only_real_changes` | **stronger** |
| 8 | `test_convert_v2_updates_template_type` | `test_execute_conversion_updates_template_type` | equivalent |
| 9 | `test_convert_v2_same_type_noop` | `test_same_type_conversion_is_noop` | equivalent |
| 10 | `test_convert_v2_invalid_target_raises` | `test_invalid_target_type_raises` | equivalent |
| 11 | `test_preview_v2_invalid_target_raises` | `test_invalid_target_type_raises` | equivalent |

来自 `backend/tests/services/test_note_conversion_pbt.py`（11 条）：

| # | v2 测试 | 迁移后 | 关系 |
|---|---|---|---|
| 12 | `test_pbt_full_roundtrip_soe_listed_soe` | `test_full_roundtrip_preserves_manual_cells` | **stronger** |
| 13 | `test_pbt_archived_sections_have_lineage` | `test_archived_sections_have_lineage` | equivalent |
| 14 | `test_pbt_manual_cells_preserved_after_roundtrip` | `test_manual_cells_are_counted_and_preserved` | **stronger** |
| 15 | `test_pbt_locked_cells_preserved` | `test_locked_cells_preserved` | **stronger** |
| 16 | `test_pbt_empty_table_safe` | `test_empty_and_none_table_data_are_safe` | equivalent |
| 17 | `test_roundtrip_preserves_manual_value_simple` | `test_manual_value_survives_simple_rewrite` | **stronger** |
| 18 | `test_roundtrip_empty_rows_safe` | `test_empty_and_none_table_data_are_safe` | **stronger** |
| 19 | `test_roundtrip_none_table_data_safe` | `test_none_table_data_is_safe` | **stronger** |
| 20 | `test_convert_v2_no_notes_still_works` | `test_no_notes_still_creates_target_only_sections` | equivalent |
| 21 | `test_preview_v2_counts_manual_cells_correctly` | `test_manual_cells_are_counted_and_preserved` | equivalent |
| 22 | `test_convert_v2_listed_to_soe_reverses` | `test_reverse_direction_swaps_archive_and_create` | equivalent |

关系分布 **equivalent 12 / stronger 10 / obsolete_by_design 0**（21 条 v2 断言全部
找到真实承接测试，没有一条被「作废」处理）。多对一/一对多共 5 组，均已逐条读新测试
断言体确认语义真被承接（`test_convert_v2_listed_only_created` 一分为二；
`test_invalid_target_type_raises` 等 4 个承接两条 v2 断言）。

**🔴 10 条被诚实加强的原因**（旧版锁定的是缺陷行为或压根没测生产代码）：

- **6 条原 PBT/roundtrip 测试实为 `copy.deepcopy` 自比** —— 被测对象是标准库而非
  生产代码（v2 对共有章节不动 `table_data`，故它们恒绿）。迁移版改为真调
  `_map_disclosure_notes`。
- **`test_convert_v2_listed_only_created`（→ #6）** 断言 `note_section == sid`，
  那是 **v2 的缺陷形态**（章节号列写成 slug，界面与 Word 导出都读它）。迁移版反向
  断言 `note_section != section_id` 且取目标模板真实 `section_number`。
- **`test_convert_v2_common_sections_preserved`（→ #3）** 只数 `common_count`，
  而 v2 **从不改写 `section_id`**。迁移版断言 sid/章节号真被改成目标侧取值。
- **`test_convert_v2_format_diff_adapted`（→ #7）** 靠 mock 造「改了」的假象；
  迁移版走 `report.changed` 事实判据，空操作不得计数。

反向不变量：生产测试 26 个用例「要么被迁移表指向、要么在 `PRODUCTION_ONLY_TESTS`
登记」，实测 unclaimed = **[]**、两表重叠 = **[]**、stale = **[]**。

**本轮修掉的一处文档缺陷**：生产测试模块 docstring 里那份导读映射表引用了 **10 个
重命名前的旧测试名**（`test_roundtrip_keeps_manual_values` /
`test_manual_cells_counted` / `test_same_type_returns_zeroed_result` 等，磁盘上
早已不存在），而 `ASSERTION_MIGRATION` 常量是按磁盘 AST 校对过的、指向真实用例。
属「基线按预期而非实测写」的同族缺陷 ⇒ 按磁盘重写 docstring + 新增守卫
`test_production_docstring_mapping_table_is_not_stale`（**判据只扫 reST 表格块**，
避免把散文里引述的 v2 旧名与交叉引用的守卫用例名误判成 stale）。

**变异检验（判据 = 失败测试名差集，三态 RED / GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷）**

基线 `162 passed / 0 failed`（三文件合跑）。锚点全部行级唯一（`hits == 1`，
`hits != 1` 即报 ANCHOR-MISS 而非静默跳过）；禁跨行锚点（CRLF 工作树必 MISS）；
`.bak` 落磁盘 + `try/finally` 无条件写回；残留核验用**正向断言**（被变异那一行是否
回到正确形态 + 整行精确匹配 + `hits == 1`），不用「变异字样是否出现」。

| # | 语义 | 锚点 | 新增失败 | 代表打红项 | 判定 |
|---|---|---|---|---|---|
| M1 | v2 符号被重新加回生产代码 | `class NoteConversionService:` @L287 | **+3** | `test_no_definition_or_call_form_anywhere[convert_disclosure_notes_v2]` / `test_symbol_not_defined_in_service` | **RED** |
| M2 | `format_adapted` 空操作守卫被移除（改回无条件 `+= 1`） | `if report.changed:` @L1164 | **+3** | `test_empty_field_mapping_does_not_count` / `test_increment_is_wrapped_by_changed_guard` / `test_noop_writeback_is_guarded_and_logged` | **RED** |
| M3 | `_map_disclosure_notes` 被改名 | `async def _map_disclosure_notes` @L832 | **+33** | 26 例迁移断言全红 + `test_scan_surface_is_non_empty` + diff_integrity 8 例 | **RED** |
| M4 | 新建章节把 `note_section` 写成 sid（复现 v2 缺陷形态） | `note_section=new_number,` @L1268 | **+1** | `test_created_note_section_is_real_number_not_sid` | **RED** |

4/4 全部 RED；四次还原后 md5 与变异前逐字相同、正确形态行 `hits == 1`。
🔴 残留判据**不能用 `git status`**（该服务文件在 HEAD 侧本就是 ` M`）⇒ 只能用
「与变异前 md5 逐字相同」。

**零回归**

- 本 spec 全部守卫（6 文件）**348 passed / 0 failed**
  （`test_note_conversion_v2_removal` 55 + `..._section_mapping_production` 26 +
  `test_note_template_diff_integrity` + `test_note_conversion_row_codes` +
  `test_note_section_matcher` + `test_variant_matrix_null_audit`）
- 广域组（仓库根 + `--continue-on-collection-errors`）
  `-k "note_conversion or note_template or note_section or disclosure_note or
  variant_matrix or offline or consol_cross"` = **1052 passed / 56 failed / 8 errors /
  2 skipped**（35777 deselected）
- **失败归属逐条判定 = 预存在 55~56 条 + 并发会话，本轮造成 0 条**。判据三条组合
  （禁 `git stash`、禁 HEAD-swap —— 该服务文件含 Task 1/2/8/9 未提交改动）：
  ① 9 个失败文件 `git status` **全部 CLEAN** ② 逐个扫「是否引用本轮改动符号
  （`ASSERTION_MIGRATION` / `DOCSTRING_ONLY_MENTIONS` / 两个新守卫测试名）或 import
  本轮改动模块」⇒ 命中数 **全为 0** ③ 失败簇的真实依赖是三份 note 模板 JSON 与
  `variant_matrix`（均 CLEAN），根因是并发 spec 在改模板数据。
  分布：`test_disclosure_notes_hardening` 25 / `test_note_template_variant_matrix`
  3 failed + 8 errors（import 期读 JSON 构造 parametrize）/
  `test_note_template_ar_soe_structure` 6 / `test_disclosure_note_formula_wave3` 4 /
  `test_note_template_row_type` 4 / `test_note_bold_marker_hygiene` 2 /
  `test_note_template_mode` 2 / `test_offline_roundtrip_uat` 1 /
  `test_disclosure_note_hardening` 1。
  🔴 与 Task 9 记录的「860 passed / 55 failed」相比 passed 数不同，是 `-k` 命中集合
  随并发会话新增测试文件而变（deselected 35777），不是回归；failed 集合的**文件构成**
  一致。

**Property 24 的口径实证（交接 Task 11）**

- `_map_report_rows` 与 `_map_disclosure_notes` 的 **`external_non_test_callers`
  均为 `[]`**，只有 `self_calls = 1`（由同类内 `execute_conversion` 调用）。
  ⇒ memory 记的「v2 删除后 Property 24 自动转绿」**不成立**（那条推断假设判据是
  「必须有服务文件之外的调用方」）。
- 守卫 `test_method_has_non_test_caller` 当前为**绿**，因其判据是「`.<method>(`
  在任一非测试文件里出现」且扫描面**含服务文件自身** ⇒ 同类内 self-call 被计入。
  已核实：该口径是**正确**的 —— `_map_*` 是私有方法，被公开入口 `execute_conversion`
  调用是正常设计，不是孤儿；而 `execute_conversion` / `preview_conversion` 各有
  真实外部调用方（`routers/note_conversion.py` + `services/event_handlers/_impl.py` /
  `routers/note_conversion.py` + `routers/standard_conversion.py`）⇒ 整条链有生产消费方。
- 本轮把这一口径**如实登记进守卫**：新增
  `test_map_methods_are_called_by_public_entry`（把「`_map_*` 的调用点必须落在
  `execute_conversion` 内」钉死）+ `test_external_caller_baseline_is_registered`
  （登记 `external=[]` 这一实证，判据若被改严即打红），并在
  `TestNoOrphanConversionFunctions` 的 docstring 里写明口径。
- **未改 design.md 的 Property 24 措辞本身**（那属 Task 11 裁决范围），只在其正文
  下追加了实证与「不得改成『必须有服务文件之外的调用方』」的告警。
  ⇒ **交接 Task 11**：若要收紧 Property 24，须先处置「私有子步骤如何表达」这一
  口径问题，否则会把全部 `_map_*` 误判成孤儿。

**三处与 memory/spec 记载不符的实证**

| 记载 | 实测 | 影响 |
|---|---|---|
| 被删的 v2 测试文件 **1 个** | **2 个**（`test_note_conversion_v2.py` 10 tests + `test_note_conversion_pbt.py` 11 tests），`git status` 两条均 ` D` | 迁移表必须覆盖 **21** 条而非 10 条（已覆盖，双向锁死） |
| 服务文件字节数（旧记 73722 → 62236） | 工作树 **72343 字节 / 1511 行**（HEAD 27605） | 字节数类基线一律现场实测，勿引用旧记 |
| v2 删除后 Property 24 **自动转绿** | **不成立** —— `external_non_test_callers` 删除前后都是 `[]`；守卫为绿是因为判据把 self-call 计入 | 见上一节，已登记口径并交接 Task 11 |

**spec 文档实际改动（8 处，全部 `str_replace` 传完整旧文本，禁 `index()` 算边界）**

- `design.md` 4 处：Overview 主线 2（「收进生产路径」→ 明确已删 + 加裁决 banner）／
  核心设计取舍「v2 优先接线而非删除」→ **「v2 删除而非接线」**（直接矛盾，必改）／
  架构图 Step4「收编 v2 逻辑」→「生产路径自身实现」／Property 24·25·26 三条正文
  （标明 25 为**接线分支不生效**、26 为**删除分支生效**并附迁移表位置）
- `requirements.md` 3 处：L39「是孤儿」段（加已删事实 + 三缺陷已在生产路径修好）／
  需求 6.1 二选一（**保留 AC 原文**，追加「实际裁决 = 删除」及理由）／Glossary
  「v2 实现」条目（标注已删除 + 指向 `_map_disclosure_notes`）
- `tasks.md` 5 处：Task 10 正文（标题与四个 bullet 改为删除口径 + 勾 `[x]`）／
  事实基线段（加「已删除」与 code-level hits=0）／依赖图注「建议选接线」→
  **已裁决删除**（直接矛盾，必改）／Task 8·9 实录两处过期表述各加一句「已由
  Task 10 删除」（**不重写实录内容**）
- 🔴 **`applicable_standard_v2` 三处未动** —— 它是列名不是 v2 实现（三份文档各
  1 处，改完复核 hits 仍各为 1）
- 结构性核验：`design.md` `### Property` **37 条无缺号无重复** + `**Validates:`
  **37** 条 + `## ` 7 个标题齐全；`tasks.md` waves JSON 可解析、复选框
  `{x:11, -:1, ~:7}`；`get_diagnostics` 三件套 **全绿**
- 🔴 **过程中自己踩了一次「脚本按行号批量改 .md」的坑**：探针脚本对同两行重复追加
  17 次注解（75722 字节 / L606 长 816 字符），已修复回 73584 字节、716 行不变、
  两行各 1 处注解。教训与平台已登记的「禁用 `index()` 算边界」同族 ⇒ **改 .md 一律
  `str_replace`，脚本只用于只读定位与结构核验**。

**与 Task 11 的边界**

- 本任务**不**创建 `backend/tests/test_note_conversion_section_mapping.py`（Task 11
  的文件，已复核仍不存在）。
- Task 11 落地前须先核实与 `test_note_conversion_section_mapping_production.py`
  （26 例）及 `test_note_conversion_v2_removal.py`（55 例）的重叠面，勿重造同语义判据。
- 移交给 Task 11 的两项裁决：① Property 24 措辞是否收紧（口径问题见上）
  ② Property 25 是否整条撤回（当前标注为「接线分支不生效」保留作记录）。

**遗留（不阻塞）**

- `format_adapted` 在真实数据上恒 0（39/39 条 `field_mapping` 全 null）—— Task 2/3 已登记。
- 真实库端到端未跑（需求 10.6 禁止为凑验收改真实项目 `template_type`），归 Task 19。
- 本 spec 全部改动**未 commit**（工作树混着并发会话改动，须按路径显式挑选，
  禁 `git add -A`）。

### 🔴 Task 17 冲突取证（2026-08-08，本会话未交付，已停手）

**结论：`backend/tests/test_note_conversion_preview_rollback.py` 正被另一个并发会话实时写入**，本会话按 Task 17 写的守卫（36 例 / 44352 字符）已被整文件覆盖一次。按平台铁律「同一文件不与并发会话并行编辑；发现时先取证再恢复，禁直接覆盖」，**未写回**（覆盖对方在写内容属难以回退的共享状态破坏）。

**冲突实证（两条独立证据）**：Kiro local history（`%APPDATA%\Kiro\User\History\-fa382ca\entries.json`）显示 17:18~17:23 是本会话三次写入（14377→29091→**44352** 字符），**17:24:07 被并发会话整文件覆盖**（14456 B），随后 17:24:38→17:29:49 它连续追加到 **72350 B**，17:34 又重写为 22497 B（仍在活跃）。40 秒双采样：**只有该文件 md5 变化**，其余 5 个相关文件（Task 10/11 三个守卫 + `note_conversion_service.py` + 本文件）全部未变。两版连替身类名都撞到 `ConversionFakeSession` ⇒ 同一条「复用 Task 10/11 替身」路线。

**两版覆盖面对比**（`_wip_t17_compare.txt`）：并发版 57 例 / 12 类，**含 Property 33 完整覆盖**（`TestProperty33_AutoTriggerRecordsSnapshotId` 10 例 + `TestAutoTriggerLeavesSnapshot` 8 例）+ 反向往返 + 两轮往返稳定性；本会话版 36 例，**完全没有 Property 33**，但有 8 处并发版当前没有的判据：`ROLLBACK_SKIP_NOTE_MISSING` / `ROLLBACK_FAIL_NUMBER_BLOCKED`（章节号被占 ⇒ **整章不动**，禁半成品回退）/ `format_adapted_not_reversible` / `count_manual_cells` 往返不减少（平台红线）/ 快照过期与 `snapshot_before` 为空两条 error 路径 / 回填 sid 退回 `None` / leftover ERROR 分支（`_LeftoverFakeSession` 行使第 3 层零写入核验）/ `details` 可追溯键 + `user_edits_dropped == 0`。⇒ **两版互补不重复**；建议以并发版为基底，把这 8 处作加法补齐。

**顺带实证的 spec 记载修正（Task 17/18 实录可直接引用）**

| spec 记载 | 实测 |
|---|---|
| `GET /note-conversion/{project_id}/{year}/preview` | 真实路由 **`GET /api/projects/{project_id}/notes/conversion/{year}/preview?target_type=`**（挂既有 router 前缀，spec 是简写） |
| —— | 服务方法是 **`preview_note_conversion`**；`preview_conversion` 是历史「报表行次」口径入口（返回 `ConversionPreview` 对象），两者并存**不可混用** |
| Task 10 实录记服务文件 72343 B | 现为 **115614 B / 2322 行**（Task 15/16 大幅扩写），该数字已过期 |
| —— | `SNAPSHOT_FORMAT_VERSION = 2`；回滚链 `rollback_conversion(project_id, year)` → `_rollback_section_state(project_id, year, snapshot_data, forward=None)`，配 `snapshot_note_state` / `_created_section_is_untouched` / `_restore_note_from_snapshot` |
| —— | **替身路由判据（已实测编译 SQL）**：`_map_disclosure_notes` 的存量查询带 `is_deleted = false`，而 `_create_snapshot` 与 `_rollback_section_state` 的查询**不带**该过滤 ⇒ 替身必须区分「全量含软删」与「仅未软删」两种返回，否则「归档进快照 / 回滚复原归档」两条路径**结构性测不到**。Task 10 的 `FakeSession` 只实现后者，另缺 `savepoint.rollback()` / `new`·`dirty`·`deleted` / `delete()` / Project 与 ChainExecution 表路由 —— 这四项是 Task 17 必须子类扩展的能力 |
| Property 33 待实现 | **已在生产落地**：`event_handlers/_impl.py` 的 `_on_standard_changed_notes` 成功分支 `logger.info(... snapshot_id=%s ..., result.get("snapshot_id"))`，失败分支从异常读 `conversion_snapshot_id` / `conversion_committed`（由 `execute_conversion` 的 `setattr` 挂上） |

**遗留产物**（`backend/scripts/diagnose/_wip_t17_*`，未清，供接手/复核）：`mine_recovered.py.txt`（**本会话完整版本，8 处 delta 的来源**）· `compare.txt`（两版用例清单逐条对比）· `conflict.txt`（40 秒双采样）· `history.txt`（local history 时间线）· `probe.txt`（服务方法真实签名全表）· `sql.txt`（8 种语句编译文本 + 两个模型的列清单与 NOT NULL 无默认列）。**本轮未改动任何生产代码**（`note_conversion_service.py` md5 全程 `0dcc66d37770`）。

### Wave 5 预览回滚守卫实录（2026-08-08，Task 17 收口）

**上一轮「冲突取证」的阻塞已解除**：并发会话把 `test_note_conversion_preview_rollback.py`
写到 68281 B / **51 例全绿** 并跑完 11 条变异（10 RED + **M2 ANCHOR-MISS**），随后停笔
（该文件 mtime 17:37:59，本轮开工 17:49 起两次 75 秒双采样 + 20 分钟静置均 QUIET）。
按平台铁律「先取证再动手、禁覆盖并发会话产出」，本轮**不重写该文件**，只做**加法式补齐**
（`fs_append` + 仅在自己新增段内 `str_replace`）—— 这样最坏情况是我的增量被覆盖，
而对方的 51 例一个字都不会丢。

**本轮交付**：51 → **62 例**（新增 11 例 / 2 个类），变异检验 **22/22 全 RED**，
生产代码**逐字节未动**。

| 项 | 结果 |
|---|---|
| 目标守卫 | `backend/tests/test_note_conversion_preview_rollback.py` **92694 B / 62 例** |
| 新增类 | `TestProperty31_PreviewTraceabilityAndLeftoverGuard`(4) / `TestProperty32_RollbackFailClosedPaths`(7) |
| 变异检验 | **22 条全 RED**（原 11 条含 M2 修正 + 新增 11 条），0 GREEN / 0 ANCHOR-MISS |
| 生产 md5 | `note_conversion_service.py` `0dcc66d37770` / `event_handlers/_impl.py` `23c632bce87e`，**与开工时逐字相同** |
| 邻居守卫 md5 | Task 10/11 三个守卫文件亦逐字未动 |

#### 补齐的 9 处语义缺口（判据 = code-level 命中数：生产有该符号而守卫 0 命中）

| 生产符号 / 分支 | service | guard(补齐前) | 新增判据 |
|---|---|---|---|
| `ROLLBACK_SKIP_NOTE_MISSING` | 2 | **0** | `test_missing_snapshot_note_is_reported_not_ignored` |
| `ROLLBACK_FAIL_NUMBER_BLOCKED` | 2 | **0** | `test_blocked_note_section_is_not_half_rolled_back`（**整章不动**，禁半成品） |
| `format_adapted_not_reversible` | 1 | **0** | `test_format_adapted_is_declared_irreversible` |
| `count_manual_cells` | 5 | **0** | `test_manual_cells_never_decrease_across_roundtrip` |
| `user_edits_dropped`（恒 0 红线） | 8 | **0** | 同上 + `test_preview_details_carry_traceability` |
| 快照过期 / `snapshot_before` 为空 | 2 | **0** | `test_expired_snapshot_reports_error_and_changes_nothing` / `test_empty_snapshot_reports_error_and_changes_nothing` |
| 回填出来的 sid 退回 `None` | 14 | **0** | `test_backfilled_sid_returns_to_null_after_rollback` |
| 预览第 3 层 leftover 核验**真会触发** | 1 | **0** | `test_leftover_guard_fires_and_rolls_back_whole_session` |
| `details` 可追溯键 / `forbidden_hits` 可读 | — | 部分 | `test_preview_details_carry_traceability` / `test_forbidden_hits_are_human_readable` / `test_details_counts_are_derived_from_the_lists` |

🔴 **上一轮「8 处 delta」清单有 5 条其实已被覆盖**（`ROLLBACK_SKIP_CREATED_HAS_CONTENT`
guard=2 / `ROLLBACK_UNRESTORED_FIELDS` 2 / `ROLLBACK_REASON_LEGACY_SNAPSHOT` 2 /
`snapshot_before` 2 / `SNAPSHOT_FORMAT_VERSION` 3）—— 那份清单是按**测试名**求差集得出的
（`<== 并发版没有` 全是名字不同），而两版对同一语义常用不同命名。**判「语义是否真缺」必须
按生产符号的 code-level 命中数，不能按测试名比对**（同族：memory 已记的「符号级匹配只产生
假阴性」）。

#### 三处与前序记载不符的实证

1. **M2 ANCHOR-MISS 的真因不是 CRLF，是锚点缩进写错** —— 上一轮实录归因「跨行锚点在 CRLF
   工作树必 MISS」，但同一脚本的 M4/M5/M7 都是跨行锚点且 hits=1 ⇒ 该文件是 **LF**。真因是
   `snapshot_note_state` 是**模块级函数**、其 dict 项缩进 **8 空格**，而脚本写了 **12 空格**
   （照抄了类内方法的缩进）。修正缩进后 **M2f = RED**（打红 6 例）。⇒ **ANCHOR-MISS 的第一
   嫌疑是缩进层级而非行尾**，判前先看被锚定的代码在模块级还是类内。
2. **`skipped` / `failed` 在真实预览场景实测均为空** ⇒ 「计数与明细自洽」在该数据下恒真。
   这让我自己写的判据出现一处 **GREEN（守卫缺陷）**，详见下节。
3. **上一轮记的服务文件 115614 B / 2322 行仍准确**（本轮全程未改），但 Task 10 实录里的
   72343 B 已过期两代 —— 字节数类基线一律现场实测。

#### 🔴 变异检验抓出我自己一处守卫缺陷（GREEN → 修好 → RED）

首轮 22 条里 **N2 判 GREEN**：把 `"skipped_count": len(skipped)` 改成写死 `0`，
`test_preview_details_carry_traceability` 竟然**不红** —— 因为真实场景 `skipped == []`，
`0 == len([])` 恒成立，那条「自洽」断言**对写死计数完全不敏感**。

修法 = 新增 `test_details_counts_are_derived_from_the_lists`：用**非空明细**直调投影
**纯函数** `_build_note_preview_payload`，让计数与明细脱钩即打红（复跑 N2 = RED）。
原断言保留但加注说明它在当前数据下恒真、真判据在新测试里。

⇒ **一条可推广的判据纪律**：凡「计数 == len(明细)」这类自洽断言，若明细在真实场景可能为空，
它就是**空转**；必须另配一条用非空替身数据直调纯函数的断言。这也是「每写完守卫必须真做一次
变异检验」的又一次兑现 —— 该缺陷四层验证（62 例全绿 / `get_diagnostics` 零诊断 / 回归全绿 /
广域零新增）**全部查不出**。

#### 变异检验汇总（判据 = 失败测试名差集，三态 RED / GREEN=守卫缺陷 / ANCHOR-MISS=脚本缺陷）

脚本 `backend/scripts/diagnose/_wip_t17b_mutate.py`（备份落 `.t17bbak` 磁盘 + `try/finally`
按字节写回 + md5 核验 + 锚点 `hits != 1` 即报 ANCHOR-MISS；`--check` 可只验锚点唯一性）。
baseline **62 passed / fails=[]**，POST-RESTORE **62 passed / fails=[]**，两个生产文件 md5 还原核验 True。

| # | 语义 | 新增失败 | 判定 |
|---|---|---|---|
| M1 | 预览漏 `await sp.rollback()` | 2 | RED |
| **M2f** | 快照不再存 `note_section` | **6** | **RED**（原 ANCHOR-MISS 已解） |
| M3 | 快照不存 `template_lineage` | 3 | RED |
| M4 | 回滚不逆向改 `binding_id` 前缀 | 4 | RED |
| M5 | 旧格式快照不再 fail-closed | 1 | RED |
| M6 | 新建章节已有内容仍物理删除 | 1 | RED |
| M7 | 快照过滤掉软删记录 | 1 | RED |
| M8 | handler 丢弃 `execute_conversion` 返回值 | 3 | RED |
| M9 | 失败分支不再从异常取 `snapshot_id` | 2 | RED |
| M10 | `execute_conversion` 不再把 `snapshot_id` 挂异常 | 2 | RED |
| M11 | 预览响应丢掉 `forbidden_hits` 键 | 2 | RED |
| N1 | `details` 丢掉 `skipped` 明细 | 1 | RED |
| N2 | `skipped_count` 写死（计数不由明细派生） | 1 | RED（**首轮 GREEN，补判据后转 RED**） |
| N3 | `forbidden_hits` 不再人可读（原始 dict 外抛） | 1 | RED |
| N4 | `count_manual_cells` 不识别 `_cell_modes` | 2 | RED |
| N5 | 快照章节已不存在时不再登记 | 1 | RED |
| N6 | 章节号被占仍强行回退（半成品） | 1 | RED |
| N7 | 不再声明格式适配不可逆 | 1 | RED |
| N8 | 过期快照不再拒绝 | 1 | RED |
| N9 | 空快照被兜底成默认值 | 1 | RED |
| N10 | 回填出来的 sid 不退回 `None` | 1 | RED |
| N11 | 预览 leftover 核验失效 | 1 | RED |

#### 实测锚点（本轮复算，后续会话可直接引用）

* 预览（soe→listed，`build_notes` 场景）：`mapped=2` / `archived=1` / **`created=65`** /
  `user_edits_preserved=1` / **`forbidden_hits=1`**（合并章↔母公司章那一对，真实数据命中）
* `details`：`binding_ids_rewritten=3` / `bridged_by_alias=5` / `forbidden_pairs=1` /
  **`skipped=0`** / `failed=0` / `format_adapted=0` / `sid_backfilled=0` / `user_edits_dropped=0`
* `_build_section_mapping_plan(soe→listed)`：`pairs=112` / `source_only=56` /
  `target_only=65` / `bridged=5`（与 Task 11 实录一致）
* `format_adapted` 在真实数据上**恒 0**（`field_mapping` 39/39 全 null）⇒ 不可逆分支
  只能靠改写快照行 `steps.conversion_forward.format_adapted` 才能触达，测试已注明

#### 回归

| 范围 | 结果 |
|---|---|
| 目标守卫单跑 | **62 passed / 0 failed** |
| 本 spec 8 个守卫文件合跑 | **454 passed / 0 failed** |
| 广域 `-k "note_conversion or note_template or note_section or disclosure_note or variant_matrix or offline or consol_cross"`（`--continue-on-collection-errors`） | **1158 passed / 56 failed / 8 errors / 2 skipped**（35875 deselected） |

**广域失败逐条判定 = 本轮造成 0 条**，三条判据：① 失败的 **9 个文件与 Task 10 实录的 9 个
文件、逐文件计数完全一致**（`test_disclosure_notes_hardening` / `test_note_template_ar_soe_structure` 6 /
`test_note_template_row_type` 4 / `test_disclosure_note_formula_wave3` 4 /
`test_note_template_variant_matrix` 3 / `test_note_template_mode` 2 /
`test_note_bold_marker_hygiene` 2 / `test_offline_roundtrip_uat` 1 / `test_disclosure_note_hardening` 1）
② 本轮**只改了一个测试文件**，两个生产文件 md5 与开工时逐字节相同 ⇒ 结构上不可能影响别处
③ `preview_rollback` 相关失败 **= 0**。passed 由 Task 10 实录的 1052 增至 1158（+106 = Task 11 的
40 + 本文件的 62 + 零星），**failed / errors 计数一字未变**。

#### 🔴 两条本轮踩到的操作教训

1. **诊断产物命名必须带会话前缀** —— 我用了 `_wip_t17_state.txt` / `_wip_t17_tail.txt`，
   与并发会话的同名产物**撞名并覆盖了它的两份**（纯诊断文件、无代码影响，但会误导后续会话）。
   本轮其余产物一律改用 `_wip_t17b_*`。**并发会话的 `_wip_*` 一律按 mtime 判**：分钟级 = 正在用，
   勿碰。
2. **长命令仍会打崩 PSReadLine**（本轮两次，`SetCursorPosition ... top 为负` 后持续吐异常）。
   命令实际都执行成功了，判成败一律读脚本写盘的输出文件，别看控制台。归纳脚本
   `_wip_t17b_sum.py`（把 pytest 输出归纳成短报告）可直接复用。

#### 本轮产物

| 文件 | 性质 |
|---|---|
| `backend/tests/test_note_conversion_preview_rollback.py` | **唯一被改的文件**（加法式，51→62 例） |
| `backend/scripts/diagnose/_wip_t17b_mutate.py` + `.txt` | 变异检验脚本与 22 条判定报告（含 `--check` 锚点自检） |
| `backend/scripts/diagnose/_wip_t17b_verify.py` + `.txt` | 「生产逐字节未动」核验 |
| `backend/scripts/diagnose/_wip_t17b_gap.py` + `.txt` | 语义缺口的 code-level 命中数比对 |
| `backend/scripts/diagnose/_wip_t17b_counts.py` + `.txt` | 预览 details 实测计数（实录锚点来源） |
| `backend/scripts/diagnose/_wip_t17b_sum.py` | pytest 输出归纳器（避开 PSReadLine） |

**遗留（不阻塞，均属既有分工）**：Property 34 零回归 characterization / CI job
`note-conversion-correctness` 归 **Task 18**（本文件届时挂进去）· 真实库验收归 **Task 19**
（需求 10.6 禁止为凑验收改真实项目 `template_type`）· 本 spec 全部改动**未 commit**
（工作树混着并发会话改动，须按路径显式挑选，禁 `git add -A`）。

### Wave 5 零回归与变异检验实录（2026-08-08，Task 18）

#### A. 零回归守卫的 5 个失败逐条定性（全部是守卫自身缺陷，生产代码零改动）

接手时 `test_note_conversion_zero_regression.py` = **5 failed / 18 passed**，收口后 **26 passed / 0 failed**（净增 3 例 = 拆分自检 1 + 替身反向自检 1 + 模块存在性自检 1）。**5 条失败里 4 条是守卫缺陷、1 条是「拿假设当基线」**，无一条是生产回归：

| # | 失败断言 | 定性 | 处置 |
|---|---|---|---|
| ① | `note_offline_import_service.py` 命中 `match_section` | **同名误命中**（不是真耦合） | 收窄判据 + 替身反向自检 |
| ② | `test_conversion_symbols_really_exist_in_production` 报 `note_conversion_service` 不存在 | 守卫缺陷：模块不按名字 import 自己 | 拆「模块名」与「成员名」两类分别自检 |
| ③ | `_extract_column_groups` 三态断言 `none > 0` | 拿假设当基线 | 按实测分布改写 |
| ④ | `is_guidance_paragraph('提示：不适用的项目请删除')` 期望 True | 拿假设当基线 | 按实测值冻结 |
| ⑤ | `fmt_amount_gt(0)` 期望 `'-'` | 拿假设当基线（与前端不同源） | 按实测值冻结 |

**① `match_section` 的定性结论 = 同名误命中，不是真耦合**（探针 `_wip_t18_scan7.py`，AST/正则双证）：

- `note_offline_import_service.py` 对 `note_section_matcher` 的 **import 数 = 0**；
- 命中来源是该模块**自己的局部函数** `match_sections`（**复数**，L338 定义 / L512 调用），裸子串 `"match_section" in src` 因子串关系被命中；
- ⇒ 「结构性零耦合」对该模块**成立**，是判据太宽，故**保留档 1 结构性判据**（不降级为行为级），只把判据收窄。

收窄后的判据 `_scan_conversion_coupling(src)` 只认三种**真耦合**形态，并把「模块名」与「成员名」分成两个集合（`_CONVERSION_MODULES` / `_CONVERSION_MEMBERS`）：

1. `from app.services.note_section_matcher import match_section`（成员进 import 清单）
2. `note_section_matcher.match_section(...)`（限定调用）
3. `from ... import match_section as ms`（别名 import，抽 `as` 前的原名）

**替身反向自检**（`test_narrow_criteria_catches_real_coupling`）钉死收窄没弱到放过真耦合：三种真耦合形态**必须**被抓到、两种误命中形态**必须**放过（同名局部复数函数 / 无 import 的裸调用）。第 3 个替身首版写成「裸 `match_section(...)` 无 import」，实测判据放过它 —— 复核后确认**该形态在 Python 里不可能触达转换侧**（要么 NameError 要么是同模块局部定义），故它是误命中形态而非真耦合，已改为别名 import 并把裸调用移入负向断言。

**② 拆分自检**：`note_conversion_service.py` 内部不会出现字符串 `note_conversion_service`（模块不按名字 import 自己）⇒ 把模块名塞进「符号必须存在于转换侧源码」的同一个 haystack 必然假红。现分两条：成员名按源码字符串断言（`test_conversion_members_really_exist_in_production`，9 个成员全部命中）、模块名按**文件存在性**断言（`test_conversion_modules_really_exist_as_files`）。

**③④⑤ 三条 characterization 一律先跑实测再冻结**（探针实测值，`_wip_t18_scan7.txt`）：

- `_extract_column_groups` 真实分布 = **none 0 / empty 506 / grouped 159**。`None` 态在真实模板里**不出现**（所有带 columns 的表都显式表态），故断言改为「`empty` 与 `grouped` 两态都必须非零 + 三态取值域仍受约束」，并在注释里写明「none=0 是当前真实分布，不要求它非零」——`None` 语义（回退前缀推断）仍由 `note_sub_table_projector` 自己的守卫覆盖。
- `is_guidance_paragraph` 的**真实判据是「整段被括号包裹」**（源码：`（）`/`()`/`【】`/`《》` 四种包裹之一 **且**含指引关键词），故 `提示：不适用的项目请删除` → **False**、`（注：不适用的项目请删除）` → **True**。原断言按「含『提示』二字即指引」写，与实现口径不符。
- `fmt_amount_gt(0)` → **`''`**（该函数 docstring 明确「空值/零值留白返回 `""`，不返 `"-"`」，R5.2 验收 8）。前端 `displayPrefs.fmtAmount(0)` → `'-'` 是**另一条链路**（受 `showZero` 偏好控制），两者不同源，已在守卫注释里写明不得混用。

#### B. 11 条变异检验三态判定表

判据 = **失败测试名差集**（`new_fails = fails_after − fails_baseline`），不看退出码；备份落磁盘 `.t18bak` + `--restore` + `try/finally` 双保险；还原用 `write_bytes`；脚本 `backend/scripts/diagnose/_wip_t18_mutate.py`，报告 `_wip_t18_mutation_report.txt`。**BASELINE = 480 passed / 0 failed**。

| # | 变异 | 判定 | new_fails | 代表性打红用例 |
|---|---|---|---|---|
| M1 | `is_mock` 改回 true | **RED** | 1 | `test_note_template_diff_integrity::TestIsMockFalse::test_stored_is_not_mock` |
| M2 | 删 `format_diff` 定位键 | **RED** | 1 | `test_note_template_diff_integrity::TestStoredMatchesLive::test_bucket_entries_equal` |
| M3 | `_map_disclosure_notes` 改回 `count(*)` | **RED** | 17 | `…section_mapping_production::TestCommonSectionRewrite::test_idempotent_rerun` 等 17 例 |
| M4 | 去掉 `template_lineage.legacy_section_ids` 追加 | **RED** | 3 | `…section_mapping::TestProperty5And6_RewriteInvariant::test_legacy_section_ids_recorded_for_every_mapped` |
| M5 | 禁止匹配对加入 `SECTION_TITLE_ALIASES` | **RED** | 4 | `test_note_section_matcher::TestForbiddenPairs::test_alias_and_forbidden_are_disjoint` |
| M6 | matcher 引入 `difflib` | **RED** | 1 | `test_note_section_matcher::TestNoSimilarityImplementation::test_no_similarity_library_imported` |
| M7 | 清空 `CROSS_VARIANT_ROW_CODE_MAP` | **RED** | 15 | `test_note_conversion_row_codes::TestSynonymTwoCodesFrozen::test_entry_has_evidence[IS-055-IS-033]` 等 |
| M8 | 让预览产生写入 | **RED** | 2 | `…preview_rollback::TestProperty31_PreviewHasNoWrites::test_preview_leaves_every_note_byte_identical` |
| M9 | 改 `note_section` 而不改 `binding_id` 前缀（P35） | **RED** | 6 | `…section_mapping_production::TestCommonSectionRewrite::test_binding_id_prefix_rewritten` |
| M10 | 对 `section_id IS NULL` 静默跳过（P36） | **RED** | 4 | `…section_mapping::TestProperty36_NullSidExplicitDisposition::test_every_null_sid_row_is_accounted_for` |
| M11 | 验收脚本里写 `Project.template_type`（P37） | **RED**（补做，见下） | 1 | `test_note_conversion_live_verifier::TestForbiddenWrites::test_no_forbidden_write_forms` |

**11 条全部 RED，无 GREEN、无 ANCHOR-MISS。** M11 曾因 Task 19 的验收脚本未交付而阻塞（当时记为 `[-]`），**Task 19 交付 `verify_note_conversion_live.py` 后已补做并判 RED**（施加前先做 dry-run 有效性自检：baseline `offenders=[]` vs 变异后 `offenders=['template_type :: 属性赋值']`，确认该变异真的改变了被测属性而非无效变异）。

**🔴 M3 首轮判 GREEN 是「无效变异」不是守卫缺陷**（本轮最值得记的一条）：首版变异改的是 L700 那行**注释** `# Requirement 4.1：实际改写的章节数（改造前是存量 count(*) 冒充）` —— 注释改了行为一点没变，守卫当然不红。定位真实计数点后（`result["mapped"] += 1` @L1999，唯一整行，hits=1）把它改成「统计全部扫描到的章节」以复现 `count(*)` 冒充，立刻 RED（17 例）。⇒ **判 GREEN 前必须先确认变异真的改变了被测属性**（memory 已记多例，本轮第 N 次兑现）。

**锚点唯一性预检**（上一轮已备，本轮全部复核 hits==1）：`legacy_section_ids` / `legacy_note_sections` / `CROSS_VARIANT_ROW_CODE_MAP` 三条在文件里分别有 5/5/4 次出现（其余在 docstring 与 `__all__`），故按**唯一整行**定位并断言 `hits == 1`：真实改写点 = L2194 `changed |= _append_unique(lineage, "legacy_section_ids", legacy_section_id)`、L2196 同款 `legacy_note_sections`、L238 `CROSS_VARIANT_ROW_CODE_MAP: Final[...] = {p.soe: p for p in _PAIRS}`。

**还原核验（md5 与开工前基线逐字节比对，全部 OK）**：

| 文件 | md5 | size |
|---|---|---|
| `note_conversion_service.py` | `0dcc66d377707685af32ed91cede72cd` | 115614 |
| `note_template_diff.py` | `05b124ed0b0bfaafc1ab8ac08484dac7` | 36220 |
| `note_section_matcher.py` | `7f19c9e120ca376e3e77ecb2b237ed20` | 9991 |
| `note_conversion_row_codes.py` | `fcb288d7f0f04d18409eb345b7116800` | 15808 |
| `note_soe_listed_diff.json` | `e9a754f989e1e236cd2eebf786211bb2` | 70229 |

残留 `.t18bak` = **0**。开工时与收尾各复算一遍，五个文件 md5 均与上一轮记录一致（未被并发会话改动）。

#### C. CI job `note-conversion-correctness`

加法式追加到 `governance-checks.yml` 末尾（`jobs` 是 map，顺序无关）。验证：`yaml.safe_load` 可解析 + 新 job 名在内 + **job 数 136 → 137**（只增不减）+ **重名 0**。

带 postgres service（照抄 `prefill-wp-prev-resolution` 形态，含迁移步骤 + `DATABASE_URL` env）—— 实测三个守卫文件连库：`test_note_conversion_row_codes.py` 与 `test_note_conversion_section_mapping.py` 读 `report_config`、`test_note_conversion_preview_rollback.py` 用 `async_session`。**13 步**，引用的 9 个测试文件逐个确认存在。

> 探针清单里曾出现一条 `MISS backend/tests/test_note_conversion_row_codes_live.py` —— 那是**我探针里的笔误**，该文件从不存在，真实守卫是 `test_note_conversion_row_codes.py`（已在 job 里正确引用）。

#### D. 本轮被实证推翻的立项/既有记载

1. **M3「守卫缺陷」判定被推翻** —— 实为无效变异（见上）。
2. **「`_extract_column_groups` 三态在真实数据里都出现」被推翻** —— `none` 态实测 **0**。
3. **「`fmt_amount_gt(0)` 返回 `-`」被推翻** —— 实为 `''`；与前端 `fmtAmount(0)→'-'` 不同源。
4. **「`is_guidance_paragraph` 按关键词判定」被推翻** —— 真实判据是「整段被括号包裹 **且** 含关键词」。
5. **两处既有 Property 注释编号偏差（如实登记，本轮不擅改）**：`test_note_section_matcher.py` 的注释标 `Property 18~21` 而 design 实为 **20~23**（Task 5 遗留，tasks.md 正文已记该错位）；`test_variant_matrix_null_audit.py` 引用了 **`Property 38`** 而 design 只有 1~37（Task 13 遗留）。两者都只是注释编号，不影响断言有效性 ⇒ 归 Task 5/13 的收尾项。

#### E. Task 18 复选框判定 = 已完成（`[x]`，M11 阻塞已解除）

四个子项**全部达成**：characterization（26 例全绿）· 变异检验 **11/11 全 RED** · 变异判据三态 · CI job `note-conversion-correctness`。

**M11 的阻塞历史（保留留痕，不删）**：M11 曾因目标文件 `backend/scripts/diagnose/verify_note_conversion_live.py` 不存在而无锚点可打（该文件属 **Task 19** 交付物），当时按「不得提前创建该脚本凑数、也不得静默跳过」的要求把 Task 18 记为 `[-]` 并逐条报告了阻塞原因。**Task 19 交付该脚本后，M11 已按原定判据补做并判 RED**：

- 变异形态 = 在脚本里注入 `project.template_type = target_type` 赋值，期望 Property 37 的源码级自禁打红；
- **施加前做了 dry-run 有效性自检**（避开已多次踩到的「无效变异伪装成守卫缺陷」）：baseline 下 `find_forbidden_writes()` 返 `offenders=[]`、注入后返 `offenders=['template_type :: 属性赋值']` ⇒ 该变异确实改变了被测属性；
- 施加后 `new_fails = 1`，首个打红用例 `test_note_conversion_live_verifier::TestForbiddenWrites::test_no_forbidden_write_forms`；
- 还原后 6 个文件 md5 与基线逐字节一致，`.t18bak` 残留 **0**。

⇒ 「11 条变异逐条 RED」这一条要求已完整兑现，Task 18 判 `[x]`。

