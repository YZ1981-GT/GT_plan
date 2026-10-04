# 语料形态与真库形态 —— C9 / C8 双簇分诊

> 范围：12 个**不能**归因到 manifest 漂移的失败。两簇的共同点是断言对象都在测试树之外
> —— 磁盘上的 xlsx 模板字节、以及 `audit_platform` 真库里的行。所以两簇的第一问相同：
> **是断言过期了，还是被断言的真东西真的变了？**
>
> 环境：cwd=`d:\GT_plan\backend`，`..\.venv\Scripts\python.exe -m pytest -q --tb=short -rf -p no:randomly`
>
> 纪律：不因为要变绿就把尺寸/计数基线重新冻结到现值；每条修复都做**变异验证**
> （把真东西弄坏 → 确认 RED → 还原）。

## 12 行判决表

| # | node | 簇 | 判决 | 处置 |
|---|------|----|------|------|
| 1 | `test_workbook_row_change_carriers.py::TestScannerRewriterAgreement::test_scanner_agrees_with_rewriter_on_whole_corpus` | C9 | REAL CHANGE（两侧实现均未回归） | 待填 |
| 2 | `test_workbook_row_change_carriers.py::TestDefinedNameClassification::test_defined_name_five_way_classification` | C9 | REAL CHANGE | 待填 |
| 3 | `test_task42_h1_grouped_dynamic_pilot.py::TestUpstreamRelsAndNamespaceDefectsAreFixed::test_ten_of_the_authoritative_workbooks_share_this_shape` | C9 | REAL CHANGE **+ 判据口径缺陷**（`*.xls*` 把 5 份 `.preclean.bak` 当工作簿） | 收紧 glob 到真工作簿后缀（370，机器无关），下界保留 |
| 4 | `test_task43_g7_two_level_dynamic_pilot.py::TestUpstreamRelsAndNamespaceShapesStillHold::test_ten_authoritative_workbooks_share_this_shape` | C9 | REAL CHANGE（与 rows 1–2 同一笔 +1） | 已按「下界 + 扩展名等式 + 结论等式」修好，本次只复核 + 变异验证 |
| 5 | `test_task48_f_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_bp5_wrong_workbook_fallback_is_reproducible` | C9 | **缺陷已被真修**（`82f58ea44` 的 `_PRIMARY_TEMPLATE_TIERS`，**不是** `_PROGRAM_TABLE_CODE_RE` 碰撞） | 退役复现判据 → 改名 `test_bp5_whole_code_fallback_is_fixed_and_unambiguous`，改锁「已修且不许回归」；BP-5 status 降级 `PARTIALLY_FIXED_WHOLE_CODE_FALLBACK_NOW_RESOLVES_CORRECTLY`（不销号） |
| 6 | `test_task50_h_cycle_migration.py::TestProperty23DynamicRowIdentity::test_positional_identity_inventory_is_exhaustive_and_partitioned` | C9 | STALE ANCHOR（**无未归族新案例**；17/3+6+8 一个没变） | 行锚 `useH4Recoverable.ts#L313→L314` 已重锚，复核 + 变异验证 |
| 7 | `test_task50_h_cycle_migration.py::TestProperty23DynamicRowIdentity::test_family_a_hits_write_to_the_declared_key` | C9 | STALE ANCHOR（同上，另一份文件 +1 行） | 行锚 `GtH4EngineeringMaterials.vue#L383→L384` 已重锚，复核 + 变异验证 |
| 8 | `test_task41_d2_large_json_pilot_pg.py::test_real_store_payload_is_the_frozen_866kb_shape` | C8 | REAL CHANGE（排版 +104,579 零信息 / 真实编辑 −852） | **已闭**：尺寸换紧凑口径下界 + 排版上限（非重冻），归因文字更正，补逐键字节取证 |
| 9 | `test_task41_d2_large_json_pilot_pg.py::test_no_other_store_item_is_touched` | C8 | REAL CHANGE（新增空 item `D2-entry-rows`）；**未**发生跨车道写入 | **已闭**：条数改下界 + 分流恒等式，泄漏两条保持等式 |
| 10 | `test_task42_h1_grouped_dynamic_pilot_pg.py::test_disposal_store_item_is_empty_across_the_whole_database` | C8 | REAL CHANGE（G4-1 探针写脏真库，51 字节全部对平） | **拒绝放宽 · 保持 RED**，owner = G4-1 车道 |
| 11 | `test_task42_h1_grouped_dynamic_pilot_pg.py::test_contract_declares_the_observed_emptiness` | C8 | REAL CHANGE（同上，成对） | **拒绝放宽 · 保持 RED**，owner = G4-1 车道 |
| 12 | `test_task61_oo94_word_pilot_gate.py::TestBindingConstraintIsMeasured::test_the_three_arms_really_run_against_the_database` | C8 | 不属本簇 —— capability 翻转的下游（前提被翻转作废） | **移交** Task 67 登记的复核方，RED 不动 |

---

## C9-1 / C9-2 —— 语料分母（`test_workbook_row_change_carriers.py`）

### 实测输出（verbatim）

```
F......F......................                                           [100%]
_ TestScannerRewriterAgreement.test_scanner_agrees_with_rewriter_on_whole_corpus _
tests\workpaper_sync\test_workbook_row_change_carriers.py:169: in test_scanner_agrees_with_rewriter_on_whole_corpus
    assert len(files) == EXPECTED["corpus_templates"], (
E   AssertionError: 语料规模变了：352 份，冻结值 351
E   assert 352 == 351
___ TestDefinedNameClassification.test_defined_name_five_way_classification ___
tests\workpaper_sync\test_workbook_row_change_carriers.py:463: in test_defined_name_five_way_classification
    assert counts == EXPECTED["defined_name_classes"], (
E   AssertionError: 实测 {'builtin_self_scope': 2513, ..., 'user_self_scope': 273, ...}
E     冻结 {'builtin_self_scope': 2465, ..., 'user_self_scope': 267, ...}
2 failed, 28 passed, 1 warning in 1.78s
```

### 🔴 先回答「跨实现对账这条红了，是哪一侧回归了？」

**两侧都没回归。** 这条判据**压根没跑到对账那一步** —— 它在第 169 行的语料规模门
（`assert len(files) == 351`）就挂了，而真正的扫描器↔改写器比对在其后。

跳过规模门直接跑全量对账（`backend/scripts/_c9_corpus_attrib.py`，352 份全扫）：

```
compared       72637
=== 跨实现对账（扫描器 vs 改写器）不吻合例数 = 0 ===
```

**0 例不吻合 / 72,637 条公式实际比对。** 扫描器（`scan_reference_carriers` 口径）与
改写器（`_rewrite_formula_refs`）在全库 352 份上完全同口径。所以这条红是**规模门的
断言过期**，不是任何一侧实现的回归 —— 不存在「把一侧对齐到另一侧」的问题。

### 归因：两笔独立的真实变更，5 个数逐一对平

冻结时点 = `eed3a34ff`（2026-09-06，本判据最后一次改动），当时 tracked xlsx = **351**。

| rev | 日期 | tracked xlsx |
|-----|------|--------------|
| `eed3a34ff`（判据冻结点） | 2026-09-06 | 351 |
| `d3b3d80d9~1` | 2026-09-13 | 351 |
| `d3b3d80d9` | 2026-09-14 | **352** |
| `HEAD` (`fb7a0ace2`) | 2026-09-23 | 352 |

`git status --porcelain backend/wp_templates` 干净、`git ls-files` 与磁盘 rglob 双向
取差集均为空 ⇒ **磁盘内容 == HEAD 内容**，352 份全部是被提交的，没有未跟踪的脏文件。

**变更① `d3b3d80d9`（2026-09-14）新增 `D/D4 收入底稿.xlsx`**
（注意：库里原已有同名无空格的 `D4收入底稿.xlsx`，两者并存，见下「待澄清」）

```
D4 收入底稿.xlsx  【eed3a34ff 里不存在 = 纯新增】
   formulas 168 / sheet 0 / external 0 / three_d 0 / no_target 0
   defined_name: builtin_self_scope +48, user_self_scope +6, 其余 +0
```

**变更② `1a0b55651`（2026-09-12「D 循环 5 个 canary 做实到 bidirectional_verified」）
改动 `D/D7 合同负债.xlsx`**

```
D7 合同负债.xlsx
   eed3a34ff: formulas 206 / sheet 105 / external 6
   HEAD     : formulas 200 / sheet 105 / external 0
   delta    : formulas -6 / external -6
     - 消失: 合同负债实质性程序表 D8A（原）: [21]底稿目录!A3
     - 消失: 合同负债实质性程序表 D8A（原）: [21]底稿目录!A4
     - 消失: 合同负债实质性程序表 D8A（原）: [21]底稿目录!A5
     - 消失: 合同负债实质性程序表 D8A（原）: [21]底稿目录!A6
     - 消失: 合同负债实质性程序表 D8A（原）: [21]底稿目录!A7
     - 消失: 附注披露信息(上市公司): [22]审定表D7!A8
```

消失的 6 条全部是**指向外部工作簿的死链**（`[21]` / `[22]` 是保存时残留的外部簿索引），
模板做实 bidirectional 时被清掉。同一份的 `sheet` 类引用 105 处**一条没动** ⇒ 不是
分词能力退化（若是能力退化，会表现为 sheet↔external 之间的搬家，或 sheet 侧同步掉数）。

**逐数对平（零残差）**

| 冻结键 | 冻结值 | + D4新增 | − D7清死链 | = 应得 | 实测 352 份 | |
|--------|--------|---------|-----------|--------|------------|--|
| `corpus_templates` | 351 | +1 | 0 | 352 | 352 | ✅ |
| `corpus_formulas` | 126,565 | +168 | −6 | 126,727 | 126,727 | ✅ |
| `corpus_external_refs` | 3,883 | +0 | −6 | 3,877 | 3,877 | ✅ |
| `corpus_sheet_refs` | 144,904 | +0 | 0 | 144,904 | 144,904 | ✅ |
| `corpus_no_target_refs` | 179 | +0 | 0 | 179 | 179 | ✅ |
| `corpus_three_d_refs` | 0 | +0 | 0 | 0 | 0 | ✅ |
| `dn.builtin_self_scope` | 2,465 | +48 | 0 | 2,513 | 2,513 | ✅ |
| `dn.user_self_scope` | 267 | +6 | 0 | 273 | 273 | ✅ |
| `dn.` 其余四类 | — | +0 | 0 | 不变 | 不变 | ✅ |

