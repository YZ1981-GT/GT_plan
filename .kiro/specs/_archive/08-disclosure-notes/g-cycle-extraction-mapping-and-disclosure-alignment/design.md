# Design Document

## Overview

本设计分五层收口 G 循环全链，**自下而上**（下层不修，上层修了也白修）：

```
L1 映射真源      report_config 4 行错码            → 迁移 + 守卫（Req 1）
L2 科目定位      render 子策略硬编码 / fallback 错  → 单一真源化（Req 2）
L3 前端消费      tb_source_codes dead output       → AccountScope + 溯源面板 + 带入按钮（Req 3）
L4 公式预设      科目/口径/sheet/成环 5 类缺陷      → 幂等脚本 + 守卫（Req 4）
L5 披露 → 附注   模板结构 + 披露逻辑 + 共章节文本   → 幂等脚本 + 载荷 + 后端合并语义（Req 5~8）
```

**关键设计判断**

1. **L1 必须先做，且必须改 `report_config` 本身，不能在各循环绕**。
   共享件 `resolve_report_line_accounts` 的语义是「报表公式优先、兜底其次」，
   在循环侧写 `fallback_gross` 纠正**无效**（解析成功时兜底不被使用）。
   若改成「循环侧覆盖报表公式」则彻底破坏「报表映射规则是单一真源」的架构前提。
2. **L1 的迁移必须条件更新**（`WHERE formula = '<已实证错值>'`），不是无条件 UPDATE。
   这样：① 幂等 ② 若并发会话已修则空操作 ③ 不覆盖 `project:` 级用户自定义。
3. **新增 `fallback_conflict` 是诊断而非修复**。它让「报表公式与循环声明的兜底码不一致」
   在溯源面板可见，是防止本次错误重现的长效手段（而非静默取报表公式）。
4. **`_note_texts` 改浅合并是平台级变更**，须保证「单 owner 章节逐字等价」：
   单 owner 推送时合并结果 ≡ 替换结果（键集相同），故 300+ 既有章节零回归。
5. **污染清理与结构修订分离**：结构修订（补 columns / guidance / 行集）是安全的幂等写库；
   污染清理（删表 / 删文本）是破坏性的，独立脚本 + 默认 dry-run + `--rollback`。

## Architecture

### L1 报表映射真源纠偏

```
backend/migrations/V135__fix_report_config_g_cycle_account_codes.sql
  ├─ BS-022: TB('1505') → TB('1506')   条件 WHERE formula LIKE '%1505%'
  ├─ BS-025: TB('1506') → TB('1507')
  ├─ BS-026: TB('1507') → TB('1519')
  ├─ IS-016: TB('6701') → TB('6702')
  └─ IS-017: TB('6702') → TB('6701')
     全部附加 AND applicable_standard NOT LIKE 'project:%'
```

🔴 **顺序陷阱**：BS-022/025/026 是链式偏移，若按 `1505→1506, 1506→1507, 1507→1519` 顺序
逐条 UPDATE，第一条把 BS-022 改成 1506 后，第二条的 `WHERE formula LIKE '%1506%'` 会
**同时命中刚改过的 BS-022**。故必须**按 row_code 精确限定**每条 UPDATE，不能只按 formula 匹配。

守卫 `backend/tests/four_table/test_report_config_account_semantics.py`：
- 数据源用 `backend/data/*account_chart*.json`（不连库，可进 CI）建 `code → name` 字典
- Property：`report_config` 每个 `TB('code')` 的 code 必须存在于科目表
- Property：报表行名与科目名的语义一致性（按关键字集比对，如「其他债权投资」行不得引用名为
  「减值准备」的科目）
- 逐行钉死本次 5 行 + 反向自检

### L2 科目定位单一真源化

```
backend/app/services/four_table/report_line_accounts.py
  + ReportLineAccounts.fallback_conflict: list[str]     # additive，默认 []
  + resolve_report_line_accounts(..., spec) 内比对 gross_standard vs spec.fallback_gross

backend/app/routers/wp_render_strategies/
  _g4_bond_investment_ecl.py    ─┐
  _g4_bond_investment_sppi.py   ─┤ 复用 g4_account_scope.G4_ACCOUNT_SPEC
  _g6_other_bond_investment_ecl.py ─┐
  _g6_..._main_service.py          ─┤ 复用 g6_account_scope.G6_ACCOUNT_SPEC
  _g7_long_term_equity_main_service.py → 复用 g7 既有 spec
```

