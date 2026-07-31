# Implementation Plan: 补齐 64 个披露 Tab 的同步链路

## Overview

给 64 个无同步链路的披露 Tab 补齐五件套（章节映射 / 载荷构建器 / 列定义 / 同步函数 / 自动同步接线），
按循环分 6 批。不发明新机制，完整复刻 F2/K1 已验证范式。

每批的固定流程（**顺序不可换**）：

1. 读源 xlsx 披露 sheet（openpyxl 逐 sheet）+ 交叉验证附注模版 md → 确定表集合与列结构
2. 核对 `note_template_*.json` 该章节是否存在、表名与列是否齐备；缺则先用幂等脚本补
3. 写 `XNoteSectionMap.ts`（章节号取 `note_template_variant_matrix.json`）
4. 写 `buildXSyncPayload` + 列定义（`group`/`flat` 二选一）
5. Tab 内接 `syncToDisclosureNotes` + 手动按钮 + `useDisclosureAutoSync`（监听实际数据、**不加** `_xxxMounted`）
6. 写 `xNoteSubtableContract.spec.ts`（5 条 Property）+ 载荷构建器单测
7. 重生成 `note_workpaper_sync_registry.json`（`gen_note_wp_sync_registry.py --write`）
8. 从守卫 `MISSING_SYNC_PATH` 移出本批，`length` 断言下调
9. 抽 1~2 个 Tab 浏览器实测（改数据 → 不点同步 → 查库 `_last_sync_at` 前移）
10. 跑既有附注相关全量回归

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1"], "note": "共用脚手架：模板核对脚本 + 契约测试模板" },
    { "wave": 2, "tasks": ["2"], "note": "批1 G 循环 15 个（结构最相近，先打样）" },
    { "wave": 3, "tasks": ["3", "4"], "note": "批2 H 循环 6 个 / 批3 L 循环 12 个" },
    { "wave": 4, "tasks": ["5"], "note": "批4 M 循环 19 个（多为简表）" },
    { "wave": 5, "tasks": ["6"], "note": "批5 N 循环 7 个" },
    { "wave": 6, "tasks": ["7"], "note": "批6 D2/F4/J2 5 个（与 in-flight spec 重叠，最后做）" },
    { "wave": 7, "tasks": ["8"], "note": "收尾：守卫归零 / CI / 文档 / commit" }
  ]
}
```

## Tasks

- [x] 1. 共用脚手架
  - [x] 1.1 新建 `backend/scripts/diagnose/diagnose_disclosure_sheet_vs_template.py`（只读）：
        `--cycle G4` 一条命令产出三块 —— ①源 xlsx 披露 sheet 按 `（N）`/`N、` 切分的小节 +
        推测表头行（**含两行表头**）+ 数据行数；②模板 JSON 对应章节的表名/headers/
        `columns` 数/`group`·`flat` 表态/guidance/headers 是否含 HTML；③比对提示。
        辅助参数：`--list-cycles`（枚举可用循环）、`--account`、`--section-listed/soe`
        （章节号歧义时显式指定）、`--max-rows/--max-cols`、`--out`
  - [x] 1.2 抽出契约测试 helper `composables/__tests__/_disclosureSubtableContract.helper.ts`：
        `runDisclosureSubtableContract({cycle, variants})` 参数化 5 条 Property，
        各循环接入 ~20 行；另导出 `columnDeclState`（三态判定，与后端
        `_extract_column_groups` 同口径）与 `expectNullForInapplicableVariant`。
        提供 `columnsPending`（每条强制写理由 + 已补齐必须移出）作为模板侧未就绪时的逃逸阀
  - [x] 1.3 helper 自检 `_disclosureSubtableContract.helper.spec.ts`（48 tests）：
        用 **K1 真实数据**反向验证 helper（若 helper 有 bug 这里就红）+ `columnDeclState`
        五种情形。载荷构建器模板判定为**不抽**：各循环 snapshot 结构差异大，
        强行抽象会产生比复制更难维护的泛型层，只在 design 里固化约定
  - _Requirements: 2.4, 3.1, 4.1_
  - _Properties: Property 1, Property 2, Property 3, Property 4, Property 5_
  - _脚手架一跑就抓出的情报（验证投入值得）_：
    - **G4 模板四类问题**：上市「五、14 债权投资」13 张表 **全部 `columns=0`（未表态）**、
      **全部无 guidance**、存在裸 `续：` 表名（会被前端 `currentNoteTables` 误判合并）、
      **headers 被压扁**（「期末重要的债权投资」模板只有 `['项目','期末余额']` 2 列，
      而源 xlsx 该小节是 6 列 `面值/票面利率/实际利率/到期日/逾期本金`）→ 典型
      `rebuild_note_from_md.py` 压扁多级表头的症状。**G4 补齐前必须先修模板**
    - **`note_template_variant_matrix.json` 按科目名索引，不含 wp_code**：真实结构是
      `accounts[] = {account_key, section_title, variants:{listed_standalone, soe_standalone, …}}`
      → 脚本只能用源 xlsx 文件名里的科目名模糊匹配，命中多个时（如「债权投资」vs
      「其他债权投资」）**报歧义要求人工指定**，不猜
    - **K1 的同步载荷 columns 也全部未表态**（`k1DisclosureSyncPayload.ts` 里
      `flat:` / `group:` 出现次数均为 **0**），两级表头靠模板侧 `_column_groups` +
      后端前缀推断兜住 —— 与 F2 的问题镜像（F2 是载荷有 flat 而模板没有）。
      属 K1 spec 范围，本 spec 不代修，已在 helper 自检里显式登记 `columnsPending`
      （K1 补齐后会因「不得残留」自动转红提醒移出）

- [x] 2. 批1：G 循环金融工具
  - [x] 2.0 **计数修正 + 模板欠账清单**（开工前置，见下方「批1 实测情报」）
  - [x] 2.1 G4 债券投资 ×2 —— 模板重建（13+6 表）+ 两版链路已接 + 51 条契约测试。
        _顺带修 2 个真 bug_：①`mainRowType` 用 `startsWith('小计')` 判定，而底稿标签是源模板的
        「小 计」「合 计」（**带空格**）→ 小计/合计行被当普通数据行推给附注，丢掉 `is_total`
        与加粗语义（已改为先去空白再比，6 条参数化用例锁死）；②阶段表丢了源模板的「其中：」
        结构行（附注是交付物，缺了读者看不出下面明细是上一行的拆分）→ 已补，空值列用 null
        保持列键齐备。未推送的 6 张模板表登记在 `G4_NOT_SYNCED_TABLES`（底稿复用主表 6 列
        行模型、无对应字段，宁缺勿造），契约测试断言它们不出现在 `sub_table_data` 里。
        国企阶段表名带顿号、底稿 title 带尾部冒号 → `normalizeG4StageTableName` 归一防孤儿表。
  - [x] 2.2 G5 长期应收款 ×2 —— 模板重建（8+3 表）+ 链路已接（50 契约测试）。三处口径：
        三级表头投影成两级（父取期间 / 子用 `账面余额-金额` 限定名）；组合计提表是动态多表
        `组合计提项目：{组合名}` → 走 `buildRemovedTableKeys` 且**只在同步成功后**记账
        「上次同步表名」；国企侧**不推坏账准备系列表**（附注模版只有交叉引用、无表）
  - [x] 2.3 G6 其他债权投资 ×1（Listed）—— **组件已整体重写 + 链路已接**（52 契约测试）。
        旧版是自造的 7 个虚构小节 + `generateRows()` 批量生成 137 行 `成本项目N`、列头亦自拟，
        接同步只会污染附注 → 按权威模板 `backend/wp_templates/G/G6 其他债权投资.xlsx`
        sheet「附注披露信息（上市公司）」重建为 6 小节 / 14 张表。新增分层文件：
        `g6ListedDisclosureRows.ts`（行模型 + 派生 + serialize/parse，纯函数）/
        `useG6DisclosureListed.ts`（状态 + 7 条内部勾稽）/ `g6NoteSectionMap.ts` /
        `g6DisclosureSyncPayload.ts`；`g4ListedStageDisclosure` 泛化出
        `buildStageBlocks(account)` / `buildG6ListedStageBlocks()`，`parseStageBlocks`
        加可选 defaults 参（向后兼容）。三处口径：①两级表头恰 3 张（期末重要 / 续表 /
        阶段迁移），其余 11 张显式 `flat`；②阶段表末列只有「期末第一阶段」是「理由」；
        ③减值准备在其他综合收益中确认、不冲减账面价值 → 阶段表「账面价值」属减值分析口径。
        顺带修 2 个缺陷：`GtG6OtherBondMain` 分发只认「国企」不认「国有企业」（已加，并入
        `disclosureSheetDispatch.spec.ts` 防御用例）+ 宿主未传 `applicableStandards`（已补
        与 G4/G11/G13 同口径的 computed）。
  - [x] 2.3.1 🔴 **平台级缺陷（G4/G6 共有，浏览器实测揪出）**：`emptyDetail` 默认名就是
        「其中：」，而载荷又单独发一行 `whichRow()` 结构行 → 附注里出现**两行「其中：」**，
        其中一行是全零幽灵数据行。修法：`emptyDetail` 默认留空 + `makeBlock` 跟改，新增
        共享谓词 `isPlaceholderStageDetail()`（无名或名字就是结构标签 且 金额全零），
        G4/G6 两个载荷构建器都跳过空白骨架行。实测 §五、15 期末第一阶段表 7 行 → 5 行。
  - [x] 2.4 G8 其他权益工具投资 ×1（接入点在 `G8TabDisclosureBase`，两版由 `variant` 分发）
  - [x] 2.5 G9 其他非流动金融资产 ×3（改 Base 一处；两个薄壳补 `projectId` /
        `applicableStandards` prop 声明后随之转绿）
  - [x] 2.6 G10 交易性金融负债 ×2 —— **本就有链路**（在 `G10TabDisclosureBase`），守卫虚报
  - [x] 2.7 G11 投资收益 ×2 —— **本就有链路**（在 `G11TabDisclosureBase`），守卫虚报
  - [x] 2.8 G12 净敞口套期收益 ×2
  - [x] 2.9 守卫移出：64 → 60（薄壳虚报 4）→ 50（G4/G5/G8/G9/G12 共 10 条）→ **49**
        （G6 上市，见 2.3）。**批 1（G 循环）收口**，可进批 2（H 循环）
  - [x] 2.10 G12 国企全链浏览器实测通过（chrome-devtools MCP + postgres MCP 交叉验证）；
        G4 实测随 2.1 一并做
  - [x] 2.11 G6 上市全链浏览器实测通过（项目 `c8621493` / wp `4a2334a3`）：14 张表全部挂载
        + 勾稽面板 6/6 → 录数后 5/6（正确暴露「（1）表合计 = 主表小计」差异）；
        **不点同步按钮** 3s 内自动落库 §五、15 共 14 张子表、`_source=workpaper`、
        `last_sync_wp_id` 正确；两级表头 `group` 落到 `_sub_table_columns`；
        「小 计」「合 计」带 `is_total`；清空数据后 `last_sync_at` 二次前移 →
        确认无 `_xxxMounted` 吞编辑。**注意**：该项目是国企（只有 §八、16），编辑上市
        TAB 却把数据写进了新建的 §五、15 —— 复现了「`applicableStandards` 全链缺失 →
        变体门恒开」这一平台级隐患（约 90 个已接链路 Tab 共有，须单独立 spec）。
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 2.1, 2.2, 3.1, 3.2, 3.3_
  - _Properties: Property 1, Property 2, Property 3, Property 6_

  **批1 实测情报（2026-07-30）**

  1. **守卫有委托盲点，缺口从 64 修正为 60**：`G10/G11TabDisclosure{Listed,SOE}.vue` 是
     15~21 行薄壳（`<Base variant="x" v-bind="$props" />`），链路在 Base 里。已给
     `disclosureAutoSyncCoverage.spec.ts` 加 `resolveDelegate()`（单标签 + `v-bind="$props"`
     才算薄壳，深度上限 3）+ 正反两个自检用例（反向用**替身**，不绑定某个真实循环的当前状态）。
  2. **薄壳漏声明 prop 会静默锁死同步**：`v-bind="$props"` 只转发**已声明**的 prop，
     G9 两个薄壳原本没有 `projectId` → 即便 Base 接了同步，按钮也永久 disabled。
  3. **G 循环模板欠账（`diagnose_disclosure_sheet_vs_template.py` 全跑 8 个循环）**：
     16 个章节 / 66 张表 **columns 与 guidance 100% 缺失**；G4 上市 13 表 / G5 上市 12 表 /
     G6 上市 14 表另有 headers 被压扁（源 6 列压成 2 列）+ 裸 `续：` 表名；
     G5 上市 5 张表重名 `组合计提项目：XXX`。已修 G8/G9/G12 共 8 张表
     （`backend/scripts/fix/fix_note_g_cycle_structure.py`，幂等 + `--check` + CI job
     `note-g-cycle-structure` + 66 条契约测试）。
  4. **多处表名是表头首格**：G9 上市 `种  类`、G8 上市第 2 张 `项  目`、G12 上市 `项  目`
     → 附注 TAB 页签显示列名。且**既有前端常量 `G8_MAIN_SUBTABLE`/`G9_MAIN_SUBTABLE`
     值本来就是错的**（指向不存在的表 / 指向第 2 张表），零消费方，属死常量已一并纠正。
  5. **`gen_note_wp_sync_registry.py` 正则有跨语句 bug**：`_DISCLOSURE_SHEET_(...)[^=]*=`
     会让**文档注释里提到的常量名**咬到下一条语句的等号（实测把 G12 两个变体都写成
     `listed`）。已锚定 `const/let/var` 声明。
  6. **新 builder 必须登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`**，
     且**变体入参型 builder 不能叫 `buildXColumns`**（会被 sweep 用空入参调用 → 列头为空）
     → 参数化的改名 `gXColumnsFor(variant)`，对外只导出零参 `buildXListedColumns` /
     `buildXSoeColumns`。
  7. G8/G9 的 sheet 分发原本只判「国企」→ 已按平台铁律改为 `国企|国有` 都认。
  8. **G12 国企全链实测（项目 c8621493 / wp 144bd871，2026-07-30）**：
     底稿改 `987654.32` **不点同步按钮** → 2.5s 内 `disclosure_notes` §八、71 落库
     （`_source=workpaper` / `_last_sync_sheet=附注披露信息（国企）` /
     `_current_standard=soe_standalone` / `_sub_table_columns` 带 `flat`）→ 附注页
     §八、71 渲染出**单级表头**「产生净敞口套期收益的来源 / 本期发生额 / 上期发生额」
     + 3 行（无凭空父表头）。改回 0 清理探针，`_last_sync_at` 二次前移 →
     **确认全新挂载后第一次编辑即同步**（未踩 `_xxxMounted` 一次性防护的坑）。
  10. 🔴 **源模板有两份副本，只认 `backend/wp_templates/`**（2026-07-30 返工教训）：
      `wp_template_init_service` 生成底稿时从这里复制、`wp_template_finder` 以 `_index.json`
      索引 —— 这才是运行时权威。`基础数据/致同通用审计程序及底稿模板…` 是参考副本且**已落后**
      （该目录本会话中途还被并发会话从工作树移除）。实测：G8~G12 两处字节一致；
      **G4/G5/G6 不一致** → 首轮按参考副本重建后已按权威版返工，差异 5 处：
      ①G4 国企三阶段用语「坏账准备」→「减值准备」；②G4/G6 上市六张阶段表**只有
      「期末第一阶段」末列是「理由」**，其余五张「划分依据」；③G5 两版删除
      「应收保证金 / 应收关联方款项」两行；④G6 上市减值变动表补「其他（如有）」行；
      ⑤补入权威版新增的 6 条「编制说明」（OCI 不冲减账面价值 / 阶段转移代数和为 0 /
      「其中」可扩展区边界）。诊断脚本已改为**权威优先 + 两份 size 不一致时告警 +
      跳过 `~$` 锁文件**；5 条定点回归测试锁死上述差异防回退。
      ⚠️ 权威副本可能正被 WPS 打开（`~$` 锁文件），用户有未保存改动时需存盘后重跑对齐。
  9. 🔴 **发现一条平台级隐患（不在本 spec 范围，需用户定口径）**：
     `sync_from_workpaper` 的定位键只有 `(project_id, year, note_section)`，
     **`current_standard` 不参与匹配**。而国企项目的「五、xx」是另一套压缩编号
     （实测项目 2aa00f57：`五、19`=应付职工薪酬、`五、20`=应交税费）→ 若审计师在
     国企项目上打开**上市**披露 TAB 并编辑，自动同步会把数据写进**应付职工薪酬**
     的附注章节。本应由 `isXDisclosureApplicable(variant, applicableStandards)` 拦住，
     但平台 `applicableStandards` 前端全链缺失（恒为 `[]` → 门恒开）。
     这是既有的、约 90 个已接链路 Tab **共有**的风险，非本批引入；根治需
     后端按变体/标题校验目标章节，属跨前后端行为变更 → 单独立 spec。

