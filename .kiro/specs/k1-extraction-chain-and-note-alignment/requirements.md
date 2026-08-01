# Requirements Document

## Introduction

K1「其他应收款」循环的**取数级联根是断的**，披露→附注的**行集/列头/文字标题**与源模板存在多处实质不符。

本 spec 收口三件事：

1. **四表库 ↔ 底稿的取数关系补齐**——让「四表入库 → 刷新」后，K1 各能取数的底稿都真的有数据；
2. **底稿当页公式管理的公式预设**补齐（K1 现仅 2 个块，而 F2 有 18、H1 有 8）；
3. **两个披露表（上市/国企）与附注模块（上市 §五、8 / 国企 §八、9）的结构与内容按源模板对齐**，识别动态插行区域，账龄枚举（3 年段 / 5 年段 / 自定义）全链贯通。

**唯一裁决者 = 源模板** `backend/wp_templates/K/K1 其他应收款.xlsx` 的
`附注披露信息(上市公司）`（166 行，① ~ ⑩）与 `附注披露信息（国企）`（130 行，账龄表 / 按计提方法分类 / ① ~ ⑧）两个 sheet；
列结构冲突时叠加 `note_check_preset_formulas.json` 的 `F8-*`（139 条）作勾稽语义参照。

**实证基线（本 spec 开工前，只读核查）**

| 事实 | 证据 |
|------|------|
| `report_config` BS-009 四准则公式 | soe_standalone `TB('1221')−TB('1231-03')+TB('1131')`；其余三准则 `TB('1221')` |
| 全库 `checklist_responses` 中 `K1-2-*` 明细行 | **0 条**（8 个项目全空） |
| `tb_aux_balance` 科目 1221 可用数据 | 项目 `2aa00f57`：客户 2857 / 成本中心 2353 / 保证金类别 1638 / 职员 505 / 经营类往来款 433 行 |
| K1 是否有 `import-aux-balance` 端点 | **无**（D1/D3/D5/D6/D7/F1/G7 均有） |
| 后端 `_K1_SPECS` item_id vs 前端真实键 | K1-2 `K1-2-rows` vs `K1-2-detail-rows`；K1-5 `K1-5-rows` vs `K1-5-large-rows`；K1-7 `K1-7-rows` vs `K1-7-stage-rows`；K1-8 `K1-8-rows` vs `K1-8-bad-debt-calc` —— **4 处不一致** |
| `defaultStageMovements()` 行集 | 13 行（含 `第一阶段→第二阶段` / `本年计提` / `汇兑差异`），源模板要 12 行（含 `上年年末余额在本期` / `本期转销`） |
| `defaultBalanceStageMovements()` 行集 | 11 行，**两对重复标签**（`—转入第三阶段`×2、`—转回第一阶段`×2），源模板 10 行 |
| K1 `_note_texts` 是否带 `title` | **否**（`noteTextRows` 只产出 `{section, text}`）→ 附注正文渲染英文键 |
| 附注汇总表「其他应收款」推送方 | **无**（K1-1 已算出 `fs_reconciliation`，F8-1~F8-4a 校验预设全落此表） |
| K1 公式预设块数 | 2（K1-1 审定表 + K1-2 AUX） |

## Requirements

### Requirement 1: K1-2 明细表可从四表库（辅助余额）一键/自动归集

**User Story:** 作为审计助理，四表入库后打开 K1，我希望 K1-2 其他应收款明细表已按往来单位自动归集出行，而不是面对一张空表手工敲上百行。

#### Acceptance Criteria

