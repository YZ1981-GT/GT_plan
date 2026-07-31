# Implementation Plan: K 循环披露表 ↔ 附注对齐

## Overview

按结构相似度分三批：批 1 损益类 K8~K13（同构单表，含三个 P0）→ 批 2 负债/递延类 K3 K4 K5 K7 → 批 3 复杂类 K1 K6。
每批四件套：附注模板幂等脚本 → 同步映射 → 组件 → 守卫，批末浏览器实测。

## Task Dependency Graph

```
0 (普查/裁决，已完成)
   ├──> 1 批1 模板脚本 ──> 2 批1 shared+6 map ──> 3 批1 组件 ──> 4 批1 守卫 ──> 5 批1 实测
   ├──> 6 批2 模板脚本 ──> 7 批2 map ──────────> 8 批2 组件 ──> 9 批2 守卫 ──> 10 批2 实测
   └──> 11 批3 模板脚本 ─> 12 批3 map ─────────> 13 批3 组件 ─> 14 批3 守卫 ─> 15 批3 实测
```

- 批与批之间无强依赖（不同循环、不同章节），但**不并行推进**（同改 `note_template_*.json` 与 `disclosureColumnsCoverage.spec.ts`）
- 每批内部严格顺序：模板 → 映射 → 组件 → 守卫 → 实测

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1"], "desc": "批1 附注模板幂等修订（K8~K13）" },
    { "wave": 1, "tasks": ["2"], "desc": "批1 共享 helper + 6 份 map 重写", "depends_on": [0] },
    { "wave": 2, "tasks": ["3"], "desc": "批1 12 份组件改造", "depends_on": [1] },
    { "wave": 3, "tasks": ["4"], "desc": "批1 守卫（契约 / sheet 名 / 后端结构 / CI）", "depends_on": [2] },
    { "wave": 4, "tasks": ["5"], "desc": "批1 测试回归 + 浏览器实测", "depends_on": [3] },
    { "wave": 5, "tasks": ["6", "7", "8", "9", "10"], "desc": "批2 K3/K4/K5/K7", "depends_on": [4] },
    { "wave": 6, "tasks": ["11", "12", "13", "14", "15"], "desc": "批3 K1/K6", "depends_on": [5] }
  ]
}
```

## Tasks

- [x] 1. 批1 附注模板幂等修订（K8~K13）
  - [x] 1.1 建 `backend/scripts/fix/fix_note_k_pl_structure.py`：K11/K12/K13 listed 表名 `项  目` → 科目名
    - _Requirements: 2.4, 4.3_
  - [x] 1.2 删占位说明行（`可无限量添加行` / `......` / `……`），语义移入 `guidance`
    - _Requirements: 3.6_
  - [x] 1.3 13 张表补 `columns`（显式 `flat`）+ `guidance`，删 `_column_groups`
    - _Requirements: 4.1, 4.2_
  - [x] 1.4 `--dry-run` 核对后 apply，再 `--check` 验幂等
    - _Requirements: 4.3_

- [x] 2. 批1 同步映射
  - [x] 2.1 建 `composables/kPlDisclosureShared.ts`（列/行/载荷构造 + 合计派生）
    - _Requirements: 3.1, 3.4_
  - [x] 2.2 6 份 `kXNoteSectionMap.ts` 重写：sheet 名改全角、章节号改模板实测值、子表名对齐、行常量
    - _Requirements: 1.1, 2.1, 2.2_
  - [x] 2.3 加零参 `build{X}ListedColumns` / `build{X}SoeColumns`（含 K10 soe 第 4 列、K12/K13 第 4 列）
    - _Requirements: 3.2, 3.3, 3.4_
  - [x] 2.4 载荷加 `_removed_table_keys`（历史泄漏表名）
    - _Requirements: 5.4_
  - [x] 2.5 重跑 `gen_note_wp_sync_registry.py --write`
    - _Requirements: 1.3_

- [x] 3. 批1 组件改造（12 份）
  - [x] 3.1 载荷调用改为传第 4 列值（K12/K13 非经常性损益、K10 soe 政府补助标记）
    - _Requirements: 3.2, 3.3_
  - [x] 3.2 可编辑金额 `el-input-number` → `WpAmountInput`；只读金额 → `fmtAmount`
    - _Requirements: 5.1, 5.2_
  - [x] 3.3 K9/K11/K12/K13 补 AI 辅助（prompt ≥20 字 + 「不得虚构」）
    - _Requirements: 5.3_

- [x] 4. 批1 守卫
  - [x] 4.1 `composables/__tests__/kPlNoteSubtableContract.spec.ts`（共享 helper + 列同形 + 合计 + 第 4 列）
    - _Requirements: 6.1_
  - [x] 4.2 后端 `tests/services/test_note_k_sheet_names.py`（openpyxl 实读 tab 名 vs `.ts` 常量）
    - _Requirements: 1.4_
  - [x] 4.3 后端 `tests/services/test_note_k_pl_structure.py`（含反向自检）
    - _Requirements: 6.3_
  - [x] 4.4 `disclosureColumnsCoverage.spec.ts` 登记 12 个 `P1_ROUTE`
    - _Requirements: 6.2_
  - [x] 4.5 CI job `note-k-pl-structure`
    - _Requirements: 6.3_

- [x] 5. 批1 验证
  - [x] 5.1 前端 vitest + 后端 pytest 绿
    - _Requirements: 6.1, 6.2, 6.3_
  - [x] 5.2 浏览器实测（抽 K12 / K10 两变体，比对落库）
    - _Requirements: 6.4_

- [x] 6. 批2 附注模板幂等修订（K3 K4 K5 K7）
  - _Requirements: 2.4, 3.6, 4.1, 4.2, 4.3_
- [x] 7. 批2 同步映射（含 K4 债券两表、K7 soe 政府补助表、K3 账龄超1年表）
  - _Requirements: 1.1, 2.1, 2.2, 3.1, 5.4_
- [x] 8. 批2 组件改造
  - _Requirements: 5.1, 5.2, 5.3_
- [x] 9. 批2 守卫
  - _Requirements: 6.1, 6.2, 6.3_
- [x] 10. 批2 验证与实测
  - _Requirements: 6.4_

- [x] 11. 批3 附注模板幂等修订（K1 37 表 / K6 11 表）
  - _Requirements: 2.4, 3.6, 4.1, 4.2, 4.3_
- [x] 12. 批3 同步映射（K1 两级表头 + 阶段表；K6 五节→多表 + 国企负债独立章节）
  - _Requirements: 1.1, 2.2, 3.1, 5.4_
- [x] 13. 批3 组件改造
  - _Requirements: 5.1, 5.2, 5.3_
- [x] 14. 批3 守卫
  - _Requirements: 6.1, 6.2, 6.3_
- [x] 15. 批3 验证与实测
  - _Requirements: 6.4_

## Notes

### 批 1（K8~K13）完成记录（2026-07-30）

**交付**：幂等脚本 `fix_note_k_pl_structure.py`（12 章节 13 表）+ 共享 helper
`kPlDisclosureShared.ts` + 6 份 map 重写 + 12 份组件改造 + 契约 `kPlNoteSubtableContract.spec.ts`
+ 后端 `test_note_k_pl_structure.py` / `test_note_k_sheet_names.py` + CI job `note-k-pl-structure`。

**修掉的实质缺陷（全部实证，非美化）**：

1. **K11/K12/K13 上市侧同步落不到章节** —— 常量写 `资产减值损失`/`营业外收入`/`营业外支出`，
   模板 `section_number` 实为 `三、资产减值损失（损`/`三、营业外收入（注：`/`三、营业外支出（注：`。
2. **K8/K9 上市侧孤儿子表** —— 常量表名 `销售费用`/`管理费用`，模板实为「（按费用性质列示）」。
3. **K10/K12/K13 列丢失** —— K10 国企第 4 列「是否为政府补助」常量未声明（组件也没有该列，已补交互点选 +
   合计后结构行「其中：政府补助」）；K12/K13 两版第 4 列「计入当期非经常性损益的金额」组件已录入却从未推送。
4. **K10 两版标签全推成空串** —— 行模型字段是 `category`，旧载荷读 `r.project`。
5. **sheet_name 半角漂移 12 处** —— 源 xlsx 是全角。
6. **K11/K13 `handleNarrativeSave` 的 `sectionIds` 全是过时字面量**（`五、73`/`五、75`/`五、营业外支出`）
   → `useNoteRefresh` 定向刷新永不命中，已改引用常量。
7. 21 处金额 `el-input-number` → `WpAmountInput`（千分符实测生效）；12 份重复 `fmtAmt` 委托平台 `fmtAmount`；
   12 处 AI prompt 补「源模板口径 + 不得虚构」约束。
8. 模板侧删占位说明行 4 处（`可无限量添加行` ×2 / `......` / `……`）+ 上市泄漏表名 `项  目` ×3 改名。

**测试**：后端 62 绿 / 前端 250 绿（含 K2 契约 + 三个跨循环守卫）。

**实测**（chrome-devtools + postgres 只读，项目 2aa00f57，国企模板）：
K10 §八、69 落库 4 列 + 结构行排在合计后 + 文本列合计 `null` + `_last_sync_sheet=附注披露信息（国企）`；
K12 §八、76 落库 4 列含 `non_recurring_amount`（改造前从未推送）。上市侧该项目模板不含
`五、68`/`三、营业外收入（注：` 章节，以契约测试与载荷断言覆盖。

**踩坑**：共享 helper 原名 `buildPlColumns` 命中 `disclosureColumnsCoverage` sweep 的
`^build[A-Z]\w*Columns$` 发现正则 → 被空入参调用产出空列头（Property 6 假阳性）+ 要求登记 P1_ROUTE。
已按平台约定改名 `plColumnsFor`；对外只暴露零参 `buildK{n}{Listed,Soe}Columns`。

### 批 2（K3/K4/K5/K7）进度记录（2026-07-30）

**已完成 Task 6 / 7 / 9**：

- 幂等脚本 `fix_note_k_liability_structure.py`（8 章节 **22** 表：K3 7+6、K4 3+1、K5 1+1、K7 1+2），
  `--check` 绿。修掉：泄漏/假表名 3 处（`项  目` → 「其中，账龄超过1年的重要其他应付款」、
  `其他应付款（表6）` → 「账龄超过1年的重要其他应付款项」、`债券名称` → 「短期应付债券（续）」）、
  占位说明行 4 处（K3 上市 `可无限量添加行` ×3、K4 国企 `……`）、22 表补 `columns`（显式 `flat`）+ `guidance`。
- **模板列键对齐既有 map**（不是反过来）：K4 债券两表用 `bond_name/face_value/...`、
  K5 上市第 4 列 `reason`、K7 用 `begin_amount/increase/decrease/end_amount/reason` ——
  K4/K5/K7 的 map 是 `disclosure-columns-coverage-rollout` 批 2 已验证过的真源，改它们会连带打断其 per-cycle spec。
- **K4 `债券名称` 改名必须同步 `K4_SUBTABLE.bondCont`**，否则模板一改 K4 立刻变孤儿表；
  已同步并加 `K4_LEGACY_OBSOLETE_TABLES` → 载荷 `_removed_table_keys`。
- **K3 映射重写**（原来只推主表 1 张，其余 6/5 张附注侧永空）：7/6 张子表常量 + 固定行常量 +
  `buildK3ListedColumns`/`buildK3SoeColumns` + 主表三行由分表合计派生（对齐源模板 `=B17`/`=C17`）+
  条件表机制。K3 sheet 名保留**半角括号**（源 xlsx 即如此）。
- 守卫：`kLiabilityNoteSubtableContract.spec.ts`（共享 helper × 4 循环 + 模板结构 + K3 载荷）
  + 后端 `test_note_k_liability_structure.py`（含反向自检）+ P1_ROUTE 登记 K3
  + CI job 合并为 `note-k-cycle-structure`（批 1 + 批 2 一起 `--check` + pytest）。
- 测试：后端 117 绿（K2 + 批1 + 批2）/ 前端 399 绿；唯一失败 `buildN2ListedColumns`
  `buildN2SoeColumns` 未登记 P1_ROUTE，属并发会话的 `n-cycle-tax-disclosure-alignment`，非 K 系。

**Task 8 已完成 K3 部分（2026-07-30 续）**：

- **K3 两版补齐附注要求的录入区块**，段序改为与附注表序一致：
  上市 9 段（应付利息 / 重要的逾期未付利息 / 应付股利 / 重要的超过1年未支付的应付股利 /
  其他应付款（按款项性质列示）/ 其中，账龄超过1年的重要其他应付款 / 按账龄分析（底稿）/
  前五名（底稿）/ 其他披露事项）；国企 8 段（无「超过1年未支付的应付股利」，附注 §八、42 无该表）。
  `section.id` 保持不变 → 既有 `K3-disc-{listed,soe}-{id}` 持久化数据不丢。
- 新增 `DisclosureSection` 的 `hidePriorColumn` / `labelHeader` / `amountHeader` / `remarkHeader` /
  `editableLabel` / `syncedToNote` 六个字段：条件表（逾期利息 / 超1年未付股利 / 账龄超1年）
  隐藏期初列并按附注模版改列头（如「债权单位 / 逾期金额 / 逾期原因」），行名可填。
- **底稿审计分析段用 `syncedToNote: false` 显式标注并在标题里写明「不进附注」** ——
  按账龄分析、前五名、期末重要明细在附注 §五、42 / §八、42 无对应表，推了会造孤儿表。
- 「账龄超过1年」段原预置 `项目1..项目5` 占位名 → 改空行骨架，否则未填行也会被推成占位披露行。
- K3 两版金额控件全部换 `WpAmountInput`（含账龄列，`el-input-number` 归零），
  `fmtAmt` 委托平台 `fmtAmount`。
- **浏览器实测通过**（项目 2aa00f57 / K3 底稿 354e0f37，国企侧）：
  §八、42 落库 **6 张表**（`应付利息` / `应付股利` / `其他应付款` / `按款项性质列示` /
  `重要的已逾期未支付的利息情况` / `账龄超过1年的重要其他应付款项`）—— 改造前只有 1 张；
  主表三行由分表合计派生（应付利息 333,333.50 / 其他应付款项 120,000 / 合计 453,333.50）；
  `_last_sync_sheet=附注披露信息(国企)`（半角，与源 xlsx 一致）；千分符生效。

**Task 8 完成 K4/K5/K7 部分 + Task 10 实测（2026-07-31）**：

- **K7 国企「其中：递延收益-政府补助情况」10 列表接线完成**（此前底稿完全没有录入位置，
  模板补了 `columns`/`guidance` 也只有 seed 路径能看到，同步路径永远推不出这张表）：
  - `K7TabDisclosureSoe.vue` 新增 10 列录入区块（动态增删行 + 全量 `WpAmountInput` +
    「本期计入损益的列报项目」`el-select`（其他收益 / 营业外收入 / 冲减相关成本费用 /
    冲减资产折旧·摊销，`allow-create` 允许例外）+「与资产相关/与收益相关」点选 +
    源模板红字提示块 + 勾稽 bar）。
  - 期末余额是**派生列不持久化**（F51-7a~7d：期初 + 新增 − 计入损益 − 返还 − 其他变动），
    纯函数 `grantDetailEndAmount()` 落在 map 里，组件与载荷同源。
  - **条件表语义**：源模板红字「仅披露金额重大的政府补助项目」→ 有行才推；
    无行时不推空表**且进 `_removed_table_keys`**。⚠️ 与 K3「应付利息/应付股利」不同 ——
    那两张压根没有录入区块、不属本载荷所有，故只跳过不 removed；本表既然有录入区块，
    用户删空后必须清掉上次推送，否则附注永久残留过时明细（实测已复现并修好）。
  - `K7_SUBTABLE` 拆成 `K7_LISTED_SUBTABLE`（仅主表）/ `K7_SOE_SUBTABLE`（主表 + 明细表）——
    该表**只在国企版**，两变体共用一份清单会让上市侧契约 P1 因模板无该表而红。
- **K5 两版 AI 是空转 stub**（只 `emit('save', ...ai-trigger)` 写 marker、从不调 AI 端点，
  按钮可见可点但零网络请求）→ 实装 `/ai/generate-text` + 预览确认 + prompt 写明源模板/CAS13 口径。
  **K7 两版同款空转**（`handleAiGenerate` + `handleAiNarrative` 两个都是），一并实装。
- **K3 两版 `context` 传的是模板字符串** → 后端 `AiGenerateTextRequest.context` 是
  `dict[str, str]`，必然 422、被 `catch` 静默吞成失败 → 改成对象。
- K4 两版 AI prompt 补「源模板/附注模版口径 + 不得虚构」约束（原本 18~22 字笼统 prompt）。
- K3/K4 四个 Tab 的 AI 按钮补 `:loading` + `:disabled="isReadonly"`（原本可无限重复点）。
- 新守卫 `composables/__tests__/kDisclosureAiWiring.spec.ts`（33 断言，覆盖 8 个 Tab）：
  真调端点 / 无 marker stub 残留 / `context` 非字符串 / 每条 prompt 都有「不得虚构」/
  按钮有 loading 与只读禁用；含 `stripComments` 自检（守卫注释里就写着反例，不剥离会误报）。

**Task 10 浏览器实测（chrome-devtools + postgres 只读，项目 2aa00f57 国企模板）**：

- K7 底稿 `5a08dd14`「附注披露信息（国有企业）」Tab 正常挂载（`.k7-tab-disclosure-soe`），
  四张卡片含新增的「其中：递延收益-政府补助情况」。
- 录入 1 行（期初 1,000,000 / 新增 500,000 / 计入损益 200,000 / 返还 100,000 / 其他变动 50,000）
  → 期末派生 **1,150,000.00**（千分符生效）；勾稽 bar 与主表比对并给出差异。
- **不点同步按钮**，自动同步在 5s 内自发触发：§八、56 `last_sync_at` 由 NULL 前移，
  `sub_table_data` 落 **2 张表**（改造前 0 张），`_last_sync_sheet=附注披露信息（国有企业）`（全角）；
  明细表 10 列键/label 与模板逐位一致、标签列 `flat: true`、合计行 `is_total` 正确。
- 删掉该行 → 子表 2 张回落 **1 张**，`last_sync_at` 二次前移（条件表 removed 生效）。
- K4 两版 / K5 国企 / K7 上市 Tab 全部挂载，`el-input-number` 计数 **0**；
  K4 国企 18 个 `WpAmountInput` 实录 `1234567.5` → 显示 `1,234,567.50`（测试值已复原）。
  K5 国企金额列本就是审定表自动取数的只读展示（源模板口径），故无金额输入框，非遗漏。

**批 2 剩余（不阻塞收口）**：

1. K3/K7 上市侧活体未测 —— 该项目模板为国企版，`五、42`/`五、51` 不在目录树内；
   且在国企项目上编辑上市 Tab 会因 `applicable_standards` 前端全链缺失而写错章节
   （平台级缺陷，须单独立 spec），故**刻意不在此项目触发上市侧同步**。
   已由契约测试 + 载荷断言覆盖。
2. K3 勾稽面板未做（主表↔分表合计已在载荷层保证一致）。

### 批 3（K1 / K6）进度记录（2026-07-31）

**Task 11 / 12 / 14 完成**（模板 + 映射 + 守卫），Task 13 组件改造与 Task 15 实测待做。

**普查实证（openpyxl 读源 xlsx + 模板 JSON 双向比对）**：K6 的章节结构**两版不对称** ——
上市 `五、11` 一节合并（资产 + 负债 + 减值准备 + 非流动资产 + 处置组），
国企拆成 `八、12`（资产 4 表）+ `八、43`（负债 1 表）；共 5 个章节 48 张表。

**幂等脚本 `fix_note_k_complex_structure.py`**（5 章节 48 表，132 处变更，`--check` 绿）：

K1（§五、8 十八表 / §八、9 十九表）
1. **37 张表 `columns` 全缺** → 后端 `_extract_column_groups` 返回 `None`、退化到
   `_infer_groups_from_headers` 前缀推断，对「期末账面余额/期末坏账准备/…」这类带期别
   前缀的表头会凭空造父表头；契约 P3「group / flat 必须表态」也不满足。
2. **两级表头被压扁成带前缀的单级**（源 xlsx 有跨列合并：上市 `B22:D22`/`E22:G22`；
   国企 `B19:F19`+`B20:C20`+`D20:E20`、`B46:D46`/`E46:G46`）→ 改为显式 `group` +
   **叶子列名**，`key` 保持既有中文数据键不变（不动同步载荷的行对象键）。
   国企「按计提方法分类」源模板是**三级表头**，按 D1/D6 范式**把顶层期别提到表名**
   （主表 + 续表两张），剩两级用 group，`账面价值` 是 rowspan=2 的独立列 → 混合分组。
3. **4 处 `header_label` 假数据行**（压扁的第二行表头残留，会渲染成一行空披露数据）。
4. **占位说明行**（上市 `可无限量添加行` ×2、国企 `……` ×4）→ 空白录入行骨架。
5. **国企裸续表名 `续：`** → 「按坏账准备计提方法分类披露其他应收款项（续：期初余额）」；
   同步侧 `K1_SOE_SUBTABLE.methodPrior` 一并改（不改必成孤儿表）。
6. **三阶段快照 6 表缺第 6 列「理由」**（源 xlsx F32/F41/F51/F63/F72/F82）——
   底稿与同步映射早已有该列，只有附注模板漏了。ECL 率列**表头按阶段不同**
   （第一阶段 = 未来 12 个月内 / 第二·三阶段 = 整个存续期），`key` 统一 `预期信用损失率`。
7. **6 条裸表名 `text_sections`** 加 `#### ` 前缀（否则被当披露正文渲染）。