新建 per-cycle 后端 scope 模块（与前端 `g{n}AccountScope.ts` 对称）：

```
backend/app/services/four_table/g_cycle_specs.py
  G1_SPEC = ReportLineAccountSpec(row_code='BS-003', fallback_gross=('1101',))
  G4_SPEC = ReportLineAccountSpec(row_code='BS-021', fallback_gross=('1504',),
                                  fallback_provision=('1505',))
  G6_SPEC = ReportLineAccountSpec(row_code='BS-022', fallback_gross=('1506',))
  G8_SPEC = ReportLineAccountSpec(row_code='BS-025', fallback_gross=('1507',))
  G9_SPEC = ReportLineAccountSpec(row_code='BS-026', fallback_gross=('1519',))
  G14_SPEC = ReportLineAccountSpec(row_code='IS-016', fallback_gross=('6702',))
  ...
```

一处声明、各 render 引用 —— 杜绝「main 与 ecl 子策略科目码分叉」。

🔴 **G2 / G3 的 row_code 需重定**：实测 `BS-015` 是「流动资产合计」（`ROW()` 派生行）、
listed 侧 `BS-016` 是「一年内到期的非流动资产」。两者目前**侥幸正确**（派生行提不出 `TB()`
码 → 返空 → 走 fallback）。但 `_fetch_formula` 会把「流动资产合计」的公式当作溯源展示给用户。
处置：G2 / G3 的 spec 改为 `row_code=None` 语义（新增支持）或指向真实行
（soe 侧 `BS-016 其中：应收股利` 对 G3 有效；G2 应收利息在 `report_config` **无独立行**，
已并入 `BS-009 其他应收款` 的 `+ TB('1131')`… 实测该式含 1131 不含 1132）
→ **本项列为待用户裁决**，默认保持 fallback 并在溯源面板标注「无独立报表行，按科目表兜底」。

### L3 前端消费链路

```
g{n}AccountScope.ts (per-cycle 单一真源)
   ├─ G{n}_REPORT_ROW_CODE / G{n}_GROSS_FALLBACK_STANDARD
   ├─ g{n}GrossQueryCodes(src)   ← 运行态取 render 下发 tb_source_codes.gross_standard
   └─ g{n}AccountCode(src)       ← 展示 / 事件载荷用

G{n}TabAdjudication.vue
   ├─ <WpFourTableSourcePanel :src="tbSourceCodes" ... />   共享件
   └─ 「从四表库带入未审数」→ useG{n}Adjudication.pullFromTB()
         ├─ findRowForPrefill: 科目码优先于行名
         └─ seedFromPrefill({ overwrite }): 手工值永不被覆盖
```

复用平台既有共享件（K2 spec 已提升）：
`components/workpaper/shared/WpFourTableSourcePanel.vue` +
`composables/shared/tbSourceCodes.ts` + `composables/shared/dynamicAdjudicationRows.ts`。

### L4 公式预设

```
backend/scripts/fix/fix_g_cycle_prefill_presets.py   （--dry-run / --check / apply）
  ├─ 删除幽灵块（sheet ∉ 源 xlsx）
  ├─ 纠正科目码与口径（损益类 → 本期发生额）
  ├─ 纠正 wp_name / description 贴错标签
  └─ 补披露 sheet 块（两变体）+ 明细表块
```

守卫 `backend/tests/test_g_cycle_formula_presets.py`（范式取自 `test_f2_formula_presets.py`）。

### L5 披露 → 附注

