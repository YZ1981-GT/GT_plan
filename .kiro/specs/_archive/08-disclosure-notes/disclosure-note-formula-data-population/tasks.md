# Implementation Plan

## Overview

按「先安全网 → 派生纯函数 → 引擎最小扩展 → 生成数据 → 预设登记 → 守卫 → 灰度两态 + 真实 round-trip」推进。

全程 additive：不改 `disclosure_notes` 表结构、无 DB 迁移、不改披露内容（行标签/表名/章节号/列头）、**不新增 source 枚举**（用 `source='formula'` + `formula_kind='sum'`，见 design 决策 3/6 修订）、不改 `VALID_SOURCES` / `SOURCE_RESOLVERS` / json `valid_sources`。生成器改数据文件后**必须**跑既有 `normalize_note_bindings.py --write` 后处理。灰度 `DISCLOSURE_NOTE_FORMULA_ENABLED` 保持默认 False。

Wave 0 核实结论见 `design.md` §「Wave 0 核实结论」（V1–V17），Wave 1/2/3 实现以其为准。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3"], "depends_on": [0] },
    { "wave": 2, "tasks": ["3.1", "3.1b", "3.2"], "depends_on": [0] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "depends_on": [1, 2] },
    { "wave": 4, "tasks": ["5.1", "5.2"], "depends_on": [3] },
    { "wave": 5, "tasks": ["6.1", "6.2"], "depends_on": [3, 4] },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3"], "depends_on": [4, 5] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 安全网 + 前置核实

- [x] 1.1 characterization 基线锁定
  - 对「生成某章节 → table_data（合计值/values 列对齐/`_cell_modes`）」与「`refill_sections` 在灰度关闭下的产出」写 characterization 测试，作为 Property 10/11/12 的逐字节对照基线
  - 锁定 `_resolve_formula_sum` 现有纯字符串 `cells` 写法的求值结果（Property 8 对照）
  - 记录 `test_disclosure_engine_v2` 现有 7 项失败为 pre-existing 基线（后续零回归门须以此区分，不得混为本 spec 回归）
  - **已完成**：`backend/tests/services/test_disclosure_note_formula_baseline.py`（16 passed）—— 锁定 `_backfill_totals` 求和范围（§V8）/ `_build_with_binding` 行序·列数·manual placeholder（§V4/V5，Property 10 声明性差异对照点）/ `_cell_value_from_table` R·C 坐标口径（Property 7 参照）/ `_resolve_formula_sum` 纯字符串 cells 求值（Property 8 参照）/ 灰度关闭时公式家族一律 None（Property 10 内核）；pre-existing 失败 7 项清单写入模块 docstring
  - _Requirements: 6.1, 6.5_
  - _Properties: Property 8, Property 10, Property 12_

- [x] 1.2 前置核实（不臆造，按实测结果调整实现）
  - 核实 `refill_sections` 构造的 `ctx` 是否注入 `report_data` / `aging_data`（决定 `report`/`aging` source 是否当期可用；不可用则本 spec 只产出 `sum`，并在覆盖率报告注明）
  - 核实 `note_template_{soe,listed}.json` 的 `tables[].rows` 是否恒为 list、`headers` 与 `header_normalize` 长度是否一致（坐标派生前提）
  - 核实 `check_note_binding_registry.py` 校验对象是 `note_binding_registry.json` 还是 `note_template_bindings.json`（决定守卫是否需同步 `sum`）
  - 核实预设 `upsert_presets` 的幂等 API 签名与 `formula_presets_seed.json` 现有条目结构
  - 产出核实结论清单，作为 Wave 1/2/3 实现依据
  - **已完成**：17 条结论写入 `design.md` §「Wave 0 核实结论」（V1–V17）；据此修订 design 决策 2/3/5/6 与 Property 3/7/10
  - _Requirements: 9.4, 9.5, 7.4_

- [x] 2. Wave 1 — 派生纯函数 + PBT

