# Design: d2-ar-disclosure-soe-alignment

## 1. 现状实测（改前基线）

| 层 | 文件 | 现状 | 源模板 |
|----|------|------|--------|
| 同步 | `d2NoteSectionMap.ts` `D2_TABLE_NAMES.soe` | 9 个表名，无 `continuedInvolvement` | 需 10 |
| 同步 | 组合分表列 | 复用 `AGING_COLUMNS_SOE`（3 列） | `账 龄` + 双期×{应收账款, 比例(%), 坏账准备} = 7 列 |
| 同步 | `OTHER_PORTFOLIO_COLUMNS_SOE` | 3 列 | 7 列 |
| 同步 | `MOVEMENT_COLUMNS_SOE` | 6 列但三变动列无 `group`，label 为 `本期计提` | `group=本期变动金额`，label `计提` |
| 底稿 | 组合分表 UI（SOE 分支） | 仅期末 3 列，无期初 | 双期 |
| 底稿 | 其他组合表 UI | 3 列 | 7 列 |
| 底稿 | 终止确认块 | 无说明文本框 | r125~128 说明 A/B |
| 附注 | `note_template_soe.json` `八、5` | 11 表；账龄 4 档无小计/减项；分类 3 列；组合分表 3 列；其他组合 3 列；变动 4 列；无继续涉入 | 见 requirements |
| 后端 | `disclosure_engine._carry_seed_column_meta` | **已存在**（f2 spec R5 实现，已在多表分支调用） | 复用，不重复实现 |
| 测试 | `d2NoteSectionMap.spec.ts` | 5 条断言过期（上市版 WIP 遗留） | 需修正 |

> 实测手段：openpyxl 读源 xlsx（`_tmp` 脚本，用后即删）+ python 直读工作区文件。
> 🔴 `readFile` 工具对本次已修改的文件返回过 HEAD 版本，本 spec 全程以 python 直读为准。

## 2. 数据流

```
D2-2 明细 / D2-1 审定 / D2-3 坏账 / D2-5 分析 / D2-11 转回核销
        │ (useD2CrossSheet 自动取数，可手工覆盖)
        v
useD2DisclosureNote  ── buildSnapshot() ──> D2DisclosureSnapshot
        │                                          │
        │ (D2DisclosureNoteBody.vue 渲染/录入)      v
        │                              buildD2SyncPayload('soe', ...)
        │                                          │ sub_table_data + columns + _note_texts
        v                                          v
  checklist_responses                POST /disclosure-notes/sync-from-workpaper
  (D2-disc-soe-* 前缀)                             │
                                                   v
                                    disclosure_notes.table_data.sub_table_data
                                                   │ project_sub_tables（读时投影）
                                                   v
                                    _tables[] → DisclosureEditor TAB + _column_groups 两级表头
                                    _note_texts → text_content（表下方富文本框）
```

未同步时：`disclosure_engine` 从 `note_template_soe.json` 的 `tables[]` 生成 `_tables`，
既有 `_carry_seed_column_meta` 已把 seed 上的 `_column_groups` 带过去，故模板态也有两级表头
——本 spec 只需把 `_column_groups` 写进模板 seed。

## 3. 关键设计决策

### D1 — 编号沿用附注既有口径，继续涉入顺延为 `（7）`
源 sheet 账龄表不编号；附注 `八、5` 既有把账龄编为 `（1）`。改编号会牵动
`note_template_bindings.json`（`八、5` 已有 binding，`table_index=0` 绑定「（1）按账龄披露应收账款」）、
`report_note_linkage`、既有 `text_sections`。收益低风险高 → 不改，仅新增 `（7）`。

### D2 — 组合分表比例列为派生只读，不落库
源 `C73=ROUND(B73/$B$79,4)` = 该账龄段应收账款 ÷ 组合合计。
比例随金额变化，落库会产生不一致的第二真源 → 前端 computed + 同步时现算。
分母 0 → 0（与源 `IFERROR(...,0)` 同义）。

