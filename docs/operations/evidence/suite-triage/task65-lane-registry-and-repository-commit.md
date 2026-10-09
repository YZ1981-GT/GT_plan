# Suite Triage — Task65 Lane Registry + Repository Commit Boundary

Date: 2026-06-01
Scope: 4 failures suspected to be self-inflicted regressions from uncommitted working-tree work.

## Clusters under investigation

### C10 — `backend/tests/workpaper_sync/test_task65_opaque_authority_bundle.py` (3 failures)
- `test_registry_covers_every_source_call_site`
- `test_commit_bytes_lane_arguments_match_registry`
- `test_wrong_lane_id_argument_fails_closed`

Suspect production file: `backend/app/services/workpaper_sync/opaque_entry_gate.py` (modified in working tree)

### C11 — `backend/tests/workpaper_sync/test_task10_orm_repository_contract.py` (1 failure)
- `test_repository_never_commits`

Guards project rule: repository/service only `flush()`, router owns the single `commit()`.
Suspect production files: `published_identity_observer.py`, `d2_bidirectional_bridge.py`

## Method
1. Reproduce each file separately (`-q --tb=short -rf -p no:randomly`).
2. Establish OURS vs PRE-EXISTING via `git diff` + non-destructive `git show HEAD:<path>` comparison.
   (`git stash` / `git checkout --` / `git reset` are FORBIDDEN — tree holds large uncommitted work.)
3. Fix production code (never weaken a detector).
4. Mutation-verify each fix (break behaviour → confirm RED → restore).
5. Re-run both files + `test_task10_repository_pg.py` for cross-regression.

---

_(Findings appended below as investigation proceeds.)_

## C10 — verbatim failure (before fix)

```
$ ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task65_opaque_authority_bundle.py -q --tb=short -rf -p no:randomly
F.F....F........................                                             [100%]

test_registry_covers_every_source_call_site
  OpaqueLaneRegistryDriftError: opaque lane 登记表与源码 `opaque_entry_id(...)` 调用点不一致：
    未登记的调用点 (2): ['backend/app/services/custom_template_ingestion/namespace_migration.py:76
      [app.services.custom_template_ingestion.namespace_migration::legacy_opaque_ids_for_wp] 命中登记 0 条',
      'backend/app/services/custom_template_ingestion/namespace_migration.py:77 [...同一函数] 命中登记 0 条']
    无调用点的登记 (0): []
    实参形态漂移 (0): []

test_commit_bytes_lane_arguments_match_registry
  OpaqueLaneRegistryDriftError: backend/app/services/custom_template_ingestion/staging_cas.py:169
    `commit_bytes(...)` 缺 `lane_id=` 实参 —— 它是必填 keyword，authority model 由它单向决定

test_wrong_lane_id_argument_fails_closed
  （同上，同一个 discovery 异常在 fail-closed 守卫里先抛出，守卫因此无法到达它要证的那条）

3 failed, 29 passed in 3.74s
```

## C10 — OURS vs PRE-EXISTING: **PRE-EXISTING**（证据，非推断）

`git diff -- backend/app/services/workpaper_sync/opaque_entry_gate.py` 的全部内容是
`ENTRY_ID_NAMESPACE_SPLIT_NOTE` 里**新增一条 `measured_at: 2026-09-23` 的计数记录**（+18/-0），
detector 从不读这个 note。

决定性证据 —— 把 HEAD 版与工作树版各自 AST 解析，逐个比对 detector 真正读的节点：

```
$ git show HEAD:backend/app/services/workpaper_sync/opaque_entry_gate.py | <ast.dump 比对>
OPAQUE_AUTHORITY_LANES                            SAME
assert_lane_registry_covers_source                SAME
assert_commit_bytes_lane_arguments_match_registry  SAME
discover_opaque_entry_id_call_sites               SAME
discover_commit_bytes_lane_arguments              SAME
lane_id_argument_of                               SAME
lane_ids                                          SAME
```

判据读的每一个节点都与 HEAD **AST 全等** ⇒ 我们的未提交改动不可能是成因。

红的真实成因（两处，都已在 HEAD 里committed）：

