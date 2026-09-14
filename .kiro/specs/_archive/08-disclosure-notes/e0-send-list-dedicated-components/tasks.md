# Implementation Plan: E0 发函清单专属 HTML 组件

## Overview

顺序是「先固化源模板事实 → 后端 componentType 与迁移落地 → 前端组件 → E1-3 取数与勾稽 → 实测收口」。

**风险面**：R2 的 P0（示例值污染）与 R5 的 legacy 迁移都在 render 路径上，写错会让 E0-6 已有数据显示为空 → 每一步都以「legacy 载荷往返无损 + 其余循环 render 逐字节不变」为验收门。取数（Task 8）与勾稽（Task 9）是加法式，可单独交付。

**协调前置（2026-08-02 复核后重写）**：
- ~~原文「`e0-confirmation-completion` 的 Task 13『E0-6 渲染形态落地』子项由本 spec 接管，
  override 目标由 `d-form-table` 改为 `confirmation-send-list-e06`」~~ → **两个前提都已过时**：
  该 spec 的 **Task 12.5 已交付 E0-6 专属组件 `confirmation-wealth-list`**（override 双键 +
  `_CONFIRMATION_COMPONENTS` + `wealth-list-v1` + 前端 registry + `confirmation/wealthList/` +
  `test_confirmation_sheet_override_contract.py` 硬断言）。
  **本 spec 改为三张新组件（E0-3/E0-4/E0-5）+ 对 E0-6 做符合度核查（R1.1b，新增 Task 17）**，
  不新建 `confirmation-send-list-e06`、不改其 `_format`。
- 该 spec 的 **Task 11 实际已落地但仍标 `[ ]`（假红）** —— `importE0ListsToSummary.ts` 已由 124 行
  改到 357 行。本 spec 的行形态需与它已实现的 `E0_LIST_SPEC` / `hasConfirmFlag` / `account_no`
  去重键**保持兼容**，不得另造一份。
