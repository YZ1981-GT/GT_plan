# Task 5.5：Task 66 删除计划 → 可收缩执行账

日期：2026-11-01　｜　AC: 1.7, 12.9

## 1. 产物

| 件 | 路径 |
|---|---|
| 生成器 | `backend/scripts/gen/generate_task66_execution_ledger.py`（`--check` / `--write`） |
| 执行账 | `backend/data/workpaper_sync_task66_execution_ledger.json` |
| 守卫 | `backend/tests/workpaper_sync/test_task66_execution_ledger.py`（13 例） |
| 变异脚本 | `tmp_workpaper_sync_impl/mutate_ledger.py`（8 组，含阴性对照） |

## 2. 为什么是新生成器而不是重跑冻结生成器

见 `phase0-spec-doc-consumer-breakage-2026-11-01.md` §6。一句话：冻结生成器把 Wave-6 任务号
（66 / 71 / 72 …）对当前 tasks.md 校验，而那些号嵌在多个**已冻结数据文件**里；全部复活等于
手抄一张 legacy→current 映射表，写下后再无从证明其正确。而 5.5 要的三件事只需把冻结计划
当**输入**对现盘现算。

冻结生成器里的五处解析层修复**保留**并被执行账复用（`_LEGACY_COMPOSABLE_NAME` /
`strip_comments` / `FRONTEND_SRC` / `OUTPUT_PATH`）—— 它们本身是真缺陷，含两处静默错。

## 3. 三态现算结果

| 计数 | 值 | 含义 |
|---|---|---|
| `plan_paths_total` | 126 | 计划里的唯一 path |
| `state_landed` | **28** | 已不在盘上 ⇒ 删除确已发生，**自动出账** |
| `state_drifted` | **28** | 还在但内容已变 ⇒ 计划裁决不再可信，须 owner 重判 |
| `state_intact` | 70 | 与计划一致 ⇒ 计划仍适用 |
| `pending_delete_paths` | 125 | |
| `pending_delete_landed` | 28 | |
| `outstanding_paths` | **97** | = 125 − 28，棘轮基线 |
| `outstanding_drifted_need_reverdict` | 27 | |
| `unplanned_legacy_paths` | **0** | 计划外无新增 |
| `live_blocking_points` | **1** | |

对照冻结计划自报的 `items_disposition_pending_delete: 207` / `pending_delete_paths_distinct: 125`
—— 那是 `plan_commit d330d7cea6bb` 时点的快照，**44% 已失效**（28 landed + 28 drifted）。
执行账的意义就在这里：计数来自现盘，不来自快照。

## 4. 释放条件现算：两条 BP 已真的释放

计划里冻结的 verdict 全部**重算**，不沿用：

| BP | 计划冻结值 | 现算 | 判定 |
|---|---|---|---|
| BP-66-1 替代面无生产宿主消费 | `replacement_surface_unreachable_from_production_host: 19` | **116** 个生产文件（非测试）import `WorkpaperSyncEditorHost`，样本含 `GtB60Bundle.vue`、`D4Tab*.vue` 等 | **已释放** |
| BP-66-2 替代面自身未入库 | `replacement_surface_untracked: 22` | `git ls-files` 现问 ⇒ untracked **0**（22/22 全入库） | **已释放** |
| BP-66-3 required scenario authority model 未定 | — | **不可在本账现算**（owner 在 Phase 6），如实标 `recomputed: false`，不假装算过 | 仍成立 |

⇒ `eligible_now_count = 0`。**不存在「已满足却没删」的欠账** —— 这是 fail closed 的结论，
不是豁免：只要还有一条 BP 现算成立，就不产生删除义务。BP-66-3 释放后守卫会立刻因
`eligible_now_paths` 非空而打红，逼迫真删 97 条。

## 5. 守卫的 13 条判据

与 5.5 三条要求的对应：

- **已满足必须真删**：`test_eligible_entries_must_not_sit_undeleted` +
  `test_live_blockers_force_zero_eligibility`（全部 BP 释放时还断言 `eligible == outstanding`，
  防止悄悄缩小分母）。
- **失效项自动移除**：`test_landed_paths_are_auto_removed_from_outstanding`
  （landed 不得进 eligible、不得带 `current_sha256`、`outstanding == pending − landed` 恒等）+
  `test_drifted_paths_are_flagged_for_reverdict`。
