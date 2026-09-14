# Implementation Plan: D 类剩余披露表与附注结构对齐（D3 / D5 / D6 / D7）

## Overview

四个循环按「模板端 → 载荷端 → 守卫 → 实测」的顺序推进，循环之间互不依赖，
按缺陷严重度排序：D3（最轻）→ D7 → D5 → D6（最重，含两级表头还原）。
共用一个幂等脚本与一份后端结构测试，因此脚本骨架（任务 1）必须先做。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "desc": "幂等脚本骨架 + 后端测试骨架", "depends_on": [] },
    { "wave": 2, "tasks": ["2", "3"], "desc": "D3 与 D7（结构相近，单级表头）", "depends_on": [1] },
    { "wave": 3, "tasks": ["4"], "desc": "D5（含 flat 抑制推断的关键修复）", "depends_on": [1] },
    { "wave": 4, "tasks": ["5", "6"], "desc": "D6 模板重建 + 载荷两级表头还原", "depends_on": [1] },
    { "wave": 5, "tasks": ["7"], "desc": "守卫、CI、回归", "depends_on": [2, 3, 4] },
    { "wave": 6, "tasks": ["8"], "desc": "浏览器实测", "depends_on": [5] }
  ]
}
```

## Tasks

- [x] 1. 幂等脚本与后端测试骨架
  - [x] 1.1 新建 `backend/scripts/fix/fix_note_d_cycle_rest_structure.py`：8 个章节条目 +
        `RENAMES`（走 `rule(aliases=...)`）/ `DROPS` 显式表 + `--dry-run` / `--check` /
        `--only` + `_aligned_by` 标记。共享工具抽到
        `backend/scripts/fix/_note_structure_kit.py`（行/列构造 + apply_plan + validate_section
        + `titleize_text_sections` + CLI 骨架 + 新增「源模板有、模板 JSON 整张缺失」时的
        `rule(insert=True)` 插表能力）
  - [x] 1.2 新建 `backend/tests/test_note_d_cycle_rest_structure.py`：91 测试
        （8 章节参数化跑 Property 1~4、6 + 逐表钉死关键结构 + 4 条反向自检）
        _Requirements: R1.5, R5.1, R5.2_

- [x] 2. D3 预收款项（五、38 / 八、38）
  - [x] 2.1 模板：3 表 / 2 表补 `columns`（全 flat）+ `guidance` + 行骨架；
        国企第 2 表按源 A10/A11 校正为 `账龄超过1年的重要预收账款` / `未偿还原因`
  - [x] 2.2 载荷 `d3NoteSectionMap.ts`：全部 `ColumnDef` 加 `flat`；列头取源模板字面
        （`项 目` / `账  龄`）；新增 `D3_NOTE_TOTAL_LABEL`（逐表实证：上市 `合 计` /
        国企主表 `合  计` / 国企超1年表 `合计`）与 `D3_OBSOLETE_TABLE_NAMES` →
        `_removed_table_keys`
  - [x] 2.3 `d3NoteSubtableContractShared.spec.ts` 接入共享 helper（25 测试）；
        原 `d3NoteSubtableContract.spec.ts` 更新到源模板期望（13 测试）
        _Requirements: R1.1, R1.2, R1.4, R3.1, R3.3, R3.4_

- [x] 3. D7 合同负债（五、39 / 八、39）
  - [x] 3.1 模板：国企第 2 表占位名 `合同负债（表2）` → `本期合同负债账面价值的重大变动`；
        3 表 / 2 表补 `columns`（flat）+ `guidance`（上市主表取源 A16 净额列示提示）
  - [x] 3.2 载荷 `d7NoteSectionMap.ts`：加 `flat` + 列头 `项  目` +
        `D7_NOTE_TOTAL_LABEL`（`合  计`）+ `D7_OBSOLETE_TABLE_NAMES` → `_removed_table_keys`
  - [x] 3.3 文本段落：新增源模板要求的**定性披露 3 段**
        （上市 A32-A34「披露以下信息：」/ 国企 A15-A17「说明：」），此前完全无录入位置 →
        `D7_QUALITATIVE_TITLES` + `D7_NOTE_TEXT_KEYS` 单一真源，
        `useD7Disclosure` 改为引用常量（删掉硬编码 5 键），组件末尾加「定性披露」卡片
  - [x] 3.4 `d7NoteSubtableContract.spec.ts`（31 测试：共享 helper + 专属 + 文本域键集守卫，
        含「composable 不得再硬编码键集」源码断言）
        _Requirements: R1.1, R1.2, R1.4, R3.1, R3.2, R4.1, R4.2_

- [x] 4. D5 应收款项融资（五、6 / 八、6）
  - [x] 4.1 模板：上市第 2 表补回标签列（原只剩 `减值准备金额` 一列）；4 表 / 1 表补
        `columns` + `guidance`（含源 A6/A7/A14/A28/A39-A43 与国企 A11/A12 交叉引用提示）
  - [x] 4.2 🔴 上市第 4 表（背书或贴现）标 `flat`：两列共前缀「期末」，
        未表态时 seed 路径必被 `_infer_groups_from_headers` 猜出凭空「期末」父表头
  - [x] 4.3 载荷 `d5NoteSectionMap.ts`：全部加 `flat`；主表行名按源模板归一
        （`NOTE_ROW_LABELS`：`小计`→`小  计`、`应收款项融资公允价值合计`→`期末公允价值`）；
        `isTotalLabel` 先去空白（源模板写的是「小  计」）；减值表首行按源 A21 改「上年年末余额」
  - [x] 4.4 `d5NoteSubtableContract.spec.ts`（26 测试，含共前缀必须 flat 的定点回归）
        _Requirements: R1.1, R1.2, R1.4, R3.1_

- [x] 5. D6 合同资产模板重建（五、10 / 八、11）
  - [x] 5.1 清理上市 9 张表 → 7 张固定表 + 2 张组合骨架：`DROPS` 空名残片；
        `续：` → `按单项计提减值准备（续：上年年末余额）`；`项  目` →
        `本期计提、收回或转回的合同资产减值准备情况`；`按单项计提减值准备：` →
        `按单项计提减值准备（期末余额）`
  - [x] 5.2 上市主表 7 列两级（期末余额 / 上年年末余额 各 账面余额·减值准备·账面价值）；
        「（2）减值准备计提情况」源模板**三级** → 顶层期间提到表名拆两张表，
        每张 6 列两级（账面余额{金额,比例(%)} / 减值准备{金额,预期信用损失率(%)} / 账面价值独立列）
  - [x] 5.3 上市组合明细表 7 列两级（期末余额 / 上年年末余额 各 合同资产·坏账准备·损失率）
  - [x] 5.4 国企 3 表：主表 7 列两级（期末数 / 期初数）、减值准备表 7 列
        （`本期变动金额` 三列一组）、重大变动表 flat + guidance 写入「国资委格式未要求披露」
  - [x] 5.5 上市 `text_sections` 3 → 8 段：补源模板 A36-A41 的说明段
        （国企侧 A32-A36 本就齐备）。🔴 说明正文**不写 `#### ` 前缀**——后端
        `_is_table_title_paragraph` 认 `#` 即标题、标题本身不进任何输出，会被静默丢弃；
        `run_section` 的 `--check` 分支加了清单比对（此前只校验表结构，段落缺失照过）
        _Requirements: R2.1, R2.2, R2.4, R2.5, R3.2, R4.3_

