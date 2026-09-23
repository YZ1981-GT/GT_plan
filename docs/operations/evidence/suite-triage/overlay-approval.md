# Overlay approval review — `approved_source_digest` gate

Status: **APPROVED**（2026-09-23）
Scope: 回答一个问题 —— **`GtWpRenderer.vue [WorkpaperWordEditor]` 退网是否预期？**

Measured drift（来源 `governance-gates.md` §2.5 / `_t73_mountdiff.txt`）：
- approved `cc0af3f8…` → current `b6291b9f…`
- mounts 266 → 244；mountId +7 / −29 / 237 stable
- files 175 → 154；0 new、21 retired（全是 `d4/**` tab，各 1 mount，全 `GtOnlyOfficeSheet`）
- components 3 → 3（0 new、0 retired）
- 22 retired `(file, component)` 对 = 21 个 D4 tab **+ `GtWpRenderer.vue [WorkpaperWordEditor]`**
- 7 对纯 re-hash；0 对挂载数变化；0 个新增对

D4 退网归因已提交的 `cd9592ff5`（`feat(d4-sync): D4 全量迁移至 useD4SyncMode`）+ `ebc6e1b92`。

---

## 1. Word editor 判定：**预期 —— 且根本不是语义变化，是度量口径差**

结论先行：**Word 编辑能力零损失，那条挂载既没搬家也没 re-hash，连 `mountId` 都和 approved 里一模一样。**

### 1.1 它从来不是 `GtWpRenderer.vue` 里的一个真实标签

- `git log -S 'WorkpaperWordEditor' -- …/GtWpRenderer.vue` → **0 commit**（该文件从未含这个字面串）
- grep `WordEditor|word-template|OnlyOfficeWordDialog|kind === 'word'` 限定该文件 → **0 命中**

它是 discoverer 合成出来的 **registry dispatcher fact**：
`audit-platform/frontend/scripts/discover-workpaper-sync-mounts.mjs` 的 `registryWordMount()`
把「`componentType === 'word-template'` 经 HTML_RENDERER_REGISTRY 派发到 WorkpaperWordEditor」
这件事记成一条 `sourceKind: 'registry_ast'` 的挂载，host 记为 `GtWpRenderer.vue`
（锚点 = 该文件的 `<component :is="rendererEntry.component">` 动态挂载行）。

### 1.2 口径差的确切机制

`discover()` 把这条 fact 放进**独立的 `dispatchers` 数组**，不进 `mounts`：

```js
const dispatchers = [registryWordMount(repoRoot)]
```

而 mount diff 的两侧口径不对称：
- **approved 侧**数的是 manifest `entries[].mounts[]` —— dispatcher **已折入**（266）
- **current 侧**数的是 live `mounts[]` —— dispatcher **被排除**（244）

于是 dispatcher 被误计为 retired。算术闭合：`removed 29 = 21 D4 + 1 dispatcher + 7 re-hash`，`added 7 = 那 7 条 re-hash`。

### 1.3 现算实证（live discover vs on-disk manifest）

```
live sourceDigest : b6291b9fd3f2ee78718c8edaaafef0cb792c5a0e2e2b54470cd4a2116d790034
live mounts       : 244        live dispatchers : 1
live byComponent  : {'GtOnlyOfficeSheet': 238, 'OnlyOfficeWordDialog': 2, 'WorkpaperWordEditor': 4}

live dispatchers[0] : WorkpaperWordEditor
  host            = audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue
  sourceKind      = registry_ast
  mountId         = mount_d4b8a91cbb8386a448b3          ← 与 approved manifest 逐字一致
  registryEvidence= registry/entries/core.ts : L87 : word-template

approved manifest (cc0af3f8…) 的同一条 :
  ('…/GtWpRenderer.vue', 'WorkpaperWordEditor', 'registry_ast', 'mount_d4b8a91cbb8386a448b3')
```

**同一个 `mountId` 在两侧都存在** ⇒ 不是退网、不是搬家、甚至不是 re-hash。

### 1.4 能力面仍完整（不是「悄悄丢了 Word 编辑」）

- `audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue` 仍在（1300+ 行）
- registry 绑定仍在：`registry/entries/core.ts#L87` `componentType: 'word-template'` →
  `defineAsyncComponent(() => import('../../WorkpaperWordEditor.vue'))`
- 真实 template 挂载 4 条俱在：`GtA10Bundle` / `GtA12Bundle` / `GtA16Bundle` / `GtA17Bundle`
- live `byComponent.WorkpaperWordEditor = 4`，且重生成后 manifest 仍有
  `docx.editable.exclusive.dynamic.room_service_wired.v1: 1`（就是这条 dispatcher entry）