| 调用点 | 落库提交 | 判据/登记表落库提交 |
|---|---|---|
| `custom_template_ingestion/namespace_migration.py:76,77` | `437998339` 2026-09-13 | `42d2f6e6f` 2026-09-02 |
| `custom_template_ingestion/staging_cas.py:169` | `437998339` 2026-09-13 | 同上 |

`git merge-base --is-ancestor 42d2f6e6f 437998339` ⇒ 登记表/判据**先**落库，新调用点**后**落库。
`git status --porcelain -- backend/app/services/custom_template_ingestion/` 为空 ⇒ 这两个文件工作树干净。
结论：本判据自 2026-09-13 起一直是红的，与本次未提交工作无关。

## C10 — 两处红各自的定性（production 错 vs 判据过宽）

### FP-A `namespace_migration.py:76,77` → **判据过宽**（production 正确）

`legacy_opaque_ids_for_wp` 是**只读探测**：它故意用同一个 `wp_id` 调两次
`opaque_entry_id`（一次 `wp_code=wp_code`、一次 `wp_code=None`）来**展示**分裂口径下的两个
legacy id。唯一调用方 `migration_plan_for_instance` 的 docstring 是「不执行写入」。

它**结构上不可能**登记成 lane：一条 lane 只有一个 `entry_id_source`，而这个函数同时产生
`wp_code` 与 `wp_id` 两种形态 ⇒ 登记任何一种，`实参形态漂移` 方向立刻打红。
lane 还要求 `writer_ref` 可 import+callable（`test_every_registered_writer_really_exists`）
且恰有一处 `commit_bytes(lane_id=...)`（`test_commit_bytes_lane_arguments_match_registry`
断言 `len(mapping) == len(OPAQUE_AUTHORITY_LANES)`）—— 只读探测两者都没有。
把它登记成 lane 等于**对 authority model 说谎**。

### FP-B `staging_cas.py:169` → **production 错**（名字冒用，判据不该为此让路）

`staging_cas.py:169` 的 `writer.commit_bytes(...)` 里 `writer` 是
`InMemoryAuthoritativeWriter` —— 同文件里自带 docstring「测试替身」的**测试替身**，
与权威写入器毫无关系。签名实测：

```
REAL   AuthoritativeContentWriter.commit_bytes(self, *, project_id, wp_id, entry_id, source,
         payload, document_type, expected_revision, substrate_path, lane_id, actor_id=None,
         adapter_id='opaque.authoritative.v1', parent_version_id=None, operation_id=None,
         reason='content_commit', idempotency_key=None) -> ContentCommitReceipt   # async
DOUBLE InMemoryAuthoritativeWriter.commit_bytes(self, *, expected_revision: str,
         staging_path: Path, entry_id: str, reason: str) -> str                    # sync
```

`commit_bytes` 在本平台是**被保留的、承载 authority model 的名字**：判据能做成一条不可绕过的
纯名字扫描，正是靠这条保留。生产源码里再放一个同名方法就是冒用，且它把判据逼向「加豁免」。
同一文件第 34–35 行还留着 `_FORBIDDEN_INPLACE = "write_cells" + "_to_xlsx"`
（注释：「拆开写，避免本文件被静态守卫误伤」）—— 对静态守卫的规避惯性已有先例。
`InMemoryAuthoritativeWriter` 的**生产调用方为 0**（只有 `tests/custom_template_ingestion/test_staging_cas.py`
与同文件的 `run_staging_cas`），改名零生产影响。

## C10 — 修复

### FP-B（production）`app/services/custom_template_ingestion/staging_cas.py`
`InMemoryAuthoritativeWriter.commit_bytes` → **`commit_staging_bytes`**（含调用点），
docstring 写清「`commit_bytes` 是平台保留的、承载 authority model 的名字，替身不得同名」。
生产调用方 0，改名零生产影响；判据保持为一条**不可绕过的纯名字扫描**（没有为此加任何豁免）。

