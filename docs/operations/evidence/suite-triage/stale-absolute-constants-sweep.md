# 「绝对常量钉死在旧世界」清扫 —— sync 测试树全量 + D2 前端孪生

- 日期：2026-06-01
- cwd：`d:\GT_plan\backend`（python `..\.venv\Scripts\python.exe`）/ `d:\GT_plan\audit-platform\frontend`（vitest）
- 性质：**预防性**。三个独立 agent 各自撞到同一类腐化，共同点是「判据里写了一个只在某一时刻成立的绝对数字/绝对 id」。
  manifest 已经 **186 → 176 → 155** 走过两次，下一次再动，这些点会再红一批。
- 铁律：本次只动**判据**（断言与其锚点），不改被测生产代码；
  `backend/data/workpaper_sync_entry_manifest.json` 与任何 `*.generated.ts` 一律不手改。

## 修复范式（本轮统一遵循）

> 从**活的真源现算**，而不是把字面量往上顶一格。

已闭环集群的真实先例（`test_task29_timeline_evidence.py:1615`）：

```python
# 绝对下限 175 → 相对下限
assert derived >= len(entries) * 9 // 10
```

并在注释里留下 `186 → 176 → 155` 的沿革，让下一个读者知道**为什么**它必须是相对的。

对写死的 entry_id：优先「在声明的约束下（已登记 / 具备所需 profile）从活 manifest 里挑」，
而不是换一个新的字面量 id；仅当**某条 entry 本身就是被测主体**时才保留显式 id，并在注释里说明。

---

## 已知目标 1：写死已退网的 `xlsx/d4/**` entry_id

### 事实基础

- 21 条 `xlsx/d4/**` manifest entry 已合法退网（D4 各 tab 迁至 `useD4SyncMode`，commit `cd9592ff5` + `ebc6e1b92`）。
- 现算核对：`data/workpaper_sync_entry_manifest.json` 共 **155** 条，其中 `entry_id.startswith("xlsx/d4/")` 的为 **0 条**。

### 命中点（3 处，全部写死 `xlsx/d4/analysis/d4-tab-customer-price`）

| 文件:行 | 语境 |
|---|---|
| `backend/tests/workpaper_sync/test_participant_leave_endpoint.py:181` | `entry = "xlsx/d4/analysis/d4-tab-customer-price"` —— 只用来拼 URL 路径 |
| `backend/tests/workpaper_sync/test_task28_sync_router.py:813` | `@pytest.mark.parametrize` 的 entry 列表第 2 项 |
| `backend/tests/workpaper_sync/test_task31_frontend_contract.py:234` | `for entry in (...)` 三元组第 2 项 |

### 潜伏性判定（BEFORE 实测）

三个文件当时**全绿**，所以这是**潜伏腐化**而非活故障：

```
tests/workpaper_sync/test_participant_leave_endpoint.py   27 passed
tests/workpaper_sync/test_task31_frontend_contract.py     28 passed
tests/workpaper_sync/test_task28_sync_router.py          101 passed
```

同型腐化在 `test_task29_timeline_evidence_pg.py` 已经真实代价过一次 —— recomputer 对未登记入口
fail closed（`EvidenceError`），采集阶段一崩，**41/42 条断言全部连坐**。所以照样修。

---

## 已知目标 2：`observed["total"] == 186`

### 命中点（3 处）

| 文件:行 | 断言 |
|---|---|
| `test_task41_d2_large_json_pilot.py:1672` | `assert observed["total"] == 186, observed["total"]` |
| `test_task42_h1_grouped_dynamic_pilot.py:2681` | 同上 |
| `test_task43_g7_two_level_dynamic_pilot.py:2899` | 同上 |

### 潜伏性判定（BEFORE 实测）

这三条是**活故障**（manifest 已 155）：

```
tests/workpaper_sync/test_task41_d2_large_json_pilot.py       6 failed, 105 passed
tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py 10 failed, 134 passed
tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py 8 failed, 197 passed
```

单点复现（task41）：

