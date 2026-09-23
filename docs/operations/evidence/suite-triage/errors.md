# workpaper_sync 套件 errors 分诊

> 目标：`backend/tests/workpaper_sync/` 报告 **16 errors**（283 failures 不在本次范围）。
> 会话早期同套件只有 6 errors，故约 10 个为本会话生产代码改动引入的回归。
> 本文件采用「边查边追加」写法，随时可被截断，已写内容即为已确认结论。

## 状态

- [x] 建立 stub
- [ ] collect-only 采集
- [ ] 逐条分诊
- [ ] 修复「ours」
- [ ] 前后对比

## 采集命令

```
cwd=backend
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/ --co -q
```

## 结果

（待追加）

### 第 1 步：collect-only（2026 本会话）

```
cwd=backend
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/ --co -q
...
8611 tests collected in 24.71s
Exit Code: 0
```

**结论：0 个 collection-time error。** 16 个 error 全部是 **fixture/setup-time** 异常，
必须靠定向跑候选文件（`-rE --tb=short`）才能暴露。

### 第 2 步：候选面锁定（按改动顺序）

（待追加）

**采集策略**：`pytest tests/workpaper_sync/ --setup-only -q -rE --tb=line`
（跑 fixture、不跑用例体 ⇒ 精准暴露 setup/teardown error，且远快于 34 分钟全量）
后台进程输出落 `docs/operations/evidence/suite-triage/_setup_only.txt`。

**已排除的猜测**：
- `MaterializeOutcome(` 全仓 grep：**仅生产代码 4 处构造**（materialize_coordinator.py:1845/1954/2026/2089），
  测试侧 0 处构造 ⇒ `reuse_verdict` 必填**不是** error 簇的来源。
- 新增测试 `test_participant_leave_endpoint.py` + `test_participant_leave_pg.py`：
  `50 passed`（task 11 自测干净）。

---

## 第 3 步：16 个 error 全量采集完成（实测输出）

```
cwd=backend
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/ --setup-only -q -rE --tb=line
...
11 warnings, 16 errors in 805.26s (0:13:25)
```

16 个 error **全部是 setup-time fixture 异常**，聚成 **2 个根因 / 3 个簇**：

### 簇 A —— 6 errors · `test_task30_closure_gate.py`

```
E  task30_writer_revision_gate.WriterGateError: inventory source digest is stale:
   production source changed without regenerating backend/data/workpaper_writer_inventory.json
   (on disk '61e3cf8831a3ceb9c9015b5b0ccb9ca4d00a6d4a04e058e0cf50c48f706a38b1',
    from source 'f29e8bc8fcd80733564ddb29a94ba0e2d65cdf126a40811cabc3db1b3669c72d')
```

1. `test_recomputation_and_the_gate_agree_on_the_multi_resolver_rows`
2. `test_the_gate_still_counts_the_criterion_its_owner_verifies_zero_with`
3. `test_the_criterion_is_either_cleared_or_its_blocker_is_registered`
4. `test_the_registered_blocker_points_at_a_task_that_really_gates_publication`
5. `test_relocating_the_criterion_did_not_invert_the_wave_order`
6. `test_owner_named_rows_match_the_gate_report`

### 簇 B —— 3 errors · `test_task67_structural_pre_reconcile.py`

```
E  task67_manifest_gen.ManifestGenerationError: mount discovery failed (1):
   [FAIL] Error: audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabFundFlow.vue:
   Vue AST parse failed: Expression expected.
```

7. `TestFiveWayLock::test_source_regeneration_reports_the_real_drift`
8. `TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk`
9. `TestGeneratorIsIdempotentAndCheckIsStrict::test_report_digest_covers_everything_except_itself`

### 簇 C —— 7 errors · `test_task73_entry_profile_manifest.py`

```
E  task73_manifest_generator.ManifestGenerationError: mount discovery failed (1):
   [FAIL] Error: audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabFundFlow.vue:
   Vue AST parse failed: Expression expected.
```