- [x] 2.1 新建 `app/services/note_formula_derivation.py`
  - `cell_coord(row_idx0, value_col_idx0) -> 'R{r+1}C{c+1}'`（R 以 `note_template.tables[].rows` 列表序为准、**含 header_label 行与合计行**；C 为数值列 1-based，不含 label 列）— §V4/V5
  - `value_col_semantics(table_binding)`：从 `binding.header_normalize` 取数值列语义（丢弃 index 0 的 label 列）— 列语义真源在 binding，模板无（§V2）
  - `derive_sum_formula(table_template, table_binding)`：`row_type ∈ {total,subtotal}` 行 → 求和范围 = 上一合计行之后到本行之前的**所有非合计行**（严格对齐 `_backfill_totals`，§V8，不是"仅 data 行"）；不可判定 → 跳过 + reason；范围内无行 → 不产出
  - `derive_movement_identity(table_template, table_binding)`：列语义四件套（`opening_balance`/`current_year_increase`/`current_year_decrease`/`closing_balance`）齐全 → data 行 `closing_balance` 带符号项规格；分列语义（`_col2/_col3`）按组齐全才产出、跨组不混算；**目标格须当前为 manual+todo** 且**行 label 在表内唯一**（重复 label 跳过，reason=`duplicate_label`，§V7）
  - `derive_note_formulas(section_number, template_section, binding_section, variant) -> DerivationResult`（`sum_specs` / `movement_specs` / `skipped[{table,row,reason}]`），纯函数无 IO；输入是模板表 + binding 表**配对**（按 `section_number` join，§V3）
  - _Requirements: 1.1, 1.3, 1.4, 2.1, 2.3, 2.5, 5.1, 5.2_
  - _Properties: Property 4, Property 5, Property 16_

- [x] 2.2 派生纯函数 PBT
  - Property 5（四件套不全不产出 / 分列按组）/ Property 6（增减列不被绑定）/ Property 16（已公式化 + manual&todo + skipped = 候选总数）
  - Property 3（产出中不存在 total/subtotal 行的公式 binding —— `source='formula'` 或 `formula_kind` 任一存在即违规）
  - _Requirements: 1.2, 2.3, 2.4, 2.5, 7.1, 8.1, 8.2_
  - _Properties: Property 3, Property 5, Property 6, Property 16_

- [x] 2.3 坐标口径属性测试
  - Property 7：对真实模板派生的 `R{r}C{c}` 经 `_cell_value_from_table` 反查，命中 `_build_with_binding` 输出对应单元格；模板行序变化时坐标随之变化（防漂移锁定）
  - 反例锁定：用 bindings 的 rows dict 序派生的坐标在含 header_label / 重复 label 的真实表上**不命中**（证明 §V4 结论已被实现遵守）
  - _Requirements: 8.1, 8.2_
  - _Properties: Property 7_

- [x] 3. Wave 2 — 引擎最小扩展（`formula_kind` 分派 + 带符号 sum）

- [x] 3.1 `_resolve_formula_sum` 支持带符号项
  - `cells` 项支持 `str`（原样，视为 `+`）或 `{"cell": str, "sign": "+"|"-"}`；构造 `ROW('a') + ROW('b') - ROW('c')` 交既有 `formula_parse_utils.evaluate_formula`（不新造求值器）
  - 项坐标取不到值 → 跳过该项；全部取不到 → None（fail-open）
  - 不扩 `VALID_SOURCES`、不注册进 `SOURCE_RESOLVERS`
  - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - _Properties: Property 8, Property 9_