**残差 = 0。** 全部 8 个变动量都落到两个具名 commit 的两份具名模板上，没有任何一分
差额需要用「不知道哪来的」解释。⇒ 判决 **REAL CHANGE**（断言过期是因为真东西动了），
不是 REGRESSED IMPLEMENTATION。

### 待澄清（不由本簇处置）

`D/D4收入底稿.xlsx`（无空格，`2dbede1d4` 2026-07-16 加）与 `D/D4 收入底稿.xlsx`
（有空格，`d3b3d80d9` 2026-09-14 加）**并存**。两者只差一个空格，像是同一份底稿的
重复入库。语料判据不负责裁定模板库该留哪份 —— 已在结论里作为遗留项上报，本次
**不删任何模板字节**。

---

## C9-3 / C9-4 —— 同一个 +1，两个不同口径（`ten_authoritative_workbooks`）

### 实测输出（verbatim，BEFORE）

两条判据在**本次分诊开始时已经是绿的** —— 工作树里已有未提交的修复（不是我改的，
`git diff` 证据见下）。先记录四个文件的整体实况，避免把别人的修复算成本簇的：

```
test_task42_h1_grouped_dynamic_pilot.py   1 failed, 143 passed  in 17.93s
test_task43_g7_two_level_dynamic_pilot.py 1 failed, 204 passed  in 32.73s
test_task48_f_cycle_migration.py          1 failed,  81 passed  in  7.04s
test_task50_h_cycle_migration.py          3 failed, 101 passed  in 44.36s
```

```
$ pytest test_task42...::test_ten_of_the_authoritative_workbooks_share_this_shape \
         test_task43...::test_ten_authoritative_workbooks_share_this_shape -q
..                                                                       [100%]
2 passed, 1 warning in 1.70s
```

**其余红全部不属本簇**，node id 如实记下，不追：

| node | 属谁 |
|------|------|
| `test_task42::TestPilotIntroducesNoResolverDebt::test_no_function_in_this_module_is_classified_as_writer_or_resolver`（`assert len(entries) == 327` 实测 371） | manifest 漂移簇 |
| `test_task43::TestProductionWiring::test_generator_is_the_only_writer_of_the_disk_contract`（`['write_bytes']`） | 其他簇 |
| `test_task50::TestOrphanLegacyComposables::test_declared_orphan_formdata_composables_really_have_no_production_consumer` | 其他簇 |
| `test_task50::TestProperty70NoCrossEntryReuse::test_deletion_plan_composables_are_distinct_and_real`（427 vs 401） | 其他簇 |
| `test_task50::TestProperty28DefinitionDriftFailClosed::test_template_resolution_audit_recomputes`（`find_template_file("H2A") is None` 实测 `H/H2 在建工程.xlsx`） | **`82f58ea44` 碰撞簇** —— 见下文 C9-5，那才是任务书描述的「已发布特性撞已发布守卫」的落点 |

### 原始红的两个数（任务书实测）与 HEAD 版判据

`git show HEAD:` 对照确认两条判据在 HEAD 上都是**等式**，工作树里已被改成下界：

| node | HEAD 版断言 | 实测 | 工作树版断言 |
|------|------------|------|------------|
| row 3 | `assert total == EXPECTED_TOTAL_WORKBOOKS`（`=369`） | **375** | `assert total >= MIN_TOTAL_WORKBOOKS`（`=369`） |
| row 4 | `assert by_extension == {".xlsx":351,".xlsm":17,".xls":1}` + `sum == 369` | **.xlsx 352** | 逐后缀 `>= frozen_floor` + 扩展名集合等式 |

两条都保留了**结论侧的等式**（`EXPECTED_LEGACY_WRITER_WORKBOOKS = 10` / `legacy_writer == 10`），
只把「分母自检」改成下界 —— 正是仓库既有的 `assert derived >= 175` → `assert derived >= len(entries) * 9 // 10`
那个模式，且 docstring 里把 `d3b3d80d9` 的历史写进去了。**这个方向是对的，本次不回退。**

### 🔴 但 row 4 只差 +1，row 3 差了 +6 —— 多出来的 5 份必须交代

rows 1–2 已把语料变化归因到**一份**新模板。row 4 的 +1 与之完全吻合；row 3 的 +6 不吻合。
差额来自两条判据的**口径不同**（`backend/scripts/_c9_rows37_attrib.py census`）：

```
task42 口径 rglob('*.xls*')                    = 375
task43 口径 suffix in ['.xls','.xlsm','.xlsx'] = 370
by suffix (loose) = {'.xlsx': 352, '.xlsm': 17, '.bak': 5, '.xls': 1}
tracked xlsx/xlsm/xls in git = 370

只被 loose 口径计入的 5 份（= 非工作簿污染）：
  backend/wp_templates/D/D3 预收账款.xlsx.preclean.bak
     tracked=False  gitignore=.gitignore:139:*.bak
  backend/wp_templates/D/D4 收入底稿.xlsx.preclean.bak      （同上）
  backend/wp_templates/D/D5 应收款项融资.xlsx.preclean.bak   （同上）
  backend/wp_templates/D/D6 合同资产.xlsx.preclean.bak      （同上）
  backend/wp_templates/D/D7 合同负债.xlsx.preclean.bak      （同上）
```

`*.xls*` 是 glob 而不是后缀判定：它匹配「任意字符 + `.xls` + 任意字符」，所以
`X.xlsx.preclean.bak` 照样命中。这 5 份**既不被 git 跟踪，也被 `.gitignore:139 *.bak` 忽略**
⇒ 它们只存在于**本机工作树**。于是 row 3 的 `total` 是**机器相关**的：本机 375，干净
checkout / CI 上 370。把 375 冻成等式或下界都等于把本机的临时文件写进判据。

### 这 5 份 `.bak` 是谁写的：钉到具名脚本 + 具名 commit

写入点是 5 个净化脚本里同一行形态（`scripts/fix/sanitize_d{3,4,5,6,7}_template_external_links.py`）：

```python
bak = TEMPLATE.with_suffix(TEMPLATE.suffix + ".preclean.bak")   # d3 L162 / d4 L217 / d5 L141 / d6 L152 / d7 L161
if not bak.exists():
    shutil.copy2(TEMPLATE, bak)
```

`shutil.copy2` 保留源 mtime，所以 `.bak` 的 mtime（2026-05-26 / 2026-07-16）是**被拷贝模板的**
mtime，不是备份时刻 —— 不能用它定年。改用**字节**定年（`.bak` 是 `copy2` 字节拷贝而非重新
打包的 zip，故 sha256 对比合法，不违反「zip 不可跨运行复现」那条纪律）：

```
D3 预收账款.xlsx.preclean.bak   bak=8a27614bd761c1a8   1a0b55651~1=8a27614bd761c1a8  <<<< BAK == 此 revision
                                                       eed3a34ff  =8a27614bd761c1a8  <<<<
                                                       1a0b55651  =699a9be0e7da639f  = 磁盘现值 = HEAD
D5 应收款项融资.xlsx.preclean.bak  同形态（bak == 1a0b55651~1 == eed3a34ff）
D6 合同资产.xlsx.preclean.bak     同形态
D7 合同负债.xlsx.preclean.bak     bak=d522ac9fc60d12fb == 1a0b55651~1 == eed3a34ff；1a0b55651=0facd3fe2297dbf7=HEAD
D4 收入底稿.xlsx.preclean.bak    bak=ecac5d56775e10b0；该路径在 1a0b55651~1 / eed3a34ff 均 ABSENT，d3b3d80d9 起=b8fb92d4c22cd5d6
```

D3/D5/D6/D7 四份 `.bak` **字节等于 `1a0b55651~1`（也等于冻结点 `eed3a34ff`）**，而模板现值等于
`1a0b55651` ⇒ 这四份备份是 `1a0b55651`（2026-09-12「D 循环 5 个 canary 做实到
bidirectional_verified」）那一轮跑 `--apply` 时落下的，时间在 2026-09-06 冻结**之后**。
这正好解释了为什么冻结时 `rglob("*.xls*")` 还能等于 369。

### row 3 逐数对平（零残差）

| 时点 / 事件 | Δ | 归因（具名 commit + 具名文件） | `rglob("*.xls*")` |
|---|---|---|---|
| 冻结 `eed3a34ff` 2026-09-06 | — | 351 `.xlsx` + 17 `.xlsm` + 1 `.xls`，磁盘尚无 `.bak` | **369** |
| `1a0b55651` 2026-09-12 | +4 | `sanitize_d{3,5,6,7}_template_external_links.py --apply` 各写 1 份 `.preclean.bak`（untracked / gitignored） | 373 |
| `d3b3d80d9` 2026-09-14 | +1 | 新增 tracked 模板 `D/D4 收入底稿.xlsx`（= rows 1–2 的那一份） | 374 |
| D4 净化同一波 | +1 | `sanitize_d4_template_external_links.py --apply` 写 `D4 收入底稿.xlsx.preclean.bak` | **375** |

**残差 = 0。** 其中 tracked 工作簿 370（`git ls-files` 现算 = 370，与磁盘 strict 口径逐一相等），
本机临时文件 5。row 4 的口径只看后缀集合，故 `.bak` 完全不进它的分母 —— 它的 351→352 就是
rows 1–2 的那一个 +1，**残差同样 = 0**。

### 顺带证伪一个「巧合正确」

5 份 `.bak` 全是**可正常打开的 zip**，循环里 `ZipFile(...)` 不会抛异常，所以它们确实进了
`total`；只是按两种 legacy 检测口径都**不命中**：

```
D3/D4/D5/D6/D7 .preclean.bak   zip-ok  task42_legacy=False  task43_legacy=False
```

也就是说 `len(target_first) == 10` 现在成立是**运气**，不是设计：备份文件与被备份文件同属
一个逻辑工作簿，一旦某份 `.bak` 恰好是 legacy writer 形态，`target_first` 会把同一本册子
数两次，把「10」这个结论本身弄脏。这是收紧 glob 的第二个理由（第一个是机器相关）。

### 「ten」还是对的分母吗？—— 它根本不是分母