- 该 spec 的 Task 4（CrossRef 按循环）/ Task 10（品种矩阵）**确认未做**，本 spec 不接管。
- **两 spec 不并行推进。**

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "源模板事实固化 + 平台级污染面盘查",
      "tasks": ["1", "2"],
      "parallel": true,
      "rationale": "四张表列集与 E1-3 两版段结构必须先用 openpyxl 钉死，后续实现全以它为裁决；污染面诊断脚本只读、与实现无依赖，可并行"
    },
    {
      "wave": 2,
      "name": "后端 componentType 落地（解 P0）",
      "tasks": ["3", "14", "4", "5"],
      "parallel": false,
      "rationale": "列集服务 → Task 14（已降级为只加 E0-5 全名 skip 不变式守卫，不再是 Task 5 的前置：实证 skip 判定 L709 全名优先、componentType 判定 L749 尾码优先，两者顺序相反使当前配置已正确）→ render 策略与迁移 → 全链注册；本 wave 结束即示例值污染消除、legacy 数据可读"
    },
    {
      "wave": 3,
      "name": "前端共享引擎 + 三个组件 + E0-6 符合度核查",
      "tasks": ["6", "7", "17"],
      "parallel": false,
      "rationale": "声明式 spec 与共享 composable 先就位，三个新组件再套壳；Task 17 是对已落地的 E0-6 组件做符合度核查并按需在其内部复用共享引擎（不换 componentType）"
    },
    {
      "wave": 4,
      "name": "上游取数（E1-3→E0-3 / F3-2→E0-5）+ 勾稽 + 完整性红线 + AI/导入导出",
      "tasks": ["8", "15", "9", "16", "18", "10", "11"],
      "parallel": true,
      "rationale": "七项互不依赖：两条取数各只影响一张表（E0-3←E1-3 / E0-5←F3-2）；三个只读派生（Task 16 消费 Task 15 的 prefill 故排其后；Task 18 的 E0-3 完整性红线可消费 Task 8 的 E1-3 发生额，取不到则 skip）；AI 与导入导出各自独立"
    },
    {
      "wave": 5,
      "name": "实测与收口",
      "tasks": ["12", "13"],
      "parallel": false,
      "rationale": "实测在全部实现之后；CI 与复盘最后登记"
    }
  ]
}
```

## Wave 1 — 源模板事实固化 + 平台级污染面盘查

- [x] 1. `backend/tests/test_e0_send_list_source_facts.py`（openpyxl 直读，三向比对）
  - 读 `backend/wp_templates/E/E0 货币资金 - 函证（Leap应对措施-函证）.xlsx`（**跳过 `~$` 锁文件**；先比对与参考副本的 size，运行时权威只认 `backend/wp_templates/`）
  - 钉死四张 sheet 的**真实 tab 名**、表头行号、列数、逐字标签：
    `货币资金发函记录表E0-3`(R5, 16 列 A~P) / `借款发函记录表E0-4`(16) /
    `应付银行承兑汇票发函记录表E0-5`(10) / `理财产品发函记录表E0-6`(R5, 11 列 A~K)
  - 钉死 **E0-3 与 E0-4 两张表**的 `E` 列 `hidden=True`（原只钉 E0-3，2026-08-02 复核发现 E0-4 同样隐藏）；
    DV：E0-3 仅 `L6:L26 O6:O26` = `"是,否"` / **E0-4 零 DV** / **E0-5 零 DV** / E0-6 仅 `K6:K10`
  - 钉死 **E0-5/E0-6 表头无 `是否函证` 列 且 `hidden cols == {}`**（Property 11 的源模板侧证据）
    - 🔴 **「列被隐藏」与「列不存在」必须分别断言**：E0-3/E0-4 是隐藏（Excel 列字母 D→F 跳号，
      肉眼数只有 15 列，用户截图即如此），E0-5/E0-6 才是真的没有该列。混成一种会让
      `hasConfirmFlag` 判错 → E0-3/E0-4 丢门控 或 E0-5/E0-6 恒 0 候选
  - 钉死四张表的 `dims` / 数据区行范围 / `print_area`（R3.2 实测值）：
    E0-3 `A1:S26`·R6:R26·`$A$1:$P$29`（`max_col=19` 但 Q/S/T 仅列宽残留）/
    **E0-4 `A1:P20`·R6:R20(15 行)·`$A$1:$P$21`** / E0-5 `A1:J20`·R6:R20·`$A$1:$J$21` /
    E0-6 `A1:K20`·R6:R20·`$A$1:$K$20`；断言这些空白行**带边框但无值**（打印骨架非数据）
  - 钉死 **E0-4 R16 的孤立残留 `G16=0 / H16=0`**（源模板残留数据行）——
    Task 4 的迁移与 Task 12 的实测都要按空行处理，**不得产出一条借款记录**；
    **反向自检**：让迁移把它转成一行必红
  - 钉死 E0-3 三列公式目标：`D←'…(仅人民币)E1-3'!$A` / `G←$C` / `K←$K`，以及行映射跳过 22/26
  - 钉死四张表**均无合计行**
  - 三向比对：源 xlsx 表头 ↔ `e0_send_list_source_manifest.json.cell_columns` ↔ `E0.yaml` 的 `dynamic_table.columns`
  - **反向自检**：把某列 label 改一字必红；把 E0-5 加上 `is_confirm` 必红
  - 另钉死 **E0-5 的归属裁决**：`底稿目录` F8=`E0-5` ↔ E8=`应付银行承兑汇票发函记录表`；
    工作簿里确有两张 tab 以 `E0-5` 结尾；**核对表在底稿目录里无索引号**且其 `T3=底稿目录!F9`（得 E0-6）是误引
    —— 与 `backend/tests/test_e0_source_template_facts.py` 已有的断言保持一致，不重复实现、只交叉引用
  - _Requirements: 1.3, 6.1, 6.2, 6.5, 6.6, 10.3, 12.1, 12.2, 12.5_

- [x] 2. E1-3 两版结构守卫 + 平台级污染面诊断脚本
  - `backend/tests/test_e1_3_segment_facts.py`：读 `E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx`，
    钉死两版 sheet 名、段头文字（`银行：` / `其他金融机构（存放财务公司款项）：` / `其他货币资金：`）、
    段内明细行区间（仅人民币版 13:21 / 23:25 / 27:33；人民币及外币版 13:17 / 19:21 / 23:28）、
    小计行文字、`（二）应计利息` 段起点、以及 design §`E1_3Variant` 声明的两组列语义
  - **反向自检**：把段头判定改成按行号必红；把「应计利息」段纳入必红
  - **🔴 grid 兜底有两类互相独立的污染，诊断脚本必须分别统计（2026-08-02 实测）**：
    **(a) 缓存示例值**（本 spec R2 的 P0）：`extract_grid` 用 `data_only=True` 读到公式的缓存值，
    E0-3 的 `D6:D24` 引用外部工作簿 `'[43]…E1-3'!$A` → 前端出现 19 行 `XX银行`/`XX财务公司`。
    **(b) 列头行被裁掉**：`strip_standard_header` 旧判据按整行子串命中「截止日」，
    而四张清单列头含**「报表截止日」** → 列头行连同上方全部被删，E0-4 只剩一张无表头空网格、
    E0-5/E0-6 直接 `cells=0`。**(b) 已于本轮修复**（判据改「关键词锚定标签 + 短标签形态过半」，
    关键词表不扩充以保证是旧判据真子集；全量 characterization 2722 sheet → 503 张少删 / 0 张多删；
    `test_wp_grid_extract.py` 31→52 例）。
    → 诊断脚本对 (a) 统计「命中格数」，对 (b) 统计「被裁行是否为列头行」，**两列分开报**；
    否则修好 (b) 之后 (a) 的数字会被误读成"污染变多了"（列头复活后可见格数必然上升）。
  - `backend/scripts/diagnose/diagnose_grid_fallback_cached_values.py`（**只读，只报告不改**）：
    扫 `workpaper_sheet_classification` × `backend/wp_templates/`，统计有多少 sheet 会走
    `extract_grid` 兜底（componentType ∈ `_ONLYOFFICE_HTML_WHITELIST` 且 ∉ `RENDERER_DISPATCH`）
    且其模板对应 sheet 的数据区含公式缓存值 → 输出 wp_code/sheet/命中格数清单（`--out` 自己写盘，禁 PS 重定向）
  - 结论写入本文件 Notes，供后续独立 spec 决策；本 spec **不**批量修
  - `backend/tests/test_f3_2_notes_source_facts.py`：读 `backend/wp_templates/F/F3 应付票据.xlsx`，
    钉死 `明细表F3-2` 两级表头 R13:R14 逐字 19 列（含 `是否函证`/`票据保证金比例`/`保证金金额`）、
    合并区 `D13:F13 票据关系人` + `G13:I13 票据期限`、派生公式 `O=L+M-N` 与 `R=O+P+Q`、
    `R9` 含「承兑保证金……与其他货币资金科目勾稽」原文；
    以及 `逾期票据检查F3-5` 的 R5:R6 列集（含 `期后支付金额`/`抵押情况`）
  - **反向自检**：把 `是否函证` 从期望列集删掉必红（防「E0-5 没有函证列 ⇒ 上游也没有」的误判复活）
  - _Requirements: 2.5, 4.2, 4.3, 12.3, 12.4, 12.9_

## Wave 2 — 后端 componentType 落地（解 P0）

- [x] 3. `backend/app/services/e0_send_list/`
  - `send_list_specs.py`：四张 sheet 名常量、`FORMAT_VERSION` 四条、`column_map(sheet)` / `fields(sheet)`
    —— **直接读 `e0_send_list_source_manifest.json`，禁抄第二份列表**
  - `e1_3_segments.py`：`E1_3Variant` dataclass + `E1_3_CNY` / `E1_3_FX` 两个声明 +
    `SEGMENT_HEADS` / `EXCLUDED_ROWS` / `INTEREST_SECTION_HEAD` +
    `split_segments(rows)` 纯函数 + `account_subject_of(head)`（银行/财务公司 → `1002`；其他货币资金 → `1012`）
  - 单测 `test_e0_send_list_specs.py` + `test_e1_3_segments.py`：切段只出明细行（Property 7）、
    含 **PBT**（随机插入小计行/空行/应计利息段，断言输出恒不含它们）
  - _Requirements: 4.2, 4.3, 4.8_

- [x] 4. `backend/app/routers/wp_render_strategies/_e0_send_list.py`
  - `_initial_data(sheet)` → `{_format, rows: [], conclusion: {audit_explanation, overall_conclusion, remarks}}`
  - `migrate_legacy_grid_payload(sheet, legacy)` 纯函数：
    已有正确 `_format` → 原样返回（幂等）；legacy grid（有 `cells`/`column_meta`/`header_rows` 而无 `_format`）
    → 按 `column_map` 转业务键 dict 行；保留 `_row_id`；`conclusion` 三键原样搬；
    manifest 未声明的列字母收进 `row['_unmapped_cells']`（**不静默丢弃**）
  - 四个 `render_e0_send_list_e0X(ctx)`：持久化 → 迁移；无持久化 → `_initial_data`；**任一环异常 fail-open**
  - **源码不得出现 `extract_grid` / `data_only`**（Property 3）
  - `test_e0_send_list_render.py`：初始 `rows == []` 且序列化不含 `XX银行`/`XX财务公司`（Property 2，
    **反向自检**：以模板缓存值构造 fixture 必红）；迁移幂等 + 零丢数 + **PBT**（Property 5）；
    render 不产生写操作（Property 6）
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 5. componentType 全链注册 + 平台级认领完备性守卫（**前置：Task 14**）
  - `RENDERER_DISPATCH` 注册**三条**；`wp_classification_service` 的 VALID 集合补三条
  - 🔴 **E0-6 不在本任务范围**：`confirmation-wealth-list` 已在四处注册齐备（实测），
    本任务 SHALL NOT 新建 `confirmation-send-list-e06`、SHALL NOT 改它的 override 双键与
    `_FORMAT['confirmation-wealth-list'] == 'wealth-list-v1'`；守卫改为**正向断言这三件事不变**
    （Property 25，含反向自检：任一处改成 `send-list-e06` 必红）
  - `wp_code_overrides.json`：短键 `E0-3`/`E0-4` + **全名 sheet 键** 三条；
    **`E0-5` 只登记全名键 `应付银行承兑汇票发函记录表E0-5`**（一码两表，短键会误命中
    `银行函证其他信息核对表E0-5`；后者 `T3=底稿目录!F9` 得 `E0-6` 是误引）
  - 🔴 **该登记只在 Task 14 落地后才生效** —— 改造前查表是尾码优先，`E0-5` 短键（现为
    `d-form-table`）会先命中、全名键永不被查到。Task 14 未完成时本任务的 E0-5 部分 SHALL 阻塞，
    不得先登记再"以为生效"（守卫须断言 `resolve_sheet_override` 在全名与尾码同时存在时取全名）
  - `test_e0_send_list_registration.py`：四处交叉一致 + **反向自检**（删任一处必红）+ Property 17
  - **平台级** `test_confirmation_component_backend_claimed.py`：前端 `htmlRendererRegistry` 的所有
    `confirmation-*` ⊆ (`RENDERER_DISPATCH` ∪ `_CONFIRMATION_COMPONENTS`)；豁免逐条登记理由
    （`confirmation-hub` 是 workbook 级 placeholder）；**反向自检**（从后端两处删一个 key 必红）
    - 依据：未被认领的 componentType 会在 `wp_render_config.py:859` 被改写成 `onlyoffice-sheet`，专属组件永不渲染
  - 断言 `e0_send_list_source_manifest.json` 的列数与 `field` 集合逐字节未变（Property 18）
  - _Requirements: 2.4, 10.1, 10.2, 10.3, 10.4, 10.5, 4.9_

- [x] 14. `E0-5` 一码两表：**只加守卫，不改查表顺序**（原「改顺序」方案已作废）
  - **✅ 待裁决 2 已关闭（2026-08-02，随裁决门 A = A-否）**：实证 `wp_render_config.py`
    的两条判定顺序**相反**，当前配置**已经正确**，方案 A（翻转查表顺序）与方案 B（删短键）
    **都不需要做**：

    | 判定 | 行 | 匹配方式 | 对两张 `E0-5` 的作用 |
    |---|---|---|---|
    | skip | L709 | **完整 sheet_name 精确** | `银行函证其他信息核对表E0-5` → `skip` → `continue`，**永不进入下方解析** |
    | skip | L722 | 尾码 `_SHEET_CODE_RE` | 尾码 `E0-5` 取值非 `skip` → 不拦 |
    | componentType | L749~758 | **尾码优先**，全名与 `{wp_code}-{sheet_name}` 作 fallback | `应付银行承兑汇票发函记录表E0-5` → 尾码 `E0-5` → 取值 |

    → 本 spec 把短键 `E0-5` 改成 `confirmation-send-list-e05` 后仍然安全（核对表已在 L709 被拦）。
    **原「Task 5 的前置」关系解除** —— Task 5 可直接推进，不再被本任务阻塞。

  - **改为落一条不变式守卫**（这是当前配置正确的**唯一支点**，必须钉死）：
    > `银行函证其他信息核对表E0-5` 的**完整 sheet_name** `skip` 条目 SHALL NOT 被删除或改值。
    > 一旦删除，该 hidden sheet 会在 L749 按**尾码**解析成 `confirmation-send-list-e05`，
    > 渲染出一个列集完全不符的多余页签（10 列核对表被当成 10 列票据清单）。
  - `backend/tests/test_sheet_override_resolution.py`：
    ① 断言全名 `skip` 条目存在且值为 `skip`（**不接受"尾码也指向 skip 所以没事"** ——
       本 spec 正是要把尾码改成非 skip 值）
    ② 影响面钉死 —— 全库 classification sheet 名中「同时命中全名键与尾码键且取值不同」
       的集合 == 已知 2 条（`银行函证其他信息核对表E0-5`、`长期应付职工薪酬实质性程序表 L2A`，
       两者全名值均 `skip`）；集合变大即红，迫使重新评估是否又出现了新的一码两表
    ③ **反向自检** —— 用**与任何真实循环无关的替身** sheet（如 `替身核对表XX-9` + `替身清单XX-9`）
       断言「全名 `skip` 在，则该 sheet 不渲染；全名 `skip` 移除，则按尾码解析」
    ④ **不动 `skip` 过滤路径的实现** —— 只加断言，不重构 L709/L722/L749 三处
       （误改会让 `长期应付职工薪酬实质性程序表 L2A` 之类历史遗留表重新出现）
  - 🔴 **与 `e0-confirmation-completion` 的 Task 19 是同一条不变式**：
    两侧 SHALL 择一实现、另一侧在 Notes 引用文件路径，**不得各写一份**
    （各写一份 → 改一处另一处不红，等于没守卫）。
    建议由**本 spec 实现**（它才是把尾码值从 `d-form-table` 改成 `confirmation-send-list-e05`、
    真正让这条不变式变关键的一方），那边引用。
  - ~~方案 A：抽纯函数 `resolve_sheet_override(...)` 翻转顺序~~ / ~~方案 B：删短键~~
    **均已作废**（当前顺序恰好正确，改动只会引入回归风险）
  - _Requirements: 10.3, 15.1, 15.2, 15.3, 15.4, 15.5_

## Wave 3 — 前端共享引擎 + 四个组件

- [x] 6. `confirmation/e0-send-list/` 声明式 spec + 共享引擎
  - `sendListSpec.ts`：`SendListColumn` / `SendListSpec` / `SEND_LIST_SPECS`（四条）；
    `hasConfirmFlag`（e03/e04 true、e05/e06 false）、`supportsPrefill`（仅 e03）、`columnToggle`（e03/e04）；
    `account_type` 枚举标 `platformEnhanced: true`；**e03 与 e04 的 `is_confirm` 都标 `sourceHidden: true`**
    （两表源模板 `E: hidden=True`；原设计只标 e03，会让 e04 的「源模板隐藏、平台显式化」差异无登记）
  - `useSendListData.ts`：`rows` / `addRow` / `removeRow` / `moveRow` / `visibleColumns` /
    `conclusion` / `buildPayload` / `hasUnmappedCells`
    —— `_row_id` 稳定键、不预置空行、删行清全字段、**`_prefill` 不进 payload**
  - `SendListTable.vue`：13px、枚举 `el-select`、日期 `el-date-picker`、`render:'amount'` 走 `WpAmountInput`、
    金额右对齐 `tabular-nums`、⚙ 列显隐、`hasUnmappedCells` 时提示条
  - **交叉锁死守卫** `sendListSpec.spec.ts`：`fs.readFileSync` 读后端 `e0_send_list_source_manifest.json`
    逐字比对 `(cell, field, label, type, enum)` 五元组序列（Property 1）；
    Property 11（`hasConfirmFlag` 四值 + e05/e06 无 `is_confirm` 列）；
    Property 12（`sourceHidden`/`platformEnhanced` 正向断言，且 **`sourceHidden===true` 的表恰为 `{e03,e04}`**、
    `hasConfirmFlag===false` 的表恰为 `{e05,e06}`；反向自检：e04 去掉 `sourceHidden` 必红 / e05 加上必红）；
    Property 14（`WpAmountInput` 覆盖金额列 + `interest_rate`/`holding_shares` 反向断言 +
    `el-input-number :formatter` 计数 0）
    - 🔴 `REPO_ROOT` 回退层数按 `confirmation/e0-send-list/__tests__/` 实际深度算，别照抄别处
  - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 3.1, 3.3, 3.4, 6.1, 6.2, 6.3, 6.4, 6.6_

- [x] 7. 三个组件 + registry 注册（E0-6 见 Task 17）
  - `GtE0SendListE03.vue` / `E04` / `E05`：套 `SendListTable` + 审计说明/结论两 `el-card`
  - `htmlRendererRegistry.ts`：union type 三条 + entry 三条（icon/label，如 `✉️ 发函清单(货币资金)`）
  - 宿主链路核查：`GtWpRenderer` 按 per-sheet componentType 分发 → 确认 `html-data` / `project-id` / `wp-id`
    三个 prop 都传到（漏传 `projectId` 是平台已知静默锁死形态）；守卫扫模板断言三个 prop 已传
  - 组件挂载 smoke 测（对齐 `alternativeCallerMount.smoke.spec.ts`）：挂载不抛 + legacy `htmlData` 载入 +
    `buildPayload()` 的 `_format` 正确 + 不含 `_prefill`
  - 🔴 自检三条只有浏览器才暴露的坑：`fmtAmount` 必须走 `displayPrefs.fmtAmount`（store 成员非模块导出）；
    `watch(` 引用的顶层 const 声明行号必须更小（TDZ）；组件解构的 composable 返回值必须真存在
  - _Requirements: 1.1, 8.1, 10.1_

- [x] 17. E0-6 已落地组件符合度核查（**不换 componentType**）
  - 逐条比对 `confirmation/wealthList/GtConfirmationWealthList.vue` 与本 spec 的
    R1.3~R1.7 / R2 / R3 / R6.5 / R8 / R9，产出「已满足 / 需补 / 有意差异」三分类清单写进 Notes
  - 重点核 8 项（都是本 spec 对另外三张表的硬要求）：
    ① 11 列 `field`/`label`/`type`/`enum` 是否逐字对齐 `e0_send_list_source_manifest.json`
    ② 初始载荷 `rows: []` 且不含 `XX银行` 类示例值（E0-6 源模板 R6:R20 全空，预期本就干净）
    ③ 动态行且**不预置空占位行**（源模板 15 行空白是 `print_area` 打印骨架）
    ④ `K` 列 `是否被用于担保或存在其他使用限制` **整列启用下拉**（源模板 DV 只到 `K6:K10` 属残缺，
       R6.5 要求整列，不得照抄残缺范围）
    ⑤ `产品净值`(H) 用 `WpAmountInput`；`持有份额`(G) **不得**套金额控件（它是份数不是金额）
    ⑥ 零 `el-input-number :formatter`（EP 2.13.6 无该 prop）
    ⑦ 审计说明/结论两区 + AI 辅助 + 复核触发齐备
    ⑧ 导入导出（`el-dropdown「导入导出▾」`）+ 往返自检
  - **需补项 SHALL 在 `confirmation/wealthList/` 内部最小改动补齐**，含改用 Task 6 的
    `sendListSpec.ts` / `useSendListData.ts`（复用发生在组件内部）
  - **SHALL NOT** 新建 `confirmation-send-list-e06`、**SHALL NOT** 改 `wealth-list-v1`、
    **SHALL NOT** 改 `wp_code_overrides.json` 的 E0-6 双键
  - legacy 载荷零回归：实测项目 `1534c6e3-eab1-4bff-8ca8-9232691ba877` 的
    `理财产品发函记录表E0-6` 往返无损（改动前先快照）
  - _Requirements: 1.1, 1.1b, 6.5, 10.1, 10.4, 10.5_

## Wave 4 — E1-3 取数 + 受限勾稽 + 完整性红线 + AI / 导入导出

- [x] 8. E1-3 → E0-3 取数（后端 + 前端带入）
  - 后端 `build_e03_prefill(ctx)`：按项目实际存在的版本分支（`E1_3_CNY` / `E1_3_FX`）读上游 sheet 数据 →
    `split_segments` → 逐明细行输出 `{bank_name, account_holder, bank_account, currency, interest_rate,
    account_subject, amount_unaudited, amount_audited, amount_statement, restricted_amount,
    restricted_reason, _segment}`；两版都无数据 → `None`；**transient 挂 `_prefill`，fail-open**
  - 仅人民币版 `currency`/`interest_rate` 输出 `null`（该版无这两列，Property 8 宁缺勿造）
  - 前端 `sendListPrefillPlan.ts`：`AmountCaliber` 三态、`DEFAULT_AMOUNT_CALIBER='unaudited'`、
    `planSendListPrefill` **委托 `composables/shared/adjudicationPrefillPlan.ts`**（手工优先/幂等/
    `{creates, fills, conflicts, skipped}`）；匹配键 `bank_account`
  - `SendListPrefillPanel.vue`：「从 E1-3 带入账户清单」按钮 + 预览确认框 + 口径选择器 +
    **tooltip 明示「源模板 E0-3.K 原公式指向 E1-3.K 期末对账单余额」**（口径待用户确认）
  - 守卫：Property 8/9/10（含 PBT：随机已有值下 plan 幂等且不覆盖）；
    Property 10 的源模板事实由 Task 1 独立钉死，**不要求实现取 K**
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 9. 受限勾稽面板
  - `sendListConsistency.ts`：R1「E1-3 受限金额非零 → `has_restriction` 必须为是」(error) /
    R2「E0-3 有账号但 E1-3 无对应账户」(warning) / R3「E1-3 有账户但 E0-3 未列」(warning)；
    `prefill == null` → 全 skip（Property 13，**不拿空当零**）
  - 紧凑单行 bar + 可折叠明细 + 规则 tooltip + `GtIndexChip` 追溯（对齐 `h1DisclosureConsistency` 范式）
  - E0-6 的 `has_restriction` 一并纳入面板（只读校验；**写入 E1 归 `e0-confirmation-completion` Task 12**）
  - 不新增「受限金额」列（源模板未定义，既有守卫已禁）；受限原因落 `remark`
  - 追加 R4「F3-2 保证金金额合计非零 而 E0-5 对应票据行 `抵（质）押品` 为空」(warning)
    —— 依据是 `明细表F3-2` R9 源模板原文「复核其应存人银行的承兑保证金，并与其他货币资金科目勾稽」；
    该链路的**写入侧**（→ E1 受限货币资金 ②表「银行承兑汇票保证金」类别）归
    `e0-confirmation-completion` Task 12 扩围，本任务只出只读勾稽并在 Notes 记交接
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 15. F3-2 → E0-5 取数（后端 + 前端带入，与 Task 8 对称）
  - 后端 `services/e0_send_list/f3_2_notes_source.py`：
    `F3NoteRow` dataclass（字段名对齐 `composables/useF3Detail.ts`：`ticketNo/noteType/acceptor/`
    `issueDate/dueDate/faceValue/depositAmount/depositRatio/isConfirmed`）+
    `select_bank_acceptance_to_confirm(rows)` → `(命中行, hints)`：
    只取 `isConfirmed=='是'` **且** `'银行' in noteType`（复用 F3 侧口径，不另写一份）；
    **供应链票据不进结果、只进 hints**（承兑人可能是平台/保理公司 = 会计判断）
  - `build_e05_prefill(rows, caliber)` → `E05Prefill | None`：
    字段映射 `bill_no←ticketNo` / `bank_name←acceptor` / `face_amount←faceValue`（或 `期末审定数`）/
    `issue_date←issueDate` / `due_date←dueDate` / `deposit_amount`+`deposit_ratio`；
    **`settle_account` 与 `currency` 恒 `None`**（F3-2 无这两列，宁缺勿造）；
    另下发 `tb_2201`（trial_balance 科目 2201，取不到则 null）与 `bank_unconfirmed_count`（供 R14.5）
  - render 侧挂 transient `_prefill`（形态见 design §transient prefill 的 E0-5 同构块），**fail-open**
  - 前端「从 F3-2 带入承兑汇票清单」按钮 + 预览确认 + 口径选择器（`face` 默认 / `audited`），
    **委托 `composables/shared/adjudicationPrefillPlan.ts`**（手工优先/幂等/仅补空值），匹配键 `bill_no`
  - hints 以提示条呈现（如「F3-2 含 N 张供应链票据未自动带入，承兑人是否为银行需人工判断」）
  - 上游无数据或无命中行 → 提示「上游 F3-2 暂无待函证的银行承兑汇票」+ 零写入
  - 守卫：Property 19（只取银承且已函证，**反向自检**去掉 `noteType` 过滤必红）、
    Property 20（`settle_account`/`currency` 恒 null）、带入幂等 PBT
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_

- [x] 16. E0-5 质量红线 + 一函多票分组（**消费 Task 15 的 prefill**）
  - `sendListE05Checks.ts`：
    `groupByIndexNo(rows)` —— 按 `index_no` 归组 + 组内票面金额小计，**展示层派生**，
    `buildPayload()` 的 `rows` 仍是扁平数组且 `_row_id` 顺序不变（Property 22）
    - 依据：`E0-1!F8` 的应付票据分支是 `SUMIF(E0-5!$A:$A, E0-1!$B, E0-5!$G:$G)`，四张清单里唯一单条件按索引号求和
    `checkE05Completeness(rows, f3Prefill, tb2201)` —— 三方勾稽：
    `Σ(E0-5 票面金额)` ↔ `Σ(F3-2 银承待函证审定数)`（不等 error）↔ `trial_balance 2201`（差异 warning + 可填说明）；
    **任一不可得 → 该项 skip，绝不拿 0 比较**（Property 21）
    `checkE05TicketNo` —— 票号唯一性 error + 与 F3-2/F3-5 一致性 warning（账面未登记 / 可能漏函）
    `checkE05Tenor(rows, cutoffDate, policy)` —— 已到期未兑付（与 F3-5 交叉提示）/ 期限异常；
    🔴 `TenorPolicy.maxTenorDays` 按会计期间可配置，**源码禁出现字面月数**（Property 23，
    含反向自检：注入不同阈值同一行标记结果须改变）
  - UI：紧凑单行 bar + 可折叠明细 + 规则 tooltip + `GtIndexChip`（对齐 Task 9 面板范式，两者同屏不重复造）；
    页头「F3-2 银承未函证 N 笔」反向提示 + 审计说明模板固化
    「本表为已决定函证的全部银行承兑汇票，未纳入函证的票据及理由见 F3-2『是否函证』列」（R14.5）
  - `抵（质）押品` 保持单列不拆，保证金以**展开行或 tooltip** 呈现「保证金金额 / 比例 / 其他质押物文本」（R14.6）
  - 全部只读派生，**不阻断保存**
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

- [x] 18. E0-3 函证范围完整性红线（R16）+ 资金归集列标注（R17）
  - 新建 `sendListScopeChecks.ts`（纯函数）：`checkSendScopeCompleteness(rows, ctx)` 三条红线
    ① 零余额（`账户余额（原币）` == 0，空值不判定）未勾函证且 `备注` 无理由 → **error**
    ② `终止日期` ∈ [periodStart, periodEnd]（**本期内注销**）未勾函证且无理由 → **error**
      （`终止日期` 为空视为存续，不判定）
    ③ 本期发生额 ≥ 重要性水平 且 余额 < 重要性水平 且未勾函证 → **warning**
      （发生额来自 Task 8 的 E1-3 prefill；取不到 → 该项 `skip`，**绝不拿 0 当发生额**）
  - 源模板依据就地展示（琥珀色左边线范式）：`E0A` 程序 1「包括零余额账户和在本期内注销的账户」+
    `E0-1!O28/O29` + `回函情况汇编` 编制说明 2/3；并提供「E0-1『二、样本选择』需汇总记录
    不执行函证程序的理由」跳转（`unconfirmedAccounts()` 给清单）
  - 🔴 **阈值禁写死**：只从 `ctx.materiality`（优先取项目重要性水平 B15）/ `ctx.threshold` 取，
    源码不得出现金额字面量常量（Property 27）；红线全部只读派生，**不阻断保存**
  - `L` 列「是否属于资金归集（资金池或其他资金管理）账户」标注为风险标记 + 列 tooltip 写
    `E0A` 程序 2 原文；**不实现**与核对表「15.附表(资金归集)」的勾稽（R17.2，核对表隐藏且
    override 为 `skip`，落点未裁决）→ 在 Notes 登记遗留与触发条件
  - 单测含 **PBT**（Property 26）：随机行集下 skip-on-missing 恒成立、无 `NaN`/`Infinity`、
    `checkSendScopeCompleteness([], null)` 全 `skip`；含反向自检（去掉「已填理由降级」必红）
  - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 17.1, 17.2, 17.3_

- [x] 10. 审计说明/结论 + AI 辅助 + 复核触发
  - 四张组件各两个文本区（`el-card` 包裹）+ 🤖 AI + 💬 `GtReviewTrigger`，`:loading` + `:disabled="isReadonly"`
  - AI 走 `POST /api/workpapers/{wpId}/ai/generate-text`，body `{section, prompt, context: dict[str,str],
    existingContent}`（驼峰；`context` 值全 `String()` 化否则 422），读 `(res.data?.data ?? res.data)?.content`
  - 后端 `review_dialog._SECTION_PROMPTS` 补 8 条（4 表 × 说明/结论），每条写明源模板口径 + 「不得虚构」
  - 守卫 `sendListAiWiring.spec.ts`（Property 15）：文本区键集 ↔ 后端 prompt 交叉（无缺无余）、
    `context` 非字符串、驼峰 `existingContent`、`handleAi*` 函数体 `stripComments()` 后
    不得只含 `emit('save'` / `console.log`（marker stub 检测）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 11. 导入导出
  - 后端 `_e0_send_list_import_export.py`：列映射**读 `E0.yaml` 的 `dynamic_table`**（`start_row`/`header_row`/
    `columns`），禁另写列表；分派挂既有 E0 路由，`sheet` 参数区分四张表
  - 前端 `el-dropdown「导入导出 ▾」`（导出模板 / 导出数据 / 导入数据）；导入部分失败必须明示失败项
  - **往返自检**（Property 16）：导出模板 → 立即经导入校验器 → 无「缺少列」
    （防 openpyxl 纵向合并清空第二行表头导致"导入自家模板失败"）
  - 守卫断言前端未另写一份列映射
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

## Wave 5 — 实测与收口

- [x] 12. 浏览器 + 真实 DB 实测 + 数据复原（**需启动 dev server**）
  - 目标项目 `1534c6e3-eab1-4bff-8ca8-9232691ba877`（重药控股安徽_2025，E0 底稿）——
    它同时具备两个验证条件：E0-3~E0-5 无持久化（验空表）+ E0-6 有 legacy grid 载荷（验迁移）
  - **先快照**：`parsed_data.html_data` 全量 + md5
  - 逐张打开 E0-3/E0-4/E0-5/E0-6：挂载、零 console error、**界面不再出现 `XX银行`/`XX财务公司`**（R2 验收核心）
  - E0-6：验 legacy 载荷往返无损（`_row_id` 保留、`conclusion` 三键保留、无 `_unmapped_cells` 丢数）
  - 动态行增删改序；枚举列 `el-select` 点选；日期列 `el-date-picker`；
    金额录 `1234567.5` → 显示 `1,234,567.50`；`el-input-number` 计数 **0**
  - E0-3：点「从 E1-3 带入账户清单」→ 验段语义只带明细行（无小计行、无应计利息段）、
    口径切换三态、手工优先不覆盖、二次带入幂等；上游无数据时提示且零写入
  - 受限勾稽：构造「E1-3 有受限金额 + E0-3 标否」→ 验 error 一条；`prefill` 为空 → 全 skip 无 error
  - E0-5：点「从 F3-2 带入承兑汇票清单」→ 验只带「银承 + 是否函证=是」的行（商承/供应链不在结果里、
    供应链出 hints 提示）、`settle_account`/`currency` 留空、口径切换两态、手工优先不覆盖、二次带入幂等；
    F3-2 无命中行时提示且零写入
  - E0-5 红线：一函多票按索引号分组 + 组内小计正确（构造同一索引号 3 张票，验小计 = 三票之和且
    `buildPayload().rows` 仍是 3 条扁平行）；票号重复 → error；构造已到期票据 → 「已到期未兑付」标记；
    三方勾稽在 `tb_2201` 取不到时该项显示 skip 而非 0 差异
  - 保证金勾稽：构造「F3-2 保证金非零 + E0-5 抵（质）押品为空」→ 验 warning 一条
  - AI 按钮 8 个：验真实发请求（200）、`context` 非 422、生成文本不虚构
  - 导入导出：导出模板 → 原样导入 → 无「缺少列」；导出数据 → 改一格 → 导入 → 值正确
  - **按 md5 逐字节复原**；不可复原字段如实记录；清理 `tmp_*`
  - _Requirements: 5.6, 12.6, 12.7_

- [x] 13. CI 登记 + 复盘
  - CI job `e0-send-list-source-facts`（后端：openpyxl 三向守卫 + E1-3 段结构 + 切段 PBT +
    **F3-2/F3-5 列集守卫** + render/迁移 + 注册交叉 + **override 查表顺序影响面** + 平台级 confirmation 认领完备性）
  - CI job `e0-send-list-frontend`（前端：spec 交叉锁死 + 组件 smoke + 带入 plan PBT + 勾稽 +
    **E0-5 红线与分组** + AI 接线 + 导入导出）
  - `yaml.safe_load` 校验 CI 文件；确认引用路径存在
  - 复盘写回 Notes：源模板自身缺陷清单、K 列口径裁决结论、Task 2 污染面盘查结果、
    遗留项与归属（尤其与 `e0-confirmation-completion` 的交接状态）
  - _Requirements: 12.8_

## Notes

### 本 spec 的来源调查（2026-08-02，只读，零代码改动）

四层现状：列定义 ✅ / HTML 渲染 ❌ / 取数 ❌ / 公式预设 ❌（后者归 `e0-confirmation-completion` Task 14）。
详细证据见 design.md 的「平台侧基线」表与 `.kiro/steering/memory.md` 的
「E0-3 货币资金发函记录表复盘（2026-08-02）」小节。

### E0-5 补充调查（2026-08-02 第二轮，只读，零代码改动）

推翻/加强了三处原判断，证据与结论已写进 requirements Introduction 第 6/7 条、R6.2、R10.3、design Notes：

1. **E0-5 的上游是 `明细表F3-2`，「是否函证」列就在那里** —— R6.2 原写「筛选动作发生在 E0-3/E0-4 内」
   对 E0-5 不成立。F3-2 两级表头含 `是否函证`/`票据保证金比例`/`保证金金额`，平台侧
   `useF3Detail.ts` 字段已齐、`F3TabDetail.vue` 已算 `bankUnconfirmed` → Task 15 是加法式接线，不是从零建。
2. **override 的两条判定顺序相反** —— skip 走 L709 **全名精确优先**，componentType 走 L749 **尾码优先**。
   → 原判断「必须翻转查表顺序」**已作废**：`应付银行承兑汇票发函记录表E0-5` 本就靠尾码命中，
   而 hidden 的核对表被 L709 的全名 `skip` 拦在前面。**当前配置已正确**，
   Task 14 降级为「只钉死全名 `skip` 不变式」且不再阻塞 Task 5。
   实测影响面全库只有 2 张一码两表 sheet，两者全名值都是 `skip`。
3. **承兑保证金 → 其他货币资金勾稽是源模板明写的要求**（F3-2 R9 原文），
   现状 F3/E1 两侧都只有横幅文字、零数据联动 → Task 9 的 R4 规则 + `e0-confirmation-completion` Task 12 扩围。

同轮已独立落地（不属本 spec，避免重复实现）：`importE0ListsToSummary` 的 E0-5/E0-6 取数口径已按
`E0-1!F8` 重写（一函多票按索引号求和、无「是否函证」列不设门、去重键含 `account_no`、兼容
`wealth-list-v1`），并新增 `backend/tests/test_e0_source_template_facts.py`(24 例) 钉死 E0-5 归属裁决；
`wp_account_mapping.json` 的 E0-3/E0-4/E0-5 D0 口径错名已修（幂等脚本 `fix_e0_wp_account_mapping.py`）。

### 待用户裁决

1. **K 列金额口径**（R4.5 / Property 10）：默认「期末余额（未审）」是本 spec 的判断，
   源模板原公式指向的是「期末对账单余额」。默认值需确认。
2. ~~**E0-5 一码两表的 override 消歧走 A 还是 B**~~ —— **已关闭（2026-08-02，随裁决门 A = A-否）**
   实证 `wp_render_config.py` 的两条判定顺序**相反**，当前配置已经正确：
   - **skip 判定 L709**：按**完整 sheet_name** 精确匹配 → `银行函证其他信息核对表E0-5` → `skip` → `continue`
   - **componentType 判定 L749**：按**尾码**优先（全名与 `{wp_code}-{sheet}` 作 fallback）
   → 核对表在 L709 就被拦下，**永不进入** componentType 解析；
   本 spec 把短键 `E0-5` 改成 `confirmation-send-list-e05` 后仍然安全。
   **无需改查表顺序（原方案 A），也无需删短键（原方案 B）** → **Task 14 降级为「只加守卫」**。
   守卫内容 = 「`银行函证其他信息核对表E0-5` 的**全名** `skip` 条目不得删除或改值」
   —— 一旦删除，该 hidden sheet 会在 L749 按尾码解析成 `confirmation-send-list-e05`，
   渲染出一个列集完全不符的多余页签。
   🔴 这与 `e0-confirmation-completion` 的 **Task 19** 是**同一条不变式**，
   两侧 SHALL 择一实现、另一侧引用，**不得各写一份**（否则改一处另一处不红）。

3. **E0-5 带入金额口径**（R13.5）：默认 `票面金额`（与 E0-5 表头同名同义），可切 `期末审定数`。默认值需确认。
4. ~~**隐藏底稿三张的去留**~~ —— **已裁决 A-否（2026-08-02 用户原话：「三张隐藏底稿不需要再实现了，已隐藏」）**
   `银行函证其他信息核对表E0-5` / `邮件传真回函核对记录F1-12` / `回函情况汇编`
   经 `sheet_state` 实证均为 **hidden**，override 已置 `skip` 且该 `skip` 走全名精确匹配、**确实生效**；
   `底稿目录` D9:F11 索引的 9 张底稿恰好 = 10 个 visible sheet 减目录本身，两者互为旁证。
   **对本 spec 的三处影响**：
   - **R17.2 / R17.3（E0-3 `L 资金归集` → 核对表「15.附表(资金归集)」的勾稽）永久留遗留**
     → Task 18 只做**列标注 + Notes 登记**，不做勾稽实现（对侧表不存在）
   - **Task 14 降级为「只加守卫」**（见待裁决 2）
   - `e0-confirmation-completion` 的 R1 / R7.1·R7.5 / R8.6 与其 Wave 6（13 要项表 ~39 KB）**已删除**；
     13 要项的口径存档在那份 spec 的 Requirement 1 与 design §1，将来若另立 spec 可直接取用

5. **E0-6 的 componentType 命名（本轮新增，建议直接采纳）**：并发会话已交付
   `confirmation-wealth-list`（全链 + 契约测试）。本 spec 原计划的 `confirmation-send-list-e06`
   **已撤回**，改为「保留 wealth-list + 符合度核查（Task 17）」。
   若用户坚持四张表命名一致（全部 `confirmation-send-list-e0x`），则需额外承担：
   改 `test_confirmation_sheet_override_contract.py`、`_format` 由 `wealth-list-v1` 换
   `send-list-e06-v1`（E0-6 legacy 载荷被迁移两次）、删除 `confirmation/wealthList/` 并重写。
   **收益仅"命名一致"，不推荐。**

### 本轮对 manifest 的变更备案（2026-08-02，与下方「明确不做」有交集，需接受或显式反驳）

「明确不做」原写「不改 `e0_send_list_source_manifest.json` 的 `field`/`label`/`type`」。
本轮**改了 E0-4 两列的 `type`**，依据是源模板公式（硬证据），`field`/`label` 逐字未动，
且 `E0.yaml` 同步更新、Task 1 的三向守卫仍可通过：

| 列 | 改前 | 改后 | 依据 |
|---|---|---|---|
| A 所属科目 | `text` | `enum ['短期借款','长期借款']` | `函证结果汇总表E0-1!F8` 的 `IF(OR(D8="短期借款",D8="长期借款")` 分支 + `E0-1（原）!S11/V11` 的 `SUMIFS(...,$A:$A,"短期借款"/"长期借款")`；「一年内到期的长期借款」并入长期借款，依据 `回函情况汇编!V9` 表头逐字「长期借款（含一年内到期的长期借款）函证情况」 |
| O 借款类型 | `enum` 4 项 | `text` | 该 sheet **零数据有效性**、`O6:O16` **全空**、**全工作簿无任何公式引用 `'借款发函记录表E0-4'!$O`**（openpyxl 逐格实证）→ 原枚举是把 A 列语义抄了一份的臆造，属违反「不臆造」铁律 |

A 列改 enum 的收益：它是 `E0-1!F` 的 `SUMIFS` 条件列，**选错值 → 发函金额恒 0 且无任何报错**，
枚举能把这种静默失败挡在录入阶段。新增守卫 3 例（`test_e0_send_list_columns.py`）：
E0-1 取数键三向断言（`$I:$I` 求和 / `$A:$A` 品种 / `$G:$G` 账号）、A 列枚举项必须在源公式里出现、
O 列不得声明枚举 + 三条反向自检（DV 为 0 条 / O 列数据区全空 / 全册不引用 O 列）。

**若本 spec owner 认为不应动 manifest**：请在 Task 1 里改为「A/O 列保持原样 + 把上述源模板事实
写进守卫注释」，但**不要恢复 O 列的 4 项枚举**（那是无源依据的臆造，会误导录入）。

### 另两条影响本 spec 的平台事实（2026-08-02 实测）

1. **`wp_render_schema/generated/` 运行时从不加载**：`WpRenderSchemaService._SCHEMA_DIR`
   = `backend/data/ledger_adapters/wp_render_schema/`（**不含 `generated/`**），且 `backend/app/**`
   全文无任何读 `generated/` 的代码。实测 E0 既无 `E0.yaml` 也无 `E-template.yaml`
   → render-config 里 **20 个 E0 sheet 的 `schema` 全为 `null`**。
   → 对 Task 11「列映射读 `E0.yaml` 的 `dynamic_table`」**无影响**（那是脚本按路径读文件，不是
   运行态 `load_schema`），但注释必须写明「E0.yaml 是数据文件、不是运行态 schema」，
   否则后人会以为 render 时能拿到 `dynamic_table`。
   → 也意味着归档 spec `e0-send-list-components`（12/12）审定的四张清单 16 列在**运行态从未生效**，
   本 spec 的专属组件是它真正落地的唯一路径。

2. **`fetchWorkpaperHtmlRows` 的 wp_code 解析断点**（`e0-confirmation-completion` Task 11 的前置，
   本 spec 是其上游）：多 sheet 工作簿的 sheet 不是独立 wp_code —— 实测 `wp_index` 里 5 个项目
   只有 2 个有 `E0-4`、`E0-6` 一个都没有，其余只有 `E0`。本 spec Wave 2 给四张表发了带 `_format`
   的专属载荷，解掉了「`hd._format` 匹配不上」那一半；**另一半（按 `E0-4` 查不到 wp_id）仍需
   下游按 `E0` + sheet_name 定位**。建议在 Task 5 的注册守卫里附一条断言：
   四个新 componentType 在**只有 `E0` 一条 wp_index 记录**的项目上也能被 render-config 输出到
   对应 sheet（防「组件注册了但下游按 wp_code 找不到」）。

### 明确不做

- 全库 grid 兜底示例值污染的批量修复（Task 2 只出诊断清单，供独立 spec）
- E0-3/E0-6 受限 → E1 的**写入**，以及 F3-2 承兑保证金 → E1 受限货币资金 ②表的**写入**
  （均归 `e0-confirmation-completion` Task 12；后者需该 spec 扩围，本 spec 只出只读勾稽）
- 四清单 → E0-1 带入纠偏（该 spec Task 11；E0-5/E0-6 口径本轮已独立修完，剩 E0-4「所属科目」分流）
- F3 循环侧的改动（F3-2 不新增列、不改其行模型）—— 本 spec 只**读** F3-2，写入侧属 F 循环 spec
- 账户/票据完整性的四方比对（含 ECDS 票号外部核验）—— 涉及外部数据源，够独立 spec
- 账户完整性四方比对（四表叶子 ∪ E1-10 央行清单 ∪ E0-3 发函清单 ∪ E0-3 回函）——
  审计价值最高但涉及新数据源，够独立 spec。**Task 18 的红线为它预留 `bank_account` 统一比对键**
- `e0_send_list_source_manifest.json` 的 `field`/`label` 修改（既有真源 + 12 组守卫）；
  `type` 已有两处备案变更（E0-4 的 A/O 列，见下方备案节）
- **新建 `confirmation-send-list-e06`**（E0-6 已有 `confirmation-wealth-list`，见待裁决 5 与 Task 17）
- **E0-3 L 列「资金归集」→ 核对表「15.附表(资金归集)」的勾稽**（R17.2；核对表隐藏且 `skip`，
  落点未裁决 → Task 18 只做列标注 + Notes 登记）
- **E0-4 P 列「期末应付利息」→ K3 应付利息底稿的勾稽** —— 源模板全册无下游引用
  （`E0-1` 只取 I 列），属"源模板未连线"，宁缺勿造；只保留录入位置。
  若将来 K3 有对应位置，可按 R7.5 范式做**只读**勾稽（不写入）
- **E0-3 I 列「利率(%)」→ E1-20 应计利息测算 / E1-30 存款规模与利息收入匹配性** ——
  方向是 E0-3 往下游推，而 E1-20/E1-30 属 `e1-orphan-components-wiring`（E1-30 是那边的孤儿组件之一）
  → 归该 spec；本 spec 只保证 `interest_rate` 可读（外币版由 E1-3 的 AL 列带入）

### Task 17 符合度核查结论（2026-08-03）

对 `confirmation/wealthList/GtConfirmationWealthList.vue` 逐条比对：

| # | 要求 | 结论 | 备注 |
|---|---|---|---|
| ① | 11 列 field/label/type/enum 对齐 manifest | **已满足** | `WEALTH_LIST_COLUMN_SOURCE` 11 项 label 逐字对齐源模板。field 命名不同（`confirm_index` vs manifest `index_no`）—— **有意差异**：wealth-list 有独立命名空间 + `_format='wealth-list-v1'` + 契约测试硬断言，不改 |
| ② | 初始载荷 `rows:[]` 且无示例值 | **已满足** | `isNewFormat` 判定 → 新格式走 Grid（空行）；源模板 R6:R20 全空无缓存值 → 天然无污染 |
| ③ | 动态行且不预置空占位行 | **已满足** | `useWealthListData.addRow()` 新增 |
| ④ | K 列整列启用（不照抄 DV K6:K10 残缺范围）| **已满足** | `WealthListGrid` 按列定义逐行渲染 select，不受 DV 限制 |
| ⑤ | `net_value` 用金额格式；`units_held` 不得套金额控件 | **已满足** | Grid 里 `net_value` 走金额；`units_held` 走普通数值 |
| ⑥ | 零 `el-input-number :formatter` | **已满足** | grep 确认 `wealthList/` 目录无 `el-input-number` |
| ⑦ | 审计说明/结论两区 + AI/复核 | **需补** | 有 `WealthListConclusion`（说明+结论），但无 🤖AI 按钮 / 💬 `GtReviewTrigger` |
| ⑧ | 导入导出 `el-dropdown` | **有意差异** | 不是标准 dropdown（Grid toolbar 里三个独立按钮），但功能等价（导出模板/导出数据/导入）→ 可接受 |

**三分类总结**：
- **已满足**：①②③④⑤⑥⑧
- **需补**：⑦（AI + 复核触发 —— 属 Wave 4 Task 10 统一补 8 条 prompt，E0-6 随其一起落地，本任务不单独改）
- **有意差异**：field 命名 / dropdown 形态

**结论：E0-6 已落地组件符合本 spec 核心要求（列/空表/动态行/控件语义/导入导出），不换 componentType。AI 辅助在 Task 10 统一补齐。**
