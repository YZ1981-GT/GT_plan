# J2/J3 lane 真实实施证据（2026-09-27）

## 🔴 前情：本 spec 此前是假绿

`tasks.md` 的 18 个 Task **全部标 `[x]`**，但同文件 Overview 写着
「**状态**：0/18（Task 0~17），Design-First 未实施」，且：

* `evidence/` 目录**不存在**（多条 Task 要求产出证据文件）
* OD-1 ~ OD-4 四个待删 orphan **全部还在**（41 / 37 / 35 / 39 行）

⇒ 判定为**未实施的假绿**。本文件记录本轮的真实实施与现算证据。

## Task 0~2：前置 + 现算基线

| 项 | 现算值 | 与 spec 冻结值 |
|---|---|---|
| `workpaper_sync_j_cycle_deletion_plan.json` | 存在，21 个顶层 key | ✓ 复用不另起 |
| manifest entry 总数 | **155** | ✓（slice 写 186，spec 已标现算） |
| J 域 entry | 2（1 独立 + 1 parent_duplicate） | ✓ |
| J 独立 entry | 恰 **1** = `xlsx/j1/gt-j1-employee-compensation` | ✓ |

## Task 1：JN-1 四侧都验「J2/J3 不是 entry」

① entry 集合恰 1 条（见上）
② manifest 里**无任何** entry 引用两宿主路径（逐 entry JSON 扫描，命中 0）
③ 两宿主外层探针全 0：

| 宿主 | 行数 | `GtOnlyOfficeSheet` | `el-segmented` | `DualMode` | `onlyoffice/health` |
|---|---|---|---|---|---|
| `j2/GtJ2DefinedBenefitPlan.vue` | **238** | 0 | 0 | 0 | 0 |
| `j3/GtJ3ShareBasedPayment.vue` | **210** | 0 | 0 | 0 | 0 |

④ registry 的 import 路径**真解析到**这两个文件（`resolves_to_host: true`）：

* `j2-defined-benefit-plan` → `../../j2/GtJ2DefinedBenefitPlan.vue`
* `j3-share-based-payment` → `../../j3/GtJ3ShareBasedPayment.vue`

🔴 **更正 spec 一处**：componentType 真源是
`components/workpaper/registry/entries/specialized.ts`，**不是** `htmlRendererRegistry.ts`
（后者按 entries 目录聚合，自身不含 j2/j3 路径 —— 按它 grep 会得 0 而误判）。

## Task 3：两阶可达性判定（JN-P5 / JN-P6）

扫描 **7427** 个前端 `.ts` / `.vue`，逐模块现算：

| ID | 文件 | 行数 | 生产边 | 测试边 | barrel 入边 | 两阶判定 | 朴素判据 |
|---|---|---|---|---|---|---|---|
| OD-1 | `components/workpaper/composables/useJ2EntryDualMode.ts` | **41** | 0 | 0 | — | 一阶孤儿 | orphan（对） |
| OD-2 | `components/workpaper/composables/useJ3EntryDualMode.ts` | **37** | 0 | 0 | — | 一阶孤儿 | orphan（对） |
| OD-3 | `composables/workpaper/j2/useJ2DualMode.ts` | **35** | 1（barrel） | 1（spec） | **0** | 二阶孤儿 | **NOT_orphan（错）** |
| OD-4 | `composables/workpaper/j3/useJ3DualMode.ts` | **39** | 1（barrel） | 0 | **0** | 二阶孤儿 | **NOT_orphan（错）** |

🔴 **反证成立**：朴素判据「入度 > 0 ⇒ 不是孤儿」在 OD-3（入度 2）与 OD-4（入度 1）上
给出**错误**结论 ⇒ 两阶配方不是多余的。行数四项与 deletion plan 逐条一致。

## Task 4：sheet 映射「接上就坏」（JN-P7）

