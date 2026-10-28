# 设计：OnlyOffice 重算公式格不再当成篡改

## §0 结论先行

- 合并核心对「受保护字段在 OO 一侧变了值」不再一律判篡改：**公式证据完好 + 输入一致** ⇒ 采纳 OO 的重算结果；其余照旧记受保护冲突。新规则只把现在的冲突变成采纳，现在采纳的不会变成冲突（R1.7）。
- 公式证据 = 提取时已经读到的公式文本，归一成与行号无关的签名，随 projection 带进合并（不进摘要）。
- 采纳的重算值同时进入 store 镜像，D2-1 审定表 / 发布到试算表等下游读到新值。
- 前端「期末余额 = 期初审定 ± 发生额」七张表（另含 D1-7 复用 D1-2 口径的一处）与权威模板「期初未审 ± 发生额」对齐，D5-2 期末审定改取期末余额列，避免表单与 OO 来回改值；全仓扫同类后，D2-3 / G2-3 / G5-3 / K1-3 坏账准备滚动表与 G2-2 一并改（§8）；真库影响 0 行。

## §1 现状 grep 确认

| 位置（现算行号） | 现状 | 本 spec |
|---|---|---|
| `merge.py` 1506–1542 | 受保护字段 `b、i 都在且 i≠b` ⇒ 先过 R10 容差（697–735，按分），否则 `conflict_protected`、merged 取 current | 改：插入公式证据判定与输入一致复核 |
| `merge.py` 1101–1122 / 1164–1171 | `FieldVerdict` 无「采纳重算」；`auto_merged_keys` 只收 took_incoming / both_sides_agree | 加 `took_recomputed` 并计入 |
| `merge.py` RETIRED_DEFERRALS（cleared_field_view 那条） | 登记 R17 视图消费 `MergeOutcome.verdicts` | 同模块加第二个视图，改写该条 consumer / reason |
| `excel_extract.py` 3722 | `_collect_fields` 把读到的公式文本记进 `formula_inventory`；`data_only=False` 视图只保留 `=` 开头的字符串（2996–3014，openpyxl 已把共享公式按格展开） | 同处顺带算签名 |
| `excel_extract.py` 2714–2790 | `_classify_protected_tamper` 产出 `protected_findings`，生产上唯一读者 `excel_rematerialize` 无调用方（只有 task37/38 测试） | 不动；合并不读 findings |
| `adapters/excel.py` 705–770 / 245–266 | `extract` 逐 binding 提取后 `_merge_projections` 只合并 values / row_keys，公式清册丢弃；`_baseline_pair` 只算主 binding | 合并时并上各 binding 的签名 |
| `adapters/base.py` 259–300 | `FieldValue.is_protected` = mode ∈ {formula, auto_source}；`Projection` 只有 values / row_keys | `Projection` 加 `formula_signatures`（compare=False） |
| `content_mutation.py` 2494–2522 | projection 摘要只序列化 values / row_keys | 不动（签名天然不进摘要，加守卫） |
| `oo_to_html.py` 2209–2233 / 2366–2373 / 2641–2645 | 三方提取 → `merge_projections(base, current, incoming)`；提交后把 R17 视图交给 store 镜像 | 镜像前再套一层重算视图 |
| `d2_bidirectional_bridge.py` 853–856 等 22 个模块 27 处 | store 合并一律跳过 `fv.is_protected` | 不动，靠视图里的值类型放行 |
| `template_skeleton_baseline.py` 184 | 骨架行「是否用户内容」跳过受保护字段（文档写的是「公式缓存值不算用户内容」） | 改为按 mode 跳过公式字段 |
| `excel_row_shift.py` 802 | `_rewrite_formula_refs` 是全仓唯一 A1 改写入口（Property 27） | 只读调用，不改 |
| `excel_materialize.py` 1754 | 公式字段写 `<v>`、保留 `<f>` | 不动 |
| `useD2Detail.ts` 135–149 | `endBalance = priorAudited + 借 − 贷`；模板 `Q = E + O − P` | 改；另 6 处同族 |
| `useD2Adjudication.ts` 165–176 | D2-1 SUMIF 读 store 里存的 `currentUnadjusted`（S 列），`publishToTb` 用它发布 | 不动，store 新值即生效 |