```
backend/scripts/fix/fix_note_g_liability_and_pl_structure.py
  五、34 / 五、35 / 八、34 / 八、35   (G10)
  五、69 / 八、70                     (G11)
  三、公允价值变动收益 / 八、72        (G13)
  三、信用减值损失 / 八、73            (G14)
  复用 backend/scripts/fix/_note_structure_kit.py（flat_columns / rule / run_section / build_cli）

backend/scripts/fix/cleanup_g13_polluted_note_section.py   （默认 dry-run + --apply + --rollback）

backend/app/services/wp_disclosure_sync_service.py
  _merge_note_texts(existing, incoming, removed)   新增纯函数
  sync_from_workpaper: _note_texts 由「整替换」改「按 section 浅合并」
```

## Components and Interfaces

### `ReportLineAccounts.fallback_conflict`（additive）

```python
@dataclass(frozen=True)
class ReportLineAccounts:
    ...
    #: 报表公式解析结果与调用方 fallback 不一致的标准码（诊断用，默认空）
    fallback_conflict: list[str] = field(default_factory=list)
```

- 仅当 `resolved_from == 'report_config'` 且 `set(gross_standard) != set(spec.fallback_gross)`
  且 `spec.fallback_gross` 非空时非空
- `as_dict()` 原样带出 → 前端溯源面板渲染橙色告警条
- 默认 `[]` = 引入前逐字等价（D1/K1/K2/F1/G5/G6/G7 零回归）

### `_merge_note_texts`（纯函数，可独立单测）

```python
def _merge_note_texts(
    existing: list[dict] | None,
    incoming: list[dict] | None,
    removed_sections: set[str] | None = None,
) -> list[dict]:
    """按 `section` 键浅合并说明段，保持既有顺序稳定。

    - incoming 中的 section 覆盖 existing 同名 section
    - existing 中未被 incoming 覆盖的 section 原样保留（多 owner 共章节的关键）
    - removed_sections 中的 key 从结果中剔除（只允许删本 owner 曾推送的段）
    - 顺序：existing 的原顺序在前，incoming 的新 section 追加在后
    """
```

**零回归论证**：单 owner 场景下 `existing` 的 section 键集 ⊆ `incoming` 的键集
（同一 builder 每次推全量）→ 合并结果的键集与值 ≡ 替换结果，仅顺序可能不同；
`_format_note_texts` 按列表顺序拼装 `text_content`，故需守卫「单 owner 往返后
`text_content` 逐字不变」。

### 披露勾稽引擎（per-cycle 纯函数）

```typescript
// composables/g{n}DisclosureConsistency.ts
export function checkG10Consistency(snap: G10Snapshot): ConsistencyCheck[]
// 规则全部取自源模板 Excel 公式，例如 五、34：
//   B8 = B9+B10+B11        交易性金融负债 = 三个子项之和
//   B12 = B13+B14          指定为FVTPL金融负债 = 两个子项之和
//   B15 = B8+B12           合计
//   E 列同构
//   B41 = SUM(B36:B40)     五、35 衍生金融负债合计
```

复用平台共享件 `shared/disclosure/WpDisclosureConsistencyPanel.vue` +
`composables/shared/disclosureConsistency.ts`。

### 动态插行区处理

源模板留白可扩行区 → 披露表动态行，复用平台共享件
`composables/shared/dynamicAdjudicationRows.ts` 的 `DynamicRowsSpec` 声明式入参：

| 循环 | 动态区 | 源模板依据 |
|---|---|---|
| G10 五、34 T1 | 指定为 FVTPL 金融负债明细 | R19:R21 三个空行 + R22 合计 |
| G10 五、34 T2 | 公允价值变动明细 | R27 示例行 + R28:R29 空行 + R30 合计 |
| G10 五、35 | 衍生金融负债分类 | R36:R40 五个空行 + R41 合计 |
| G11 五、69 T1 | 处置交易性金融资产投资收益明细 | R25:R33 含「其中：」层级 |

行 key 用 `{slot}_{seq}`（禁用中文 label 作 key —— 源模板多处默认名相同会撞键）。

## Data Models

### `report_config` 纠偏前后（本次唯一的库结构相关变更，仅数据不改 schema）