| ID | 常量 | 映射目标数 | 模板真实 sheet 数 | 交集 |
|---|---|---|---|---|
| OD-1 | `J2_SHEET_MAP` | **8** | **9** | **空集** |
| OD-2 | `J3_SHEET_MAP` | **4** | **6** | **空集** |

根因：映射用**简码**（`J2-1` / `J3-1`），模板真名是**全名**（`审定表J2-1` / `股份支付情况表J3-1`）。
⇒ 接上宿主会按不存在的 sheet 名取数，「接上就坏」不是「接上能用」；
删它**不等于**丢失 sheet 映射能力 —— 那份能力从来不正确。

## Task 5：OD-4 违规直调（JN-P8）

`useJ3DualMode.ts` 直调 `GET /api/workpapers/onlyoffice/health`
⇒ 命中 `legacy_deletion_paradigm` **step 6 明禁项**（OO 探测只能经 sync bridge 的
materialize 协议）。它自带的 `checkOOHealth` 与共享基类重复且更弱（无 `_silent`、
无信封双形态兼容）。风险性质：现在无危害**只因整个模块不可达**；顺着 barrel
接起来就是绕过 bridge 的旁路。

## Task 6：barrel 入边 + 🔴 不得过度宣称（JN-P9）

两个 barrel 入边**各 0**（现算，按目录名 import 与 `/index` 显式路径两种形态都扫）。

🔴 **不宣称整个 `composables/workpaper/j3/` 目录死**：同目录 `useJ3ImportExport` 有
**真实深链生产边** `components/workpaper/j3/core/J3TabDetail.vue`（不经 barrel）。

### 🔴 本轮新增裁决：两个 barrel **都不删**（与 Task 9 原文的「删两个 orphan barrel」不同）

逐条现算每个 export 的消费情况后发现：

| barrel | export 数 | 有深链生产边 | 仅经 barrel 且**有测试边** | 仅经 barrel 且无测试边 | 可删 |
|---|---|---|---|---|---|
| `j2/index.ts` | 8 | 2 | **4** | 2 | **否** |
| `j3/index.ts` | 8 | 2（删簇后） | 0 | 5 | 是 |

`j2/index.ts` 后面还挂着 4 个「只经它被生产消费」的模块
（`useJ2AccrualCheck` / `useJ2Adjudication` / `useJ2Detail` / `useJ2Disclosure`）——
删 barrel 等于**额外宣称那 4 个也死**，超出本 lane 授权（Task 6 明令不过度宣称，
deletion plan 的 `orphan_dual_mode_to_delete` 精确只列 4 条）。
`j3/index.ts` 虽可删，但同目录还有 5 个 `orphan_behind_barrel` 未被 spec 授权处置，
删 barrel 会把它们一起判死。⇒ **两个 barrel 保留，只摘掉指向已删模块的 re-export**，
并在 barrel 里留注释写清判定依据。剩余 orphan 归下一轮。

## Task 7：共享基类保留 + 🔴 窄口径（JN-P10 / JN-P11）

| 项 | 现算（删除后） | 说明 |
|---|---|---|
| `useWorkpaperEntryDualMode.ts` 行数 | **65** | ✓ 与 spec / plan 一致 |
| `localStorage` 命中 | **0** | ✓ |
| 窄口径（statement）边 | **27** | 删前 29 − OD-1 − OD-2 = 27 |
| 宽口径边 | **31** | — |
| 差集 | **4** 个文件，**含** `workpaperSyncLegacyBaseline.generated.ts` | ✓ JC-16 判据（写「包含」不写死 1 个） |
| J 域贡献（窄口径） | **1** = `j1/GtJ1EmployeeCompensation.vue` | OD-1/OD-2 已删 |

🔴 **三处冻结数字互不一致**（正好印证「禁写死阈值」）：

| 来源 | 窄口径删前 | 宽口径 | 差集 |
|---|---|---|---|
| deletion plan | 29 | **30** | **1 处** |
| `tasks.md` Task 7 | 29 | **34** | 现算 5 个 |
| 本轮现算 | 29（27 + 2） | **33**（31 + 2） | **4 个** |