## §2 根因与实证（2026-10-25，只读）

**真库受保护冲突**（`working_paper_sync_conflict` ⋈ application）：

| entry | 策略 | 条数 | 保存次数 | 其中「base = current、incoming ≠ base」 |
|---|---|---|---|---|
| D2 应收账款 | read_only_formula | 333 | 5 | 333 |
| D4 营业收入 | read_only_formula | 17 | 8 | 17 |
| D4 营业收入 | read_only_masked_cell | 1 | 1 | 1 |

最新一条（【测试】项目 `7cdfbe36`）：`明细表D2-2!Q/S/AB`，base 1000 / current 1000 / incoming 2500 —— 用户只改了借方发生。

**OO 是否改公式文本**：5 组真实 base / incoming（【测试】3 组、和平药房 2025、重药安徽 2025），9 张 sheet 逐格比对 openpyxl 展开后的公式文本，Q/S/AB 与其余受管公式全部逐字相同；OO 会把公式重写成共享公式（`t="shared"` 550 → 711），展开后无差异。唯一差异是重药安徽一组在可编辑的账龄列 I13/I14 多了结构化引用公式（用户输入），与受保护字段无关。

**store 镜像丢值**：只读探针（假 session 截住写库）把真库 store 投影的公式字段值 +0.37 后交给生产 `mirror_projection_into_store`：现状 0 个写入；同一视图把这些值包成「不受保护」后全部写入 —— D2（和平 2024 / 2025 / 重药安徽：2268 / 2187 / 3780 个）、H1（2）、D3（4）、D5（4）、D6（36）、H9（12）。store 本就不存公式字段的 provider（G7~G14、H8 等）两种情况都不写。

**前端与模板口径**：D2-2 期末余额前端用期初审定 H、模板用期初未审 E；同族共 7 处（§8）。七张表的真库 store 共 2760 行，期初调整（AJE/RJE）全部为 0 ⇒ 两种口径现在算出同一个数。

## §3 ADR-1：修订 AC 6.6 / Property 24（不改归档）

- 原文（`_archive/17-…/workpaper-html-onlyoffice-bidirectional-writeback-closure` requirements.md:155、design.md:923–961 / 1585–1590）：OO 修改 formula / auto-source 单元格时 current 公式与值不变，并生成 protected conflict。R10（`_archive/42-…/design.md:109`）加了按分容差。
- 问题：原文把「OO 改了这一格」与「OO 重算了这一格」当成同一件事。前者是用户覆盖公式结果；后者是公式在新的输入上算出的新结果，正是用户要的。
- 修订：受保护的**公式字段 / 公式遮罩格**在公式证据完好且输入一致时，incoming 值即公式结果，采纳；公式被换成数值、被改写、数值格被写入公式、只读数值格被改值、没有证据、输入不一致 ⇒ 仍按原文。自动取数格不在修订范围（OO 不重算它）。
- 归档按惯例不回填；本条即修订记录，归档索引在 INDEX 本 spec 行注明。

## §4 公式签名

`formula_signature(text, *, own_row) -> str`（新模块 `formula_recompute_evidence.py`）：

1. 调 `excel_row_shift._rewrite_formula_refs(text, remap=…)`：remap 把 `own_row` 映射为哨兵行 1048577（Excel 最大行 + 1，真实引用不可能用到），其余行原样；再把输出里的哨兵数字换成 `{r}`。
2. 继承改写器的四类防误命中：字符串字面量、跨表前缀（`current_sheet=None` ⇒ 一切带表名的引用逐字不动）、带数字的函数名（`LOG10(`）、`&quot;` 实体。
3. `$` 锁定照样换（插行时 OO 也会推动锁定行）：`$E$13`@13 → `$E${r}`。区间逐端点换：`SUM(B12:M12)`@12 → `SUM(B{r}:M{r})`；`SUM(E13:E16)`@12 原样。
4. 原文已含哨兵数字串 ⇒ 不归一、原样返回（只会多出冲突，不会少）。