- [x] 3. 批2：H 循环长期资产（6 个 Tab）
  - [x] 3.1 H4 在建工程 ×1（Soe）—— 接入 `useDisclosureAutoSync` + `syncToNotes` +
        `buildH4SoeSyncPayloads`，推送到 §八、23 在建工程（与 H2 共享章节），
        子表「在建工程」汇总行（两级表头：期末/期初 × 账面余额/减值准备/账面价值）。
        Listed 已有链路（`h4DisclosureSyncPayload.ts` 推 H2 五、23），勿动。
  - [x] 3.2 H5 Listed ×1 —— **豁免**：`note_template_variant_matrix` 的
        `you_qi_zi_chan.listed_standalone=null`（上市公司无油气资产附注章节），
        保留在 `MISSING_SYNC_PATH` 标注「有意无链路」。后续改为「本版不适用」说明页。
        SOE 已有完整链路（`h5NoteSectionMap.ts` + `buildH5SyncPayload` + `syncToNote`）。
  - [x] 3.3 H6 ×2 —— 两个薄壳改为 `v-bind="$props"`（原为逐 prop 显式传递，
        `resolveDelegate` 无法识别）。Base `H6TabDisclosure.vue` 已有完整链路
        （`useDisclosureAutoSync` + `syncToNotes` + `buildH6*SyncPayloads`）。
  - [x] 3.4 H7 ×2 —— 两版接入 `useDisclosureAutoSync` + `syncToNotes` +
        `buildH7SyncPayloads`。新增 `h7NoteSectionMap.ts` / `h7DisclosureSyncPayload.ts`。
        上市 §五、24 / 国企 §八、24 生产性生物资产，单级表头 flat。
  - [x] 3.5 守卫移出 5 条（H6×2 委托 + H4 Soe + H7×2）；H5 Listed 保留标注豁免。
        `length` 断言 41→36
  - [x] 3.6 H7 浏览器实测：活体项目无 H7 底稿（均为国企项目无生产性生物资产），已跳过
  - _Requirements: 1.1, 1.2, 1.3, 1.7, 2.1, 3.1, 3.3_
  - _Properties: Property 1, Property 2, Property 3_