- discoverer 自带防线：`registryWordMount()` 在 word-template 条目消失时会 **throw**，
  真丢了不会静默通过 —— 这也反证本次不是真丢

**⇒ 批准 bump digest。**

---

## 2. Overlay 改动（`backend/data/workpaper_sync_entry_overlay.json`）

1. `approved_source_digest`：`cc0af3f8…` → **`b6291b9fd3f2ee78718c8edaaafef0cb792c5a0e2e2b54470cd4a2116d790034`**
2. **删除已死的 `parent_rules[0]`**（`…/workpaper/d4/**/*.vue` × `GtOnlyOfficeSheet`
   → `xlsx/gt-d4-operating-revenue`）。21 个 D4 tab 宿主退网后该 glob 再无匹配，
   而 generator 对 0 匹配规则 fail closed（`stale overlay parent_rules`），
   留着会让 `generate_workpaper_sync_manifest.py` **永久不可运行**。
   parent_rules 7 → 6；其余（h4/h8/n1/j1/WorkpaperWordEditor/b60）均仍有匹配，未动。
   D4 根 entry `xlsx/gt-d4-operating-revenue` 本身仍在。
3. `review_basis`：按文件既有约定（中文散文 + `前一版基线：…` 链式追溯）重写，
   记录上述两条归因与现算证据，并把上一版归因原文追加保留。
   `review_status` 仍为 `reviewed`（generator 强制）。

**刻意未动**：`overrides[]` 里 `GtWpRenderer.vue × WorkpaperWordEditor` 的
`registry_dispatch_reviewed` 规则 —— dispatcher fact 仍然存在且 mountId 未变，
删它才是错的（会把一条真实存在的派发面判成无主）。
`defaults_by_component.WorkpaperWordEditor` 的 `dynamic` scenario 说明同理仍准确。

## 3. Manifest 重生成

命令（生成器 docstring 记载，仓库根执行）：

```
python backend/scripts/gen/generate_workpaper_sync_manifest.py --check
python backend/scripts/gen/generate_workpaper_sync_manifest.py --apply
```

`--check` 不再报 `stale overlay parent_rules`（该根因已消除），`--apply` 成功：

```
[SOURCE]    hosts=154 mounts=244 dispatchers=1 entries=155 independent=142
            parent_duplicates=12 unadjudicated=132 unreachable=1
[APPLIED]   backend\data\workpaper_sync_entry_manifest.json          sha256=53292ce85bcace7d
[APPLIED]   …\workpaper\sync\workpaperSyncManifest.generated.ts      sha256=b12eea7d56fbf7af
[OK]        manifest digest afdffafdba8861d9522c9387394f9f9378e27b7ab78706fbc6228d812e7edc60
```

## 4. 测试前后对比

同命令（`cwd=backend`，`-p no:randomly`）：

| | before | after |
|---|---|---|
| `test_task73_entry_profile_manifest.py` | **8 failed** | **1 failed** |
| `test_task67_structural_pre_reconcile.py` | **6 failed** | **6 failed** |
| 合计 | 14 failed / 98 passed | **7 failed / 105 passed** |

task73 剩下的 1 条：`TestClosureGateConsumesProfileDrift::test_profile_drift_participates_in_the_blocking_total`
→ `ClosureGuardError: legacy characterization is stale for the current manifest`，
即 `workpaperSyncLegacyBaseline.generated.ts`（另一份产物、另一个生成器）需随之重生成 —— **本次未动**。

task67 仍 6 failed，但**构成变了**：之前其中一条是
`test_source_regeneration_reports_the_real_drift` 因生成器根本跑不起来（`stale overlay parent_rules`）而失败；
现在该条改为断言 `digests_agree is False` 失败 —— 因为 digest 已经对齐了，而 task67 报告里
记录的仍是「存在 drift」的旧普查结果。这 6 条全部同源：**task67 census 报告需 `--write` 重生成**，
而那会翻动 `rollback_isolation_gate.verdict`（`blocked` → `open`）—— 属仍待拍板的独立决策，
按约束**未触碰** `test_task66_legacy_deletion_plan.py` 与
`backend/data/workpaper_sync_task66_legacy_deletion_plan.json`。
（`test_task66_plan_is_an_untouched_input` 的失败 before/after 完全一致，是既存状态，非本次引入。）

## 5. 未做的事（约束内）

- 未弱化任何断言、未加 skip/xfail、未手改任何其他哈希
- 未 `git stash` / `git checkout --`
- 未跑全量套件