```
tests\workpaper_sync\test_task41_d2_large_json_pilot.py:1672:
    assert observed["total"] == 186, observed["total"]
E   AssertionError: 155
E   assert 155 == 186
```

**并行协调**：另一个 agent 正在同三个文件里处理 `TestOrderingGate` 等 capability-flip 失败。
本轮**只碰 `186` 这一行**，改完逐文件复跑对账，确认没有互踩。

---

## 已知目标 3：`d2SyncHostWiring.spec.ts` 6 条前端失败

### 事实基础（HEAD vs 工作树逐锚点核对）

用一次性探针 `backend/scripts/_anchor_probe.py`（`git show HEAD:` 只读比对，未动工作树）实测：

```
anchor                                     HEAD   WORK
useD2SyncBridge(                          False  False
const ooSheetRef                          False  False
ref="ooSheetRef"                          False  False
flushBeforeOo                             False  False
requestForceSave                          False  False
useWorkpaperSyncBridge(                    True   True
const syncEditorHostRef                    True   True
ref="syncEditorHostRef"                    True   True
<WorkpaperSyncEditorHost                   True   True
syncEditorHostRef.value.forceSave()        True   True
formData.flushPendingSave()                True   True
reloadHtml:                                True   True
HEAD chars=21737  WORK chars=21737
```

⇒ 五个旧锚点在 **HEAD 与工作树都不存在** ⇒ 判据**陈旧**，不是回归。
D2 已在 `42d2f6e6f` 迁到统一路径：宿主 import `useWorkpaperSyncBridge`，模板挂
`<WorkpaperSyncEditorHost ref="syncEditorHostRef">`，切回结构化视图时
`await syncEditorHostRef.value.forceSave()`（内部走 room forcesave）。

### BEFORE

```
npx vitest run src/components/workpaper/__tests__/d2SyncHostWiring.spec.ts --reporter=dot
  Tests  6 failed | 9 passed (15)
```

6 条失败分布在前两个 describe（宿主侧）；后两个 describe（`useD2SyncBridge.ts` 自身 + `GtOnlyOfficeSheet.vue`）9 条全绿。

---

## 修复内容（三个已知目标）

### 目标 1 —— 写死的退网 entry_id → 按约束从活 manifest 现挑

新增三个同型 helper，约束**照写**、取值**现算**（排序后取第一条，保证确定性）：

| 文件 | helper | 约束 |
|---|---|---|
| `test_participant_leave_endpoint.py` | `_deep_registered_entry_id(min_segments=4)` | 已登记 + ≥ 4 段 |
| `test_task28_sync_router.py` | `_shape_entry_id(prefix=..., segments=...)` | 已登记 + 前缀 + 段数 |
| `test_task31_frontend_contract.py` | `_shape_entry_ids()` | 三格形态：2 段 xlsx / 4 段 xlsx / docx |

`test_task28` 的 `@pytest.mark.parametrize` 从「三个字面量 id」改为「三个**形态**声明」，
`ids=["two-segment","four-segment","docx"]` 保持不变（用例名不变，可读性不退）。
三处 helper 在形态缺失时抛的是**指对人**的消息：
「这一格形态在真源里已不存在，判据要重挑形态而不是改数字」。

顺带修正 `test_task28` docstring 里同类冻结数字：「186 条 entry_id 全部含 `/`」
→「当时 186 条，现算 155 条 —— 条数会变，『全部含斜杠』这个形态不会」。

### 目标 2 —— `observed["total"] == 186` → 与活 manifest 现算条数比

三处统一改成：

```python
assert observed["total"] == len(manifest["entries"]), (...)
assert observed["total"] >= 100, f"manifest 只有 {observed['total']} 条 ⇒ 分母可疑"
```

并在原地留下 `186 → 176 → 155` 的沿革与「这是分母自证、不是业务常量」的说明。
测试签名加了已存在的 module-scope `manifest` fixture —— 等式两侧是**两次独立读**
（`observed` 走 `load_entry_manifest()`，右侧走 fixture 直读 `_MANIFEST_PATH`），
所以「观测面没覆盖整份 manifest」仍然打红，不是自证重言式。