### FP-A（判据）`app/services/workpaper_sync/opaque_entry_gate.py`
新增 `NonWriterEntryIdSite` + `NON_WRITER_ENTRY_ID_SITES`（当前恰 1 条）+
`assert_non_writer_sites_are_read_only()`，并在 `assert_lane_registry_covers_source`
里**先验后放行**。不是「把它从分母里删掉」—— 豁免必须**挣来**且四个方向都 fail-closed：

| 方向 | 形态 | 结果 |
|---|---|---|
| 登记指向不存在的函数 | 探测被删/改名 | RED |
| 函数里出现权威写入标记 | `commit_bytes` / `commit_restore` / `AuthoritativeContentWriter` | RED |
| 调用条数 ≠ `call_count` | 在已豁免函数里悄悄多加一处调用 | RED |
| 豁免记账不符 | 这批 sites 里豁免函数一次都没命中 | RED |

新增两条可注入的守卫：`test_non_writer_exemption_must_be_earned`（三个方向逐条 falsify）、
`test_exempt_site_still_accounted_in_coverage`（stale 豁免）。

## C10 — 变异检验（每条都 RED，且已还原）

| # | 变异 | 期望 | 实测 |
|---|---|---|---|
| M1 | `writer.commit_staging_bytes(` → `writer.commit_bytes(` | RED | ✅ RED：`staging_cas.py:178 缺 lane_id=`（2 failed）；`RESTORED: True` |
| M2 | 往豁免函数 `legacy_opaque_ids_for_wp` 里塞一句 `_writer.commit_bytes(lane_id=...)` | RED | ✅ RED：7 failed（含 `test_non_writer_exemption_must_be_earned`）；`RESTORED: True` |
| M3 | `custom_workpaper_cells` 的 `lane_id="custom_cells"` → `"wopi_put_file"` | RED | ✅ RED：`commit_bytes(lane_id=...) 实参与 lane 登记不一致`；`RESTORED: True` |

## C10 — `test_wrong_lane_id_argument_fails_closed`：**报警被卡死，不是防线被拆掉**

结论（按优先级单独交代）：**fail-closed 行为本身一直在**，M3 证明真实源码里换错 lane_id
当场打红 ⇒ 没有「错的 lane_id 被静默接受」这个洞。

但**报警确实哑了**，这一点必须直说：红的成因是守卫构造输入时调用的
`discover_commit_bytes_lane_arguments()` 先抛（被 `staging_cas.py` 那处名字冒用卡在门口），
守卫根本**到不了**它要证的那句断言 —— 看 fix 前的 verbatim：`test_wrong_lane_id_argument_fails_closed`
报的是 `staging_cas.py:169 缺 lane_id=`，而不是它自己的 `lane_id 不符`。
后果：自 2026-09-13 起，`test_commit_bytes_lane_arguments_match_registry` 与
`test_wrong_lane_id_argument_fails_closed` 双红 ⇒ 真出现 M3 那种 lane_id 调换，
**与既有的红无法区分**，等于把一条 security-shaped 判据静默降级成噪音。
一个 discovery 异常能把整条判据链全局卡死，这本身是判据的脆弱点；
现在两条都绿，且 M1/M3 证明它们会咬人。

---

## C11 — verbatim failure (before fix)

```
$ ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task10_orm_repository_contract.py -q --tb=short -rf -p no:randomly
....F..........................                                              [100%]
tests\workpaper_sync\test_task10_orm_repository_contract.py:259: in test_repository_never_commits
    assert not offenders, (
E   AssertionError: repository 出现事务边界调用（只 flush 不 commit）: line 2075: .begin_nested()
1 failed, 30 passed in 1.84s
```

## C11 — OURS vs PRE-EXISTING: **PRE-EXISTING**（且两个点名嫌疑文件都不是判据读的文件）

判据读的是 `_REPOSITORY_SRC = backend/app/services/workpaper_sync/repository.py` ——
**只有这一个文件**。点名的 `published_identity_observer.py` / `d2_bidirectional_bridge.py`
虽然工作树已改，但判据根本不读它们，不可能是成因。

```
$ git status --porcelain -- backend/app/services/workpaper_sync/repository.py
(空 ⇒ 无未提交改动)

$ git show HEAD:backend/app/services/workpaper_sync/repository.py | <逐字比对>
identical to HEAD: True
HEAD begin_nested count: 1 | work: 1
HEAD line 2075: 'async with self._session.begin_nested():'
```