效果：同一列的公式在行增删后签名不变（`=E13+O13-P13`@13 与 `=E14+O14-P14`@14 都是 `=E{r}+O{r}-P{r}`）；引用别的行、别的表、结构化引用的公式在行号变化时签名会变 ⇒ 这些公式所在行如果值也变了，仍按现状报冲突（不比现在差）。

## §5 证据通道

- `Projection.formula_signatures: Mapping[str, str] | None = field(default=None, compare=False, repr=False)`：stable key → 签名，只含读到公式的受管格（任何 mode）。`None` = 来源不提供证据。
- `excel_extract._collect_fields` 在记 `formula_inventory` 的同一处算签名（坐标已知，`own_row` 取自坐标），两个 `extract_projection` 分支把它挂到各自产出的 projection 上。
- `ExcelSyncAdapter._merge_projections` 合并各 binding（主表 + 兄弟表）时并上签名；转置表（D4-29 / D4-12 / G4-9 / G5-9 / G6-11）的 part 没有签名 ⇒ 这些键无证据、按现状。
- 不进摘要：`_projection_payload` 只序列化 values / row_keys，不需改；加守卫「带签名与去掉签名的摘要相同」。不参与相等比较（`compare=False`），P8 复用 / P9 缓存命中原样带着。
- 被否：在适配器上挂「最近一次提取的证据」（有状态、跨线程不可靠）；另开 `extract_with_evidence` 接口（三方提取、P9 缓存、冲突裁决重跑都要改，而 projection 本来就是「从这份文件读出的东西」）。

## §6 合并规则

记号：b / c / i = base / current / incoming 信封；「重算策略」= `read_only_formula`、`read_only_masked_cell`。

```text
逐字段真值表（顺序不变，只在两处插入）：
  受保护 ∧ b、i 都在 ∧ i ≠ b：
    重算策略 ∧ i ≈ b（R10）          ⇒ kept_current（不变）；c ≠ b 时记入 current_only
    证据 = 完好（两侧签名都在且相同） ⇒ took_recomputed，merged = i，记入候选
    否则                             ⇒ conflict_protected（原因按证据分类，无证据时原因逐字不变）
  OO 新增行（行生命周期 added_by_incoming）∧ 公式字段 ∧ 重算策略 ∧ b、c 都缺、i 在：
    i 的签名 ∈ base 同一列的签名集合 ⇒ took_recomputed（merged = i，同现状），记入新增行候选
  i == b（kept_current）且 c ≠ b ⇒ 记入 current_only
循环之后：
  有候选 ∧（current_only 非空 ∨ 已有任何冲突 ∨ 有搁置的行 / 键）：
    候选 ⇒ conflict_protected（原因：输入不一致，点名第一处差异）、merged = c
    新增行候选 ⇒ took_incoming（merged 不变）
```

- 证据分类（`classify_formula_evidence`）：任一侧 projection 不带签名 ⇒ 无证据；两侧都有且相同 ⇒ 完好；只有 base 有 ⇒ 公式被换成数值；都有但不同 ⇒ 公式被改写；只有 incoming 有 ⇒ 数值格被写入公式；都没有 ⇒ 只读数值格被改值。
- 输入一致的判据零额外比较：「合并结果 ≠ OO 一侧」只可能来自 kept_current 且 c ≠ b（在真值表里已算出 `same_current_base`）、任何冲突、或被搁置；took_incoming / both_sides_agree / row_deleted 按构造与 incoming 相同。
- 为什么是全局而不是逐公式依赖：没有公式依赖解析器，逐公式只能靠签名猜依赖；输入不一致只在「OO 编辑期间服务器侧另有保存」时出现，罕见，且结论与现状相同（冲突、保留服务器值）。代价：一张表里任何一处冲突都会让同次保存的重算候选一起成为冲突 —— 与现状相同，不更差。
- 冲突裁决：候选只在零冲突时被采纳，因此 `apply_resolutions` / 裁决重跑永远看不到「已采纳的重算 + 待裁决冲突」并存；ConflictRecord 的不变式（protected ⇒ keep_current）不变。
- 不变的：自动取数精确比较；可编辑字段规则；R10；公式文本变了而值没变不报（插行会改他行引用的文本，报了只会增加伪冲突）；`projection_requires_client_refresh`（采纳后 settled = incoming，自然不要求重载）。

