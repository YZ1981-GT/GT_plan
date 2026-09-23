# C5 集群：派生产物漂移（generated-artifact drift）

**集群定义**：磁盘上的派生产物与其生成器"现在"计算出的结果不一致。15 个失败节点。

**判定口径（每节点必须择一）**
- **Q1 = 产物过期**：上游事实合法演进，磁盘产物没跟上 ⇒ 合法修复 = 重跑生成器 + 提交新产物。
- **Q2 = 真实漂移**：断言是天花板/冻结基线/检测器自检，重生成会把真实回归洗白成新基线
  ⇒ **拒绝重生成**，定位真因；真因超出本次授权则如实 BLOCKED 留红。

**环境**：cwd=`d:\GT_plan\backend`，python=`..\.venv\Scripts\python.exe`，
每文件单独 `-q --tb=short -rf -p no:randomly`（从不跑整套 `tests/workpaper_sync`）。

---

## 0. 第二轮复核（本轮）——先纠正上一轮的两处失实结论

上一轮表格把 **#12 / #13 标成「✅ 绿」**。**实测不成立**：

| 证据 | 结论 |
|------|------|
| `git status` 里 `backend/data/workpaper_row_change_reachability.json` **未出现在改动列表** | 那次 `--apply` 从未落盘 |
| 实跑 3 个节点：`test_inventory_matches_current_computation` / `test_host_binding_is_content_addressed` 均 **FAILED** | 两条仍是红 |

**本轮实测 15 节点现状：2 绿 / 13 红。**

| 节点 | 现状 |
|------|------|
| #1 task44 `test_generated_registry_data_file_is_fresh` | ✅ **PASS**（上一轮"修真因"确实落盘且有效） |
| #14 row_change `test_binding_verifier_detects_injected_digest_drift` | ✅ **PASS**（`_DELIVERED_CONTRACTS` 派生化已落盘） |
| 其余 13 条 | ❌ FAIL |

已落盘的真实改动只有 3 个文件（`git diff --stat` 实证）：
`check/check_task44_oo94_excel_pilot_gate.py` +8、`gen/generate_workpaper_task44_pilot_probe_registry.py` +13、
`tests/.../test_workbook_row_change_reachability.py` +19/-3。

---

## 1. 三条共同上游根因（15 个节点全由这三条解释）

### 根因 A：本 checkout 的行尾被 `core.autocrlf=true` 翻成 CRLF —— 本轮已**逐字节证明**

`git config core.autocrlf` = **true**，且 `.py` / `.md` / 大部分 `backend/data/*.json`
在 `.gitattributes` 里**没有** `eol=lf` 规则。于是任何"对文本真源取 **raw** sha256"的门，
在 Windows 工作树算出的值 ≠ 产物里登记的 LF 值。

**本轮对 #6/#7 拿到了闭环证据**（`backend/data/onlyoffice_word_sdt_carrier_contract.json`）：

| 取值方式 | sha256 | 等于什么 |
|---------|--------|---------|
| 工作树 **raw** 字节 | `bb82909043ab…` | **= 生成器现算值**（`calc`） |
| 工作树 **CRLF→LF 归一** | `be4d11dde4e9…` | **= 磁盘产物登记值 = HEAD blob 值** |

`CRLF=347 处 / 单独 LF=0 处`，且 `LF归一(工作树) == HEAD blob` 逐字节 **True** ⇒ **内容完全相同，差异 100% 只是行尾**。

**⇒ 对这类节点重生成 = 把 Windows-only 的 CRLF digest 焊进基线，本机变绿、CI（Linux/LF）必红。这是洗白。**

`.gitattributes` 里已经为同一故障形态留了先例注释（`backend/data/workpaper_sync_contracts/*.json` 那一段）。

### 根因 B：D 循环权威模板被"净化"后，下游冻结基线没跟上

commit **`1a0b55651`**（`feat(workpaper-sync): D 循环 5 个 canary 做实到 bidirectional_verified`）
改了 4 份权威模板，字节实测（`git show --stat`）：

| 模板 | 前 → 后 | 缩幅 |
|------|---------|------|
| `D/D3 预收账款.xlsx` | 133116 → 74402 | −44% |
| `D/D5 应收款项融资.xlsx` | 113287 → 53811 | −52% |
| `D/D6 合同资产.xlsx` | 421708 → 125607 | −70% |
| `D/D7 合同负债.xlsx` | 379551 → 88777 | −77% |

**缩幅是否"毁坏"——本轮查清了，结论是良性**：脚本实际是 `scripts/fix/sanitize_d{3,5,6,7}_template_external_links.py`
（上一轮写的 `sanitize_dN_…py` 这个文件名**不存在**，已纠正），机制是
`zipfile` 逐 entry 重建 + 丢弃 `externalReference` 部件，**并非 openpyxl 全量重写**；
openpyxl 只用于**验收**（`_snapshot_managed` 对受管 sheet 逐格 diff + `_gate_ext_count` 前后计数）。
缩幅来自两处合法原因：① 丢掉 `externalLink*.xml` 里缓存的整份外部工作簿数据；② 重建时统一 `ZIP_DEFLATED` 重压缩。
⇒ 不是 `H3 投资性房地产` 那种 openpyxl 毁坏形态。

`*.preclean.bak` 是脚本刻意保留的**门负例 fixture**，被 `.gitignore:139 *.bak` 忽略 ⇒ 未跟踪、fresh clone / CI 上不存在。

传播状况实测：**10/10 per-entry 契约的 `template_sha256` 与净化后的磁盘字节完全相符（problems=0）**
⇒ 契约层已重冻结。仍然 stale 的只有 4 处下游：D 循环 frozen slice、`wp_templates/_index.json` 的 `size_kb`、
row-change 清册、row-change 冻结基线。

### 根因 C：`find_template_file` 新增"程序表码回落主工作簿"

commit `82f58ea44 feat(d4-ipo)` 在 `wp_template_finder.find_template_file` 末尾**有意**加了
`_PROGRAM_TABLE_CODE_RE` 回落（`D4A / F2A / K3A …` → 主码主工作簿）。
于是 `find_template_file("H2A")` 从 `None` 变成 `H/H2 在建工程.xlsx`，`S12A` 从 `legacy_verdict=none` 变成 `parent_workbook`。
**这与一条明写的守卫直接冲突**（节点 #4）——已发布特性 vs 已发布守卫，需 owner 裁决。

---

## 2. 15 行判定表（本轮复核后）

| # | 节点 | 生成器 / 产物 | 根因 | Q1/Q2 | 现状 | 处置 |
|---|------|--------------|------|-------|------|------|
| 1 | task44 `test_generated_registry_data_file_is_fresh` | `gen/generate_workpaper_task44_pilot_probe_registry.py` → `data/workpaper_task44_pilot_gate_probes.json` | A | **Q2** | ✅ 绿 | 修真因：哈希前行尾归一；**产物零改动** |
| 2 | task46 `test_authoritative_templates_digests_recompute` | 无生成器（手工 frozen slice `data/workpaper_sync_d_cycle_manifest_slice.json`） | B | **Q2** | ❌ 红 | BLOCKED（D 循环 owner 重裁决） |
| 3 | task46 `test_every_entry_template_ref_is_registered_with_digest` | 同上 | B | **Q2** | ❌ 红 | BLOCKED（同 #2） |
| 4 | task50 `test_template_resolution_audit_recomputes` | 无生成器（H slice 的 `program_table_code_note` 前提） | C | **Q2** | ❌ 红 | BLOCKED（owner = commit `82f58ea44` d4-ipo） |
| 5 | task58 `test_ledger_is_in_sync_with_sources` | `gen/generate_workpaper_word_template_adjudication.py` → `data/workpaper_word_template_adjudication.json` | C | **Q2** | ❌ 红 | BLOCKED（同 #4；重跑会把争议行为记成既成事实） |
| 6 | task62 `test_build_record_is_byte_stable` | `gen/generate_task62_generic_docx_adjudication.py` → `data/workpaper_sync_task62_generic_docx_adjudication.json` | A（**已证明**） | **Q2** | ❌ 红 | BLOCKED：真因=app 层 raw 哈希，**一行可修**，见 §3.1 |
| 7 | task62 `test_check_matches_the_file_on_disk` | 同上 | A（**已证明**） | **Q2** | ❌ 红 | 与 #6 **同一处差异**（同一个 digest），同 §3.1 |
| 8 | task63 `test_record_is_reproducible` | `gen/generate_workpaper_task63_subcode_adjudication.py` → `data/workpaper_sync_task63_subcode_adjudication.json` | A + 移动输入 | **blocked-on-moving-input** | ❌ 红 | 拒绝重跑（`registry.py` 等真源正被并行改动） |
| 9 | task63 `test_source_digests_cover_every_file_…` | 同上 | A + `adapters/registry.py` 真实内容漂移 | **blocked-on-moving-input** | ❌ 红 | 拒绝重跑（同 #8） |
| 10 | task64 `test_generator_check_is_idempotent` | `gen/generate_task64_dedicated_word_chain.py` → `data/workpaper_sync_a16_a17_word_chain_adjudication.json` | A（+ 合法的 4→10 契约进展） | **Q2** | ❌ 红 | BLOCKED（与 #6 共用 `probe_gate_identity()` 真源） |
| 11 | template_override `test_index_size_drift_is_registered_not_growing` | 无生成器（测试常量 `_INDEX_SIZE_CONSISTENT=451`） | B | **Q2** | ❌ 红 | 拒绝抬/降常量；已查清"是谁、是否合法"，见 §3.2 |
| 12 | row_change_reachability `test_inventory_matches_current_computation` | `gen/generate_row_change_reachability.py` → `data/workpaper_row_change_reachability.json` | B + 契约交付进展 | **Q1（但耦合 BLOCKED）** | ❌ 红 | 产物确实 stale，但重生成会**新红 3 条**，见 §3.3 |
| 13 | row_change_reachability `test_host_binding_is_content_addressed` | 同上（+ 测试字面量 `4`） | 契约交付进展 | **Q1（同 #12 打包）** | ❌ 红 | 测试侧已派生化；仍差产物落盘，见 §3.3 |
| 14 | row_change_reachability `test_binding_verifier_detects_injected_digest_drift` | 同上（+ 测试字面量 `4`） | 契约交付进展 | **Q1** | ✅ 绿 | 分母 4→10 派生化；**检测器本身完好**，见 §3.4 |
| 15 | row_change_zero_regression `test_behaviour_matches_frozen_baseline` | `gen/generate_workbook_row_change_zero_regression_baseline.py` | B | **Q2** | ❌ 红 | 拒绝重冻结（违反测试自写的 re-freeze 前置） |

