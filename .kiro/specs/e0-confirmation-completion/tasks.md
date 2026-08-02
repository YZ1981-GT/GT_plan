# Implementation Plan: E0 货币资金函证精细打磨

## Overview

按「先核实、再动共享件、最后 E0 专属」排序。共享件（列集/可靠性/备忘录/CrossRef）
先做且每步都带 golden 零回归凭据，因为它们被七个函证循环共用；
E0 专属件（13 要项表 / 品种矩阵 / 受限联动）后做，可单独交付。

**风险面**：`confirmationColumnSpec.resolveConfirmationColumns` 与
`memoTemplates.getTemplate` / `reliabilityTypes.ReliabilityRow` 是七枢纽共用真源，
改错会同时打断 D0/F0/G0/H0/K0/L0 → 每项都以「其余六个循环逐字节不变」为验收门。

### ✅ 裁决门 A 已关闭 = **A-否**（2026-08-02 用户：「三张隐藏底稿不需要再实现了，已隐藏」）

`银行函证其他信息核对表E0-5` / `邮件传真回函核对记录F1-12` / `回函情况汇编` 三张经
`sheet_state` 实证为 **hidden**，override 已置 `skip` 且生效；`底稿目录` D9:F11 只索引 9 张
（= 10 个 visible sheet 减目录本身），两证一致。

**落地**：原 Wave 6（Task 7/8/9，13 要项表 ~39 KB）**已删除**，新增 Task 19（守卫）
→ 任务数 20 → **18**（已完成 2：Task 11 口径纠偏 / Task 12.5 E0-6 专属组件）。
Task 1 / 2 / 13 中原标 `[Cond-A]` 的子项已按 A-否 收敛。
`e0-send-list-dedicated-components` 的「待裁决 4」同步关闭。

**A-否 之后仍必做的三条**（不要连带砍掉）：
1. `cycleConfirmationMeta.E0.reliabilityCode` 的**注释必改**（取值 `null` 对、注释错）→ Task 2
2. **可靠性按渠道补 12 列照做**（共享件增强，D0-7 受益）→ Task 6，实测改在 D0-7 上做
3. **Task 19 新增**：钉死「hidden ⇒ `skip`」不变式（Property 28），
   特别是 `银行函证其他信息核对表E0-5` 的**全名** `skip` 条目不得删
   —— componentType 解析（`wp_render_config.py` L749）是**尾码优先**，
   删了全名条目该表会被解析成 `confirmation-send-list-e05` 并渲染出多余页签

**顺带解掉一件事**：`E0-5` 一码两表**已随 A-否 自然消歧** ——
skip 判定（L709 全名精确）**先于** 尾码判定（L722），核对表被拦在 componentType 解析之前。
→ `e0-send-list-dedicated-components` 的 **Task 14 降级为「只加守卫、不改查表顺序」**，
其「待裁决 2」（消歧走 A 还是 B）随之关闭。

### 状态更正（本轮实测，非计划变更）