🔴 **更正 `tasks.md` 的「删后剩 26」**：plan 的 recipe 写「29 − 3 = 26，三条 J 边里
**J1 宿主那条随 step 4 改线消失**」—— 那是**地基 spec** 的动作，不属本 lane。
本 lane 只删 OD-1/OD-2 两条 ⇒ **27** 才是本 lane 完成后的正确值
（plan 的 per-module `action_side_effects` 也写着 29→28→**27**，与本轮实测一致）。

## Task 8：JN-3 `useJ3FormData` 整簇不可达（JN-P12 ~ JN-P16）

| 模块 | 行数 | 生产边 | 非 barrel 生产边 | 自身入度 |
|---|---|---|---|---|
| `useJ3FormData` | **151** | barrel + `useJ3Detail` + `useJ3Integration` | 2 | **3** |
| `useJ3Detail` | 119 | 只 barrel | 0 | **1** |
| `useJ3Integration` | 172 | 无 | 0 | **0** |
| （barrel `j3/index.ts`） | — | — | — | **0** |

🔴 **两层判定的必要性被实测坐实**：单层扫描把 `useJ3FormData` 判成
`alive_via_deep_chain`（它确实有 2 条非 barrel 生产边）—— 只有再看一层
（那 2 条的来源自身入度 1 / 0）才能定性为「只经一个孤立 barrel 相连的簇」。
变异「只看一层」SHALL 判成活着而打红 ✓

管道完整性（证明它长得像活代码）：`render-config` GET **3** · `checklist-responses` PUT **1** ·
`events/publish` **1**（簇内 `useJ3Integration` 另有 **3**，合计 **4**）·
`cross-wp-references/batch` **1**（在 `useJ3Integration`）。

### 🔴 `J3-${key}` 形态：spec 说「生产命中 0」需分成读/写两侧

| 侧 | 现算 | 结论 |
|---|---|---|
| **写** | **0** —— 唯一会写它的就是这个不可达模块 | ✓ `FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION` 成立 |
| **读** | **2 处** —— `j3/core/J3TabIndex.vue` 的 `progressKeys: ['J3-detail', …]` / `['J3-check', …]` | 🔴 spec 未记 |

⇒ 这两个键**永远读到空**，J3 完成度恒少算两项。这是删除**暴露**出来的既有缺陷，
不是删除**造成**的（同 BP-12「猜键回退链静默取空」族）。修法归业务确认，本轮登记不修。

正例锚点：`composables/workpaper/j2/useJ2FormData.ts` **不存在** ✓（上一轮删除已兑现）。
🔴 登记（slice 未提）：`j3/core/J3TabDetail.vue` **自己也直写** `PUT …/checklist-responses`（1 处）。

## Task 9：删除执行（JN-P15 / JN-P38）

已删 **7** 个文件（OD-1~OD-4 + `useJ3FormData` 簇 3 个），共约 **594 行**：

```
components/workpaper/composables/useJ2EntryDualMode.ts      41
components/workpaper/composables/useJ3EntryDualMode.ts      37
composables/workpaper/j2/useJ2DualMode.ts                   35
composables/workpaper/j3/useJ3DualMode.ts                   39
composables/workpaper/j3/useJ3FormData.ts                  151
composables/workpaper/j3/useJ3Detail.ts                    119
composables/workpaper/j3/useJ3Integration.ts               172
```

同步改动：`j2/index.ts` 摘 1 条 re-export · `j3/index.ts` 摘 4 条 ·
`j2/__tests__/j2Components.spec.ts` 去掉 `useJ2DualMode` 的 import 与 describe 块。

删除前**显式确认联动**：`events/publish` 4 处 + `cross-wp-references/batch` 1 处
随整簇消失 —— 现状是整簇不可达 ⇒ 这些联动**本来就没跑过**。