**统计**：Q1 = 3（#12/#13/#14，其中仅 #14 真正落地）；Q2 拒绝重生成 = 10（#1~7、10、11、15，其中 #1 已通过修真因转绿）；
blocked-on-moving-input = 2（#8/#9）。
**净结果：2 绿 / 13 红，且 13 条红全部是"诚实红"——没有任何一条是靠改基线/抬天花板换来的。**

---

## 3. 本轮新增的逐节点取证

### 3.1 #6 / #7：**不是**生成器非确定性，是 CRLF；且两条是同一处差异

测试名与断言文案误导了诊断，先纠正两点：

1. **`test_build_record_is_byte_stable` 名不符实**。它的 `record` fixture（`scope="module"`）是
   **读磁盘产物**（`RECORD_PATH.is_file()` → `json.loads`），不是第一次 `build_record()`。
   所以这条比的是"磁盘 vs 现算"，与 #7 **同一个事实**；它的失败文案却写
   「记录含非确定性内容（时间戳/集合序）」——照它字面去查会查错方向。
2. **生成器其实是确定性的**。实测连续 3 次 `build_record()`：
   - 裸进程：`call1 vs call2 = 0 处差异`，`call2 vs call3 = 0 处差异`
   - pytest 环境内（conftest 全加载）：同样 `0 处 / 0 处`
   并且 #7 的"现算"digest 跨两次独立 pytest 运行**稳定**为 `bed69f1a1f36`。

用生成器自己的 `_canonical_text()` 做行级 diff（两侧都过一遍，消除 tuple↔list 往返噪声），
4481 行里**只有 1 行不同**：

```
       "identity": {
-        "carrier_contract_sha256": "be4d11dde4e92110d8da74c8da6de849c62f2ea58233f54e5ab6632466d67acc",
+        "carrier_contract_sha256": "bb82909043ab380f5e1cd0bd441e62ca16e800cd9b6ff99286017911b8e1c272",
         "carrier_gate_digest": "ec469dc7722cde207db52992a36628f2b2119a863cc165399a75b9f0d288ab3a",
```

这个值来自 **app 层**而不是脚本：`word_instrumentation.py::WordSdtCarrierGate.load()`

```python
raw = WORD_GATE_CONTRACT_PATH.read_bytes()      # data/onlyoffice_word_sdt_carrier_contract.json
contract_digest = _sha256_bytes(raw)            # ← raw 哈希，平台相关
payload = json.loads(raw.decode("utf-8"))       # JSON 解析对行尾不敏感
```

配合 §1 根因 A 的逐字节证明（`raw==bb82` / `LF归一==be4d==HEAD blob` / 内容相同），**结论确定**：
磁盘产物登记的 `be4d…` 是**正确的（LF/CI）值**，现算的 `bb82…` 是 Windows 工作树产物。
**重跑 `--write` = 把 `bb82…` 焊进产物 ⇒ 本机绿、CI 红。拒绝。**

**一行真因修复（未施加，交 owner）**：在上面 `read_bytes()` 之后归一行尾即可
（`raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")`），`payload` 解析不受影响，
现算立刻回到 `be4d…`，**产物一个字节都不用改**。这与 #1 已验收的修法同型
（见 `generate_workpaper_task44_pilot_probe_registry.py` 的 `_normalize_eol()` + `check_task44_*.py`
的 `read_task_body()` 归一，两处都带完整理由注释）。

**为什么本轮没有直接改**：`WordSdtCarrierGate.load()` 是 **fail-closed 证据门**
（`WordProbeEvidenceStaleError`，挂 Requirement 14.16 / Property 71），`carrier_contract_sha256`
会被写进多份裁决证据（task62 / task64 共用 `probe_gate_identity()`）。改它等于改一个已发布
身份字段的口径，blast radius 需要跑整套 `workpaper_sync` 才能确认，而整套被明令禁止（~34 min）。

**顺带发现（同一函数，同样隐患，建议一起裁）**：同一个 `load()` 里的 Tier A stale 判据用
`_sha256_bytes(target.read_bytes())` 逐份比基线，**同样是 raw 哈希**。只要基线里哪天进了一份
受 `autocrlf` 影响的文本文件，这道门就会在 Windows 上无条件 fail-closed。建议与上面一并归一。

- **owner**：Task 6 载体裁决 / Requirement 14.16 责任人
- **解除条件**：确认 `carrier_contract_sha256` 口径改为"行尾归一后的内容哈希"，
  或给 `backend/data/*.json` 补 `.gitattributes eol=lf`（二者任一即可，后者一次修掉整类）

### 3.2 #11：测试自写的"查是谁、是否合法"——本轮查清了

测试文案自己给了处置协议：「漂移**变多** ⇒ 有人改了权威模板（查是谁、是否合法）；
漂移**变少** ⇒ 有人重算了索引」。实测是**变多**：

| 项 | 测试登记 | 实测 | 差 |
|----|---------|------|----|
| `consistent` | 451 | **447** | −4 |
| `drifted` | 23 | **27** | +4 |
| `missing` | 2 | 2 | 0 |

新增漂移**恰好 4 份，全部 D 循环、全部 SHRANK**，且 `git log` 点名同一个 commit：

| 模板 | 索引声明 vs 磁盘 | 最后改动 |
|------|-----------------|---------|
| `D\D3 预收账款.xlsx` | 130.0KB vs 72.7KB | `1a0b55651` |
| `D\D5 应收款项融资.xlsx` | 110.6KB vs 52.5KB | `1a0b55651` |
| `D\D6 合同资产.xlsx` | 411.8KB vs 122.7KB | `1a0b55651` |
| `D\D7 合同负债.xlsx` | 370.7KB vs 86.7KB | `1a0b55651` |

**"是谁" = 已 push 的 `1a0b55651`；"是否合法" = 合法**（§1 根因 B：zipfile 重建 + 丢外链缓存 + 重压缩，
openpyxl 逐格验收，不是毁坏形态）。`wp_templates/_index.json` 自身 **HEAD == 现盘（未被改动）**⇒ 索引是 stale 的那一侧。

**为什么仍然拒绝动手**：
- 降常量到 447/27 = **洗白**（等于把 4 份新漂移登记成"可接受"，天花板反向抬高）。
- 全量重算 `_index.json` = **另一种洗白**：会把**既有 23 份**漂移一起"修平"，而那 23 份带
  `H\H3 投资性房地产.xlsx` 索引 712.3KB vs 磁盘 142.7KB（−80%）这类**已报 A 裁**的证据，抹掉即毁证。
- 且 `_index.json` 全仓**唯一写者**是 `scripts/ops/setup_wp_templates_dir.py`，它从
  `致同通用审计程序及底稿模板（2025年修订）/` **重新拷贝源模板** ⇒ 跑它会把已 push 的净化结果覆盖回未净化版本。**绝不能跑。**

**给 owner 的一步决策**：只把这 **4 条** entry 的 `size_kb` 按磁盘刷新（`consistent` 回到 451、
`drifted` 回到 23，**不动任何测试常量、不碰其余 472 条、23 份存量证据原样保留**），
或者显式把 447/27 连同 `1a0b55651` 的理由重新登记。
- **owner**：D 循环 / 权威模板库责任人
- **解除条件**：二选一拍板；无论哪个都**不要**执行 `setup_wp_templates_dir.py`

### 3.3 #12 / #13：产物确实 stale（Q1），但落盘会**新红 3 条**——打包交 owner

`--apply` 跑通（`xlsx 352 / 含跨 sheet 182 / 已发契约 entry 10`），产物 diff `+1029 / −182`。
**diff 形状体检合格**（不是"几百条不相关 entry 变动"）：

| 维度 | 结果 |
|------|------|
| 顶层键 | **无增无删**（无 schema 漂移） |
| `contracted_entries` | 4 → 10：**新增 6、删除 0、改动 0**，恰好是 d1/d3/d4/d5/d6/d7 |
| `denominators` | 10 项变动，全部可归因（新增 D4 工作簿 ⇒ `xlsx_total` 351→352；净化去外链 ⇒ `external_sites` 2908→2902） |
| `placeholder_markers` | 12 键无增删，5 项计数位移（多扫了一份工作簿） |
| `host_ambiguity` | 4 → 44：**新增 40、删除 0、改动 1**。逐条归因：35 条含新增 `D/D4 收入底稿.xlsx`；另 5 条是 D1/D3/D5/D6/D7 各自新契约行，且 `templates_containing: 1`（其实不歧义）；改动的 1 条是 `附注披露信息（国企）` 的 39→40 |

⇒ **100% 变动可追溯到"6 份 D 循环契约交付 + 1 份新工作簿"，零无关 churn。Q1 成立。**

**但**：用 python 写回 HEAD 字节 / 再放回重生成版本，做了可逆 A/B（**全程未用
`git stash` / `checkout --` / `reset`**），跑**整个文件**：

| 产物状态 | 结果 | 红的是谁 |
|---------|------|---------|
| HEAD（stale） | **2F / 20P** | #12、#13 |
| 重生成后 | **3F / 19P** | `test_design_denominator_table_matches_inventory`、`test_design_marker_table_matches_inventory`、`test_d2_is_the_only_entry_with_propagation_demand` |

**关键洞察：那 3 条现在的绿是 stale 产物撑出来的"假绿"。** 尤其第 3 条——
现算已是 `{d2:52, d3:51, d5:24, d6:3, d7:3}`，而它断言"D2 是**唯一**有传播需求的 entry"，
失败文案自己写着「Wave 2 的首要判据载体（D2）需重新裁定」。事实已经长出了这条断言的边界。