### 目标 3 —— `d2SyncHostWiring.spec.ts` 重新指向统一路径

锚点对照（文件头已写成表格留档）：

| 旧锚点 | 当前等价物 |
|---|---|
| `useD2SyncBridge(` | `useWorkpaperSyncBridge(` |
| `flushBeforeOo` | `flushHtml`（**必须**第一步 `await formData.flushPendingSave()`） |
| `requestForceSave` | 宿主 `await syncEditorHostRef.value.forceSave()` |
| `const ooSheetRef` | `const syncEditorHostRef` |
| `ref="ooSheetRef"` | `ref="syncEditorHostRef"`（绑在 `<WorkpaperSyncEditorHost>`） |

语义一字不改（宿主必须真接 flush/reload、必须真持有实例去 forcesave），并**加厚**了三处：

- `flushHtml` 内部 `flushPendingSave()` 必须**排在** `readStoreProjection` 之前（顺序反了等于没 flush）；
- `forceSave()` 调用必须被 `syncBridge.canForcesave.value` 门控；
- `capability` 必须 `capabilityForEntry(...)` 现算，不得内联字面量（谓词 8）。

后两个 describe 从 legacy 的 `useD2SyncBridge.ts` / `GtOnlyOfficeSheet.vue`
改指 `useWorkpaperSyncBridge.ts` / `WorkpaperSyncEditorHost.vue` —— 它们才是宿主**现在**
消费的模块，原来那两个已经不在 D2 链路上（判据形式上绿、实质上守着一条没人走的路）。

---

## 变异检验（全部 RED = 判据真有牙）

### D2 宿主（`backend/scripts/_d2_host_mutation_harness.py`）

宿主原始 `sha256=10fe4041…e7b40`，24584 bytes；每轮变异后**字节级还原**，末尾复核一致。

| # | 变异 | 结果 |
|---|---|---|
| M1 | 桥调用整体改名（宿主根本不接统一桥） | **RED** 4 failed / 11 passed |
| M2 | `flushHtml` 里删掉 `flushPendingSave()`（缺陷 A 原型） | **RED** 1 failed / 14 passed |
| M3 | 模板上摘掉 `ref="syncEditorHostRef"` | **RED** 1 failed / 14 passed |
| M4 | 删掉 `await syncEditorHostRef.value.forceSave()`（缺陷 B 原型） | **RED** 1 failed / 14 passed |
| M5 | 删掉实例 ref 声明 | **RED** 1 failed / 14 passed |
| M6 | `capability` 内联字面量 | **RED** 1 failed / 14 passed |
| M7 | `reloadHtml` 不再 `loadAll()` | **RED** 1 failed / 14 passed |

`还原后 sha256=10fe4041…e7b40 一致=True`，且
`git diff --stat` / `git status --porcelain` 对该宿主**均为空** ⇒ 宿主未被改动。

> 第一轮 M2/M3/M7 曾判 SKIP —— 原因是宿主是 CRLF，而 harness 的锚点用 `\n`。
> 修成「按文件真实换行风格改写锚点」后 7/7 全部命中。**SKIP 不等于通过**，这一点记在这里。

### 后端「现算」判据（`backend/scripts/_mutate_manifest_plugin.py`）

不写真 manifest 一个字节：把 `entry_profile.ENTRY_MANIFEST_PATH` 指到 tmp 里的扰动副本
（`load_entry_manifest.cache_clear()`），即从代码视角「活输入」真的变了。

| 变异 | 期望 | 实测 |
|---|---|---|
| `drop_one`（少 1 条 entry） | 三条 `total` 判据必须红 | **RED ×3**：`扫过 154 条，活 manifest 现算 155 条 ⇒ 观测面没覆盖整份 manifest` |
| `no_deep`（删掉全部 ≥4 段 entry） | 三条 entry_id 判据必须红 | **RED ×3**，消息各自点名「该形态在真源里已不存在」 |
| `reshuffle`（4 段 entry 全部改名） | 形态还在 ⇒ 必须**照样绿**（证明没钉死字面量） | **5 passed** |
| `inflate`（条数翻倍） | `test_task69` 的相对下限必须随活 manifest 上移 | **RED** |