零回归验证：`grep` 四个模块名**零代码引用**（仅剩注释说明）· `tsc --noEmit` 两个 barrel
**EXIT=0** · vitest J 全域 **6 文件 105 passed**。

## Task 10：5 处位置化行身份现算（JN-P17 / JN-P18）

扫 J2/J3 两个组件目录 **23** 个文件，逐处按值命中：

| 族 | 位置 | 改造前写法 |
|---|---|---|
| **family_a** | `j2/J2TabAdjustment.vue#L104` | `id: i + 1`（htmlData 派生，**无**上游兜底） |
| family_b | `j2/J2TabAdjustment.vue#L111` | `id: e.id ?? i + 1` |
| family_b | `j3/core/J3TabCheck.vue#L103` | `id: r.id ?? i + 1` |
| family_b | `j3/core/J3TabCheck.vue#L105` | `id: r.id ?? i + 1` |
| family_b | `j3/core/J3TabDetail.vue#L126` | `id: p.id ?? i + 1` |

**family_a 1 处 / family_b 4 处 / 合计 5** ⇒ 与 spec 声明逐条一致。

### 🔴 真库实证：spec 漏记「family_b 也有已落库的下标身份」

```
J2-3-entries    171 B  [{"id":1,"description":"重分类一年内到期辞退福利",…}]   ← family_a 产生
J3-2-variation  288 B  [{"id":1,"category":"","time":"2024年度",…}]            ← family_b 回落产生
```

spec 只说「family_a 是全 J 域唯一且已有真实数据受影响」⇒ 若按它只对 family_a 做
grandfather，修 family_b 时会**重写 `J3-2-variation` 的 id = 换身份**。
本轮的 grandfather 策略对**两族一致**。

## Task 11 / 12：修复 + grandfather（JN-P19 / JN-P20）

新建 `components/workpaper/composables/jRowIdentity.ts`。

🔴 **不复用 `f5RowIdentity.ts` / `hSeedRowIdentity.ts`**：那两套铸 **string**，而 J 侧
`id` 是 **number** 且宿主用 `Math.max(...)+1` 做游标、`r.id === row.id` 做定位 ⇒
换 string 会让 `Math.max` 返回 `NaN`、打断 4 个行接口的类型、与已落库的数字 id 冲突。
本文件铸 number：`Date.now()*1000 + Math.floor(Math.random()*1000)`
（含随机 ✓ / 不含下标 ✓ / 量级 1.7e15 < `MAX_SAFE_INTEGER` ✓ / 严格大于现存 id ✓）。

🔴 **与 F5 刻意相反的一条**：F5 对「命中旧下标模式」的 id **重铸**，J 侧**不重铸** ——
F5 的旧 id 带可识别前缀（`oc-migrated-3`）能区分「旧格式」与「真身份」，
而 J 侧旧 id 就是裸数字 `1`，**无法**区分「历史下标 1」与「合法身份 1」⇒ 重铸必然误伤。

改动点：5 处 load 回落 → `withJRowIds()` · 5 处新增行 `seq++` → `mintJRowId(...)` ·
删掉 3 个变成只写不读的死游标（`seq` / `vSeq` / `vcSeq`）。

守卫 `__tests__/jRowIdentity.spec.ts` **15 passed**，含：

* **原缺陷复现**：旧写法删中间行后重载 ⇒ C 的身份从 3 变 2，而 2 上一轮属于 B（备注串行）
* **修复后**：删行不改变其余行身份
* **grandfather 反向自检**：造一条 `id: 1` 的历史行，三轮「载入→保存→再载入」后仍是 `1`
* 两条真库载荷（`J2-3-entries` / `J3-2-variation`）的 `id: 1` 原样保留
* 真实回落情形：render-config 种子派生行未保存 / 旧数据 `null`/`undefined`/空串
* 混合批（部分有 id）：有的保留、没的铸新且不与保留者冲突

## Task 14 / 15：模板层现算（JN-P24 ~ JN-P32）