两个 node 名里的 `ten` 指的是**结论的分子**（legacy writer 形态实测 10 本），不是分母。分母是
语料总量。实测 10 本在收紧后的 370 本语料上**依然精确成立**（5 份 `.bak` 两种口径都不命中，
去掉它们不改变命中集合），且两条判据用**两个独立写法**的检测器（row 3 扫整个 rels 串，row 4
只看第一个 `<Relationship>`）都得出 10 ⇒ `ten` 保持**等式**是正确的，它是结论本身。
需要「现算派生」的是**分母**，而那正是下界修复已经做到的事。所以：
**不改 `10`，只把 `total` 的口径从 `*.xls*` 收紧到真工作簿后缀。**

### 处置：row 3 收紧 glob（row 4 无需改动）

row 4 的下界修复是正确的，**不动**。row 3 只改语料口径（新增 `WORKBOOK_SUFFIXES` 常量，
把 `rglob("*.xls*")` 换成「遍历 + 后缀集合过滤」，与 row 4 同口径），`MIN_TOTAL_WORKBOOKS = 369`
下界与 `EXPECTED_LEGACY_WRITER_WORKBOOKS = 10` 等式**都保持不变**。改完 `total` 现算 370，
与 `git ls-files` 的 tracked 工作簿数相等 ⇒ 机器无关。

### 变异验证（`backend/scripts/_c9_rows37_mutate.py`）

**绝不动真语料**：把 370 份真工作簿复制到临时目录，在**副本**上扰动，并把两条判据的语料根
monkeypatch 到副本（row 3 打 `pilot_h1_grouped_dynamic.authoritative_template_path`，
row 4 打测试模块的 `_BACKEND`）。

```
权威模板 = H/H1 固定资产.xlsx ；副本工作簿数 = 370

=== BASELINE（副本未扰动）===        row 3: GREEN      row 4: GREEN
=== M1 藏掉 2 份非 legacy（370→368）===
  row 3: RED — 语料只扫到 368 个工作簿，少于冻结下界 369
  row 4: RED — .xlsx 少于冻结下界 351（实测 350）
=== M1 还原后 ===                    row 3: GREEN      row 4: GREEN
=== M2 藏掉 1 份 legacy（10→9）===
  row 3: RED — ['A17  重大事项概要程序表.xlsx', …]（命中集合少一本）
  row 4: RED — 9
=== M3 放入 `G7 长期股权投资.xlsx.preclean.bak` ===
  row 3（新后缀口径）: GREEN         row 4: GREEN
  旧口径 `*.xls*` 在同一副本上现算 legacy 命中 = 11（≠10 ⇒ 旧口径确实会被备份污染）

=== 变异验证汇总：11/11 条符合预期 ===
```

**M1 证明分母下界是活的**（不是永真），**M2 证明「10」这条结论等式是活的**，
**M3 证明本次收紧不是洁癖**：旧口径下只要有一份 legacy 形态的 `.bak` 落在语料里，
`legacy_writer` 就变 11 打假红 —— 本机现存的 5 份恰好都不是 legacy 形态，纯属运气。

还原验证：

```
$ git status --porcelain backend/wp_templates      # 空 ⇒ tracked 字节未变
$ .preclean.bak 计数 = 5   *.hidden 计数 = 0   工作簿计数 = 370
```

---

## C9-6 / C9-7 —— 行身份划分（`TestProperty23DynamicRowIdentity`）

### 🔴 先回答「未归族的新案例是什么」——**不存在未归族案例**

任务指引预期这里是「出现了不属于任何族的新案例」。**实测不是。** 拿 **HEAD 版** slice 对
**当前源码**跑同一套扫描（`_c9_rows37_attrib.py row-identity-red`，只读，不动工作树）：

```
=== HEAD 版 slice ===
  total_hits 声明 = 17   实测 = 17
  family_a=3(声明3) family_b=6(声明6) family_c=8(声明8)
  仅在声明里 (1): ['…/composables/useH4Recoverable.ts#L313']
  仅在实测里 (1): ['…/composables/useH4Recoverable.ts#L314']
      实测未归族: …/useH4Recoverable.ts#L314  ->  rowId: `cf-${c.year || i + 1}`,
=== 工作树版 slice ===
  total_hits 声明 = 17   实测 = 17
  仅在声明里 (0): []     仅在实测里 (0): []
```

`total_hits` 17 没变，三族 3 + 6 + 8 = 17 也一个没变。「仅在实测里」那一条
（`rowId: \`cf-${c.year || i + 1}\``）**就是**「仅在声明里」那一条 —— 同一个逻辑命中，
同一族（family_c），只是行号从 313 变 314。判据用的是 `路径#L行号` 集合做差集，所以
**1 行的位移会同时表现为「少了一个旧案例」+「多了一个新案例」**，读起来像穷举性被破坏，
实际上划分从未被破坏。

⇒ 判决 **STALE ANCHOR**，不是 REAL CHANGE，也不是 REGRESSED IMPLEMENTATION。
**没有任何桶被放宽**：三族计数与 `forbidden_identity_kinds` 一字未动。

### 两条红各自的 +1 行，钉到具名 commit 与具名文件

**row 6** —— `useH4Recoverable.ts` 整体下移 1 行：

```
$ git log --format='%h %ad %s' --date=short -2 -- …/composables/useH4Recoverable.ts
7b65c77b9 2026-09-03 fix(frontend): 逐一修复 13 处一打开就崩的悬空引用与 8 处缺失类型导入
856625b43 2026-07-22 chore: batch commit all local changes …

$ git show 7b65c77b9 --unified=2 -- …/useH4Recoverable.ts
@@ -12,4 +12,5 @@
+import type { H4RecoverableSourceKind, H4SensitivityRow } from './h4RecoverableModel'
```

`7b65c77b9` 在第 13 行**只加了一行** `import type` ⇒ 其下全部内容 +1 行 ⇒ L313 → L314。
净行数 +1，与观测位移完全相等，**残差 = 0**。

**row 7** —— `GtH4EngineeringMaterials.vue` 整体下移 1 行：

```
$ git show afdcbf0cc --unified=3 -- …/GtH4EngineeringMaterials.vue
@@ -266,7 +266,8 @@ const {
  -   writebackTrialBalance,
  +   // 注：writebackTrialBalance 已从 useH4FormData 移除（零消费死代码，此前 destructure 从不调用）；
  +   // TB 回写走 H4TabAdjudication 显式发布门。spec: tb-writeback-explicit-publish-gate Task 17。
net line delta in this commit = 1

afdcbf0cc~1   L383= allResponses.value.set('H4-2-rows', {          | L384= item_id: 'H4-2-rows',
afdcbf0cc     L383= // 内存态写入（未编辑不落库，composable 的 watch 会消费）| L384= allResponses.value.set('H4-2-rows', {
HEAD          L383= // 内存态写入（…）                              | L384= allResponses.value.set('H4-2-rows', {
```

`afdcbf0cc`（2026-09-14「Task 17 死代码集中清理(TB回写零消费writeback)」）把 1 行
`writebackTrialBalance,` 换成 2 行注释 ⇒ **净 +1 行** ⇒ 写入点 L383 → L384，而 L383 变成注释。
判据 `assert key in site_line` 于是在注释行上找 `H4-2-rows` 找不到 ⇒ RED。实测复现：

```
  [HEAD]  …/GtH4EngineeringMaterials.vue#L383  key=H4-2-rows  行内含键=False
          实际该行: // 内存态写入（未编辑不落库，composable 的 watch 会消费）
  [工作树] …/GtH4EngineeringMaterials.vue#L384  key=H4-2-rows  行内含键=True
```

**残差 = 0。** 两条红各由**一个**具名 commit 的**一行**净增量解释，没有任何一条命中需要
用「不知道哪来的」解释。

### 处置：工作树里的重锚是对的，不改；本次只复核 + 变异验证

`git diff backend/data/workpaper_sync_h_cycle_manifest_slice.json` 里 `dynamic_row_identity`
段的改动**全部**是 `#L313→#L314` / `#L383→#L384` 这类行锚重锚（另有 H3/H5 的
`endpoint_write_source` 等同类重锚），`count` / `total_hits` / `registered_as` / 族归属
一个字未改 ⇒ 是正确的重锚，不是放宽。**本次不追加改动。**

### 变异验证（`backend/scripts/_c9_rows67_mutate.py`）

不动仓库任何前端源：把 `components/workpaper/` 整棵子树（5,975 个文件）复制到临时目录，把
测试模块的 `ROOT` / `FRONTEND` / `WP_COMPONENTS` / `COMPOSABLES` 指向副本；声明侧
`MANIFEST_SLICE_PATH` 仍读**真** slice ⇒ 变的是「被断言的真东西」，不是断言本身。

```
副本文件数 = 5975（源 5975）
=== BASELINE（副本未扰动）===   row 6: GREEN   row 7: GREEN
=== M1 在 useH4Recoverable.ts 的 L300 之上插一行（L314 → L315）===
  row 6: RED — 位置化清单与实测集合不等：
  row 7: GREEN（只看 family_a 的三个 writes_to_key_site，不含本文件 ⇒ 预期如此）
=== M1 还原后 ===               row 6: GREEN
=== M2 在 GtH4EngineeringMaterials.vue 的 L300 之上插一行（写入点 L384 → L385）===
  row 7: RED — …/h4DetailPrefill.ts#L50: writes_to_key_site 指向的行不含键 'H4-2-rows'（实际 '// …）
=== M2 还原后 ===               row 7: GREEN

=== 变异验证汇总：7/7 条符合预期 ===
```

两条判据都**对 1 行位移敏感**（这既是它们的强度，也正是本次两条红的成因）。还原验证：
`git status --porcelain` 对两份前端源为空，`_c9 mutation` 残留行数 = 0。

---

## C9-5 —— BP-5 复现判据

> node（判决表 row 5 列的原名）：`test_bp5_wrong_workbook_fallback_is_reproducible`
> 本次**换向并改名**为 `test_bp5_whole_code_fallback_is_fixed_and_unambiguous`，理由见下。
> 排在 C9-6/7 之后是因为它是本簇唯一需要动代码的一行，留在最后收口。

### 实测输出（verbatim，BEFORE）