真 manifest 核对：`git status` 显示的 ` M` 是**本会话之前**就有的未提交改动
（文件 `LastWriteTime = 20:13:50`，本会话 22:20 之后才开始），与本轮无关。

### I 循环 slice 行号守卫（`backend/scripts/_i_slice_guard_mutation.py`）

slice 原始 `sha256=785c94ca…ce5d53`，182307 bytes；还原后一致。

| 变异 | 第一版守卫 | 加厚后 |
|---|---|---|
| MI-1 合法行号推到 `#L9999` | **GREEN（假绿）** | **RED** |
| MI-2 区间右端推到 `-4315` | **GREEN（假绿）** | **RED** |

两处假绿暴露了守卫自身的两个洞，已就地补掉：① 区间**右端**也要查；
② 裸文件名要按 basename 在前端/后端树里唯一定位（否则「定位不到 ⇒ 静默跳过」会吃掉整类腐化），
并加 `assert not skipped` 让「定位不到」本身也打红。

---

## 全量清扫表

范围：`backend/tests/workpaper_sync/**`、`backend/tests/workpaper_sync_frontend/**`、
`backend/data/workpaper_sync_*_manifest_slice.json`（12 份）、D2 前端宿主与相关 spec。

| file:line | 反模式 | 判定 | 处置 |
|---|---|---|---|
| `test_participant_leave_endpoint.py:181` | 写死退网 entry_id `xlsx/d4/analysis/d4-tab-customer-price` | **FIXED**（原为潜伏） | 改 `_deep_registered_entry_id(min_segments=4)` |
| `test_task28_sync_router.py:813` | 同上（parametrize 第 2 格） | **FIXED**（原为潜伏） | parametrize 改「形态声明」+ `_shape_entry_id` |
| `test_task31_frontend_contract.py:234` | 同上（三元组第 2 项） | **FIXED**（原为潜伏） | 改 `_shape_entry_ids()` |
| `test_task28_sync_router.py:823`（docstring） | 冻结「186 条 entry_id」 | **FIXED** | 改「当时 186，现算 155；形态才是判据」 |
| `test_task41_d2_large_json_pilot.py:1672` | `observed["total"] == 186` | **FIXED**（活故障） | `== len(manifest["entries"])` + `>= 100` 非空底 |
| `test_task42_h1_grouped_dynamic_pilot.py:2681` | 同上 | **FIXED**（活故障） | 同上 |
| `test_task43_g7_two_level_dynamic_pilot.py:2899` | 同上 | **FIXED**（活故障） | 同上 |
| `workpaper_sync_frontend/test_task69_frontend_regression.py:878` | `entry_total >= 186` 绝对下限（上游 Task 67 冻结产物仍是 186，一旦重算成 155 即红） | **FIXED**（潜伏，扫出的新点） | `>= len(live_entries) * 9 // 10`，两个方向都站得住 |
| `d2SyncHostWiring.spec.ts`（5 个锚点 × 6 条） | 锚在 `42d2f6e6f` 之前的 D2 接线名 | **FIXED**（活故障） | 整卷重新指向统一路径，7/7 变异 RED |
| `workpaper_sync_i_cycle_manifest_slice.json`：`i1CategoryScope.ts#L136` ×3 | 冻结行号指到 EOF 之后（文件 132 行） | **FIXED**（潜伏） | → `#L111`（`exploration: 'mining_right'` 真实位置） |
| 同上：`htmlRendererRegistry.ts#L1647-1694` / `#L1648-1649` / `…1656-57` / `…1664-65` / `…1672-73` / `…1680-81` / `…1688-89`（7 处） | 引用**文件与行号双错**：该文件已缩到 361 行，6 个 I 循环 componentType 的 `defineAsyncComponent` 模块边早搬到 `registry/entries/specialized.ts` | **FIXED**（潜伏，守卫扫出的新点） | 逐条核对 `componentType: '<id>'` 真在那一行后改指 `registry/entries/specialized.ts#L314-315 / 322-323 / 330-331 / 338-339 / 346-347 / 354-355`，整段 `#L314-355` |
| `test_task51_i_cycle_migration.py`（守卫缺口） | ref 判据只查**路径存在**、行号一律不查 —— 正是上面 10 处腐化能活下来的原因 | **FIXED**（新增判据） | 加 `test_every_frozen_line_number_in_the_slice_is_still_in_range`：整份 JSON 全部 `#Lxx`（含区间右端）逐个核行数，`checked >= 100` 锁分母，`skipped` 非空也打红 |
| `test_task46_d_cycle_migration.py:1165` | `assert len(d4_subs) == 31`，对**活** manifest 算 `xlsx/d4/` 前缀 —— 现算 0 条 | **OWNED-ELSEWHERE**（活故障） | 未动。该文件 9 条失败集中在 `TestManifestAlignment` / `TestProperty28DefinitionDriftFailClosed` / `TestProperty20And21ContractAndAdapter`，整块是 manifest↔slice 集群；且正确修法取决于「D4 子 tab 要不要重新入册」这个迁移裁决，不是判据写法问题 |
| `test_task61_oo94_word_pilot_gate.py:113,116`（`planned/unregistered: 186`） | 形似冻结 manifest 数 | **LATENT-LEFT（判定为非腐化）** | 它是**离线替身输入**，文件头明写「与 2026-09-01 真实库实测一致」，只承载相对不变量（arm_b/arm_c = arm_a + 1）；真库那一臂的判据已经是 `arm_a["planned"] > 0`（相对）。改它反而会伪造一次「实测」 |
| `test_task29_timeline_evidence.py:1615` | 曾是 `>= 175` | 已闭环（本轮参照的先例） | 未动，`>= len(entries) * 9 // 10` |
| `test_task29_timeline_evidence_pg.py`（d4 entry_id） | 曾写死 `xlsx/d4/analysis/d4-tab-indicator` | 已闭环 | 未动，已改为现挑 |
| `test_task46_d_cycle_migration.py:1176/1180`、`test_task29*`（`startswith("xlsx/d4/")`） | 前缀判据而非写死 id | 非腐化 | 未动 |
| `test_workbook_row_change_{insert,apply}.py`（`sites: 46` / `entries: 44`） | 形似冻结计数 | 非腐化 | 未动：D2 真实模板的逐处扫描分母，同 assert 内有独立重算对账（另一 agent 已把 42→46 校正） |
| `test_task44_oo94_excel_pilot_gate.py:149-150,1187`（`42` / `173` / `168`） | 形似冻结计数 | 非腐化 | 未动：`42*4+5=173` 是自洽乘积，与 manifest 无关 |
| `test_task57/56/55/54/53/50_*`（`consumers == 0/2/29/4` 等） | 形似冻结计数 | 非腐化 | 未动：均为「声明 vs 现扫」双侧对账，或恒 `== 0` 的不变量 |
| `test_task58_word_canonical_resolver.py:579`（`checked == 42`） | 形似冻结计数 | 非腐化 | 未动：同一循环内现扫行数的自证，非 manifest 量 |
| `test_task75_published_identity_observer.py:370,1817`、`test_task60:1954`、`test_task73:406` | `>= 100` 非空分母 | 已是相对写法 | 未动，正是本轮采用的范式 |
| `workpaper_sync_{abcs,d,e,f,g,h,j,k,l,m,n}_cycle_manifest_slice.json` | 冻结 `#Lxx` 行号 | **无腐化**（实扫 1918 个引用，越界 0） | 未动。H/L/N 的同型腐化此前已被其他 agent 修过，本轮复核确认干净 |