### D3 — 其他组合表「计提比例」= 坏账准备 ÷ 账面余额
源模板该列名为「计提比例（%）」而非「预期信用损失率」，语义为组合整体计提率，同为派生只读。

### D4 — 国企继续涉入表按源模板 2 列 + 资产/负债分块行
源 r130~r136：`项 目` / `期末金额`，行 = `资产：` / 明细 / `资产小计` / `负债：` / 明细 / `负债小计`。
底稿行模型 `D2ContinuedInvolvementRow{item, transferMethod, assetAmount, liabilityAmount}` 保持不变
（底稿多一列「资产转移方式」便于追溯），同步时按变体转形：
- 上市 → 4 列宽表（既有 `CONTINUED_INVOLVEMENT_COLUMNS`，不动）
- 国企 → 2 列 + 分块行：`资产：`(header_label) → 每行 `assetAmount` → `资产小计`(subtotal)
  → `负债：`(header_label) → 每行 `liabilityAmount` → `负债小计`(subtotal)
- 「资产转移方式」信息由 `note-continuedInvolvement` 说明文本承载（源模板 r138 说明即要求文字描述转移方式）

### D5 — 附注模板修订走幂等脚本，不手改 JSON
`scripts/fix/rebuild_note_from_md.py` 会重建 `note_template_soe.json`，手改会被冲掉。
故写 `backend/scripts/fix/fix_note_ar_soe_structure.py`：
- 定位 `section_number == '八、5'`（唯一）
- 整段替换 `tables` 与 `text_sections`（以源模板为准的常量表）
- 打幂等标记 `_aligned_by: 'd2-ar-disclosure-soe-alignment'`；已存在标记且结构相等 → 空操作
- 不动其他 186 个 section，不动 `check_presets` / `scope` / `sort_order`

### D6 — `减：坏账准备` 行类型沿用平台既有约定
`八、7 预付款项` / `八、9 应收利息` 等 22 张表统一用
`[data..., 小计(subtotal), 减：X(data), 合计(total)]`。
`note_total_recalc` 的「上一合计行之后求和」算法无法表达 `合计 = 小计 − 减项`，
这是既有平台限制（正解是 `DISCLOSURE_NOTE_FORMULA_ENABLED` 公式引擎，当前灰度关闭）。
本 spec **不新造 row_type**，与既有 22 张表保持一致；附注侧实际数值由底稿同步供给
（`project_sub_tables` 不跑 recalc，逐行按推送值渲染）。

### D7 — 分类披露「合计 = 单项 + 组合」同理
源 `B28=B20+B21`，`其中：` 各组合为信息性子行。模板行类型取源模板语义
（`按单项计提坏账准备`/`按组合计提坏账准备` 为 data，`其中：` 为 header_label，示例组合行为 data，`合 计` 为 total），
数值由底稿同步供给。较改前（把 `按组合计提坏账准备` 误标为 `total`）更贴近源模板。

## 4. 目标结构（附注模板 `八、5`，12 张表）

