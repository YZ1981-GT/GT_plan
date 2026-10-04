# 证据：D4 物化的趟数 / 墙钟 / 内存峰值

**spec**：`oo-single-pass-materialize-and-room-leave`　**Requirement 1.1 / 1.5**

## 怎么重跑（任务 7 的「前后对照」就是重跑它）

```powershell
# 逐 binding 链式路径（改动前基线）
.venv\Scripts\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py --mode chained
# 当前默认路径（单趟化落地后用它记「后」，建议同时换 --label）
.venv\Scripts\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py --mode default
# 任务 7：like-for-like 前后对照（生产 CPU 段五步逐段 · 两路径交错 · 3 轮）
.venv\Scripts\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py `
    --segment --mode both --repeat 3 --label task7-segment-before-after
```

⚠️ 上面前两条量的是 `adapter.materialize` **一段**；需求 1.5 的「~30s」是 materialize +
extract + verify 合计的口径 —— 两者不可互比，正式判定看 `--segment` 那条（见本文「任务 7」节）。

墙钟与内存分两趟量：tracemalloc 对这条路径的开销是数量级的（同机实测 69s vs 20s），
掺进去的数字既高估现状也会高估提速，所以 `timing` 只来自**没开** tracemalloc 的那趟。

## 文件

| 文件 | 路径 | 说明 |
|---|---|---|
| `baseline-chained.json` | 显式摘掉单趟入口 | **回落**路径（插行 / openpyxl 全量重写 / 同格 payload 冲突时走它）；`test_chained_fallback_path_call_counts` 钉的就是它 |
| `current-default.json` | 当前默认路径 | 任务 3 落地后 = **单趟**路径，`single_pass_log` 为「单趟物化命中」 |
| `task7-segment-before-after.json` | `--segment --mode both --repeat 3` | **任务 7** 的 like-for-like 前后对照：生产 CPU 段五步逐段 × 两条路径 × 3 轮，含需求 1.5 的机器可读判定（`verdict`）与 steady-state 探针 |
| `binding-dependencies.json` | `analyze_d4_binding_dependencies.py` | 任务 2 的 39 binding 依赖调查逐一入册 |

## 2026-09-22 实测（阶段 2 · 任务 3 单趟写入落地后）

单趟化把 decline 判据从「跨 binding 坐标碰撞」收紧为「坐标碰撞**且写入 payload 冲突**」
（拍板记录见 design 附录 A.7），D4 的 4 格良性重叠因此可以合并，单趟对 D4 真正生效：

| 量 | 链式（回落路径） | 单趟（默认路径） | 说明 |
|---|---|---|---|
| 写入趟数 | 39 | **1** | 单趟入口只走一次，39 份计划共用同一份 substrate 字节 |
| `openpyxl.load_workbook` | 83 | **7** | —— |
| 其中 substrate 链（文件） | 78 = 39 趟 × 两视图 | **2** | 需求 1.1 要解耦的就是这一项，上界 `≤ 2` |
| 其中 BytesIO 固定开销 | 5 | 5 | 转置 sheet 4 + 整簿指纹 1，不随 binding 数变 |
| `Workbook.save` | 2 | 2 | 全来自转置 sheet；主写入是 zip 级字节改写 |
| 墙钟 | 16.7s | **5.3s** | ⚠️ 这一格只是 `adapter.materialize` **一段**。任务 7 的 like-for-like 实测：「≤10s」在这一段上成立，在用户那份 ~30s 的口径（materialize+extract+verify 全段）上**尚未**成立（12.8s）—— 见本文「任务 7」节 |
| tracemalloc 峰值 | 118.1MiB | **26.0MiB** | —— |
| 进程 RSS 峰值 | 257.6MiB | 160.1MiB | `peak_wset`，含 harness 铺 world |

🔴 design 七里「openpyxl 单趟写入内存峰值升高 ⇒ 可能 OOM」这条风险**实测反向**：少解析
76 次 workbook 之后峰值内存降了 4.5 倍，不需要「按 sheet 分组多趟」的退路。

⚠️ 产物 `sha256` 在两次运行之间**本就不同**（见本文末「产物字节不是逐字节可复现的」），
所以本目录里 chained 与 default 两份的 `artifact.sha256` 不相等**不能**当成「新旧不等值」
的证据；`artifact.bytes` 两边均为 246110。新旧等值的正式判据是任务 4 的反读逐字段比对。

## 2026-09-22 实测（阶段 1 · 改动前基线）

| 量 | 实测 | 备注 |
|---|---|---|
| binding 数 | 39 | 真实契约派生，不是手写清单 |
| `materialize_projection` 趟数 | 39 | 一 binding 一趟 |
| `openpyxl.load_workbook` | 83 | 78 = 39 趟 × `data_only` 两视图；+4 转置 sheet；+1 整簿指纹 |
| `Workbook.save` | 2 | 全部来自转置 sheet；主写入是 zip 级字节改写，不过 openpyxl |
| 墙钟 | 20.3s（chained）/ 22.2s（default） | 单次 `adapter.materialize`，不含 extract/verify |
| tracemalloc 峰值 | 118MiB | 仅 Python 堆 |
| 进程 RSS 峰值 | 258MiB | `peak_wset`，含 harness 铺 world |

🔴 **两处与 requirements 1.1 措辞不符，按实测记**：`load_workbook` 是 83 不是 39；
`Workbook.save` 是 2 不是 39。随趟数走的只有那 78 次，另 5 次（转置 4 + 指纹 1）是固定
开销、不随 binding 数变，单趟化带不走 —— 所以「load/save 各降到 1」这个目标对 `save`
本就不成立，对 `load` 的可达下界也不是 1。最终判据由任务 3 定。

**阶段 1 时单趟入口 decline 的原因**（当时 `current-default.json` 的 `single_pass_log` 原文）：
binding `customer_prior_rows` 与 `customer_current_rows` **都写 `sheet14.xml` 的第 38 行**
—— 真实契约里存在跨 binding 的同格写入，先后由链式顺序决定。这条直接喂任务 2 的依赖调查。

⚠️ **日志里那个列号（实测见过 `C38` 与 `E38`）是不确定的**：decline 检查按
`for coord in set(plan.coords)` 遍历，set 顺序随进程 hash 种子变 ⇒ 每次报的是碰撞集合里
**任意一格**。完整碰撞集合由任务 2 求出（见下），本证据只如实记「报的列号不唯一」，
避免下游把 `C38` 当成唯一碰撞点。

✅ 任务 3 已修掉这条不确定性：判据改为逐对求交 + 按 `(part, 行, 列)` 排序 + 报**完整**碰撞
集合（`excel_materialize._cross_binding_payload_conflicts`），且只在 payload 真冲突时才
decline ⇒ D4 不再回落。

## 2026-09-22 实测（阶段 1 · 任务 2 依赖调查）

```powershell
.venv\Scripts\python.exe backend/scripts/analyze/analyze_d4_binding_dependencies.py
```

证据 `binding-dependencies.json`。结论摘要（完整版见
`.kiro/specs/oo-single-pass-materialize-and-room-leave/design.md` 附录 A）：

| 依赖类 | 判决 | 实证 |
|---|---|---|
| 读前一 binding 的写入结果 | **实证无依赖** | 39/39 binding 的计划签名在「原始字节」与「链式字节」上完全相同（漂移 0） |
| 跨 binding 同坐标写入 | **4 格，良性** | `sheet14.xml` 的 `C24`/`E24`/`C38`/`E38`，碰撞对仅 `customer_current_rows` × `customer_prior_rows`；两方 payload 逐字段相同，两种顺序 apply 后该 part 逐字节相同 |
| 公式落格 | **实证无依赖** | 52 处受保护格全 `cached_value_only`（`<f>` 逐字保留），`formula_text` 改写 0 处 |
| 跨 sheet 引用 | **实证无命中** | 扫 47 个 worksheet part / 168 条 `<f>`，指向他人写入面的引用 0 条 |
| 命名区域 / `_GT_SYNC` | **本趟无依赖（有前提）** | `xl/workbook.xml` 与 `_GT_SYNC` 本趟未被写（39/39 无 `row_shift`）；插行路径下这三处会被改写，那是真依赖 |

🔴 **两处更正**：碰撞是 **4 格**不是 1 格；行 38 **不是**「两区共用的合计行」（本期段 footer=23、
上期段 footer=37，行 24/38 分别是两段各自的总额行）。真因是 D4-9 的表级标量表
`customer_totals` 按 `managed_tables_of` 的静态表归属规则被**两个** binding 共同持有。
⇒ 当前「坐标相交即 decline」对 D4 是**过度保守**，D4 本可合并。

## 另一条阶段 1 实测：产物字节**不是**逐字节可复现的

同一 projection 连续两次物化，`artifact.sha256` 不同（本目录两次 chained 各不相同），
但逐 zip entry 比对：**全部 entry 的字节完全相同**，差异只在 zip 条目的时间戳
（实测 `23:44:42` vs `23:45:02`）。

对任务 4「新旧产物等值判据」的直接含义：**不能拿 sha256 或裸字节比新旧路径**，否则会红在
一个与单趟化无关的原因上。判据要么按需求 1.2 走「反读等值」（`extract` 逐字段比），要么
逐 entry 比字节并显式忽略 `date_time`。

## 2026-09-22 实测（阶段 2 · 任务 4 新旧产物等值）

判据（**不产证据 JSON，判据本身就是证据**）：
`backend/tests/workpaper_sync/test_single_pass_artifact_equivalence.py`（27 条，实测 57s）。

```powershell
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_single_pass_artifact_equivalence.py -q   # cwd = backend
```

「旧链式」不是 git 检出的考古复刻，而是**仍在服役的回落路径**（`force_chained_path()` 摘掉
单趟入口即到达）。判据显式断言两侧真的走了不同路径：链式 39 趟 / substrate 解析 78，单趟
1 趟 / substrate 解析 2 —— 否则「逐字段相等」会永远绿。

| 量 | 链式 | 单趟 |
|---|---|---|
| `extract` 字段数 | 218 | 218（**0 缺 / 0 多 / 0 改**；header 与 `row_keys` 全同） |
| zip entry | 142 | 142（内容**逐 entry 全同**；142/142 `date_time` 不同 ⇒ sha256 不同） |
| 产物字节 | 246110 | 246110 |

⇒ 需求 1.2 成立：单趟没有少写任何东西。比较面取 `repr(value)`（与
`excel_materialize._write_payload` 同口径）——`0`/`0.0`/`Decimal('0')`/`False` 在 `==` 下相等
而落盘字节不同，用 `==` 比这条判据就是空话。

### 🔴 变异反证顺带证明：反读判据单独**不够用**

| 漏写一个 binding（只注入单趟侧） | 反读判据 | 字节判据 |
|---|---|---|
| `d4_32_groups`（34 处 `inline_text`） | **红**：24 个字段 `'1'` → `1` | 红：`sheet41.xml` |
| `d4_10_rows`（49 处写入） | **绿 ⇐ 窟窿** | **红**：`sheet15.xml` −95 字节 |

projection 取自 substrate 自身 ⇒ 漏写 = 保留原值 ⇒ ① key 集合不会少（所以 design P2 原话
「字段缺失」实测是**值/类型变**）；② 写入只改变单元格**表示形态**而不改变反读值时，漏写在
`extract` 侧完全看不见。**所以逐 entry 字节判据（忽略 `date_time`）是必需项，不是加强项。**
详见 design 附录 B.4（需求 1.2 措辞是否补入字节判据，待拍板）。

## 2026-09-22 实测（阶段 2 · 任务 7 真库前后对照 · **需求 1.5 的正式判定**）

证据：`task7-segment-before-after.json`（本目录里唯一一份**多轮 + 分段**的，与任务 1/3 那两份
单轮单段的分开命名）。

```powershell
.venv\Scripts\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py `
    --segment --mode both --repeat 3 --label task7-segment-before-after
```