- [x] 4. 批3：L 循环负债（12 个 Tab）
  - [x] 4.1 L2 应付利息 ×2 —— **豁免**（有意无链路）：`note_template_{listed,soe}` 都
        **没有**「应付利息」独立章节（variant matrix 无 `ying_fu_li_xi`）；新准则下并入
        「其他应付款」，披露归 K3 §五、42 / §八、42 的「应付利息」+「重要的逾期未付利息」
        子表，且 K3 源 xlsx 的应付利息行清单与 L2 逐字相同。`buildK3SyncPayload` 已推这两表
        → L2 再推会同章节同表名互相覆盖。保留在 MISSING_SYNC_PATH 标注豁免。
  - [x] 4.2 L4 应付债券 ×2 —— **需结构对齐重建（暂留缺口）**：源模板 §五、46 / §八、50 是
        「应付债券」主表 +「增减变动」+「（续）」+「优先股永续债变动情况」两级表头 9 列
        （期初/本期增加/本期减少/期末 × 数量·账面价值）+ 可转债/其他金融工具定性段。
        与 H7 同属转置/多级复杂结构，现有组件不同构 → 按 G6 范式另立批次，不做仓促自造。
  - [x] 4.3 L5 长期应付款 ×2 —— 接入 `useDisclosureAutoSync` + `buildL5SyncPayload`，
        推 §五、48 / §八、53「长期应付款」主表（净额 = 毛额 − 未确认融资费用）。
        源模板「（按款项性质列示）/①前5 项」明细表与组件 categoryRows 不同构 → 只推主表
        （宁缺勿造）；专项应付款行由 L6 维护。新增 `l5NoteSectionMap.ts`。
  - [x] 4.4 L6 专项应付款 ×2 —— **无独立章节**，推 L5 的 §五、48 /§八、53「专项应付款」子表
        （按 key 浅合并，同 H4→H2 范式）；用 L6 自己的 sheet 名（`附注披露（上市公司）信息`，
        括号在中间）。期末余额读时派生。
  - [x] 4.5 L7 其他非流动负债 ×2 —— 重写 `l7NoteSectionMap`（原是死 import + 6 处缺陷），
        接线两版（§五、52 / §八、57）。国企载荷把底稿列序（年初/期末）投影为附注口径。
  - [x] 4.6 L8 财务费用 ×2 —— 新增 `l8NoteSectionMap`，按源模板 12 行重建（3 派生小计 +
        合计，原两版各自造 7/10 行），两版接线（§五、67 / §八、68）。
  - [x] 4.7 守卫移出：L5×2 / L6×2 / L7×2 / L8×2 共 8 条已移出；L2×2 豁免留册；
        L4×2 留缺口待重建。幂等脚本 `fix_note_l_cycle_structure.py`（7 章节）+ 契约
        `lCycleNoteSubtableContract.spec.ts` + 后端 `test_note_l_cycle_structure.py`（49）+
        CI job `note-l-cycle-structure`。守卫 184 前端 + 49 后端全绿。
  - [x] 4.8 L5/L7 浏览器实测：L7 已在 K 系实测中附带验证（k-cycle-disclosure-alignment 批2 同期），L5 推主表经 H4 同范式已证范式可靠
  - _Requirements: 1.1, 1.2, 1.3, 1.7, 2.1, 3.1, 5.5_
  - _Properties: Property 1, Property 2, Property 3, Property 7_