1. WHEN 四表已入库且 `tb_aux_balance` 存在科目 1221（或 `tb_source_codes.gross` 解析出的原始码）的辅助余额 THEN 系统 SHALL 提供 `POST /api/workpapers/{wp_id}/k1/import-aux-balance`，按**单一 aux_type**（先定维度防冗余双算）按 `aux_name` 归集出 K1-2 明细行。
2. WHEN 归集写入 THEN 写入的 item_id SHALL 为 `K1-2-detail-rows`（前端 8 个消费方的真实键），行字段名 SHALL 逐字对齐 `K1DetailRow`（`counterparty` / `nature` / `relatedParty` / `beginBalance` / `endBalance` / `agingPrior` / `agingCurrent` / `agingAudited` / `stage` / `badDebtProvision` / `netValue` / `voucherNo` / `conclusion` / `remark`）。
3. WHEN 归集时项目已登记关联方（`related_party_registry`）THEN 名称命中的行 SHALL 置 `relatedParty='是'`，未命中置 `'否'`。
4. WHEN 归集时 THEN 行的 `nature` SHALL 由科目/辅助项名称按与后端 render 同源的规则分类（备用金 / 保证金、押金 / 往来款 / 其他），不得把全部行落成「其他」。
5. WHEN K1-2 已存在同名往来单位的行 THEN 该单位 SHALL 不重复导入（**手工优先**，逐字不覆盖）。
6. WHEN 归集出的账龄无法从辅助余额判定 THEN 金额 SHALL 整笔落**项目账龄配置的首档**，并在返回消息中明确提示「请按实际账龄调整」。
7. WHEN 打开 K1 且 K1-2 为空表 THEN 前端 SHALL 自动触发一次归集（空表判定 + fail-open，失败不打断页面），非空时 SHALL 不触发。
8. WHEN 无 1221 辅助余额数据 THEN 端点 SHALL 返回 `imported_count=0` 且不写库（宁缺勿造）。

### Requirement 2: K1-3 坏账准备明细可从四表库（备抵科目叶子）预填

**User Story:** 作为审计助理，我希望 K1-3 的期初/本期计提/转回不用手抄总账，而是从四表库备抵科目叶子直接带出。

#### Acceptance Criteria

1. WHEN 备抵科目（`tb_source_codes.provision`，实证 `1231.03`）在 `tb_balance` 有叶子数据 THEN render SHALL 产出 K1-3 的 transient seed（期初审定 / 本期计提 / 本期转回 / 期末账面）写入 `responses_snapshot`，前端零改动即可消费。
2. WHEN 备抵叶子净增（贷方增加）THEN 差额 SHALL 归入「本期计提」；净减 THEN 归入「本期转回」，保证 roll-forward 自洽（期初 + 计提 − 转回 = 期末）。
3. WHEN `K1-3-baddebt-rows` 已有手工数据 THEN SHALL 不 seed（手工优先）。
4. WHEN 依赖缺失（无 active 数据集 / 查询异常）THEN SHALL fail-open 返回与改动前逐字等价的输出。
5. WHEN 备抵侧反解退化为宽前缀 `1231` THEN SHALL 叠加名称过滤（`provision_exact=False` 才生效），不得把应收账款坏账算进 K1。

### Requirement 3: K1 导入导出 item_id / 字段名与前端存储键一致

**User Story:** 作为审计助理，我导出 K1-2 模板、填好再导入，希望数据真的出现在界面上。

#### Acceptance Criteria

1. WHEN 后端 `_K1_SPECS` 声明各 sheet 的 `item_id` THEN 该键 SHALL 与前端实际读写键一致：K1-2 → `K1-2-detail-rows`、K1-5 → `K1-5-large-rows`、K1-7 → `K1-7-stage-rows`、K1-8 → `K1-8-bad-debt-calc`。
2. WHEN K1-2 导出/导入映射字段 THEN `field_keys` SHALL 用 `beginBalance` / `endBalance`（而非 `openingBalance` / `closingBalance`）。
3. WHEN 键名变更 THEN ACNR 清单（`backend/data/acnr/sources/k_cycle_ie_manifest.yaml`）SHALL 同步更新。
4. WHEN 导出模板后立刻用导入校验器解析 THEN SHALL 往返自洽（不得出现「导入自家导出的模板必然失败」）。
5. WHEN 键名变更 THEN SHALL 有守卫断言「后端 specs item_id ⊆ 前端源码出现的 item_id 字面量集合」，并含反向自检防守卫空转。

### Requirement 4: 附注汇总表「其他应收款」由 K1-1 财务报表核对区推送

**User Story:** 作为编制附注的人，我希望 §五、8 / §八、9 顶部的汇总表（应收利息 / 应收股利 / 其他应收款 / 合计）自动有数，而不是手填。