- [x] 6. D6 载荷两级表头还原与缺失段补齐
  - [x] 6.1 `d6NoteSectionMap.ts` 重写：主表列头由拍平组合名（「期末账面余额」）改为
        `label` + `group`，抽 `d6MainColumns(variant)` / `twoPeriodColumns()` 单一真源
        （两期同构由构造保证）
  - [x] 6.2 「（2）减值准备计提情况」补回**上年年末段 + 账面价值列**
        （旧载荷只有期末 4 列）→ 期末/续表两张同构表
  - [x] 6.3 「按单项计提减值准备」拆期末 / 续表两张；组合明细补回上年年末 3 列
  - [x] 6.4 表名与模板逐字对齐；`D6_OBSOLETE_TABLE_NAMES` + 按当前组名推导的旧组合表名
        一并进 `_removed_table_keys`
  - [x] 6.5 国企减值准备表列头改 `group`（`本期变动金额`）
  - [x] 6.6 上市「或：披露格式如下」（源 A20-A26）二选一：`D6MainFormat` +
        `mainFormat` 持久化（`D6-note-listed-main-format`）+ 底稿 `el-radio-group` 切换；
        简化式行由 `buildD6SimpleMainRows()` 纯函数从明细派生（载荷与 UI 共用，
        派生行「小  计」「合  计」「减：…」按去空白判定不参与二次汇总）。
        两格式**同名同表** → 不需要 `_removed_table_keys`，只是 columns/rows 形态不同
  - [x] 6.7 组件 `D6TabDisclosure.vue`：主表改两级表头；新增上年年末段两张可录入表
        （`useD6Disclosure` 加 `impairmentPriorRows` / `singlePriorRows` 持久化
        `D6-note-listed-s2-prior-rows` / `-s3-prior-rows`）；组合表加上年 3 列；
        金额输入全部走 `WpAmountInput`；(3) 表列名按源 D85 改「本期转销/核销」；
        **修掉 snapshot 字段名与载荷接口不符导致的静默推 0**（`endBalance` vs `balance`）
  - [x] 6.8 `d6NoteSubtableContract.spec.ts`（42 测试：共享 helper + 两期同构逐表钉死 +
        「不得是拍平组合名」反向断言 + 上年段真的带数据 + `_removed_table_keys`）
        _Requirements: R2.1, R2.2, R2.3, R2.4, R2.5, R3.1, R3.3_

