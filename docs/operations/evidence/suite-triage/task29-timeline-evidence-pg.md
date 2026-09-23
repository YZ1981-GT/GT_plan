# Cluster C2 — `test_task29_timeline_evidence_pg.py` 41 red / 1 root cause

- 日期：2026-09-23
- 失败文件：`backend/tests/workpaper_sync/test_task29_timeline_evidence_pg.py`（41 failed / 3 passed）
- 同族文件：`backend/tests/workpaper_sync/test_task29_timeline_evidence.py::TestDerivationOverTheRealManifest::test_every_entry_either_derives_or_reports_profile_drift`（1 failed）
- 运行环境：cwd=`d:\GT_plan\backend`，解释器 `..\.venv\Scripts\python.exe`，真库 `audit_platform` PG

## 1. 首因（verbatim）

```
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task29_timeline_evidence_pg.py -q --tb=line -rf -p no:randomly -x

D:\GT_plan\backend\tests\workpaper_sync\test_task29_timeline_evidence_pg.py:1233: AssertionError: {'collect': "EvidenceError: manifest 里没有 entry 'xlsx/d4/analysis/d4-tab-indicator' —— 未登记入口不得产出 evidence @ evidence.py:770 <- test_task29_timeline_evidence_pg.py:1176"}
FAILED tests/workpaper_sync/test_task29_timeline_evidence_pg.py::TestHarness::test_no_phase_crashed_during_collection
1 failed, 1 passed, 1 warning in 16.11s
```

该文件是 "collect once → 41 条断言读同一快照" 的 harness。collect 阶段抛 `EvidenceError`
后全部下游断言连坐；`TestHarness::test_no_phase_crashed_during_collection` 是 harness
自身的 fail-closed 守卫，它变红是**正确行为**，不是噪声。

## 2. W1 / W2 裁定：**W1 —— manifest 是对的，测试烂了**

`backend/data/workpaper_sync_entry_manifest.json` 在工作树里被改过（`M`，346+/2887-），
条数 **176 → 155**：删 21 条、加 0 条，且删掉的 21 条**全部**是 `xlsx/d4/**`：

```
xlsx/d4/analysis/{d4-tab-customer-price,d4-tab-customer-structure,d4-tab-indicator,
                  d4-tab-margin-monthly,d4-tab-product-price}
xlsx/d4/inspection/{completeness,contract,cutoff-backward,cutoff-forward,discount,
                    erp-check,export,occurrence,return}
xlsx/d4/ipo/{invoice-compare,ipo-indicator,third-party}
xlsx/d4/other/{other-contract,other-cutoff,other-margin}
xlsx/d4/related/related-price
```

五条定 W1 的证据：

1. **live 源码里这些挂载已经不存在。** 直接跑 discoverer：
   ```
   node scripts/discover-workpaper-sync-mounts.mjs --json
   → total mounts 244 / d4 mounts 0 / files matching "Indicator": []
   ```
   D4 各 tab 不再各自挂 `GtOnlyOfficeSheet`。
2. **退网源于已提交的 commit，不是工作树改动。** `audit-platform/.../workpaper/d4/` 下
   21 个 `.vue` **全部仍存在且 `git status` 干净**；退网来自已 push 的
   `cd9592ff5 feat(d4-sync): D4 全量迁移至 useD4SyncMode` + `ebc6e1b92`。
   即：源码事实早已变更，**committed manifest（176 条）才是 stale 的那一份**。
3. **overlay 的改动是有署名的复核记录，不是误删。**
   `approved_source_digest` `cc0af3f8…` → `b6291b9f…`，`review_basis` 逐条写明
   「21 个 `d4/**` tab 宿主退网…属有意迁移的既成事实」，并顺手删掉随之失效的
   `d4/**` `parent_rules`（generator 对 0 匹配规则 fail closed，不删则永久不可运行）。
4. **generator 契约测试对现盘 manifest 全绿。**
   `tests/test_workpaper_sync_manifest_contract.py` → **6 passed**。该套件现场重跑
   discoverer + overlay 生成 expected 再与盘上文件比对，并断言
   `manifest template_ast mount 集合 == discovery mount 集合`。若 manifest 是被误删的，
   这条会立刻打红。它绿 ⇒ 现盘 155 条 == 源码现算结果。
5. **没有改名。** 全量 grep manifest 无 `tab-indicator` / `tab_indicator` 残留，
   `added = 0`；D4 根 entry `xlsx/gt-d4-operating-revenue` 仍在。

结论：`xlsx/d4/analysis/d4-tab-indicator` 是**合法退网**的入口。测试把它写死成常量，
宿主拓扑一迁移就烂 ⇒ 修测试，且改成从 manifest 现算，断掉复发路径。

## 3. 修复