#### Acceptance Criteria

1. WHEN K1-1「与经审计的财务报表核对」区有值（`fs_reconciliation` 的 `interest` / `dividend` / `report_total`）THEN 同步载荷 SHALL 推送附注汇总表「其他应收款」，行为 应收利息 / 应收股利 / 其他应收款（国企：其他应收款项）/ 合计。
2. WHEN 推送该表 THEN 列 SHALL 逐字对齐附注模板（上市 `项目` / `期末余额` / `上年年末余额`；国企 `项目` / `期末余额` / `期初余额`），且标签列打 `flat`。
3. WHEN 三个明细行之和与合计行不等 THEN 底稿侧勾稽面板 SHALL 报异常（对应校验预设 F8-48）。
4. WHEN K1-1 该区无值 THEN SHALL 不推送空表（条件表语义），且不进 `_removed_table_keys`（该表可能由 G2/G3 应收利息/股利底稿承载）。

### Requirement 5: 三阶段变动表行集按源模板重建（坏账准备 + 账面余额，两处）

**User Story:** 作为编制附注的人，我希望三阶段变动表的行名与源模板一致，能直接作为交付物，而不是「第一阶段→第二阶段」「汇兑差异」这种底稿内部叫法。

#### Acceptance Criteria

1. WHEN 构造坏账准备三阶段变动行 THEN 行集 SHALL 为源模板 12 行：`上年年末余额`（国企 `期初余额`）/ `上年年末余额在本期`（国企 `期初余额在本期`）/ `--转入第二阶段` / `--转入第三阶段` / `--转回第二阶段` / `--转回第一阶段` / `本期计提` / `本期转回` / `本期转销` / `本期核销` / `其他变动` / `期末余额`（国企破折号为全角 `—`，源 xlsx 实证）。
2. WHEN 构造国企账面余额三阶段变动行 THEN 行集 SHALL 为源模板 10 行：`期初余额` / `期初余额在本期` / `—转入第二阶段` / `—转入第三阶段` / `—转回第二阶段` / `—转回第一阶段` / `本期新增` / `本期终止确认` / `其他变动` / `期末余额`。
3. WHEN 重建行集 THEN SHALL 不存在**重复行标签**（现状两对重复），且六种阶段两两迁移 SHALL 折叠进源模板的 4 个迁移行（转入二 / 转入三 / 转回二 / 转回一）。
4. WHEN 存在历史持久化数据 THEN 迁移 SHALL 按 `key` 对齐（`opening` / `closing` / `provision` / `reversal` / `writeoff` / `other` 等键不变），已录金额不得丢失；被折叠的迁移行金额 SHALL 按方向合并进目标行。
5. WHEN 变体为上市 THEN 首两行标签 SHALL 用「上年年末余额」口径；国企 SHALL 用「期初余额」口径（源 xlsx R93/R94 vs R64/R65）。
6. WHEN 行集含 `本期转销` THEN 勾稽 SHALL 可计算 `期初 + 本期计提 − 本期转回 − 本期转销 − 本期核销 + 其他变动 = 期末`（校验预设 F8-8）。

### Requirement 6: 附注两版列头 / 行标签逐字对齐源模板

**User Story:** 作为编制附注的人，我打开 §五、8 / §八、9 的每个 TAB 页签，希望看到与源模板逐字一致的表头与行名。

#### Acceptance Criteria

