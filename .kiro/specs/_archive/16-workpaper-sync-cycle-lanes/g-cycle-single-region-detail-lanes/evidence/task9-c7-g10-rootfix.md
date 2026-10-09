# Task 9 / C-7：G10 交易性金融负债 —— 前端 19 列对齐权威模板 + 后端发布链五环

spec `g-cycle-single-region-detail-lanes` 九条 lane 的**第二条**。
commit：前端 `840663ecb`（18 文件）+ 后端 `cad12759c`（9 文件）。

---

## 1. 模板逐格实测（openpyxl，禁推演）

`G/G10 交易性金融负债.xlsx`：99,458 B / sha256 `3afd5131f3783c017f3b7e728e1b081188de71acebb46bdb43e2f8b24fb63da3` / 12 sheets。
受管 sheet `明细表G10-2`：`max_row=38` / `max_column=24` / **0 个 definedName**。

### 1.1 两级表头与 R9 合并几何

R9 的**横向**合并区只有三个 —— 这是判据口径的关键：

| 合并区 | 值 |
|---|---|
| `C9:E9` | 期初余额 |
| `H9:J9` | 本期变动（增加"+"/减少"—"） |
| `K9:O9` | 期末余额 |

另有六个**跨两行**的单列合并（`A9:A10` 类别 · `B9:B10` 项目【按明细项目列示，如债券名称】 ·
`P9:P10` 到期日 · `Q9:Q10` 票面利率 · `R9:R10` 期末应付利息 · `S9:S10` 发行文件索引）。

🔴 **`F` / `G` 在 R10 有文本但 R9 无任何合并区**：

```
   F  in_r9_group=0  R9=None  R10='期初调整数'
   G  in_r9_group=0  R9=None  R10='期初审定数'
```

这不是模板缺陷，是**负债侧的会计口径**：调整与审定都不拆分量。
⇒ 判据里「是否分组列」必须按**该列是否落在 R9 横向合并区内**判定；照 G9 的
「R10 有叶子 ⇒ 必须声明 `group_header_cell`」会把这两列判红（假红）。
判据 `test_group_header_cell_follows_r9_merge_geometry` 就是按 merge 几何现算的。

### 1.2 有效列 19，UUID 列取 T

`max_column=24` 含空列。逐列实测（R9/R10 + R11-R21 任一非空）有效列恰为 `A..S` 共 **19** 个，
`T`/`U`/`V`/`W`/`X` 全空 ⇒ `uuid_col="T"`（有效列右移一列）。

🔴 **不是 `max_column+1=Y`**。判据 GC-3 的口径是有效列 —— 这条与 G 循环三张
16384 列表（G4-9/G5-9/G6-11）的处置同源：UUID 不能放 `max_col+1`。

### 1.3 六条公式（R11 逐格，R11-R20 同型）

```
E11 = =C11+D11        期初公允价值 = 初始确认金额 + 累计公允价值变动
G11 = =E11+F11        期初审定数（单列调整 F）
K11 = =C11+H11        🔴 期末初始确认金额（未审线，不从审定数 G 推）
L11 = =D11+I11+J11    🔴 期末累计公允价值变动（**含利息 J**）
M11 = =K11+L11        期末公允价值
O11 = =M11+N11        期末审定数（单列调整 N）
```

### 1.4 footer R21 逐列 SUM，O21 唯一例外

```
C21..N21, R21  = =SUM(x11:x20)
O21            = =M21+N21      🔴 唯一例外
P21/Q21/S21    = '--'          文本占位
A21            = '合计'
```

O 列在数据行是 `=M+N`，合计行若照抄 SUM 会与 `M21+N21` 双源；模板选了后者。
这条差异是「footer 不受管」的具体理由之一 —— 引擎按统一 pattern 重写 footer 会抹平它。
判据 `test_footer_is_column_wise_sum_with_o21_exception` 逐格钉住。

### 1.5 裸 IF 现算 28 格

按生产函数 `neutralize_oo_crash_if_formulas` 的口径（**格数**，不是 findall 次数）在模板副本上实测：