**处置：不落盘，打包交 owner。** 理由是落盘等于把 2 条已分派的红换成 3 条**未分派**的红，
其中 `test_d2_is_the_only_entry_with_propagation_demand` 是 **Wave 2 范围裁决**（与 #4/#5 同级），
不是我能单方面改的；另 2 条要改 `.kiro/specs/excel-workbook-wide-row-change-propagation/design.md`
的分母表/标记表（spec 文档，owner 可见）。**产物已还原为 HEAD 字节，测试侧 `_DELIVERED_CONTRACTS` 派生化保留。**

- **owner**：`excel-workbook-wide-row-change-propagation` spec / Wave 2 责任人
- **解除条件（一个 commit 里三件一起）**：① `generate_row_change_reachability.py --apply`；
  ② 同步 design.md 的分母表 + 标记表；③ 对"D2 不再是唯一有传播需求 entry"重新裁决并改写该守卫。

### 3.4 #14：检测器自检——**检测器完好，红的是过时字面量**

预警清单把它列为"检测器自检，红了可能是检测器本身坏了"。**实测不是**：
`verify_contract_template_binding()` 读**磁盘契约**逐份真 hash，与清册产物无关；
注入 digest 漂移后它确实报出 `d2.receivable_detail`。红的原因只是测试里硬写了分母 `4`。

修法遵循 C2 集群已验收的**派生优于抬字面量**：新增带完整理由的 `_DELIVERED_CONTRACTS = 10`，
三处 `4` 改为引用它。注意这个分母的作用是**防空集恒真**（契约集合若变空，`problems` 也空 ⇒ 守卫恒真），
所以它必须留一个"会让人意识到自己在改数字"的显式常量，**不能**写成 `len(contracts)` 那种自证。
分母 4→10 是**覆盖面变大**（10/10 契约实测 `problems=0`），守卫被加强不是削弱。

---

## 4. 变异验证（Q1 / 已落地修复不是假绿）

**#1（真因修复型：哈希前行尾归一）—— 最需要验的一条**，因为"归一"有可能顺手把门变成 no-op。
实测最小扰动（只改一个整数、字节长度不变）：

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | `workpaper_task44_pilot_gate_probes.json` 里 `gate_probe_count: 5 → 6`（32690 → 32690 字节） | — |
| 2 | 跑 `test_generated_registry_data_file_is_fresh` | **FAILED** ✅ 门仍在真比内容 |
| 3 | 按字节还原 | — |
| 4 | 复跑 #1 + #14 | **2 passed** ✅ |

⇒ 归一只吃掉了平台相关的行尾，**内容漂移照抓**。

**#12 / #13 的等价验证**已由 §3.3 的可逆 A/B 提供：同一个文件在"HEAD 产物 / 重生成产物"两种状态下
分别是 2F/20P 与 3F/19P，**两侧红的集合完全不同** ⇒ 这些断言确实在读产物，不是恒真。

**收尾状态核对**：`git diff --stat` 对 `workpaper_task44_pilot_gate_probes.json` 与
`workpaper_row_change_reachability.json` 均**无差异**（与 HEAD 内容一致）。
唯一副作用：还原时按 HEAD blob 写入，故 `workpaper_row_change_reachability.json` 的工作树行尾
由 CRLF 变 LF，git 提示 "LF will be replaced by CRLF the next time Git touches it"——
内容零差异，且这个方向与 CI（LF）一致，无需处理。

---

## 5. 按文件的最终计数

| 文件 | 本集群节点 | 绿 | 红 |
|------|-----------|----|----|
| `test_task44_oo94_excel_pilot_gate.py` | 1 | **1** | 0 |
| `test_task46_d_cycle_migration.py` | 2 | 0 | 2 |
| `test_task50_h_cycle_migration.py` | 1 | 0 | 1 |
| `test_task58_word_canonical_resolver.py` | 1 | 0 | 1 |
| `test_task62_generic_docx_entries.py` | 2 | 0 | 2 |
| `test_task63_subcode_adjudication.py` | 2 | 0 | 2 |
| `test_task64_dedicated_word_chain.py` | 1 | 0 | 1 |
| `test_template_override_resolution.py` | 1 | 0 | 1 |
| `test_workbook_row_change_reachability.py` | 3 | **1** | 2 |
| `test_workbook_row_change_zero_regression.py` | 1 | 0 | 1 |
| **合计** | **15** | **2** | **13** |

（`test_workbook_row_change_reachability.py` 整文件维度：**2F / 20P**，红的就是 #12/#13。）

---

## 6. 交 owner 的三个决策包（按 ROI 排序）

| 优先 | 决策 | 一并解除的节点 | 动作 |
|------|------|--------------|------|
| **1** | 给 `backend/data/*.json` 等文本真源补 `.gitattributes eol=lf`，**或**把 `WordSdtCarrierGate.load()` 的 `contract_digest` 与 Tier A 判据改为行尾归一后哈希 | #6 #7 #10（+ 降低 #8 #9 噪声） | 一处配置 / 一行代码，**产物零改动**；#1 已验收同型修法 |
| **2** | `excel-workbook-wide-row-change-propagation`：一个 commit 里同时落 ①`--apply` ②design.md 分母/标记表 ③重裁"D2 是否仍是唯一有传播需求 entry" | #12 #13（并消掉 1 条假绿） | 见 §3.3 |
| **3** | D 循环权威模板 `1a0b55651` 已确认合法 ⇒ 决定是刷新 `_index.json` 那 4 条 `size_kb`（回 451/23），还是显式重登记 447/27 | #11（#2 #3 #15 同源，需同一次裁决） | 见 §3.2；**禁跑** `setup_wp_templates_dir.py` |

**未解决且不属我裁的**：#4 #5（commit `82f58ea44` 的 `_PROGRAM_TABLE_CODE_RE` 回落 vs 已发布守卫，
特性与守卫正面冲突）、#15（重冻结违反测试自写的 re-freeze 前置：`insert_ctx` 不得变，而 D7 的
`insert_ctx` 确实变了）、#8 #9（真源正被并行改动，重跑只会 flapping）。

**本轮一条基线都没改、一个天花板都没抬、一份冻结产物都没重冻。13 条红全部是诚实红。**

---

## EOL 根因修复

> 2026-06-01。本节只做一件事：把 §1 根因 A（`core.autocrlf=true` 把本 checkout 翻成 CRLF）
> 从"已证明"推进到"已修复 + 已变异验证 + 已扫全仓"。
> **零产物改动** —— `backend/data/` 下没有任何文件被重新生成，这是本次修复的前提而不是副作用。

### 1. 前提复核（本轮独立重测，不沿用上一轮结论）

```
git config core.autocrlf                                            -> true
git check-attr text eol -- backend/data/onlyoffice_word_sdt_carrier_contract.json
    -> text: unspecified      eol: unspecified
```

即该 JSON **没有** `eol=lf` 规则（`.gitattributes:20` 只给
`backend/data/workpaper_sync_contracts/*.json` 配了），所以工作树是 CRLF、CI 是 LF。

`backend/data/onlyoffice_word_sdt_carrier_contract.json`（17270 字节）实测：

| 读法 | sha256 | 含义 |
|---|---|---|
| 工作树 **raw** | `bb82909043ab380f5e1cd0bd441e62ca16e800cd9b6ff99286017911b8e1c272` | 修复前生成器算出的值 |
| 工作树 **CRLF→LF 归一** | `be4d11dde4e92110d8da74c8da6de849c62f2ea58233f54e5ab6632466d67acc` | 产物登记值 = CI 值 |
| `git show HEAD:<path>` | `be4d11dde4e92110d8da74c8da6de849c62f2ea58233f54e5ab6632466d67acc` | 与归一值**逐字节相等** |

`CRLF=347`、裸 `LF=0`、`LF_normalized(worktree) == HEAD blob` → **True**，`raw == HEAD blob` → **False**。
⇒ 内容一个字节没变，100% 的差异是行尾。**重跑生成器会把 Windows-only digest 焊进基线（本机绿、CI 红）**，
所以上一轮拒绝重跑并升级，是正确的。

### 2. 选定修法 (a)：读侧行尾归一，并**刻意不动** Tier A

`backend/app/services/workpaper_sync/word_instrumentation.py`：

- 新增 `_normalize_eol()` / `_sha256_text_source()`（带 🔴 理由注释）。
- `WordSdtCarrierGate.load()` 的 `contract_digest` 改走 `_sha256_text_source(raw)`；
  `payload = json.loads(raw.decode("utf-8"))` **保持读原始字节**——JSON 解析对行尾不敏感，语义零变化。

选 (a) 而非 (b)（`.gitattributes` 加 `backend/data/*.json text eol=lf`）的理由：(a) 窄、不重签出、
且与仓库里**已落地并转绿**的同形修法一致（`scripts/gen/generate_workpaper_task44_pilot_probe_registry.py`
的 `_normalize_eol()`、`scripts/check/check_task44_oo94_excel_pilot_gate.py` 的 `read_task_body()`）。

#### 2.1 为什么 Tier A **不能**一起归一 —— 这是本轮最重要的反直觉结论

任务书要求"两处都修"。实测表明**修 Tier A 会把门直接打死**，故未修，理由如下。

Tier A 的基线是 `backend/data/onlyoffice_word_instrumentation_gate.json`。对它登记的每条
文本 digest 逐条比对"raw 值 vs 归一值"，**工作树与 HEAD 两个版本都测**（排除未提交改动的干扰）：

| 基线版本 | 文本条目 | CRLF-captured | LF-captured | 内容漂移 |
|---|---|---|---|---|
| worktree | 7 | **7** | 0 | 0 |
| **HEAD** | 7 | **7** | 0 | 0 |

7 条全部是 **CRLF-captured**（`carrier_contract` / `fingerprint_module` / `probe_script` /
`operation_matrix` / `instrumentation_report` / `independent_recompute` / `oo_build`），
即这份 fail-closed 基线本身就是在 Windows 工作树上采的。

后果两条，缺一不可：
1. **只在读侧归一 ⇒ 实测变 LF 值、与基线的 CRLF 值不符 ⇒ `WordSdtCarrierGate.load()`
   立刻 fail closed，所有调用方全红。**
2. **归一也救不了 Linux**：LF 工作树无论归一与否都算不出 CRLF digest，基线值在 Linux 上**不可达**。