### 为什么不能直接拿 5.3s 去比 30s

requirements 1.5 的「~30s」与 design 一的 cProfile 拆解（materialize 42.8 / extract 6.0 /
verify 6.9）是用户在真实切 OO 时观测的，口径是 **materialize + extract + verify 合计**；
任务 1/3 那两份证据量的是 `adapter.materialize` **一段**。拿 5.3s 比 30s 是换了口径 ——
所以本任务改量**生产 CPU 段**（`ContentMutationService._stage_cpu_segment_scoped`）的五步，
两条路径同段对同段。脚本带一条复刻自检（生产那段的调用清单少一步就报错，不许悄悄少量一段），
证据里记 `protocol.replica_fidelity`：五步全部在生产源码里找到，且生产确实用**一个**
`workbook_read_scope()` 包住整段。

### 协议（为了让「前后对照」不退化成「先后对照」）

| 项 | 做法 |
|---|---|
| 同一 wp / 同一 projection | 一个 world 建一次，两条路径共用同一份 substrate 字节与同一份 projection |
| 多轮 | 每条路径 3 轮，记 **min/median/max**；判定按 **max**（最慢轮），不挑最有利的样本 |
| 交错 | 同一轮里 chained→default 紧邻跑，机器漂移不整段落在一侧 |
| 结构指纹缓存 | 每轮前 `clear_structure_fingerprint_cache()` —— 它按**字节内容**记忆化，不清就是第一轮付钱、后面几轮白捡 |
| tracemalloc | **关**（开着这条路径要 3 倍时间，掺进去会同时高估现状与提速） |
| 反空转 | 每轮断言路径真的不同：chained 39 趟 / 单趟 0 次，default 1 趟 / 单趟 1 次 —— `force_chained_path()` 哪天变 no-op，脚本直接报错而不是产出一份「提速 0%」的证据 |