| 项 | J2 | J3 | 与 spec |
|---|---|---|---|
| sheet 数 | **9** | **6** | ✓ |
| definedName 基线 | **37** | **502** | ✓ |
| definedName 断链 | **30** | **479** | ✓ |
| 裸 IF | **12 格 / 24 次** | **0** | 🔴 见下 |
| Excel Table | 0 | 0 | ✓ 干净点 |
| 尾部空格 sheet | 0 | 0 | ✓ |
| 名中空格 sheet | 2 | 1（合计 **3**） | ✓ |
| hidden sheet | `长期应付职工薪酬实质性程序表 L2A` | 无 | ✓ L2A 确为 hidden 且属 **L 循环**串册 |
| 审定表 | `审定表J2-1` | **无** | ✓ J3 无审定表、无独立科目 ⇒ 判据**不得**要求 J3 有 TB 门 |

### 🔴 裸 IF 的计数口径差异（spec 12 vs 实测 24，两个都对）

`审定表J2-1` 有 **12 格**含裸 IF，每格恰好 **2 个嵌套 IF**：

```
I7  =IF(AND(B7=0,E7=0),0,IF(AND(B7=0,E7>0),1,H7/B7))
K7  =IF(AND(D7=0,G7=0),0,IF(AND(D7=0,G7>0),1,J7/D7))
```

⇒ 按**格数**计 12（spec 口径）· 按**出现次数**计 24（findall 口径）。
两者都不错，但**判据必须写明是哪个口径**，否则复核时必然对不上
（这与 J 地基 spec 登记的同类差异同源）。per-file 挂中性化，整册统一挂 SHALL 打红。

### 几何（逐格 openpyxl 实测）

| sheet | max_row | max_column | 有效列 | 公式数 | merged | protection |
|---|---|---|---|---|---|---|
| `明细表J2-2` | **90** | **14** | **14** | **221** | **30** | False |
| `审定表J2-1` | 81 | 14 | 12 | 261 | 17 | False |
| `股份支付情况表J3-1` | **43** | **18** | **14** | **7** | 8 | False |
| `股份支付检查表J3-2` | 43 | 19 | 19 | 27 | 11 | False |

`明细表J2-2` 与 `股份支付情况表J3-1` 六项全部与 spec 逐条一致（含 J3-1 的 f=7 ——
那 7 个公式全是 R3/R4 的 `=底稿目录!A2`/`A3` ⇒ **整表零业务公式**）。
有效列 14 vs max_column 18 ⇒ UUID 列 **15**（不放 19）。

### 🔴 J3 definedName 是跨循环复制残留（逐条样本）

`AS2DocOpenMode` · `_.dbf` · `_1、受本循环影响的相关交易和账户余额`(B) ·
`_1固定资产数据库_筛选打印`(H) · `_2、主要业务活动`(B) · `_2其他资产_开办费除外_明细表`(K) ·
`_3余额表_一级_.dbf` · `fix2000.dbf` · `fixlj2000.dbf` · `zjgch2000.dbf`

spec 列的 6 个样本**全部命中**，本轮另发现 4 个（`_3余额表…` / 三个 `*.dbf`）。
**不删**（删会让 `max_column` 内公式整片失效），只声明「同步时不新增、不改写」。
🔴 比 I 循环严重一级：I 只是「非 0」（I4 476 / I5 334，未查断链），
J 是「非 0 **且绝大多数断链**」（30/37 = 81% · 479/502 = 95%）。

## Task 16：接入前置清单（登记不执行）

🔴 **J2/J3 真库都有非空载荷**（现算 top）⇒ 将来成为 entry 时**满足 canary 硬标准**，
与 J1 的 primary managed table 三键真库全空**相反**：

```
J2-2-dbp-status   2731 B      J2-1-dbo         1503 B
J2-soe-change     2556 B      J2-2-main        1101 B
J2-2-plan-assets  1581 B      J3-2-variation    288 B
```