- **计划外立即打红**：`test_no_unplanned_legacy_object_on_disk`。
- **棘轮只减**：`test_outstanding_ratchet_only_shrinks`（基线 97 写在**守卫**里而非产物里 ——
  写产物里则重跑 `--write` 就能抬基线，棘轮成装饰）+ `test_ratchet_baseline_is_not_inflated`
  （基线不得比现算高出 5 以上，预留空间等于静默容许回弹）。

另四条守「判据本身别坏掉」：`test_ledger_reuses_frozen_generator_predicate`（legacy 正则必须
与冻结生成器**同一个对象**，并静态断言执行账没自己定义一份）·`test_ledger_output_is_idempotent`
（禁时间戳字段与 ISO 字面量 —— 幂等是 `--write` + `git diff` 式门禁不永红的前提）·
`test_ledger_check_mode_passes_and_reports_counters`（同时断言 **stdout 有预期内容**，不只看
returncode）·`test_retired_generator_is_not_wired_into_any_gate`（退役生成器不得留在 CI /
pre-commit / pre-push 里当永红项）·`test_frozen_plan_digest_matches_recorded`（这才是「冻结
产物真的没再变」的断言，取代那条跑不通的 `--check`）·`test_states_are_closed_and_every_path_has_one`。

跑测：`13 passed`，带 `-W error::pytest.PytestUnhandledThreadExceptionWarning` 复跑同样 13 passed
（确认没有被吞的子线程异常）。

### 5.1 守卫首跑抓到的真实问题

`test_ledger_check_mode_passes_and_reports_counters` 第一次就红了，红在我自己 docstring 里
写的那个坑上：`subprocess.run(..., text=True)` 按**本机 locale**（Windows gbk）解码子进程
写的 utf-8 中文 ⇒ 断言「输出里有没有这句话」永假。只设 `PYTHONIOENCODING` 不够 —— 它管
子进程**写**的那一端，管不了父进程**读**的那一端。已按根因加 `encoding="utf-8"`。

这也反过来印证了那条设计：同一不变量写两种强度的判据（看退出码 / 看输出内容）能互相咬出
假绿 —— 本例里是「断言 counters 文本」这条先过、「断言中文结论」这条打红。

## 6. 变异证明（8 组，含阴性对照）

脚本在任一变异**存活**时返回非 0；实测返回 **0**。

| 组 | 变异 | 期望 | 结果 |
|---|---|---|---|
| M0 | 阴性对照：只在生成器加一行注释 | 绿 | 绿（13 passed） |
| M1 | 棘轮基线 97 → 117（虚高 20） | 红 | 红 |
| M2 | eligibility 忽略 live blocker（无视前置放行） | 红 | 红（两条用例同时红） |
| M3 | landed 行照样带 `current_sha256`（失效项没真出账） | 红 | 红 |
| M4 | 产物加 `generated_at`（破坏幂等） | 红 | 红 |
| M5 | 执行账自己 fork 一份 legacy 正则 | 红 | 红 |
| M6 | 把退役生成器接回 `governance-checks.yml`（制造永红项） | 红 | 红 |
| M7 | 现盘放一个计划外 legacy 组合式 `useZZMutationProbeDualMode.ts` | 红 | 红 |

每组跑完逐字节恢复并校验 sha256（源文件 + 产物），结尾核对产物 sha 与原始相同 ⇒ `True`。
数据级变异（M0 / M2 / M3 / M4 / M7）都先 `--write` 重生成产物再跑用例，所以验的是真实
重算结果而不是手改的 JSON。

## 7. 冻结生成器的退役登记

- **verdict**：`retired_superseded_by_this_ledger`（写在执行账的
  `frozen_generator_verdict` 字段里，附理由与「解析层修复已保留并被复用」说明）。
- **不留永红门禁**：现查 `ci.yml` / `governance-checks.yml` / `.pre-commit-config.yaml` /
  `.git-hooks/pre-commit` / `.git-hooks/pre-push` 五处均未引用它，守卫钉死；要断言的
  「冻结产物真的没再变」由 `frozen_inputs.plan_digest` + 对应用例承担。
- **冻结输入 digest**：计划 `plan_digest`、生成器 `frozen_generator_digest` 都记在账里，
  任一变动则 `--check` 不一致、必须重生成并复核 diff。

## 8. 遗留（不在 5.5 范围）

- 27 条 `drifted` 需要 owner 逐条重判「内容变了之后还算不算 legacy」。本账只把「需要重判」
  显式记下来，不替它下结论（内容判据属各 cycle lane，Phase 4）。
- BP-66-3 的释放归 Phase 6（required scenario authority model）。它一释放，97 条就全部变成
  必须物理删除的欠账，守卫会立刻打红。