- [x] 7. 守卫、CI 与回归
  - [x] 7.1 `disclosureColumnsCoverage.spec.ts` 登记 8 个新 builder 的 `P1_ROUTE`
  - [x] 7.2 `backend/tests/services/test_note_word_export_d_cycle.py`（30 测试）：
        D6 七张两级表头表走 `_build_two_level_header_rows`
        （row0 覆盖列数 / row1 只放分组子列 / 独立列 rowspan=2 / flat 表无 `_column_groups`）
  - [x] 7.3 CI job `note-d-cycle-rest-structure`（`--check` + 后端契约 + Word 导出）
  - [x] 7.4 回归：后端 91 + 30 绿；前端 D3/D5/D6/D7 相关全绿
        （d3 共享 25 + d3 专属 13 + d5 26 + d6 42 + d7 31 + d7NoteSectionMap 6）；
        改动的 8 个 `.vue`/`.ts` Vite transform 200。
        `disclosureColumnsCoverage` / `disclosureAutoSyncCoverage` 各 1 条失败**不属本 spec**
        （`buildN2*` / `buildN4*` 与 N2/N4 Tab 为并发会话在飞改动）

- [x] 8. 浏览器实测（Playwright 独立实例登录，避开共享 Chrome 被并发会话抢占）
  - [x] 8.1 七个 Tab 逐个实测（`?sheet=` 精确匹配失败 → 改点 tab 名进入，见 Notes「已知偏差」）：
        **D6 上市**主表两级表头 + 减值两张同构表 + 单项期末/续表；
        **D6 国企**两级表头正确（期末数{3}/期初数{3}、本期变动金额{计提,转回,转销/核销}）；
        **D5 两版**挂载正常（`d5-disclosure`）；
        **D7 两版**挂载正常且**定性披露卡片渲染出 6 个文本域**（3 按表说明 + 3 定性）；
        **D3 两版**组件已挂载（`d3-disclosure-listed`）但被门控挡住，显示
        「当前项目不适用上市公司附注披露格式」→ 即平台级 `applicable_standards`
        前端全链缺失（恒 `[]`）的既有缺陷，**非本 spec 引入**，须随平台 spec 一并修。
        控制台 0 error
  - [x] 8.2 D6 上市录入前直接同步 → 落库 7 张表（含两张「续：上年年末余额」），
        `_sub_table_columns.合同资产` 带 `group: 期末余额 / 上年年末余额`，
        `_last_sync_at` 前移；主表 UI 表头实测为两级（项 目 | 期末余额{3} | 上年年末余额{3}）
  - [x] 8.3 未造脏数据（同步的是全 0 空骨架，属正常业务操作，无需回滚）
        _Requirements: R6.1, R6.2, R6.3_