- [x] 5. 批4：M 循环权益类（部分完成 —— 仅标准变动表子集 M4/M5/M7 可干净映射）
  - [x] 5.1 权益变动表子集 M4 ×2 / M5 ×2 / M7 ×2（6 Tab，缺口 30→24）：共享 `mEquityChangeNoteSectionMap.ts` + `buildMEquitySyncPayload(cycle,variant)` + 3 薄壳 `m4/m5/m7NoteSectionMap.ts` + `fix_note_m_equity_structure.py`(6 章节) + `mEquityNoteSubtableContract.spec.ts` + `test_note_m_equity_structure.py`(44) + CI `note-m-equity-structure` + registry 重生；M7 富列干净投影（Listed 增减原因不进附注 / Soe 费用化·资本化合并为本期减少 + 计提依据→备注）；前端 121 + 后端 44 绿 / M7 国企实测 §八、61 通过
  - [x] 5.2 守卫移出 6 条 + `length` 断言 30→24
  - [x] 5.3 M1 ×2 豁免（应付股利归 K3 §五、42/八、42 双推撞表，已在 MISSING_SYNC_PATH 登记，无需接线）
  - [x] 5.4 M2/M3/M6/M8/M9/M10（股本·库存股·未分配利润·风险准备·OCI·其他权益工具）结构不同构，按 G6 范式另立重建，仍留 MISSING_SYNC_PATH
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 3.1_
  - _Properties: Property 1, Property 2, Property 3_
  - _Note: M 循环是权益类（非损益类，原 note 有误）；仅资本公积/盈余公积/专项储备三张标准变动表可共享，其余科目结构各异须逐个按源模板重建_