K6（§五、11 / §八、12 / §八、43）
8. **上市 6 张表里 5 张是垃圾名**：`期末，持有待售资产的情况：`（A44 段落文本泄漏）、
   `子公司A` / `分公司B`（示例处置组名）、`项  目`（表头首格泄漏，且内容与处置组表重复 → 删）；
   且 `tables[1]` **名（持有待售资产减值准备）与内容（持有待售负债行）整体错位一位**。
9. **主表两级表头 6 列被压扁成 3 列** —— 而同步映射 `buildK6ListedColumns()` 早已是 7 列
   两级 → 模板与载荷列数不符，校验预设 F11-4（账面余额 − 减值准备 = 账面价值）无从落地。
10. **减值准备表缺「本期减少」二级拆分**（源 `D32:E32`/`D22:E22` 合并，下辖
    `本期转回`/`本期出售`）→ 模板压成单列。
11. **11 张表 `guidance` 全缺** + 占位行 + `header_label` 假行 + 3 条裸表名段落。

**映射（Task 12）**：
- `K1_DISCLOSURE_SHEET_NAME.listed` 由全角全角改为**前半角后全角** `附注披露信息(上市公司）`
  （源 xlsx tab 名实测）—— 原先 `?sheet=` 精确匹配落空。`note_workpaper_sync_registry.json`
  已重跑 `gen_note_wp_sync_registry.py --write` 同步。