```
_ TestProperty28DefinitionDriftFailClosed.test_bp5_wrong_workbook_fallback_is_reproducible _
tests\workpaper_sync\test_task48_f_cycle_migration.py:1259: in test_bp5_wrong_workbook_fallback_is_reproducible
    assert fallback.name == "F2-16 存货及跌价准备-会计政策（Leap-常规程序）.xlsx", (
E   AssertionError: F2 整册码回落实测返回 'F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx'
E     —— 与 BP-5 描述不符。若解析器已修好，请更新 BP-5 的 status 与本判据
1 failed, 81 passed, 1 warning in 7.04s
```

这条判据断言的是**缺陷仍可复现**。它红了，所以第一问必须是「缺陷是不是被修好了」，
而不是「怎么让它重新复现」。

### 🔴 结论：缺陷被**真修**了，而且是**有意**修的；不是 `82f58ea44` 的碰撞

BP-5 说的是「**整册码** `find_template_file('F2')` 会打开会计政策册」。实测：

```
  BP-5 声称回落返回 : F2-16 存货及跌价准备-会计政策（Leap-常规程序）.xlsx
  实测回落返回     : F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx
  F2 核心组 template_ref = F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx
  => 回落 == 核心组 template_ref ? True
```

**判据自己预先写好的反向锁就是这个判定标准**：

```python
assert fallback.name != expected, (
    "回落结果与 F2 核心组的 template_ref 相同 ⇒ BP-5 描述的缺陷不存在，不得虚报"
)
```

作者事先承诺了「回落 == template_ref ⇒ 缺陷不存在」。该条件现已满足 ⇒ 按判据自身的契约，
**BP-5 描述的缺陷不存在了**，继续把它当「可复现缺陷」就是虚报。

### 归因：`82f58ea44` 的 `_PRIMARY_TEMPLATE_TIERS`，**不是** `_PROGRAM_TABLE_CODE_RE`

`backend/app/services/wp_template_finder.py` 上两个机制的出现时点（`_c9_rows37_attrib.py bp5`）：

```
  eed3a34ff    _PRIMARY_TEMPLATE_TIERS=no  _pick_by_tier=no  _PROGRAM_TABLE_CODE_RE=no
  82f58ea44    _PRIMARY_TEMPLATE_TIERS=YES _pick_by_tier=YES _PROGRAM_TABLE_CODE_RE=YES
  891aec512    （同上，全 YES）
  HEAD         （同上，全 YES）
```

两个机制**同一个 commit 进来**（`82f58ea44` 2026-09-13「feat(d4-ipo): D4 IPO/价格分析/四表取数/公式治理 综合交付」），
但**作用在不同的码上**，必须分开看：

| 机制 | 作用对象 | 影响的判据 |
|------|---------|-----------|
| `_PRIMARY_TEMPLATE_TIERS` + `_pick_by_tier` | **整册码**（`F2`、`D4`）的候选优先级 | **本行 row 5（BP-5）** |
| `_PROGRAM_TABLE_CODE_RE = ^([A-Z]+\d+)A$` | **程序表码**（`H2A`/`D4A`/`F2A`）回落到主册 | `test_task50::…::test_template_resolution_audit_recomputes`（**别的簇**） |

`"F2"` 不带尾字母 `A`，`_PROGRAM_TABLE_CODE_RE` 根本不匹配它 ⇒ **BP-5 与那条「已发布特性撞已发布守卫」的碰撞无关。**
任务书提示的碰撞确有其事，但它落在 `find_template_file("H2A")` 那条判据上（实测返回
`H/H2 在建工程.xlsx`，见本文件上方「其余红不属本簇」表），**不是 row 5**。

修复是**有意为之**，生产代码注释里点名了 F2：

```python
#: 🔴 「审定」必须**严格高于**「常规程序」，不能像原来那样 `or` 成同一级：
#: … D4-12 …（Leap-常规程序）.xlsx 排在 D4-1至D4-4 … 审定表明细表（Leap-常规程序）.xlsx
#: 之前，两者都含「常规程序」⇒ 同级下由**索引顺序**决定结果，D4 拿到了「合同检查」。
#: F2 同理拿到了「会计政策」。
#: 用「审定」而不是「审定表」：F2 的主表叫「审定**明细**表类」，不含连续三字「审定表」。
_PRIMARY_TEMPLATE_TIERS: tuple[str, ...] = ("审定", "常规程序")
```

第三行「F2 同理拿到了「会计政策」」= BP-5 的 `what` 逐字对应；第四行专门为 F2 把层级 token
从「审定表」放宽成「审定」。作者知道 F2 坏了，并且**针对 F2 调了 token**。

### 机制逐一对平（零残差）：为什么结果从「会计政策」变成「审定明细表类」

`find_template_file` 的精确匹配分支先按 `_index.json` 筛 `wp_code == "F2"` 且
`format in ("xlsx","xlsm")`，再交给 `_pick_by_tier`。实测候选与分层
（`_c9_rows37_attrib.py f2-tier`）：

```
_index.json 里 wp_code=='F2' 的候选 = 10 条（全 xlsx，全 exists=True）
_PRIMARY_TEMPLATE_TIERS = ('审定', '常规程序')
  层 '审定'     命中 1 条: ['F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx']
  层 '常规程序' 命中 3 条: ['F2-16 …会计政策（Leap-常规程序）.xlsx',
                            'F2-1至F2-14 …审定明细表类（Leap-常规程序）.xlsx',
                            'F2-52 …关联交易（Leap-常规程序）.xlsx']
```

* **旧行为**：「审定表 or 常规程序」同级 ⇒ 3 条同时命中 ⇒ 胜出者由**索引顺序**决定，
  `F2-16 会计政策` 排在最前 ⇒ 返回会计政策册。**这正是 BP-5 描述的第 3 条
  `observable_consequences`（「被 4 本同时命中的册子稀释，胜出者只由索引顺序决定」）。**
* **新行为**：第一层「审定」**只有 1 条**命中 ⇒ 语义唯一确定 ⇒ 返回审定明细表类册，
  且与核心组 `template_ref` 一致。

子码解析未被这层改动吞掉（这是 BP-5「只在回落路径暴露」那个限定的另一半）：

```
  find_template_file('F2-16') = F2-16 存货及跌价准备-会计政策（Leap-常规程序）.xlsx
  find_template_file('F2-21') = F2-21至F2-26 …盘点类（Leap应对措施- 存货监盘）.xlsx
  find_template_file('F2-38') = F2-38至F2-44 …计价测试（Leap-存货程序）.xlsx
  find_template_file('F2-47') = F2-47至F2-49 …跌价准备测试（Leap应对措施-会计估计）.xlsx
  find_template_file('F2-1')  = F2-1至F2-14 …审定明细表类（Leap-常规程序）.xlsx
```

**残差 = 0**：从「会计政策」到「审定明细表类」这一个行为变化，完全由
`82f58ea44` 引入的 `_PRIMARY_TEMPLATE_TIERS` 第一层「审定」的 1 条唯一命中解释，
不需要任何其它变更参与。

### 顺带修正 BP-5 / BP-8 prose 里的一个数（非承重）

两条 BP 都写「索引里 wp_code=='F2' 有 **11** 条候选」，实测 **10** 条。
`backend/wp_templates/_index.json` 自 `71ca5f233`（2026-05-15）起未再改动，而 F slice 冻结于
`42d2f6e6f`（2026-09-02）⇒ 这不是漂移，是**当时就写错的 prose**。同一条 BP-8 里「15 条 F
索引项」实测 = 15 ✅ 相符。10 还是 11 不改变任何结论（稀释仍然发生、合册仍然不可达），
故只在此记录、随 BP-5 改写一并订正。

### 处置：退役复现判据，换成「已修且不许回归」的三重锁

判据改名 `test_bp5_wrong_workbook_fallback_is_reproducible`
→ **`test_bp5_whole_code_fallback_is_fixed_and_unambiguous`**，锁三件事 + BP-5 登记状态：

| # | 锁什么 | 破裂时的含义 |
|---|-------|------------|
| ① | 回落结果 == 核心组 `template_ref` | 修复被改坏（又选错册） |
| ② | 第一层「审定」在 F2 候选集里**恰好命中 1 条** | 命中 0 ⇒ 掉回第二层被 3 本稀释（原缺陷）；命中 ≥2 ⇒ 层内又由 `(len, name)` 排序决定（**潜伏形态复发**） |
| ③ | 子码 `F2-16` 仍解析到会计政策册本身 | 「审定」层把子码解析也吞了 = 过度修复 |
| ④ | BP-5 `status` 以 `PARTIALLY_FIXED` 开头 **且** 有 `still_not_fixed` | 行为已修而 slice 仍写未修（虚报）；或悄悄销号 |

slice 侧 BP-5 的改动（**不销号，只降级**）：
`status` `REGISTERED_NOT_FIXED` → `PARTIALLY_FIXED_WHOLE_CODE_FALLBACK_NOW_RESOLVES_CORRECTLY`
（`PARTIALLY_FIXED_*` 是本仓既有词汇，现存 5 条用它），并新增
`status_amendment_2026_09_23`（归因到 `82f58ea44`，并显式声明与 `_PROGRAM_TABLE_CODE_RE` 无关）、
`still_not_fixed`（**哪一半没修**：F2 约 60 个 sheet 仍无 sheet→模板映射，回落路径上
「看到的是本表」仍不成立，只是错得没那么远）、`latent_regression_shape`。

**为什么是 PARTIALLY 而不是 FIXED**：BP-5 的 `what`（选错册）已修；但回落**路径本身**还在，
用户处在 F2-21/F2-38/F2-47 而尾码提不出子码时，打开的仍不是本表。`consequence` 那一半未兑现，
所以降级不销号，`capability_target_blocked_by` 对 BP-5 的引用**原样保留** ——
F2 能否转 bidirectional 是 capability 裁决，不在本簇权限内。

### 变异验证（`backend/scripts/_c9_row5_mutate.py`）

不改任何生产源字节，全部 monkeypatch 内存态：