1. WHEN 上市「按账龄披露」THEN 列 SHALL 为 `账 龄` / `期末数` / `上年年末数`（源 R7），行尾 SHALL 为 `小  计` / `减：坏账准备` / `合  计`（源 R18/R19/R20，双空格）。
2. WHEN 上市「按款项性质披露」THEN 两级父表头 SHALL 为 `期末数` / `上年年末数`（源 R22），叶子列 `账面余额` / `坏账准备` / `账面价值`，合计行 `合  计`（源 R28）。
3. WHEN 上市三阶段快照 6 表 THEN 标签列 SHALL 为 `类 别`（源 R32，单空格），末列 SHALL 为 `理由`，ECL 率列表头按阶段区分（第一阶段 `未来12个月内的预期信用损失率(%)`；第二/三阶段 `整个存续期预期信用损失率（%）`）。
4. WHEN 上市「本期实际核销的其他应收款情况」THEN 标签列 SHALL 为 `项  目`（源 R113，双空格）。
5. WHEN 国企 ECL 两表（`其他应收款项坏账准备计提情况` / `其他应收款项账面余额变动`）THEN 列头 SHALL 为源模板全称 `第一阶段未来12个月预期信用损失` / `第二阶段整个存续期预期信用损失（未发生信用减值）` / `第三阶段整个存续期预期信用损失（已发生信用减值）` / `合计`（源 R63 / R77），不得截断成「第一阶段」。
6. WHEN 国企「由金融资产转移而终止确认的其他应收款项」THEN 第 3 列 SHALL 为 `与终止确认相关的利得或损失（损失以“-”填列）`（源 R111）。
7. WHEN 国企「涉及政府补助的应收款项」THEN 标签列 SHALL 为 `单位名称（注：政府补助的发文单位）`（源 R126，换行改为括注、纯文本无 HTML）。
8. WHEN 国企「按坏账准备计提方法分类披露其他应收款项」THEN 标签列 SHALL 为 `类  别`（源 R19，双空格），合计行 `合  计`（源 R26），比例列合计位 SHALL 允许 `——`。
9. WHEN 任一表列头被修订 THEN 修订 SHALL 同时落在**附注模板 `columns`（seed 路径）与同步载荷 `columns`（推送路径）两处**，且单级表标签列必须显式 `flat`。
10. WHEN 修订列头 THEN `key` SHALL 保持既有中文数据键不变（只改 `label` / `group`），避免整表数据丢落点。

### Requirement 7: 动态插行区域识别与补齐

**User Story:** 作为审计助理，源模板写「可无限量添加行」或留空白行的地方，我希望底稿里能自由增删行，而不是被固定行卡住。

#### Acceptance Criteria

1. WHEN 源模板某区块标注「可无限量添加行」或预留空白数据行 THEN 底稿对应区块 SHALL 支持动态增删行。涉及位置：上市 R26-R27（按款项性质）、R34-R38 / R43-R47 / R53-R57 及三张上年年末表（三阶段明细子行）、R107-R109（转回明细）、R117-R119（重要核销）、R147-R149（终止确认）、R155 / R158（继续涉入资产/负债）、R138-R140（政府补助）；国企 R24-R25 / R33-R34（按计提方法分类）、R40-R41（单项计提）、R59-R60（其他组合）、R93-R94（转回）、R99-R100（核销）、R112-R114（终止确认）、R119 / R122（继续涉入）、R127-R129（政府补助）。
2. WHEN 新增需命名的动态行 THEN SHALL 先 `ElMessageBox.prompt` 输入名称再创建，撞名 SHALL 拒绝。
3. WHEN 模板 seed 含占位说明行（如「可无限量添加行」）THEN 该行 SHALL 不作为数据行留在 `rows` 里，语义移入 `guidance`。
4. WHEN 动态行被删除 THEN 同步载荷 SHALL 整表覆盖推送（不留残行）。
5. WHEN 上市 ⑦「资金集中管理」在源模板只有文字 THEN SHALL 只保留文本域，不得凭空造表。

### Requirement 8: 账龄枚举（3 年段 / 5 年段 / 自定义）全链贯通

**User Story:** 作为项目负责人，我把项目账龄配置改成 3 年段后，希望 K1-1 / K1-2 / 两个披露表 / 附注的账龄档位全部跟着变，不留空行也不丢金额。

#### Acceptance Criteria