| row_code | applicable_standard | formula (before) | formula (after) |
|---|---|---|---|
| BS-022 | listed_consolidated / listed_standalone / soe_consolidated / soe_standalone | `TB('1505','期末余额')` | `TB('1506','期末余额')` |
| BS-025 | 同上 4 条 | `TB('1506','期末余额')` | `TB('1507','期末余额')` |
| BS-026 | 同上 4 条 | `TB('1507','期末余额')` | `TB('1519','期末余额')` |
| IS-016 | 同上 4 条 | `TB('6701','本期发生额')` | `TB('6702','本期发生额')` |
| IS-017 | 同上 4 条 | `TB('6702','本期发生额')` | `TB('6701','本期发生额')` |

共 20 行受影响。`CFSS-003` / `CFSS-004` 已正确，不动。

### `disclosure_notes.table_data` 形态（`_note_texts` 语义变更）

```jsonc
{
  "sub_table_data": { "<表名>": [ { "<列key>": <值>, "is_total": true } ] },
  "_sub_table_columns": { "<表名>": [ { "key": "...", "label": "...", "flat": true } ] },
  // 变更点：多 owner 共章节时按 section 键累积，不再被单个 owner 整体替换
  "_note_texts": [
    { "section": "soe-audit-note", "title": "应收利息审计说明", "text": "..." },   // G2 owns
    { "section": "k1-nature", "title": "款项性质说明", "text": "..." }             // K1 owns
  ],
  "_source": "workpaper",
  "_last_sync_at": "...",
  "_last_sync_wp_id": "..."
}
```

### G 循环科目映射真源表（纠偏后，本 spec 的权威结论）

| 循环 | 科目 | 报表行 | 标准码 | 备抵 |
|---|---|---|---|---|
| G1 | 交易性金融资产 / 衍生金融资产 | BS-003 / BS-004 | 1101 / 1102 | — |
| G2 | 应收利息 | 无独立行（待裁决） | 1132 | — |
| G3 | 应收股利 | BS-016（仅 soe） | 1131 | — |
| G4 | 债权投资 | BS-021 | 1504 | 1505 |
| G5 | 长期应收款 | BS-023 | 1531 | — |
| G6 | 其他债权投资 | BS-022 | **1506** | — |
| G7 | 长期股权投资 | BS-024 + IMP-009 | 1511 | 1512 |
| G8 | 其他权益工具投资 | BS-025 | **1507** | — |
| G9 | 其他非流动金融资产 | BS-026 | **1519** | — |
| G10 | 交易性金融负债 | BS-042 | 2101 | — |
| G11 | 投资收益 | IS-011 | 6111（本期发生额） | — |
| G12 | 净敞口套期收益 | IS-014（formula None） | 6103（兜底） | — |
| G13 | 公允价值变动收益 | IS-015 | 6101（本期发生额） | — |
| G14 | 信用减值损失 | IS-016 | **6702**（本期发生额） | — |

## Correctness Properties

### Property 1: 报表公式引用的科目码必须存在于标准科目表

`report_config` 中每个 `TB('code', …)` / `SUM_TB('a~b', …)` 的 code（区间端点亦然）
都能在标准科目表中查到，不存在悬空引用。

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8**

### Property 2: 报表行名与所引科目名语义一致

若报表行名含「减值准备」/「坏账准备」则所引科目名亦含；反之若行名不含备抵关键字
则所引科目名不得含 —— 这条正是抓住 BS-022 引用「债权投资减值准备」的判据。

**Validates: Requirements 1.1, 1.8, 1.9**

### Property 3: 迁移幂等且不越权

对同一库连续执行两次纠偏迁移，第二次影响行数为 0；
且执行前后 `applicable_standard LIKE 'project:%'` 的行逐字不变。

**Validates: Requirements 1.6, 1.7**

### Property 4: G render 源码不含其它循环的科目码字面量

对每个 G render 文件（`stripComments()` 后），源码中出现的 4 位科目码字面量
必须属于「本循环科目 ∪ 本循环备抵 ∪ 平台通用码」集合。

**Validates: Requirements 2.1, 2.2, 2.3, 2.7**

### Property 5: fallback_conflict 仅在真冲突时非空且默认等价