| # | 表名（TAB） | headers | `_column_groups` | rows |
|---|------------|---------|------------------|------|
| 1 | （1）按账龄披露应收账款 | 账 龄 / 期末数 / 期初数 | — | 6 档 + 小 计 + 减：坏账准备 + 合 计 |
| 2 | （2）按坏账准备计提方法分类披露应收账款 | 类 别 / 金额 / 比例(%) / 金额 / 预期信用损失率(%) / 账面价值 | 账面金额(1,2) 坏账准备(3,2) | 单项 / 组合 / 其中：(header_label) / 2 示例组合 / 合 计 |
| 3 | 同上（续：期初数） | 同 2 | 同 2 | 同 2 |
| 4 | 期末单项计提坏账准备的应收账款 | 债务人名称 / 账面余额 / 坏账准备 / 账龄 / 预期信用损失率（%） / 计提理由 | — | 合 计 |
| 5 | 组合计提项目：应收中央企业客户 | 账 龄 / 应收账款 / 比例(%) / 坏账准备 / 应收账款 / 比例(%) / 坏账准备 | 期末数(1,3) 期初数(4,3) | 6 档 + 合 计 |
| 6 | 组合计提项目：应收海外企业客户 | 同 5 | 同 5 | 同 5 |
| 7 | 采用余额百分比或其他组合方法计提坏账准备的应收账款 | 组合名称 / 账面余额 / 计提比例（%） / 坏账准备 / ×2 | 期末数(1,3) 期初数(4,3) | 合 计 |
| 8 | （3）本期计提、收回或转回的坏账准备情况 | 类 别 / 期初数 / 计提 / 收回或转回 / 转销或核销 / 期末数 | 本期变动金额(2,3) | 单项 / 组合： / …… / 合 计 |
| 9 | 收回或转回的坏账准备 | 4 列（不变） | — | 合 计 |
| 10 | （4）本期实际核销的应收账款 | 6 列（不变） | — | 合 计 |
| 11 | （5）按欠款方归集的期末余额前五名的应收账款 | 4 列（不变） | — | 合 计 |
| 12 | （6）由金融资产转移而终止确认的应收账款 | 3 列（不变） | — | 合 计 |
| 13 | （7）应收账款转移继续涉入形成的资产、负债的金额 | 项  目 / 期末金额 | — | 资产：(header_label) / 资产小计 / 负债：(header_label) / 负债小计 |

`text_sections` = 既有 7 条 + `（7）应收账款转移继续涉入形成的资产、负债的金额`。

## 5. 变更文件清单

| 文件 | 变更 |
|------|------|
| `composables/d2NoteSectionMap.ts` | `D2_TABLE_NAMES.soe.continuedInvolvement`；新增 `PORTFOLIO_COLUMNS_SOE` / `CONTINUED_INVOLVEMENT_COLUMNS_SOE`；改写 `OTHER_PORTFOLIO_COLUMNS_SOE` / `MOVEMENT_COLUMNS_SOE`；`D2OtherPortfolioRowLike`；SOE 分支推 6 值键 + 继续涉入 |
| `composables/useD2DisclosureNote.ts` | `D2TwoPeriodManualRow` → 增 `provision`/`priorProvision`；`portfolioRatio()` / `otherPortfolioRate()` 派生纯函数；`buildSnapshot` 补字段 |
| `d2/D2DisclosureNoteBody.vue` | SOE 组合分表两级表头 7 列；其他组合表 7 列；终止确认说明 textarea |
| `backend/app/services/disclosure_engine.py` | **不改动**（`_carry_seed_column_meta` 已由 f2 spec 提供并已接线） |
| `backend/scripts/fix/fix_note_ar_soe_structure.py` | 新增幂等修订脚本 |
| `backend/data/note_template_soe.json` | 由脚本产出 |
| `__tests__/d2NoteSectionMap.spec.ts` | 修正 5 条过期断言 + 新增国企契约断言 |
| `backend/tests/services/test_note_template_ar_soe_structure.py` | 新增模板结构 + 幂等契约测试 |

## 6. Properties（测试目标）

- **P1 列头字面一致**：国企各表 `columns[].label` 与源模板逐字相等
- **P2 双期同构**：组合分表 / 其他组合表 期末与期初子列 label 序列相同
- **P3 比例派生**：`比例(%)` = 分子/分母×100，分母 0 → 0；不出现在持久化 payload 的落库键里
- **P4 继续涉入转形**：国企载荷行序 = `资产：`→资产明细→`资产小计`→`负债：`→负债明细→`负债小计`，小计等于对应明细之和
- **P5 文本节全覆盖**：`_note_texts` 键集合 ⊆ `D2_NOTE_TEXT_SECTIONS`，非空即推送
- **P6 模板幂等**：修订脚本连跑两次 JSON 逐字节相等
- **P7 透传零回归**：模板表无 `columns`/`_column_groups` 时 `_build_table_data` 返回键集合不变
- **P8 历史兼容**：`otherPortfolioRows` 旧持久化（无 provision）读入后不丢 `endAmount`/`priorAmount`