- `k1DisclosureSyncPayload.ts` 27 张表列定义重写：新增 `amtG`/`txtG`（key≠label + group）
  与 `flat()` 助手，单级表全部显式 `flat`，两级表用 group + 叶子列名。
- `k6NoteSectionMap.ts` 重写：`K6_LISTED_SUBTABLE`(5) / `K6_SOE_SUBTABLE`(4) /
  `K6_SOE_LIABILITY_SUBTABLE`(1) + 4 个列构造器 + `K6DisclosureSnapshot` 分区块载荷
  （条件区块有行才推，无行进 `_removed_table_keys`）+ `K6_LEGACY_OBSOLETE_TABLES` 清旧名
  + **`buildK6SoeLiabilityPayload()` 单独 POST §八、43**（`sync_from_workpaper` 定位键
  是 `(project_id, year, note_section)`，一个 payload 只能写一节）+ 旧签名兼容。

**守卫（Task 14）**：
- 后端 `test_note_k_complex_structure.py` 40 项（通用结构参数化 × 5 章节 + K1/K6 专项 +
  **`sheet_name` 直接 openpyxl 比对源 xlsx tab 名** + 反向自检 + 抽取器自检）。
- 前端：`k6NoteSectionMap.spec.ts` 由单表契约扩到 26 项多表契约；
  `k1NoteSubtableContract.spec.ts` 加 5 项（续表正名 / 三阶段理由列 / columns↔headers 同形 /
  group·flat 表态）；`k1DisclosureListed.spec.ts`、`k1DisclosureSoe.spec.ts` 两级表头断言更新；
  `disclosureColumnsCoverage` P1_ROUTE 登记 `buildK6SoeLiabilityColumns`。