| 格数 | sheet |
|---|---|
| 28 | `审定表G10-1` |
| 0 | 其余 11 张（含受管表 `明细表G10-2`） |

⇒ 仍按 per-file 保守策略挂 `oo_crash_neutralization_fn`：中性化作用于整册 substrate 副本，
用户点同册任一 sheet 的在线编辑都会触发整册加载。BP-4（真 OO 9.4 场景集）未交付前
不得以「受管表干净」推断某册不需要。

---

## 2. 前端根治：35 列 → 19 列（用户拍板选项 C）

### 2.1 移除 16 列，每条指得出归属

台账落 `useG10Detail.DROPPED_LEGACY_G10_FIELDS`（判据 `test_dropped_legacy_fields_are_not_managed_and_each_has_a_home` 断言 16 条且每条 reason 非空）。

| 组 | 字段 | 归属 |
|---|---|---|
| FVOCI 口径（**会计错误**） | OCI / 减值四列 | CAS22 下 FVTPL **不确认** OCI 与减值 |
| 属别表 | `fairValueLevel` / `valuationMethod` | `公允价值测试表G10-5` / `第三层次公允价值计量的调节表G10-6` |
| 属别表 | `isDerivative` / `hostContractDesc` / `embeddedDerivativeJudgment` | `衍生金融工具核查表G10-8` |
| 与模板双源 | `currentDecrease` | 模板 H 是净额列（表头逐字「增加"+"/减少"—"」），拆增减会与 H 双源 |
| **口径错** | `closingBalance` | legacy 走审定线（`=期初审定+变动−减少`），与模板 `M=K+L`（未审线）冲突 |
| 资产侧概念 | `confirmationStatus` | G10 是**负债**不对外发函（G9 的 AB「发函情况」才是资产侧函证） |
| 模板无 | `liabilityType` / `counterparty` / `contractDate` / `remark` | 类别走 A、细分走 B 文本、到期日走 P、索引走 S |
| legacy 单值 | `initialAmount` / `openingBalance` / `currentIncrease` / `profitLossAmount` | 与模板 C/E/H/I 重复 |

🔴 **G8/G6 是 FVOCI，不得照抄「删 OCI 四列」** —— 这条反例在 C-6 evidence §1 已登记，
Task 9b（G8）要按 FVOCI 口径**保留** OCI/减值列。

### 2.2 与 G9 的三处会计差异（照镜像会错一整列）

| # | G10（负债） | G9（资产） | 抄错的后果 |
|---|---|---|---|
| ① | 调整/审定**单列**（F/G、N/O，R9 无合并区） | 拆两分量（M/N 调整 → P/Q 审定） | 给 G10 造两列调整会与 F/N 错位一整列 |
| ② | `L=D+I+J` **含利息** | 无此列 | 漏 J ⇒ 期末累计变动与审定数**系统性偏小** |
| ③ | 本期变动是**净额列** | 同（但 G9 有 O 列股息不进余额） | 拆增减列与 H 双源 |

②的会计依据：交易性金融负债的利息计入财务费用**同时增加负债账面价值**。
改造前前端算 `D+I`。判据 `test_closing_fv_accum_includes_interest_column_j`
断言差额恰为 J 且同时推高 M 与 O。

`K=C+H` 走未审线（同 G9 的 `P=C+M`）：期初有调整数时期末初始确认金额不受其影响
（判据造 `openingAdjustment=50` 的行，断言 `closingInitialAmount=110` 而非 160）。

### 2.3 跨表消费方 4 处

| 消费方 | 原行为 | 处置 |
|---|---|---|
| `g10CrossHelpers.pushG10FvToDetail` | G10-5 往 G10-2 回写层次三列 | **停用**恒返 0 不写 store（层次权威源就是 G10-5，G10-2 无此列） |
| `g10DerivativeCross.pushG10DerivativeCheckToDetail` | G10-8 往 G10-2 回写衍生标记 | 同上 |
| `g10CrossHelpers.sumG10DetailLevel3Closing` / `useG10L3Reconciliation` | Level3 名单从明细表倒推 | 改由 **G10-5** 定 |
| `isG10DerivativeDetailRow` | 读已删除的 `isDerivative` | 只按 **B 列项目名称**判 |
| `g10CrossChecks` | `closingAdjusted ?? closingBalance` 回退链 | 审定数一律取模板 O 列，删回退链 |