- [x] 3.1b `formula_kind` 子类型分派（三处 additive，均在灰度门控内）
  - `resolve_formula`：`kind = binding.get('formula_kind') or binding.get('kind') or source` 后按 kind 分派 sum/report/aging/prior_year_note；`source in ('sum','report','aging')` 旧直调语义逐字节保留（向后兼容）
  - `disclosure_engine.refill_sections` 公式家族判定 `_src in ('sum','report','aging')` → 追加 `'formula'`
  - `NoteFormulaEvaluator.FORMULA_FAMILY_SOURCES` / `_RESOLVE_FORMULA_DIRECT` 各追加 `'formula'`
  - 单测：`source='formula'` + `formula_kind='sum'` 在灰度开时经三条路径（dispatch 首遍 / refill / 第二遍 evaluator）均命中 sum 求值；灰度关时全返 None 不覆盖既有值
  - _Requirements: 9.4, 6.1, 6.3_
  - _Properties: Property 8, Property 10_

- [x] 3.2 带符号 sum PBT
  - Property 8（纯字符串写法逐字节兼容；带 `sign:'-'` 按减法）/ Property 9（缺项跳过、全缺返 None、refill 不覆盖既有值）
  - **已完成**：`tests/services/test_note_formula_signed_sum.py`（20 passed）；同步更新 `tests/test_disclosure_note_formula_wave2.py::test_formula_family_sources` 常量断言（追加 `'formula'`，附本 spec 决策 3 注释）
  - _Requirements: 9.1, 9.2, 9.3_
  - _Properties: Property 8, Property 9_

- [x] 4. Wave 3 — 生成数据（binding + 预设）

- [x] 4.1 新建 `scripts/gen/generate_note_formula_data.py`
  - 读 `note_template_{soe,listed}.json` + `note_template_bindings.json`（按 `section_number` 配对，§V3）→ 调派生纯函数 → 写 `note_template_bindings.json`：仅对当前为 `manual` + `todo` 的候选单元格写 `{"source":"formula","formula_kind":"sum","cells":[…带符号…],"table_index":n,"mode":"auto","derived_by":"movement_identity","derived_note":…}`；`trial_balance`/`prior_year_note`/人工标注一律不覆盖
  - 合计行**不写**公式 binding（决策 2 硬约束，§V10），只加追溯标注字段
  - **不改** `valid_sources` 声明（`formula` 已在其中，§V11/决策 6）
  - 幂等：重复运行逐字节一致；产出覆盖率报告（soe/listed 分别：已公式化/仍 manual+todo 语义分布/skipped 带 reason；注明 `aging` 因 ctx 未注入 aging_data 而不产出，§V1）
  - 预期规模参考（§V14/V15）：四件套齐全表 48 张、`closing_balance` manual+todo 候选 1030 格
  - 生成后跑既有 `normalize_note_bindings.py --write` 后处理
  - **已完成（实测结果）**：146 章节配对（listed 84 / soe 60，2 章节结构未对齐跳过：`六`=tables_missing、`十一、关联交易情况`=table_count_mismatch）；**变动表恒等式 119 条**写入 binding，覆盖 24 章节；**合计追溯标注 393 行**（不写公式 binding）；候选三分类校验通过：119 已公式化 + 154 被跳过的候选 + 2799 仍 manual+todo = 3072 候选总数；跳过原因分布 non_summable_semantic 382 / movement_quad_incomplete 252 / duplicate_label 156 / total_at_first_row 117 / target_not_manual_todo 19 / empty_sum_range 11 / rows_empty 11；**幂等实证**：二次 `--apply` 后两数据文件 SHA-256 逐字节一致（bindings `f97743d0…` / seed `33124251…`）；binding 必填字段（source/field/mode/account_codes）已按 `test_note_template_bindings.py` 契约补齐；已跑 `normalize_note_bindings.py --write`（keys 146→146 不变）
  - _Requirements: 1.1, 1.4, 2.1, 2.2, 2.4, 5.1, 5.2, 5.3, 5.4, 7.1, 9.5_
  - _Properties: Property 1, Property 2, Property 3, Property 6, Property 12, Property 16_