扫描器（用完即删）：`_slice_lineno_probe.py`（12 份 slice × 1918 个 `#L` 引用）、
`_anchor_probe.py`（HEAD vs 工作树逐锚点）。

---

## 结论

**关闭的潜伏腐化点：14 处**

- 3 处写死的退网 `xlsx/d4/**` entry_id（三个文件当时全绿 ⇒ 纯潜伏；同型腐化在
  `test_task29_timeline_evidence_pg.py` 已经真实连坐过 42 条断言）
- 1 处 `entry_total >= 186` 绝对下限（上游 Task 67 冻结产物一重算即红）
- 1 处 docstring 里的冻结「186 条」
- 3 处 `i1CategoryScope.ts#L136` 指到 EOF 之后
- 6 处 `htmlRendererRegistry.ts#L16xx`（文件与行号双错，模块边早已搬走）

**修掉的活故障：9 条断言**

- 3 条 `observed["total"] == 186`（manifest 已 155）
- 6 条 `d2SyncHostWiring.spec.ts`（锚在 D2 迁统一路径之前的名字）

**新增的防复发判据：1 条**
`test_task51_i_cycle_migration.py::test_every_frozen_line_number_in_the_slice_is_still_in_range`
—— 原来 slice 的 ref 判据只查路径不查行号，这正是上面 9 处行号腐化能活下来的原因。
新判据经两轮变异加厚（区间右端 + 裸名解析），MI-1/MI-2 由假绿转红。