⇒ 真正的平台无关需要「归一读」+「基线重采成 LF 值」**同时**改；后者要改 `backend/data/` 下的
fail-closed 基线产物，属独立决策（见 §6 决策包），不在本次范围。

同一个文件因此**合法地**需要两个 digest：Tier A 的 `role=carrier_contract` 登记 CRLF 值 `bb8290…`
（必须 raw 读），而产物里发布的 `carrier_contract_sha256` 登记 LF 值 `be4d…`（必须归一读）。
所以这不是"只修了一半"，而是两个角色本来就该用两种读法。

### 3. 修复后实测：digest 回到 `be4d…`，产物零改动

```
gate.load() = OK
  carrier_contract_sha256 = be4d11dde4e92110d8da74c8da6de849c62f2ea58233f54e5ab6632466d67acc
```

磁盘上登记 `carrier_contract_sha256` 的产物共 2 份，两份都已经是 `be4d…`，**均未重新生成**：

| 产物 | 登记值 |
|---|---|
| `backend/data/workpaper_sync_task62_generic_docx_adjudication.json` | `be4d11dd…`（= LF/CI 值）|
| `backend/data/workpaper_sync_a16_a17_word_chain_adjudication.json` | `be4d11dd…`（= LF/CI 值）|

### 4. 变异验证：门没有被改成 no-op

方法：在契约 JSON 里翻**一个整数位**，保持字节长度不变（只动内容、不动排版），
`finally` 里按内存原字节还原并用 digest 复验。

```
[baseline]  17270 bytes  raw=bb829090…  norm=be4d11dd…  gate.load()=OK(green)
[mutation]  "expected_tag_count" 8 -> 9   17270 bytes (长度不变: True)
   [1] 归一 digest 变了      : True   (be4d11dd… -> cea70b8a…)
   [2] gate.load() 转红      : True   WordProbeEvidenceStaleError
   [3] 归一对行尾不敏感      : True   (CRLF 形态与 LF 形态 digest 相等)
[restore]   与原字节逐字节相同: True   raw=bb829090…  norm=be4d11dd…  gate.load()=OK(green again)
[VERDICT] PASS - gate is NOT a no-op
```

关键点：[1] 与 [3] 一起成立才算真修好——digest 对**内容**敏感、对**行尾**不敏感。
只验 [2] 是不够的（[2] 是经 Tier A 的 raw 判据转红，不能证明归一那条判据还活着）。

### 5. 3+2 个节点的逐条复测

命令（三份文件，`-q --tb=short -rf -p no:randomly`）：
`test_task62_generic_docx_entries.py` + `test_task64_dedicated_word_chain.py` + `test_task63_subcode_adjudication.py`
→ **4 failed, 116 passed, 7 xfailed**。

| # | 节点 | 结果 | 判定 |
|---|---|---|---|
| 1 | `task62::TestGeneratorIsIdempotentAndCheckIsStrict::test_build_record_is_byte_stable` | ✅ 绿 | EOL 修复关闭 |
| 2 | `task62::TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk` | ✅ 绿 | EOL 修复关闭 |
| 3 | `task64::TestGeneratorContract::test_generator_check_is_idempotent` | ❌ 仍红 | **独立红**：registry 真实增长，非 EOL |
| 4 | `task63::TestAdjudicationRecord::test_record_is_reproducible` | ❌ 仍红 | **独立红**：输入仍在动 |
| 5 | `task63::TestResidencyReverification::test_source_digests_cover_every_file_the_measured_criteria_read` | ❌ 仍红 | **独立红** + 底下压着真 EOL 受害者 |

`task62` 文件整体 **53 passed**（含上面 #1 #2）。所以任务书预期的"关闭 3 条"实际关闭 **2 条**；
第 3 条不是 EOL 问题，证据如下。

#### 5.1 #3 task64：EOL 已不在差异里，真因是 adapter registry 从 4 涨到 10

把 `build_record()` 现算结果与磁盘产物 `workpaper_sync_a16_a17_word_chain_adjudication.json`
逐字段展平对比：**47 处字段差异，全部落在 `registry_facts` 一个子树内**，
且 `carrier_contract_sha256` **不在差异清单里**（证明 EOL 那条已经对上了）。

```
registry_facts.delivered_per_entry_contract_count   on_disk=4   recomputed=10
registry_facts.allowed_provider_modules[4..9]       on_disk=<MISSING>
    recomputed= phase5_d1_notes_receivable / phase5_d3_prepaid_receipts /
                phase5_d4_revenue_detail / phase5_d5_receivables_financing /
                phase5_d6_contract_assets / phase5_d7_contract_liabilities
registry_facts.available_contract_ids[4..9]         on_disk=<MISSING>
    recomputed= d1.notes_receivable_detail … d7.contract_liabilities_detail
build_record() 连跑两次 canonical bytes 相同 -> True   （生成器确定性，不是随机红）
```

⇒ 冻结产物停在 4 条 per-entry contract，而 D 循环 phase5_d1~d7 provider 已经进仓。
这是 §1 根因 B（下游冻结基线没跟上）那一类，**须重跑生成器**——本次范围禁止改
`backend/data/` 产物，且此刻仓库有 151 条未提交改动、其中含 6 份 `backend/data/*.json`
manifest slice 正在被并行改，重跑会把别人半成品焊进基线。→ 交 owner，见 §6。

生成器自身还有一个**掩盖诊断**的小 bug：`--check` 失败路径 print `\u21b3`（↳），
在 GBK 控制台抛 `UnicodeEncodeError`，把真实差异信息盖成编码栈。
复现须带 `PYTHONIOENCODING=utf-8` 才看得见 `popup source digest 未变` 这句关键提示。

#### 5.2 #4 / #5 task63：输入仍在动；且底下压着一份**真** EOL 受害者

`test_bp16_manifest_criterion_is_recomputed_from_the_manifest` 报 `186 == 155`
（manifest 条目增长），`test_source_digests_cover_every_file…` 首个断言就死在
`adapters/registry.py`。对该产物登记的每条 source digest 逐条三方比对：

| 登记文件 | 登记值属于 | 判定 |
|---|---|---|
| `backend/app/services/workpaper_sync/adapters/registry.py` | 既非 raw 也非 LF | **真漂移**：工作树==HEAD，但基线比 HEAD 还旧 |
| `backend/data/workpaper_sync_entry_manifest.json` | 既非 raw 也非 LF | **真漂移**：未提交改动（并行工作）|
| `backend/app/services/workpaper_sync/word_sdt_engine.py` | **LF 值** | 🔴 **纯 EOL 受害者**（内容==HEAD，只因 raw 读而红）|
| `backend/app/services/workpaper_sync/word_instrumentation.py` | HEAD blob 的 LF 值 | 本次修复动了此文件内容，叠加 |
| `backend/data/workpaper_word_template_adjudication.json` | **raw/CRLF 值** | 现在靠 raw 读才过 |
| `backend/app/data/wp_code_overrides.json` | **raw/CRLF 值** | 现在靠 raw 读才过 |
| `backend/wp_templates/_index.json` | **raw/CRLF 值** | 现在靠 raw 读才过 |

⇒ **这份基线是 CRLF-captured 与 LF-captured 混在一起的**。把 task63 的读侧改成归一，
会修好 `word_sdt_engine.py` 一条、同时把上面 3 条现在过的打红。**读侧单改在此处数学上不可能修好**，
与 §2.1 的 Tier A 同构。这两条节点的正确定性是：**仍在动（真漂移）**，
且即使漂移收敛也还需要基线重采才能彻底转绿。

### 6. 触类旁通全仓扫描（按"登记值到底等于哪个 digest"实测，不靠 grep 猜）

grep `read_bytes()`-then-hash 会捞出上百个 mutation harness 的**同进程自还原**校验
（`before/after` 比的是同一份字节，跨平台无风险），信噪比太低。改为直接量**危害面**：
扫描 `backend/data/**/*.json` 与 `.kiro/specs/**/*.json` 里所有持久化的 `{path, sha256}` 对，
只保留指向"工作树含 CRLF 的文本文件"的条目，逐条判定登记值等于 raw 还是归一值。

```
TOTAL text entries examined: 451     baselines touched: 27
   CRLF-captured = 193      LF-captured = 33      drifted = 225
MIXED baselines (一个文件里两种采集风格并存) = 5
```

| 基线 | 判定 |
|---|---|
| `backend/app/services/workpaper_sync/word_instrumentation.py` `contract_digest` | ✅ **FIXED**（本次）|
| 同文件 Tier A 三处 `_sha256_bytes(target.read_bytes())`（约 line 360 / 408 / 455） | ⚠️ **LATENT-LEFT（刻意）**：基线 7/7 CRLF-captured，归一即 fail closed，见 §2.1 |
| `backend/data/onlyoffice_excel_instrumentation_gate.json` | ⚠️ **LATENT-LEFT**：5/5 CRLF-captured，与 Word 门**完全同构**（Excel 侧同一个坑，同一个理由不能单改读侧）|
| `backend/data/workpaper_sync_task63_subcode_adjudication.json` | ⚠️ **LATENT-LEFT（MIXED）**：raw 与 LF 混采，读侧单改会净增红，见 §5.2 |
| `backend/data/workpaper_sync_task66_legacy_deletion_plan.json` | ⚠️ **LATENT-LEFT（MIXED）** |
| `.kiro/.../g0-4-host-consumes-unified-path/index.json` | ⚠️ **LATENT-LEFT（MIXED）** |
| `.kiro/.../task49-g-cycle-migration/mutation_report.json` | ⚠️ **LATENT-LEFT（MIXED）**：8 CRLF / 2 LF |
| `.kiro/specs/four-table-extraction-entry-completion/evidence/gap-inventory.json` | ⚠️ **LATENT-LEFT（MIXED）** |
| `backend/data/workpaper_sync_legacy_baseline.json` 等 156 条全 drifted 的基线 | ⏸ 与 EOL 无关，属 §1 根因 B/C 的漂移面 |
| `scripts/gen/generate_workpaper_task44_pilot_probe_registry.py` `_normalize_eol()` | ✅ 先例，已绿 |
| `scripts/check/check_task44_oo94_excel_pilot_gate.py` `read_task_body()` | ✅ 先例，已绿 |

