# Task 12 / C-11：G13 公允价值变动收益接入双向回写

commit `b3a6c5a6e`（17 文件，+2973 / −27）。九条 lane 的**第六条**。

## 一句话结论

G13-2 的模板受管区对应的是**派生汇总视图**，而 store 里存的是更细粒度的原始明细 ——
这是**载体层错配**，不是字段层错配。用户拍板选项 A：把前端原有的分类骨架**落库**成独立
store item 并受管它，工具明细保持 HTML-only 平台增强。附带三处推翻既有登记、四处首版判据
打红后的实测纠正，以及一个 resync 脚本从未生效的分支。

## 模板实测（`backend/wp_templates/G/G13 公允价值变动收益.xlsx`）

* 58,717 B · sha256 `fd5e5e9eeca7b392d59ca54beac51e96bb1575894113c0f3e69f05a234b0f099`
  · 8 sheets · **0 definedName**（与 slice 的 `authoritative_templates.files[5]` 逐字一致）
* 受管 sheet `明细表G13-2`：`max_row=34` / `max_column=12` / merged 8 个
* **两级表头 R9/R10**：
  * 横向组 `B9:D9`（本期数）· **`F9:J9`**（对应科目-公允价值变动）
  * 纵向合并 `A9:A10`（项目）· `E9:E10`（对应科目）· `K9:K10`（核对）· `L9:L10`（索引号）
  * `R8` 是段标题「二、审计过程：」只占 `A8`
* 数据区 **R11-R20（固定 10 个损益表项目）** / footer **R21**「合计」/ R22「三、审计说明：」
  / R26「编制说明：」
* 有效内容列 **12**（A..L）**恰等于** `max_column` ⇒ `uuid_col="M"`
* 🔴 **整册裸 IF 11 格，受管 sheet 命中 0 格** ⇒ 中性化不动本表（与 G9/G10/G8/G14 同族、
  与 G11 的 44 格相反）⇒ `D`/`I`/`J`/`K` 判 `formula` 成立

### 数据区公式分布（XML 逐格，排除自闭合 `<c/>`）

| 列 | A | B | C | D | E | F | G | H | I | J | K | L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `<f>` 格数 | 0 | **3** | **3** | 10 | 0 | 0 | 0 | 0 | 10 | 10 | 10 | 0 |

`B`/`C` 的 3 格全在父行：`B11=B12+B13` · `B14=B15+B16` · **`B17=B18`**（单子行，不是加法）。
`D=B{r}+C{r}` · `I=F{r}+H{r}` · `J=G{r}` · `K=J{r}=D{r}` 十行同形。

### 三层父子结构（与前端 `kind`+`indent` 逐行对应）

| 行 | A 列 | 性质 | 前端 `kind` / `indent` |
|---|---|---|---|
| R11 | 交易性金融资产 | **父行**（B/C 汇总 R12+R13） | `main` / 0 |
| R12 | 其中：指定为…金融资产 | 子行 | `ofWhich` / 1 |
| R13 | `     衍生金融资产` | 子行 | `derivative` / 1 |
| R14 | 交易性金融负债 | **父行**（汇总 R15+R16） | `main` / 0 |
| R15 / R16 | 其中：… / `     衍生金融负债` | 子行 | `ofWhich` / `derivative` / 1 |
| R17 | 其他非流动金融资产 | **父行**（只汇 R18） | `main` / 0 |
| R18 | 其中：…金融资产 | 子行 | `ofWhich` / 1 |
| R19 | 以公允价值计量的投资性房地产 | 🔴 **无子行的顶层行**（B/C 手填） | `main` / 0 |
| R20 | 其他 | 🔴 同上 | `main` / 0 |

## 🔴 裁决一：受管载体是「分类骨架」（用户拍板选项 A）

### 错配的准确位置：载体层，不是字段层

```
G13-detail-rows (store)  = 用户自填的「金融工具」明细行（动态 N 行，addRow/removeRow）
      ↓ buildG13CategorySkeleton()（computed，**不落库**）
固定 10 行                = 与模板 R11-R20 逐行对应
      ↓ buildG13CategoryTotalRow()
合计行                    = 模板 R21
```

⇒ 模板受管区对应的是**派生汇总视图**，而 store 里存的是更细粒度的原始明细。直接受管
`G13-detail-rows` 会让行表引擎按序把第 N 条工具写进第 N 个损益项目行 —— **产出错数**。