## §7 store 与下游

- `cleared_field_view.py` 加 `store_view_with_recomputed_formulas(view, *, merge)`：verdict 为 `took_recomputed` 且 mode 为 formula 的键换成 `RecomputedFieldValue`（FieldValue 子类，`is_protected` 恒假，mode 仍是 formula）；无可换时原样返回同一对象。遮罩格本就是 editable mode，store 合并函数已会写它。
- `oo_to_html._apply_committed`：R17 视图之后再套这一层，镜像拿到的仍是名为 `store_view` 的视图（R17 的 AST 守卫不变）。发布的 content version 不受影响。
- 各 provider 不改：store 里有这个字段的（D2 的 `endBalance / currentUnadjusted / currentAudited` 等）写入；按自身规则过滤公式字段的（如 B60 按 `MANAGED_FIELD_SPECS` 的 mode）照旧不写。
- `template_skeleton_baseline.pure_template_skeleton_rows`：按 mode 跳过公式字段（不再借道 `is_protected`），否则重算值会被当成「用户往模板空行里填了内容」，R12 的骨架行问题会回来。
- 登记表：`RETIRED_DEFERRALS` 里 cleared_field_view 那条的 consumer / reason 补第二个函数（同一模块不得重复登记）。

## §8 前端期末余额族（R4）

| 表 | 文件:行 | 现在 | 模板 |
|---|---|---|---|
| D1-3 | `useD1DetailCustomer.ts:84-85` | 期初审定 + 增 − 减 | `J = D + H − I`（期初未审） |
| D1-2 | `useD1DetailCategory.ts:100` | `calcCurrentUnadjusted(priorAudited, …)` | `H = B + F − G` |
| D2-2 | `useD2Detail.ts:141` | `priorAudited + 借 − 贷` | `Q = E + O − P` |
| D3-2 | `useD3Detail.ts:141` | `calcEndBalance(priorAudited, 贷, 借)` | `O = E + N − M` |
| D5-2 | `useD5Detail.ts:137` | `calcEndBalance(F, 增, 减)` | `J = C + H − I` |
| D6-2 | `useD6Detail.ts:176` | `calcEndUnadjustedDebit(priorAudited, 借, 贷)` | `Q = G + O − P` |
| D7-2 | `useD7Detail.ts:149` | `calcCreditEndBalance(priorAudited, 贷, 借)` | `P = F − N + O` |
| D1-7「明细账(D1-2)」行 | `useD1MemoReconciliation.ts:495` | 同 D1-2（按 D1-2 口径重建） | 同 D1-2 |
| D5-2 期末审定 | `useD5Detail.ts:139` | `calcEndAudited(L, AJE, RJE)`（期末未审） | `O = J + N + M`（期末余额，不含被审计单位重分类 K） |
| D2-3 坏账准备 | `useD2BadDebt.ts` `recalcRow` | 期初审定 + 计提 + 其他增加 − 转回 − 核销 − 其他减少 | `K = B + SUM(F:G) − SUM(H:J)` |
| G2-2 | `useG2Detail.ts` `computeRow` | `calcDebitBalance(期初审定, 借, 贷)` | `H = C + F − G` |
| G2-3 坏账准备（明细行 / 合计行 / 跨表读取） | `useG2BadDebtDetail.ts` `computeAmounts` · `sumLeaves`；`g2CrossHelpers.ts` `computeClosing` | 期初审定 + 增 − 减 | `J = B + SUM(E:F) − SUM(G:I)` |
| G5-3 坏账准备（明细行 / 小计合计 / 两处跨表兜底） | `useG5BadDebtDetail.ts` `computeMovement` · `sumLeaves`；`g5CrossHelpers.ts` 兜底；`g5ListedDisclosureRows.ts` 兜底 | 同上 | `J = B + SUM(E:F) − SUM(G:I)` |
| K1-3 坏账准备 | `useK1BadDebt.ts` `recalcK1BadDebtMainRow` | 期初审定 + 增 − 减（期末账面） | `J = B + SUM(E:F) − SUM(G:I)` |