**停用而非删除**：保签名恒返 0，避免打断 4 个调用方。
`resolveG10LiabilitySuffix` 参数全 optional ⇒ 删 `liabilityType`/`isDerivative` 后自动回落名称推断。

---

## 3. 后端发布链五环

| 环 | 产出 |
|---|---|
| ① 契约 | `generate_phase5_g10_contract.py` + `data/workpaper_sync_contracts/g10.trading_liabilities_detail.json`（写盘前过 `parse_contract`，双向锁；`canonical_digest=6251caeea06c1b6d7…`） |
| ② provider | `phase5_g10_02_detail.py`（155 行 sheet 层）+ `phase5_g10_trading_liabilities.py`（704 行 entry 层） |
| ③ plan | `store_item_registry` G10 plan（单 item + `oo_crash_neutralization_fn`） |
| ④ 登记 | `adapters/registry` 交付登记行（`adapter_registered=False`，卡 BP-1~BP-3 平台级缺口） |
| ⑤ 零回归 | `check_sync_provider_golden_digest` 加 `("g10", "phase5_g10_trading_liabilities", "ADAPTER_ID", True, True)` |

### 3.1 单区 ⇒ 薄转发，不抽伴生模块

G9 是「一个 store 键 × 三个受管区」，store 门面要遍历三段、主模块触 800 行门禁而抽了
`phase5_g9_store_facade.py`。G10 单区 ⇒ 三个门面各自 ≤3 行薄转发框架层引擎（照 G2），
entry 层 704 行未触门禁。

签名形态刚性：`build_store_projection(payload, *, contract, limits=None, store_item_id=None)`
**单位置参**。零回归门按 `mod.build_store_projection(rows, contract=contract)` 调用，
写成两位置参的 F1/F2 在该门上直接 `TypeError`（G2 初版照抄 F1 踩过同一坑）。

### 3.2 wp_code 裁决：幻影码 `G10T`，真码 `G10`

`workpaper_sync_entry_wp_code_adjudication.json` 的该节点逐字：

* `heuristic_would_say: ["G10T"]` —— CamelCase 启发式产物，wp_index **0 命中**
* `wp_codes: ["G10"]` —— 真码，wp_index 有活行
* `store_payload_evidence`：`remark_bytes=2` / `conclusion_bytes=0` / `wp_count_with_payload=1`
* 🔴 该节点的 `contract_id` 就是 `g10.trading_liabilities_detail` —— 与本 provider 的
  `ADAPTER_ID` 逐字一致（不是我起的名，是裁决时就定的）

⇒ 幻影码只用于 matcher 域（`EntryMatcher(document_type="xlsx", wp_codes={"G10T"})`），
provisioning 用真码。`sheet_keys` 留空安全：`G10T` 只服务本 entry 一条（G10 册 1:1）。

### 3.3 🔴 真库载荷 2 B ⇒ 判据一律合成行

与 G9 的 605 B 不同，`G10-detail-rows` 真库是**空数组**。因此：

* roundtrip 判据用合成行，**不**声称「行数 > 0 且来自真库」（那是 G9 的措辞）
* **刻意不**照 G9 补整套迁移函数（`migrateLegacyG9Row` / `isLegacyG9Row` /
  `createG9MigrationStats` / `parseG9DetailRows` 返 `{list,stats}`）与迁移回写 ——
  只在 `enrichG10DetailRow` 内做**读取兼容**（四个 legacy 单值键落位、不回写原名）。
  照 G9 补一套是给不存在的数据写代码。
* BP-10 仍是未清欠账：`G10-detail-rows` 有 **6 处**重复声明（G 循环第二严重，仅次于
  `G1-2-rows` 的 8 处），收敛到 per-cycle storage contract 不在本 lane 范围；
  provider 侧已立单一口径 `all_store_item_ids()`。

---

## 4. 判据与零回归