### 3.1 `test_task29_timeline_evidence_pg.py`（41 red → 0）

删掉写死的 `ENTRY_WITHOUT_RUN`，换成 `_pick_entry_without_run(entries_by_id)`：从真实
manifest 现算一个满足三条约束的 entry —— ①已登记；②不是本 harness 唯二写过 run 的
`ENTRY`/`OTHER_ENTRY`；③profile 能干净推出 required set。排序取首条保证确定性；
一个都找不到时抛 `_HarnessError`（仍是 fail closed，不静默跳过）。

判据本身与「是哪个 entry」无关（原注释即写明「只用来证明一个 entry 一次 run 都没有也是
unverified」），所以现算不削弱语义。实测 148 条候选可选，现算落在 `docx/workpaper-word-editor`。

顺带**加强**了消费侧断言 —— 原版看不见的一个真实漏洞：「没有 run」与「profile 漂移」两条
分支的 `result` 同为 `unverified`，写死 entry_id 的旧版一旦选中漂移 entry 会被冒名顶替
而不自知。现在补断言 `defects == []` 且 `required_scenario_ids` 非空，并断言现算结果没
撞上写过 run 的那两个 entry。

### 3.2 `test_task29_timeline_evidence.py`（同族，1 red → 0）

同一 manifest 缩容，另一种表现：绝对条数下限写死。

```
tests/workpaper_sync/test_task29_timeline_evidence.py:1607:
    assert derived >= 175, f"只有 {derived} 条能推导出 required set"
E   AssertionError: 只有 150 条能推导出 required set
E   assert 150 >= 175
```

150 derive + 5 drift = 155，**分区是完整的**，坏的只是那个钉在旧条数上的下限。该测试自己的
注释已经写明「不断言 drifted 的具体条数：那会把 manifest 当前的欠账锁成基线」，所以下限
改成**相对 manifest 现有条数**（`derived >= len(entries) * 9 // 10`）而非绝对值：大面积
漂移照样打红，却不会把「manifest 缩了」误报成「推导坏了」。类 docstring 里写死的
「跑真实 186 条 manifest」同步去掉条数（实测 186 → 176 → 155，它早就烂了）。

## 4. 第二层缺陷：无

PG 文件清掉首因后一次到底 44 passed，没有堆叠缺陷。预先核查了采集阶段另外两个写死的
entry：`xlsx/gt-d2-accounts-receivable`、`xlsx/cash-flow-verification`、以及 drift 判据用的
`docx/gt-a10-bundle` —— **三条都仍在 155 条 manifest 里**，故未受缩容影响。

## 5. 变异验证（守卫没被关掉）

把 `_pick_entry_without_run` 顶部临时插回 `return "xlsx/d4/analysis/d4-tab-indicator"`
（未登记入口），重跑：

```
41 failed, 3 passed, 1 warning in 16.18s
FAILED ...::TestHarness::test_no_phase_crashed_during_collection      ← fail-closed 守卫如期变红
```

逐字复现原始失败签名（41F/3P），证明 fail-closed 守卫与下游 40 条连坐机制都还在，
不是被放宽/skip/xfail 掩掉的。随后已恢复。

## 6. 前后计数

| 文件 | 修前 | 修后 |
|---|---|---|
| `test_task29_timeline_evidence_pg.py` | 41 failed / 3 passed | **44 passed / 0 failed** |
| `test_task29_timeline_evidence.py` | 1 failed / 129 passed | **130 passed / 0 failed** |
| 合计（两文件同跑） | — | **174 passed / 0 failed** |

`getDiagnostics` 两文件均 0。未触碰 `audit_platform` 真实项目数据（PG 用法为
scratch schema `tmp_task29_evidence_<hex>` + 结束 `DROP SCHEMA CASCADE`）。

## 7. 触类旁通 grep：写死退网 entry 的其他文件（不属本簇，交编排方路由）

全仓 grep `xlsx/d4/(analysis|inspection|ipo|other|related)/` 命中另外 3 个文件仍写死
`xlsx/d4/analysis/d4-tab-customer-price`（已退网）：

- `tests/workpaper_sync/test_participant_leave_endpoint.py:181`
- `tests/workpaper_sync/test_task28_sync_router.py:813`
- `tests/workpaper_sync/test_task31_frontend_contract.py:234`

实测 `test_task31_frontend_contract.py` 2 failed，但**首因不同**（
`:250 NameError: name 'participant' is not defined`，测试自身笔误），写死的 d4 id 在
那里只是潜在腐化风险、不是当前失败原因 ⇒ 独立一簇，未在本次改动范围内处理。

另有 3 个文件写死 `observed["total"] == 186`（`test_task41/42/43_*_pilot.py`），属同一类
「绝对条数钉死在旧 manifest」腐化模式，同样交编排方另簇处理。
