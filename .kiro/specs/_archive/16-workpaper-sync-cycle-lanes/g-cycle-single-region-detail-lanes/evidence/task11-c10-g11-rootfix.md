# Task 11 / C-10：G11 投资收益明细分析表接入双向回写

commit `23b310df9`（15 文件，+2106 / −36）。九条 lane 的**第五条**。

## 一句话结论

G11-2 是九条里**唯一受管表自身命中裸 IF 的一家**（44 格）。中性化会摘掉受管列自己的公式
⇒ 占比列 `G`/`K` 只能判 `auto_source`，不能判 `formula`。这推翻了 Task 5 判据的后半句，
判据已按实测改写（保护力度不放宽）。**前端零改动**（九条唯一）。

## 模板实测（`backend/wp_templates/G/G11 投资收益.xlsx`）

* 75,600 B · sha256 `a1b1d87f29e2dc63e279326d887b3d09bcda6b48c9c54881d82a875a0fe0f513`
  · 10 sheets · **0 definedName**
  * 🔴 entry 模块注释原写「99,458 B」是笔误，本轮实测纠正为 75,600 B
* 受管 sheet `明细分析表G11-2`：`max_row=39` / `max_column=13`
* 🔴 **单级表头 R9**（九条唯一）：**R8/R9 零合并格** —— R8 是段标题「二、审计过程」只占 A8，
  不是表头行。照前四条写两级会让 `header_rows=2` 把段标题当组行
* 数据区 **R10-R30（21 行，九条最长）** / footer **R31**「合计」
* 🔴 **R32「本年利润总额」是手填分析行** —— 既非 footer 也不受管（前端另有独立 store 键
  `G11-detail-profit-total`）。受管区必须止于 R30，否则行表引擎会把 R32 当数据行吞掉
* R33「三、审计说明：」R34「1、对变动比率在 20% 以上的项目…」
* 有效内容列 13（A..M）**恰等于** `max_column`（无空尾列）⇒ `uuid_col="N"`
* A 列 R10-R30 预填 `1..21`（`seq` 是真列的直接证据）

### 数据区公式分布（逐格，排除自闭合 `<c/>` 后重测）

| 列 | A | B | C | D | E | F | G | H | I | J | K | L | M |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `<f>` 格数 | 0 | 0 | 0 | 0 | 0 | 21 | 21 | 0 | 0 | 21 | 21 | 21 | 0 |

`F=D+E` · `G=IF(F10=0,0,F10/$F$31)` · `J=H+I` · `K=IF(J10=0,0,J10/$J$31)` · `L=F-J`。
`D`/`E`/`H`/`I` 是**空可填格**（判 `editable` 正确）。

> 🔴 首版探针把 D/E/H/I 都数成 21 格 —— 正则 `<c r="D10"[^>]*>` 的 `[^>]*` 吃掉了自闭合
> `<c r="D10" s="5"/>` 的斜杠，随后 `(.*?)</c>` 跨到下一个带 `</c>` 的格。改成「一次扫全部
> `<c>` 建 ref→inner 映射、自闭合记空串」才得到真数。判据里的 `_cell_map()` 就是修好的那版。

### footer R31

* `D`/`E`/`F`/`H`/`I`/`J`/`L` 七列：`<f>SUM(x10:x30)</f>`（普通公式）
* 🔴 `G31`/`K31`：自闭合 **shared 成员格** `<f t="shared" si="1"/>` / `si="2"`，**不带公式文本**，
  主格在 `G10`/`K10`
* ⇒ `footer_carries_total_formula=True`

## 🔴 裁决：`G`/`K` 判 `auto_source`（本条与前四条的根本差异）

### 中性化实测（真跑，非推演）

`adapters/excel.py` 在 materialize **之前**对 substrate 副本跑
`g7_oo_crash_if_neutralize.neutralize_oo_crash_if_formulas(path)`（**就地改**），它把含词界
`IF(` 的 `<f>` 元素**整个摘掉**（`<v>` 留着）。复制模板到临时目录真跑一次：

```
数据区 R10-R30：F 21→21 · G 21→**0** · J 21→21 · K 21→**0** · L 21→21
footer  G31 <f t="shared" si="1"/><v>0</v> → <v>0</v>      ← 成员格也被摘
        F31 <f>SUM(F10:F30)</f><v>0</v>   → 原样保留       ← SUM 不受影响
受管 sheet 触及 **44** 格（= 21×2 + footer 两格），全列名只有 {G, K}
整册 **95** 格 = 受管表 44 + 收益率分析表G11-4 32 + 审定表G11-1 19（全 G 循环最多）
```