- 只改调用处的第一个参数（期初审定 → 期初未审；D5-2 期末审定：期末未审 → 期末余额）与注释，计算函数不动（`calc*` 是多处共用的通用函数）。期末余额是「账面滚动」，审定调整走期末 AJE / RJE 两列；用期初审定滚动会把上年审计调整算进「未审」，与试算表未审数对不上。F 循环已按「对齐致同源模板」统一过（`useF2*Formulas.ts` 文件头；F1-2 裁决 F1-H3：`useF1Detail.recalcRowFormulas` 的 `O = E + M − N`、`X = O + V + W`，D5-2 期末审定与后者同形）。
- 表中行号是改前的现算行号。
- 普查口径：子代理逐格比对 D1~F5 契约的本行公式（结果 `C:\Users\Administrator\ofr_probe\p4_scratch.md`，交付后删除，要点并入 §11）；G~N 只列了模板公式、未逐个比对前端（§11）。
- 触类旁通（实施期补）：全前端扫「期初审定名（prior / opening / begin… + Audited / Adjusted）作加减起点」（去注释、跨行表达式也认），78 处命中，多数是差额 / 净值 / 小计相加，滚动类逐个对照模板：表末五行是同一问题（只差起点、其余加减项与模板相同）；H1 / H2 / H6 / H8 的审定列滚动（审定期初 + 审定增减）与模板同形，不改；M2 / N1 是界面校验值、G4 / G2-1 / F4 的旧数据迁移、`shared/usePeriodAdjudication.ts`（唯一调用方 `CycleTabAdjudication.vue` 全仓零挂载）不改；D1-4 / D6-3 与几张审定表另有差异，登记 §11。真库：这五张表的 store 键 0 条。

## §9 影响面

- 规则对全部 Excel entry 生效（91 份生产契约，受管字段 3841，其中公式字段 641、遮罩格判定在运行时）：静态分析 514 个公式字段经字段链依赖可编辑字段、36 个依赖非受管格、67 个跨表。
- 已开启双向回写的 45 个 entry 中受影响 24 个：D2 明细 / D2 检查、D1、D4、F1、F2 ×4、F3、F4、F5、G6、H1、L1、L4~L8、M1、M5、M8、N4；A5-1 未定；G7、M9 及无公式字段的 K1 / J1 等不受影响。尚未开启的 32 个（G1/G2/G3/G5/G8~G14、H2~H6/H8/H9、D3/D5/D6/D7、E1、M2/M3/M6/M7/M10、N1~N3、B60）开启后同样受益。

## §10 被否决的方案

| 方案 | 否决理由 |
|---|---|
| 服务端按模板公式重算 | 需要公式求值器；与 OO / 前端形成第三个真源 |
| 受保护字段一律保留 current、不报冲突 | store 与已发布内容长期是旧值；每次保存都 `refresh_required` |
| 输入不一致时静默保留 current | 旧值会流进 D2-1 与发布到试算表而无人知晓；冲突至少让人看见 |
| 公式原文比较 | OO 插行会改写下方各行公式的行号 ⇒ 伪冲突 |
| 行身份重映射（引用 → 行 UUID） | 需要跨 sheet 的行身份表与区外行（合计行）偏移规则，复杂度远超收益；签名已覆盖同行公式这一主体 |
| 前端加载时修复并保存 | 打开即写库、逐组件实现；且救不了 OO 新增行 |