### 分段实测（3 轮 · min / median / max，秒）

| 段 | 链式（改动前） | 单趟（改动后） | 说明 |
|---|---|---|---|
| `materialize` | 17.089 / **17.127** / 17.510 | 5.418 / **5.490** / 5.602 | 本 spec 阶段 2 唯一动过的一段，median 提速 **3.12×** |
| `extract` | 2.798 / 2.800 / 2.931 | 2.720 / **2.747** / 2.820 | 未优化（产物全量重解一遍） |
| `roundtrip_verify` | 0.001 | **0.001** | 纯内存逐字段比对，成本可忽略 |
| `unmanaged_verify` | 2.137 / 2.170 / 2.676 | 2.081 / **2.113** / 2.131 | 未优化 |
| `structure_hash` | 2.322 / 2.342 / 2.382 | 2.405 / **2.408** / 2.412 | 未优化（发布时刻整簿再解一遍） |
| **CPU 段合计** | 24.611 / **24.791** / 24.886 | 12.675 / **12.800** / 12.876 | median 提速 1.94× |

三轮之间的漂移很小（单趟侧 materialize 全落在 5.42~5.60），与任务 1 时期同一 HEAD 上
16.7/19.8/20.3/22.2s 那种漂移不是一个量级 —— 交错 + 清缓存 + 关 tracemalloc 三条协议起了作用。
`spans_sum` 与 `segment_total` 逐轮吻合（12.800 vs 12.800）⇒ 段与段之间没有未计入的时间。