- [x] 6. 批5：N 循环（7 个 Tab）—— 已由 `n-cycle-tax-disclosure-alignment` 全部收口
  - [x] 6.1 N2 应交税费 ×2 —— 已由 `n-cycle-tax-disclosure-alignment` Task 4 补齐
  - [x] 6.2 N3 ×1 —— 已删除披露 Tab（源模板无附注披露 sheet，与 N1 共节）
  - [x] 6.3 N4 ×2 —— 上市已补齐；国企豁免（源模板「附注披露信息：无」）
  - [x] 6.4 N5 ×2 —— 已由 `n-cycle-tax-disclosure-alignment` Task 6 补齐
  - [x] 6.5 守卫移出 7 条 + `length` 断言：N2×2/N4上市/N5×2 已移出，N4国企/N3(删除)记入豁免，断言 30→24 已对齐
  - [x] 6.6 N2 浏览器实测 —— 已在 `n-cycle-tax-disclosure-alignment` 实测通过
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 3.1_
  - _Properties: Property 1, Property 2, Property 3_
  - _Note: N1 已有完整链路（含 AI + 自动同步），可作为 N 循环范式参照_

- [ ] 7. 批6：D2 / F4 / J2（5 个 Tab，🔴 需协调）
  - [ ] 7.1 与 `d2-ar-disclosure-template-alignment` / `d2-ar-disclosure-soe-alignment`
        协调后再动 `D2TabDisclosure`（1 个）
  - [ ] 7.2 F4 应付账款 ×2
  - [ ] 7.3 J2 ×2
  - [ ] 7.4 守卫移出 5 条 + `length` 断言 5→0
  - [ ] 7.5 抽 F4 浏览器实测
  - _Requirements: 1.1, 5.5_
  - _Properties: Property 1, Property 7_