顺带纠正：`evidence/task8-c6-…md` §7.2 把 `instrumentName` 映射到模板 A 列「项目」是错的。
模板 A 列是固定的 10 个损益表项目名，不是用户自填的工具名。

### 四个方案与取舍

| | 做法 | 判断 |
|---|---|---|
| **A** ✅ | 骨架落库为第二个 store item（`G13-detail-skeleton`，10 行固定行集，`rowKey` 为身份），受管它；工具明细保持 HTML-only | **采纳** |
| B | 直接受管明细行 | ❌ 按序映射产出错数 |
| C | provider 侧从明细现算汇总、单向投影 | ❌ 汇总不可逆，回流方向断 |
| D | 本轮 HTML-only + 缺口登记 | 诚实但九条少一条 |

选 A 的四条依据：① 真库该键 **2 B 空数组** ⇒ 零存量迁移（推翻 Task 2 方案②的代价判断）
② 前端已有全部构件（固定行集 + 汇总逻辑），只需加持久化 ③ 与 G11「骨架行落库 + 用户增行」、
G14「固定行集落库」同族 ④ 业务上模板 G13-2 本身就是分类汇总表，工具明细是平台增强。

### 手工覆盖优先（同批拍板）

骨架值默认来自工具明细汇总。若 OO 回流后被汇总无条件重算 ⇒ **回流等于无效**。
⇒ 落库行带 `manualOverride`：有标记的行用存库值，`resetSkeletonRow()` 退回汇总口径。
覆盖行的公式列（`D=B+C` / `I=F+H` / `J=G`）按模板口径**重算**，否则 UI 会显示
「未审+调整 ≠ 审定」这种自相矛盾的数。

新增 `g13SkeletonStore.ts`：`parseStoredSkeleton`（容错） · `mergeSkeletonOverrides`（合并）
· `buildSkeletonPersistPayload`（**恒 10 行**，缺行会让行表引擎错位） · `setSkeletonOverride`
/ `clearSkeletonOverride` / `countSkeletonOverrides`。

### 推论：前端 21 个工具明细字段一个都不用删

`evidence` §7.2 的「删 5 个字段」建议基于「受管工具明细」这个已被替换的前提。
且 `instrumentType`/`remark` 是**骨架分类的驱动字段**（`mapBelongToAdjRow` /
`isDesignatedInstrument` / `mapBelongToOfWhichRow` 都读它们），删了就分不出「其中：指定」
与「衍生」两类子行。

### UI 改动（最小闭环）

category 视图原本全只读且**缺模板 E 列**（12 列只显示了 11 列）。本轮补：
E 列「对应科目」· 项目列的「手工值」标签 · 逐行「撤销覆盖」按钮 · 顶部覆盖行数提示。
编辑入口后置 —— OO 侧编辑 + 回流是主路径，前端只需保证「能看见覆盖 + 能撤销」。

## 🔴 裁决二：`B`/`C` 判 `editable`（列级 mode 对行级 mask 无解）

| 候选 | 后果 |
|---|---|
| `formula` | 7 个无公式格触发 `ProtectedRegionWriteError`（要求 `view.has_formula`） |
| `auto_source` | 3 个公式格触发 `ProtectedRegionWriteError`（要求该格**不是**公式） |
| 拆多 spec | 父行 `{11,14,17}` **非连续**，`first_data_row`/`last_data_row` 是连续区间 ⇒ 要 **7 个 spec**（R11 / R12-13 / R14 / R15-16 / R17 / R18 / R19-20），footer 还只有一行、归属不清 |
| **`editable`** ✅ | 父行三格的模板公式 materialize 后变成字面量（**公式丢失**） |

三条依据：

1. 逐格实测三格是**普通公式** `<f>B12+B13</f>` 而**不是 shared 主格** ⇒ 写字面量不会撞
   `SharedFormulaMasterWriteError`（`excel_materialize` 对非 formula/auto_source 的格只拦
   共享公式主格）。模板一旦把它们改成 shared 主格，本裁决立即失效 ⇒ 判据
   `test_parent_cells_are_plain_formulas_not_shared_masters` 就是那道警报。
2. 值仍然正确：前端骨架父行值 = 子行汇总，与模板公式**同口径**。丢的只是「在 OO 里改子行后
   父行自动重算」这个 Excel 内联动，而 OO 改动**必须回流**才算生效、回流后前端重算骨架 ⇒
   窗口极小。