- **`_disclosureSubtableContract.helper.spec.ts` 的 K1 `columnsPending` 逃逸阀已清空**
  （27 张表原本全部挂在豁免名单里，现在跑 P1~P6 全量真断言）。
- CI job `note-k-cycle-structure` 加挂 `fix_note_k_complex_structure.py --check` +
  后端测试 + 前端 `k6NoteSectionMap` / `k1NoteSubtableContract` 契约。

**验证**：后端 157 绿（K2 + 批1 + 批2 + 批3）；前端 K1/K6 相关 112 绿 +
`disclosureColumnsCoverage` 15 绿 + `disclosureSheetNameRegistry` 6 绿。

**Task 13（组件）完成（2026-07-31）**：

改造前两个 K6 披露 Tab **只喂主表** —— 附注要求的另外 3~4 张表在底稿里完全没有录入位置，
模板补了 `columns`/`guidance` 也只有 seed 路径能看到，同步路径永远推不出这些表。

- 新建 `composables/useK6NoteBlocks.ts`（两变体共用）：4 个区块（减值准备变动 / 持有待售
  非流动资产 / 处置组 / 持有待售负债）的增删改 + 反序列化补齐（旧载荷缺列不让 `undefined`
  进公式变 NaN）+ 派生列读时推导（期末 = 期初 + 增加 − 转回 − 出售，纯函数在 map 里，
  组件与载荷同源）+ `wasTouched()`。item_id = `K6-disclosure-{variant}-{block}-rows`。