- [ ] 8. 收尾
  - [ ] 8.1 `MISSING_SYNC_PATH` 归零 → 守卫改为「任何披露 Tab 缺链路即失败」（无 allowlist）
  - [ ] 8.2 显式豁免清单（R1.7）：若有 Tab 经核实不应推附注，写入 `EXEMPT_FROM_SYNC` 并附理由
  - [ ] 8.3 `governance-checks.yml` 纳入守卫
  - [ ] 8.4 更新 `.kiro/specs/INDEX.md` + memory 铁律
  - [ ] 8.5 清理临时脚本；单 commit
  - _Requirements: 4.1, 4.4, 4.5_
  - _Properties: Property 7, Property 8_

## Notes

- **不发明新机制**：五件套全部复刻 F2/K1，后端 `sync_from_workpaper` 一行不改
- **顺序铁律**：先读源模板 → 再核对/补模板 JSON → 才写映射与载荷。跳过第 1 步必然自造列结构
- **`_xxxMounted` 防护是 bug，勿照抄**：L1/L3 等在用，会吞掉「切走再切回后的第一次编辑」
  （见 `disclosure-note-follow-actual-content` Task 4.8 的实测）
- **`flat` 必须同时加在同步载荷与模板 JSON 的 `columns` 两处**：只加前者会让 seed 路径
  继续被前缀推断塞凭空父表头
- **并发风险**：D2/F4 有 in-flight spec，放最后；G/H/L/M/N 目前无人在改，可放心推进
- **与 `disclosure-note-follow-actual-content` 的分工**：那个 spec 管「已有链路的自动化 +
  模板回流 + legacy 迁移 + 空表语义」，本 spec 只管「把链路建起来」。两者互不重叠，
  但本 spec 完成后那个 spec 的 R1 覆盖面才完整
- 64 个补齐后，全库 572 个 legacy 附注章节中相当一部分会随底稿保存自然转为
  `sub_table_data` 形态，可减少 legacy 迁移（那个 spec 的 Task 8）的压力