3. 与 G8 的 `R`/`T` 裁决同型（那两列模板整格无公式 ⇒ 判 formula 会抛 ⇒ 只能 editable，
   正是判据 P12 的技术根据）。

⇒ 推翻 tasks.md Task 12 原写的 `formula_columns=("B","C","D","I","J","K")`，实际是
`("D","I","J","K")`。父行三格的**逐行不同形**公式落 `TEMPLATE_PARENT_FORMULAS_G1302`
（照 G8 的 `TEMPLATE_ROW_FORMULAS_G802` 范式），由判据按行比对但不参与 materialize。

`R19`/`R20` 是**无子行的顶层行**（B/C 手填）—— spec 原文把它们与父行混为一类，照那样判
formula 会覆盖用户手填值（与 G8 误标同型危害）。判据
`test_top_level_leaf_rows_must_not_be_treated_as_parents` 钉住这条。

## 三处推翻既有登记

### ① Task 2「发现 I：前端无骨架无父子字段」不成立

原结论来自「全文扫 `isParent`/`parentId`/`parentKey`/`children`/`isChild`/`indent`/`level`
⇒ 0 命中」。但骨架能力在**另外两个文件**里：

* `g13Constants.G13_ADJUDICATION_ITEMS` —— **恰 10 项**，`rowKey`/`label`/`kind`/`indent`
  与模板 R11-R20 逐行对应
* `g13CategorySkeleton.buildG13CategorySkeleton()` —— 按这 10 项汇总工具明细

⇒ 父子关系由 `kind`（`main`/`ofWhich`/`derivative`）+ `indent`（0/1）表达，**不需要新加
`parentId` 字段**。判据 `test_parent_child_structure_comes_from_kind_and_indent` 把
「indent=0 的行 == 父行 ∪ 顶层行」「indent=1 的行 == 子行」钉成可执行事实。

> 教训：扫字段名判「有没有某能力」是脆的 —— 能力可能以别的形态（常量表 + 汇总函数）存在于
> 别的文件。应先看**消费方 import 了什么**（`useG13Detail.ts` 顶部就 import 了骨架构建器）。

### ② 真库零存量 ⇒ 方案②的代价判断不成立

`checklist_responses` 实测：

| item_id | rows | 非空 | max remark | max conclusion |
|---|---|---|---|---|
| `G13-detail-rows` | 1 | 0 | **2 B**（`[]`） | 0 |
| `G13-detail-skeleton` | — | — | （本轮新建） | — |
| `G13-disclosure-listed` | 1 | 1 | 940 B | 0 |
| `G13-disclosure-soe` | 1 | 1 | 661 B | 0 |

Task 2 evidence §4.1 写方案②的代价是「改前端数据模型 + **存量数据迁移**，超出本 spec 声明层
范围」—— 存量迁移不存在。附注披露两键有真实载荷但属别的 sheet、不在受管面。

### ③ evidence §7.2「前端删 5 个字段」失效

见上文「推论」。

## 四处首版判据打红后的实测纠正

写完判据第一次跑 **2 failed / 62 passed**，两条都是我写错而不是代码错：

| # | 我写的 | 实测 | 根因 |
|---|---|---|---|
| 1 | E 列 `交易性金融资产-衍生金融资产` | **`交易性金融资产/衍生金融资产`** | 首版探针输出中文乱码，把 `/` 读成 `-` |
| 2 | `K` 的 shared 主格在 `K12`、组 `K12:K20` | **主格 `K13`、组 `K13:K21`** | 照 `D`/`I`/`J` 的形态推演 K |

另两处是写判据时就按实测钉住的（spec/evidence 原文不准确）：

| # | 文档原文 | 实测 |
|---|---|---|
| 3 | evidence §7.1 组区间 `F9:I10` | 横向组是 **`F9:J9`**，**含 J 列** —— 而 `J10`=「计入损益」语义上不属该组 |
| 4 | tasks.md「footer R21 `=B11+B14+B17+B19+B20`」 | 成立，但同一行还有**另两种约定**：纯 SUM（`I21`/`J21`）+ 布尔（`K21=J21=D21`） |

### 🔴 `K` 列 shared 组跨越 footer 边界

```
K11  <f>J11=D11</f>                             ← 普通公式
K12  <f>J12=D12</f>                             ← 普通公式（D/I/J 在这里已是主格）
K13  <f t="shared" ref="K13:K21" si="3">J13=D13</f>   ← 🔴 主格，组区间右端就是 footer
K14..K21  <f t="shared" si="3"/>                ← 成员格（**含 K21**）
```