```
=== BASELINE（未扰动）===            row 5: GREEN
    实测 find_template_file('F2') = F2-1至F2-14 …审定明细表类（Leap-常规程序）.xlsx
=== M1 `_PRIMARY_TEMPLATE_TIERS` 退回旧形态 ('常规程序',) ===
    实测回落 = F2-16 存货及跌价准备-会计政策（Leap-常规程序）.xlsx
  row 5: RED — F2 整册码回落实测返回 'F2-16 …会计政策…'，应为核心组 template_ref …
=== M1 还原后 ===                    row 5: GREEN
=== M2 索引注入第二本含「审定」的 F2 册子 ===
  row 5: RED — 第一层 '审定' 在 F2 的 11 个候选里命中 ['F2-1至F2-14 …', 'F2-99 …审定补充表（人为注入）…']
=== M2 还原后 ===                    row 5: GREEN
=== M3 slice 的 BP-5 status 改回 REGISTERED_NOT_FIXED ===   row 5: RED
=== M4 删掉 BP-5 的 still_not_fixed ===                      row 5: RED
=== 全部还原后最终复核 ===            row 5: GREEN

=== 变异验证汇总：8/8 条符合预期 ===
```

🔴 **M1 是本行归因的决定性证据**：只把 `_PRIMARY_TEMPLATE_TIERS` 退回旧形态（不动任何别的
东西、不动一个字节的模板），`find_template_file('F2')` 就**精确复现**出 BP-5 原文描述的
`F2-16 存货及跌价准备-会计政策（Leap-常规程序）.xlsx`。⇒ 该常量是这次行为变化的
**唯一**原因，**残差 = 0**；也同时证明断言①不是永真。
M2 证明「唯一命中」这个前提是被真检查的（潜伏复发可检出），M3/M4 证明 slice 登记侧是双向锁。

---

## 顺带结清 rows 1–2 留下的「待澄清」：D4 同名双份是什么关系

rows 1–2 把 `D/D4收入底稿.xlsx`（无空格）与 `D/D4 收入底稿.xlsx`（有空格）并存列为遗留项，
猜测「像是同一份底稿的重复入库」。本次归因 `.preclean.bak` 时顺带测到了确切关系
（`_c9_rows37_attrib.py bak-shape`）：

```
  有空格(已净化)   D4 收入底稿.xlsx               199176 B  sha=b8fb92d4c22cd5d6  externalLinks部件=2
  无空格           D4收入底稿.xlsx                352950 B  sha=ecac5d56775e10b0  externalLinks部件=36
  .preclean.bak    D4 收入底稿.xlsx.preclean.bak  352950 B  sha=ecac5d56775e10b0  externalLinks部件=36
  → 无空格 == .preclean.bak ? True
```

`sanitize_d4_template_external_links.py` 的 `TEMPLATE` 常量指向**有空格**那份，其
`.preclean.bak` 又与**无空格**那份**字节完全相同** ⇒ 关系是：
**有空格那份是无空格那份的「拷贝后就地净化」产物**，无空格原件留在库里**未净化**
（仍带 36 个 `xl/externalLinks/` 部件）。

所以不是「重复入库」，是「净化时另存了一份新名字，旧名字没退场」。`wp_template_finder.py`
第 140~143 行的注释已经记着这件事。**仍然不由本簇处置**（本次不删任何模板字节），但遗留项的
性质从「不明重复」收敛成「净化留下的未退场原件」—— 对应的处置是 BP-8 那一类
「权威目录内不可达冗余模板清理」，owner 待立项。

---

## 跨簇上报（本次实证，但**不是**本簇的 5 个 node，未处置）

`test_task50_h_cycle_migration.py::TestProperty28DefinitionDriftFailClosed::test_template_resolution_audit_recomputes`

```
E   AssertionError: H2A 这类程序表码不该解析出独立模板 —— program_table_code_note 的前提失效
E   assert WindowsPath('D:/GT_plan/backend/wp_templates/H/H2 在建工程.xlsx') is None
```

**这才是任务书提示的那个碰撞。** `82f58ea44` 引入的
`_PROGRAM_TABLE_CODE_RE = ^([A-Z]+\d+)A$` 让程序表码回落到主册，实测：

```
  find_template_file('H2A') = H2 在建工程.xlsx      （判据要求 None）
  find_template_file('D4A') = D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx
  find_template_file('F2A') = F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx
```

判据那一侧的理由写得同样明确（「这些码在 finder 上解析不到任何文件」被当作可打红判据，
「零回退的最强形态是根本没有回退」）⇒ **已发布特性 vs 已发布守卫，两边都有署名理由**。
这是**裁决**，不是分诊能单方面定的：要么承认程序表码回落是设计（改判据），要么承认它破坏了
契约 source_ref 的唯一性（给 `_PROGRAM_TABLE_CODE_RE` 加 render-schema 例外或退回）。

**判决：BLOCKED —— 需裁决。** owner 建议 = `82f58ea44` 的作者（D4 IPO 交付）与
Task 50 H 循环判据作者，并与 BP-5 的 `owner_task`（「待立项：D slice BP-5 / E slice G1 /
F slice BP-5 三处并为一个解析器 spec」）并案 —— 三者都是同一个
`find_template_file` 优先级链 + 回落链上的问题。本簇**不动它**。

---

## C9 rows 3–7 —— 逐文件最终计数（AFTER）

```
test_task42_h1_grouped_dynamic_pilot.py    1 failed, 143 passed  in 13.74s
test_task43_g7_two_level_dynamic_pilot.py  1 failed, 204 passed  in 27.19s
test_task48_f_cycle_migration.py           0 failed,  82 passed  in  5.89s   ← 本簇修掉 1 条
test_task50_h_cycle_migration.py           3 failed, 101 passed  in 40.86s
```

BEFORE → AFTER 对照，以及每条残留红的归属：

| 文件 | BEFORE | AFTER | 本簇负责的 node | 残留红归属 |
|------|--------|-------|----------------|-----------|
| test_task42 | 1F / 143P | 1F / 143P | row 3（进场时已绿，本次收紧口径后仍绿） | `TestPilotIntroducesNoResolverDebt::test_no_function_in_this_module_is_classified_as_writer_or_resolver`（327 vs 371）= manifest 漂移簇 |
| test_task43 | 1F / 204P | 1F / 204P | row 4（进场时已绿，本次只复核 + 变异） | `TestProductionWiring::test_generator_is_the_only_writer_of_the_disk_contract`（`['write_bytes']`）= 其他簇 |
| test_task48 | 1F / 81P | **0F / 82P** | row 5（**本次修掉**） | — |
| test_task50 | 3F / 101P | 3F / 101P | rows 6、7（进场时已绿，本次只复核 + 变异） | `TestOrphanLegacyComposables::…no_production_consumer`、`TestProperty70NoCrossEntryReuse::…distinct_and_real`（427 vs 401）= 其他簇；`TestProperty28DefinitionDriftFailClosed::test_template_resolution_audit_recomputes` = **`82f58ea44` 碰撞簇，BLOCKED 待裁决**（见上节）

未按任务书预期出现「`TestOrderingGate` / `TestFrozenEntrySelection` /
`TestContractIsGroundedInTheTemplate`」的红 —— 它们进场时已绿（由其它 agent 修好），本次未触碰。

### 本簇改动清单（4 个文件 + 4 个一次性脚本）

| 文件 | 改了什么 |
|------|---------|
| `backend/tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py` | 新增 `WORKBOOK_SUFFIXES` 常量（带完整成因注释）；`rglob("*.xls*")` → 遍历 + 后缀过滤。`MIN_TOTAL_WORKBOOKS=369` 与 `EXPECTED_LEGACY_WRITER_WORKBOOKS=10` **未动** |
| `backend/tests/workpaper_sync/test_task48_f_cycle_migration.py` | `test_bp5_wrong_workbook_fallback_is_reproducible` → `test_bp5_whole_code_fallback_is_fixed_and_unambiguous`，改锁「已修 + 唯一命中 + 未过度修 + slice 已降级」四件事 |
| `backend/data/workpaper_sync_f_cycle_manifest_slice.json` | BP-5：`status` 降级为 `PARTIALLY_FIXED_WHOLE_CODE_FALLBACK_NOW_RESOLVES_CORRECTLY`，新增 `status_amendment_2026_09_23` / `still_not_fixed` / `latent_regression_shape`；`what` 里 11→10 订正。**`capability_target_blocked_by` 原样保留** |
| 本文件 | rows 3–7 判决 + 分析 |
| `backend/scripts/_c9_rows37_attrib.py` | 归因取证（`census` / `bak-provenance` / `bak-shape` / `row-identity-red` / `bp5` / `f2-tier`），**只读** |
| `backend/scripts/_c9_rows37_mutate.py` | rows 3–4 变异（真语料复制到临时目录后扰动） |
| `backend/scripts/_c9_rows67_mutate.py` | rows 6–7 变异（前端子树复制到临时目录后扰动） |
| `backend/scripts/_c9_row5_mutate.py` | row 5 变异（全 monkeypatch 内存态） |

4 个 `_` 前缀脚本是一次性取证件，可随时删；保留的唯一理由是本文件里
「11/11、7/7、8/8」三组变异结论需要可复跑。

### 纪律自检

* `git status --porcelain backend/wp_templates` **空** ⇒ 权威模板字节全程未变；
  `.preclean.bak` 仍恰好 5 份，`*.hidden` 残留 0 份，工作簿仍 370 份。
* 变异全部在**临时目录副本**或**内存 monkeypatch** 上做，从未改动 `backend/wp_templates/`
  与任何前端源（`git status` 对 `useH4Recoverable.ts` / `GtH4EngineeringMaterials.vue` 为空，
  `_c9 mutation` 残留 0 行）。
* 未运行 `backend/scripts/ops/setup_wp_templates_dir.py`；未运行整套 `tests/workpaper_sync`；
  未触碰任何 `*_pg.py`（`git status` 里那 7 个 `_pg.py` 的修改是并发 agent 的，不是本簇的）。
* 未使用 `git stash` / `git checkout --` / `git reset`；历史对照全部走 `git show <rev>:<path>` 只读。
* zip 制品**未做跨运行 sha256 对比**：唯一用到 sha256 的地方是 `.preclean.bak` 与 git blob 的
  比对，那两侧都是**既存字节的拷贝**（`shutil.copy2` / git object），不是重新打包的 zip。

## C8 —— 真库形态