## §11 范围外 / 已知限制

1. **前端与模板口径其他不一致**（D1~F5 普查，未改，待拍板）：贴现利息按 360 天（D1-9、D5-4，模板 365）；差额方向相反（D1-15 `实际 − 应计`、D2-9 `实际 − 应计` 而模板 `审定余额 − 实际`）；D6-3 期末未审 / 期末审定与模板列不同；D1-4 坏账期末加减项不同；D7-6 方向相反；D1-7 背书 / 到期一次性填写而模板按状态公式；D2-10 前端按情景算加权；F4-6 联动行取 F4-2 审定期末；变动率边界（D1/D3/F4 分母为 0 时返回值不同）；D1-4 / D6-3 的期末未审除了起点（期初审定 vs 期初未审）还有加减项 / 引用列不同，未改起点，整式一并待裁；审定表 F3-1 / G3-1 / G10-1 的模板从明细表取期末未审，前端却按「期初审定 ± 本期借贷」推导（结构不同，非起点问题）。这些在新规则下表现为「值随最后保存的一侧变化」而不是冲突，涉及业务口径，逐条请用户裁决。G~N 的非滚动类公式（比例、测算、校验等）尚未逐个比对。
2. **篡改裁决后公式不还原**：物化把合并值写进 incoming 的 `<v>` 并保留 incoming 的 `<f>`，`intended_formulas` 生产上未传；用户在公式格敲了数字、裁决保留服务器值后，发布的文件里那一格仍是数字（代码阅读结论，未实测）。与本 spec 的重算路径无关，建议另立。
3. **转置表无证据**：五张转置 sheet 走 `phase5_transposed_sheet.extract_file`，不产签名 ⇒ 按现状。
4. **引用别的行 / 别的表的公式**在 OO 插行后签名会变（如 D4-9 占比 `C{r}/$C$24` 的合计行下移）⇒ 那次保存里值也变了的行仍报冲突（不比现在差）。
5. **三处「受保护」定义不一致**（`FieldValue.is_protected`、`contracts.PROTECTED_MODES` 含 cross_sheet、merge 的 `_protection` 不含 cross_sheet）：本 spec 不收敛，只在用到处按 mode 明确判断。
6. **通用期间审定表是死代码**：`shared/usePeriodAdjudication.ts` 的 `calcClosingUnadjusted` 按「期初审定 ± 借贷」算期末未审，但唯一调用方 `CycleTabAdjudication.vue` 全仓零挂载（只出现在 `components.d.ts`），无运行时影响；未改，建议随死代码清理一并删除。
7. **冻结契约文本与事实不符**：D1-3 契约 `review.reviewed_basis`（`phase5_d1_notes_receivable._REVIEWED_BASIS`，与磁盘契约逐字相等）写着前端 `G+H−I` 与模板 `D+H−I`「数值语义等价」——有期初调整时两者差 E+F，并不等价，这正是本问题长期没被发现的原因之一。冻结文本不改；同一句在 `phase5_d1_03_customer.py` 模块文档里已更正。

## §12 测试与验收

- 单测（新文件 `test_formula_recompute_evidence.py`）：签名表驱动（同行 / `$` / 区间 / 他行 / 跨表 / 字符串 / 结构化引用 / 带数字函数名 / 哨兵）、插行不变性；合并真值表（采纳 / 输入不一致 / 四类篡改 / 无证据 / 自动取数 / R10 / 新增行三种 / 遮罩格 / auto_merged_keys）；提取与适配器（真 D4 world：签名覆盖多个 binding、摘要不变、P9 命中带证据；在真 D4 文件上模拟 OO 重算 / 敲数字 / 改公式三种 incoming）；store 视图（真 D2 契约 + 真 D2 store 合并：重算值进 store、骨架行不进、未采纳时不换、AST 接线）。
- 修订既有判据：`test_merge_recomputed_formula_values.py` 的「差一分就是篡改」限定为「无公式证据时」，在文件里写明修订理由；其余既有受保护冲突判据（task14 / task37 / task38）构造的是无证据或篡改形态，预期不变，以实跑为准。
- 磁盘变异（隔离副本）：去掉输入一致复核、证据分类判反、签名不归一 / 全归一、适配器漏并兄弟表、签名进摘要、视图不换值 / 换了非公式字段、骨架判据回退、新增行不查同列公式族等，每条须打红。
- 真实历史冲突重放（只读）、浏览器实测、回归 —— 见 tasks.md。