当 `spec.fallback_gross` 为空、或解析结果与兜底码集合相等、或 `resolved_from == 'fallback'`
时，`fallback_conflict == []`；其余情况非空且等于差异码集。
引入该字段前后，既有消费者（D1/K1/K2/F1/G5/G6/G7）的 `as_dict()` 其余键逐字相同。

**Validates: Requirements 2.5, 2.6**

### Property 6: 「带入未审数」不破坏手工录入

对任意「已有行集 + prefill 数据」组合，`seedFromPrefill` 后：
所有原本有手工值且四表无对应数据的行金额不变；
所有四表有数据的行按科目码匹配（而非行名）落位；
行数只增不减。

**Validates: Requirements 3.3, 3.4**

### Property 7: 每个 render 输出的 tb_source_codes 都有前端消费点

对每个输出 `tb_source_codes` 的 G render，前端该循环目录下必存在读取该字段的代码路径
（`WpFourTableSourcePanel` 挂载点或 `g{n}AccountScope` 的运行态取值）。

**Validates: Requirements 3.1, 3.2, 3.6**

### Property 8: 预设公式的科目码属于本循环报表行引用集合

每条预设的 `TB()` / `ADJ()` 科目码 ∈ (`account_chart` 全集) ∩
(本循环报表行公式引用的科目集 ∪ 本循环备抵码 ∪ 显式登记的例外)。

**Validates: Requirements 4.1, 4.3, 4.4, 4.10**

### Property 9: 损益类预设口径恒为本期发生额

对损益类循环（科目码首位为 6）的每条 `TB()` 预设，第二参数为 `本期发生额`，
不得为 `期初余额` / `期末余额`。

**Validates: Requirements 4.2, 4.10**

### Property 10: 预设 sheet 名存在且无成环

每个预设块的 `sheet` ∈ 该循环源 xlsx 的 `sheetnames`；
且不存在 `A.sheet` 引用 `WP(cycle, B.sheet)` 同时 `B.sheet` 引用 `WP(cycle, A.sheet)` 的环。

**Validates: Requirements 4.5, 4.6, 4.8, 4.10**

### Property 11: 附注表列元数据完整且显式表态

对本 spec 覆盖的 10 个章节的每张表：`columns` 非空、每列有 `flat` 或 `group` 之一、
`guidance` 非空且不含 markdown 粗体、`headers` 为纯文本（不含 HTML）。

**Validates: Requirements 5.1, 5.2, 5.8**

### Property 12: 附注行集与源 xlsx 三向一致

对每张表，附注模板 `rows[].label` 序列（归一化空白与编号后）与源 xlsx 对应行区逐项相等；
`headers` 与源 xlsx 表头行逐项相等；同步载荷 `columns[].label` 与 `headers` 逐项相等。

**Validates: Requirements 5.4, 5.5, 5.8, 6.5**

### Property 13: 表名无泄漏且无年份字面量

本 spec 覆盖章节的每张表名：不等于其 `headers[0]`、不含换行、长度 ≤ 40、
不含四位年份数字、不为纯「续：」。

**Validates: Requirements 5.3, 5.6**

### Property 14: `_note_texts` 浅合并保留其他 owner 的段

对任意 `(existing, incoming)`：结果的 section 键集 == `existing` 键集 ∪ `incoming` 键集
− `removed`；`incoming` 中的 section 取 `incoming` 的值；其余取 `existing` 的值。
当 `incoming` 为空时结果 == `existing`。

**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 15: 单 owner 章节的文本合并逐字等价

若 `existing` 的 section 键集 ⊆ `incoming` 的键集，则
`_format_note_texts(_merge_note_texts(existing, incoming))` 与
`_format_note_texts(incoming)` 逐字相同（既有 300+ 章节零回归的保证）。

**Validates: Requirements 7.1, 7.2, 7.4**

### Property 16: 同章节多 owner 的子表名两两无交集

对每个被多个循环推送的附注章节，各 owner 声明的子表名集合两两交集为空，
且并集 ⊆ 该章节模板的 `tables[].name` 集合（无孤儿）。

**Validates: Requirements 7.5, 7.7**

### Property 17: 污染清理只删可识别的外来内容