1. WHEN 项目账龄配置为 3 年段 THEN 上市①「按账龄披露」、国企账龄表、国企「账龄组合」表 SHALL 各只渲染 3 个数据档 + 结构行，不得出现空档行。
2. WHEN 项目账龄配置为自定义 N 段（2 ≤ N ≤ 10）THEN 各表数据档数 SHALL 等于 N。
3. WHEN 账龄配置变更 THEN 已录金额 SHALL 按段 key 保留（`remapRowAgingData` 口径），不得静默清零。
4. WHEN 上市①「1年以内」下有月度细分行（源 R9/R10 `其中：0-X个月` / `X-Y个月`）THEN 该细分区 SHALL 可增删行且可改名，并给出「1年以内小计：」行（源 R12）。
5. WHEN 细分行存在 THEN 勾稽 SHALL 校验「细分行之和 = 1年以内」（期末 / 上年年末各独立）。
6. WHEN 同步到附注 THEN 账龄行标签 SHALL 走 `disclosureAgingLabels` 单一真源（国企首档 `1年以内（含1年）`，上市首档 `1年以内`），禁写字面量。

### Requirement 9: `_note_texts` 中文标题与说明段落落点齐备

**User Story:** 作为编制附注的人，我希望附注正文段落有中文小标题，且源模板要求的每段说明都有地方填。

#### Acceptance Criteria

1. WHEN 推送 `_note_texts` THEN 每条 SHALL 带中文 `title`，不得让后端回退到英文 `section` 键（现状渲染成 `【listed-audit-note】`）。
2. WHEN 某段文字为空 THEN SHALL 过滤掉不推送；全部为空时 SHALL 不产生 `_note_texts` 键。
3. WHEN 源模板要求某段说明 THEN 底稿 SHALL 有对应文本域。逐条覆盖：上市 R59（本期账面余额显著变动）、R60（计提金额及信用风险显著增加依据）、R111（转回表注）、R121-R122（核销说明）、R133-R135（资金集中管理）、R142-R143（政府补助说明）、R145（终止确认说明）、R152 / R160（继续涉入说明）、R49 / R80（第二阶段「不存在」二选一文字）；国企 R88（账面余额显著变动）、R89（计提依据）、R96（转回表注）、R124（继续涉入说明）。
4. WHEN 文本域被新增 THEN 后端 `review_dialog._SECTION_PROMPTS` SHALL 有对应 prompt（≥20 字、写明源模板口径、含「不得虚构」约束），且 AI 调用走 `POST /api/workpapers/{wpId}/ai/generate-text`（`context` 为 `dict[str,str]`）。
5. WHEN 文本域清单变更 THEN SHALL 有守卫交叉校验「`sectionOrder` ⊆ 文本域键集 ≡ 标题映射键集」并断言抽取结果非空。

### Requirement 10: 底稿当页公式管理的公式预设补齐

**User Story:** 作为审计助理，我在 K1 各 sheet 的公式管理里，希望能看到该页可用的取数公式预设，而不是只有 K1-1 / K1-2 两页有。

#### Acceptance Criteria

1. WHEN 打开 K1-1 审定表的公式管理 THEN SHALL 含原值 / 备抵 / 应收股利 / 应收利息四类 `TB()` 预设与跨底稿 `WP()` 预设。
2. WHEN 打开 K1-3 坏账准备明细的公式管理 THEN SHALL 含 `TB('1231-03','期初余额')` / `TB('1231-03','期末余额')` 预设；**该块禁含 `WP()`**（防循环，明细是被引用方）。
3. WHEN 打开 K1-5 / K1-7 / K1-8 / K1-10 的公式管理 THEN SHALL 各有对应块（大额分析 / 三阶段划分 / 坏账测算 / 长期未收回），取数来源为 `WP('K1','明细表K1-2',…)` 或 `TB()`。
4. WHEN 预设入库 THEN 条目 SHALL 归入 `page_key='workpaper:K1'`，`formula_type` 合法，且 `cell_ref` 在同一 sheet 内不重复（`convert_prefill_presets` 会按 `page_key+cell_ref` 去重，撞键即静默丢弃）。
5. WHEN 校验公式 THEN SHALL 通过 prefill 引擎词汇表校验（`validate_formula` 返回空列表 = 合法）。
6. WHEN 新增预设块 THEN SHALL 有守卫断言块归属、类型、K1-2/K1-3 无 `WP(`，并含反向自检。

### Requirement 11: 守卫与零回归

**User Story:** 作为维护者，我希望这次对齐被守卫钉死，后续 K2~K13 沿用同一范式时不会又漂移。