## §13 实施记录（2026-10-25）

**代码**（行数按提交树现算）：新模块 `formula_recompute_evidence.py`；`merge.py` +66（1929 ≤ 1944）、`excel_extract.py` +14（4522 ≤ 4616）、`adapters/excel.py` +3（1071 ≤ 1078）、`adapters/base.py` +6、`cleared_field_view.py` +66、`oo_to_html.py` +6、`template_skeleton_baseline.py` +9；`phase5_d1_03_customer.py` 只改模块文档（§11 第 7 条）。前端 16 个文件只改 §8 表里的起点与注释（D 循环 8 个 composable + 触类旁通 8 个）；其中 G2-2 / G2-3 / G5-3 / K1-3 的模块文档原本写着「对齐致同模板」，起点却不符，已随改更正。计算引擎函数（如 `calcEndBalance(priorAudited, …)`）是通用 a ± b，参数名与引擎层用例标题沿用旧称呼，未改。

**测试**：新增后端 3 个文件 83 例（证据 43 / 合并 25 / 提取与 store 15），修订 `test_merge_recomputed_formula_values.py`（45 例）；`test_single_pass_artifact_equivalence.py` 的 P2 比较面加上公式签名（回归抓到，见下）。新增前端 `periodEndFromPriorUnadjusted.spec.ts` 16 例（D 循环 9 + 触类旁通 7），改写钉住旧口径的 10 处用例（D 循环 7、G2-3 1、G5-3 2，理由写在用例旁；G2-2 另有一条用例只改标题）。

**磁盘变异（隔离副本，sha256 逐字节还原）**：
- 后端 40 条，首轮 34 红、6 存活：搁置行没有冲突记录时不复核（M1e）、新增行不看 mode（M10c）、公式族不分列（E7）、静态区提取丢签名（X2）、store 视图放行非公式字段（V2）/ 放行 took_incoming（V2b）。补 6 条判据（搁置行无冲突记录、新增行遮罩格仍 took_incoming、他列同形公式、A5-1 静态区两例、视图只放行重算的公式字段）后第二轮 6 条全红。教训：存活的 6 条都是「同一判据只测了一种形态」。
- 前端 19 条（内存替换，不落盘）全红：D 循环 9 条（8 处逐处退回，D5-2 的 J / O 各一条）+ 触类旁通 10 条（D2-3、G2-2、G2-3 明细行 / 合计行 / 跨表、G5-3 明细行 / 合计行 / 两处跨表兜底、K1-3 各单独退回）。
- P2 比较面 2 条（比较不看签名 / 字段清单漏登记）全红。

**真实历史冲突重放**（真库只读事务 + 只读存储；当前契约 + 生产 binding 内核，逐 binding 走生产 `extract_projection`；偏离：`retain_identity_inventory=False`、旧文件没有的受管区逐个跳过并记录、current 取 base —— 这些冲突全部 b = c）：

| 保存 | 现存受保护冲突 | 旧规则重放 | 新规则 |
|---|---|---|---|
| D4 8 次 | 17（期间合计 11、D4-9 金额占比 3 / 数量占比 3） | 17 逐条复现 | 0 冲突，17 条 took_recomputed |
| D2 `7cdfbe36` | 3（Q / S / AB） | 3 复现 | 0 冲突，3 条 took_recomputed |
| D2 其余 4 次 | 276（81 / 33 / 108 / 54） | 0（浮点尾差，R10 已消除） | 0 |
| D4 `ee6667bc` | 1 | 0（D4-1 B 列在现行契约里是可编辑） | 0 |