前四条（G9/G10/G8/G14）的受管表**零裸 IF**，中性化只动审定表 ⇒ 这条是**唯一**会摘掉
受管列自己公式的。

### 为什么只有一种声明能过

`excel_materialize` 的两条检查方向**相反**（单区路径 L1811/L1830 · 行表路径 L1979/L1996）：

| mode | 检查 | 中性化后的 G/K |
|---|---|---|
| `formula` | 要求 `view.has_formula` 为真 | ❌ 抛 `ProtectedRegionWriteError` |
| `auto_source` | 要求该格**不是**公式 | ✅ |

⇒ `F`/`J`/`L` 判 `formula` 进 `formula_columns`；**`G`/`K` 判 `auto_source`**。

### 被否掉的三个替代方案

| 方案 | 否决理由 |
|---|---|
| G/K 判 `formula` | materialize 必抛 `ProtectedRegionWriteError`（substrate 无公式） |
| G/K 判 `editable` | OO 侧可改 + 值进 store，与前端派生形成双源 |
| 不挂中性化 / 给 G11-2 加 sheet 白名单 | GC-2 要求 per-file 一律挂；G11-2 在 OO 侧仍会崩 |

`auto_source` 与 `formula` 同属 `contracts.PROTECTED_MODES` ⇒ 不入 store、OO 改动不合并，
**保护力度与 `formula` 完全相同**，这不是把判据改松。
先例：`phase5_f1_05_long_term` 的 `J` 列（模板无公式 + 前端派生 + OO 不合并）。

### 推翻 Task 5 判据的后半句

`test_g_single_region_p10_p11_shift.py::test_conclusion_g_and_k_stay_managed_as_formula_columns`
→ 改名 `..._but_as_auto_source_not_formula`。

* P10 结论「G/K **受管**」**成立** —— 它们在 `field_specs` 里、OO 侧只读、不入 store
* 「受管为 **formula_columns**」**不成立** —— 中性化后那两列没有公式可保护

改写后判据守的三件事：① 模板公式列集合仍是 `{F,G,J,K,L}`（模板事实）② provider 两族之并
**恰等于**它（一列不漏）③ `auto_source ∈ PROTECTED_MODES`（保护力度不放宽）。

## 占比列引合计行（裁决 G1R-H5）

* `G10 = =IF(F10=0,0,F10/$F$31)` 引 `$F$31`；`K10` 引 **`$J$31`** —— **两个分母不同**
  （spec 原文只说「引 F31」，Task 2 实测发现 K 引 J31）
* Task 5 真跑 `excel_row_shift.shift_sheet_rows`：插 3 行后既有行主格 `$F$31→$F$34` /
  `$J$31→$J$34` ⇒ **位移成立**，G/K 不改判 HTML-only
* 🔴 框架层缺陷（Task 5 新发现，本 spec 不修）：**新插入行**的 fill-down 公式绝对引用**不位移**，
  仍 `$F$31` —— 而 R31 位移后已是新行。⇒ **实践后果：G11-2 不要在数据区插行**（21 行足够）
* 🔴 判「占比列指向哪一行」**必须看 shared 组主格**：openpyxl 会**自动展开**成员格
  （`ws["G31"].value` 返 `=IF(F31=0,0,F31/$F$31)`），看成员格的 openpyxl 值会被展开式骗过去。
  判据同时钉住「XML 层是自闭合成员格」+「openpyxl 层会展开」两个事实，防后人改回 openpyxl 口径

## 🔴 前端零改动（九条唯一）

`useG11DetailAnalysis.G11DetailRow` 的 21 个字段里，13 个受管字段**实测已与模板列序
A..M 逐列对齐**（不是改出来的）：

```
seq A / itemName B / investeeName C / currentUnadjusted D / currentAdjustment E
/ currentAudited F / currentShare G / priorUnadjusted H / priorAdjustment I
/ priorAudited J / priorShare K / changeAmount L / reasonIndex M
```