- [x] 4.2 预设登记（合计 + 恒等式）
  - 同一派生结果经 `upsert_seed_presets(entries: list[PresetEntry])` 幂等写入 `formula_presets_seed.json`（§V12 实名）：`page_key='note:{章节}'`、`formula_type='auto_calc'`、机器可读 `expression`、`variant='soe'|'listed'`、`target_cell` 用稳定派生 id（不与既有 1549 条中文 `check_presets` 撞 `(page_key,target_cell)`）
  - 只写显式 seed，不触碰 `prefill_formula_mapping` / `note_check_preset_formulas` / 宽表 MD 三源（读时收敛）
  - **已完成**：`upsert_seed_presets` 写入 **995** 条（119 movement `auto_calc` + 876 合计逐列 `auto_calc`），seed 365 → 1360；重跑 `seed_formula_presets.py` 刷新 `inventory.json`（§V19；note scope 页数 59 → 129）
  - _Requirements: 1.1, 3.1, 3.4, 3.5, 5.1_
  - _Properties: Property 1, Property 14_

- [x] 4.3 新建 `scripts/gen/generate_note_cross_check_presets.py`
  - 从 `report:cross_check` 条目提取 `NOTE('{章节}', …)` → 为该章节登记 `note:{章节}` 的 `logic_check` 预设，**表达式与容差沿用原条目**（同源，不另写口径）
  - 幂等 + 稳定 `target_cell`；无法解析章节的条目跳过并记录（实测 93 条中 61 含 `NOTE()`、32 为纯报表内恒等式 → 预期跳过 32 条，§V13）
  - **已完成（实测）**：93 源条目 → **61 条**附注侧 `logic_check` 预设（覆盖 61 个附注章节，`target_cell=note-crosscheck:{章节}:{原 id}`，表达式/容差/refs 逐字沿用原条目），32 条纯报表内恒等式跳过并记录；seed 1360 → 1421；`inventory.json` 刷新后 232 pages / 3939 formulas（note scope 131 pages / 2607 formulas）
  - _Requirements: 3.2, 3.3, 7.3_
  - _Properties: Property 15_

- [x] 5. Wave 4 — linkage 口径明确化 + 诊断

- [x] 5.1 `report_note_linkage` 只读诊断
  - `diagnose_missing_write_linkage()`：列出"有报表↔附注勾稽关系但无写值 linkage"的章节（只呈现不写入）
  - 经既有 `GET .../formula-health` 附加字段暴露（不新增路由）；`cells_updated=0` 在响应/日志中可区分于"失败"
  - **已完成**：`ReportNoteLinkage.diagnose_missing_write_linkage(notes, cross_check_sections=None)`（缺省从预设库取 `note:*` 的 `logic_check` 章节集合，fail-open）+ `_load_cross_check_sections()`；`GET .../formula-health` 附加 `missing_write_linkage` / `missing_write_linkage_count` 字段（try/except fail-open，不影响健康度主体，不新增路由）
  - _Requirements: 4.1, 4.3, 4.4_
  - _Properties: Property 13_

- [x] 5.2 linkage 不变性测试
  - Property 13：`report_note_linkage.json` 业务条目数本 spec 前后不变（仍为 0）；诊断只读
  - **已完成**：`tests/services/test_report_note_linkage_diagnose.py`（9 passed）—— 业务条目 0 + `_rules` 元数据保留 + 诊断只读（note/config 前后逐字节一致）+ 已有 binding/config 目标章节不算缺口 + 无勾稽章节不算缺口 + 预设库不可用 fail-open
  - _Requirements: 4.1, 4.2_
  - _Properties: Property 13_

- [x] 6. Wave 5 — 契约守卫 + 覆盖率