八项现状：OO 挂载 0 · segmented + 二级门控 0 · 🔴 4 个 orphan **一个都不能接**（已删）·
notice 0 · contract 0 且 **J2 列映射可共用 J1**（两者 14 列语义逐字相同）·
🔴 **J3 不需要 TB 门**（无审定表无独立科目，实测 `adjudication_sheets = []`）·
`wp_guidance/J2.json` 缺失**登记不补** · 两份 render schema **已存在不重造**。

## Task 17：交接与复盘核验

「N 处」类表述与列举项数逐条相等：**4** orphan（已删 4）· **8 / 4** 个映射目标（实测 8 / 4）·
**5** 处位置化（实测 family_a 1 + family_b 4）· **3** 张名中空格（实测 J2 2 + J3 1）·
**四项**干净点（Excel Table 0 / 尾部空格 0 / 越界 0 / retired 0）。

### 本轮对 spec / plan 的 6 处更正（现算否证冻结值）

| # | spec / plan 原文 | 现算 | 性质 |
|---|---|---|---|
| 1 | componentType 真源在 `htmlRendererRegistry.ts` | 实为 `registry/entries/specialized.ts` | 按原文 grep 得 0 会误判 |
| 2 | Task 9「删两个 orphan barrel」 | **都不删**（j2 后挂 4 个仅经它消费的模块） | 删会过度宣称，违 Task 6 |
| 3 | Task 7「删后剩 26」 | 本 lane 后 **27**（26 含地基 spec 的 J1 改线） | plan 的 per-module side effect 也写 27 |
| 4 | 宽口径 30（plan）/ 34（tasks） | **33** | 三处冻结值互不一致 |
| 5 | `J3-${key}` 生产命中 0 | **写** 0 ✓ / **读** 2 处（J3TabIndex 的 progressKeys） | 完成度恒少算两项 |
| 6 | family_a 是「唯一已有真实数据受影响」 | family_b 的 `J3-2-variation` 也已落库 `"id":1` | grandfather 必须覆盖两族 |
| 7 | 裸 IF J2 = 12 | 12 **格** / 24 **次**（每格 2 个嵌套 IF） | 口径差异，判据须写明 |

### 交付边界（七项不交付）

不发 contract · 不注册 adapter · 不做 roundtrip · 不设 canary · 不改模板字节 ·
不把 J2/J3 写进 manifest · 不冻结 J2/J3 键全集。
🔴 **BP-1 ~ BP-4 对本 lane 不是阻塞**（不发 contract 不注册 adapter）—— 已显式登记，
避免后来者误以为本 lane 也卡在平台供给上。

### 未完成项（如实登记，非假绿）

| Task | 状态 | 原因 |
|---|---|---|
| 9（部分） | `[ ]*` | 两个 barrel 保留 —— 删它需先处置 j2 后挂的 4 个 + j3 后挂的 5 个 orphan，超本 lane 授权 |
| 13 | `[ ]*` | J2 披露层 11 键 / J3 9 键的**修法**归业务确认（spec 原文已标 `[ ]*`） |
| 14（清理） | `[ ]*` | definedName 断链清理属模板治理另一链路 |

### 零回归

| 验证 | 结果 |
|---|---|
| `grep` 7 个已删模块名 | **零代码引用**（仅注释说明） |
| `tsc --noEmit` 两个 barrel | **EXIT=0** |
| vitest J 全域（j1/j2/j3 组件 + composables） | **6 文件 105 passed** |
| vitest `jRowIdentity.spec.ts` | **15 passed** |
| `getDiagnostics` 4 个改动文件 | **零 diagnostics** |
| 契约目录 | **不变**（本 lane 不发 contract） |

🔴 **1 项预存失败（与本轮无关）**：`j2/J2RuntimeMigration.unit.test.ts#L26` 断言宿主
不含 `provide('jumpToSection'`，而它实在 `GtJ2DefinedBenefitPlan.vue#L143`。
`git status` 确认本轮**未改**该宿主 ⇒ 测试期望与实现不符，属预存。