| 判据 | 结果 |
|---|---|
| `test_g10_column_isomorphism.py`（新建 436 行） | **65 passed** |
| `useG10Detail.spec.ts`（新建） | **36 passed** |
| 六个 lane 判据文件 | 24 failed → **22 failed**（G10 两条转绿） |
| 前端 G9/G10/G13 共 19 文件 | **231 passed / 0 failed** |
| `vue-tsc -p tsconfig._g10.json` | 26 → **25 error**（新引入 1 条已修，余 25 全既存） |
| `check_file_size.py`（7 个暂存文件） | 通过（entry 层 704 < 800；test_task49 3299 = 阈值上限） |

### 4.1 列同构判据四层闭环

① `header_text` 逐列 == 模板逐格（19 列参数化）
② `json_key` 集合/顺序 == 前端 `G10DetailRow`（**双向**相等，不是单向包含）
③ 公式列逐条 + 负债侧三条口径 + 「无减少列」
④ 单区几何 / footer O21 例外 / 幽灵行锚点 / 读写**不盖** `section`

### 4.2 本轮抓到并修掉的真缺陷

`g10CrossChecks.ts:300` 仍引用被删的 `closingBalance` —— 该文件不在 C-7 原改动清单里，
是 `vue-tsc` 窄配置抓出来的（vitest 全绿，因为那条分支没被测到）。
⇒ **教训**：删字段后必须用窄配置 `vue-tsc` 扫一遍，不能只看 vitest。

### 4.3 如实登记的阻塞

* G9/G10 进 golden digest **基线文件**要等 F1 修 `build_store_projection` 两位置参签名 ——
  该门跑到 f1 即 `TypeError`，无法 `--update`。属 `f1-sync-coverage-and-first-canary` 作业面。
  逐 provider 现算实测：14 家里 13 家算得出三个 digest（含 g10），唯一 FAIL 是 f1。
* P18 两条「九条全在 digest / 全发契约」按设计要到 Task 15 才绿；本轮
  `test_all_nine_contracts_are_published` 的缺失名单已从 8 条降到 **7 条**。

---

## 5. 协作事故：并发会话两次撞散暂存区

**不是** `git reset --hard`（工作树完好），是暂存区被撞：

| 时点 | 现象 | 后果 |
|---|---|---|
| 并发会话 commit `09fc4339c`（H6，15:43） | 提交时暂存区含本会话 staged 的两个**共享台账**文件 | `store_item_registry.py` 的 G10 plan 与 `adapters/registry.py` 的交付登记行被它带走（该 commit message 自己也记了「无法分离」） |
| 本会话 `git add` 前端后 | 后端 10 个文件被撞出暂存区 | 第一个 commit 只含前端 18 文件 |

处置：
1. 核 HEAD 内两处台账内容**完整**（sha256 / `L=D+I+J` / BP-10 / 28 格裸 IF 全在）⇒ 不重复提交
2. 撤出当时混入暂存区的并发会话 I2 登记行（`git restore --staged`，不动工作树）
3. 后端另起 commit `cad12759c` 补齐，并在 commit message 里写明拆两 commit 的原因

**对策固化**：`git add` 与 `git commit` 放**同一条命令**缩小竞争窗口；commit 后立刻
`git show --name-only --format="" <sha> | Measure-Object` 核文件数是否等于预期。

---

## 6. 后续 lane 可复用的结论

1. 「是否分组列」一律按**该列是否落在表头组行的横向合并区内**判，不按「叶子行有无文本」判
2. `uuid_col` 取**有效内容列**右移一列，先逐列实测有效列再算（`max_column` 可能含大片空列）
3. footer 的**逐格**公式要实测到「有无例外格」，不能假设整行同型
4. 删前端字段后必须跑窄配置 `vue-tsc`（vitest 覆盖不到的分支只有类型检查能抓）
5. 真库载荷为空的 entry **不**造迁移函数与迁移回写，只做读取兼容
6. 会计口径差异要落到判据（`L` 含 J、`K` 走未审线、单列 vs 两分量），
   靠注释提醒挡不住下一条 lane 照抄