### 需求 1.5 判定：**部分达成（partial）**

| 口径 | 改动前 median | 改动后 median / max | ≤10s？ |
|---|---|---|---|
| `adapter.materialize` 一段（requirements 1.5 字面的「物化耗时」） | 17.127s | 5.490s / 5.602s | ✅ **达标**（连最慢轮都达标） |
| CPU 段合计（用户那份 ~30s / cProfile 三段的口径） | 24.791s | 12.800s / 12.876s | ❌ **未达标** |

🔴 **所以需求 1.5 现在不能记「已满足」**：它指名的 D4 entry 上，「物化」若按用户观测的那个
口径算，还差 2.8s。剩下的钱在哪里，逐段是明的：

| 段 | 改动后 median | 归谁 |
|---|---|---|
| `extract` | 2.747s | **任务 8**（产物全量重解） |
| `unmanaged_verify` | 2.113s | **任务 8** |
| `structure_hash` | 2.408s | **任务 8**（发布时刻整簿再解一遍） |
| 合计 | **7.269s** | 任务 8/9 落地前，这 7.3s 一分没动过 |

⇒ 单趟化把 materialize 从 17.1s 压到 5.5s（省 11.6s），CPU 段合计从 24.8s 到 12.8s。要把合计
压到 10s 以内，需要任务 8 把 materialize 之外那 7.3s 里的重复解析吃掉（够不够 2.8s 由任务 8
实测，本任务不预言）。

### 本证据的 total **不是**端到端 —— 不在里面的东西逐条列清