时间线：判据落库 `42d2f6e6f` 2026-09-02；savepoint 落库 `da57bad76` 2026-09-14
（`git log -S begin_nested`）；`git merge-base --is-ancestor` 确认判据在前。
⇒ 该判据自 2026-09-14 起一直红，与本次未提交工作无关。

## C11 — 哪一侧错：**判据过宽**（production 正确，且必须保留 savepoint）

`repository.py:2075` 的 `begin_nested()` 在 `record_or_get_delivery` 里，
是「INSERT 撞 `delivery_key` 唯一键 → 回滚 savepoint → 按 key 读回赢家那行」的保护。

1. **它不是事务边界**：SAVEPOINT 无法让任何东西持久化，父事务的 commit/rollback 仍然只归
   router ⇒ 项目铁律要保护的「跨 service 编排原子性」一点没动。
2. **它是正确性必需**：PG 里一条语句报错（23505）会把**整个**事务置为 aborted，之后任何
   语句都是 25P02。去掉 savepoint，后面那条 re-fetch SELECT 读不出来，且 router 事务里
   此前所有写入一起废掉（本平台踩过同款：一条 UndefinedColumn 让事务 aborted、后续全 500）。
   DocServer 对 500 不重投 ⇒ 静默丢件。**删掉它才是引入真 bug。**

所以修判据，但**不弱化**：`commit` / `begin` 仍然一律打红；`begin_nested` 走
`_SAVEPOINT_ALLOWED_HOSTS`（宿主 qualname → 条数）登记 + **结构挣来**
（savepoint 必须包在 catch `IntegrityError` 的 `try` 里）+ 条数钉死（stale 方向）。

## C11 — 变异检验（每条都 RED，且已还原）

| # | 变异 | 期望 | 实测 |
|---|---|---|---|
| M4 | 在 `mark_delivery_downloading` 里加 `await self._session.commit()` | RED | ✅ RED：`line 2111: .commit()`；`RESTORED: True` |
| M5 | 在**未登记**宿主 `mark_delivery_downloading` 里加 `begin_nested()` | RED | ✅ RED：`.begin_nested() 出现在未登记的宿主 ...mark_delivery_downloading`；`RESTORED: True` |
| M6 | `except IntegrityError:` → `except ValueError:` | RED | ✅ RED：`... 没有 except IntegrityError 兜底 —— 豁免未挣来`；`RESTORED: True` |
| M7 | `record_or_get_delivery` 改名 | RED | ✅ RED：`.begin_nested() 出现在未登记的宿主 ...record_or_fetch_delivery`；`RESTORED: True` |

---

## Before / After 计数

| 文件 | before | after |
|---|---|---|
| `tests/workpaper_sync/test_task65_opaque_authority_bundle.py` | 3 failed, 29 passed | **34 passed, 0 failed**（+2 新守卫） |
| `tests/workpaper_sync/test_task10_orm_repository_contract.py` | 1 failed, 30 passed | **31 passed, 0 failed** |
| `tests/workpaper_sync/test_task10_repository_pg.py`（真库兄弟，交叉回归） | — | **28 passed, 0 failed** |
| 三文件合并一次跑 | — | **93 passed, 1 warning in 15.45s** |
| `tests/custom_template_ingestion/`（改名影响面） | — | **298 passed** |

`getDiagnostics` 四个改动文件全部 0 条。全套 `tests/workpaper_sync`（~34 分钟）按指令未跑。

## 改动文件

* `backend/app/services/custom_template_ingestion/staging_cas.py`（production：替身方法改名，去掉对保留名的冒用）
* `backend/app/services/workpaper_sync/opaque_entry_gate.py`（判据：只读豁免登记 + 挣来校验 + 记账方向）
* `backend/tests/workpaper_sync/test_task10_orm_repository_contract.py`（判据：savepoint 登记 + 挣来 + 条数钉死）
* `backend/tests/workpaper_sync/test_task65_opaque_authority_bundle.py`（新增 2 条可注入守卫）