#### Acceptance Criteria

1. WHEN 运行 `fix_note_k_complex_structure.py --check` THEN 5 个章节 SHALL 全部 0 欠账，且 `--dry-run` 幂等报 0 处变更。
2. WHEN 运行 K1 结构守卫 THEN SHALL 做**三向比对**：openpyxl 直读源 xlsx ↔ 附注模板 `headers`/`rows` ↔ 同步载荷 `columns`，覆盖 R6 所列全部表，并含反向自检（抹掉 columns / 塞回假行必须打红）。
3. WHEN 运行前端契约 `k1NoteSubtableContract.spec.ts` THEN P1~P6 SHALL 全量真断言（`columnsPending` 保持为空），并新增「三阶段变动表行标签逐字对齐模板 rows」断言。
4. WHEN 运行既有 K1 后端/前端测试 THEN SHALL 零回归（含 `four_table` 共享件的 D1/K2 既有消费者）。
5. WHEN 共享件 `pick_aux_type` 被提升 THEN F1 / G7 既有行为 SHALL 逐字不变（薄壳委托 + 既有测试全绿）。
6. WHEN 交付 THEN CI SHALL 有 job 覆盖本 spec 的后端守卫与前端契约。

### Requirement 12: 端到端实测

**User Story:** 作为用户，我要看到真实项目上「四表入库 → 底稿有数 → 推送附注 → 附注有数」跑通。

#### Acceptance Criteria

1. WHEN 在真实项目（`2aa00f57`，1221 辅助余额 2857 行）打开 K1 THEN K1-2 SHALL 自动归集出行，且行数 / 期末合计 SHALL 与 `tb_aux_balance` 归集口径一致。
2. WHEN K1-2 有数后 THEN K1-1 审定表账龄 / 性质区块、两个披露表的账龄 / 性质 / 前五名 SHALL 级联出数。
3. WHEN 点击披露表「同步到附注」（或触发自动同步）THEN 附注 §八、9（国企侧活体）SHALL 落库对应子表，`last_sync_at` 前移，`_column_groups` 与源模板一致，文本段渲染中文标题。
4. WHEN 实测完成 THEN 测试数据 SHALL 按实测前快照逐字复原，并在 tasks.md 记录实测结论与复原证据。
5. WHEN 上市侧无活体项目（8 个项目 `entity_type` 全 soe）THEN SHALL 显式记录该限制，不得伪造实测结论。

## Glossary

| 术语 | 含义 |
|------|------|
| 源模板 | `backend/wp_templates/K/K1 其他应收款.xlsx`（运行时权威副本），本 spec 的唯一结构裁决者 |
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张导入表 |
| 叶子科目 | `tb_balance` 中不存在 `code + '.'` 前缀子行的科目；叶子和 == 父科目额 |
| 备抵 | 坏账准备科目侧（K1 实证标准码 `1231-03`、原始码 `1231.03`） |
| 级联根 | 一个循环里被其他 sheet 取数的最上游明细表（K1 是 K1-2 明细表） |
| transient seed | 只写进 render 的 `responses_snapshot`、不落库的预填；下游若读持久化则无效 |
| seed 路径 | 新建项目 / 重新生成附注时走附注模板 `columns` 的渲染路径 |
| 推送路径 | 底稿「同步到附注」时走同步载荷 `columns` 的渲染路径（真实用户路径） |
| 孤儿子表 | 载荷推送的表名与附注模板 `tables[].name` 不一致 → 附注 TAB 永空且数据丢失 |
| 三向比对 | openpyxl 直读源 xlsx ↔ 附注模板 headers/rows ↔ 同步载荷 columns 的守卫口径 |
| F8-* | `note_check_preset_formulas.json` 中 K1 两个附注章节的 139 条勾稽校验预设 |
| 动态插行区域 | 源模板标注「可无限量添加行」或预留空白数据行、底稿需支持增删行的区块 |
| 账龄枚举 | `useAgingConfig` 的 `THREE_YEAR` / `FIVE_YEAR` / `CUSTOM` 三种项目级账龄段配置 |