- 14 次全部满足 R1.7：新冲突 ⊆ 旧冲突，冲突以外的合并值无一变化。T10 产生的冲突保存（`57412edb`）同法重放得到同样的 3 条与原因分类。
- 签名开销：D2 大表 2223~2247 个签名每次提取 11.9~14.7 ms（提取 1.21~1.32 s 的约 1%）；19~66 个签名的 < 1 ms。

**回归**：
- 后端：`tests/workpaper_sync` 全目录 + 4 个相关文件，在同一 HEAD（779d8b436）的两个隔离 worktree 里改前 / 改后各跑一遍，junit 逐条对比：16501 → 16584 例（+83 新增），失败 1937 / 错误 771 两边相同。只在改后失败的 1 例 —— `test_single_pass_artifact_equivalence::test_comparison_surface_covers_every_dataclass_field`：`Projection` 加了 `formula_signatures`，P2（链式与单趟物化反读逐字段等值）的比较面没跟上。这不是放宽守卫能解决的：签名决定重算能否采纳，两条物化路径反读出的公式也必须一致 ⇒ 比较面加上签名（有无 + 逐键）、非空转断言、再加一条「比较面真的比了签名」的判据；修后该文件两棵树都是同 2 例既有失败（D4-4 成受管 sheet 后的趟数 / entry 数，主工作树已由并发会话改基线）。只在改前失败的 1 例是真 OnlyOffice 引擎用例（x2t），与本次无关。
- 前端：D 相关 995 个文件失败 36 = 改前 36；G2 / G5 / K1 / D2 相关 514 个文件失败 6 = 改前 6（内存换回改前版本对照）；sync 目录 17 = 17。单区域 vue-tsc：注入 TS2322 能报出；其余报错都在未改动的行上（HEAD 既有：`useK1BadDebt.ts` 331 / 494、经 import 带进来的 `g4CrossHelpers.ts` 9 条、`useD5Detail.spec` 字面量、`useD7Detail` 事件名）或并发会话改动（`useD2Adjudication`）。
- golden digest 242 条不变；行数门 0 违规（`adapters/excel.py` 1071 ≤ 1078、`merge.py` 1929 ≤ 1944、`excel_extract.py` 4522 ≤ 4616）。

**浏览器实测**（经接口新建【测试】OO公式重算验收有限公司_2025，结束后经平台删除）：
- D2-2 一行：期初未审 1000、期初 AJE 200 / RJE 50、借 300 / 贷 100、重分类 30、期末 AJE 7 / RJE 3 ⇒ 期末余额 1200（旧口径 1450）、期末未审 1230、期末审定 1240，store 相同。
- 在线编辑把借方发生 300 → 500，OO 显示期末余额 1400；保存回表单：application applied、0 冲突；store 与表单为 1400 / 1430 / 1440，D2-1（该行设单项计提后）期末未审 1,430、审定 1,440。
- 再往期末余额格敲 9999 保存：3 条受保护冲突 —— 期末余额「公式被换成数值」，期末未审 / 期末审定「输入不一致」（OO 侧 10029 / 10039，保留 1430 / 1440）；横幅「在线编辑的改动没有合并进表单」。
- console 有 3 类 error，都不在本次改动的代码路径上（前端只改了计算参数）：Vite 依赖预构建过期（504 Outdated Optimize Dep + `en-gb` 动态导入失败）、Univer「column width is less than 0」×31、一次来源未定位的 422（之后 4 次整页加载均未复现）。未用改前代码在浏览器里对照。
- 清理：软删进回收站；删除前后逐表计数不变（按 project_id 18 张表、按 wp_id 3 张表），编辑锁 4 条均已释放、OO room 2 个均 closed。