**留作潜伏（附理由）：2 处**

1. `test_task46_d_cycle_migration.py:1165` `== 31` —— **OWNED-ELSEWHERE**。是活故障，
   但整块属 manifest↔slice 集群（同文件 9 红），且正解取决于迁移裁决而非判据写法。
   在别人正改的文件里动一条断言只会来回抖。
2. `test_task61_oo94_word_pilot_gate.py` 的 `186` —— 复核后**判定不是腐化**：
   离线替身的输入数据，明文声明是某次真库实测的复刻，只承载相对不变量；
   真库那一臂已经用 `> 0`。改它等于伪造实测。

**逐文件 before / after**

| 文件 | BEFORE | AFTER | 备注 |
|---|---|---|---|
| `test_participant_leave_endpoint.py` | 27 passed | 27 passed | 潜伏修复，计数不变 |
| `test_task31_frontend_contract.py` | 28 passed | 28 passed | 同上 |
| `test_task28_sync_router.py` | 101 passed | 101 passed | 同上 |
| `test_task41_d2_large_json_pilot.py` | 6 failed / 105 passed | **0 failed / 111 passed** | 我修 1（`186`），另一 agent 修掉 5 条 `TestOrderingGate` |
| `test_task42_h1_grouped_dynamic_pilot.py` | 10 failed / 134 passed | **1 failed / 143 passed** | 余 1 条 `no_resolver_debt` 本就在 BEFORE 名单里，属他人集群（收尾复跑时 `required_set_digest` 也已被另一 agent 修好） |
| `test_task43_g7_two_level_dynamic_pilot.py` | 8 failed / 197 passed | **0 failed / 205 passed** | 我修 1，其余由另一 agent 修掉 |
| `workpaper_sync_frontend/test_task69_frontend_regression.py` | 1 failed / 78 passed | 1 failed / 78 passed | 唯一失败是 `test_gate_check_passes`（冻结报告过期），属产物集群，非我引入 |
| `test_task51_i_cycle_migration.py` | 123 passed | **124 passed** | +1 为新增行号守卫；0 failed |
| `d2SyncHostWiring.spec.ts` | **6 failed / 9 passed** | **15 passed** | 与 `d2SyncDurableGate.spec.ts` 同跑 27 passed，无连带 |

**新增失败：0 条。** 三个 pilot 文件的剩余失败全部出现在 BEFORE 名单里，
未与并行 agent 互踩（每次改动后逐文件复跑对账）。

**生产代码改动：0 行。** 本轮只动判据、判据 helper 与 slice 的文档性引用。
D2 宿主经 7 轮变异后字节级还原，`git diff` / `git status` 均为空。
