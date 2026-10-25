# Task 14 证据：stable-field 三方 merge 与冲突 domain

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` / Wave 1 Task 14
Requirements: 6.6, 6.7, 6.8, 6.9, 7.4, 8.1, 8.5
Properties: **P24 / P25 / P26 / P27 / P32 / P35**
实测日期：2026-08-25（仓库根、`.\.venv\Scripts\python.exe`）

> ⚠️ 本任务是**接续**一次被中断的实现完成的。接手时磁盘上已有 `conflicts.py` /
> `merge.py` / 守卫三个文件，但守卫 **4 例失败**、**零 Hypothesis 属性**（`given`/`settings`
> 已 import 却从未使用）、`TestTask14ScopeBoundary` **在两处 docstring 里被引用但根本不存在**。
> 下面第 4 节逐条记录了这些缺口与处置。

---

## 1. 交付物

### 生产代码（前一轮已在磁盘，本轮**未改动一行**）

| 文件 | 行数 | 职责 |
|---|---|---|
| `backend/app/services/workpaper_sync/conflicts.py` | 993 | 字段级冲突记录（AC 8.1 九要素）、`ValueEnvelope`（absent ≠ present-but-null）、五类 `ConflictKind`、七类 `SchemaAnomalyKind`、四条互不遮蔽的裁决拒绝路径、`ConflictSet` 摘要与 dedupe、resolve fence 九步不可交换顺序（AC 8.5） |
| `backend/app/services/workpaper_sync/merge.py` | 1396 | `MISSING` 独立哨兵、按 `ValueType` 的比较键规范化、三方真值表、行生命周期（按 row identity，永不看位置）、Word 多实例归并、`ContractIndex`、结构异常收敛、`apply_resolutions`、`DEFERRED_CONSUMERS` 延后登记 |

两个模块 md5 在本轮结束时与开始时一致（变异全部还原）：

```
merge.py      3df52b04eada87a32cc8dcec79100268
conflicts.py  175747c3418a44f0621fbeb7caba8a1f
__init__.py   f956970cf1a761167ab9600aeade88e9
```

### 守卫（本轮补齐）

`backend/tests/workpaper_sync/test_task14_merge_conflicts.py` —— **177 passed**
（15 个测试类 / 109 个测试方法）

| 测试类 | 例数 | 方法 |
|---|---:|---:|
| `TestMissingSentinel` | 34 | 9 |
| `TestTypeNormalization` | 33 | 12 |
| `TestThreeWayTruthTable` | 15 | 6 |
| `TestProperty24ProtectedField` | 8 | 6 |
| `TestProperty25DifferentFieldsAutoMerge` | 4 | 4 |
| `TestProperty26SameFieldDifferentValues` | 7 | 7 |
| `TestProperty27DeleteUpdate` | 6 | 6 |
| `TestProperty32WordDuplicateInstances` | 6 | 6 |
| `TestProperty35ConflictTraceability` | 10 | 10 |
| `TestStructuralConflicts` | 10 | 10 |
| `TestConflictSetDigest` | 3 | 3 |
| `TestResolveFence` | 22 | 11 |
| **`TestProperty25And26Hypothesis`**（本轮新建） | 5 | 5 |
| **`TestTask14ScopeBoundary`**（本轮新建） | 7 | 7 |
| **`TestMergeOutcomeDerivedJudgements`**（本轮新建） | 7 | 7 |

### 变异脚本（本轮新建）

`backend/scripts/diagnose/mutate_task14_merge_conflict_guards.py` —— **81 条**，全部 be 侧，
走 `backend/scripts/_mutation_kit` 共享件（`guard_files` 分母 + 声明期校验 + 静态锚点自检 +
冻结基线 + 四态判定都由 kit 强制）。

---

## 2. 实测命令与结果

```
# 守卫
.\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task14_merge_conflicts.py -q
  → 177 passed, 1 warning in 2.67s

# 变异声明静态校验（不改文件）
... mutate_task14_merge_conflict_guards.py --list
  → [OK] --list 校验通过：81 条变异声明、1 个分母文件全部可定位
    （每条锚点在目标文件里恰好命中 1 行；每个 want 都能在守卫文件里定位）

# 变异检验（全量）
... mutate_task14_merge_conflict_guards.py --run all --out <本目录>/mutation_report.json
  → 后端基线 177 passed，失败名集合：空集
    RED 81 / GREEN 0 / WRONG-TEST 0 / ANCHOR-MISS 0 / ERROR 0
    还原核验：81/81 restored=True，全仓零 `.mutbak` 残留
    守卫文件覆盖面：1/1 个登记守卫文件被至少一条变异打红
    累计 473s

# 锚点只读自检
... mutate_task14_merge_conflict_guards.py --check-anchors
  → 锚点自检：81/81 OK，0 MISS   RC=0
    只读性核验：目标文件 md5 全部未变、无 .mutbak 残留
    （运行前后对 merge.py / conflicts.py / __init__.py 各取 md5，Compare-Object 差异数 = 0）

# 派生文件新鲜度
backend/scripts/gen/generate_workpaper_writer_inventory.py --check           → RC=0
  [SOURCE] rows=322 writers=271 resolvers=72 unadjudicated=270 bypass_unified_commit=271
  [OK] inventory digest bf99230ed52edaf64b55152d86d5e6efdb48ad1368e864a4bce891c9b5e11529
backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py --check   → RC=0
  [check] OK: row_count=79 resolver_fork_count=64 migrated=13 deferred=66 regressed=0
```

### 两份派生清册为什么**没有**漂移（本轮核对过原因，不是「碰巧没红」）

`workpaper_writer_inventory.json` 的 `source_digest` 不是对 `workpaper_sync/` 做文件哈希，
而是对**扫出来的 writer/resolver 行**（`writer_id` / `kind` / `delegates_to_content_writer` /
探测到的 facts）取摘要。`merge.py` 与 `conflicts.py` 是纯域：零 SQL update、零 commit、
零 resolver 调用 ⇒ 扫不出任何行 ⇒ 摘要不变。实测核对：

```
inventory entries = 322，其中 writer_id 含 workpaper_sync/merge|conflicts 的行 = 0
inventory 里 workpaper_sync 下已登记的文件 = {artifacts, repository}   ← 只有这两个是 writer
resolver migration matrix rows = 79，含 merge|conflicts 的行 = 0
```

这反过来是「纯域、零 commit 面」这条承诺的**第二重证据**（第一重是
`TestTask14ScopeBoundary::test_no_carrier_library_or_persistence_surface`，由变异 M76/M80 锁死）。
所以两个生成器都**不需要** `--apply`。

### 辐射面（按引用关系反查，不跑全量 `backend/tests`）

扫 `backend/tests/**/test_*.py` 共 **2255** 个文件，对本轮改动物的**符号/模块名**逐个反查：

| 反查对象 | 归属 |
|---|---|
| `workpaper_sync.merge` / `workpaper_sync.conflicts` / `merge_projections` / `evaluate_resolve_fence` | 被变异的生产模块 |
| `_mutation_kit` / `mutate_task14` / `mutation_report` | 新建变异脚本与共享件 |
| `strip_comments_and_docstrings` / `generate_workpaper_resolver_migration_matrix` | 守卫复用的剥注释器 |
| `workpaper_writer_inventory` / `resolver_migration_matrix` | 派生清册 digest 守卫 |
| `assert_direct_primary` / `fold_effective_sequence` | conflicts 复用的 Task 10 真源 |
| `canonical_json_bytes` / `canonical_digest` | merge/conflicts 复用的 Task 12 真源 |
| `WorkpaperSyncConflict` / `ck_wpsc_conflict_kind` | 守卫与 ORM/V151 双向锁死的对象 |

命中 **21** 个文件：

```
backend/tests/four_table/test_g7_column_source_facts.py
backend/tests/four_table/test_i_cycle_accounts.py
backend/tests/four_table/test_l0_book_amounts.py
backend/tests/four_table/test_legacy_encoding_balances_stay_zero.py
backend/tests/test_ai_chat_mcp_tools_data.py
backend/tests/test_deliverable_capabilities_matrix.py
backend/tests/test_mutation_kit_adoption.py
backend/tests/test_mutation_kit_capabilities.py
backend/tests/test_mutation_kit_scripts_tracked.py
backend/tests/test_mutation_span_skeleton.py
backend/tests/test_note_conversion_live_verifier.py
backend/tests/test_note_conversion_zero_regression.py
backend/tests/test_note_section_matcher.py
backend/tests/test_sampling_evaluation_fill_path.py
backend/tests/test_workpaper_writer_inventory.py
backend/tests/workpaper_sync/test_task10_orm_repository_contract.py
backend/tests/workpaper_sync/test_task12_canonical_resolver.py
backend/tests/workpaper_sync/test_task12_resolution_pg.py
backend/tests/workpaper_sync/test_task13_contract_registry.py
backend/tests/workpaper_sync/test_task14_merge_conflicts.py
backend/tests/wp_export/test_wp_file_resolver.py
```

```
.\.venv\Scripts\python.exe -m pytest <上述 21 个文件> -q
  → 2 failed, 1080 passed, 5 warnings in 89.05s