对比 `D`/`I`/`J`：R11 普通公式 · **R12 主格**（ref `X12:X20`）· R13-R20 成员 · footer 另有
自己的公式（`D21` 属 `C21:D21` 组、`I21`/`J21` 是 SUM）。

⇒ 后果登记：**改 `K13` 会同时改掉 footer 的布尔格**（数据区与合计行共用一份公式文本）。

## resync 脚本修了一个从未生效的分支

`resync_g_slice_source_refs.py` 里同步 `dynamic_row_identity` 的那段读
`table.get("store_key")`，而 slice 的字段名是 **`table_key`** ⇒ `TABLE_TO_ENTRY.get("")`
恒 None ⇒ **整段 for 从未命中**，六条 lane 的 `row_identity.source_ref` 一直是旧值。

修字段名的同时发现第二件事：**`source_ref` 与 `row_identity_generator_source` 口径不同**

| 字段 | 口径 | G11 实测冻结值 |
|---|---|---|
| `html_counterpart.row_identity_generator_source` | `return` 那一行（逐字回源身份形态） | `#L72` |
| `dynamic_row_identity.…row_identity.source_ref` | **函数声明行**（回源哪个函数负责铸造） | `#L71` |

⇒ 新增 `_resolve_decl_line()` 现算声明行，而不是把 `return` 行号灌进去改掉口径。

🔴 `TABLE_TO_ENTRY` 与新增的 `SOURCE_REFS_MIRROR_WRITE_SITE` **只放 G11/G13 两条**。
实测依据：

| entry | `dyn source_ref` 冻结值 | 本脚本现算的声明行 | 判断 |
|---|---|---|---|
| G11 | `#L71` | `#L71` | ✅ 口径一致（**活证据**，现算后逐字不变） |
| G13 | `#L65`（改动前是声明行） | `#L84` | ✅ 同口径，本轮真漂移 ⇒ 同步 |
| G8 | `#L76` | `#L197` | ❌ 差 121 行，指的不是生成器 ⇒ 排除 |
| G9 | `#L82` | `#L277` | ❌ 同上 |
| G10 | `#L109` | `#L175` | ❌ 同上 |
| G14 | `#L61` | `#L151` | ❌ 同上 |

同理 `html_counterpart_source_refs` 里镜像写入点的那一项：G11 的 `#L233` 与
`payload_column_source` 逐字相同（镜像成立）、G13 改动前的 `#L185` 亦然；而 G8 `#L400` /
G9 `#L322` / G10 `#L382` / G14 `#L199` 与各自写入点**不同值** ⇒ 那一项指别的取证点。

> 把它们一并「同步」会改掉别人的取证口径 —— 排除，留给各自 lane 判定。
> `adjudication.reason` 里的 `#L185` 是裁决叙述文本，**不改**（与前几轮一致）。

## EXPECTED 加两个新键而不是改旧键

`test_store_merge_plan_is_registered_with_oo_neutralization[G13]` 首次红：
`EXPECTED["G13"]["store_item_id"]` 是 `G13-detail-rows` 而注册的是 `G13-detail-skeleton`。

直接改旧键会连带打破三条判据：

* `test_row_identity_three_families`（`by_key == {"id":…, "rowId":…, "rowKey":{"G14"}}`）
* `test_row_identity_key_and_generator_are_source_backed`（在 `useG13Detail.ts` 里 grep
  `{key}: string` —— `rowKey` 在 `g13SkeletonStore.ts` 而不在它里面）
* `test_wp_code_adjudication_*`（`store_payload_evidence.store_item_id` 记的是**真库载荷
  证据**那个键）

⇒ 两个键指的是**不同的事**：`store_item_id`/`row_identity_key` = 工具明细（slice 冻结口径
+ 真库证据），新增 `managed_store_item_id`/`managed_row_identity_key` = 受管载体。
另加判据 `test_only_g13_manages_a_different_store_item_than_its_legacy_table` 钉住
「这种分歧只发生在 G13」—— 别家出现分歧就是接错了载体（或遇到同类结构性错配，那该像本
Task 一样单独裁决，而不是静默跟随）。

## 验证