10. `TestProfileParticipatesInTheManifestDigest::test_source_digest_gate_is_untouched`
11. `TestDerivationIsIndependentOfBusinessAdjudication::test_flipping_every_capability_leaves_the_profile_byte_identical`
12. `TestGeneratorFailsClosed::test_a_dropped_profile_field_is_rejected`
13. `TestGeneratorFailsClosed::test_reviewed_expectation_mismatch_is_rejected`
14. `TestGeneratorFailsClosed::test_stale_reviewed_expectation_is_rejected`
15. `TestGeneratorFailsClosed::test_missing_expected_profile_is_rejected`
16. `TestGeneratorFailsClosed::test_reachability_and_reviewed_unreachable_rule_must_agree`

簇 B + 簇 C 同一根因（同一个 Vue 文件过不了 AST parse），合计 **10 个** ——
与「会话早期 6 errors → 现在 16 errors」的增量 **精确吻合**，指向 Vue 簇为本会话新增。
待 git 核实归属。

---

## 第 4 步：根因定位

### 根因 ①（簇 B + 簇 C = 10 errors）：6 个 D4 Vue 文件被**错位拼接**成语法错误

复现（非 pytest，直接跑 manifest 生成器依赖的 node 发现器）：

```
cwd=audit-platform/frontend
node scripts/discover-workpaper-sync-mounts.mjs --json
→ [FAIL] Error: audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabFundFlow.vue:
         Vue AST parse failed: Expression expected.
  at discoverVueFile (scripts/discover-workpaper-sync-mounts.mjs:235:11)
Exit Code: 1
```

精确定位（`vue-eslint-parser` + `@typescript-eslint/parser`，与发现器同一套 parser）：

```
MSG: Expression expected.
line: 138 col: 98 index: 9465
```

`D4TabFundFlow.vue:138` 起的真实内容 —— 一个 `useD4ImportExport({...})` 调用被
**从 `computed(()` 正中间劈开**，中间硬插了注释块 + 3 个函数，尾巴掉到第 148 行：

```js
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(()

// ─── expose 给 GtWpRenderer 工具栏委托 ────────────────────────────────
function handleExportTemplate() { exportTemplate('D4-32') }
function handleExportData() { exportData('D4-32') }
async function handleImportClick() {
  ...
  input.click()
} => props.wpId), projectId: computed(() => props.projectId) })
```

健康兄弟文件（`D4TabCutoffForward.vue` / `D4TabDiscount.vue` / `D4TabCustomerDetail.vue`
/ `D4TabThirdParty.vue` 等）证明正确形态是**一行写完**：

```js
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
```

**触类旁通 grep（尾巴特征行）确认这是系统性的 6 处，不是 1 处** ——
发现器 fail-fast 只报第一个，所以 pytest 里只看到一个文件名：

```
src/components/workpaper/d4/ipo/D4TabFundFlow.vue:148
src/components/workpaper/d4/ipo/D4TabInterviewSummary.vue:159
src/components/workpaper/d4/other/D4TabOtherCheck.vue:144
src/components/workpaper/d4/other/D4TabOtherContract.vue:112
src/components/workpaper/d4/other/D4TabOtherCutoff.vue:134
src/components/workpaper/d4/other/D4TabOtherMargin.vue:167
```

**判定：ours**（前端 D4 批量插入 export/import 委托那一批改动的文本拼接事故；
6 个文件全在 `git log` 的 HEAD 提交 `8022b49ad` 里被动过）。
不属于 task 3/8/10/11 的后端改动，但属于本会话工作树，且是**真语法错误**必须修。

### 根因 ②（簇 A = 6 errors）：writer inventory 的 source digest 陈旧

`workpaper_writer_inventory.json` 的 on-disk digest 与「从生产源现算」的 digest 不一致
⇒ 生产源改了没重生成清册。**待确认是否本会话改动所致**（见下一步）。

---

## 第 5 步：根因 ② 精确归属（不是"改了行为"，是纯行号漂移）

用一次性脚本把 on-disk 清册与「从生产源现算」逐 `writer_id` 比对（`371 / 371` 行，
**0 added / 0 removed**），CHANGED 只有 3 条，且全是**位置事实**、无任何行为事实变化：

```
disk source_digest  61e3cf88...a38b1
fresh source_digest f29e8bc8...69c72d
disk rows 371 / fresh rows 371
ADDED   []
REMOVED []
CHANGED 3
  ~ app.routers.wp_formula::delete_formula -> ['facts']
      facts.swallowed_exception_lines: [882, 890] -> [895, 903]
  ~ app.routers.wp_render_strategies._d4_import_export::_handle_d4_13_import -> ['line','facts']
      line: 2992 -> 3278
      facts.swallowed_exception_lines: [3025] -> [3311]
  ~ app.services.workpaper_sync.repository::WorkpaperSyncRepository.bump_content_revision -> ['line']
      line: 268 -> 269
```