> 5 个节点分属三个文件、四类成因。共同点与 C9 相同：断言对象在测试树之外（`audit_platform`
> 真库的行），所以第一问仍是「断言过期，还是被断言的真东西真的变了？」
>
> **实测结论先行**：5 个节点**没有一个**是 REGRESSED IMPLEMENTATION。三个是真库内容真的
> 变了（两个已按「量纲换口径」处置完毕、一个拒绝放宽），一个是真库内容被**我们自己的
> 取证探针**写脏，一个压根不属于本簇（capability 翻转的下游）。

### 实测输出（verbatim，BEFORE）

```
$ ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py -q --tb=short -rf -p no:randomly
.....................................                          [100%]
37 passed, 1 warning in 28.14s
```

```
$ ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot_pg.py -q --tb=short -rf -p no:randomly
..FF.............................                                     [100%]
_______ test_disposal_store_item_is_empty_across_the_whole_database ________
tests\workpaper_sync\test_task42_h1_grouped_dynamic_pilot_pg.py:939: in test_disposal_store_item_is_empty_across_the_whole_database
    assert len(real["disposal_rows"]) == EXPECTED_DISPOSAL_ROWS_WORKPAPERS == 0, real[
E   AssertionError: [{'bytes': 51, 'wp_id': 'c71b7c54-6868-4fb9-9e14-083034f57815'}]
E   assert 1 == 0
______________ test_contract_declares_the_observed_emptiness _______________
tests\workpaper_sync\test_task42_h1_grouped_dynamic_pilot_pg.py:953: in test_contract_declares_the_observed_emptiness
    assert real["disposal_total_bytes"] == 0
E   assert 51 == 0
2 failed, 31 passed, 1 warning in 12.28s
```

```
$ ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py -q --tb=short -rf -p no:randomly
.................F....                                                [100%]
_ TestBindingConstraintIsMeasured.test_the_three_arms_really_run_against_the_database _
tests\workpaper_sync\test_task61_oo94_word_pilot_gate.py:1579: in test_the_three_arms_really_run_against_the_database
    assert arm_a["registered_adapter_ids"] == []
E   AssertionError: assert ['d2.receivab...sposal_check'] == []
E     Left contains 4 more items, first extra item: 'd2.receivable_detail'
1 failed, 159 passed, 5 warnings in 42.68s
```

🔴 **两条口径更正**（任务书里的读数与实测不一致，先摆正再分诊）：

1. 第 8/9 号节点（`test_task41_..._pg.py`）**当前是绿的**，不是红的。该文件有未提交改动
   （`git status` = ` M`），把尺寸等式换成了「信息量下界 + 排版开销上限」。所以这两条我的
   工作是**复核别人已落的处置是否是洗绿**，而不是重新修。复核结论见下（结论：处置方向
   正确，但**归因文字算错了一笔**，已修正）。
2. 第 12 号节点空的那一侧是**断言**而不是观测：`registered_adapter_ids` 实测是**非空的
   4 个** adapter，`== []` 是冻结期望。所以不存在「真库侧缺行 vs 读路径过期」这个二选一
   —— 读路径完全活着（见下文逐项对齐），是**前提翻转**。

---

### C8-8 —— D2 真实载荷尺寸（`test_real_store_payload_is_the_frozen_866kb_shape`）

**判决：REAL CHANGE**（真库那一行真的变了；已落的处置正确，归因文字我改了一处算错）

#### 冻结基线的出处（不是凭记忆）

`.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/`
`task41-d2-large-json-pilot/real_payload_facts.json`（2026-09-06 实测）存了**结构性事实**：
`payload_bytes 906,239` / `total_remark_bytes 915,155` / `d2_item_count 24` /
`payload_sha256 6c5d6d4c…` / `row_count 1260` / `keys_per_row 25` / 逐键 `non_empty_counts`。
它刻意不含业务值，所以旧**字节**无法还原，但旧**计数**可以逐键对账 —— 下面全部基于它。

#### 现测（只读 `public.checklist_responses`，`wp_id=e2c95d10-…edd1`）

```
stored_bytes            = 1009966
compact_bytes           =  905387   (separators=(',',':'))
python_default_bytes    = 1009966   (json.dumps 默认 ', ' / ': ')
stored == python_default? True          ← 逐字节吻合
whitespace_bytes        =  104579
updated_at              = 2026-09-10 08:07:46.809272+00
rows = 1260 / distinct rowId = 1260 / distinct key-sets = 1 (keys_per_row=25)
```

#### 归因① 排版：+103,727 字节，零信息增量

`stored == json.dumps(parsed, ensure_ascii=False)` **逐字节为 True** ⇒ 库里这一行现在的
文本就是 Python 默认分隔符（`", "` / `": "`）的产物。排版空白 = 1,009,966 − 905,387 =
**104,579** 字节。形态侧同时**全部未动**：1260 行、1260 个不重复 `rowId`、每行 25 键、
键集合只有 1 种。

🔴 并且这个「紧凑口径」是**写入方无关**的 —— 我验了 Python 紧凑与 JS `JSON.stringify`
口径在这份数据上**完全相等**（905,387 == 905,387），因为整个载荷里**整数值 float 有 0 个**
（`.0` 这类 Python/JS 分歧点一个都没踩到）。所以拿紧凑字节当「信息量」不依赖「上次是谁写的」
这个未知量，这个量纲是站得住的。

#### 归因② 信息量：−852 字节 —— 🔴 这里原归因算错了，已改

已落改动的注释写的是「剩下 −852 字节是一次真实编辑（`debitOccurrence` 非空数 1093 -> 1092）」。
**那一笔编辑是真的，但它解释不了 852 字节**：

* 逐键 truthy 计数对账（与 evidence 同谓词），**只有一个键变了**：
  `debitOccurrence` 1093 → 1092（falsy 行 167 → 168，多出来那格现值 `0`）。
  其余 `creditOccurrence 1131` / `currentAudited 750` / `currentUnadjusted 750` /
  `customerName 1260` / `endBalance 750` / `priorAudited 751` / `priorUnadjusted 751` /
  `relationType 1260` / `rowId 1260` / `seq 1260` **逐项相等**。
* 但 `debitOccurrence` 的单值紧凑序列化长度 **min=2 / max=18**。一格从最长值变成 `0`
  最多省 **17** 字节。⇒ **−852 在量级上不可能来自这一格**，差了 50 倍。

我能证到的是**差额被关进了「值字节」**（这一步是精确的，不是估算）：

```
结构字节 = 496441   （25 个键名+冒号+逗号+括号，逐行恒定 × 1260 行 + 行间逗号 + [ ]）
值字节   = 408946
合计     = 905387   ← 与实测 compact 逐字节相等，残差 0
```

键集合只有 1 种、行数不变 ⇒ **结构字节是常量**，所以 906,239 → 905,387 的 −852
**全部落在值字节里**。同时 aging 三组 1260×3 个 dict 的序列化长度 **min=max=63**（即
`{"within1":0,…,"over5":0}` 全零形态，22,680 个叶子一个都没填），也是常量，不参与差额。

⇒ **诚实的边界**：`−852` 是一次**真实内容编辑**（同形态、同行数、同键集合，只有值变短），
与排版无关；但**不能再往下逐键分解**，因为 2026-09-06 的 evidence 记的是「计数 + 类型」
而**没记逐键字节**，而旧字节已被 2026-09-10 那次保存覆盖。truthy 计数这个谓词太粗：
一格从 `1234567.89` 改成 `1234567.9` 会少 1 字节而计数不变，这类变化它一个都抓不到。

#### 归因③ 其余 item：−2 字节，逐条对平，残差 0

```
= 22 条 item 与 2026-09-06 冻结清单**逐条字节相等**
! D2-detail-audit-note   1656 -> 1652   −4   updated=2026-09-10 08:07:52  ← 与载荷同一次保存（相隔 6 秒）
! D2-entry-rows          （不存在）-> 2  +2   updated=2026-09-11 02:03:48  ← 新开分区产生的空 item `[]`
其余 item 合计: 8916 (23 条) -> 8914 (24 条)      逐条 delta 合计 = −2   合计差 = −2   对平残差 = 0
item_count: 24 -> 25
```

#### 逐数对平

| 冻结键 | 冻结值 | + 排版 | + 真实编辑 | + 新空 item | = 应得 | 实测 | |
|--------|--------|--------|-----------|------------|--------|------|--|
| `payload_bytes`（stored） | 906,239 | +104,579 | −852 | — | 1,009,966 | 1,009,966 | ✅ |
| `payload_compact_bytes` | 906,239 | +0 | −852 | — | 905,387 | 905,387 | ✅ |
| `total_remark_bytes` | 915,155 | +104,579 | −852 −4 | +2 | 1,018,880 | 1,018,880 | ✅ |
| `d2_item_count` | 24 | 0 | 0 | +1 | 25 | 25 | ✅ |
| `row_count` / `distinct_row_ids` | 1260 | 0 | 0 | — | 1260 | 1260 | ✅ |
| `keys_per_row` | 25 | 0 | 0 | — | 25 | 25 | ✅ |
| `total_stable_fields` | 49,140 | 0 | 0 | — | 49,140 | 49,140 | ✅ |

**残差 = 0**，在「stored / compact / 合计 / 条数 / 形态」五个量纲上同时对平。唯一**未**分解
到底的是 −852 内部的逐键构成（上面说明了为什么不能，以及我为此补的取证，见处置）。

#### 处置（已落改动的复核 + 我的更正）

复核已落的那笔改动：**不是洗绿**。它没有把 `906_239` 重冻成 `1_009_966`，而是换了**量纲**：

| 断言 | 改前 | 改后 | 为什么不是洗绿 |
|------|------|------|----------------|
| 尺寸 | `payload_bytes == 906_239` | `payload_compact_bytes >= 900_000` | 紧凑口径**排版无关**（已证 Python/JS 口径在这份数据上相等），真变小仍然打红 |
| 排版 | 无 | `payload_whitespace_bytes <= 110_000` | 原来排版膨胀**根本看不见**（混在等式里），现在它有独立上限、继续可打红 |
| 形态 | 等式 | **保持等式**（1260 行 / 39 字段 / 25 键） | 这才是 pilot 依赖的不变量，一个都没放宽 |
| item 数 | `== 24` | `>= 24` 且 `== item_count − 1` | 条数是用户行为的函数；分流恒等式仍是等式 |

我改的两处：