另 8 个非模板列字段（`FRONTEND_ONLY_FIELDS_G1102`）：`id`（行身份）· `rowKey`（与 G11-1
对齐的分项勾稽键）· `group` · `tradingDisposeSubtype`（上市附注子表子类）· `changeRate`
（变动率 —— 模板只有变动额 `L`）· `changeRateHighlight` / `reasonRequired`（阈值派生）·
`isSkeleton`（骨架行不可删）。

**不为「统一风格」动前端**：已对齐就是对齐，判据改成「保持对齐」的守卫。

### 三处不可照抄前四条的细节

| # | G11 | G9/G10/G8 |
|---|---|---|
| ① 行身份键 | **`id`** | `rowId` |
| ② `generateId()` 随机后缀 | `slice(2, 6)` = **4** 位 | `slice(2, 5)` = 3 位 |
| ③ `seq`（A 列「序号」） | **真列**（模板 A10-A30 预填 1..21）必须受管 | 纯显示序号，不占模板列 |

③ 照抄会漏掉 A 列（OO 侧改序号不回流）。判据 `test_seq_is_a_real_template_column_unlike_g9_g10_g8`
直接比对 `[ws.A10..A30] == list(range(1, 22))`。

## 另修两条判据自身的缺陷

### ① 扫 `vars(module)` 找 spec 对象是脆的（第三次同类修正）

`test_g11_provider_declares_footer_carries_total_formula` 首版：

```python
specs = [s for s in vars(mod).values() if s.__class__.__name__ == "RowTableSheetSpec"]
assert specs, "G11 provider 未导出 RowTableSheetSpec"   # ← 交付后实测 [] ⇒ 假红
```

根因：本 spec 九条一律「entry 层 + sheet 层」两模块，spec 对象声明在
`phase5_g11_02_detail.SPEC_G1102`，entry 层只通过 `managed_row_table_specs()` 动态汇总、
不把它 import 进模块命名空间。同坑 Task 10（G14 布尔列判据）踩过一次。

⇒ 改走 **provider 公开接口** `mod.managed_row_table_specs()`，并断言
`[s.managed_sheet for s in specs] == ["明细分析表G11-2"]`。

### ② 写死的期望值教人放宽判据（GC-10）

`test_g_foundation_p20_golden_digest_baseline.py::test_g_provider_whitelist_contains_exactly_the_delivered_ones`
写死 `g_mods == ["…phase5_g2_interest_receivable"]` 并留了「新增 G lane 时在此追加」的指引。

实际效果：Task 8/9/9b/10/11 交付 G9/G10/G8/G14/G11 后必红，而那五条都是**合法交付**。
写死的是**分母**，每条 lane 都得来手改一次，改的人还得判断「该不该改」⇒ 判据在教人放宽自己。

⇒ 改为**现算**：期望值从 `DELIVERED_PER_ENTRY_CONTRACTS` 取，守的是真正要守的
「白名单 ↔ 交付台账**双向配平**」（任一侧多/漏都红）+ 保留「G2 canary 不得掉出白名单」的下界。

## 行数门禁

| 文件 | 实测 | 处置 |
|---|---|---|
| `test_task49_g_cycle_migration.py` | 3300 > 3299 | 压缩 `SLICE_DELIVERED_CONTRACTS` 上方注释 3 行 → 3297 |
| `delivered_contracts_ledger.py` | 1773 > 1718 | 基线 1637 → 1773 |

🔴 **whitelist 里「不可再拆」那句站不住，本轮如实修正**：按循环切成 `_d.py`/`_efg.py`/`_h.py`
再在主文件 `+` 聚合，判据 `test_contract_directory_matches_the_delivery_ledger` 拿到的仍是
一张完整表 ⇒ 技术上**可拆**。本轮不拆的真实理由只有两条：① 它是**并发会话共享**文件
（G/H/I/J/K 五条线同时追加条目），拆分会把每条线的 commit 都变成跨文件大范围冲突
② 拆分不在任何在途 lane 的作业面内，顺手拆等于无主改动。
⇒ 已写入**触发条件**：行数过 **2400**，或在途并发会话降到 1 条时必须立项拆分。

## 验证