**结论（本次修复最有价值的副产物）**：全仓 EOL 采集风格是**不一致**的 ——
193 条按 Windows CRLF 采、33 条按 LF 采、5 份基线内部自相矛盾。
所以"把所有 raw hash 都改成归一 hash"是**错的**，会打红 193 条；
反之"全留 raw"会让那 33 条在 Linux/CI 上不可达。
唯一彻底解法是**统一采集口径**（推荐全部归一为 LF）并**一次性重采全部基线**，
这必须是一次独立、串行、仓库干净时的动作。

### 7. 修法 (b) 未实施，附实测爆炸半径

按要求**未施加** `.gitattributes` 的 `backend/data/*.json text eol=lf`。实测半径：

```
backend/data/*.json      (顶层)   190 个，其中含 CRLF 181 个
backend/data/**/*.json   (递归)  1008 个，其中含 CRLF 987 个
其中同时有未提交改动的顶层文件：6 个
    workpaper_resolver_migration_matrix.json / workpaper_row_change_reachability.json
    workpaper_sync_abcs_cycle_manifest_slice.json / workpaper_sync_d_cycle_manifest_slice.json
    workpaper_sync_entry_overlay.json / workpaper_sync_n_cycle_manifest_slice.json
仓库未提交条目总数：151
```

即 (b) 会重写 **987 个**工作树文件的行尾，与 151 条在途改动正面相撞；
更关键的是它会让上面 **193 条 CRLF-captured digest 全部失配**（§6），
等于把 5 个 fail-closed 门同时打红。**(b) 单独做是净负收益**，必须与"基线重采"打包。

### 8. 顺手修掉一个误导诊断的测试名

`task62::test_build_record_is_byte_stable` 名为"两次构建字节稳定"，实际实现是：

```python
def test_build_record_is_byte_stable(self, record):   # record fixture = 读磁盘产物
    again = GEN.build_record()                        # 只算一次
    assert GEN._canonical_text(again) == GEN._canonical_text(record)
```

三个后果：① 确定性**从未被测**（只有一次现算，没有第二次可比）② 它与
`test_check_matches_the_file_on_disk` 断言同一个事实，一处上游漂移打红两条，虚增计数
③ 失败信息写"记录含非确定性内容（时间戳/集合序）"，把诊断引向"生成器非确定性"，
而实测生成器连跑 3 次 0 diff、真因是行尾 —— 本轮诊断确实被它带偏过。

已改为**名副其实**：去掉 `record` fixture，改成连调两次 `build_record()` 相比，
并留 🔴 注释说明不要把 fixture 加回来。覆盖率没有损失（"现算 == 磁盘"由
`test_check_matches_the_file_on_disk` 原样覆盖），反而补上了原本缺失的确定性判据。
改后 `test_task62_generic_docx_entries.py` **53 passed**。

### 9. 交 owner 的决策（补充 §6 的三个决策包）

| # | 决策 | 为什么必须 owner 拍板 |
|---|---|---|
| D-EOL-1 | **统一全仓 digest 采集口径为 LF + 一次性重采 5 个 fail-closed 门的基线** | 要改 `backend/data/` 下的 fail-closed 基线产物；必须在仓库干净、无并行在途时串行做，否则焊进半成品 |
| D-EOL-2 | 重跑 `generate_task64_dedicated_word_chain.py --write` 收敛 registry 4→10 | 同上，且此刻 6 份 manifest slice 正被并行修改 |
| D-EOL-3 | 修 `generate_task64_*.py` 的 `↳` GBK `UnicodeEncodeError` | 纯诊断可用性，无判据语义，可随时做 |

### 10. 本次改动清单

| 文件 | 改动 |
|---|---|
| `backend/app/services/workpaper_sync/word_instrumentation.py` | 新增 `_normalize_eol()` / `_sha256_text_source()`；`contract_digest` 改归一；Tier A 处加"刻意保留 raw"的 🔴 理由注释 |
| `backend/tests/workpaper_sync/test_task62_generic_docx_entries.py` | `test_build_record_is_byte_stable` 改为真的两次现算相比（§8）|
| `backend/data/**` | **零改动**（无任何产物被重新生成）|
| `.gitattributes` | **未改**（修法 (b) 仅作建议，见 §7）|

---

# 决策包 2 落地（row-change 传播清册）

**授权**：§6 决策包 2（优先级 2）已获准落地。本节是 §3.3 那份"测量完成、未落地"的收口。
**环境**：cwd=`d:\GT_plan\backend`，python=`..\.venv\Scripts\python.exe`，
每文件 `-q --tb=short -rf -p no:randomly`。**全程未跑整套 `tests/workpaper_sync`**，
未碰任何 `*_pg.py`，未跑 `setup_wp_templates_dir.py`，未动 `backend/wp_templates/**`
（`git diff --stat` 对该目录**零条目**实证），未用 `git stash` / `checkout --` / `reset`。

## 0. 结论摘要

| part | 内容 | 结果 |
|------|------|------|
| 1 | `generate_row_change_reachability.py --apply` + diff 形状再体检 | ✅ 落盘；形状与 §3.3 描述**逐项吻合**，另查出 §3.3 漏记的一维（见 §2.1 第 6 行） |
| 2 | design.md 分母表（10 值）+ 标记表（5 行） | ✅ 两条 design 表判据转绿 |
| 3 | `test_d2_is_the_only_entry_with_propagation_demand` 重裁 | ✅ **属性仍成立，已重新表达并转绿**，无需 owner 裁决；判据改名为 `test_d2_remains_the_sole_maximal_propagation_carrier` |
| 4 | 变异验证（产物侧 2 条 + design.md 侧 2 条 + part3 非重言 5 条 + 变异清单 M07 1 条） | ✅ 10/10 按预期 RED，产物与 design.md 均按 sha256 逐字还原 |
| 5 | `zero_regression::test_behaviour_matches_frozen_baseline` | 🔴 **仍红，未重冻结**（Q2 REFUSE 成立，且**本次落地对它零影响**：前后都是 1F/17P） |

**§3.3 的预测被修正了一处（更好的结果）**：那里预测"落盘后 3F/19P"。实测落盘 + part 2 之后是
**1F/21P**，落盘 + part 2 + part 3 之后是 **22P 全绿**。原预测把两条 design 表判据算成"新红"，
但它们是**可修的**（改真源表即可），不是需裁决的；真正需裁决的只有第 3 条，而它重裁后成立。

**净结果**（精确计数）：stale 产物原本撑着 **3 条假绿**（`test_design_denominator_table_matches_inventory`、
`test_design_marker_table_matches_inventory`、`test_d2_is_the_only_entry_with_propagation_demand`），
另有 **2 条诚实红**（#12 `test_inventory_matches_current_computation`、#13 `test_host_binding_is_content_addressed`）。
落地后：3 条假绿 → **真绿**（2 条靠改真源表、1 条靠重裁），2 条诚实红 → **绿**，
**新红 0 条，被抬宽的基线 0 条，被重冻结的产物 0 份。**

## 1. Part 1：重生成 + diff 形状再体检

`--apply` 输出与 §3.3 那次测量**逐字相同**：

```
xlsx 352 / 含跨 sheet 182 / 引用 144154 处 / 受影响 136 份 / 已发契约 entry 10 / 极端组合 10（最大 63240）
```

`git diff --numstat` = **1029 / 182**，与 §3.3 登记值精确一致。

> ⚠ 计数口径备忘：`git -c core.autocrlf=false diff --numstat` 给的是 **4673 / 3826**
> —— 那是"整份文件都变了"的行尾噪声（本仓 `core.autocrlf=true`，见 §1 根因 A）。
> **1029/182 才是内容级 diff**。后来者若量出四千多行不要惊慌，先看 autocrlf。

### 1.1 逐维体检（我自己重跑的，不是引用 §3.3）

| 维度 | §3.3 描述 | 本次实测 | 吻合 |
|------|----------|---------|------|
| 顶层键 | 无增无删 | 仅 before `[]` / 仅 after `[]` | ✅ |
| `contracted_entries` | 4→10，新增 6 / 删 0 / 改 0，恰为 d1/d3/d4/d5/d6/d7 | 4→10，**新增 6 / 删除 0 / 改动 0**，逐一核对为 d1/d3/d4/d5/d6/d7 | ✅ |
| `host_ambiguity` | 4→44，新增 40 / 删 0 / 改 1；40 条全部可归因到 6 份新契约，其中 35 条涉新 D4 工作簿、5 条 `templates_containing: 1` | 4→44，**新增 40 / 删除 0 / 改动 1**；**40/40 全部可归因**（无法归因 0 条）；`bound_host` 是新 D4 工作簿的 **35** 条；`templates_containing == 1` 的 **5** 条；改动那 1 条是 `附注披露信息（国企）` 39→40 | ✅ |
| `denominators` | 10 项变动，全部可归因 | 10 项，键无增删，逐项归因见下表 | ✅ |
| `placeholder_markers` | 12 键无增删，5 项计数位移 | 12 键无增删，**5** 项位移（ellipsis_single / ellipsis_double / xx_placeholder / item_n / dots_ascii） | ✅ |
| `affected_templates` | §3.3 **未提** | 🔴 **136 → 136（无增无删），但有 5 行内容变动**：D1/D3/D5/D6/D7 的 `state/reason` 从 `blocked/no_projection_contract` 翻成 `propagated/implemented` | ⚠ 补记 |
| `extremes` | §3.3 未提 | 10 → 10，无增删无改动 | — |

**§3.3 漏记的那一维是良性的，且是生成器的既定分叉**：`build_inventory()` 里
`"state": "propagated" if in_contract else "blocked"` —— 这 5 份模板刚拿到契约，翻转是
**定义使然**，不是新事实。它不改变 `affected_templates` 的**条数**（136 不变），所以
`test_affected_inventory_covers_declared_denominator` 与
`test_uncontracted_templates_are_blocked_with_gate1_reason`（阈值 90%）都不受影响：
无契约阻塞的从 135/136 降到 **130/136 = 95.6% > 90%**，仍成立。

### 1.2 10 个分母的逐项归因