```

两条 failed **都是既存的治理守卫，不是本轮引入**（见第 6 节「已知欠账」）：

* `test_mutation_kit_adoption.py::test_new_scripts_must_use_the_shared_kit` —— 列出 14 个不用
  共享件的存量脚本，**本轮新建的 `mutate_task14_...` 不在其中**（它走 kit）。与本轮无关。
* `test_mutation_kit_scripts_tracked.py::test_every_mutation_script_is_tracked_or_exempt` ——
  列出 13 个未入库的变异脚本，其中 12 个是 Task 4/5/6/7/8/9/10/11/12/13/16 的，本轮新建的
  是第 13 个。该守卫**在本轮之前就是红的**（`git status --porcelain` 实证四个同类脚本均为 `??`）。

---

## 3. 三方真值表（**如实现**，逐行跑真实执行）

`merge_projections` 的判据从上到下短路。`b/c/i` = base / current / incoming 的
**值信封**（absent 与 present-but-null 不折叠）。

| 序 | 条件 | merged | verdict | 锁它的变异 |
|---:|---|---|---|---|
| 0 | 所属键/行被结构冲突封锁 | `c`（fail closed） | `held_by_schema_conflict` | M48（键级）/ M81（行级） |
| 1 | 所属行处于 delete-update 冲突 | `c`（整行 hold） | `held_by_row_conflict` | M31 / M32 / M33 |
| 2 | `mode = word_only` | 不进 HTML projection | `word_only` | M43 |
| 3 | **非行域**字段在 incoming 缺失 | `c` | `conflict_schema` | M44 |
| 4 | protected 且 `b`/`i` 都在且 `i ≠ b` | `c` | `conflict_protected` | M17 / M18 / M19 / M20 |
| 5 | `i == b`（OO 未改） | `c` | `kept_current` | M24 |
| 6 | `c == b`（仅 OO 改） | `i` | `took_incoming` | M23 |
| 7 | `c == i`（两侧同改） | `c` | `both_sides_agree` | M27 |
| 8 | `b` 在且 `c`/`i` **恰一侧**缺失 | `c`（**不选边**） | `conflict_delete_update` | M34 / M35 |
| 9 | 其余（三值互异） | `c`（**不选边**） | `conflict_value` | M74（注入） |

`TRUTH_TABLE` 是这张表的可执行形态（10 行参数化 + 5 个定向方法，共 15 例）：

| `b` | `c` | `i` | verdict | merged |
|---|---|---|---|---|
| 10 | 20 | 10 | `kept_current` | 20 |
| 10 | 10 | 10 | `kept_current` | 10 |
| 10 | 10 | 30 | `took_incoming` | 30 |
| 10 | 40 | 40 | `both_sides_agree` | 40 |
| 10 | 20 | 30 | `conflict_value` | 20 |
| MISSING | MISSING | 30 | `took_incoming` | 30 |
| 10 | MISSING | 10 | `kept_current` | MISSING |
| 10 | MISSING | MISSING | `conflict_schema` | MISSING |
| 10 | 10 | `None` | `took_incoming` | `None` |
| 10 | `None` | 10 | `kept_current` | `None` |

### 两处**刻意不放进真值表**的行（前一轮把它们写成真值表行，实测与实现矛盾）

**(1) `(MISSING, MISSING, MISSING)` 不是真值表的一行。**
键域是 `base ∪ current ∪ incoming`，三方全缺时没有可判定的对象 —— 既无 verdict 也不进
merged。前一轮把它写成 `kept_current` 一行，实测 `KeyError`。**不能**改实现去迎合它：
那要求遍历整份契约的键空间，而行域字段的 `{row_uuid}` 模板本就无法枚举，等于给从未出现
的行凭空造 verdict。改成显式判据
`test_key_absent_from_all_three_sides_is_outside_the_key_domain`（断言不在 verdicts、
不在 merged、conflict_count=0）。

**(2)「两侧同时删除 ⇒ 删除」只对**行域**字段成立。**
静态受管格（`header_block/total_amount`）在 incoming 侧消失 = **载体漂移**，走真值表第 3 行
`conflict_schema`（fail closed，不按位置猜测）；动态行字段同样的输入是**合法删除**，走第 7 行
`both_sides_agree`。前一轮把静态键的 `(10, MISSING, MISSING)` 写成 `both_sides_agree`，
实测得 `conflict_schema` —— 这不是实现错，而是把两条独立判据合成了一条。拆成：
真值表里那一行如实记 `conflict_schema`（M44 锁）+ 新增
`test_row_scoped_field_deleted_on_both_sides_agrees_without_conflict`（锁行域那一支）。

### MISSING 的表示形态与**非折叠**证明

| 层 | 形态 | 与 `None` 的关系 |
|---|---|---|
| 域内值 | `merge.MISSING` = `_Missing()` **独立单例**；不实现 `__bool__`（保持真值）、不实现 `__eq__`（身份相等）、`__copy__`/`__deepcopy__`/`__reduce__` 都返回自身 | `MISSING == None` 恒 `False`；对 `""`/`0`/`0.0`/`False`/`[]`/`{}`/`"MISSING"` 亦然（8 例参数化） |
| 规范化 | `normalize_value(MISSING, vt) is MISSING` 对**全部 8 个 ValueType** 恒等返回 | `None` 保持 `None`，两者互不转换 |
| 值比较 | `values_equal` 只在**两侧同为 MISSING** 时判等 | `values_equal(MISSING, None, vt) is False`（全 8 类型） |
| 信封 | `ValueEnvelope(present=False)` vs `ValueEnvelope(present=True, value=None)` | `to_jsonb()` 分别是 `{"present": false}` 与 `{"present": true, "value": null}` ⇒ **落库后仍可区分**；`present=False` 携带值直接抛 `ConflictRecordError` |
| merged | 键**缺失** vs 键存在且值为 `None` | `_put` 对 absent **不写键** |

**非折叠方向靠注入反例证明**（否定式承诺没有可短路的语句）：

| 层 | 变异 | 手法 | 判定 |
|---|---|---|---|
| 规范化 | M01 `return MISSING` → `return None` | 折叠 | RED（20 条新增失败） |
| 值比较 | M02 `return a is MISSING and b is MISSING` → `return True` | 折叠 | RED |
| 信封比较 | M04 `if left.present != right.present:` → `if False:` | 折叠 | RED |
| 落库形态 | M03 `{"present": False}` → `{"present": True, "value": None}` | 折叠 | RED |
| **merged 出口** | **M05** 给哨兵加 falsy `__bool__` · **M06** 去掉 `__reduce__` · **M75 注入** `if not envelope.present: envelope = ValueEnvelope.of(None)` | 折叠 / 身份丢失 | RED |

其中 M75 是任务点名的那一条：`test_deleted_and_cleared_produce_different_merged_results`
构造 `i=MISSING`（行/载体被删）与 `i=None`（在 OO 里清空）两次 merge，断言
`deleted.value_of(key) != cleared.value_of(key)`；M75 把两者压成同一个结果 ⇒ 打红。

### 受保护字段（`formula` / `auto_source` / mask 覆盖的 editable 格）

三类只读来源是**三条独立判据**（`ProtectionPolicy` 三个成员），OO 改动一律产出
`ConflictKind.protected` + `suggested_action=keep_current`，merged **保持 current 的值**：

| 契约字段 | mode | `ProtectionPolicy` | `FieldSource` |
|---|---|---|---|
| `equity_changes/{row_uuid}/subtotal` | `formula` | `read_only_formula` | `server_formula` |
| `equity_changes/{row_uuid}/tb_amount` | `auto_source` | `read_only_auto_source` | `auto_data_source` |
| `equity_changes/{row_uuid}/masked_note` | `editable`（列落在 `formula_mask` `K8:K200` 内） | `read_only_masked_cell` | `onlyoffice_cell` |

裁决层是**第二道门**：`resolved_value_for` 对受保护字段只接受 `keep_current`，
其余抛 `ProtectedFieldOverrideError`（M21 锁）。检测（M17/M18/M19）与裁决（M21）分开，
缺一道等于没有。

---

## 4. 接手时的四条 failed + 两个缺失能力：逐条处置

| # | 现象 | 归因 | 处置 |
|---|---|---|---|
| 1 | `TestThreeWayTruthTable::test_row[b6-c6-i6-kept_current]` → `KeyError` | **守卫错**：把「三方全缺」写成真值表行 | 移出真值表，改成显式的「不在键域」判据（见 §3 (1)） |
| 2 | `test_row[10-c8-i8-both_sides_agree]` → 实得 `conflict_schema` | **守卫错**：把静态载体漂移与动态行合法删除合成一条 | 真值表如实记 `conflict_schema`，另加行域那一支的独立判据（见 §3 (2)） |
| 3 | `test_resolution_pointing_at_a_nonexistent_conflict_is_rejected` → 抛 `UnresolvedConflictError` 而非 `UnknownConflictResolutionError` | **守卫错，且正是「同顺序遮蔽」**：`assert_all_conflicts_resolved` 先查 missing、后查 unknown，只给一条假裁决必先撞 missing ⇒ unknown 那条判据**从未被测到** | 补上真实冲突的裁决再多给一条假的；另加 `test_missing_and_unknown_resolutions_are_two_distinguishable_types` 双向断言两者不互为子类 |
| 4 | `TestResolveFence::test_invalid_duplicate_link_...[stranded]` → `AttributeError: OperationState has no attribute 'durable'` | **守卫错**：枚举成员名不存在（`OperationState` 无 `durable`） | 改用 `waiting_application`（Task 10 的 pre-correlation shell 形态）；并把 5 个反例扩成 6 个（拆出 `chain_pointer`/`chain_state` 两个面）、每个只坏一条、逐个 `match` 自己的可分辨文案 |
| 5 | **零 Hypothesis 属性** —— `given` / `settings` / `st` 已 import 却从未使用；任务点名的四条属性一条都没有 | 前一轮未完成 | 新建 `TestProperty25And26Hypothesis`（5 例），见 §5 |
| 6 | **`TestTask14ScopeBoundary` 不存在** —— `merge.py` 模块 docstring 与守卫文件 docstring 都写着「一旦 Task 15/26 接线，边界守卫打红」，但类根本没写 | 前一轮未完成；这正是**假绿第①源**（零消费方的域 + 只有 fixture 测试） | 新建 7 例边界类，见 §7 |

`OperationState` 的实际成员（实测 17 个）：`created, command_pending, accepted,
waiting_application, application_bound, duplicate, extracting, merging, conflict,
rematerializing, applying, applied, refresh_required, error, rejected, superseded,
authorization_stale`。

---

## 5. 四条 Hypothesis 属性（`max_examples=60`，全称命题而非穿了 `@given` 的定向例）

样本量取 60 而非平台 PBT 默认的 5：判据是纯函数、单例 <1ms，`max_examples=5` 对
「任意合法值下不变式仍成立」几乎等于定向测试；四条属性合计 <1s。

取值策略对每个键都是**单射**的（`text` 用排除了 CR/LF/BOM/NBSP/零宽的字母表，
`amount` 用 `Decimal(n)/100`）—— 否则属性里 `assume(a != b)` 表达的「两值不同」会因为
规范化后相等而假成立，断言随之失真。

| 属性 | 测试 | 命题 | 反证变异 |
|---|---|---|---|
| **幂等** | `test_property_merge_of_three_identical_sides_is_the_identity` | 任意 `p`（9 个受管键 × {值, MISSING}）：`merge(p,p,p).merged ≡ p`，零冲突、零 conflict verdict。含受保护键 —— `i == b` 时保护判据不触发 | M24 |
| **幂等（不动点）** | `test_property_merged_result_is_a_fixpoint` | 任意 `(b,c,i)`：把 `settled_projection(merge(b,c,i))` 喂回三侧 ⇒ 不变且零冲突。**无 `assume`** —— 首次 merge 有冲突时 merged 被 hold 在 current，二次 merge 仍必须是不动点（AC 8.10 的域内形态） | M24 |
| **未改保持** | `test_property_untouched_incoming_preserves_current_everywhere` | `incoming == base`（OO 一个字没动）⇒ merged **逐键**等于 current 且零冲突。三个方向一起锁：current 改过的保新值 / current 删掉的不被 base 复活 / current 新增的保留。另断言零 `took_incoming` | M24 |
| **不同字段自动合并** | `test_property_disjoint_field_edits_merge_without_conflict` | 6 个非受保护键被任意划分给 `current`/`incoming`/不动（3⁶ 种划分，跨静态格与两行动态行）⇒ 两侧改动**全部**进 merged，零冲突；每个真被 OO 改过的键都出现在 `auto_merged_keys` 且 verdict 为 `took_incoming`。`assume` 只用来保证两侧各至少一个**真**改动（否则退化成「两侧都没改 ⇒ 没冲突」的恒真空转） | M23 |
| **同字段不自动选边** | `test_property_same_field_three_values_never_auto_picks_a_side` | 任意三个互异值落在同一键上 ⇒ 必冲突；merged **等于 current**、**不等于 incoming**、**不等于 base**；冲突记录带全三值（未被规范化改写）+ JSON Pointer + OO 地址 + 正确行身份；不给裁决就要 merged ⇒ 抛 `UnresolvedConflictError` | **M74（注入）** / M28 |

第五条用 `st.data()` 交互抽样，保证三个值与被抽中的键**类型一致**（text 键抽字符串、
amount 键抽 Decimal）。

---

## 6. Property → 守卫映射（六条都有**行为级**判据，没有一条是「源码里有这个字符串」）

### Property 24：保护字段修改形成冲突（AC 6.6）

`TestProperty24ProtectedField`（6 方法 / 8 例）。三类保护来源参数化，逐类断言
`ConflictKind.protected` + `ProtectionPolicy` + `FieldSource` + `suggested_action` +
**merged 仍是 current 的值** + `record.incoming` 保留被篡改值（供篡改检测）。
另三个方向：OO 未改 ⇒ 服务端重算的公式值胜出且零冲突；OO 新增行 ⇒ 其公式格不误报；
OO 删行 ⇒ 其受保护格不误报；裁决层 `take_incoming` 必拒。
变异 M17（检测）/ M18（分类集合）/ M19（mask 判据）/ M20（`b.present` 前提）/
M21（裁决门）/ M22（记录自洽）—— 6 条全 RED。

### Property 25：不同字段自动三方合并（AC 6.8）

`TestProperty25DifferentFieldsAutoMerge`（4 例：跨字段、跨行、纯重排、插行后 footer 下移）
\+ Hypothesis 全称属性（见 §5）。变异 M23 / M25 / M26（注入位置敏感性）全 RED。

### Property 26：同字段异值必冲突（AC 6.8）

`TestProperty26SameFieldDifferentValues`（7 例）+ Hypothesis 全称属性。
覆盖三值完整、两侧同值则合并、缺裁决必抛、四种裁决落地（keep/take/manual/合并为删除）、
指向不存在冲突必拒、missing 与 unknown 两类可分辨、重复裁决必拒。
变异 M27 / M28 / M29 / M30 / **M74（注入 last-write-wins）** 全 RED。

### Property 27：delete/update 冲突不整表覆盖（AC 6.9）

`TestProperty27DeleteUpdate`（6 例）。两个方向（OO 删/服务端改、服务端删/OO 改）各自
断言到**行级**判定（`lifecycle is delete_update_conflict` + `held is True` +
行内未改动字段的 verdict 是 `held_by_row_conflict`），并断言另一行照常合并、
冲突只锁那一行。裁决为删除 ⇒ 整行移除；裁决为 keep_current ⇒ 整行保留。
变异 M31 / M32 / M33 / M34 / M35 / M36 全 RED。

### Property 32：Word 多实例异值冲突（AC 7.4）

`TestProperty32WordDuplicateInstances`（6 例）。值一致 ⇒ 合并为一个字段；异值 ⇒
`duplicate_word_instance` 冲突且 `word_instances` 列出**全部** XPath；`take_incoming`
歧义必拒（`InstanceSelectionRequiredError`）；全等实例不得记成 duplicate；
实例 XPath 重复必拒；`word_only` 永不进 HTML projection。
变异 M37 / M38 / M39 / M40 / M41 / M42 / M43 全 RED。

### Property 35：冲突记录双侧可追溯（AC 8.1 / 8.2）

`TestProperty35ConflictTraceability`（10 例）。混合场景（同时含 value / delete_update /
schema 三类冲突）下逐条断言 `json_pointer` 以 `/` 开头、`oo_location` 非空、
`business_label` 非空、三值都是 `ValueEnvelope`、`reason` ≥8 字。另与库/ORM 双向锁死：

* `ConflictKind` 逐字对 V151 的 `ck_wpsc_conflict_kind` CHECK（正则从迁移 SQL 解析后**集合相等**）
* `to_row()` 的键集合 **== AC 8.1 的九列**，且 ⊆ `WorkpaperSyncConflict.__table__.columns`
* `dedupe_key` 与 `uq_wpsc_field UNIQUE(operation_id, stable_field_key, row_key, oo_location)` 同构
* xlsx 静态格地址 = `Sheet!列行`，动态行 = `Sheet!列@row=<row_uuid>`（**行号不是稳定身份**）
* docx 地址 = 实例化后的 `sdt_tag`
* 四类拒绝路径 + `UnresolvedConflictError` 共 5 个异常类**两两不互为子类**（双向 `issubclass`）

变异 M54 / M55 / M56 全 RED。

---

## 7. 假绿第①源（additive 死代码）的处置：显式登记 + **可验证**的边界

merge 域**当前零生产消费方**。实测（扫 `backend/app/**/*.py`，排除本域两个模块）：

```
workpaper_sync.merge            -> []
workpaper_sync.conflicts        -> []
merge_projections               -> []
apply_resolutions               -> []
MergeOutcome                    -> []
evaluate_resolve_fence          -> []
ContentMutationService          -> 只出现在 6 个模块的注释/文案里，全仓零 `class ContentMutationService`
```

一个零消费方、只有 fixture 测试的域就是假绿第①源 —— 除非把这条边界**锁成可 falsify 的判据**。
`merge.DEFERRED_CONSUMERS` 登记三条延后，`TestTask14ScopeBoundary`（7 例）把它变成可验证：

| capability | `blocking_task` | consumer |
|---|---|---|
| `merge_projections / MergeOutcome` | **15**, 26 | `ContentMutationService.commit(...)` / OO→HTML coordinator |
| `evaluate_resolve_fence / apply_resolutions` | 27, 28 | 冲突预览/resolve API |
| `StructuralAnomaly / WordInstanceObservation` 输入形态 | 37, 59 | Excel / Word extractor |

| 边界判据 | 内容 | 反证变异 |
|---|---|---|
| `test_no_carrier_library_or_persistence_surface` | 剥注释 + **剔除延后登记表**后，两个模块不含 `openpyxl` / `python-docx` / `lxml` / `xlsxwriter` / `sqlalchemy` / `AsyncSession` / `repository` / `outbox` / `.commit(` / `session.` / `file_version` / `content_revision` / `EventBus` | M76（注入载体库）· M80（注入 `session.commit()`） |
| `test_merge_domain_has_no_production_consumer_yet` | 扫 `backend/app/**/*.py` 的 6 个**结构化** import 形态，命中即红并要求退役登记 | **M78（往 `workpaper_sync/__init__.py` 真接一次 import）** |
| `test_deferred_consumers_registration_is_complete` | 每条登记必带 capability / intended_status / blocking_task / consumer / reason；`blocking_task` 必须是逗号分隔的**任务号数字**；reason ≥40 字；capability 不重复 | M79（清空 `blocking_task`） |
| `test_blocking_task_15_is_registered_and_its_target_does_not_exist_yet` | merge 域登记恰一条、`blocking_task` 含 **15**、consumer 点名 `ContentMutationService`；且全仓**无 `class ContentMutationService` 定义** | **M77（注入类定义）** |
| `test_boundary_judgement_distinguishes_mention_from_wiring` | 反向自检：登记表文案里的名字不算副作用面、不算接线、不算类定义；真 import 与真类定义必须被抓 | —（自检项，见下方说明） |
| `test_no_engine_or_router_package_leaked_into_this_task` | `adapters/excel`、`adapters/word` 不存在；两模块无 `APIRouter` / `@router.` / `Depends(` | — |
| `test_task14_modules_declare_spec_requirements_and_properties` | 两模块 docstring 含 spec / Requirements / P24·25·26·27·32·35 | — |

> **为什么必须先剔除 `DEFERRED_CONSUMERS` 声明块再扫。**
> 该登记表逐字写着 `"ContentMutationService.commit(...)"` 与「不读 repository」，直接扫全文
> 会把「明令延后」误判成「已经接线」（Task 13 已实测过同款假红：`FORBIDDEN_SIDE_EFFECT_ATTRS`
> 把 `finalize_candidate` 写进禁用名单**字符串**）。剔除用**括号配对计数**定界 ——
> 不是固定字符窗口、也不是 `index()` 算边界，后两者会随文案长度失效。M80 就是用来锁这条：
> 在登记表**之外**注入一处真 `session.commit()`，若定界改成过宽的写法就会把它一起吞掉而变 GREEN。
>
> `test_boundary_judgement_distinguishes_mention_from_wiring` 是**纯自检**（对合成字符串断言），
> 因此没有生产侧变异能打红它 —— 这是它的性质而非缺陷：它保证的是上面四条判据的
> 「不误判 / 不漏判」两个方向都成立，而它们各自的可 falsify 性由 M76~M80 五条注入证明。

---

## 8. 否定式承诺：靠**注入**证明可 falsify

「不做某件事」没有可短路的语句，短路式变异必 GREEN（Task 12 的 M51、Task 13 的 M40~M43 已实证）。
本任务六条否定式承诺各配注入变异：

| 承诺 | 注入 | 变异 | 判定 |
|---|---|---|---|
| 同字段冲突**不自动选边**（AC 4.6 / P26） | 往 value/delete_update 冲突分支写 `_put(..., i)` | **M74** | RED |
| `MISSING` **永不折叠**成 `None`（AC 6.7 / design §Extract） | 在写 merged 的唯一出口注入 `absent → ValueEnvelope.of(None)` | **M75** | RED |
| 位置变化**不得**被当成整表覆盖（AC 6.9） | 让行序差异本身产出 `delete_update_conflict` 行决策 | **M26** | RED |
| 本任务**零**载体库依赖 | 注入 `if False: import openpyxl` | **M76** | RED |
| Task 15 的 `ContentMutationService` **还不存在** | 注入 `class ContentMutationService` | **M77** | RED |
| merge 域**当前零生产消费方** | 往生产包 `__init__.py` 注入一次真 import | **M78** | RED |

M76 刻意包在 `if False:` 里：真执行 `import openpyxl` 会变成文件级 collect ERROR，判定退化成
WRONG-TEST 而不是 RED；包起来同时也证明判据扫的是**源码结构**而不是运行时导入。

---

## 9. 首轮变异实测到的四条判据缺陷（全部按「不降标」修补）

首轮 80 条：**RED 76 / GREEN 2 / WRONG-TEST 2**。逐条归因：

| # | 变异 | 首轮判定 | 归因 | 处置 |
|---|---|---|---|---|
| 1 | **M32** `if incoming_changed` → `if False`（行生命周期分类） | **GREEN** | **守卫缺陷**。`test_current_deletes_row_incoming_updates_it` 只断言「有一条 `delete_update` 冲突 + 只锁 R1 + 另一行照常合并」。可是**被改动的那个字段**单靠真值表第 8 行就会产出字段级 `delete_update` 冲突 —— 于是行级分类被短路成 `deleted_by_current` 后三条断言仍全部成立。对照它的镜像 `test_incoming_deletes_row_current_updates_it` 就有行级断言，两条不对称 | 补 `r1.lifecycle is delete_update_conflict`、`r1.held is True`、行内**未改动**字段的 verdict 必须是 `held_by_row_conflict`。转 RED |
| 2 | **M48** `blocked_keys.update(...)` → `update(())` | **GREEN** | **守卫缺陷**。结构异常有**两条**封锁路径：`blocked_rows`（整行，靠 `blocks_row_key`）与 `blocked_keys`（单键）。唯一的守卫用的是行级路径，键级路径**零判据** | 新建 `test_key_level_anomaly_blocks_only_that_key`（静态键异常，不带 `blocks_row_key`，断言只封锁自己那个键、同表另一键照常采纳 OO 改动）；另补 **M81** 锁行级那条路径，两条封锁各有自己的 want。均转 RED |
| 3 | **M50** `if not matches:` → `if False`（`ContractIndex.resolve`） | **WRONG-TEST** | **脚本缺陷（判据归属写错）**。声明的 want 是 `test_unknown_stable_key_in_a_projection_fails_closed`，但那条测试实际由 Task 13 的 `Projection.assert_matches_contract` 在**更早**的入口拦下，与本判据不是同一道门。真正覆盖本判据的是 `test_contract_index_rejects_prefix_only_matches` 与 `test_anomaly_outside_the_contract_must_bring_its_own_traceability` | 改 want。转 RED。（顺带确认：merge 自己的 `UnknownStableKeyError` 路径是有判据的，不是漏洞） |
| 4 | **M56** `"base": self.base.to_jsonb()` → `"base": None` | **WRONG-TEST** | **守卫缺陷**。`test_digest_changes_when_any_of_the_three_values_changes` 名字说「三值中任一变化」，实际只变了 current 与 incoming，**base 一路缺失**。红的是本轮新加的 `test_digest_payload_carries_the_three_values_and_kind` | 把该测试改成三路字典（base / current / incoming 各一路）并逐路断言。转 RED |

第二轮 81 条：**RED 81 / GREEN 0 / WRONG-TEST 0 / ANCHOR-MISS 0 / ERROR 0**。

> 冻结基线随之由 **175 → 177 passed**：新增 2 例全部来自上面 #1/#2/#4 的「不降标」修补
> （补行级封锁断言、补键级封锁路径、补 base 变化路径）。改基线的来源写在脚本的调用处注释里。

### 顺带验证到的一处**已经**做对的反遮蔽设计

M39（`if len(payloads) < 2:`）与 M40（`if len(self.word_instances) < 2:`）打的是同一个
`ConflictRecord.__post_init__` 里的两条判据。短路 M40 后，单实例输入会**继续**被 M39 那条
拦下并抛同一个 `ConflictRecordError` —— 典型的同类型遮蔽。之所以仍判 RED，是因为守卫
`test_all_equal_instances_cannot_be_recorded_as_duplicate_conflict` 对两个反例分别
`match="≥2"` 与 `match="值相同"`，**断言到了各自那句话**。这正是第 10 节第 1 条教训的正例。

---

## 10. 本任务实测到的判据设计教训（已固化进守卫与脚本）

1. **同类型异常/同形状记录必须断言到「自己那句话」。** 本 spec 第三次踩到。本轮三处：
   * `assert_all_conflicts_resolved` 的 missing/unknown 是**同一函数里的先后两查**，
     只给一条假裁决永远撞不到 unknown（接手时的 failed #3）；
   * `models.assert_direct_primary` 的六条禁令共用 `DuplicateLinkError` 且被收成同一个
     `FenceReason` ⇒ 反例必须构造成「其余五条都成立、只坏一条」并 `match` 各自文案，
     否则 M67 会被别的分支遮蔽；
   * `ConflictRecord` 的「实例数 <2」与「值全等」两条（见 §9 末）。
2. **`if False:` 短路某些校验会让下游抛同类型异常 ⇒ 行为不变 = 无效变异。** 关掉「金额空串」
   判据后 `Decimal("")` 仍抛 `InvalidOperation` 并被收成同一个 `ValueNormalizationError`。
   这类位置改用**语义化 fail-open**（M09 把空串变成 `"0"`）。
3. **一条判据的「作用域」要与守卫的断言层级对齐。** M32 的 GREEN 根因是守卫断言在**字段级**
   而变异改的是**行级** —— 字段级现象恰好被另一条规则复现出来。判「行是否被 hold」必须
   断言 `RowDecision`，不能只看「有没有冲突记录」。
4. **「名单/文案里写着」≠「正在调用」（Task 13 的教训在本任务复现）。** `DEFERRED_CONSUMERS`
   的 reason 里就写着 `ContentMutationService.commit(...)` 与「不读 repository」。边界判据
   必须先**剔除登记表声明块**，且剔除用括号配对计数定界（M80 锁死定界不过宽）。
5. **多行 `if (...)` / `raise (...)` 不可整行替换**（破坏续行语法 ⇒ 文件级 collect ERROR ⇒
   判定退化）。M20 / M23 / M31 / M37 / M65 一律只改其中**一个条件行**。
6. **属性检验的取值策略必须单射。** 否则 `assume(a != b)` 表达的「两值不同」会因规范化后
   相等而假成立。`text` 字母表排除 CR/LF/BOM/NBSP/零宽，`amount` 用 `Decimal(n)/100`。
7. **`--check-anchors` 是「已归档 spec 的变异体系是否还可复现」最便宜的判据**：只读、秒级、
   跑完自校验 md5 未变且无 `.mutbak` 残留。本轮用它复核了 81 个锚点。
8. **被工具超时打断的 `--run all` 不等于进程已死。** 本轮实测：wrapper 被 `^C` 后子进程
   （PID 6588）仍在跑，先后观察到 merge.py 停在 M06 与 M16 两个不同的变异态。判「是否留下
   残留」不能只看 `.mutbak` 是否存在那一瞬 —— 要先 `Get-CimInstance Win32_Process` 确认没有
   在跑的变异进程，再核 md5。等它自己跑完是最安全的收尾（本轮如此，81/81 restored=True）。

---

## 11. 已知欠账（本任务范围外，已登记）

| 欠账 | owner | 现状 |
|---|---|---|
| merge 域**零生产消费方** | **Task 15**（`ContentMutationService.commit(...)`）+ Task 26（OO→HTML coordinator） | `DEFERRED_CONSUMERS` 显式登记 `blocking_task=15,26`；`TestTask14ScopeBoundary` 4 条判据 + M77/M78 两条注入把它锁成可 falsify 的边界。接线当天守卫必红，迫使同步退役登记 |
| resolve fence 只有纯判据，无 router / 409 映射 | Tasks 27 / 28 | `DEFERRED_CONSUMERS` 登记 `blocking_task=27,28`；本域不注册路由、不读 repository（M80 锁 commit 面） |
| 结构异常的**探测**（行 UUID 空/重复/载体缺失）与新行 identity 分配 | Tasks 37（Excel）/ 59（Word） | 本域只定义封闭词表 `SchemaAnomalyKind` 并把异常收成可追溯的 schema 冲突，不做 OOXML 解析、不生成 row UUID。登记 `blocking_task=37,59` |
| 契约**没有中文业务标签字段**（Task 13 的 `FieldSpec` 不含 label） | 契约 schema 演进（Task 13 后续 / Task 36） | `ContractIndex._label` 派生一个确定、可追溯、非空的路径式标签（`sheet / table / leaf`），并允许调用方用 `label_overrides` 覆盖。`FieldLocator` 强制 `business_label` 非空（空串直接抛），所以不会出现「冲突预览里没有名字」 |
| `MergeOutcome.is_row_scoped_map` 无判据 | — | 该属性带 `# pragma: no cover - 诊断用`，只供人工排查。其余公开判据（`requires_client_refresh` / `incoming_managed_keys` / `deleted_keys` / `of_kind` / `digest_payload`）本轮补齐了 `TestMergeOutcomeDerivedJudgements`（7 例） |
| **本任务全部产物 `git status` 为 `??` 未跟踪** | 提交方 | 见下 |
| 本 spec 尚未挂 CI job | 与 Tasks 1~13 一致（该 spec 全程未新增 workflow job） | 守卫与变异均可用单条命令复现；是否统一挂 CI 由收口任务决定 |

### 🔴 入库状态：本任务（乃至整个 spec）的产物全部未跟踪

`git status --porcelain` 实测：

```
?? .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
?? backend/app/services/workpaper_sync/__init__.py
?? backend/app/services/workpaper_sync/conflicts.py
?? backend/app/services/workpaper_sync/merge.py
?? backend/data/workpaper_resolver_migration_matrix.json
?? backend/data/workpaper_writer_inventory.json
?? backend/scripts/diagnose/mutate_task14_merge_conflict_guards.py
?? backend/tests/workpaper_sync/test_task14_merge_conflicts.py
```

**连生产代码与整个 spec 目录都不在 git 里。** 两个后果：

1. 丢工作树即全部蒸发，且干净 checkout 下无法复核任何进度数字；
2. `test_mutation_kit_scripts_tracked.py::test_every_mutation_script_is_tracked_or_exempt`
   因此**长期为红**（本轮实测列出 13 个未入库的变异脚本，Task 4/5/6/7/8/9/10/11/12/13/16
   各一个 + 本任务 1 个）。这条不是本轮引入 —— 实测四个同类脚本（Task 8/12/13/16）均为 `??`。

本轮按约定**不建 commit**，故只登记不处置。处置方式是 `git add` 上述路径（**不是**登记
`backend/data/mutation_kit_exemptions.json` 豁免 —— 豁免是给「本就不该入库」的脚本用的，
这里的正解是入库）。