没有 writer 增删、没有 domain/kind/verdict/fact 集合变化 ⇒ 这是**生成物没跟着源重生成**，
不是需要裁定的新 writer。清册最后一次重生成在 `cd9592ff5`（= origin/main），之后本分支
10 个提交里有 3 个动过这三个源文件（`ebc6e1b92` 动 wp_formula、`30622dfa3`+`8022b49ad`
动 repository、`8022b49ad` 动 _d4_import_export），**都没重生成清册**。

**判定：ours（本分支累积债，起点 `ebc6e1b92`，非 task 3/8/10/11 引入）。**
gate 的报错文案本身就指定了修法 = 重生成清册。
**确认无冻结基线钉住这两个 digest**（全仓 grep `6a051515…` / `61e3cf88…` 只命中清册自身），
所以重生成不会把别处从绿改红。

---

## 第 6 步：修复动作（均为根因修复，未放宽任何断言、未 skip/xfail）

### 修复 ① —— 6 个 Vue 文件的错位拼接（还原为健康兄弟文件的规范形态）

每个文件两处编辑：把被劈开的 `useD4ImportExport({...})` 合回一行，并摘掉焊在
`handleImportClick` 收尾花括号上的孤儿片段 `} => props.wpId), projectId: ... })`。

| 文件 | wp |
|------|----|
| `d4/ipo/D4TabFundFlow.vue` | D4-32 |
| `d4/ipo/D4TabInterviewSummary.vue` | D4-30 |
| `d4/other/D4TabOtherCheck.vue` | D4-35 |
| `d4/other/D4TabOtherContract.vue` | D4-34 |
| `d4/other/D4TabOtherCutoff.vue` | D4-36 |
| `d4/other/D4TabOtherMargin.vue` | D4-33 |

逐文件 parser 验证（与发现器同一套 `vue-eslint-parser` + `@typescript-eslint/parser`）：

```
OK   src/components/workpaper/d4/ipo/D4TabFundFlow.vue
OK   src/components/workpaper/d4/ipo/D4TabInterviewSummary.vue
OK   src/components/workpaper/d4/other/D4TabOtherCheck.vue
OK   src/components/workpaper/d4/other/D4TabOtherContract.vue
OK   src/components/workpaper/d4/other/D4TabOtherCutoff.vue
OK   src/components/workpaper/d4/other/D4TabOtherMargin.vue
```

发现器本体（fixture 真正调用的那个）：

```
cwd=audit-platform/frontend
node scripts/discover-workpaper-sync-mounts.mjs --json
→ exit=0，产出 667686 bytes JSON（修复前 exit=1）
```

### 修复 ② —— 重生成 writer 清册

```
cwd=backend
..\.venv\Scripts\python.exe scripts\gen\generate_workpaper_writer_inventory.py --apply
→ [SOURCE] rows=371 writers=312 resolvers=84 unadjudicated=0
→ [APPLIED] backend\data\workpaper_writer_inventory.json sha256=a0d8d71a08599889
→ [OK] inventory digest 84fcce2f137f1cd25d1af1dc27e43733e8d3a049565f0bf4e190e46e2bfcab63
exit=0
```

新 digest `84fcce2f…` 与第 5 步预测值**逐字一致**（证明重生成就是纯粹的 re-sync）。
复验 `--check`：`[OK] inventory digest 84fcce2f…` exit=0，陈旧报错消失。

---

## 第 7 步：前后对比（真实命令输出）

### collect-only

| | 命令 | 结果 |
|--|------|------|
| 修复前 | `pytest tests/workpaper_sync/ --co -q` | `8611 tests collected` · 0 collection error |
| 修复后 | 同上 | `8612 tests collected` · 0 collection error |

（8611 → 8612：collect 数 +1 与本次修复无关，是并发会话在同套件加了 1 个用例；
两次都是 0 collection error，本次 16 个 error 从头到尾都是 setup-time。）

### 三个受影响文件（error 数为本次唯一 KPI）