- 新建展示组件 `K6NoteBlockTables.vue` + 复用块 `K6FairValueBlock.vue`（公允价值 5 列表
  三处复用：非流动资产 / 处置组 / 国企负债）。含「计量校验」列（源模板红字
  `期末账面价值 ≤ 期末公允价值 − 预计处置费用`，底稿侧提示，**不进附注**）。
- 变体差异按源 xlsx 分开取值，禁抽共享常量：「预计出售费用」(上市) vs「预计处置费用」(国企)；
  减值准备表首列「上年年末数」vs「期初数」；持有待售负债上市 2 列余额口径并入 §五、11、
  国企 5 列公允价值口径走 §八、43。
- 国企 Tab **发两次 POST**（§八、12 + §八、43），上市 Tab 只发一次。
- 两个 Tab 的 CAS42 金额输入由 `el-input-number` 换 `WpAmountInput`，`fmtAmt` 委托
  平台 `fmtAmount`（两处原本自造 `toLocaleString('zh-CN')`）。
- 原「决策 B1 不推上市负债」的成因（模板 `tables[1]` 的 name↔rows 错位）已在 Task 11
  正名 → 上市负债现在正常推送。
- 守卫 `k6NoteBlocksWiring.spec.ts`（读组件源码 + 跑 composable，含 `stripComments` 自检）。