| 门 | 结果 |
|---|---|
| `test_g13_column_isomorphism.py` | **65 passed**（五层闭环，含 XML 逐格 shared 组形态 + 真跑中性化） |
| 六 lane 判据（12 文件） | 13 → **10 failed / 615 passed**（G13 三条转绿） |
| 零回归门逐 provider 现算 | 18 家 **17** 家出 digest；g13 `contract=eb8d915e9084` / `projection=f20d3ac0257c` |
| 契约双向锁 | `--apply` 后 recheck OK（`canonical_digest=eb8d915e9084…`） |
| `resync --check` | 无待改（G11 零改动 = 口径活证据） |
| 行数门禁（15 暂存文件，pre-commit 真跑） | 绿 |
| 前端 G13 12 spec / 96 tests | 全绿（含新增 `g13SkeletonStore.spec.ts` **15 条**） |

### 剩余 10 条红的归属（全非本 lane）

* G12/G3/G1 各 2 条（provider 未交付 + store merge 未注册）= 6 → Task 13/14
* G12 布尔列 1 条 + G12 docstring 缺陷登记 1 条 → Task 13
* P18 两条（九条 adapter 全进 digest / 九条契约全发布）→ Task 15

### 未做的事（如实登记）

* **未修 `useG13Detail.ts` 的 2 条 vue-tsc 报错** —— 在 `mergeG13SourceSeeds` 调用处
  （`G13MergeTargetRow` 与 `G13DetailRow` 类型不兼容），属 `g13SourceDetailPull.ts` 的类型
  定义链、**改动前就存在**、不在本 lane 作业面（修它要动类型声明、有回归风险）
* **未加骨架格的前端编辑入口** —— OO 侧编辑 + 回流是主路径；前端只做到「能看见覆盖 +
  能撤销」的最小闭环。若后续需要现场直填骨架，`setSkeletonCell(rowKey, field, value)`
  已就绪，只需接 UI
* **未做真实 OO 栈 / Playwright 实测** —— 需 `start-dev.bat` 环境，归 Task 15 收口
* **`adapter_registered=False`** —— 与 D1/D3/D5/D6/D7/E1/F1~F5/G2/G8/G9/G10/G11/G14 卡在
  同一平台级缺口（umbrella BP-61-1 = G slice 的 BP-1~BP-3）
* **未改 G8/G9/G10/G14 的 slice 引用** —— 口径与本脚本不同（见上表），排除

## 一次性件已删

`_g13_probe.py` / `_g13_cell_xml.py` / `_g13_refs_probe.py` / `_g13_ek_probe.py` /
`_gd_per_provider.py` / `_g13_entry_from_g11.py` / `_g13_docstring.py` / `_g13_notes.py` /
`_g13_footer_note.py`（共 42 个临时件含中间输出）。保留 `backend/scripts/check/_vt_report.py`。

## 给后续 lane 的可复用结论

1. **「前端有没有某能力」不能只扫字段名** —— 先看消费方 `import` 了什么。G13 的骨架能力在
   两个被 import 的文件里，扫 `isParent`/`children` 字段扫不到（Task 2 因此误判）
2. **载体层错配与字段层错配要分开判**：前者是「store 的行粒度 ≠ 模板的行粒度」，改字段没用，
   必须换 store item 或新建一个；后者才是列模型对齐的问题
3. **列级 `mode` 表达不了行级 mask**。遇到「同一列 N 行有公式 + M 行无公式」时，三条路
   （formula / auto_source / 拆多 spec）都要先算代价；若父行**非连续**，拆 spec 的份数会爆
   ⇒ 判 `editable` + 把丢失的公式落台账，并钉住「那几格不是 shared 主格」这个前提
4. **shared formula 组的起点不可跨列推演**：G13 的 `D`/`I`/`J` 主格在 R12，而 `K` 在 R13
   且组区间**跨越 footer**。逐列读 XML，不要用一列的形态套另一列
5. **改 slice 引用前先核「冻结值与现算值是否同口径」**：六条 lane 的 `source_ref` 口径不统一，
   一并「同步」会改掉别人的取证。把已验证一致的留在白名单里当活证据（现算后逐字不变）
6. **判据的期望表与实测冲突时，先分清「两个值是不是同一件事」**：G13 的
   `store_item_id`（真库证据）与受管载体是两件事 ⇒ 加新键，不是改旧键。改旧键会让另一条
   判据必红，那种「按下一个翘起另一个」就是信号
7. **探针输出中文必须 `Get-Content -Encoding utf8` 读**：本轮按乱码把 `/` 读成 `-`，
   写进了 provider 与前端两处常量，靠判据打红才发现