- [x] 6.1 新建 `scripts/check/check_note_formula_contract.py`
  - 断言：预设库本 spec 产出条目的章节集合 ≡ binding 中 `formula_kind='sum'` 章节 ∪ 合计登记章节（任一侧漂移即失败，失败信息指名章节+字段）
  - 断言：附注侧 `logic_check` 与 `report:cross_check` 表达式/容差同源
  - 断言：合计登记求和范围 ≡ `_backfill_totals` 口径（上一合计行之后的全部非合计行）
  - 断言：产出不含 total/subtotal 行的公式 binding；不含新增披露内容；`valid_sources` 声明未被本 spec 改动
  - 以数据文件遍历为源，不硬编码逐条清单；挂 `governance-checks.yml`
  - **已完成**：`backend/scripts/check/check_note_formula_contract.py --strict` **exit 0**（binding movement 24 章节 ≡ 预设 24；合计标注 117 ≡ 预设 117；附注侧勾稽 61 全部与 `report:cross_check` 表达式/类型同源；linkage 业务条目 0；`valid_sources` 未改；行标签全部来自模板）；已挂 `governance-checks.yml` 新 job `note-formula-contract`（strict）
  - _Requirements: 7.2, 7.3, 7.4, 5.3_
  - _Properties: Property 3, Property 4, Property 12, Property 14, Property 15_

- [x] 6.2 覆盖率报告落地
  - 覆盖率统计产出可读报告（soe/listed 分别统计 total 行登记数/总数、恒等式覆盖数/候选数、仍 manual+todo 语义分布 top N）
  - **已完成**：`backend/data/note_formula_coverage_report.md`（由生成器 `--apply` 落地）：章节配对（listed 84 / soe 60 / 未对齐 2）+ 恒等式 119 条/24 章节 + 合计预设 876 条/标注 393 行 + 候选三分类校验 + 跳过原因分布表 + **诚实说明未产出的公式类型**（`aging` 因 ctx 未注入 `aging_data`；`report` 因决策 1 只校验不写值）
  - _Requirements: 7.1_
  - _Properties: Property 16_

- [x] 7. Wave 6 — 灰度两态 + 零回归 + 真实 round-trip

- [x] 7.1 灰度两态验证
  - Property 10：`DISCLOSURE_NOTE_FORMULA_ENABLED=False` 时生成/刷新的 `values`/`label`/`is_total`/`headers` 与 1.1 基线逐字节等价；显式断言 `_cell_modes` 由 `manual`→`auto` 是唯一声明性差异且值仍为 None（存量 note 经 merge 保留 OLD `_cell_modes`，用户手工值不被覆盖）
  - Property 11：开关开启后合计与恒等式单元格数值与关闭时 `_backfill_totals` 结果一致（公式只把黑箱显式化，不改数）
  - **已完成**：`backend/tests/services/test_note_formula_gray_two_state.py`（4 passed）—— **用 shipped `note_template_bindings.json` 里 Task 4.1 真实写入的 `source='formula'` binding 驱动**（不造假 binding）；table_data 按**模板行序**构造（§V4/V5，坐标口径与生成器一致）：①灰度关→产出与入参逐字节一致（入参未被就地修改）②灰度关→既有人工数值 777 不被 None 覆盖 ③灰度开→变动表恒等式 `100+30-10=120` 正确填入 ④灰度开经公式填期末 + `_backfill_totals` 的合计结果与"人工填同样期末数"逐字节相等（Property 11：公式只把黑箱显式化不改数）
  - _Requirements: 6.1, 6.2, 6.3_
  - _Properties: Property 10, Property 11_

- [x] 7.2 零回归门
  - 全量跑 `test_disclosure_note_formula_wave*` / `test_disclosure_engine_v2`（基线 7 failed / 53 passed，§V17）/ `test_note_template_bindings`（基线全绿，含 cell.source 枚举断言）/ `test_note_source_resolvers` / `note_validation` / `test_wp_disclosure_sync*` / 附注相关 e2e + 前端 vitest；以 1.1 记录的 pre-existing 失败清单区分，不得新增变色
  - `disclosure_notes` 无表结构改动、无迁移（Property 12）
  - **已完成**：21 个测试文件汇总 **371 passed / 11 failed / 8 errors**，失败集合与 §V17/V18 pre-existing 基线**逐项一致**（7 项 `test_disclosure_engine_v2` + `test_note_template_variant_matrix` 3 failed+8 errors[traceback 指向另一仓库路径 `D:\GT_workplan`] + `test_variant_matrix::test_every_matrix_code_exists_in_index`），**零新增变色**（基线 367 passed，本 spec 新增 gray-two-state 4 项后 371）；`git status` 实证未改变体矩阵数据文件；无 DB 迁移、`disclosure_notes` 表结构未动（Property 12）
  - _Requirements: 6.4, 6.5_
  - _Properties: Property 10, Property 12_