**Task 15（实测）完成（chrome-devtools + postgres 只读，项目 2aa00f57 / K6 底稿 5f9b3c99）**：

- 国企 Tab 正常挂载，4 个新区块齐备，`el-input-number` 计数 **0**。
- 减值准备表**两级表头正确渲染**（「本期减少」跨列在「本期转回 / 本期出售」之上），
  录 1,000,000 / 500,000 / 200,000 / 100,000 → 期末派生 **1,200,000.00**（千分符生效）。
- 非流动资产表「计量校验」列在 900,000 ≤ 1,000,000 − 20,000 时显示「合规」。
- **不点同步按钮**，自动同步在 5s 内自发触发：§八、12 子表 **0 → 4 张**
  （持有待售资产 / 减值准备 / 非流动资产 / 处置组）、§八、43 **0 → 1 张**，
  `_last_sync_sheet=附注披露信息(国企）`（前半角后全角，与源 xlsx 一致）；
  主表 `_sub_table_columns` 两级分组 = 期末数(1,3) / 期初数(4,3)，
  减值准备表 `group=本期减少` 落在 `reverse`/`disposal` 两列，
  国企负债列头是「预计处置费用」（非上市的「预计出售费用」）。
- 删空区块 → §八、12 由 4 张回落 1 张、§八、43 清空，`last_sync_at` 均二次前移。