```
cwd=backend
..\.venv\Scripts\python.exe -m pytest \
  tests/workpaper_sync/test_task30_closure_gate.py \
  tests/workpaper_sync/test_task67_structural_pre_reconcile.py \
  tests/workpaper_sync/test_task73_entry_profile_manifest.py -q --tb=no -rE
```

| | errors | 说明 |
|--|--------|------|
| 修复前 | **16** | 6 + 3 + 7，全部 setup 阶段炸，用例体从未执行 |
| 修复后 | **0** | `15 failed, 107 passed`（两次独立复跑同结果） |

**16 → 0，套件 error 清零。**

### 16 个 error 的最终去向

| 簇 | 数量 | 修复后 | 归属 |
|----|------|--------|------|
| A `test_task30_closure_gate` | 6 | **5 pass** + 1 fail | ours（清册未重生成，本分支累积债） |
| B `test_task67_structural_pre_reconcile` | 3 | **1 pass** + 2 fail | ours（Vue 拼接事故） |
| C `test_task73_entry_profile_manifest` | 7 | 7 fail | ours（Vue 拼接事故）→ 暴露出下游既存债 |

**6 个直接转绿；10 个从「setup 炸掉、永远跑不到」变成「跑到了、卡在下游既存评审门」。**

---

## 第 8 步：剩余 10 个 failure 为什么**不能**由我改绿（诚实交代）

修复 ① 让 mount 发现重新能跑之后，`build_manifest` 才第一次走到下一道门并报：

```
source mounts changed since the reviewed overlay:
approved='cc0af3f8756e8946403c68a606be0c72dd530afb8e6ebe34bd6a59d2773d74c0'
current ='b6291b9fd3f2ee78718c8edaaafef0cb792c5a0e2e2b54470cd4a2116d790034';
review the mount diff before updating approved_source_digest
```

这是**人工评审门**，不是可机械 re-sync 的生成物。git 实证它是长期债、与本次 6 文件修复无关：

```
backend/data/workpaper_sync_entry_overlay.json 最后评审于 0c9eb40d6
git rev-list --count 0c9eb40d6..HEAD                     → 111
0c9eb40d6..HEAD 中改动过的 workpaper/*.vue（去重）        → 141
```

**overlay 的 approved_source_digest 已落后 111 个提交、141 个前端组件。**
门的文案明确要求「review the mount diff before updating」——
直接把 `approved_source_digest` 改成当前值＝跳过对 141 个组件的评审，
属于放宽评审门（本次任务明令禁止）。故**保留为 failure，交由 owner 裁定**。

另：簇 A 剩下那 1 个 failure 与清册无关——
`test_relocating_the_criterion_did_not_invert_the_wave_order` 断言
`tasks.md 里找不到 `## Task Dependency Graph` 的 json 块`，
是 spec 文档缺块（tasks.md 属本次禁改文件），既存债、与本次修复无关。

---

## 结论

| 项 | 值 |
|----|-----|
| 本次 KPI：套件 error | **16 → 0** |
| 根因数 | 2（6 个 Vue 文件错位拼接 / writer 清册未重生成） |
| 改动文件 | 6 个 `.vue` + 1 个生成物 `workpaper_writer_inventory.json` |
| 放宽的断言 / 新增 skip·xfail | **0** |
| 未动 | 283 个既存 failure（他人 scope）、spec 三件套 |

一次性诊断脚本 `_writer_inv_diff.py` / `_mount_diff.py` 已按 `_` 前缀约定用完即删。

---

## 附：并发会话影响复核（收尾时 HEAD 已移动）

收尾时发现 HEAD 从 `8022b49ad` 变成 `fb7a0ace2`（并发会话提交
`feat(guidance): 补全 D4-1~36 编制说明 + 精编静态说明中性呈现`），
该提交把我修好的 6 个 `.vue` 一并带入（`git diff HEAD -- <6 files>` 为空）。
已复核修复未被回退：

```
6 文件 parser 复验            → ALL 6 OK
孤儿片段 `^} => props.wpId)` 全仓计数 → 0
node scripts/discover-workpaper-sync-mounts.mjs --json → exit=0
writer 清册 --check           → [OK] inventory digest 84fcce2f… exit=0
```

仍属本次未提交改动的只有生成物 `backend/data/workpaper_writer_inventory.json`。
