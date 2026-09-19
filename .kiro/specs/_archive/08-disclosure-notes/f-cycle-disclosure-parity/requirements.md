# Requirements: F 类披露表与附注对齐补齐（F1 / F3 / F4 追平 F2）

## 背景

F2 存货披露在 `f2-inventory-disclosure-template-alignment` Sprint 7 完成了六类修复
（seed 行集 / 标签列头 / `_note_texts` 中文 title / 永空表二选一 / 模板 columns·guidance /
子表契约守卫）。2026-07-30 对 F 类全循环做了同口径复盘，F1 预付款项、F3 应付票据、
F4 应付账款各有欠账，本 spec 按 P1→P3 收口。

**裁决顺序**（沿用 F2 Sprint 7 结论）：运行时权威源 xlsx（`backend/wp_templates/F/`）
> `note_check_preset_formulas.json` > 现状模板 JSON。`基础数据/附注模版/*.md` 在本仓库
不存在，不作为裁决依据。

源模板实证（`F3 应付票据.xlsx`，逐格 openpyxl）：

| sheet | A6 | B6 | C6 | 行序 |
|---|---|---|---|---|
| 附注披露信息(上市公司) | 种类 | 期末余额 | 上年年末余额 | r7 银行承兑汇票 → r8 商业承兑汇票 → r9 合计 |
| 附注披露信息(国企) | 类别 | 期末余额 | 期初余额 | 同上 |

## P1

### R1 F3 国企披露列头必须与国企模板一致

1. WHEN 国企披露 Tab 同步到附注 THEN `columns` SHALL 为
   `类别 / 期末余额 / 期初余额`（源 xlsx 国企 A6/B6/C6）。
2. 现状：`f3NoteSectionMap.ts` 只有一份 `F3_YFPJ_COLUMNS` 给两变体共用，值为上市口径
   `种类 / 期末余额 / 上年年末余额` → 3 列错 2 列，国企项目同步后附注表头显示上市口径。
3. WHEN 上市披露 Tab 同步 THEN `columns` SHALL 保持 `种类 / 期末余额 / 上年年末余额`。
4. 两变体 SHALL 各有独立的子表名常量（`F3_LISTED_SUBTABLE` / `F3_SOE_SUBTABLE`），
   与模板 `tables[].name` 逐字一致。

### R2 F3 分类行序对齐源 xlsx

1. WHEN 渲染 F3 附注表 THEN 行序 SHALL 为 `银行承兑汇票 → 商业承兑汇票 → 合计`
   （源 xlsx r7/r8/r9）。现状模板与 `orderF3ClassRows` 均为「商业 → 银行」，与源相反。

### R3 F3 附注模板补齐 columns / guidance 并打对齐标记

1. 现状两变体「应付票据」表 `columns` 为空、`guidance` 为空、`_aligned_by` 为 null。
2. WHEN seed 路径渲染（新建项目 / 重新生成附注）THEN 表 SHALL 有显式 `columns`
   且在 `flat` / `group` 之间明确表态（单级表头 → `flat`），避免
   `_infer_groups_from_headers` 前缀推断。
3. 每张表 SHALL 有 `guidance`（附注 TAB 编制提示），内容只取源 xlsx 说明行与红字括注。
4. 修订 SHALL 由幂等脚本完成（`--dry-run` / `--check`），并有结构守卫测试。

### R4 F3 补子表契约守卫

1. F3 SHALL 有 `f3NoteSubtableContract.spec.ts`，接入平台共享
   `runDisclosureSubtableContract`（P1~P5）。F3 是 F 类唯一缺此守卫的循环，
   R1 的列头错位正是因为无人守。

## P2

### R5 `_note_texts` 必须带中文 title

1. WHEN F1 同步 THEN 7 条 `_note_texts`（`listed-note-aging` / `listed-note-over1` /
   `listed-note-top5` / `listed-top5-summary` / `soe-note-*`）SHALL 各带非空中文 `title`。
   现状全缺 → 附注正文渲染成 `【listed-note-aging】`。
2. WHEN F3 同步 THEN `${variant}-note` SHALL 带中文 title。
3. WHEN F4 同步 THEN `_note_texts` SHALL 同时带 `section` 与中文 `title`
   （现状为 `[{ text }]`，无来源标识）。
4. 空文本 SHALL 被过滤，不写入 `_note_texts`。

### R6 F4 披露 Tab 接自动同步

1. 现状 `useF4Disclosure{Listed,SOE}` 只有手动 `syncToNotes`，两个 Tab 均未使用
   `useDisclosureAutoSync` → 用户改数据不点按钮永不进附注（F1/F2/F3 都已接）。
2. WHEN 披露表数据或说明文本变化 THEN SHALL 触发防抖自动同步，与手动按钮同源幂等。
3. SHALL NOT 使用 `_xxxMounted` 一次性防护（会吞掉「切走再切回后的第一次编辑」）。

## P3

### R7 F1 模板 headers 去除 HTML 标记

1. `按预付对象归集的预付款项期末余额前五名单位情况` 的 `headers` 含两处 `<br/>`
   （md 表格排版残留）。`el-table-column :label` 与 Word 导出都不解析 HTML。
2. WHEN 渲染该表 THEN `headers` SHALL 为纯文本，与同步 `columns[].label` 逐位一致。

### R8 契约守卫覆盖模板 headers 的 HTML

1. 共享 helper 的 P4 只校验 `columns` 的 label/group，模板 `headers` 是盲区
   （F1 的 `<br/>` 因此长期未被发现）。
2. helper SHALL 增加一条 Property：模板 `tables[].headers` 为纯文本。

### R9 F1 / F3 / F4 披露文本域补 AI 辅助

1. 平台铁律：多 section 底稿每个文本区都要 AI 辅助（F2 上市 6 / 国企 5 已配齐）。
2. F1 三个文本域、F3 一个、F4 一个，现状 `runAi` 命中为 0。
3. F3 后端已注册 `listed-note` / `soe-note`；F4 已注册 `disclosure-listed-note` /
   `disclosure-soe-note`；F1 SHALL 新增披露 section 到
   `_SUPPORTED_SECTIONS` + `_SECTION_PROMPTS` + 前端联合类型 + Tab 的 `AI_TARGETS`
   四处（缺一即空转），prompt SHALL ≥20 字并写明源模板口径与「不得虚构」约束。

## 不在本 spec 范围

- F4 上市按性质表模板自补的「设备款 / 服务费 / 其他」3 行：源 xlsx 只有
  「货款 / 工程款 / 可无限量添加行 / 合 计」，是否保留待用户定口径。
- F3 上市源 xlsx 的【供应链票据】红字是否在 seed 显式列一行「供应链票据」，待用户定口径。
- F1 上市账龄表比源 xlsx 多的「小计 / 减：减值准备」两行（按校验预设有意加）。
- F4 国企账龄标签走 `disclosureAgingLabels.ts` 单一真源，不改回源 xlsx 字面。