**🔴 实测挖出的实质缺陷（已修 + 守卫）**：清空持有待售负债后 §八、43 **永久残留上次
推送的过时明细**（子表仍在、`last_sync_at` 不前移）—— 因为 `buildK6SoeLiabilityPayload`
在无行时返回 `null`、整节不发请求。先尝试「只在该区块被改动过时才清理」（`wasTouched`
启发式），但宿主会重建 `allResponses` 并重挂 Tab，实测出现「同一次会话里 add 能识别、
delete 识别不到」的不确定行为（改成模块级标记后仍不稳定）→ **改为无条件发送清理载荷**
（`clearWhenEmpty` 默认 true）。代价：从未有持有待售负债的项目 §八、43 显示「无数据」
而非模板空白骨架 —— 该节只承载 K6 这一张表，如实显示可接受，重新生成附注即恢复骨架。

**批 3 剩余（不阻塞收口）**：K1 两个披露 Tab 的两级表头未肉眼复验（列头已由契约 +
后端守卫双向锁死）；K1/K6 上市侧无活体（项目为国企模板，且在国企项目上编辑上市 Tab
会因 `applicable_standards` 前端全链缺失写错章节 → 刻意不触发）。

### 普查实证结论（2026-07-30）

见 `requirements.md` §Introduction 表格。三个 P0：K11~K13 上市章节号错、K8/K9 上市孤儿子表、K10/K12/K13 第 4 列丢失。

### 不做的事（含理由）

- **不改 listed 模板 `三、` 章的 `section_number`**：整章 70+ 条都被 md 重建截断为 10 字符，是既有真源形态；改动波及全章与并发 spec。改常量对齐模板。
- **K8/K9 源 xlsx 的「合并报表」块不推附注**：附注 listed 模板该章只有 1 张表，推两张会造孤儿表；合并口径归合并附注模板。
- **K12 国企「与企业日常活动无关的政府补助明细」不推附注**：模板 §八、76 只有 1 张表，无对应落点；保留为底稿侧审计明细。