1. **修正归因文字**：把「−852 字节是一次真实编辑（`debitOccurrence` 1093 -> 1092）」改成
   实测能站住的表述 —— 那一笔编辑存在但最多解释 17 字节，余额来自「计数不变而值变短」，
   并写明**为什么不能再往下分解**（旧 evidence 没记逐键字节）。留着错的归因比留个已知
   空白更糟：下一个人会按「已经查清了」跳过。
2. **补上取证，让下一次可归因**：`_real_payload_phases` 现在把
   `payload_value_bytes_by_key`（逐键值字节）/ `payload_value_bytes` /
   `payload_struct_bytes` / `payload_distinct_keysets` 落进快照，并新增
   `test_size_delta_is_attributable_to_value_bytes` 锁**分解恒等式**
   （结构 + 值 ≡ 紧凑、键集合恰 1 种、aging 三组恒为 `63 × 1260`）。
   🔴 它**不冻结任何尺寸数字** —— 结构字节由键集合现推，所以它锁的是「差额只能落在值
   字节里」这条推理链本身，而不是某个数。

#### 变异验证（真实观测路径，三次，均已还原）

| # | 扰动（真库可见的真行/真测量） | 预期 | 实测 |
|---|------------------------------|------|------|
| M1 | `D2_WP_ID` 指向**另一份真实 D2 底稿** `ef7f88e3-…6c88`（其 `D2-detail-rows` 真有 550,531 字节） | 形态 + 分母同时打红 | ✅ `assert 741 == 1260`；新判据 `每行键集合出现 4 种`；node 9 `旁边只剩 1 条 item（下界 23）` |
| M2 | 紧凑口径只量前 900 行（`_parsed[:900]`） | 尺寸下界打红 | ✅ `紧凑口径只剩 651438 字节（下界 900000）`；新判据 `分解不闭合：结构 496441 + 值 408946 != 紧凑 651438` |
| M3 | 让一条**真实邻居 item** `D2-bd-aging-rows` 出现在契约 blob 里 | 泄漏判据打红 | ✅ `AssertionError: ['D2-bd-aging-rows']` |

三次扰动后 `git diff` 中 `MUTATION` 残留 = `[]`，`D2_WP_ID` 已复原。

---

### C8-9 —— D2 隔离守卫（`test_no_other_store_item_is_touched`）

**判决：REAL CHANGE**（条数变了；**没有**跨车道写入）

#### 🔴 先回答「隔离守卫红了是不是有人写出了车道？」—— 它没红，而且真库证明没越界

这条现在是**绿的**。原红因是 `other["count"] == 24 − 1 == 23` 这个等式，而 2026-09-10 11:30
真库多了一条 `D2-entry-rows`（内容 `[]`，2 字节，用户新开一个分区就会产生）⇒ 24 → 25 条。
**条数是用户行为的函数，不是被测系统的性质**；已落处置把它换成「下界 + 分流恒等式」，
而结论性的两条（`leaked_into_contract == []`、`merged_key_prefixes == ["receivable_detail_rows"]`）
**保持等式**。M1/M3 证明这两条真的会咬人。

为了不只靠断言、而是直接问真库「有没有人写进这份底稿的其他 item」，我做了独立核查 ——
用取证探针的 marker 形态（`g4h\d{4,}` / `g5d\d{4,}` / `PROBE-` / `探针`）扫这份底稿的全部
25 条 item：

```sql
SELECT ... FROM public.checklist_responses
WHERE wp_id = 'e2c95d10-181d-4549-8910-d5ab5bc5edd1'
  AND (remark ~ 'g4h[0-9]{4,}' OR remark ~ 'g5d[0-9]{4,}' OR remark ~ 'PROBE-' OR remark ~ '探针');
-- []  ← 零命中
```

**零命中**，且 23 条邻居 item 里有 22 条与 2026-09-06 冻结清单**逐条字节相等**（唯一变的
`D2-detail-audit-note` −4 字节是与载荷同一次保存、6 秒之隔的人工编辑）。

⇒ **隔离守卫没有指示跨车道写入**。对照事实很有说服力：同一批取证探针**确实**在真库里留下了
marker，但 D2 那一发落在**另一份** D2 底稿 `ef7f88e3-…6c88`（`customerName": "g4h205660"`），
**不是** pilot 的目标底稿。也就是说 D2 这条车道线被守住了 —— 而 H1 那条没有（见下）。

---

### C8-10 / C8-11 —— H1 空载体这一对（`..._pg.py::test_disposal_store_item_is_empty_*`）

**判决：REAL CHANGE**（库真的不空了）→ **处置：拒绝放宽，保持 RED**（详见下）

这一对是「一个观测、一个契约声明观测」的互锁。任务书要求：库若不空，**解释那些行，不要把
断言放宽**。下面就是那一行的完整来历，**残差 0**。

#### 那一行是什么

```sql
SELECT wp_id, item_id, length(remark), remark, created_at, updated_at
FROM public.checklist_responses WHERE item_id = 'H1-8-rows';
```

```
wp_id      = c71b7c54-6868-4fb9-9e14-083034f57815
item_id    = H1-8-rows
length     = 51
remark     = [{"rowId": "GTROW-H18-0013", "name": "g4h1324785"}]
created_at = 2026-09-11 02:44:59.683482+00
updated_at = 2026-09-12 04:29:11.983498+00
```

底稿归属（`wp_index` 无 `name` 列，用 `wp_name`）：

```
wp_code = H1「固定资产」   audit_cycle = H   status = not_started
project = 2aa00f57-…8749  重庆和平药房连锁有限责任公司_2025      ← 真实项目
```

注意它**不是** pilot 的参考底稿（`H1_WP_ID = dbd9cc36-…71d3`）—— 所以同文件的
`test_the_same_workpaper_family_really_has_h1_data`（24 条 item / 19,524 字节）仍然绿。

#### 归因：G4-1 取证探针写的，逐项对齐

`g4h1324785` 这个字符串在仓库里有**唯一**出处：

`.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/`
`g4-1-h1-host-unified-path/network-and-callback.json`

| evidence 里的字段 | 值 | 与真库行对齐 |
|---|---|---|
| `script` | `e2e/g4-1-h1-unified-path.spec.ts` | 写入方具名 |
| `captured_at` | `2026-09-12T04:30:18.317Z` | 行 `updated_at` = `04:29:11` ⇒ **早 67 秒**，同一次跑 |
| `scope.wp_id` | `c71b7c54-…57815` | **逐字符相同** |
| `scope.project_id` | `2aa00f57-…8749` | **逐字符相同** |
| `html_dom_roundtrip.marker` | `g4h1324785` | **逐字符相同** |
| `html_dom_roundtrip.store_mirrored` | `true` | 解释了它为什么会落进 store |
| `oo_write_target` | `D13` | 见下 |
| `oo_cell_edit_probe.activeSheet` | `减少检查表H1-8` | 正是本 pilot 的受管 sheet |

**51 个字节全部对上，一个字节不剩**：

* 契约 `h1.disposal_check.json` 里 `asset_name` 一格的 `json_pointer` =
  `/rows/{row_uuid}/name`、`cell.column = "D"`、`source_ref = 源xlsx!减少检查表H1-8!D13`
  ⇒ store 侧键名就是 `name`，探针写的 **D13** 就是 `asset_name`；
* `row_uuid` 由 `excel_instrumentation.row_uuid()` 预生成为 `GTROW-{template_id}-{row:04d}`
  ⇒ 第 13 行 = `GTROW-H18-0013`（与 `bp-21` 交接文档记的 `GTROW-H18-0013 … -0027` 一致）；
* ⇒ 这 51 字节 = 「1 行 × 1 格」的最小 store 形态，内容恰是
  `disposal_check_rows/GTROW-H18-0013/asset_name = "g4h1324785"`。
  **没有任何业务数据**，也没有第二格。

#### ⇒ 这不是「真实审计数据出现了」，是我们自己的取证探针写脏了真库

判据的 docstring 写着「真实数据一旦出现，这条打红，提醒把 oracle 改跑在真实载荷上」。
实测出现的**不是**真实数据，而是 G4-1 e2e 探针经 HTML→store 真链路留下的 marker。所以：

* **`== 0` 不能放宽成 `<= 1`**：那会把「我们的探针在真实项目底稿里留了一行」洗成
  「库本来就可能有一行」，并且以后真有业务数据进来时这条判据已经失去分辨力；
* **我也不会去删那一行**：它落在**真实项目**（重庆和平药房连锁_2025）的底稿上，
  删除 = 写真实项目数据，必须由 owner 授权，不属本次只读分诊的权限；
* 合成行 oracle 的**理由依然成立**（该 item 里零业务载荷），所以离线守卫不需要改。

#### 🔴 触类旁通：同一批探针让**四处**「全库 0 行」的观测同时失真

扫全表 `g4h\d{4,}` / `g5d\d{4,}`，命中 **6** 条，全部是 2026-09-12 当天的探针 marker：

| wp_id | item_id | 字节 | marker | 曾被记为「全库 0 行」的地方 |
|---|---|---|---|---|
| `c71b7c54` | `H1-8-rows` | 51 | `g4h1324785` | 本判据 + `workpaper_sync_entry_wp_code_adjudication.json` |
| `d35c715a` | `D3-det-rows` | 59 | `g5d3439283` | 同 json 的 D3 条目 |
| `1ed2feaf` | `D6-2-rows` | 525 | `g5d6309270` | 同 json 的 D6 条目 |
| `629d762a` | `D5-2-rows` | 55 | `g5d5979837` | 同 json 的 D5 条目 |
| `ef7f88e3` | `D2-detail-rows` | 550,531 | `g4h205660` | （非 pilot 目标底稿，见 C8-9） |
| `6f23dcce` | `D7-2-rows` | 728 | — | — |

`backend/data/workpaper_sync_entry_wp_code_adjudication.json` 有四处写着
「`H1-8-rows` / `D3-det-rows` / `D5-2-rows` / `D6-2-rows` 全库 0 行（空表单是合法业务事实）」
—— 这四句**现在都已失真**，原因同一个。本次**不改那份 json**（它是别人的裁决取证，
且属 manifest↔slice 簇），作为遗留项上报。

#### 处置：保持 RED，具名 owner + 精确解除条件