清理脚本对某章节的操作满足：被删表的行标签序列与外来章节某表逐字相同；
被删文本段的主题判据命中；该章节自有的表与文本逐字保留；
`--rollback` 后 `table_data` 与清理前逐字相同。

**Validates: Requirements 8.1, 8.2, 8.4, 8.6, 8.7**

### Property 18: 清理后无剩余子表时保留 seed 骨架

若清理后 `sub_table_data` 为空，则 `_tables` 保留、`_source` / `_last_sync_*` 被撤回，
章节回退 legacy 渲染而非显示空白。

**Validates: Requirements 8.5**

### Property 19: 动态行 key 稳定且不撞键

对任意动态区的任意增删改名序列，行 key 形如 `{slot}_{seq}` 且全局唯一；
改名不改 key；删除后重新新增不复用已删 key。

**Validates: Requirements 6.3, 6.4**

### Property 20: 占位骨架行不进附注

金额列全零且行名为空或等于结构标签（「其中：」/「合  计」等）的动态行，
不出现在同步载荷中。

**Validates: Requirements 6.4, 6.5**

### Property 21: 账龄档位随项目配置联动

对 3 年段 / 5 年段 / 自定义三种项目账龄配置，披露载荷的账龄行标签集合
等于 `disclosureAgingLabels` 按该配置派生的集合，源码中无档位字面量。

**Validates: Requirements 6.9**

### Property 22: 金额控件与格式单一真源

G 循环披露表与审定表中 `el-input-number :formatter` 出现次数为 0；
可编辑金额一律 `WpAmountInput`；只读金额一律经 `displayPrefs.fmtAmount()`；
比例 / 利率 / 天数 / 年度列不得套用 `WpAmountInput`。

**Validates: Requirements 6.6**

### Property 23: AI 辅助接线正确

每个披露文本域都有 AI 按钮；请求走 `/ai/generate-text`；`context` 为对象而非字符串；
每条后端 prompt 长度 ≥ 20 字且含「不得虚构」；按钮有 `loading` 与只读禁用。

**Validates: Requirements 6.7**

### Property 24: 勾稽规则源自源模板公式

每条勾稽规则都能追溯到源 xlsx 的一个单元格公式（规则对象带 `source_ref`），
不存在凭常识自造的规则。

**Validates: Requirements 6.8**

### Property 25: 叶子聚合等于父科目余额

对每个 G 循环科目，`select_leaves` 选出的叶子的期末余额之和
等于该科目在 `tb_balance` 的父行期末余额（按方向带符号）。

**Validates: Requirements 9.2**

### Property 26: 实测数据完整复原

实测结束后，被触碰的 `checklist_responses` 键集与 `disclosure_notes.table_data`
与实测前快照逐字相同，`last_sync_at` 回到实测前值。

**Validates: Requirements 9.6**

## Error Handling

| 场景 | 处置 | 依据 |
|---|---|---|
| `report_config` 无该报表行 / 公式为 None | `resolve_report_line_accounts` 返回 `resolved_from='fallback'` + 用 `spec.fallback_gross` | 既有 fail-open 铁律，G12 的 IS-014 即此形态 |
| `account_chart` 查询失败 | 备抵判定降级为码族启发，不阻断 render | 既有实现 |
| `account_mapping` 无反解记录 | 退化为标准码一级段前缀 + `provision_exact=False` | 既有实现；G4~G9 当前即此形态 |
| 迁移的 `WHERE` 未命中（已被并发会话修正） | 影响 0 行，迁移成功退出 | Property 3 |
| 迁移发现 `project:` 级覆盖 | 不修改，写 `RAISE NOTICE` 列出，交人工 | Req 1.7 |
| 报表公式与 `fallback_gross` 冲突 | 取报表公式（真源优先）+ `fallback_conflict` 标注 + 溯源面板橙色告警 | Req 2.6；不静默 |
| `adjudication_prefill` 为空 | 界面显示「四表库暂无该科目数据」，不静默空转 | Req 3.5 |
| 「带入未审数」与手工值冲突 | 弹确认框，提供「仅补空值」选项 | Property 6 |
| 预设块 sheet 不存在 | `--check` 报欠账；apply 时删除该块并在报告中记录依据 | Req 4.5 |
| 附注模板某表在 seed 里不存在 | `rule(insert=True)` 补整张表；未声明的表不动 | `_note_structure_kit` 既有语义 |
| 污染清理判据不命中 | 跳过并计入「未识别」清单，不猜测删除 | Property 17 |
| 清理后无剩余子表 | 保留 `_tables`、撤回 `_source` → 回退 legacy 渲染 | Property 18 |
| 同步载荷 `_note_texts` 为空 | 保留既有 `text_content`，不置 `None` | Req 7.2（本次修正点） |
| 跨主体类型推送 | 既有 `detect_standard_conflict` 抛 409 | 平台既有守卫 |
| AI 生成失败 / 422 | toast 提示具体错误，不静默 `catch {}` | Property 23 |