`stage_stream` / `publish_representation` 的文件 IO、projection artifact 序列化与发布、
DB 单事务与 outbox、HTTP / OO 握手 / 前端加载态 —— 全部在 CPU 段**之外**，不在 12.8s 里。
用户感知的 ~30s 含这些。另外本证据量的是**复用落空**那条路径（复用命中时整段压根不跑）。

### 🔴 量 verify 时发现的两件事（都如实登记，都不在本任务修）

**① `verify_unmanaged_regions` 逐 binding 比完就 assert，第一个 binding 报漂移就抛。**
harness world（substrate = 刚 instrument 出来的模板）上它确实抛 —— 首版计时因此只含 39 分之
一的比对量。把那个数字当 verify 成本记进证据，等于把「后」这一侧记少。改法：verify 段内把
`UnmanagedRegionReport.assert_equivalent` 暂换成**收集器**，让生产那个循环跑完 39 个 binding
（生产里 verify 通过时也是跑完 39 个），量到完整成本；每个 report 的结论逐一进证据。

**② 那些漂移是「模板 → 第一代产物」造成的，不是生产缺陷。** 用 steady-state 探针实测：
把第一次物化的产物当 substrate 再跑一整段，**39/39 report 全部等价、drifted 0**
（正常 runs 是 drifted 39/39，首个差异恒为 `workbook_and_styles`）。原因：harness 的 base
模板 `xl/styles.xml` 从未被 openpyxl 重序列化过，而物化里的转置 sheet 会经 `wb.save()` 重写
整簿状态；生产的 substrate 恒是**上一次发布的产物**（已归一化），所以第二代才是生产常态。
探针那一段的耗时也一并记了（materialize 5.435 / extract 2.785 / unmanaged 2.667 /
structure_hash 1.902 / 合计 **12.790s**）—— 与正常 runs 的 12.8s 一致，且那一段 verify 是
**真的判等价**通过的 ⇒ 上面那份 12.8s 不是靠「verify 提前抛出」省出来的。
（verify 的**结论**本就是任务 9 的命题，见 design 附录 D.2 同一纪律。）

### 顺手给任务 8 的坐标（默认路径 · 全 CPU 段的 `load_workbook` 分布）

单段证据里单趟是 7 次（2 文件 + 5 内存）；把 extract/verify/structure_hash 算进来后是
**19 次（4 文件 + 15 内存）**：

| 调用点 | 次数 |
|---|---|
| `phase5_transposed_sheet.py resolve_managed_sheet` | 12 |
| `excel_extract.py _acquire_read_only_workbook` | 4（substrate 两视图 + 产物两视图） |
| `excel_structure_fingerprint.py _structure_fingerprint_uncached` | 2（before + after） |
| `excel_structure_fingerprint.py _read_gt_sync_pairs` | 1 |

链式同口径是 95 次（80 文件 + 15 内存）。需求 2.1 要的「对同一份产物字节解析 1 次」当前是
**2 次**（`data_only` 两视图，而需求 2.2 又明说两视图不可互相冒充）—— 这个口径冲突留给任务 8
拍板，本任务只记实测。转置 sheet 那 12 次也值得任务 8 看一眼（materialize 4 + verify 8）。

### 环境阻塞：真实端到端（走 OO 切换）**未取到**

本地栈是活的（`audit-postgres` / `audit-onlyoffice` 均 healthy，后端 9980 `/api/health` 200，
`working_paper_sync_entry_state` 里 `xlsx/gt-d4-operating-revenue` 有真实行，updated
2026-09-22 13:36）。没做的原因不是栈不通，是**代价与风险**：要让复用落空必须**真改真实项目
底稿内容**（写真库业务数据），而「改动前」那一侧还要把后端切回单趟化之前的 HEAD 重启一次。
两件都超出一条计时证据该自己决定的范围 ⇒ 登记为待拍板，不拿本证据的 12.8s 冒充端到端数字。

## 2026-09-22 实测（阶段 3 · 任务 8 解析复用 · **需求 1.5 达成**）

证据：`task8-segment-after-parse-reuse.json`。任务 7 那份 `task7-segment-before-after.json`
**未覆盖** —— 前后两份都留着，改动前的基线只在那一份里。

```powershell
.venv\Scripts\python.exe backend/scripts/analyze/measure_d4_materialize_baseline.py `
    --segment --mode both --repeat 3 --label task8-segment-after-parse-reuse