- [x] 7.3 真实项目 round-trip*
  - 灰度开启后对真实项目某变动表章节生成/刷新 → 恒等式与合计数值正确 → 公式管理中心附注节点可见对应预设（分类正确）→ 直连 DB 备份/恢复并断言 `RESTORED_IDENTICAL`（零污染）
  - 灰度开关默认 False + 请求时读取，若共享后端不便切换则以进程内 standalone 脚本对真实 DB 验证（不擅自重启共享 server，不假绿）
  - **已完成（进程内 standalone 脚本对真实 DB，项目 `0ec33ac9…`/2025，不重启共享后端）**：table0 含 `formula` 的章节 18 个 → 命中真实附注 **7 条 / 17 个恒等式目标行**；①**灰度 OFF**：`refill_sections` 正常刷新其它数据源格（cells_updated=17）但公式目标格**被填数=0**（Property 10 零回归）②**灰度 ON**：cells_updated=17 / sections_recomputed=7 / errors=[]，**恒等式 17/17 正确**（期末 = 刷新后实际期初 + 增 − 减；不能拿播种值当期望，因同一遍 refill 会用 `trial_balance` 重算期初格）③**公式管理中心可见性**：`find_presets_for_page('note:{章节}')` 返回该章节预设，`formula_type` 分类正确（`auto_calc` / `logic_check` / `reasonability`）④`await db.rollback()` 后重查比对 → **`RESTORED_IDENTICAL=True`**（零污染，脚本跑完即删）
  - **实测澄清**：真实附注该 17 行原始期初/增/减本身为空 → 公式 fail-open 返 None 不覆盖（这也是它们仍为 manual+todo 候选的原因）；故 round-trip 在内存播种增减值后验证，未 commit
  - _Requirements: 8.3, 3.3_
  - _Properties: Property 11_

## Notes

- **灰度默认关**：本 spec 不改 `DISCLOSURE_NOTE_FORMULA_ENABLED` 默认值；是否开启由用户在覆盖率与 round-trip 结果确认后另行决定。
- **合计真源不动**：`_backfill_totals` 保持唯一计算真源；合计只做预设可见化 + binding 追溯标注（决策 2），避免双算。
- **不批量填 linkage**：`report_note_linkage.json` 维持 `_rules`，只加只读诊断（决策 1，用户已拍板）。
- **宽表 MD 源缺失**：`附注模版/{国企版,上市版}宽表公式预设.md` 实测不存在，故本 spec 公式走显式 seed，不依赖该收敛源。
- **生成器后处理**：改 `note_template_bindings.json` 后必须跑 `normalize_note_bindings.py --write`（补国企 legacy_aliases），否则既有变体矩阵测试会失败。
- **`SOURCE_RESOLVERS['formula']` 原为死键**（`resolve_formula` 内部再读同名 `source` 不匹配 sum/report/aging）；本 spec 用 `formula_kind` 子类型分派把它**激活**（Task 3.1b），既让已声明的 `formula` source 名副其实，又不新增枚举值、不动 `VALID_SOURCES` 契约。
- **不用 `source='sum'`**：`test_note_template_bindings.py` 硬编码 8 项集合断言每个 `cell.source ∈ 其中`（§V11），写 `sum` 会直接打破既有测试。
- **并发会话**：`confirmation-attachment-ocr-linkage` / `adjustment-import-export-contract` 由并发会话执行中；本 spec 只碰附注公式相关文件，commit 前须 `git status` 只 stage 自己文件。