| 项 | 内容 |
|---|---|
| 状态 | **RED（诚实红）**，两条断言一个字节都没动 |
| owner | **G4-1 车道**（`e2e/g4-1-h1-unified-path.spec.ts` 的作者/维护方）—— 它是唯一写入方，证据见同目录 `network-and-callback.json` |
| 解除条件（二选一） | ① G4-1 把 DOM-roundtrip 那一步的目标从**真实项目底稿** `c71b7c54` 改到 scratch 底稿，并在 owner 授权下删掉 `public.checklist_responses` 里 `wp_id=c71b7c54 AND item_id='H1-8-rows'` 这**一行**（51 字节，内容已在上文完整留档，可逐字节复原）⇒ 本对自动转绿；② 若决定保留该行，则必须由 owner 重新裁决 `h1.disposal_check.json` 的 `review.html_store.observed_empty_in_reference_database`，并把 H1 oracle 改跑在真实载荷上 —— 那是改契约，不是改断言下界 |
| 不做什么 | 不放宽 `== 0`；不删真实项目数据；不改离线守卫（合成行 oracle 的理由仍成立） |

---

### C8-12 —— Word 三臂真跑（`test_task61_…::test_the_three_arms_really_run_against_the_database`）

**判决：不属本簇 —— 移交（capability 翻转的下游）**

#### 🔴 先摆正读数：空的是断言，不是观测

任务书说「measured red with `registered_adapter_ids == []`，注意 manifest 现在真有 4 个
注册 adapter，请判断空列表是真库缺行还是读路径过期」。实测**两者都不是**：

```
arm_a_control:
  planned                = 155
  registered_adapter_ids = ['d2.receivable_detail', 'd4.revenue_detail',
                            'g7.soe_subsidiary_disclosure', 'h1.disposal_check']
  registered_entry_ids   = ['xlsx/gt-d2-accounts-receivable', 'xlsx/gt-d4-operating-revenue',
                            'xlsx/gt-g7-long-term-equity-main', 'xlsx/gt-h1-fixed-assets']
  unregistered           = 151
binding_constraint_id              = None      （冻结期望 "BP-61-1"）
arm_b_reason_equals_control_reason = False     （冻结期望 True）
arm_c_reason_differs_from_arm_b    = True      （冻结期望 True ✅ 唯一还对的一条）
```

`[]` 是**冻结期望**那一侧。观测侧非空且**内容正确**，读路径完全活着 —— 证据是三重自洽：

* 4 个 `registered_adapter_ids` 与 4 个 `registered_entry_ids` **一一对应**，正是既定语境里
  `capability=bidirectional` 的那 4 个 entry（D2 / D4 / G7 / H1）；
* `planned = 155` 与既定语境的 manifest 实数**逐数相等**（176 → 155，退役 21 条
  `xlsx/d4/**`；`single_onlyoffice 145 + single_html 5 + bidirectional 4 + unreachable 1 = 155`）；
* `unregistered 151 = planned 155 − registered 4`，**残差 0**。

所以这条红与「真库形态」无关：它是 `cd9592ff5` + `ebc6e1b92`（D4 → `useD4SyncMode`）与
`42d2f6e6f`（D2 pilot → 统一路径）把 D2/D4/G7/H1 做实成 `bidirectional` +
`adapter_registered` 的**直接下游**。

#### 门自己已经写明该由谁裁决（不是我能顺手宣布的）

`backend/scripts/check/check_task61_oo94_word_pilot_gate.py` 的 `BINDING_CONSTRAINTS`
里，BP-61-1 的 `measured_readings` 上方已经留了这段：

> 🔴 本序列只登记**行数**。「capability 是否已翻转、BP-61-1 是否已解除」不在此处裁决 ——
> 2026-09-23 实测 `registered_adapter_ids` 已非空、manifest 里 `bidirectional` 已有 4 条，
> 与上面快照的「仍为空 / 0 条」相反，那是一次**状态翻转**，归 `owner_task` 登记的解除方
> 裁决，不由本序列顺手宣布。

而 `owner_task` 具名为：

> 供给侧 = `published-representation-production-path-and-lane-adjudication` spec（首版发布宿主）；
> **capability 翻转侧 = manifest 重生成 + `approved_source_digest` 人工复核（Task 67 登记的复核方）**
> —— 均不属 Task 61

⇒ 这条节点的**前提**（「Word lane 未注册」+「BP-61-1 是那条绑定约束」）已被翻转作废。
它不是一个数过期，而是四条断言里有三条同时失去意义（`== []` / `binding_constraint_id ==
"BP-61-1"` / `arm_b_reason_equals_control_reason is True`）。把它改绿等于**代替 owner 宣布
BP-61-1 已解除** —— 那是裁决，不是分诊。

#### 处置

| 项 | 内容 |
|---|---|
| 状态 | **RED，一个字节没动**（含 `TestAdmissionIsRealReadback::test_no_f2_entry_is_admitted_today`，那条是别人刚修好的，本次未触碰） |
| 移交给 | capability 翻转簇 / manifest↔slice 簇 —— 即 BP-61-1 `owner_task` 里具名的 **Task 67 登记的复核方**（manifest 重生成 + `approved_source_digest` 人工复核） |
| 解除条件 | 由该 owner 裁决 BP-61-1 是否随 4 个 adapter 注册而**解除**；裁决后按新前提重推 arm_a 的期望（`registered_adapter_ids` 应为那 4 个、`binding_constraint_id` 是否还存在），并同步 `BINDING_CONSTRAINTS` 与离线替身 `offline_binding_arms`（现仍是 `planned 186 / registered []` 的 2026-09-01 形态） |
| 附带事实（供 owner 直接用） | `planned 155` / `unregistered 151` / `binding_constraint_id` 现算为 `None` / `arm_b_reason_equals_control_reason` 现为 `False`；三臂真跑只读、`registry` 逐值复原（同文件 `test_the_arms_do_not_mutate_the_production_registry` 仍绿） |

---

## 结论

### 计数

| 类别 | 条数 | node |
|------|------|------|
| **已闭**（断言过期，按真实归因换量纲后转绿） | **2** | 8、9 |
| **拒绝放宽**（真变了，但放宽会洗掉真问题 ⇒ 诚实红） | **2** | 10、11 |
| **移交**（不属本簇） | **1** | 12 |
| **阻塞在真实数据** | **0** | —— |
| C9 半（另一半，已闭） | 2 | 1、2 |

12 行判决表里 **C8 的 5 行（8~12）全部落定**。C9 半不属本次范围，由该簇的处置方维护
（撰写本节时 rows 3/4/6/7 已由并行会话补齐，rows 1~2 的「处置」列仍 `待填`）。

### 每文件最终计数

| 文件 | BEFORE | AFTER | 说明 |
|------|--------|-------|------|
| `test_task41_d2_large_json_pilot_pg.py` | 37 passed / 0 failed | **38 passed / 0 failed** | +1 = 新增 `test_size_delta_is_attributable_to_value_bytes` |
| `test_task42_h1_grouped_dynamic_pilot_pg.py` | 31 passed / **2 failed** | 31 passed / **2 failed**（不变，故意） | 拒绝放宽；owner = G4-1 车道 |
| `test_task61_oo94_word_pilot_gate.py` | 159 passed / **1 failed** | 159 passed / **1 failed**（不变，故意） | 移交；`TestAdmissionIsRealReadback::test_no_f2_entry_is_admitted_today` 未触碰，仍绿 |

### 五个「第一问」的答案汇总

**没有一个是 REGRESSED IMPLEMENTATION。** 三条是真库内容真的动了（8/9 = 用户与写入方的
正常行为；10/11 = 我们自己的取证探针），一条是判据前提被上游 capability 翻转作废（12）。
把 10/11 放宽、或把 8 的尺寸重冻到现值，都会让红消失而问题留下 —— 那是本次明确拒绝的两件事。

### 改了什么

仅 `backend/tests/workpaper_sync/test_task41_d2_large_json_pilot_pg.py` 一个文件：

1. 更正 `MIN_PAYLOAD_BYTES` 上方归因段里**算错的一笔**（−852 字节不可能来自
   `debitOccurrence` 单格，实测单值最长 18 字节），并写明可证边界与不可证的原因；
2. `_real_payload_phases` 增采 `payload_value_bytes_by_key` / `payload_value_bytes` /
   `payload_struct_bytes` / `payload_distinct_keysets`；
3. 新增 `test_size_delta_is_attributable_to_value_bytes` —— 锁**分解恒等式**
   （结构 + 值 ≡ 紧凑、键集合恰 1 种、aging 恒为 `63 × 1260`），**不含任何冻结尺寸数字**。

H1 与 Task 61 两个文件**一个字节未动**。真库**只读**：本次全部查询为 `SELECT`，
未新建/删除任何 scratch schema 之外的对象，未改真实项目数据。

### 遗留移交（未处置，本次不动）

1. **（承接 C9）`D/D4收入底稿.xlsx`（无空格）与 `D/D4 收入底稿.xlsx`（有空格）并存**
   —— 分别由 `2dbede1d4`（2026-07-16）与 `d3b3d80d9`（2026-09-14）加入，只差一个空格，
   像同一份底稿重复入库。语料判据不负责裁定模板库该留哪份；**本次未删任何模板字节**。
2. **G4/G5 取证探针在真库留下 6 条 marker 行**（含 1 条在**真实项目** H1 底稿上）
   —— 完整清单见 C8-10。owner = 对应 e2e 车道；需 owner 授权后清理，并把 DOM-roundtrip
   目标改到 scratch 底稿。
3. **`backend/data/workpaper_sync_entry_wp_code_adjudication.json` 四处「全库 0 行」已失真**
   （`H1-8-rows` / `D3-det-rows` / `D5-2-rows` / `D6-2-rows`），根因同第 2 条。
   属 manifest↔slice 簇的裁决取证，本次未改。
4. **BP-61-1 是否随 4 个 adapter 注册而解除** —— 见 C8-12，owner = Task 67 登记的复核方；
   连带需同步离线替身 `offline_binding_arms`（仍是 `planned 186 / registered []` 的
   2026-09-01 形态）。
5. **D2 载荷 −852 字节的逐键构成** —— 永久不可考（旧字节已被 2026-09-10 保存覆盖，
   旧 evidence 只记计数与类型）。已用新增取证把**下一次**变动变成可归因，不再欠新账。