## Notes

- **并发风险**：`note_template_{listed,soe}.json` 与 `disclosure_engine.py` 被多个在飞 spec
  同时改动，本 spec 只碰自己的 8 个章节，且所有改动落在幂等脚本里，测试红了先重跑脚本
- **不改**：D1 / D2 已收口章节；D4（营业收入）披露量大且源模板分 8 个 xlsx，另立 spec
- **已知偏差（待查）**：D6 底稿 `?sheet=附注披露信息(上市公司）` 精确匹配未命中（落回底稿目录），
  而 `workpaper_sheet_classification` 里该值与常量逐字一致 → 疑在 URL 参数解析或
  `currentSheet` 分发环节，需单独定位（不影响点 tab 进入与同步链路）
- [x] 9. 三项遗留收口（AI 辅助 / 底稿列头统一 / 深链失效）
  - [x] 9.1 抽共享 `composables/useDisclosureNoteAi.ts`（消除四份复制），D3 上市 3 处、
        D5 4 处、D6 上市+国企各 1 处（按 section 循环渲染）、D7 按表 3 处 + 定性 3 处
        全部接上「🤖 AI」+「💬 复核」；`related_data` 字段名用 `section_key`
        （顶层 `section:` 是历史错误字段，会让后端 422）
  - [x] 9.2 后端 `review_dialog._SECTION_PROMPTS` 登记 **30 条**专属 prompt
        （D3 上市 3 / D5 4 / D6 9 / D7 14，含定性 3 段 × 两版），每条 ≥20 字 +
        写明源模板与准则口径 + `_NO_FABRICATION`；守卫
        `backend/tests/test_review_dialog_d_cycle_prompts.py`（从前端**文本域键集常量**
        派生期望 id → 新增文本域必然要求补 prompt；另拦孤儿 prompt 与 buildSectionId 前缀漂移）
  - [x] 9.3 底稿 UI 列头统一到源模板字面：D5 上市「项  目 / 期末余额 / 上年年末余额」、
        国企「项  目 / 期末余额 / 期初余额」；D7 两版**期末列前置**且按变体取
        「上年年末余额」/「期初余额」（原为「期初数/期末数」顺序相反）
  - [x] 9.4 🔴 修平台级深链失效：`?sheet=` 传的是**源 xlsx tab 名**
        （`附注披露信息(上市公司）`），而 render-config 下发的 `sheet_name` 带科目前缀
        （`合同资产附注披露信息（上市公司）`）→ 两者既差前缀又差括号宽度；
        `GtWpRenderer` 第 3 级兜底此前用**未归一**原串做 `endsWith/includes`，必然落空 →
        深链回退「底稿目录」。抽纯函数 `utils/normalizeSheetName.resolveSheetNameByDeepLink`
        （三级匹配，第 3 级改用归一串），`GtWpRenderer` 三处 sheet 定位统一走它；
        守卫 15 测试（含上市/国企不得串台、完整名优先于前缀名）
  - [x] 9.5 浏览器实测：`?sheet=附注披露信息(上市公司）` 深链**直接命中** D6 上市披露 Tab；
        AI 6 个 + 复核 6 个按钮渲染；二选一格式开关两项可见；
        直调 `review-dialog/ai-generate`（`d6-disclosure-listed-text-1-note`）返回 **200**
        且生成文本遵守「不虚构」约束（缺数据写 `[待补充]`）
  - [x] 9.6 CI job `note-d-cycle-rest-structure` 增加 AI prompt 守卫步骤；
        后端 171 绿（含既有 D1 守卫）/ 前端 13 文件 210 绿 / 7 个改动文件 Vite 200
        _Requirements: R4.1, R4.2, R5.5, R6.1_

## Notes 补充：仍未收口

- **D3 因 `applicable_standards` 门控恒关，两版披露表在真实项目里用户不可达**
  （附注侧结构与 AI 均已就绪，等平台级 spec 放开门控后即可用）
- **已知平台级遗留**：披露 Tab 无 `applicable_standards` 门控（跨前后端，须单独立 spec）；
  `disclosure_notes.source_template` 与章节号变体错配（实测 五、10 记为 `soe`），
  两者均非本 spec 引入
