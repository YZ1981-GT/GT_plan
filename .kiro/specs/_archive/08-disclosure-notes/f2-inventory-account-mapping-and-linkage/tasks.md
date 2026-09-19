# Implementation Plan: F2 存货科目映射与底稿间联动

## Overview

5 波。Wave 1 先建名称归类单一真源（后续全部依赖它），Wave 2 接后端两条取数路径，
Wave 3 下发项目科目表并收前端兜底，Wave 4 重写公式预设 + 底稿间联动，Wave 5 验证。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "名称归类单一真源", "tasks": ["1.1", "1.2"], "parallel": false },
    { "wave": 2, "name": "后端取数接线", "tasks": ["2.1", "2.2", "2.3"], "parallel": false, "depends_on": [1] },
    { "wave": 3, "name": "项目科目表下发与前端兜底", "tasks": ["3.1", "3.2", "3.3"], "parallel": false, "depends_on": [2] },
    { "wave": 4, "name": "公式预设与底稿间联动", "tasks": ["4.1", "4.2"], "parallel": false, "depends_on": [1] },
    { "wave": 5, "name": "披露/附注核查与实测", "tasks": ["5.1", "5.2", "5.3"], "parallel": false, "depends_on": [2, 3, 4] }
  ]
}
```

## Tasks

## Wave 1 — 名称归类单一真源

- [x] 1.1 新建 `backend/app/services/f2_extraction/category_rules.py`
  - `F2_CATEGORY_RULES`（顺序即优先级）/ `classify_f2_category` / `classify_f2_leaf`
    / `is_f2_impairment_category`
  - 零依赖纯函数，docstring 写明两个标准变体的冲突实证
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [x] 1.2 守卫 `backend/tests/test_f2_category_rules.py`
  - 两变体 `(code, name)` 样本参数化：同名必同 rowKey、与编码无关
  - Property 1~5（含 PBT：桶之和 == 全集）
  - 反向自检：把「跌价准备」规则挪到末尾必失败
  - _Requirements: 6.1_

## Wave 2 — 后端取数接线

- [x] 2.1 `_f2_inventory_main.py` 改造
  - 删 `_row_depth`，改用 `four_table.select_leaves`
  - `_build_adjudication_prefill` 按名称归类（叶子名 → 父级名回退）
  - `F2_CATEGORIES.account` 加「兜底/展示用」注释
  - _Requirements: 1.4, 2.1, 2.2, 2.3_

- [x] 2.2 `f2_extraction/extract.py` 委托同一归类
  - `build_default_bindings` 带 `row_key`；`expression` 改展示字符串
  - 灰度开/关两条路径行为一致
  - _Requirements: 1.1, 1.4_

- [x] 2.3 render 输出 `tb_source_codes`（含 `classified` 明细）
  - _Requirements: 6.4_

## Wave 3 — 项目科目表下发与前端兜底

- [x] 3.1 render 输出 `project_context.inventory_accounts`
  - 取自 `account_chart` 14xx（fail-open `[]`）
  - _Requirements: 3.1_
  - 已在 Wave 2 的 `_f2_inventory_main.build_inventory_accounts` 落地（`render()` 输出
    `project_context.inventory_accounts` + `tb_source_codes.classified`）。

- [x] 3.2 `f2AccountModel.ts` 加 `resolveF2InventoryAccounts` / `resolveF2AccountToRowKey`
  - 静态映射标注为兜底
  - _Requirements: 3.2, 3.3_
  - 新增 `resolveF2InventoryAccounts`（动态清单优先，空/缺失回退 `F2_INVENTORY_ACCOUNTS`）、
    `resolveF2AccountToRowKey`（动态 `row_key` 优先，回退 `F2_ACCOUNT_TO_ROW_KEY`）、
    `resolveF2RowKeyToAccounts`（rowKey→多科目码清单，供溯源面板“周转材料=周转材料+
    包装物+低值易耗品”这类多对一展示）。

- [x] 3.3 消费点接线（`F2TabAdjudication` AJE 科目下拉 / `F2FourTableSourcePanel`）
  - _Requirements: 3.2_
  - `useF2Adjustment` 新增 `inventoryAccounts` 入参 → 内部 `accountOptions` 改为
    `computed(() => resolveF2InventoryAccounts(inventoryAccounts?.value))`（AJE 科目
    编码/名称下拉 + 双向联动查找均改用动态清单）。
  - `GtF2InventoryMain.vue` 新增 `inventoryAccounts` computed（读
    `htmlData.project_context.inventory_accounts` → 回退 `formData.projectContext`），
    透传给 `F2TabAdjustment`（新 prop `inventoryAccounts`）与
    `F2FourTableSourcePanel`（新 prop `inventoryAccounts`）。
  - `F2FourTableSourcePanel.vue` 的「来源科目」列改用
    `resolveF2RowKeyToAccounts` 按 rowKey 展示项目实际子科目清单（多个用 `/` 分隔），
    缺失时回退单一编码兜底 `F2_ROW_KEY_ACCOUNT`。
  - 新增 6 条前端测试（`f2AccountModel.spec.ts`）：变体 B 动态清单覆盖静态假设、
    空清单回退、多对一分组、undefined 安全。前端相关测试 16/16 通过。

## Wave 4 — 公式预设与底稿间联动

- [x] 4.1 重写 `prefill_formula_mapping.json` 的 `workpaper:F2`
  - 删「编码=分类」类；跌价保留 `1416`/`1461` 两条并注明二选一
  - 新增 `WP()` 联动：F2-1←F2-2；F2-2←F2-3~F2-13；两个披露 sheet←F2-1/F2-2；
    F2-47←F2-1；F2-11/F2-10→披露 (5)(6)
  - `cell_ref` 页内唯一
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - 新建幂等脚本 `backend/scripts/fix/fix_f2_prefill_presets.py`（`--dry-run`/
    `--check`，同 `fix_f1_prefill_presets.py` 范式）：
    - `审定表F2-1` 删 14 条「编码=分类」写死映射（原材料/在产品/库存商品/
      工程物资/委托加工物资/存货跌价准备各 2 条 opening+closing），追加 7 条
      （区间口径 `TB_SUM('1401~1499',…)` + 跌价 `1416`/`1461` 各期初期末 4 条
      + `AJE调整净额`=`WP('F2','调整分录汇总F2-14','借方合计')-WP(...,'贷方合计')`
      + `明细汇总期末合计`=`WP('F2','明细汇总表F2-2','期末余额合计')`）。
    - `明细汇总表F2-2` 删 17 条（含改造前按仓库/存货分类维度的 4 条 `AUX()`
      写死示例），追加 26 条：F2-3~13 每张明细表 2 条（期初/期末，
      `WP('F2','<明细表 sheet 名>','期初/期末余额合计')`）+ 跌价二选一 4 条；
      本期借方/贷方发生区间从漏了六个分类的 `1401~1408` 补全到 `1401~1499`。
    - `分析程序F2-3` 是改造前**贴错标签**的 sheet 名（源 xlsx 无此 tab）→
      改为源 xlsx 真实 tab `存货总体分析表F2-18`，区间口径同样补全到
      `1401~1499`，`上年审定数` 因 `page_key` 忽略 sheet 与 F2-1 撞键 → 改名
      `上年审定数（分析程序）`。
    - 新增两个披露 sheet 块（`附注披露信息（上市公司）`/`（国企）`，改造前
      公式管理页完全空白），各 2 条：分类披露期末合计←F2-2、跌价准备变动
      期末←F2-1（并在 description 注明跌价二选一）。
    - `跌价准备测试表F2-47` 追加 1 条引用 F2-1 审定数（Req 4.3）。
    - 顺带修正 3 处描述文字错误：F2-38~40（计价方法测试系列）把 `1403`
      （两版标准科目表一致的「原材料」）误标成「库存商品」。
  - `workpaper:F2` 从 18 块/71 条 → 20 块/85 条。

- [x] 4.2 守卫 `backend/tests/test_f2_formula_presets.py`
  - Property 6 + 禁写死编码分类 + `validate_formula` + 防循环（明细表禁 `WP()`）
  - _Requirements: 4.5, 6.3_
  - 36 例：`cell_ref` 页内唯一 + 运行态条目数与 JSON 声明数一致（防静默去重）
    / 禁写死编码分类（正则扫 `1401~1411`，跌价 `1416`/`1461` 显式豁免）+ 反向
    自检该正则确实能命中改造前写法 / 跌价二选一齐备且 description 标注 /
    区间口径保留 / 分析块已改真实 sheet 名 / F2-1↔F2-14/F2-2、F2-2↔F2-3~13
    （11 张明细表参数化）、两个披露 sheet、F2-47↔F2-1 联动齐备 / F2-2 不反
    引 F2-1（防成环）+ F2-3~13 各明细表本身无 `WP()` / 全部公式
    `validate_formula` 语法合法（`ADJ`/`TB_SUM`/`LEDGER`/`LEDGER_DETAIL` 四个
    prefill 专属词汇豁免，含反向自检「若某天被注册则豁免应移除」）。
  - **F2 相关测试 168 passed**（`test_f2_formula_presets.py` +
    `test_f2_category_rules.py` + `f2_extraction/` + `test_f2_render_prefill.py`）。

## Wave 5 — 披露/附注核查与实测

- [x] 5.1 守卫 `backend/tests/test_f2_source_template_facts.py`
  - openpyxl 直读两个披露 sheet：(1) 分类表两级 7 列 / (2) 变动表 / (3) 二选一 /
    (5)(6) 房企表；含反向自检
  - _Requirements: 5.1_
  - **已由姊妹 spec `f2-inventory-disclosure-template-alignment`（Sprint 1~8）
    完整覆盖，本 spec 不重复建守卫**：`tests/services/test_note_inventory_structure.py`
    （56 例，openpyxl 直读源 xlsx + `fix_note_inventory_structure.py --check`）+
    前端 `composables/__tests__/f2NoteSubtableContract.spec.ts`（37 例）。
    本次复核 openpyxl 直读两个披露 sheet 结构确认：上市 (1) 分类表 9 行
    + 房企扩展 2 行（`开发成本`/`开发产品`，源 R20 红字授权）两级 7 列表头
    （`期末数`/`上年年末数` 各 3 子列）；(2) 变动表两级 7 列（期初/本期增加
    {计提,其他}/本期减少{转回或转销,其他}/期末）；(3) 按组合/按库龄组合
    二选一（各含期末+上年年末两张续表）；国企 (1) 分类表用同款行名
    （原材料/自制半成品及在产品/…/库存商品（产成品）/周转材料（包装物、
    低值易耗品等）），逐字确认**行标签 = 科目分类名称**（非编码）—— 与
    Wave 1 的按名称归类设计完全对应，取数结果可直接铺进披露行。

- [x] 5.2 三方一致性核查（底稿列常量 ↔ 附注模板 `columns` ↔ 源 xlsx）
  - 不一致则以源 xlsx 为准修 `fix_note_inventory_structure.py` + 契约测试
  - _Requirements: 5.3_
  - 复核结论：三方一致，无需再修改。`f2NoteSectionMap.ts` 的
    `F2_LISTED_SUBTABLE`/`F2_SOE_SUBTABLE` 表名与 `note_template_{listed,soe}.json`
    的 `tables[].name`、源 xlsx 小节标题逐字对应；列头（账面余额/跌价准备/
    账面价值、期初余额/本期增加/本期减少/期末余额）与本 spec 新增的
    `resolveF2InventoryAccounts`/`classify_f2_leaf` 输出的 rowKey→label 映射
    （`raw-materials`→原材料 等）完全对齐 `F2_CATEGORIES` 既有 label，
    故取数结果可不经转换直接按 rowKey 对应的中文名铺入披露行。

- [x] 5.3 真实 DB 直跑 render（变体 A + 变体 B 各一项目）+ 全量测试
  - 断言桶之和 == 14xx 叶子合计；库存商品桶在两版下都取到库存商品
  - _Requirements: 6.4_
  - 直接调用 `_f2_inventory_main.build_inventory_accounts` /
    `_build_adjudication_prefill` 对真实数据库两个变体项目直跑（非 HTTP，
    避免依赖本机服务重启）：
    - **变体 A**（`0ec33ac9`）：29 个存货科目全部正确归类（`1405`→自制半成品/
      `1406`→库存商品，与变体 B 相反）；3 个非零桶
      `finished-goods`(closing 159,109,974.32) / `goods-in-transit`(25,384,542.39) /
      `impairment-provision`(24,912.02，已 abs) 之和 **184,519,428.73**
      **逐分不差**等于 14xx 叶子期末合计（原始符号）184,519,428.73。
    - **变体 B**（`c8621493`）：`1405`→库存商品/`1406`→发出商品（与变体 A
      相反，编码语义冲突在真实数据上复现）；1 个非零桶 `finished-goods`
      closing **1,440,046.64** 等于叶子合计 1,440,046.64。
    - 两个项目 `1406.01/.02/.03`（客户自定义子科目）均正确归入
      `finished-goods`（叶子名带「库存商品」，父级回退未触发也能命中）。
  - **F2 相关测试全量 168 passed**（`test_f2_formula_presets.py` 36 +
    `test_f2_category_rules.py` 50 + `f2_extraction/` 68 + `test_f2_render_prefill.py` 14）
    + 前端 `f2AccountModel.spec.ts` 16 + `useF2Adjustment.spec.ts` 6。

## Wave 1~5 收尾状态

**全部 13 个任务完成**。F2 存货循环的四表取数科目映射问题（两版标准科目表
编码语义冲突）已从根源修复：后端按名称归类（`category_rules.py`）+ 前端
消费点动态科目清单（`f2AccountModel.ts` 的 `resolveF2*` 系列）+ 公式管理页
预设重写（删写死编码，改区间/联动口径）+ 披露表三方结构核查确认一致。

后续如需扩展（不在本 spec 范围）：
- F2-3~13 各明细表若要接自动同步/自动取数（当前手工录入 + 底稿间 `WP()`
  公式管理提示），可另立 spec。
- 灰度开关 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 默认值是否翻转，属平台级决策
  （同 D-cycle/K1/K2 等循环，已在 memory.md 记录待用户裁决）。

## Notes

### 本 spec 明确不做（防复盘重复提议）

- **上市 (1) 分类表不回退到源模板的 9 行**：源 xlsx R20 红字明确
  「（注：根据企业具体情况分类，房地产开发企业应增加"开发成本""开发产品"等种类）」
  → 现 11 行（Sprint 8 加的开发成本/开发产品）是**源模板授权的扩展**，保留。
- **不改 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 灰度默认值**：翻默认属平台级决策；
  本 spec 让开/关两条路径都走同一归类函数，故先修正确性、灰度另议。
- **不动附注 §五、9 / §八、10 的表结构**：`f2-inventory-disclosure-template-alignment`
  已按源模板对齐（Sprint 1~8），本 spec 只在 5.2 发现三方不一致时才动。
- **不把 `F2_ROW_KEY_ACCOUNT` 删掉**：AJE 写回 TB 与历史持久化数据仍按编码键，
  删除会打断存量；改为「兜底 + 运行时优先项目科目表」。

### 关键实证（本 spec 的裁决依据，勿凭直觉改）

`account_chart` `source='standard'` 两变体冲突（9 个真实项目，2026-08-01 只读实测）：

| 码 | 变体 A（0ec33ac9 / 12c15a96 / a7fc75e5） | 变体 B（4f6dbc36 / b39809ed / c8621493 / df5b8403 / f064f5e4） |
|---|---|---|
| 1405 | 自制半成品 | 库存商品 |
| 1406 | 库存商品 | 发出商品 |
| 1407 | 发出商品 | 商品进销差价 |
| 1408 | 商品进销差价 | 委托加工物资 |
| 1409 | 周转材料 | —— |
| 1411 | 委托加工物资 | 周转材料 |
| 1416 | 存货跌价准备（5 项目） | —— |
| 1451 | 包装物 | 损余物资 |
| 1461 | —— | 存货跌价准备（6 项目） |

`tb_balance` 全库 14xx 期末合计（判「现映射取到 0」的依据）：
`1401` 0.00 / `1403` 0.00 / `1406` 2,242,931,345.04 / `1407` 197,680,027.88 /
`1409` 406,464.76 / `1416` −4,149,232.42 / `1452` 10,279.66。

### 实测结论（Wave 1~2，真实 DB 直跑 render）

**核心证明：同名 → 同 rowKey，与编码无关。** 两个变体各取一个真实项目直跑
`build_inventory_accounts` + `_build_adjudication_prefill`：

| 科目码 | 变体 A 项目 `0ec33ac9` | 变体 B 项目 `c8621493` |
|---|---|---|
| `1405` | 自制半成品 → `semi-finished` | **库存商品 → `finished-goods`** |
| `1406` | **库存商品 → `finished-goods`** | 发出商品 → `goods-in-transit` |
| `1407` | 发出商品 → `goods-in-transit` | 商品进销差价 → `price-difference` |
| `1408` | 商品进销差价 → `price-difference` | 商品进销差价 → `price-difference` |
| `1411` | 委托加工物资 → `outsourced-processing` | 周转材料 → `revolving-materials` |
| `1416`(+.01~.04) | 存货跌价准备 → `impairment-provision` | 同 |
| `1461` | 存货跌价准备 → `impairment-provision` | 同 |
| `1471` / `1472` | 合同取得/履约成本 → `contract-performance` | 同 |

→ 改造前写死 `1406 → finished-goods` 在变体 B 项目上会把**发出商品**的钱算进库存商品行；
写死 `1403 → revolving-materials`（周转材料）在两版下都错（1403 两版都是原材料）。

**客户自定义子科目也正确归类**（叶子名自带类别词时不需要父级回退）：
`1406.03 库存商品_外购商品（零售）` → `finished-goods`；
`1416.04 存货跌价准备_库存商品` → `impairment-provision`（备抵优先级生效，
若被「库存商品」吃掉会让 −324.9 万备抵反向抵减库存商品）；
`1404.03 材料成本差异_周转材料差异` → `revolving-materials`（叶子名胜过父级名）。

**Property 1（不重不漏）在真实数据上成立**：

| 项目 | 桶合计（备抵已 abs） | 14xx 叶子期末之和（原符号） | 叶子数 |
|---|---|---|---|
| `0ec33ac9` | 184,519,428.73 | 184,519,428.73 | 20 |
| `c8621493` | 1,440,046.64 | 1,440,046.64 | 20 |
| `2aa00f57` | 124,371,919.02 | 117,808,961.20 | 3 |

前两个项目桶合计与叶子合计**分文不差**（这两个项目的 `1416` 叶子期末为**正**
—— v2 正数口径，`abs()` 是恒等变换）；`2aa00f57` 的 `1416.04` 叶子期末为
**−3,281,478.91**，`abs()` 后差 2×3,281,478.91 = 6,562,957.82，
`124,371,919.02 − 6,562,957.82 = 117,808,961.20` **正好等于叶子合计** → 不变量成立。

> ⚠️ 诊断脚本里的「一致=False」是**脚本自身**的符号还原假设写死了「备抵恒为负」，
> 与项目 `0ec33ac9` 的正号存储冲突，不是代码缺陷（两种符号约定 `abs` 同解，
> 这正是 `build_category_prefill` 取 `abs` 的原因）。

**测试**：`tests/f2_extraction` + `tests/test_f2_render_prefill.py` +
`tests/test_f2_category_rules.py` 共 **132 passed**（新增归类守卫 50 例）。

### 诚实修正的既有测试（不是「改断言凑绿」）

三个测试文件原先锁定的是**旧的错行为**，已改为锁定新口径并补上「旧实现必然失败」的断言：

1. `tests/f2_extraction/test_f2_extraction_characterization.py` —— 原断言
   `1401 → raw-materials`（原材料）、`test_prefill_multi_level_picks_deepest`
   （显式锁定「取最深层级」）。**新增两条旧实现必红的用例**：
   `test_prefill_is_code_agnostic_across_chart_variants`（用变体 B 编码）与
   `test_prefill_ragged_tree_keeps_shallow_leaf`（参差树丢浅层叶子）。
2. `tests/test_f2_render_prefill.py` —— 构造 tb 行时补 `account_name`
   （`_ASSET_ACCOUNTS` 由 `[code]` 改 `[(code, label)]`）。
3. `tests/f2_extraction/test_f2_prefill_gray.py` —— `mock_active_filter` 由
   `MagicMock()` 改真实 `sa.true()`。**这一条本身修掉一个假绿**：
   取数改用 `sa.and_(active_filter, code.like('14%'))` 后 `MagicMock` 会被
   `sa.and_` 拒绝（"SQL expression for WHERE/HAVING role expected"）→ 被 fail-open
   吞成空结果，测试会「通过」却什么都没测到。

### 剩余（Wave 3~5，未做）

- Wave 3：`project_context.inventory_accounts` 已由后端输出，**前端消费点未接**
  （`f2AccountModel` 的 `resolveF2InventoryAccounts` / AJE 科目下拉 / 溯源面板）。
- Wave 4：`workpaper:F2` 的 71 条公式预设**未重写**（运行态实测科目码几乎全错，
  详见 requirements 第 5 条清单）。
- Wave 5：披露/附注三方一致性守卫、浏览器活测。