| key | Wave 0 | 现算 | 归因 |
|---|---:|---:|---|
| `xlsx_total` | 351 | 352 | 新增权威工作簿 `D/D4 收入底稿.xlsx`（commit `d3b3d80d9`，已 push；`git status` 对 `wp_templates/D/` 零未提交项） |
| `delivered_contract_entries` | 4 | 10 | phase5 交付 6 份 per-entry 契约并注册 adapter |
| `external_sites` | 2908 | 2902 | D3/D5/D6/D7 模板净化丢弃 `externalReference`（commit `1a0b55651`，§1 根因 B 已验为良性） |
| `max_host_name_collisions` | 39 | 40 | `附注披露信息（国企）` 多一份同名 sheet 宿主（新 D4 工作簿） |
| `defined_name_cross` | 5002 | 5004 | 新 D4 工作簿 |
| `defined_name_builtin_self_scope` | 2457 | 2505 | 新 D4 + 净化后外链目标回到簿内 |
| `defined_name_target_not_in_workbook` | 2001 | 1949 | 净化去外链 ⇒ 这一类 −52 |
| `defined_name_user_self_scope` | 292 | 298 | 新 D4 工作簿 |
| `hyperlink_location_cross` | 3480 | 3553 | 新 D4 工作簿 |
| `hyperlink_location_in_workbook` | 3138 | 3211 | 同上 |

**两条自洽校验现场复算通过**：definedNames 四分类和 `2505+1949+298+252 = 5004` **恰等**总数；
hyperlink 三分类 `3211+321 = 3532`，`3553 − 3532 = 21` **恰等**原登记的 `same_sheet` 21。
⇒ 这两个和不是凑出来的，是同一次扫描的内部一致结果。

**零无关 churn 复核**：`templates_with_cross_sheet` 182 / `cross_sheet_sites` 144154 /
`cross_sheet_formulas` 72825 / `resolvable_*` 三项 / `unresolvable_cross_sheet_sites` 3428 /
`affected_templates` 136 / `extreme_max_sites` 63240 等 20+ 个分母**逐字未变**
⇒ 新 D4 工作簿不含跨 sheet 限定引用，净化也没碰任何被引用关系。**Q1 成立，非洗白。**

## 2. Part 2：design.md 分母表 + 标记表

改的是 `.kiro/specs/excel-workbook-wide-row-change-propagation/design.md`（+81 行 / 该文件）。

**分母表**：上表 10 个 key 的值改为现算值。**没有一个是被"抬宽"的** —— 全部照
`--apply` 的现算值填。另在表前加了一段带日期的「复算更新」小表，把 Wave 0 值与现算值并列 +
逐项归因，这样后来者不会把这 10 个数字当成无来由的漂移。

**标记表**：5 行计数改为现算值（`ellipsis_single` 730/163→**763/164**、
`ellipsis_double` 625/140→**657/141**、`xx_placeholder` 465/150→**476/151**、
`item_n` 40/24→**41/25**、`dots_ascii` 38/28→**39/29**）。其余 7 行逐字未动，
`renameable` 仍是 **0/0**（表后那句"全库 351 份 xlsx 里命中 0 次"同步改 352，
该 0 值已在现算里复核）。

**刻意没改的三处（保留审计轨迹，本仓铁律「历史档案不回填修改」）**：

1. **Property 28 的零回归冻结分母**（`351` 份 / `126,565` 条公式 / 外部 `2,908` 处）——
   那是 Wave 0 Task 6 于 2026-09-04 **冻结的行为基线**的描述，不是活分母。
   改它 = 给 §5 那条 Q2 REFUSE 的节点偷偷重冻结。**不动。**
2. **Gate 1 / Gate 2 的 Wave 0 普查表**（含"今天这个集合大小是 4"那张四行表、
   "全库 351 份实测"）—— 那是**裁决依据的原始记录**。改写它等于改写裁决过程。
   处置：在原文下方加**带日期的更正块**，指明现算值与真源位置（清册 JSON），原表保留。
3. **`test_uncontracted_templates_are_blocked_with_gate1_reason` 的 0.9 阈值** ——
   实测 130/136 = 95.6% 仍过，阈值不动。只把失败文案里硬写的 `4` 改成引用 `_DELIVERED_CONTRACTS`
   （那是纯文案，不是判据）。

**同步改掉的两处误导性 prose（这两处会直接坑 D2 迁移，见 §6）**：
- 「判据分层」第 2 条：「D2 …… 它是今天**唯一**既有已审核契约、又有真实跨 sheet 引用的 entry」
- Gate 1 裁决第 3 条：「🔴 **今天唯一有真实传播需求的 entry 是 D2**（52 处）」

两处均加带日期的更正块（原句保留 + 明写"上一句的「唯一」已不成立，不要照它规划迁移"），
并补上 5 个 entry 的 fan-in 对照表。

**验收**：`test_design_denominator_table_matches_inventory` 与
`test_design_marker_table_matches_inventory` 双双转绿；该文件由 **2F/20P → 1F/21P**
（剩下的 1F 就是 part 3）。

## 3. Part 3：`test_d2_is_the_only_entry_with_propagation_demand` 重裁（完整推理）

### 3.1 先拆：那条断言实际焊了三件事

原文：

```python
assert with_demand == {"d2.receivable_detail": 52}, (
    f"有传播需求的契约 entry 集合变了：{with_demand} —— Wave 2 的首要判据载体（D2）需重新裁定")
```

它是**一个等式承载三个互相独立的主张**，所以"事实一变就整条塌"：

| # | 被焊进去的主张 | 现状 | 该归谁 |
|---|--------------|------|-------|
| ① | **普查口径**：契约 entry 只有 4 个 | ❌ 已死（现 10 个） | 已由 `delivered_contract_entries` 分母 + `_DELIVERED_CONTRACTS = 10` 各自钉住。在本条里重述 = 重复 |
| ② | **精确处数集合** `{d2: 52}` | ❌ 已死（现 `{d2:52, d3:51, d5:24, d6:3, d7:3}`） | 🔴 已由 `test_inventory_matches_current_computation` 钉住 —— 它用 `diff_inventory()` 把**整个** `contracted_entries` 块与现算逐字比对，**那五个数字早已被锁死**。在这里再抄一遍 = 零新增保护 |
| ③ | **载体裁决**：Wave 2 的判据落在 D2 身上（design.md「首要判据载体」） | ✅ **仍成立** | 🔴 **这才是本条要保护的属性** |

**⇒ 为什么"改成 `{d2:52, d3:51, d5:24, d6:3, d7:3}`"是错的做法**：那只是把 ② 抄一遍，
而 ② **已经被另一条判据逐字锁住了**。这么改不仅零新增保护，还会让本条在每次交付新契约时
都要被人来改一次数字 —— 一条"每次真源变都要手动跟"的判据，最终一定被改成
`len(with_demand) >= 1` 之类的恒真式。本仓 `mutate_workbook_row_change_guards.py` 的 M07
注释里写着同一件事：「把分母改**宽松**（`>= 0` 那类）不会有任何测试失败 ⇒ GREEN ⇒ 那是无效变异」。

### 3.2 再问：③ 还成立吗？成立的**理由**变了吗？

实测（`contracted_entries` 现算，10 个 entry 全列）：

| entry | demand 处数 | 引用侧 sheet 张数 (fan-in) | 被引用的不同行数 | state/reason |
|---|---:|---:|---:|---|
| `d2.receivable_detail` | **52** | **4** | 3 | propagated/implemented |
| `d3.prepaid_receipts_detail` | 51 | 2 | 3 | propagated/implemented |
| `d5.receivables_financing_detail` | 24 | 1 | 2 | propagated/implemented |
| `d6.contract_assets_detail` | 3 | 1 | 1 | propagated/implemented |
| `d7.contract_liabilities_detail` | 3 | 1 | 1 | propagated/implemented |
| `b60` / `d1` / `d4` / `g7` / `h1` | 0 | 0 | 0 | out_of_scope/no_propagation_demand |

**③ 成立（D2 仍是首要载体），但支撑它的度量必须换。** 理由：

🔴 **"处数最多"已经不是一个可用的判据了**：D2 = 52 对 D3 = 51，**领先 1 处（1.9%）**，
且 D2 只占全部需求的 **39.1%**（52/133）。任何对 `D/D3 预收账款.xlsx` 的琐碎改动
（多一条引用公式）就能翻转排名 —— 而那与"谁适合当载体"**毫无关系**。
按处数设的守卫会在无意义的时刻打红，于是下一个人只会把它放宽掉。**脆判据 = 未来的假绿。**

**真正让 D2 成为载体的是 fan-in。** 一次插行会出错的地方，是"多张引用侧 sheet 之间不一致"；
`d5` 那种 24 处**全挤在单张 sheet** 上的是**重复**样本而非**广**样本。
D2 的 fan-in 是次席的 2 倍、其余四个的 4 倍，是唯一能一次压满 AC 2.2/2.3/2.4/2.6 的样本
（design.md 的载体理由本来写的就是这个：「被 **4 张 sheet** 的 52 处公式引用」，
当时"唯一有需求"这一点让 fan-in 显得只是个描述，现在它才是承重的那半）。

### 3.3 重新表达的属性

判据改名 `test_d2_is_the_only_entry_with_propagation_demand` →
**`test_d2_remains_the_sole_maximal_propagation_carrier`**（旧名字断言的是一个**已为假**的事实，
留着名字就是留着误导）。新断言三段：

**P1（反真空下界）**：`_PRIMARY_CARRIER`（= `d2.receivable_detail`，写成显式常量而非从数据现取，
因为它是一个**裁决**）必须在需求队列里；且队列规模 `>= _MIN_DEMAND_COHORT = 2`。
理由：下面的"严格最大"在比较集为空/单元素时会**真空成立**。
🔴 刻意**不写 `== 5`** —— 那五个数字已被 §3.1 ② 那条判据逐字锁住，抄过来就是复述。

**P2（载体裁决，承重的那条）**：
`fan_in[D2] > max(fan_in[其它全部有需求 entry])`，**严格大于**。
`best_other` 取的是**其它全部**的最大值，所以"严格 >"一条同时表达了**最大**与**唯一**：
两个 entry 并列最大 ⇒ margin == 0 ⇒ 红。这就是"证据不被摊薄"的形式化。

