# Implementation Plan: 受限资产附注表行级合并接入

## Overview

一张共享表、八个 owner。先修模板与平台缺口（所有 owner 的共同前提），
再逐 owner 接入。**每个 owner 一个独立任务**，可单独交付、单独回滚。

**风险面**：改的是 `note_template_{listed,soe}.json` 的 `report_row_code`（段归属真源）
→ 改错会让 owner 段定位到别人的行。故 Wave 1 先用 `report_config` 交叉验证再动模板。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "平台补强：显式无主行",
      "tasks": ["1", "2"],
      "parallel": false,
      "rationale": "soe 末行「其他」若不标 unowned，H2 在建工程段推送就会删掉它；这是所有 owner 接入的前提"
    },
    {
      "wave": 2,
      "name": "模板结构修订",
      "tasks": ["3", "4"],
      "parallel": false,
      "rationale": "Task 3 改 report_row_code 是段归属真源，Task 4 的守卫要读它的结果做三向比对"
    },
    {
      "wave": 3,
      "name": "共享映射件 + 首个 owner（E1）",
      "tasks": ["5", "6", "7"],
      "parallel": false,
      "rationale": "Task 5 的共享件是全部 owner 的输入；E1 作为首个消费者验证端到端链路后其余 owner 才照抄"
    },
    {
      "wave": 4,
      "name": "其余 owner 逐个接入",
      "tasks": ["8", "9", "10", "11", "12", "13"],
      "parallel": true,
      "rationale": "各 owner 改各自循环的披露 Tab + 一份薄壳，互不依赖；共享件与平台能力已就绪"
    },
    {
      "wave": 5,
      "name": "勾稽与收口",
      "tasks": ["14", "15", "16"],
      "parallel": false,
      "rationale": "勾稽要等各段都能推；实测在勾稽之后；CI 最后登记"
    }
  ]
}
```

## Wave 1 — 平台补强：显式无主行

- [x] 1. `row_type: "unowned"` → 段可写区排除
  - `note_shared_table_segments.py`：`_is_unowned_row()` + `split_segments` 计算
    `data_end` 时取「段尾合计行右界」与「段内首个 `unowned` 行下标」的**更小者**
  - `unowned` 位于段中间时可写区止于其前（**不跨越保留**，否则 owner 数据被劈成两段）
  - 生成器清单重跑（`data_end` 可能变化）+ `--check` 0 欠账
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [x] 2. `unowned` 守卫 + 零回归
  - Property 2/3/4：真实模板行集 + 内联 fixture（段中间 / 段尾 / 多个 `unowned`）
  - **PBT**：随机位置插 `unowned` → 可写区永不跨越它、`start < data_end <= end` 恒成立
  - **反向自检**：去掉 `unowned` 判定，相邻段推送必删掉该行
  - Property 3：全部 29 张共享表在**无 `unowned` 行**时 `(start,end,data_end)` 与引入前相同
    （拿当前 `note_shared_table_segments.json` 作 golden，改动后逐段比对）
  - `disclosure-note-row-level-merge` 的 4 个测试文件不改断言跑绿
  - _Requirements: 2.4, 5.5_

## Wave 2 — 模板结构修订

- [x] 3. `fix_note_restricted_assets_structure.py`（`--dry-run` / `--check`）
  - **段归属纠错（先用 `report_config` 交叉验证再动）**：
    - soe「应收款项融资」补 `report_row_code = "BS-007"`（现 `null`，被卷进 D2 段）
    - soe「存货」`BS-008` → **`BS-010`**（`BS-008` 实为预付款项；listed 侧本就是 `BS-010`）
    - soe 末行「其他」标 `row_type = "unowned"`
  - **列元数据**：三张子表补 `columns`（listed 主表 2 列 / listed 续表 2 列 / soe 3 列，
    标签列必标 `flat`）+ `guidance`（写明本表跨循环共享、各段 owner、合计口径）
  - **假行**：删 listed 两表的 `row_type = "header_label"` 行
  - **续表正名**：`续：` → `所有权或使用权受到限制的资产（续：上年年末）`（走 `rule(aliases=)`，
    **不能进 drops**），旧名进 legacy 种子
  - 复用 `_note_structure_kit`；`rows=None` 不动其余行集
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 4. 模板守卫 `test_note_restricted_assets_structure.py`
  - openpyxl 直读源 xlsx 三向比对表名/列头/行集（先定位源 sheet：逐个 owner 循环的
    披露 sheet 里找「受到限制」块；找不到就以附注模板 + `report_config` 双源锁死并写明）
  - Property 1：每段 `owner_row_code` 都能在 `report_config` 查到**同名**报表行
  - Property 5/6/7：合计行存活 / columns 齐备且单级 / 续表正名 + 旧名在 legacy 种子
  - 反向自检：把「存货」改回 `BS-008` 则 Property 1 必红
  - _Requirements: 5.1, 5.4_

## Wave 3 — 共享映射件 + 首个 owner（E1）

- [x] 5. `restrictedAssetsNoteSectionMap.ts`（共享件）
  - `RESTRICTED_ASSETS_NOTE_SECTION` / `RESTRICTED_ASSETS_TABLE` /
    `RESTRICTED_ASSETS_OWNERS`（owner code → 段标签，与模板逐字一致）
  - 零入参 `buildRestrictedAssetsColumns()`（3 张表的列定义，登记 `P1_ROUTE`）
  - `buildRestrictedAssetsPayloads(variant, wpId, standards, { ownerRowCode, rows })`
    → listed 返 2 个（主表期末 + 续表上年年末）、soe 返 1 个；**空数据返 `[]`**
  - _Requirements: 3.1, 3.3, 3.5, 3.6_

- [x] 6. E1 owner 接入（`BS-002` 货币资金）
  - 数据源 = E1 ②表「受限制的货币资金明细」（期末/期初 + 受限原因，与 soe 三列天然对齐）
  - `E1TabDisclosure` 加 `syncRestrictedAssetsToNote()`，与外币段同款并列调用；
    把 `restrictedRows` 加进自动同步 watch（它已在依赖数组里，确认即可）
  - 消费 `row_scope_unresolved` 给用户提示
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 7. E1 契约测试 + 平台守卫回归
  - Property 8/9/10/14：双期两 payload / 变体列差异 / 空数据不推 / 平台守卫扫到
  - `disclosureSharedTableRowScope.spec.ts` 应自动把新映射判为「已声明」（无需改守卫）
  - `disclosureColumnsCoverage` 的 `P1_ROUTE` 登记 `buildRestrictedAssetsColumns`
  - _Requirements: 5.2, 5.3_

## Wave 4 — 其余 owner 逐个接入

> 每条的验收口径相同：载荷带 `_row_scope` + 他段逐字不变 + 空数据不推 +
> 契约测试断言 `owner_row_code` ∈ 段集合 + 平台守卫判为已声明。
> 接入前必先确认该循环披露 Tab **已有**受限资产录入位置；没有的**不接**（宁缺勿造），
> 改为在 spec Notes 里记录缺口并归属该循环的 per-cycle spec。

- [x] 8. D1 owner（`BS-005` 应收票据）—— 数据源「期末已质押的应收票据」
  - ✅ **已接入**：`pledgedRows: {category, pledgedAmount}` 是结构化受限金额（质押 = 受限）
  - 该表**只有期末口径**（无上年年末）→ `priorAmount` 不声明，共享件据此
    **只推 listed 主表、不推续表**（推 0 会覆盖审计师在续表手填的上年年末值）
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 9. 共享采集件：`restrictedAssetsSources.ts` + `useRestrictedAssetsSync.ts`
  - 声明表 `RESTRICTED_ASSETS_SOURCES`（owner → `{wpCode, itemIds, note, collect}`），
    纯函数、零 Vue 依赖；`readRestrictedRows` 支持 legacy 键按优先级回退
  - `condenseReasons`：原因去重后最多 3 条、其余写「等」（**金额一条不少**）
  - `reasonOf` 只收 ≤16 字短限定词（底稿 `description` 是长串拼接，不进附注列）
  - `useRestrictedAssetsSync`：读 → 归纳 → 带 `_row_scope` 推送 → `row_scope_unresolved`
    提示 → `eventBus` 广播；空数据/只读/缺 projectId 静默跳过
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 10. D2 owner（`BS-006` 应收账款）—— 数据源 `D2-pledge-rows`
  - D2-12 质押检查表 `PledgeRow.{pledgeAmount, pledgee, pledgePurpose}`
  - 只有期末口径 → listed 只推主表、不推续表
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 11. H1 owner（`BS-028` 固定资产）—— 数据源 H1-16/H1-17 抵押行
  - `H1-listed-mortgage-rows` / `H1-soe-restricted-rows`（同一次 merge 写入两个键，
    内容相同 → 变体无关）+ legacy `H1-disc-listed-restricted-rows`
  - 两个变体 Tab 各接一次；`titleCertRows`（未办妥产权证书）**不进**受限表
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 12. H2 owner（`BS-029` 在建工程，**仅 soe**）—— 数据源 `H2-listed-mortgage-rows`
  - H2-2 明细 `isMortgaged='Y'` 带入，金额优先审定净值
  - 键名带 `listed` 是**历史命名**，内容是与变体无关的底稿事实；段只在 soe，
    故只有 soe Tab 调用 + `isRestrictedAssetsOwnerApplicable('listed','BS-029')===false` 双保险
  - _Requirements: 3.1, 3.2, 3.6_

- [x] 13. I1 owner（`BS-032` 无形资产）—— 数据源 `I1-8-rows`
  - 取 `mortgageRestricted==='Y'` 的行、金额取 `mortgageValue`
    （与 `useI1TitleCheck.totalMortgage` 同口径），两个变体 Tab 各接一次
  - **顺带修掉 I1 两个 Tab 的自调度**（`syncToNotes` 内 `scheduleAutoSync(syncToNotes)`
    = 800ms 周期无限 POST；平台守卫只认 `syncToDisclosureNotes` 这个函数名故逃过清理）
    → 改 watch 实际数据 + `autoSyncToNotes()` 包装（自动路径不弹模态确认框）
  - _Requirements: 3.1, 3.2, 3.3_

## Wave 5 — 勾稽与收口

- [x] 14. 合计勾稽 + 段级溯源
  - 纯函数 `restrictedAssetsConsistency.ts`：合计行 = 全部数据行之和（含无主行「其他」，
    容差 0.01）；**soe 源模板无合计行 → skip**；未接入的段 **skip 不 error**；
    `_seg` 段戳泄漏到附注行 → error
  - 段级溯源：`RESTRICTED_ASSETS_OWNER_WP`（owner → wp_code，全 8 段）+
    `resolveRestrictedRowOwner`（`_seg` 优先、回退行标签反查）+
    `describeRestrictedRowProvenance`；与声明表的 `wpCode` **交叉锁死**
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 15. 真实 DB + 浏览器实测 + 数据复原
  - 新建 `verify_restricted_assets_merge_live.py`（变体/note-id/user-id 由 CLI 传入）
  - 真实 DB：**逐 owner 依次推 6 段** → 每次断言本段被替换、他段行数不变、
    无主行「其他」存活且未被打段戳；不存在的 owner 验 fail closed（整表逐字未变）
  - 浏览器：D2/H1/H2/I1 四个国企披露 Tab 全部挂载、零 console error、同步按钮在
  - **先快照后改、按 md5 逐字节复原**
  - _Requirements: 3.2, 3.4, 4.1_

- [x] 16. CI 登记 + 复盘
  - `note-restricted-assets-structure`（脚本 `--check` + 后端守卫 + 段清单）
    与 `note-restricted-assets-frontend`（3 个契约文件 + 平台 row-scope 守卫回归）
  - `yaml.safe_load` 校验通过（82 job）+ 引用的 7 个路径全部存在
  - 复盘写回 Notes（下方 Wave 5 实录）
  - _Requirements: 5.3_

## Notes

### Wave 1 落地实录（2026-08-02）

**产出**：`note_shared_table_segments.py` 新增 `UNOWNED_ROW_TYPE = "unowned"` +
`_is_unowned_row()`；`split_segments` 在算完「段尾合计行右界」后，再取**段内首个
`unowned` 行**下标进一步收窄 `data_end`（两者取更小者）。守卫 8 条 + 1 条 PBT。

**零回归凭据（Property 3）**：全库 29 张共享表**目前无任何 `unowned` 行** →
重算后 `(start, end, data_end)` 与引入该字段**之前**生成的
`note_shared_table_segments.json` 逐段相同。守卫直接拿清单当 golden 比对，
并断言「若哪张表出现 `unowned` 行则本用例必须更新」（防止零回归凭据悄悄失效）。

**落地时踩到的一个测试自身缺陷**：首版用 `(variant, section_number, table_name)`
建字典比对清单 → `三、在合营安排或联营` 章节里**有两张重名表 `项  目`**，
建字典会互相覆盖，报出假漂移 `(1,6,6) != (1,4,4)`。改为**按顺序**比对 29 条。
（同款陷阱在任何「按表名建索引」的地方都存在 —— 全库 29 张共享表里有 3 个重名/空名。）

**段首行保护**：模板若把段首行本身标成 `unowned`（写错），可写区仍保住段首行
（`data_end >= start + 1`），不产出空区间 —— PBT 与专门用例双向锁死。

### Wave 2 落地实录（2026-08-02）

**产出**：`backend/scripts/fix/fix_note_restricted_assets_structure.py`（12 处变更 →
`--check` 0 欠账 → 重复 `--dry-run` 0 变更）+ 守卫
`backend/tests/test_note_restricted_assets_structure.py`（22 例）。

**修订结果实测**：

| 表 | 行数 | 段 | 可写区收窄 |
|----|------|----|-----------|
| listed 主表 | 8（删假行后） | 6 | `BS-032` `[5,8)` → `data_end=7`（合计行保住、`……` 在区内） |
| listed 续表（已正名） | 8 | 6 | 同上 |
| soe | 9 | 8（补 `BS-007`、纠 `BS-010`） | `BS-029` `[7,9)` → `data_end=8`（`unowned` 的「其他」保住） |

**🔴 源模板真相（诚实记录，与立 spec 时的假设不同）**：全量扫 349 个 xlsx 后确认
**`backend/wp_templates/` 里没有这张披露表的 sheet**。唯一相关的是
`A3-5 合并附注汇总-2019.xlsx` / `A3-6 母公司附注汇总-2019.xlsx` 的 sheet
「所有权受限资产」—— 那是**合并/母公司按主体横向展开的汇总工作表**
（审定数/抵消数/汇总/母公司审定/子公司1..N，行只有 货币资金·应收票据·存货·固定资产·
无形资产 + 2 空行 + 合计），**不是附注披露表本身**。
故守卫按 spec 预留的兜底口径执行：**附注模板 + `report_config` 双源锁死**，
A3-5/A3-6 的 5 个科目作**旁证**（openpyxl 直读断言它们都在附注行集里），
并加一条**反向自检**「源 xlsx 里确实没有该披露表 —— 哪天补了本用例必红，
届时守卫要改成直读源 sheet 的三向比对」。

**soe 表无合计行**（源模板如此，9 行止于「其他」）→ design 的 Property 5
只适用 listed 两表，守卫按 `listed 有 / soe 无` 双向锁死，不得凭空加合计行。

**连带更新的既有守卫（3 处，都写明了理由）**：
1. `tests/services/test_note_template_row_type.VALID_ROW_TYPES` 加 `unowned`
   + `scripts/migrate_disclouse_notes_to_v2.VALID_ROW_TYPES` 同步（两处必须一致）
2. `tests/test_note_shared_table_segments.py` 与前端
   `disclosureSharedTableRowScope.spec.ts` 的基线：可写区收窄段数 **14 → 15**、
   可扫描表名 **14 → 15**（`续：` 正名后不再是脏名，从 `GENERIC_TABLE_NAMES` 移出）；
   listed `五、32` 的下标断言整体前移一位（删假行）
3. `tests/test_note_report_row_code_alignment._MANUAL_ALLOWLIST`：
   `soe|八、93|存货|BS-008` → `BS-010`（「存货」标签在 `report_config` 里本身
   ambiguous，`BS-010` 是按公式实证选定的）

**顺带清掉 2 条不属本 spec 的陈旧 allowlist 条目**（守卫要求「已消失必移出」）：
`listed|五、1|其他货币资金|BS-002` 与 `soe|八、18|其他综合收益|BS-053` —— 两处的
`report_row_code` 已被 e1 / g7 两个 spec 重写章节时置空（实测确认现为 `null`），
与本 spec 的 `八、93` 改动无关。

**回归基线**：相关 280 passed / 1 skipped。另有**预存在失败**（与本次无关，
`git status` 显示相关测试文件干净）：`test_note_template_ar_soe_structure.py` 6 例
（D2 `八、5` 的 `_aligned_by` 被 `d-cycle-extraction-chain-completion` 覆盖，属 D 类 spec）、
`test_note_bold_marker_hygiene.py` 2 例（`五、8`/`八、9` guidance 残留 `**`，属 K1 spec，
memory 已记「循环级脚本与平台级 `fix_note_bold_markers.py` 互相打架」）、
`test_note_template_variant_matrix.py` 3 例（memory 已记为失效测试）。

### Wave 3 落地实录（2026-08-02）

**产出**：
- `composables/restrictedAssetsNoteSectionMap.ts`（八循环共享件）：
  `RESTRICTED_ASSETS_NOTE_SECTION` / `RESTRICTED_ASSETS_TABLE`（3 张子表名）/
  `RESTRICTED_ASSETS_OWNERS`（8 段 code → 段标签）/ `RESTRICTED_ASSETS_SOE_ONLY_OWNERS` /
  `isRestrictedAssetsOwnerApplicable` / 零参 `buildRestrictedAssetsColumns` /
  `summarizeRestrictedRows` / `buildRestrictedAssetsPayloads`
- `E1TabDisclosure.vue` 发**第三个 payload**（`syncRestrictedAssetsToNote`，
  与主章节 + 外币段并列；`restrictedRows` 本就在自动同步 watch 依赖里）
- 契约测试 `restrictedAssetsNoteSectionMap.spec.ts`（25 例）+ `P1_ROUTE` 登记

**设计判断（写下来免得下一个 owner 走偏）**：
该附注表是**按资产类别**披露（一个科目一行），而各循环底稿的受限数据是**按受限类别**
分行（E1 ②表：银行承兑保证金 / 信用证保证金 / 境外受限 …）。故 owner 推送时
用 `summarizeRestrictedRows` 归纳成**一行**（金额求和、受限原因去重拼接 `；`），
类别明细留在各自的附注章节（E1 的 ②表在 `五、1`/`八、1`）。
行级合并允许段内行数 ≠ 模板段行数，所以想推明细行也不会报错 —— 但那会让
「按资产类别」的表变成明细表，与源模板口径不符。

**「只有原因、没有金额」也算有实质数据** → 照推（受限事实本身要披露）；
只有「全零 + 无原因」才返回 `[]` 不推。

**listed 双期 = 两个 payload**（主表 `end_amount` / 续表 `prior_amount`），
两次都带 `_row_scope`（owner 相同、表名不同），**各自独立返回不做事务耦合**。
listed 侧**不推 `reason`**（源模板 2 列）—— 平台铁律「底稿可多留审计列，
同步时投影成附注形状」。

**平台守卫零改动即生效**：`disclosureSharedTableRowScope.spec.ts` 扫的是
`*NoteSectionMap.ts`，新文件天然被扫到并判为「已声明 `_row_scope`」；
`owner_row_code ∈ 段集合` 也自动通过（该文件含全部 8 个 code，是三张表段集合的并集）。

**E1 侧守卫含反向边界**：断言源码里**只有** `'BS-002'`，出现任何他段 code 即红
（防止 E1 越权覆盖别人的段）。

**回归**：前端 `restrictedAssets` 25 例 + 相关 8 文件通过；唯一失败是预存在基线
（`disclosureColumnsCoverage` 挂 `buildJ2{Listed,Soe}Columns` 未登记 `P1_ROUTE`，
commit `f7b28ff0` 起就红）。后端 166 passed。

### Wave 4 落地实录（2026-08-02）—— 8 段里 6 段已接，只有 2 段真的没数据

**🔴 首轮判定被用户推翻，此处是返工后的正确结论。**

首轮我按「披露 Tab 里有没有受限金额录入控件」判定，把 D2/H1/H2/I1 全判成「不接」
（连同 D5/F2 共 5 条）。用户指出标准过严：**「有些表只有期末数，你直接接期末数即可，
不需要期初」**。深查后确认首轮 4 条是误判 —— 这些循环的受限金额**都有结构化落库**，
只是不在披露 Tab 的行模型里，而在**底稿 Tab 写进 `checklist_responses` 的键**里：

| owner | 循环 | `checklist_responses` 键 | 行字段 | 期初 |
|-------|------|--------------------------|--------|------|
| `BS-002` | E1 | 披露 Tab 内存行模型 `restrictedRows` | `endingAmount`/`openingAmount`/`reason` | 有 |
| `BS-005` | D1 | 披露 Tab 内存行模型 `pledgedRows` | `pledgedAmount` | 无 |
| `BS-006` | D2 | `D2-pledge-rows`（D2-12 质押检查） | `pledgeAmount`/`pledgee`/`pledgePurpose` | 无 |
| `BS-028` | H1 | `H1-listed-mortgage-rows` / `H1-soe-restricted-rows`（H1-16/17 带入） | `name`/`amount`/`description` | 无 |
| `BS-029` | H2 | `H2-listed-mortgage-rows`（H2-2 `isMortgaged=Y` 带入） | `name`/`amount` | 无 |
| `BS-032` | I1 | `I1-8-rows`（无形资产权属检查） | `mortgageRestricted`/`mortgageValue`/`mortgageNature` | 无 |
| `BS-007` | D5 | — | — | **真的没有** |
| `BS-010` | F2 | — | — | **真的没有** |

**🔴 三条修正后的判定原则**：
1. **受限金额是「底稿事实」不是「披露变体产物」** —— 它落在 `checklist_responses`
   里，与 listed/soe 无关；变体只决定附注怎么呈现（listed 2 列双期拆两表 /
   soe 3 列含受限原因）。所以 `H2-listed-mortgage-rows` 这种**键名带 `listed`
   的历史命名**照样能喂 soe 段（内容本身与变体无关，段只在 soe 是**附注**侧的事）。
2. **「只有期末数」不是不接的理由** —— 只有期末就只推期末，listed 侧不推
   「（续：上年年末）」续表。只有「真的一条结构化受限金额都没有」才登记不接。
3. **「未办妥权属证书」≠「所有权或使用权受到限制」**（这条首轮就对，保留）——
   H1/I1 的 `titleCertRows` 是产权证书未办妥的独立披露要求，推进受限资产表
   就是自造披露内容。I1 的正确来源是 I1-8 里的 `mortgageRestricted=Y` 行。

**产出（Task 9~13）**：
- `composables/restrictedAssetsSources.ts` —— **声明式来源表**（4 条，纯函数零 Vue 依赖）：
  `readRestrictedRows`（legacy 键按优先级回退、非 JSON/空数组跳过）/
  `condenseReasons`（原因去重后最多 3 条 + 「等」，**金额一条不少**）/
  `reasonOf`（只收 ≤16 字短限定词）/ `RESTRICTED_ASSETS_UNSOURCED`（只剩 2 条）
- `composables/useRestrictedAssetsSync.ts` —— **一行接线件**：读 → 归纳 →
  带 `_row_scope` 推送 → `row_scope_unresolved` 提示 → `eventBus` 广播；
  空数据/只读/缺 projectId 静默跳过（**不推空段**）
- 6 个披露 Tab 各一行接入：`D2DisclosureNoteBody` / `H1TabDisclosureListed` /
  `H1TabDisclosureSoe` / `H2TabDisclosureSoe` / `I1TabDisclosureListed` / `I1TabDisclosureSoe`

**🔴 为什么把 `description` 丢掉**：底稿的 `description` 是拼接串
（`权利限制:抵押；性质:银行借款抵押；抵押权人:工商银行某分行；抵押面积:1200㎡；
权证:粤(2020)某字第123号；抵押/账面金额:1,000,000`），塞进附注「受限原因」列会变成
不可读的数据倾倒 → 只用 `质权人 / 质押目的 / 抵押性质` 这类审计师手填的短字段。

**顺带修掉一处预存在 P0（I1 两个 Tab）**：`syncToNotes()` **内部**调
`autoSync.scheduleAutoSync(syncToNotes)` = 调度自己 → 点一次同步就进入 800ms 周期的
无限 POST（直到组件卸载 `cancelPending`）。平台守卫 `disclosureAutoSyncCoverage`
的自递归检测**只认 `syncToDisclosureNotes` 这个函数名**（`syncFnBody` 正则写死），
I1 用 `syncToNotes` 命名故逃过了那一轮 16 处清理。修法：删掉自调度 + 监听实际数据
（与 `buildI1{Listed,Soe}SyncPayloads` 所用字段一致）+ 新增 `autoSyncToNotes()` 包装
（有阻断项/编制提示时自动路径直接跳过 —— 自动同步**绝不弹模态确认框**，
与 memory 记的 I6 同款问题不再复制）。守卫已在契约测试里钉死（含函数体大括号配平截取
+ 「找不到 syncToNotes 则本用例必红」的空转自检）。

**守卫「owner 接入状态登记」升级**：`WIRED` 改为 8 条 + `mode: 'direct' | 'shared'`
（E1/D1 是内存行模型直接调载荷构造器；其余 6 个走共享 composable，
断言 `useRestrictedAssetsSync` + **真的 `await syncRestrictedAssets(`** 调用，
防「只建实例不调用」假接入）；新增「variant 声明必须对」（listed Tab 不许写 `'soe'`）；
`NOT_WIRED_OWNERS` **5 → 2**，上限同步收紧到 2（只许变少）。

**未接入 owner 的缺口归属**：D5(`BS-007`) → `d-cycle-*`；F2(`BS-010`) → `f2-*`。
补齐结构化受限录入位置后在 `restrictedAssetsSources.ts` 加一条声明即可接入。

**回归**：`restrictedAssets` 两个契约文件 **66 例全绿**；D2/H1/H2/I1/E1/D1 相关
**162 文件 / 2331 例全绿**；9 个改动文件 Vite transform 全 200。平台守卫
`disclosureSharedTableRowScope` / `disclosureSheetNameRegistry` 绿；
两个失败是**预存在基线**（`disclosureColumnsCoverage` 挂 `buildJ2{Listed,Soe}Columns`
未登记 `P1_ROUTE`、`disclosureAutoSyncCoverage` 挂 `D2TabDisclosure.vue` 的
显式 props 委托无法被 `resolveDelegate` 识别，均在 memory 已记）。

### Wave 5 落地实录（2026-08-02）

**Task 14 产出**：`composables/restrictedAssetsConsistency.ts`（纯函数）+ 23 例守卫。

三条 check：①合计行 = 全部数据行之和（**含**无主行「其他」，容差 0.01 元）；
**soe 变体 skip**（源模板无合计行）②逐段比对附注金额 vs 该循环底稿受限金额，
**未提供底稿金额的段 skip 不 error**（「附注有值而底稿没接」既可能是审计师在附注
模块手填、也可能是该 owner 还没接推送，报 error 会把两种正常情形一起打红）
③`_seg` 段戳泄漏到附注行 → error。

段级溯源：`RESTRICTED_ASSETS_OWNER_WP`（owner → wp_code，**全 8 段**；声明表只有 4 条，
E1/D1 走内存行模型不在里面，故不能从声明表派生）+ `resolveRestrictedRowOwner`
（`_seg` 优先、回退行标签反查）+ `describeRestrictedRowProvenance`。
守卫断言两处 wp_code **交叉锁死**（改一侧漏一侧必红）。

**遗留（已明示，不算完成）**：附注编辑器侧把 provenance 渲染成 tooltip / 溯源列
属附注模块的 UI 工作，本 spec 只提供 derivation 真源。

**Task 15 —— 真实 DB 直跑 95 条断言全绿**
（`python -m scripts.diagnose.verify_restricted_assets_merge_live --note-id
7deac406… --user-id … --variant soe`，项目 `a7fc75e5` / `八、93`）：

- **模板段边界实证**：`BS-002(0,1,1)` `BS-005(1,2,2)` `BS-006(2,3,3)` `BS-007(3,4,4)`
  `BS-010(4,5,5)` `BS-028(5,6,6)` `BS-032(6,7,7)` **`BS-029(7,9,8)`**
  —— 末段 `data_end=8` 正确排除了下标 8 的 `unowned` 行「其他」
- 逐 owner 推 6 段，每次 `row_scoped_tables=[表名]` / `row_scope_unresolved=[]`；
  本段替换为 1 行、标签/金额/受限原因分文不差；**他段行数每次都不变**
- 「其他」行每次都存活且 `_seg` 为**空串**（不属任何 owner）
- **未接入的 BS-007/BS-010 是纯标签骨架**（`{"_seg":"BS-007","label":"应收款项融资"}`，
  无任何数值列）—— 宁缺勿造在落库层得到实证
- fail closed（`BS-9999`）→ `row_scope_unresolved=[表名]` + `row_scoped_tables=[]`
  + `sub_table_data` **逐字未变**（服务端日志 `reason=owner_row_code_not_in_template`）
- **复原**：`table_data` md5 `29975c5b…` 前后相同；`text_content` / `last_sync_at`
  / `last_sync_user_id` / `updated_by` / `last_sync_source` 全部回到原值（均为 NULL）

**浏览器实测（chrome-devtools）**：D2（项目 `2aa00f57` / wp `7c1ee1f6`）与
H1 / H2 / I1（项目 `c8621493` / wp `e7d2459f` · `bb31c194` · `77168d01`）
四个**国企**披露 Tab 全部正常挂载（表格 11 / 6 / 4 / 4，输入 72 / 88 / 27 / 133），
`vite-error-overlay` 无，**console error 0**，「同步到附注」按钮在。
只做挂载与无错校验、**未触发同步写库**（服务端链路已由真实 DB 直跑覆盖），
实测后 `disclosure_notes` 近 2 小时零写入（SQL 确认）。

🔴 **上市侧仍无活体**：`五、32` 只有项目 `0ec33ac9` 是 `source_template=listed`，
而该项目 `entity_type=soe` → 推 `listed_standalone` 会被
`standard_unification_service.detect_standard_conflict` 拦成 409（与
`disclosure-note-row-level-merge` 同款遗留）。listed 侧由 40 例契约测试
+ 模板三向比对覆盖。

**🔴 实测顺带发现的两个平台级事实（不属本 spec，已记档）**：

1. **本表的 legacy 快照有 note 侧公式绑定值，首次推送后会消失**。项目 `a7fc75e5`
   的 `八、93` 原 `table_data._tables[0].rows` 是**位置化 legacy 快照**，9 行都带
   `_cell_meta.binding_id = "八、93.货币资金.closing_balance"` 并已取到真实金额
   （货币资金 112,166,836.03 / 应收账款 3,145,022,332.65 / 固定资产 62,946,084.85 …）。
   任何 owner 首次推送会把该章节翻成 `_source=workpaper` → 投影器只渲染
   `sub_table_data`、不与 `_tables` 合并（memory 已记的平台语义）→ **未接入段
   （D5 应收款项融资 / F2 存货）会从「有绑定金额」变成「空骨架」**。
   这是既有平台语义（不是行级合并引入的），但本表因「零 pusher + 有绑定值」
   而格外显眼 → 归属 `disclosure-note-follow-actual-content` 的 legacy 迁移议题。
2. **`H1-soe-restricted-rows` 是孤儿写入键**：`useH1TitleCheck.syncMortgagedToDisclosure`
   往它写数据，但 `H1_SOE_KEYS` 没有对应条目、H1 国企披露 Tab 也不读它
   → 该键此前从未被消费过。本 spec 的声明表把它列为 H1 的来源键之一
   （与 `H1-listed-mortgage-rows` 同内容），算是给它找到了第一个消费者。

**Task 16**：CI 两个 job（`note-restricted-assets-structure` /
`note-restricted-assets-frontend`），`yaml.safe_load` 校验通过（全文件 82 job），
引用的 7 个脚本/测试路径逐个 `os.path.exists` 确认存在。

### 立 spec 时已实证的事实（不需重复验证）

| 事实 | 证据 |
|------|------|
| listed `五、32` 主表 9 行 / 「续：」9 行 / soe `八、93` 9 行 | 逐行读 `note_template_*.json`（2026-08-02） |
| listed 段 6 个 / soe 段 7 个 | `split_segments` 实测 |
| **soe「存货」标 `BS-008`（预付款项）是错码** | `report_config` 实证 `BS-008 = TB('1123')` 预付款项、`BS-010 = SUM_TB('1401~1499')` 存货；listed 侧标的 `BS-010` 是对的 |
| **soe「应收款项融资」缺 `report_row_code`** | 该行 `account_codes=['1124']`，`report_config` 实证 `BS-007 应收款项融资 = TB('1124')` |
| soe 末行「其他」被卷进 `BS-029 在建工程` 段 | 段 `[7,9)`，「其他」在下标 8，不是合计行故 `data_end` 不剔除 |
| listed 两表 `[0]` 是 `header_label` 假行 | md 重建把压扁的第二行表头留成数据行 |
| 三张子表 `columns=0` + `guidance` 空 | 逐表读模板 |
| 末段合计行已由平台 `data_end` 保住 | `disclosure-note-row-level-merge` Task 15，5 张真实表参数化守卫含本表两张 |
| 该表**零 pusher** | 平台守卫 `disclosureSharedTableRowScope.spec.ts` 全量扫描无命中 |

### 关键踩坑预防（本 spec 直接适用）

- **改 `report_row_code` 前必查 `report_config`** —— 它是段归属真源；本表已查出两处错
- **`unowned` 不跨越保留**：段中间的无主行让可写区提前截断，别试图「跳过它继续」
- **续表改名走 `rule(aliases=)` 不进 `drop_tables`**（drop 在 apply 前执行会连行删掉）
- **`flat` 必须 seed 与推送两处都加**（H8 踩过只加一侧的坑）
- **listed 是双期拆两张表**，两次推送各自独立，不做事务耦合
- **没有录入位置的 owner 不接**（宁缺勿造），把缺口记进 Notes 并归属对应 per-cycle spec
- **守卫读源码先 `stripComments()` + 反向自检**
- **PowerShell `>` 重定向会腌坏 UTF-8 中文** → 诊断脚本用 Python 自己写盘
- **`read_file` 对本会话改过的文件返回陈旧版本** → 判落盘真相用 Python 直读

### 与平台 spec 的衔接

`disclosure-note-row-level-merge`（14/14 + Task 15）提供：`_row_scope` 触发、
`_merge_rows_by_scope`、`Segment.data_end`（表级合计行保护）、共享表清单与 drift 守卫、
平台守卫「推共享表必带 `_row_scope`」。本 spec 只新增 `row_type: "unowned"`
这一项平台能力（Wave 1），其余全是本表的接入工作。