```

### 解析次数（本任务的主命题）

| 调用点 | 任务 7（复用前） | 任务 8（复用后） |
|---|---|---|
| `phase5_transposed_sheet resolve_managed_sheet` | 12 | **4**（全是 materialize 私有：每张转置 sheet 读一次 + 写一次） |
| `excel_extract shared_workbook_from_bytes` | — | **1**（产物字节的完整 DOM 视图，8 个消费方共用） |
| `excel_extract _acquire_read_only_workbook` | 4 | 4（substrate 两视图 + 产物两视图） |
| `excel_structure_fingerprint _structure_fingerprint_uncached` | 2 | 2（**不可共享**：`iter_rows()` 会惰性新建空格） |
| `excel_structure_fingerprint _read_gt_sync_pairs` | 1 | 1（**不可共享**，同上） |
| **合计** | **19** | **12** |

产物字节单独看：**12 次 → 5 次**（2 个 `read_only` 视图 + 1 个可共享完整 DOM + 2 个不可共享）。

非 openpyxl 的重复解析同时收掉了（需求 2 的用户故事说的就是「读同一个文件三次」）：

| 量 | 实测 |
|---|---|
| `_sheet_part_map` 调用 | **549** 次 |
| 其中有文件身份的真解析 | `xl/workbook.xml` **3** + Excel Table 清册 **3** = 6（段内 3 个字节形态各一次 ⇒ 下界） |
| 其中 BytesIO（无身份，不记忆化） | `xl/workbook.xml` 39 次（= binding 数，单趟计划阶段）；贵的 `parse_tables` **0** 次 |
| `sharedStrings` 前缀 digest | 调用 117 次 → 真算 ≤4 次 |

### 分段实测（3 轮 · median / max，秒）

| 段 | 任务 7 单趟 median | 任务 8 median / max | 差 |
|---|---|---|---|
| `materialize` | 5.490 | **4.651 / 4.876** | −0.839 |
| `extract` | 2.747 | **1.461 / 1.550** | −1.286 |
| `roundtrip_verify` | 0.001 | 0.001 | 0 |
| `unmanaged_verify` | 2.113 | **0.208 / 0.212** | −1.905 |
| `structure_hash` | 2.408 | **0.991 / 1.047** | −1.417 |
| **CPU 段合计** | **12.800 / 12.876** | **7.463 / 7.470** | **−5.337** |

### 需求 1.5 判定：**达成（met）**

| 口径 | 改动前（任务 7 链式）median | 现在（单趟 + 解析复用）median / max | ≤10s？ |
|---|---|---|---|
| `adapter.materialize` 一段 | 17.127s | **4.651s / 4.876s** | ✅ |
| CPU 段合计（用户那份 ~30s / cProfile 三段的口径） | 24.791s | **7.463s / 7.470s** | ✅ **达标（连最慢轮）** |

任务 7 的判定是「部分达成、还差 2.8s、归任务 8」—— 本任务实交 **5.34s**，余量 2.5s。

⚠️ 口径提醒一字不改：CPU 段合计**不是**端到端（`stage_stream`/`publish_*` 的 IO、DB 单事务、
HTTP/OO 握手、前端加载态都在段外），真实端到端数字仍**未取到**（同任务 7 节末的理由）。
本证据里 `chained` 一列**不是**改动前基线：记忆化对两条路径都生效，链式同轮也降到 20.383s；
「≤10s」只读 `default` 一侧。

### 两处 requirements 措辞变更（本任务拍板并落地）

* **2.1** 从「解析次数 SHALL 为 1」收紧为「每个**解析视图** `(字节身份, read_only, data_only)`
  各 1 次、与消费方个数**解耦**，且每个不可共享的消费方逐一列名」—— 原措辞与 **2.2 自相
  矛盾**（2.2 明说 `data_only` 两视图不可互相冒充）；
* **1.2** 补入「逐 zip entry 字节等值（忽略 `date_time`）」为**必需项** —— 任务 4 实测反读
  判据对「只改表示形态」那一类漏写天生是盲的（漏写 49 处、218 字段全等、少 95 字节）。

详见 design 附录 F（含「登记在案、本任务不做」的 4 条剩余杠杆）。