**P3（demand ⟺ state/reason 双条件）**：对**全部 10 个** entry 断言
`demand > 0 ⟺ (state, reason) ∈ {(blocked, pending_implementation), (propagated, implemented)}`，
`demand == 0 ⟺ (out_of_scope, no_propagation_demand)`。
原断言只对"D2 之外"要求 `out_of_scope` —— 那在"只有 D2 有需求"时才等价于双条件；
今天 5 个有需求，**诚实的推广是双向蕴含**，而不是把 d3/d5/d6/d7 挪到白名单里。

**为什么 P2 不是重言式（三条独立论证）**：

1. **可被真实世界推翻**：任一 entry 的 fan-in 涨到 4，或 D2 掉下来 ⇒ 红。而那时载体
   **确实**该重裁 —— 红得有意义。变异 MV3/MV4/MV5 实测全 RED（§4）。
2. **不能靠放宽通过**：多列几个 entry 只会让它**更难**成立。这条性质是"抗放宽"的，
   与原等式相反（原等式放宽即绿）。
3. 🔴 **携带的信息严格多于"放宽版复述"**——已实测证明：在 MV4（把 D3 的 fan-in 改成 4，
   与 D2 并列）之下，`with_demand` 的值**逐字不变**
   （`{d2:52, d3:51, d5:24, d6:3, d7:3}`）⇒ **放宽版等式判 GREEN（漏抓）**，
   而 fan-in 版判 **RED**。这就直接证明了"把断言扩成 d2/d3/d5/d6/d7 有需求"是**信息更少**的写法。

**顺手删掉一条我自己写出来的装饰性断言**：首版我在 P2 后面还跟了
`assert at_max == [_PRIMARY_CARRIER]`（"达到最大值的只有一个"）。复核发现它被 P2
**严格蕴含**（`margin > 0` ⟹ 任何 other 都 `< D2` ⟹ `at_max` 必为单元素）⇒ 它永远
不可能单独打红，是一行恒真装饰。按本仓「变异用例的唯一保护性」口径**已删除**，
uniqueness 的语义并入 P2 的失败文案。

### 3.4 裁决结论

**属性仍然成立，不需要 owner 决策，part 3 已落地转绿。**

说清边界：**我没有改动任何范围裁决。** Gate 1 的裁决（覆盖面 = 有契约的 entry 集合，
其余 `no_projection_contract`）原样不动；D2 作为 Wave 2 首要判据载体的裁决原样不动。
我改的是**支撑这个裁决的度量**：从"唯一有需求"（已为假）换成"fan-in 严格唯一最大"（为真）。
① 与 ② 两个已死的主张**没有被改写成新的等式，而是被移交给了已经在管它们的判据**。

**若将来 P2 打红，那时才是真的需要 owner**：owner = `excel-workbook-wide-row-change-propagation`
spec / Wave 2 责任人；解除动作 = 重选首要判据载体（fan-in 最大的那个）并同步
design.md「判据分层」第 2 条 + Gate 1 第 3 条。

## 4. Part 4：变异验证（10 条，全部按预期 RED）

驱动脚本一律 `try/finally` 按**字节**还原，并以 sha256 复核。**未用 git 还原手段。**

### 4.1 产物侧（证明 freshness / inventory 判据真在读产物）

产物基线 `sha256 = fee32b1070083159208690cb3eae7f995085e85ba7e34fb44d239900c79c80cd`（126,897 字节）。

| 变异 | 扰动 | 等长 | 跑的 node | 判定 |
|------|------|------|----------|------|
| MV1 | `"xlsx_total": 352` → `353` | ✅ 字节长度不变 | `test_inventory_matches_current_computation` + `test_design_denominator_table_matches_inventory` | **RED**（2 failed） |
| MV2 | `ellipsis_single.sheets 763` → `764` | ✅ 字节长度不变 | `test_inventory_matches_current_computation` + `test_design_marker_table_matches_inventory` | **RED**（2 failed） |

### 4.2 design.md 侧（证明**双向**锁的另半边也是活的）

MV1/MV2 只证明了"产物变了会红"。要证明 design 表**那一侧**没有被写成单向读取，
还得反着扰动一次。design.md 基线 `sha256 = f7f19727…`（51,690 字节）：

| 变异 | 扰动 | 等长 | 判定 |
|------|------|------|------|
| MV8 | design.md 分母表 `xlsx_total` **352 → 353** | ✅ | **RED**（`test_design_denominator_table_matches_inventory`） |
| MV9 | design.md 标记表 `ellipsis_single` 命中模板 **164 → 165** | ✅ | **RED**（`test_design_marker_table_matches_inventory`） |

⇒ 两侧各自扰动都红 ⇒ **不是"改真源表跟着改代码"那种单向糊弄，锁是真双向的。**

### 4.3 Part 3 非重言性（扰动"底层的活事实"）

扰动对象是清册里 D2/D3/D6 的 `referencing_sheets` / `propagation_demand_sites` / `state`
（即 part 3 判据依赖的**真实事实**，不是判据本身）：

| 变异 | 扰动的活事实 | 打的是哪一段 | 判定 |
|------|------------|------------|------|
| MV3 | D2 的 fan-in **4 → 2**（掉到与次席并列） | P2 严格最大 | **RED** |
| MV4 | D3 的 fan-in **2 → 4**（并列最大 ⇒ 证据被摊薄） | P2 严格最大 / 唯一性 | **RED** |
| MV5 | D3 的 fan-in **2 → 5**（反超 ⇒ 载体该换人） | P2 严格最大 | **RED** |
| MV6 | D6 有 3 处需求却标 `out_of_scope/no_propagation_demand` | P3 双条件耦合 | **RED** |
| MV7 | 把需求队列缩到只剩 D2（d3/d5/d6/d7 归零） | P1 反真空下界 | **RED** |

**MV7 是专门验 P1 不是装饰的**：若没有这条下界，MV7 之后 `max(others)` 会抛/或
比较集退化成单元素，"严格最大"真空成立 ⇒ 判据变恒真。实测 RED ⇒ 下界承重。

🔴 **MV4 的附带结论（§3.3 第 3 点的实测依据）**：MV4 之下 `with_demand` 逐字不变
⇒ **"放宽版"等式在 MV4 上判 GREEN，fan-in 版判 RED。** 这是"重新表达 ≠ 复述产物"的硬证据。

**还原校验**：产物 `sha256` 回到 `fee32b10…`（与基线一致 = True）；
design.md `sha256` 回到 `f7f19727…`（一致 = True）。

### 4.4 变异清单 M07 的锚点迁移（顺手修掉一处会静默失效的耦合）

`backend/scripts/diagnose/mutate_workbook_row_change_guards.py` 的 **M07** 锚在
`assert with_demand == {"d2.receivable_detail": 52}, (` 这一整行上 —— 我重裁把这行删了，
**锚点会漂移**。该文件自己的注释里记着上一次锚点漂移的教训（「锚点必须按内容现查」，
且「`--check-anchors` 报 OK ≠ 打中我想要的那一处」），所以不能只靠自检。

处置：把 M07 重锚到重裁后的 `assert margin > 0, (`，变异为
`assert margin > 99, (`（要求 fan-in 领先 99 张，实测领先 2 张 ⇒ **更严格且不成立**，
符合 M07 原本的"只有改严格才是有效变异"口径），并把口径更换的理由与
"为什么新口径刻意不再打处数"写进注释。

**实跑验证**（不只是 `--check-anchors`）：

```
--check-anchors : 10/10 OK, 0 MISS （M07 命中 L530，唯一）
--run M07       : be 侧基线 49 passed / 1 skipped
                  判定 RED (8.2s)  还原=True
                  1 failed, 48 passed, 1 skipped
                  命中 want = test_workbook_row_change_reachability.py::
                              test_d2_remains_the_sole_maximal_propagation_carrier
                  新增失败 1 条（无连带）
```

⇒ 打中的正是重裁后的那条判据，新增失败恰好 1 条，无连带，文件按 md5 还原、无 `.mutbak` 残留。

## 5. Part 5：`zero_regression::test_behaviour_matches_frozen_baseline` 的状态

**结论：仍红，未重冻结，且本次落地对它零影响。** 前后都是 **1F / 17P**
（落地前实测 1F/17P，落地后实测 1F/17P，红的是同一条）。这是预期的 ——
它读的是**另一份**冻结产物（`generate_workbook_row_change_zero_regression_baseline.py`），
与 row-change 清册无关，清册落盘不可能影响它。

**§2 第 15 行的 Q2 REFUSE 判定本轮复核后成立，且证据比 §3.3 记的更硬。** 实测 4 处差异：

| # | 差异 | 详情 |
|---|------|------|
| 1 | `denominators` | `xlsx_total` 351→**352**、`formula_texts` 126565→**126727**、`external_sites` 2908→**2902**；`cross_sheet_formulas` 72825 / `cross_sheet_sites` 144154 / `templates_with_cross_sheet` 182 / `three_d_sites` 0 **未变** |
| 2 | 新增模板 | `['D/D4 收入底稿.xlsx']` |
| 3 | 🔴 `D/D7 合同负债.xlsx` 的三个 digest **全变** | `insert_ctx` `120e4e11…` → `e62813a6…`；`insert_no_ctx` `120e4e11…` → `e62813a6…`；`filldown` `fe3be94f…` → `255b0d5a…` |
| 4 | `D/D7 合同负债.xlsx` 的 `formulas` | 206 → **200**（少 6 条） |

**测试自己写了三条 re-freeze 前置**（失败文案原文）：
① 确认差异全部落在 `filldown` 情景而不是跨 sheet 的绝对引用；
② `insert_ctx` / `insert_no_ctx` **不得变**；③ 才可以重跑 `--apply` 并在 commit 里写明理由。
**否则这是真因归零（真实回归）。**

🔴 **①②两条**都不成立：`insert_ctx` 与 `insert_no_ctx` 双双漂移（第 3 行），
差异也不止落在 `filldown`。⇒ **重冻结会把一个未被解释的 `insert_ctx` 变动焊成新基线，
从此再也无法分辨"D7 的插行改写行为变了"是净化的副作用还是 `_rewrite_formula_refs` 的回归。
拒绝重冻结。**