| 门 | 结果 |
|---|---|
| `test_g11_column_isomorphism.py` | **58 passed**（五层闭环，含真跑中性化 + shared 主格逐格比对） |
| 六 lane 判据（10 文件） | 16 → **13 failed / 534 passed**（G11 三条转绿） |
| 零回归门逐 provider 现算 | 17 家 **16** 家出 digest；g11 `contract=804325e658e2` / `projection=db29d174b571` |
| 台账 ↔ 白名单配平（`test_registrar_delegates_to_each_entry_own_attach`） | 绿 |
| 行数门禁（12 暂存文件，pre-commit 真跑） | 绿 |
| 前端 G11 13 spec / 100 tests | 全绿 |

### 剩余 13 条红的归属（全非本 lane）

* G13/G12/G3/G1 各 2 条（provider 未交付 + store merge 未注册）= 8 → Task 12/13/14
* G12/G13 布尔列 2 条 → Task 12/13
* G12 docstring 缺陷登记 1 条 → Task 13
* P18 两条（九条 adapter 全进 digest / 九条契约全发布）→ Task 15

### 零回归门唯一 FAIL：f1（**非本轮引入**）

```
f1  FAIL  TypeError: build_store_projection() missing 1 required positional argument: 'payload'
          pos=2('store_item_id', 'payload')
```

门按 `mod.build_store_projection(rows, contract=contract)` 调用（**单位置参**）。逐家实测签名：
除 f1 外全部 16 家都是 `pos=1('payload',)`，只有 f1 是两位置参。

> 🔴 本轮笔记纠正：曾误记「G 全族都是两位置参」。grep `def build_store_projection(` 时下一行
> 显示的是 `payload:` 就以为第一个参数是 `store_item_id` —— 实际 G 族一律
> `(payload, *, contract, limits, store_item_id)`，`store_item_id` 走关键字。G11 的 docstring
> 里已写明「签名形态是刚性的」并登记了 F1/F2 的这个缺陷。
> ⇒ 该 FAIL 属 `f1-sync-coverage-and-first-canary` 作业面。

### 未做的事（如实登记）

* **未新建 `tsconfig._g11.json` 跑窄 vue-tsc** —— 前端**零改动**、无新类型面；改为跑 13 个
  G11 前端 spec（100 tests 全绿）证明判据里按值 grep 的形态与运行时一致
* **未修 `excel_row_shift.py` 的新插入行绝对引用不位移缺陷** —— 跨循环影响面 + 引擎核心，
  Task 5 已明确另立项；判据 `test_newly_inserted_rows_keep_the_stale_absolute_denominator`
  钉住**当前**行为，修好后必红并提示改断言为 `$F$34`
* **`adapter_registered=False`** —— 与 D1/D3/D5/D6/D7/E1/F1~F5/G2/G8/G9/G10/G14 卡在同一
  平台级缺口（umbrella BP-61-1 = G slice 的 BP-1~BP-3），供给就绪后真栈注册
* **未做真实 OO 栈 / Playwright 实测** —— 需 `start-dev.bat` 环境，归 Task 15 收口

## 一次性件已删

`_g11_probe.py` / `_g11_neutralize_probe.py` / `_g11_neutralize_recheck.py` /
`_g11_spec_check.py` / `_g11_iface_probe.py` / `_gd_per_provider.py` /
`_g11_entry_from_g14.py`。保留 `backend/scripts/check/_vt_report.py`（跨 lane 复用的
vitest JSON 报告解析）。

## 给后续 lane 的可复用结论

1. **中性化要真跑，不能推演**：`neutralize_oo_crash_if_formulas` 是**就地改**，判据要复制
   模板到临时目录跑；断言口径是「各列 `<f>` 数量前后对比」，模板改写成不含 IF 的形式即打红
2. **openpyxl 会自动展开 shared formula 成员格** ⇒ 凡涉及「这一格自己有没有公式文本」的判断
   一律读 XML；判据把两层口径同时钉住，防后人改回 openpyxl
3. **扫 XML `<c>` 必须处理自闭合格**（`<c r="D10" s="5"/>`），否则正则跨格吃到下一个公式，
   空格被误判成有公式 —— 这类探针 bug 会直接污染列模型裁决
4. **判据扫 `vars(module)` 找声明对象一律改走 provider 公开接口**（第三次踩）
5. **写死期望值的「新增时在此追加」指引是反模式**：它把分母写死，每条 lane 都要来手改并自行
   判断该不该改 ⇒ 改成从台账现算（GC-10）
6. **模板字节数这类注释值也要实测**（G11 entry 注释把 75,600 写成 99,458）