## Testing Strategy

### 后端

| 测试文件 | 覆盖 |
|---|---|
| `backend/tests/four_table/test_report_config_account_semantics.py` | Property 1, 2（数据源用 `backend/data` 的科目表 JSON，不连库） |
| `backend/tests/test_migration_v135_report_config_fix.py` | Property 3（幂等 + 不越权 `project:`） |
| `backend/tests/four_table/test_g_cycle_specs.py` | Property 4, 5（源码级字面量扫描 + `fallback_conflict` 等价性） |
| `backend/tests/test_g_cycle_formula_presets.py` | Property 8, 9, 10 |
| `backend/tests/test_note_g_liability_and_pl_structure.py` | Property 11, 12, 13（openpyxl 直读源 xlsx 三向比对 + 反向自检） |
| `backend/tests/test_note_texts_merge.py` | Property 14, 15（含 hypothesis PBT，`max_examples=5`） |
| `backend/tests/test_cleanup_g13_pollution.py` | Property 17, 18 |
| `backend/tests/test_review_dialog_g_cycle_prompts.py` | Property 23 的后端半（prompt 登记 + 长度 + 「不得虚构」） |

### 前端

| 测试文件 | 覆盖 |
|---|---|
| `composables/__tests__/gCycleAccountScope.spec.ts` | Property 4 的前端半（字面量清零）、Property 7 |
| `composables/__tests__/gCycleFourTableWiring.spec.ts` | Property 6, 7 |
| `composables/__tests__/gCycleNoteSubtableContract.spec.ts` | Property 11, 12, 16（复用 `_disclosureSubtableContract.helper`） |
| `composables/__tests__/gCycleDisclosureConsistency.spec.ts` | Property 24（每条规则有 `source_ref`） |
| `composables/__tests__/gCycleDynamicRows.spec.ts` | Property 19, 20（含 PBT） |
| `composables/__tests__/gCycleAgingLabels.spec.ts` | Property 21 |
| `composables/__tests__/gCycleAmountInput.spec.ts` | Property 22（含反向边界：比例列不得套用） |
| `composables/__tests__/gCycleDisclosureAiWiring.spec.ts` | Property 23（`stripComments()` + 反向自检） |

### 活体实测（Property 25, 26）

工具链：`chrome-devtools` MCP 驱动浏览器 + `postgres` MCP 只读复核。

1. 真实项目直跑 render，读 `tb_source_codes`（`resolved_from` / `gross_standard` / `fallback_conflict`）
2. postgres 复核叶子和 == 父额（Property 25）
3. 浏览器点「从四表库带入未审数」，比对金额与四表库
4. 披露表改数 → 等自动同步 → postgres 查 `last_sync_at` 前移 + 子表数 + `_sub_table_columns`
5. **共章节交叉验证**：K1 录说明 → 同步 → G2 改数 → 同步 → 查 `_note_texts` 两个 section 都在
6. 逐键复原并留证

### 回归基线

- 改动前先跑 `four_table` 全量 + `g*` 全量后端测试、前端 `src/components/workpaper` 全量
  （JSON reporter），记录失败基线，收口时逐项比对
- 已知预存在基线：`views/composables/__tests__` 9 例 / 5 文件；
  `disclosureAutoSyncCoverage.spec.ts` 的 `D2TabDisclosure.vue` 一条