**最可能的真因（明确标为未验证）**：D7 模板净化（commit `1a0b55651`，−77% 字节，
丢弃 `externalReference`）把 6 条依赖外链的公式一并去掉 ⇒ `formulas` 206→200 可解释，
digest 变动也可解释。但"可解释"≠"已证明"：`insert_ctx` 是**插行后**的行为指纹，
要证明它只因公式少了 6 条而变、而非改写逻辑变了，必须拿净化**前**的 D7 跑一遍对照。

**给 owner 的一条可执行诊断**（我没有执行，属节点 #15 的裁决范围）：
用 `git show 1a0b55651^:"backend/wp_templates/D/D7 合同负债.xlsx"` 取净化前字节到临时路径
（只读，不碰 `wp_templates/`），对它跑同一份基线生成器的单模板路径，比对 `insert_ctx`。
- 若净化前的 `insert_ctx` == 冻结值 `120e4e11…`，且净化后 == `e62813a6…`
  ⇒ 变动**纯由模板内容引起**，re-freeze 前置②可以带理由豁免，此时重冻结是合法的。
- 若对不上 ⇒ 是 `_rewrite_formula_refs` 侧的真实行为变化，**必须先定位代码**。

**owner**：D 循环权威模板责任人 + Wave 0 Task 6 零回归基线责任人（同一次裁决，
与 §2 的 #2 / #3 / #11 同源 —— 都是 `1a0b55651` 的下游未跟上）。

## 6. 🔴 对即将开始的 D2 底稿迁移的影响（本节比测试计数重要）

用户即将把**全部 D2 底稿**迁到以 D4 为范本的统一双向路径。**落地前，磁盘上的传播清册
会把这次迁移引到一张错的地图上**，具体错三处：

| 迁移规划会读到的（落地前） | 真实情况 | 后果 |
|---|---|---|
| 契约 entry **4** 个（b60 / d2 / g7 / h1） | **10** 个（新增 d1 / d3 / d4 / d5 / d6 / d7） | 会把 D 循环当成"只有 D2 有契约"，**D4 范本自身的契约 `d4.revenue_detail` 在旧清册里根本不存在** —— 照旧清册规划，"以 D4 为范本"这句话在清册层面无从对照 |
| 只有 **D2** 有传播需求 | **5 个**有：`d2=52 / d3=51 / d5=24 / d6=3 / d7=3` | 会以为"迁完 D2 就把传播这条线收干净了"。实际 D3 只比 D2 少 1 处，**迁 D2 的同一套改动会立刻在 D3/D5/D6/D7 上产生同型需求**，不纳入就是 4 个新缺口 |
| D1/D3/D5/D6/D7 五份受影响模板是 `blocked / no_projection_contract` | 已翻成 `propagated / implemented` | 会以为这五份"没契约、不用管"，实际它们**已经在传播路径上**了 |

**两条对迁移的直接建议（不属本次授权，只上报）**：

1. **D4 是范本但它自己 `propagation_demand_sites = 0`**（fan-in 0）。也就是说
   D4 的双向路径**从未在"受管 sheet 被本工作簿其它 sheet 引用"这个场景下被行使过**
   —— 而 D2 恰恰有 52 处、4 张引用侧 sheet。把 D2 迁到 D4 范本上，等于**第一次**让该范本
   承担跨 sheet 传播。建议迁移计划里把这条列为首要风险项，并以 D2 的 52 处作为验收样本
   （design.md 已实测其形态：绝对行区间 18 / 相对行单格 24 / `#REF!` 10）。
2. **迁移会不会动 D2 模板的公式，是本次新判据的红线**。
   `test_d2_remains_the_sole_maximal_propagation_carrier` 的 fan-in 取自**权威模板的公式**，
   与运行时路径无关 ⇒ 正常迁移**不该**让它变红。**若它在迁移中打红，那是一个信号
   而不是一个麻烦**：说明迁移改动了 D2 权威模板的引用关系，那必须先解释再继续。

⇒ **这就是决策包 2 必须在 D2 迁移之前落地的原因，也是它优先级高于测试计数的原因。**

## 7. 前后计数（逐文件）

先确认"读同一份产物的兄弟文件"到底是哪些 —— 全仓 grep `workpaper_row_change_reachability`
实证：**只有 2 个测试文件读它**（`test_workbook_row_change_reachability.py` 与
`test_workbook_row_change_carriers.py`）。`insert` / `apply` / `zero_regression` 不读它，
但按要求一并量了基线，用来证明"落盘零连带"。

| 文件 | 落地前 | 落地后 | 变化 |
|------|-------|-------|------|
| `test_workbook_row_change_reachability.py` | **2F / 20P** | ✅ **0F / 22P** | 2 条诚实红转绿 + 3 条假绿转真绿 |
| `test_workbook_row_change_carriers.py`（读同一产物） | 0F / 30P | ✅ 0F / 30P | 无回归 |
| `test_workbook_row_change_insert.py` | 0F / 43P | ✅ 0F / 43P | 无回归 |
| `test_workbook_row_change_apply.py` | 0F / 26P | ✅ 0F / 26P | 无回归 |
| `test_workbook_row_change_zero_regression.py` | 1F / 17P | 🔴 1F / 17P | **零影响**，见 §5（Q2 REFUSE 保留） |
| **合计（5 文件一次跑）** | 3F / 136P | **1F / 138P** | 净 −2F / +2P |

（最后一行的合计由一次 5 文件联跑实测：`1 failed, 138 passed in 20.35s`。）

## 8. 落盘清单与收尾核对

`git diff --stat`（4 个文件，**`backend/wp_templates` 零条目**）：

```
.kiro/specs/.../design.md                                    |   81 +-
backend/data/workpaper_row_change_reachability.json          | 1211 ++++++++++---
backend/scripts/diagnose/mutate_workbook_row_change_guards.py|   23 +-
backend/tests/.../test_workbook_row_change_reachability.py    |  158 ++-
4 files changed, 1244 insertions(+), 229 deletions(-)
```

🔴 **归属声明（这棵树里有大量他人未提交改动，别把它们记到本包账上）**：
`git status` 显示 `backend/data/workpaper_sync_entry_manifest.json`、多份 `*_pg.py`、
两份 `*.generated.ts` **也处于 modified 状态 —— 那些是本会话开始前就在树里的他人改动，
不是本包所为**。本包的足迹精确地就是上面那 4 个文件（另加本证据文档，untracked）。
判断依据：对本包路径单独跑 `git diff --stat` 得到的恰好是那 4 行。

**没有碰的**（逐条自查）：`*_pg.py` —— 本包**一次都没有打开或写入**（另有 agent 正在用真库）；
`backend/wp_templates/**` —— `git status` 对该目录**零条目**，逐字未动；
未跑 `setup_wp_templates_dir.py`；`workpaper_sync_entry_manifest.json` / overlay /
`*.generated.ts` —— 本包零写入；未跑整套 `tests/workpaper_sync`；未用
`git stash` / `git checkout --` / `git reset`（所有 HEAD 对照走 `git show HEAD:<path>`，
所有还原走"预先按字节快照 + 写回 + sha256 复核"）；未重冻结任何冻结基线；
未抬宽任何天花板（唯一被调大的数字 `_DELIVERED_CONTRACTS` 在上一轮已落地，本轮未动）。

**顺带发现（不属本次授权，上报）**：`tasks.md` 与
`docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md` §2661 都登记
Wave 5 Task 29 交付了一条判据 **`test_only_d2_flipped_to_propagated`**
（"翻成 `propagated` 的 entry 集合恰为 D2，受影响模板分布恰为
`{(blocked, no_projection_contract): 135, (propagated, implemented): 1}`"）。
**全仓 grep 实证：该测试函数不存在**，只在被重裁掉的那条判据的注释里被引用
（「恰好是哪一态」由它单独钉死）。⇒ 那句注释是**悬空引用**，且"恰好是哪一态"实际上
**没有任何判据在钉**。本轮重裁已把状态维以 P3 双条件的形式接管（比原设想更强：管全部 10 个
entry 而不只是 D2），注释里的悬空引用已随整段重写移除。
若 owner 仍要那条独立判据，它的登记值现在应是 **5 个 entry 翻转**、
分布 `{(blocked, no_projection_contract): 130, (propagated, implemented): 6}`。

**未解除、仍留给 owner 的**（与本包无关，原样保留）：§2 的 #2 #3 #4 #5 #6 #7 #8 #9 #10 #11 #15。
决策包 2 的三个解除条件（§6 优先级 2）**全部满足并已落地**。

### 8.1 §2 十五行判定表的节点映射（表本身按审计轨迹原样保留，不回填）

§2 那张表是"本轮复核（落地前）"的快照，**刻意不改**。读表的人请按下表对照当前状态：

| §2 行号 | 节点 | §2 登记 | 本节落地后 |
|---|------|---------|-----------|
| #12 | `test_inventory_matches_current_computation` | ❌ 红（Q1 但耦合 BLOCKED） | ✅ **绿** —— 产物已落盘，耦合已解 |
| #13 | `test_host_binding_is_content_addressed` | ❌ 红 | ✅ **绿** —— 10/10 契约 digest 与磁盘相符，`problems = 0` |
| #14 | `test_binding_verifier_detects_injected_digest_drift` | ✅ 绿 | ✅ 绿（未动） |
| #15 | `test_behaviour_matches_frozen_baseline` | ❌ 红（Q2 拒绝重冻结） | 🔴 **仍红，原样保留**，见 §5 |
| §6 决策包 2 | 三个解除条件 | 待 owner | ✅ **三条全部落地** |

⇒ §2 的统计"2 绿 / 13 红"在本节之后应读作 **4 绿 / 11 红**（#12 #13 转绿），
其中 11 条红仍全部是诚实红。

> 📌 一处看起来像矛盾、实则自洽的数：**有传播需求的 entry 是 5 个，但翻成
> `propagated` 的受影响模板是 6 份。** 原因是 `affected_templates` 的分叉依据是
> `rel_path in contracted_templates`（**有没有契约**），而 `contracted_entries` 的分叉依据是
> `propagation_demand_sites > 0`（**有没有需求**）。D1 有契约但需求为 0 ⇒ 它的模板算第 6 份。
> 两个口径**本来就不同**，生成器里是两处独立分支。（D4 的模板不在 `affected_templates` 里
> —— 它没有"被引用 sheet 含占位标记"的命中。）