| 项 | 原标记 | 实测 | 处置 |
|---|---|---|---|
| Task 11 `importE0ListsToSummary` 口径纠偏 | `[ ]` | 并发会话已把该文件由 124 行改到 357 行（`E0_LIST_SPEC` / `hasConfirmFlag` / `account_no` / per-list `amountKeys` / 三元去重 / E0-4 `所属科目` 优先）| **拆分**：口径部分标 `[x]`，硬前置与统计回报新开 **Task 11b** |
| E0-6 componentType | Task 13 计划「→ `d-form-table`」 | 并发会话已交付 **`confirmation-wealth-list`** 全链（Task 12.5 已 `[x]`），契约硬断言两个 override 键 | Task 13 **删除 E0-6 相关子项**；send-list spec 原计划的 `confirmation-send-list-e06` 已撤回 |
| E0-1 下区 | 只有 Task 10（品种矩阵） | 下区实为**四块**（`C27 一、函证情况` / `O27 二、样本选择` / `V27 三、审计说明` / `V34 四、审计结论` + `A37/A38` 提示）—— 第二版漏了 O/V 列 | 新增 **Task 18** |
| Task 4 / Task 10 | `[ ]` | 确认**未做**（`buildCrossRefRules` 0 命中、`D0-5`/`D0-7` 字面仍在、`其他货币资金`/`应付票据`/`占账面` 全 0 命中）| 保持 `[ ]` |
| Wave 6（13 要项表） | 原 Wave 3 → 复盘时移到 Wave 6 | 用户裁决 A-否 | **整节删除**，口径存档在 requirements R1 / design §1 |

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "源模板事实固化 + 核实类结论",
      "tasks": ["1", "2"],
      "parallel": false,
      "rationale": "13 要项列名/列号、E0-1 列集、品种矩阵指标、五段话术、真实 tab 名必须先以 openpyxl 守卫钉死，后续所有实现都以它为裁决；functional_type 与「回函情况汇编」形态是先做核实再决定动不动的两项"
    },
    {
      "wave": 2,
      "name": "共享件改造（七枢纽零回归）",
      "tasks": ["3", "4", "5", "6"],
      "parallel": false,
      "rationale": "列集剔除机制 / CrossRef 按循环 / 备忘录按循环 / 可靠性补列都改同一批共享文件，串行做以便每步单独验证 golden"
    },
    {
      "wave": 3,
      "name": "E0-1 下区四块 + 品种矩阵 + 带入链路 + 受限联动",
      "tasks": ["18", "10", "11b", "12"],
      "parallel": false,
      "rationale": "Task 18（下区四块骨架）先做，Task 10 的品种矩阵是它的「一、函证情况」块内容故必须在其后；11b 与 12 独立但同属取数/联动收口。原 wave 3（13 要项表）已因裁决门 A 移到 wave 6"
    },
    {
      "wave": 4,
      "name": "映射与预设纠偏 + B50",
      "tasks": ["13", "14", "15"],
      "parallel": false,
      "rationale": "override 只剩 E0-7 一条（E0-6 已由 12.5 落地、核对表属 Cond-A）→ 不再依赖 13 要项的新 componentType，故可前移到 Task 7~9 之前；预设纠偏与 B50 跳转独立但都属收口"
    },
    {
      "wave": 5,
      "name": "实测与收口",
      "tasks": ["19", "16", "17"],
      "parallel": false,
      "rationale": "Task 19（hidden⇒skip 不变式守卫）是裁决门 A = A-否 的执行性保障，与实测一起收口；实测覆盖 9 张 visible 底稿 + 在 D0-7 上验可靠性补列；CI 最后登记。原 wave 6（13 要项表）已随 A-否 裁决删除"
    }
  ]
}
```

## Wave 1 — 源模板事实固化 + 核实类结论

- [ ] 1. `test_e0_source_template_facts.py`（openpyxl 直读源 xlsx）
  - **🔴 先加一条无条件断言：`sheet_state` 与 `底稿目录` 索引清单的双向锁死**
    —— 10 个 visible sheet ≡ `底稿目录` D9:F11 索引的 9 张 + 目录本身；
    三张 hidden（`银行函证其他信息核对表E0-5` / `邮件传真回函核对记录F1-12` / `回函情况汇编`）
    SHALL 在 `wp_code_overrides` 里为 `skip`。这是整个 spec 的裁剪依据，必须可执行
    （并发会话已有 `test_e0_hidden_sheets_skipped.py`，本条 SHALL 复用而非重写）
  - ~~钉死 13 要项 `OTHER_ITEM_DEFS` ↔ 源模板 `F6:R6`~~ **已删除（A-否）** ——
    要项清单存档在 requirements R1；本文件 SHALL NOT 为不实现的表写守卫
  - 钉死 E0-1 的 **30 列**（A..AD，A5:AD7 两级表头）与四组分段名 + 组边界：
    `发函询证纪要 C5:I5`(7 列) / `1、发函信息 J5:N5`(5) / `2、收到回函 O5:U5`(7) /
    `3、回函金额确认 V5:Y5`(4)，另 A/B 与尾部 Z/AA/AB/AC/AD 五列不属任何组
  - 钉死品种矩阵 6 品种（E28:J28）× 6 指标（C29:C34）
  - **钉死 E0-1 下区四块锚点与固定文字**（本轮补：`C27` / `O27` / `V27` / `V34` +
    `A37`/`A38`）：`E0_LOWER_ZONE_TEXTS` 每条 `text` ↔ `anchor` 单元格逐字，
    跨格（`O30+O31` / `V32+V33`）按顺序拼接后比对；
    `V32` 的源模板笔误 `本函证证` SHALL 原样断言（防被"顺手修正"）；
    **反向自检**：把 `O30+O31` 拆回两条独立文本必红
  - 钉死 E0-7 五段话术关键词（对公柜台 / XX部门 / 寄回致同会计师事务所 /
    公示内容一致 / 补记）+ 三个「是否」项 + 签名栏
  - 钉死**真实 tab 名**：`跟函函证过程控制E0-7`（两个「函」）；
    另两个易错名 `银行函证其他信息核对表E0-5`（无「询证」）与 `邮件传真回函核对记录F1-12`
    **仍要断言** —— 它们是 Task 19 的 `skip` 清单成员，名字写错会让 `skip` 条目失效
  - **反向自检**：把 `跟函函证过程控制E0-7` 少写一个「函」必红；
    把 `银行函证其他信息核对表E0-5` 写成带「询证」的必红（那样 `skip` 就匹配不上了）
  - _Requirements: 12.1, 12.2, 12.4_

- [ ] 2. 核实类结论（先查后决定，不先动）
  - **`functional_type`（无条件）**：核实 `ACTION_REGISTRY['confirmation']` 的动作对四张发函记录表
    是否适用 → 适用则写幂等迁移；不适用则保持 `NULL` 并在 Notes 写明理由
  - **🔴 `cycleConfirmationMeta.E0.reliabilityCode` 的注释必改（A-否 下取值不动、只改注释）**：
    取值保持 `null`（恰好正确），注释由「E0 无回函可靠性验证 sheet」（**错的** ——
    源模板有 `邮件传真回函核对记录F1-12`）改为
    「源模板有 `邮件传真回函核对记录F1-12`，但为 hidden sheet 且 override 置 skip，故不启用」。
    **结论错、取值对** 是最危险的形态：守卫全绿、下个会话照注释再判一次
  - **两条源模板事实写进 Notes（无条件，A-否 下更要写）** —— 载体表不实现，但事实必须留存：
    - 「回函情况汇编 = E0-1 的品种横向视图 + 替代程序区 + 11 条编制说明 + 参考结论 A/B/C，
      33 列里 90% 来自 `VLOOKUP/SUMIFS 函证结果汇总表E0-1`」→ 将来重新裁决不必再精读
    - `回函情况汇编!V9` 表头逐字「长期借款（含一年内到期的长期借款）函证情况」
      → 它是 `e0-send-list-dedicated-components` 的 E0-4 `所属科目` 枚举只取两项的**唯一依据**，
      **这条丢了那边的枚举就失去依据**
  - ~~「回函情况汇编」形态二选一~~ / ~~`F1-12` 的 wp_code 归属~~ **已作废（A-否）**：
    既不新建组件、也不在 E0-1 内做「按品种横向」视图切换
    （把用户看不到的表的形态引进可见底稿 = 凭空造需求）
  - _Requirements: 7.6, 8.7b, 11.5, 11.6_

## Wave 2 — 共享件改造（七枢纽零回归）

- [ ] 3. 列集剔除机制 + E0 四个新增列
  - `confirmationColumnSpec.ts` 加 `CYCLE_EXCLUDED_COLUMNS`（除 E0 外全空数组）
    与 `variantOverrides`（让 `row_conclusion` 在 E0 归到新 group `row_summary`）
  - 新增四个 E0 variant 列（`pledge_note` / `other_items_match` / `mismatch_note` /
    `row_conclusion`），`source` 逐字写源模板列名与列号
  - `resolveConfirmationColumns` 改为 `BASE − EXCLUDED ∪ VARIANT`
  - `ConfirmationFullGrid` 已按 `resolveConfirmationColumns` 渲染 → 无需改；
    **`ConfirmationMaster.vue` 仍硬编码列**（实测 `resolveConfirmationColumns` 0 命中）
    → 核实它是否是 E0 的实际渲染路径，是则一并改为配置驱动
  - **golden 零回归**：六个非 E0 循环的列集与改造前逐字节比对
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 4. CrossRef 规则改按循环解析
  - `GtConfirmationSummary.vue` 删 `CROSS_REF_RULES` 常量，改
    `computed(() => buildCrossRefRules(props.wpCode))`
  - 平台守卫 `confirmationSharedNoHardcodedD0.spec.ts`：扫 `confirmation/**` 共享组件，
    `stripComments()` 后不得含写死 `D0-` sheet 编码；豁免逐条登记写明理由
  - 反向自检：把常量加回去必红
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 5. 备忘录话术按循环
  - `memoTemplates.ts` 改 `getTemplate(scenario, { cycle })` + `scenariosFor(cycle)`
  - 新增 E0 五段银行话术（逐字取源模板 A8/A10/A12/A14/A15），
    占位补 `bank_staff_name/no`、`bank_reviewer_name/no`、`bank_department`、`gt_office`
  - `FollowupDetail` / `FollowupMemoPreview` 按 `scenariosFor(cycle)` 出场景选项
  - **零回归**：`getTemplate('immediate')` 不传 cycle 时逐字不变
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 6. 回函可靠性按渠道补 12 列
  - `reliabilityTypes.ts` additive 加 12 个 optional 字段（字段 ↔ 源模板列名对照写注释）
  - `ReliabilityGrid` 按 `reply_method` 只展开对应渠道列组，其余折叠
  - `cycleConfirmationMeta.E0.reliabilityCode` 按 Task 2 结论声明，
    注释写明「源模板索引号沿用 F1-12，非 E0-x」；不可解析则保持 null 并写明
  - **零回归**：旧 `reliability-v1` 载荷读写一次逐字节不变（不写 `undefined` 键）；
    六个非 E0 循环表现不变
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

## Wave 3 — E0-1 下区四块 + 品种矩阵 + 带入链路 + 受限联动

- [ ] 18. E0-1 下区四块（`e0SummaryLowerZone.ts` + `E0SummaryLowerZone.vue`）
  - **逐格实证**：下区共四块，第二版只写了矩阵一块（首轮 dump 只取 A..L 列漏掉 O/V）——
    `C27 一、函证情况`（矩阵，内容归 Task 10）/ `O27 二、样本选择` / `V27 三、审计说明` /
    `V34 四、审计结论`，另 `A37 提示：对收到的回函重点检查：` + `A38`（合并 `A38:N38`）4 条
  - `E0_LOWER_ZONE_TEXTS` 单一真源：每条带 `text`（逐字）+ `anchor`（源模板格，跨格用 `+`）
    + `readonly`
  - **两处「一句话被源模板拆成两格」必须合并渲染**（否则界面出现半句话）：
    `O30`+`O31`（准则例外条件）/ `V32`+`V33`（未函证其他信息的处理）
  - `V32` 的源模板笔误 `本函证证` **原样保留**（守卫按原文断言，防被"顺手修正"后三向比对打红）
  - 「二、样本选择」：3 段固定说明就地展示（琥珀色左边线方法论块）+
    **「未函证账户的理由」录入位置**（`O29` 明确要求记录）
  - 「三、审计说明」：3 条小标题各自独立 textarea + AI 辅助 + `GtReviewTrigger`
    （多 section 底稿每个文本区都要 AI 的铁律）
  - 「四、审计结论」：结论录入 + AI；「提示」4 条只读
  - **分工守卫**：本任务新增文件 SHALL NOT 实现零余额/注销账户的**判定逻辑**
    （那归 `e0-send-list-dedicated-components` 的 R16 / `sendListScopeChecks.ts`）；
    `零余额`/`注销` 作为源模板固定文字常量允许出现，作为 `if`/`filter`/`some` 条件则打红
  - 守卫：`e0SummaryLowerZone.spec.ts`（Property 26/27，含两条反向自检）
    + 后端 openpyxl 三向比对（并入 Task 1）
  - _Requirements: 3.7, 3.8, 3.9, 3.10, 3.11_

- [ ] 10. 品种矩阵 `e0SummaryMatrix.ts` + 渲染（= Task 18 的「一、函证情况」块内容）
  - 纯函数 `buildE0SummaryMatrix`（6×6；求和对齐 `SUMIF`；分母 0 → 0；
    `bookAmounts` 缺 → `null` 渲染「—」；绝不产 `NaN`/`Infinity`）
  - 账面金额由 render 侧四表预填注入（`1002`/`1012`/`2001`/`2501`/`2201`；
    理财产品**无固定科目故不预填**），带取数口径 tooltip
  - 除账面金额行外全部只读
  - 单测含 **PBT**（Property 6）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 11. `importE0ListsToSummary` 口径纠偏（**6 个缺陷，非原记的 3 个**）—— 并发会话已落地
  - **状态更正（2026-08-02 实测，原 `[ ]` 是假红）**：该文件已由 124 行改写到 357 行，
    含 `E0_LIST_SPEC` 声明式 per-list 规格 / `hasConfirmFlag`（E0-5·E0-6 不过滤）/
    `account_no` 必填 / per-list `amountKeys`（含 `票面金额`·`产品净值`）/
    三元去重键 / E0-4 优先读 `所属科目`
  - **本任务只覆盖「口径」**，取数链路能否拿到数据 + 统计回报 → 见 **Task 11b**
  - _Requirements: 5.1, 5.2, 5.4, 5.7, 5.8, 5.9, 5.10_

- [ ] 11b. 取数链路硬前置 + 统计回报（**Task 11 的口径改对了也可能一行数据都拿不到**）
  - **🔴 硬前置（2026-08-02 实测）：`fetchWorkpaperHtmlRows` 有两处断点，不解则 Task 11 全部改动仍是 dead code**
    —— 口径改对了也拿不到一行数据：
    1. **`wp-id-by-code` 解析 wp_code**：多 sheet 工作簿的 sheet **不是独立 wp_code**。
       实测 `wp_index` 里 5 个项目只有 2 个有 `E0-4`（`E0-6` 一个都没有），其余 3 个（含
       `重药控股安徽_2025` / `首汽租车_2025` / `和平药房_2025`）只有 `E0` → 直接返 `null` 后 `continue`。
       → 改为**先解析 `E0` 的 wp_id、再按 sheet_name 定位 sheet**（或按 `E0-x` 失败后回退到
       `E0` + `SEND_LIST_SHEET_NAME[code]`），两条路径都要有守卫。
    2. **`hd._format === format` 匹配**：`d-form-table` 的 grid 载荷**根本没有 `_format` 键**
       （实测 keys 只有 `cells`/`col_widths`/`column_meta`/`header_rows`/`max_col`/`max_row`/
       `merged_cells`/`project_context`）→ 循环永不命中，`rows` 恒 `[]`。
       → 由 `e0-send-list-dedicated-components` Wave 2 的 `confirmation-send-list-e0X`
       专属载荷（带 `_format` + 业务键 `rows`）解掉；**本任务的 `spec.formats` 不要再声明
       `'d-form-table'` 作兜底**（那个兜底永远不会命中，属自欺）。
    - 验收：一条真实项目的端到端断言（拿到 ≥1 行、`account_no` 非空），不接受纯 fixture 单测通过
  - **依赖**：断点 2 由 `e0-send-list-dedicated-components` Wave 2 的
    `confirmation-send-list-e03/e04/e05` 专属载荷（带 `_format` + 业务键 `rows`）解掉；
    E0-6 由已落地的 `confirmation-wealth-list`（`_format = 'wealth-list-v1'`）解掉
    → **`spec.formats` SHALL NOT 再声明 `'d-form-table'` 作兜底**（那个兜底永远不会命中，属自欺）
  - **剩余口径缺口两条**（Task 11 已做的部分不重复）：
    - `E0-4` 品种两列皆缺时回退 `短期借款` SHALL 标 `fallback` 并在 UI 提示
      —— 静默归类会让长期借款品种恒空且无人察觉（R5.3）
    - 返回值 SHALL 报告每张清单的命中/跳过统计与原因（`noConfirmFlagColumn` /
      `missingAccountNo` / `emptyReason`），UI 就地展示；SHALL NOT 静默返回空（R5.6）
  - **`E0-5` 一码两表的 `emptyReason`**：A-否裁决下天然成立（核对表已 `skip`、
    `fetchWorkpaperHtmlRows` 拿不到它），但守卫 SHALL 保留按列指纹判别的反向断言
    防将来 override 变动（R5.5）
  - 守卫 `importE0Lists.spec.ts`：**用例行由 openpyxl 抽出的源 xlsx 真实表头构造**
    （禁手搓 fixture —— 手搓行会带上源表没有的「是否函证」键从而掩盖已修的 P0#1）；
    含 Property 18/19/20 三条反向自检（给 E0-6 加 `confirmFlagKeys` 必红 /
    退回二元去重键必丢行 / 改成份额×净值必红）
    —— 三条针对 Task 11 已实现的行为，属**回归锁**，须核实是否已存在，缺则补
  - _Requirements: 5.3, 5.5, 5.6_

- [ ] 12. E0-3 / E0-6 受限标记 → E1 联动
  - `e0RestrictedToE1.ts`：`collectE0Restricted` 覆盖**两处**来源列
    （E0-3 O `是否存在冻结、担保或其他使用限制（如是，请注明）` +
    E0-6 K `是否被用于担保或存在其他使用限制`）+ `planE1RestrictedMerge`
    （复用 `composables/shared/adjudicationPrefillPlan.ts` 的 plan→resolve→describe）
  - E1 ②表加「从 E0 发函记录带入受限账户」按钮 + 确认预览（手工优先 / 冲突弹确认 /
    可选「仅补空值」）
  - E0-6 受限行的落点按核算科目二选一（其他货币资金 → E1 ②表 /
    交易性金融资产等 → 受限资产附注段），**由用户点选**，未指定不自动落任一处
  - **单向**：不产生任何对 E0-3 / E0-6 的写入（守卫断言）
  - Notes 记录源模板「回函情况汇编」O 列 `#REF!` 的事实与本实现按意图落地
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

## Wave 4 — 映射与预设纠偏 + B50

- [x] 12.5 E0-6 专属组件（`confirmation-wealth-list`）—— 用户裁决插入项
  - 新建 `confirmation/wealthList/` 七件套（宿主 / 看板 / 网格 / 结论 / types / enums / composable），
    分层对齐 `confirmation/reliability/`（D0-7 范式）
  - 11 列逐字对齐源 `A5:K5`；`产品类型`「封闭式/开放式」与`是否受限`「是/否」点选；
    `是否受限` 整数据区可选（不照抄源模板残缺的 `K6:K10`）
  - `产品净值` 用 `WpAmountInput`（千分符）；`持有份额` 保持 `el-input-number`（数量非金额）
  - 看板 7 卡 + 4 类告警；**汇总键缺失**（缺 索引号/产品名称）红色告警 —— 对应 Task 11 的 P0②
  - 合计行按 `column.property` 判别（自定义 `#header` 的列 `label` 为空）
  - 注册五处：前端 registry / `_CONFIRMATION_FORMAT_MAP` / `_CONFIRMATION_COMPONENTS` /
    `wp_classification_service` / `wp_code_overrides` **编码尾码 + sheet_name 两处**
  - 守卫：`wealthList.spec.ts` 27 例（含 2 条 PBT + 「Σ净值 ≠ Σ(份额×净值)」反向自检）
    + `test_e06_both_override_paths_point_to_dedicated`（sheet_name override 优先级陷阱）
  - _Requirements: 8.1, 8.8, 8.9, 8.10, 8.11, 8.12, 8.13, 8.14, 8.15, 8.16_

- [ ] 13. override 补条目 + meta 交叉守卫（**范围已收窄，见下**）
  - **只剩 `E0-7 → confirmation-followup` 一条**：
    - ~~`E0-6 → d-form-table`~~ **已由 Task 12.5 落地为 `confirmation-wealth-list`**
      （编码尾码 + sheet_name 两处 override + 契约硬断言），本条**删除**；
      与 `e0-send-list-dedicated-components` 的互斥裁决 = 那边撤回 `confirmation-send-list-e06`，
      E0-6 唯一形态是 wealth-list（理由见 design §`confirmation-wealth-list`）
    - ~~`银行函证其他信息核对表 → confirmation-other-items`~~ **已作废（A-否）**：
      保留 `skip` 不动；「不得删该全名 `skip` 条目」这条不变式由 **Task 19** 守卫
  - `test_confirmation_meta_override_alignment.py`：7 循环交叉比对 meta 非 null code
    ↔ override；meta 为 null 不要求映射；**反向自检**（删 E0-7 映射必红）
  - **新增无条件断言（Property 12 补充）**：override 里被置 `skip` 的 sheet
    SHALL NOT 出现在任何 meta 的非 null code —— 否则 meta 声称有那张表、渲染层却 skip 掉
    = 静默失效；这条让 A-否裁决在守卫层可执行（`reliabilityCode` 若被填成 F1-12 立刻打红）
  - ~~E0-6 渲染形态落地~~ **已在 Task 12.5 完成**（Property 21/23/24/25 已有守卫）
    → 本任务不重复；send-list spec 的 Task 17 做**符合度核查**（8 项），两侧不重叠
  - _Requirements: 6.6, 6.7, 8.2, 8.3, 8.4, 8.5, 12.3_

- [ ] 14. E0 公式预设纠偏（幂等脚本）
  - `backend/scripts/fix/fix_e0_prefill_presets.py`（`--dry-run` / `--check`）：
    `sheet='审定表E0-1'` → `函证结果汇总表E0-1`；`wp_name='银行询证函'` → 同上
  - 科目按 `BS-002 = TB('1001')+TB('1002')+TB('1012')` 解析结果校验；
    现有两条 `TB('1002',期初/期末)` 对货币资金函证合理 → 保留并补说明
  - round-trip 自检（`json.dumps` 不能逐字复现原文即 exit 2）
  - `test_e0_formula_presets.py` 守 sheet/wp_name 逐字命中源 xlsx tab 名
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 15. B50 跳转实装（七枢纽共享）
  - `GtConfirmationFraudRisk.handleJumpB50` 实装：按 `wp_code='B50'` 解析 workpaper id 并导航
  - 查不到 / 无权限 → `ElMessage.warning`；有「已识别未应对」迹象先 `ElMessageBox.confirm`
  - 守卫（Property 14）：函数体 `stripComments()` 后不得只含 `console.log`
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

## Wave 5 — 实测与收口

- [ ] 19. 「hidden ⇒ `skip`」不变式守卫（**裁决门 A = A-否 的执行性保障**，Property 28）
  - `test_e0_hidden_sheets_skipped.py` **扩展**（并发会话已建，复用而非重写）：
    - 判据以 **openpyxl 直读 `sheet_state`** 为准，**不写硬编码 sheet 清单**
      （否则源模板改动时守卫自己就过期）
    - 断言 `银行函证其他信息核对表E0-5` 的**完整 sheet_name** `skip` 条目存在
      —— **不能只依赖尾码 `E0-5`**：`wp_render_config.py` 两条判定顺序**相反**，
      skip 是 L709 全名精确优先、componentType 是 L749 尾码优先
      → 删了全名条目，该 hidden sheet 会被解析成
      `confirmation-send-list-e05`（send-list spec 落地后）并渲染出列集完全不符的多余页签
    - 断言 override 里 `skip` 的 sheet 集合 ∩ 任一 `cycleConfirmationMeta` 的非 null code = ∅
      —— 防「meta 声称有那张表、渲染层却 skip 掉」的静默失效
  - **两条反向自检**：把全名 `skip` 条目改成任意 componentType 必红；
    把 `E0.reliabilityCode` 填成 `邮件传真回函核对记录F1-12` 必红
  - **SHALL NOT** 为不实现的三张表写任何形态/列集守卫（那会变成"看着像实现了"的噪声）
  - _Requirements: 7.5, 7.6, 8.4, 8.5, 12.3_

- [ ] 16. 浏览器 + 真实 DB 实测 + 数据复原
  - 逐张打开 E0 的 **9 张 visible 底稿**（E0A / E0-1 / E0-2 / E0-3 / E0-4 / E0-5 /
    E0-6 / E0-7 / E0-8）：挂载、零 console error、派生列正确（品种矩阵比例 / 差异）
    —— **原写的「银行函证其他信息核对表 + 回函情况汇编」两张已剔除**（hidden + `skip`，
    render-config 不下发，打不开不是缺陷）；**逐 sheet 断言 render-config 的 `sheets` 恰好 10 项**
    （9 张 + `底稿目录`）与 Excel 可见 sheet 逐字一致
  - **E0-1 下区四块**：验四块齐备 + 两处跨格文字已合并成完整句子（无半句话）+
    「未函证账户的理由」可录入 + 三条审计说明各有 AI 按钮 + 提示区只读
  - 四张清单带入 E0-1：E0-3/E0-4 勾「是否函证=是」，**E0-5/E0-6 不勾**（源表无该列）
    → 验四品种金额、`account_no` 已填、长/短期借款分流、统计条显示命中/跳过原因
  - **E0-6 录同一家银行两只理财产品** → 验带入后是 2 行不是 1 行（三元去重键）
  - E0-3 / E0-6 勾受限 → 带入 E1 ②表，验手工优先与冲突确认；E0-6 验落点点选
  - E0-7 选五种场景验话术含工号与公示核对
  - **可靠性补列在 D0-7 上实测**（E0 的 F1-12 是 hidden 不可达，A-否 裁决下永久如此）：
    按渠道折叠 + 旧载荷读写往返逐字节不变 —— **不得因 E0 侧不可达而跳过实测**，
    这 12 列是七枢纽共享件增强，D0-7 才是它的实际受益方
  - **先快照后改、按 md5 逐字节复原**；不可复原字段如实记录
  - 清理本会话 `tmp_*`
  - _Requirements: 12.6, 12.7_

- [ ] 17. CI 登记 + 复盘
  - `e0-confirmation-source-facts`（后端：openpyxl 三向守卫 + 预设 `--check` +
    meta/override 交叉 + **Task 19 的 hidden⇒skip 不变式**）
  - `e0-confirmation-frontend`（前端：E0-1 下区四块 + 品种矩阵 + 带入统计 + 受限联动 +
    列集 golden + 无写死 D0 + 备忘录 + 可靠性兼容）
  - `yaml.safe_load` 校验 + 确认引用路径存在
  - 复盘写回 Notes：源模板自身缺陷清单、遗留项与归属、七枢纽零回归凭据、
    **裁决门 A = A-否 的结论与依据**（`sheet_state` + `底稿目录` 双证 + 用户裁决原话）、
    Task 2 留存的两条源模板事实
  - _Requirements: 12.5_

## ~~Wave 6 — 13 要项核对表~~ —— **已删除（裁决门 A = A-否，2026-08-02 用户裁决）**

原 Task 7/8/9（`confirmation/otherItems/` 类型与派生 → `GtConfirmationOtherItems.vue`
→ componentType 注册与 E0-1 取数，合计约 39 KB）**不实现**：
`银行函证其他信息核对表E0-5` 经 `sheet_state` 实证为 **hidden**、不在 `底稿目录` 索引的
9 张底稿内、override 已置 `skip` 且生效（用户答复原话「三张隐藏底稿不需要再实现了，已隐藏」）。

**口径不丢**：13 要项的 label/colRef（源 `F6:R6`）与 D7/E7 派生公式已逐格核实，
存档在 requirements 的 Requirement 1 与 design 的 §1 / `OtherItemsPayload`；
将来若平台侧解决「隐藏 sheet 可控纳入渲染」后另立 spec，可直接取用不必重新精读。

**替代守卫**：新增 **Task 19**（Property 28）钉死「hidden ⇒ `skip`」这一不变式 ——
否则某天有人删掉 `skip` 条目，这三张表会以错误的 componentType 悄悄出现在页签上。
**SHALL NOT** 用 `skip` 标记让原 Property 1/2/3 的守卫先绿（绿守卫会被当成"已实现"的证据）。

## Notes

### 源模板精读结论（2026-08-02，逐格读值 + 读公式 + 读合并区）

**20 个 tab 里 13 张是真实底稿**，7 张是 `原版本备份/（原）/(备份)/旧版/参考用/F1-10-原` 参考件。
真实 13 张：`底稿目录` / `函证程序表E0A` / `函证结果汇总表E0-1` / `核实被函证单位信息E0-2` /
`货币资金发函记录表E0-3` / `借款发函记录表E0-4` / `应付银行承兑汇票发函记录表E0-5` /
`理财产品发函记录表E0-6` / `跟函函证过程控制E0-7` / `函证程序舞弊风险评价表E0-8` /
`回函情况汇编` / `银行函证其他信息核对表E0-5` / `邮件传真回函核对记录F1-12`。

**E0-1 是取数中枢**：30 列里 11 列是公式 ——
`C/J/M/N/P/T/U` = `VLOOKUP(索引号, E0-2!A:AL, {2,3,4,10,16,19,22})`；
`F` = 嵌套 IF + SUMIF/SUMIFS 按品种汇总四张发函记录表；
`I = F*H`（本位币 = 原币 × 汇率）；`W = IF(O="是", V-F, "未回函")`；`Y = X*H`。
→ 底稿内这些列本就不该手输。

**E0-3 的三列引用外部工作簿** `'[43]银行存款及其他货币资金明细表(仅人民币)E1-3'!$A/$C/$K`
→ E0 与 E1 在源模板层就是打通的（开户银行 / 银行账号 / 账户余额），
平台侧对应「从 E1-3 带入发函清单」，本 spec 的 Task 12 是它的反向补齐（受限标记 E0-3 → E1）。

### 源模板自身的缺陷（按意图实现，不照抄）

1. **`回函情况汇编` O 列 `SUMIF('货币资金发函记录表E0-3'!$B:$B, 索引号, '...E0-3'!#REF!)`**
   —— 第三参已坏成 `#REF!`，全列 15 行都是。意图明确 = 按索引号汇总 E0-3 的受限金额。
2. **`核实被函证单位信息E0-2` AA 列标题写「跟函函证控制过程（E0-3）」** —— 索引号应为 `E0-7`。
3. **`邮件传真回函核对记录F1-12` 的索引号贴错** —— F1 是预付款项循环，这张是 E0 的回函可靠性表。
   **不改索引号**（改了会打断 `回函情况汇编` 与既有项目数据），只在 meta 注释写明。
4. **`银行函证其他信息核对表E0-5` 的 T3 索引号写 `E0-6`**（`=底稿目录!F9`）而标题是 E0-5
   —— 一码两表的根源之一。
5. **`回函情况汇编` r77 残留编辑痕迹**「这块内容删掉了」、r84/r85 残留
   「1.10-删除程序表13有资金池相关说明」「1.11-放到程序表10」—— 源模板未清理的编辑批注。
6. **`借款发函记录表E0-4` r16 有孤立的 `G:0 H:0`** —— 残留数据行。
7. **`理财产品发函记录表E0-6` K 列数据验证范围只到 `K6:K10`，而数据区是 `R6:R20`**
   —— 对比 E0-3 是 `L6:L26 O6:O26` 全覆盖。平台侧整列启用「是/否」，不照抄残缺范围。

### E0-6 逐格精读（2026-08-02，本轮新增）

`理财产品发函记录表E0-6`：`A1:K20`，合并区仅 `A1:K1`（所名）`A2:K2`（表名），
表头单行在 **R5**（填充 `FFE4DFEC` + 加粗），数据区 **R6:R20 全空骨架**，
**无合计行、无两级表头**。表头引用 `A3=底稿目录!A2`（被审计单位）/ `A4=!A3`（截止日）/
`E3=!A4`（编制人）/`E4=!A6`（复核人）/`G3=!A5`（编制日期）/`G4=!A7`（复核日期）/
`K3=底稿目录!F9`（索引号 → `E0-6`，**本表自己引对了**；引错的是「银行函证其他信息核对表E0-5」）。

11 列逐字：`索引号 | 报表截止日 | 开户行名称及收件人 | 产品名称 | 产品类型（封闭式/开放式） |
币种 | 持有份额 | 产品净值 | 购买日 | 到期日 | 是否被用于担保或存在其他使用限制`。

**编制思路**（与其余三张发函记录表对照后得出）：
四张表都是「按品种铺开发函对象 → 汇入 E0-1」，但**列集与汇总键三者各不相同**：

| | 被询证单位列 | 账号位（→E0-1 E） | 金额列（→E0-1 F） | 汇总匹配键 | 有「是否函证」 | 有「所属科目」 |
|---|---|---|---|---|---|---|
| E0-3 | 开户银行 | 银行账号 | 账户余额（原币） | 银行账号 | ✅ E5 | ✅ A5 |
| E0-4 | 借款人名称 | 借款账号 | 余额 | 所属科目 + 借款账号 | ✅ E5 | ✅ A5 |
| E0-5 | 开户银行 | 银行承兑汇票号码 | 票面金额 | 索引号 | ❌ | ❌ |
| E0-6 | 开户行名称及收件人 | **产品名称** | **产品净值** | 索引号 + 产品名称 | ❌ | ❌ |

三条由此得出的结论：

1. **E0-6 的「账号」位由 `产品名称` 承担** —— 理财产品没有账号，源模板用产品名称做键
   （E0-1 表头 `E6='账号/理财产品名称'` 正是这个多态设计）。故 `产品名称` 属 `account_no`
   **不属** `entity_name`；被询证单位是**银行**（`开户行名称及收件人`）。
2. **`产品净值` 是总额口径不是单位净值** —— E0-1 F 列 `SUMIFS(E0-6!$H:$H,…)` 直接求和 H，
   与 E0-3 的 `账户余额（原币）`、E0-4 的 `余额`、E0-5 的 `票面金额` 同构。
   `持有份额`(G) 是询证函正文的补充信息，**不参与金额计算** → 禁改成 `G×H`。
3. **E0-5/E0-6 没有「是否函证」列 = 入表即发函** —— 这两张表是"已决定要函证的对象清单"，
   筛选动作在 E0-3/E0-4 内（那两张从 E1-3 全量账户里挑）。故带入逻辑对这两张表**不得过滤**。

**E0-1 品种矩阵是 6 品种 × 6 指标**（R28 列头 E:J = 银行存款/其他货币资金/短期借款/长期借款/
应付票据/理财产品；R29 本期期末账面金额**无公式=手工** / R30 发函金额 `SUMIF(D:D,品种,F:F)` /
R31 占比 / R32 回函确认 `SUMIF(D:D,品种,X:X)` / R33 回函占发函 / R34 回函占账面）。
理财产品在四表里无独立科目 → R29 该列保持手工（宁缺勿造）。

### 第一版被推翻的两处（已在 requirements 记录，此处留证）

- `reliabilityCode: null` 的注释「E0 无回函可靠性验证 sheet」→ **有**（F1-12）
- 第一版把 sheet 名写成 `银行询证函其他信息核对表E0-5` → 真实无「询证」二字，
  DB `workpaper_sheet_classification` 记的才对。**教训**：sheet 名一律以
  openpyxl 直读 `wb.sheetnames` 为准，不能凭 GBK 控制台输出或记忆。

### 平台侧实证（改造前基线）

| 事实 | 证据 |
|---|---|
| 13 要项关键词在 `confirmation/**` 全 0 命中 | 逐词 grep（注销账户/委托贷款/对外担保/贴现商业汇票/托收商业汇票/外汇买卖合约/托管证券/资金归集/其他信息核对/回函不符） |
| 品种矩阵 5 个品种在 `GtConfirmationSummary.vue` 0 命中 | grep（其他货币资金/短期借款/长期借款/应付票据/理财产品 全 0；占账面 0；发函金额占 0） |
| `importE0ListsToSummary` 从不写 `account_no` | 源码 `out.push({entity_name, confirm_index, account_type, amount})` 四字段 —— 而 `confirmationTypes.account_no` 与 `confirmationColumnSpec.account_no`（label「账号或理财产品名称」）早已存在 = 字段闲置；E0-1 F 列源公式按该列匹配 → 发函金额第二条归零路径 |
| `是否函证` 门把 E0-5/E0-6 整表滤空 | `buildSummaryRowsFromListRows` 首行 `if (!isConfirmFlagYes(raw)) continue`；openpyxl 实证两表 R5 无该列 → 恒 0 候选 |
| `ENTITY_KEYS` 无 `开户行名称及收件人`，却含 `产品名称` | 源码候选表；E0-6 的 pick 会落到 `产品名称` → 被询证单位填成产品名 |
| `dedupeSummaryRows` 二元键丢行 | `keyOf = entity_name||account_type`；同一家行多只理财产品 account_type 同为「理财产品」→ 第 2..N 行被丢 |
| E0-4 品种真源被误判为 `借款类型` | E0-1 F 列 `SUMIFS(…,'借款发函记录表E0-4'!$A:$A,'函证结果汇总表E0-1'!$D…)` 匹配的是 **A 所属科目**；O 借款类型是另一列 |
| `GtConfirmationSummary.vue` L391~393 写死 `D0-5/D0-6/D0-7` | 源码直读，而 `buildCrossRefRules(wpCode)` 已在 meta 备好 |
| `handleJumpB50()` 只 `console.log` | `GtConfirmationFraudRisk.vue` L300~303 |
| `ConfirmationMaster.vue` 未用 `resolveConfirmationColumns` | grep 命中 0（`ConfirmationFullGrid.vue` 命中 2）→ Task 3 需核实实际渲染路径 |
| E0 override 只有 7 条，缺 `E0-6`/`E0-7` | `backend/app/data/wp_code_overrides.json` |
| 四张发函记录表 `functional_type` 为 NULL | `workpaper_sheet_classification` 查询 |
| `memoTemplates.ts` 只有 D0-3 口径三段 | 全文 38 行，无「工号」「公示」概念 |
| `ReliabilityRow` 无邮寄/跟函/电子平台渠道字段 | `reliabilityTypes.ts` 全文 |

### 关键踩坑预防（本 spec 直接适用）

- **sheet 名逐字**：`银行函证其他信息核对表E0-5`（**无**「询证」）、
  `跟函函证过程控制E0-7`（**两个**「函」）—— GBK 控制台会腌坏中文，一律 UTF-8 落盘再读
- **共享件改动必带 golden**：`resolveConfirmationColumns` / `getTemplate` /
  `ReliabilityRow` 是七枢纽真源，验收门 = 其余六个循环逐字节不变
- **派生列必须只读**（异常项目 / 比例 / 差异 / 本位币），可编辑就会出现双真源
- **比例分母 0 → 0，缺账面金额 → `null` 渲染「—」**，绝不填 0 冒充（覆盖率显示 0% 会误导）
- **守卫读源码先 `stripComments()` + 反向自检**（本 spec 的踩坑说明里会写反例）
- **PowerShell `>` 重定向会腌坏 UTF-8 中文** → 诊断脚本用 Python 自己写盘
- **`read_file` 对本会话改过的文件返回陈旧版本** → 判落盘真相用 Python 直读
- **一码两表消歧不能"随便挑一张"**，不能改源模板 sheet 名；做不到就如实记遗留

### E0-4 借款发函记录表逐格精读（2026-08-02，本轮新增）

**结构**：`dims=A1:P20`，16 列 A:P，表头 R5，**数据区 R6:R20 共 15 行空白带边框**
（`print_area=$A$1:$P$21` 旁证那是打印骨架非数据），**零数据有效性**，无冻结窗格，
`merged` 仅 `A1:P1`/`A2:P2`，**E 列 `hidden=True`**。列逐字：`所属科目 | 索引号 |
报表截止日 | 开户银行 | 是否函证(隐藏) | 借款人名称 | 借款账号 | 币种 | 余额 |
借款日期 | 到期日期 | 利率(%) | 抵(质)押品/担保人 | 备注 | 借款类型 | 期末应付利息`。
R16 残留孤立 `G16=0 / H16=0`（借款账号/币种两列的 0，源模板残留数据行 → 渲染时以
「0 0」出现在表尾；迁移必须按空行处理，不得产出一条借款记录）。

**~~⚠️ 与用户手上副本不一致~~ → 已证伪，两份是同一模板（2026-08-02 复核，留证防再犯）**：
首轮据用户第一张截图判「用户那份是 15 列、无『是否函证』列」，**是误判**。根因：
**E 列（是否函证）在源模板是隐藏列**（`column_dimensions['E'].hidden is True`，E0-3 亦同）
→ Excel/WPS 里列字母从 **D 直接跳到 F**，肉眼数只有 15 列。第二张截图放大后可见列字母
`A B C D F G H I J K L M N O P` 与 I 列表头逐字「余额」，与权威模板完全一致。

**铁律**：判「某列在不在」只能看 `column_dimensions[x].hidden`，**禁按截图数列**；
「列被隐藏」与「列不存在」是两件事 —— E0-3/E0-4 是隐藏，E0-5/E0-6 才是真的没有该列
（`hidden cols == {}` 且表头 10/11 列里无「是否函证」）。两者混淆会直接导致
`hasConfirmFlag` 判错（E0-3/E0-4 丢门控，或 E0-5/E0-6 恒 0 候选）。

**编制思路（链条位置）**：`底稿目录!F7='E0-4'` → E0-4 → `E0-1!F`（发函金额（原币））。
`E0-1!F8` 逐字：
```
=IF(OR(D8="银行存款",D8="其他货币资金"), SUMIF(E0-3!$G:$G, E0-1!$E8, E0-3!$K:$K),
 IF(OR(D8="短期借款",D8="长期借款"),   SUMIFS(E0-4!$I:$I, E0-4!$A:$A, E0-1!$D8, E0-4!$G:$G, E0-1!$E8),
 IF(D8="应付票据",                     SUMIF(E0-5!$A:$A, E0-1!$B8, E0-5!$G:$G),
 IF(D8="理财产品",                     SUMIFS(E0-6!$H:$H, E0-6!$A:$A, E0-1!$B8, E0-6!$D:$D, E0-1!$E8), 0))))
```
→ **E0-4 的品种权威列是 A 列「所属科目」**（对齐 E0-1 D 列「账户/交易」），
账号键是 G 列「借款账号」（对齐 E0-1 E 列），金额是 I 列「余额」。
备份 sheet `函证结果汇总表E0-1（原）!S/V` 用的是 `$B:$B`(索引号)+`$A:$A`(所属科目)
—— 现行版把匹配键从索引号换成了借款账号，两版都以 A 列判品种。

**O 列「借款类型」在整册零消费方**：全工作簿无任何公式引用 `'借款发函记录表E0-4'!$O`，
且该 sheet 无 DV、O6:O16 全空 → 改造前 `manifest`/`E0.yaml` 给它写的枚举
`['短期借款','长期借款','一年内到期的长期借款','其他']` 是**把 A 列语义抄了一份的臆造**，
本轮已撤回为 `text`；A 列改 `enum ['短期借款','长期借款']`（依据 = 上述公式字面量；
「一年内到期的长期借款」并入长期借款，依据 `回函情况汇编!V9` 表头逐字
「长期借款（含一年内到期的长期借款）函证情况」）。守卫见
`test_e0_send_list_columns.py` 新增 3 例（源 xlsx 公式 ↔ manifest ↔ E0.yaml 三向 +
反向自检「全册不得引用 E0-4 的 O 列」）。

**P 列「期末应付利息」同样无下游消费方**（E0-1 只取 I 列）→ 属可增强点（可与 K3
应付利息底稿勾稽），源模板未连线故**宁缺勿造**，只保留录入位置并在 manifest 写明。

### 本轮已落地的平台级修复（2026-08-02，非本 spec 任务，但解掉 E0 的显示阻塞）

**`wp_grid_extract.strip_standard_header` 把列头行当编制信息行删掉** —— 旧判据按
「整行文本包含 致同/被审计单位/编制人/编制日/截止日/复核人」子串命中并取 rows1..7
最后一个命中行，而四张发函清单的列头行含**「报表截止日」（内含「截止日」）**
→ 列头行连同上方全部被裁。实测后果：E0-4 前端只剩一张无表头空网格（唯一可见内容
是源模板残留的两个 0，与用户截图一致）、E0-3 只剩 19 行 `XX银行` 示例值、
E0-5/E0-6 `cells=0` 完全空白。

已修：判据改「关键词锚定标签（格以关键词**开头**且后面还有分隔符/取值 →
`报表截止日` 不算、裸 `索引号` 不算）+ 短标签形态（无换行/≤30 字/冒号在第 1~12 字符）
**过半**」。关键词表**刻意不扩充**以保证新判据是旧判据真子集（结构性只少删不多删）。
凭据：全量 characterization 351 模板 × 2722 sheet，**503 张少删行 / 0 张多删 /
复活行中 0 张仍被判为编制信息行**；live render-config 实测 E0-4 现在下发 16 个列头
（此前 `nonempty=0`）。测试 `test_wp_grid_extract.py` 31→52 例（含反向自检、
子集不变式 `test_prep_keywords_are_identical_to_legacy_set`、变体标签守卫）。

→ 对本 spec 的影响：Task 16 实测时 E0-3/E0-4/E0-5 已可看到真实列头；
但 **E0-3 的 19 行 `XX银行` 示例值是另一类污染**（`extract_grid` 用 `data_only=True`
读到外部工作簿引用的缓存值），归 `e0-send-list-dedicated-components` Wave 2 的
专属 componentType 解决，不要与本条混为一谈。

### 与其它 spec 的衔接（2026-08-02 复盘重写）

#### `e0-send-list-dedicated-components`（0/18，**不并行推进**）

三处协调点 + 一个共同裁决项：

| 项 | 状态 |
|---|---|
| **E0-6 componentType 命名** | **硬冲突已解** —— 那边原计划 `confirmation-send-list-e06`，本 spec 的 Task 12.5 已交付 `confirmation-wealth-list` 全链且契约硬断言两个 override 键 → 那边**已撤回**，改为「符合度核查（其 Task 17，8 项）」。最终形态 = **三 + 一**（send-list 只做 E0-3/E0-4/E0-5）。**命名不一致是有意接受的**，两份 spec 的 Glossary 都要写明，否则下个会话会再提一次统一 |
| **取数链路（本 spec Task 11b 依赖那边 Wave 2）** | 断点 2（`hd._format` 匹配）要靠 `confirmation-send-list-e0X` 的专属载荷（带 `_format` + 业务键 `rows`）解掉；E0-6 已由 `wealth-list-v1` 解掉 → **Task 11b 排在那边 Wave 2 之后** |
| **E0-1「二、样本选择」↔ 那边 R16（完整性红线）** | 同一准则要求的两个落点：`O28` 逐字「所有银行账户全部函证（包括零余额账户和在本期内注销的账户）。」是红线的第二处源模板依据（第一处是 `E0A` 程序 1）。**本 spec 只做说明文字 + 未函证理由录入位置，逐账户校验归那边** → Property 27 用源码级反向断言防两侧各造一份 |
| **裁决门 A ≡ 那边「待裁决 4」** | **已裁决 A-否（2026-08-02 用户）** → 本 spec 的 R1/R7.1/R7.5/R8.6 与 Wave 6 **已删除**；那边 R17.2/R17.3（资金归集勾稽）**永久留遗留**，只做 E0-3 `L 资金归集` 的列标注 + Notes 登记 |
| **那边「待裁决 2」（`E0-5` override 消歧走 A 还是 B）** | **随 A-否 关闭** —— 实证 `wp_render_config.py` 的 skip 判定（L709 全名精确）**先于** 尾码判定（L722），核对表被拦在 componentType 解析之前，当前配置已正确。→ 那边 **Task 14 降级为「只加守卫、不改查表顺序」**；守卫内容与本 spec 的 Task 19 是**同一条不变式**（全名 `skip` 条目不得删），二者 SHALL 择一实现、另一侧引用，**不得各写一份** |

**另接受那边一处 manifest 变更**（不反驳）：E0-4 `A 所属科目` 由 `text` 改
`enum ['短期借款','长期借款']`、`O 借款类型` 由 4 项 `enum` 改 `text`。
依据是源模板公式（`E0-1!F8` 的 `SUMIFS(...,$A:$A,E0-1!$D)` + 全册零引用 O 列），属硬证据；
A 列枚举能把「选错值 → 发函金额恒 0 且无任何报错」挡在录入阶段，与本 spec 的 R5.3 同向。
**O 列的 4 项枚举不得恢复**（无源依据的臆造）。

#### `e1-orphan-components-wiring`（0/14，**不并行推进**）

- E1 侧孤儿组件接线与本 spec Task 12（E0-3/E0-6 → E1 受限）都会碰 E1 ②表
- E0-3 `I 利率(%)` → E1-20 应计利息测算 / E1-30 存款规模与利息收入匹配性，
  **归那边**（E1-30 是那边的孤儿组件之一）；本 spec 只保证 `interest_rate` 可读

#### `restricted-assets-note-row-scope-rollout`（已完成 16/16）

E1 的受限资产附注段（`BS-002` 货币资金段）已打通行级合并，
Task 12 补齐的是它的**上游数据来源**（E0-3/E0-6 发函清单里的受限标记）。

#### 平台级守卫的归属

- 「孤儿组件守卫」→ `e1-orphan-components-wiring`，本 spec 不重复造
- 「hidden sheet 全库扫描」→ **另立 spec**（`analyze_wp_templates.py` 无可见性过滤，
  全库 247 张隐藏 sheet / 353 行分类记录 / 228 个 wp_code 受影响）；
  本 spec 只消费 E0 侧已落地的 `skip` 结论
