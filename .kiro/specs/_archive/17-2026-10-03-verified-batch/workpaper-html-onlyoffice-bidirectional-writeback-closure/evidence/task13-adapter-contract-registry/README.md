# Task 13 证据：通用 adapter protocol、canonical contract/bundle schema 与 fail-closed registry

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` / Wave 1 Task 13
Requirements: 1.4, 6.1, 6.2, 6.3, 6.10, 6.14, 6.20, 9.8, 12.1
Properties: **P3 / P20 / P21 / P28**
实测日期：2026-08-25（仓库根、`.venv\Scripts\python.exe`、Node/vitest 3.2.4）

---

## 1. 交付物

### 生产代码（新建）

| 文件 | 职责 |
|---|---|
| `backend/app/services/workpaper_sync/contracts.py` | `SyncContract` 强校验器：字段级语义（stable key / JSON Pointer / cell / mode / value_type / source_ref / row identity / 动态列 / footer anchor / formula mask / delete policy / identity 载体）+ 结构漂移定位 |
| `backend/app/services/workpaper_sync/adapters/base.py` | 文档无关 adapter protocol、`SyncContext` / `Projection` / `ProjectionMutation` / `MaterializeResult` / `UnmanagedRegionReport`、副作用面守卫、substrate 准入 |
| `backend/app/services/workpaper_sync/adapters/registry.py` | 启动期 fail-closed registry（RG-1 ~ RG-19）、`RegistryReport` |
| `backend/app/services/workpaper_sync/entry_profile.py` | source-backed profile 三字段（`editability` / `room_model` / `scenario_profile`）取值域与四类交叉规则 |
| `backend/app/services/workpaper_sync/canonical_interop.py` | 跨语言 canonical 约束（XL-1 ~ XL-6）与 golden 用例构造 |
| `backend/data/workpaper_sync_contracts/` | per-entry 契约真源目录：`README.md`（schema 说明）+ `_example.candidate.json`（候选骨架，被真解析器拒绝） |
| `backend/data/workpaper_sync_canonical_golden.json` | 两侧共享的 golden fixture（13 正例 + 11 反例种类，期望字节以 hex 存放） |
| `backend/scripts/gen/generate_workpaper_sync_canonical_golden.py` | golden fixture 生成器（`--check` / `--apply`） |
| `audit-platform/frontend/src/components/workpaper/sync/canonicalJson.ts` | 与后端 `canonical_json_bytes` 逐字节等价的 TS 实现（code-point 键序、XL 反例前置拒绝） |

### 生产代码（修改 —— 给 registry 接上真消费方）

| 文件 | 改动 |
|---|---|
| `backend/scripts/check/check_workpaper_sync_closure.py` | 新增 `REGISTRY_ISSUE_KEYS` + `build_registry_facts()`；`evaluate_closure()` 增加**可选**第三参数（旧调用点两参形态不变）；`main()` 把 registry 事实传入并计入阻断总数。导入失败 **fail closed**（抛 `ClosureGuardError`），不吞成「无事实」 |

### 守卫

| 文件 | 例数 |
|---|---|
| `backend/tests/workpaper_sync/test_task13_contract_registry.py` | **237 passed** |
| `audit-platform/frontend/src/components/workpaper/sync/__tests__/canonicalJson.spec.ts` | **42 passed** |

### 变异脚本

`backend/scripts/diagnose/mutate_task13_adapter_contract_registry_guards.py`（66 条，be 64 + fe 2）

---

## 2. 实测命令与结果

```
# 后端守卫
.\.venv\Scripts\python.exe -m pytest backend/tests/workpaper_sync/test_task13_contract_registry.py -q
  → 237 passed, 1 warning in 1.56s

# 前端跨语言守卫（含 Task 1/2 的两个既有 sync spec）
npx vitest run src/components/workpaper/sync
  → Test Files 3 passed (3) / Tests 49 passed (49)
    其中 canonicalJson.spec.ts 42 passed

# 变异检验（全量）
.\.venv\Scripts\python.exe backend\scripts\diagnose\mutate_task13_adapter_contract_registry_guards.py --run all
  → RED 66 / GREEN 0 / WRONG-TEST 0 / ANCHOR-MISS 0 / ERROR 0   RC=0
    覆盖面：2/2 个登记守卫文件各至少一条变异打红
    还原核验：66/66 restored=True，全仓零 `.mutbak` 残留

# 锚点只读自检
... --check-anchors → 66/66 OK，0 MISS；目标文件 md5 全未变
... --list          → [OK] 66 条声明、2 个分母文件全部可定位

# 闭合门（registry 报告已进阻断总数）
.\.venv\Scripts\python.exe backend/scripts/check/check_workpaper_sync_closure.py
  → registry_missing_entry_profile: 142
    registry_bidirectional_without_registered_adapter: 0
    registry_fake_bidirectional: 0
    registry_stale_adapter: 0
    registry_contract_file_without_adapter: 0
    total blocking facts: 836   [BLOCKED]  RC=1（Wave 1 应为红）

# 派生文件新鲜度（本任务改动 workpaper_sync/ 必然使其失效，已重生成）
generate_workpaper_writer_inventory.py --check          → RC=0（digest bf99230e…）
generate_workpaper_resolver_migration_matrix.py --check  → RC=0（79 行 / 13 migrated / 66 deferred / 0 regressed）
```

### 辐射面（按引用关系反查，不跑全量 `backend/tests`）

扫描 `backend/tests/**/test_*.py` 共 **2254** 个文件，对本任务改动物及其复用的 Task 12
共享真源（`canonical_json_bytes` / `validate_bundle_slot` /
`build_bundle_canonical_payload` / `DefinitionBundleSnapshot` / `marker_slot_spec` /
`definition_slot_spec` / `evaluate_closure` …）逐个反查引用，命中 **4** 个；另加
`test_workpaper_writer_inventory.py`（派生文件 digest 守卫）：

```
backend/tests/test_workpaper_sync_legacy_baseline.py            check_workpaper_sync_closure / evaluate_closure
backend/tests/workpaper_sync/test_task10_orm_repository_contract.py   validate_bundle_slot
backend/tests/workpaper_sync/test_task12_canonical_resolver.py  canonical_json_bytes / bundle canonicalizer / slot spec
backend/tests/workpaper_sync/test_task13_contract_registry.py   本任务守卫
backend/tests/test_workpaper_writer_inventory.py                inventory source digest
```

```
.\.venv\Scripts\python.exe -m pytest <上述 5 个文件> -q
  → 399 passed, 5 warnings in 58.66s
```

---

## 3. 四条 Property 的判据落点

### Property 3：未注册 adapter 不得宣称双向（AC 1.4）

`WorkpaperSyncAdapterRegistry.assert_bidirectional_ready()` 的三条缺失路径抛**三种
互不继承**的异常：

| 缺什么 | 异常 | 变异 |
|---|---|---|
| adapter | `AdapterNotRegisteredError` | — （报告侧由 M43/M61 覆盖） |
| approved bundle | `BundleIntegrityError` | M47 |
| approved per-entry contract | `AuthorityModelMismatchError` | M48 |

`test_three_failure_paths_have_pairwise_distinct_types` 双向断言 `not issubclass(...)`
—— 合并类型后删任一分支都会被另一条遮蔽。伪双向另有两个方向（M52 / M53）。

**实况**：真实 manifest 186 条 entry 中 **capability=bidirectional 为 0、adapter_id 全为
`null`**，`migration_state=legacy_fake_bidirectional` 有 141 条。因此
「未注册不得宣称双向」现在覆盖全部入口，判据不锁数字、从 manifest 现算
（`test_real_manifest_has_no_bidirectional_entry_yet`）。

### Property 20：generated col 占位不可注册生产 adapter（AC 6.1）

`col_[a-z]+` 形态**无条件**拒绝（stable key 段 / column_key / table_key / sheet_key
四处），与「缺 `source_ref`」是**两条独立判据**：

* M01 关掉 col 形态 → 红；
* M02 关掉 source_ref → 红；
* `test_col_placeholder_rejected_even_with_full_source_ref` 证明「有来源也不放行」。

> 🔴 Property 20 原文是「含 col_* **且** 无 stable key/source_ref 时失败」。若按原文合成
> 一条，删掉 col 形态检查仍会被 source_ref 缺失挡住 ⇒ 变异必 GREEN。故实现取更严格的
> 无条件形态，`TestGuardSelfCheck::test_source_ref_only_parser_would_accept_col_placeholder`
> 用替身证明了这一点。

### Property 21：contract 字段完整（AC 6.2 / 6.3）

六个语义面逐个**单独抽掉**都被拒（`test_each_missing_facet_is_rejected`），且
**六条错误文案两两不同**（`test_missing_facet_messages_are_pairwise_distinct`）——
文案重合会让「到底缺哪一面」不可分辨。docx 侧另有 `sdt_tag`。
结构面（两级表头 / merge 语义 / formula mask / 动态行列 / footer anchor / 删除策略 /
row identity）由 `test_structure_facets_required_by_ac_6_3_are_all_parsed` 逐项断言。

### Property 28：immutable definition 漂移 fail closed（AC 6.10 / 9.8）

三条**互不遮蔽**的漂移路径 + bundle 侧空值反例：

| 漂移 | 判据 | 变异 |
|---|---|---|
| 契约 ↔ frozen bundle typed slot | `assert_contract_identity_frozen` / `SyncContract.assert_matches_bundle_slots` | M26 / M27 / M39 / M49 |
| 契约 ↔ 磁盘真源（stale adapter） | `assert_contract_file_current` | M50 |
| 契约声明结构 ↔ 实测结构 | `assert_no_structure_drift`（报首个 sheet/table/field/locator） | M25 |
| bundle slot omission / SQL·JSON NULL / 空串 / 全零 hash / 跨 slot marker / marker 冒充 contract | `definitions.build_bundle_canonical_payload` + `models.validate_bundle_slots`（Task 12 单一真源，本任务只加消费方判据） | Task 12 的 M15~M24；本任务 M47 / M48 |
| alias 变更不改变历史 | `DefinitionAliasRegistry.resolve_for_history` 恒抛 + registry 零 alias 入口 | M40（注入） |

---

## 4. 否定式承诺：靠**注入**证明可 falsify

「不做某件事」没有可短路的语句，短路式变异必 GREEN（Task 12 的 M51 已实证）。本任务
四条否定式承诺各配一条注入变异：

| 承诺 | 注入 | 变异 | 判定 |
|---|---|---|---|
| registry 不得按 alias 重组历史 bundle（历史只读 frozen FK+digest） | 往 `resolve_for_entry` 注入 `DefinitionAliasRegistry.resolve_for_publish(...)` | M40 | RED |
| 本任务不 finalize upgrade candidate、不发布 representation | 往 `build_production_registry` 注入一次 `finalize_candidate(...)` 调用 | M41 | RED |
| 本 Wave 不引入 Excel/Word engine | 往 `adapters/base.py` 注入 `import openpyxl` | M42 | RED |
| registry 报告必须有真消费方（非 additive 死代码） | 断掉 closure gate 的 `build_registry_facts(manifest)` 传参 | M43 | RED |

---

## 5. 假绿第①源（additive 死代码）的处置

| 新增能力 | 消费方 / 登记 |
|---|---|
| `contracts.py` | `adapters/base.py`（`SyncContext.contract`）、`adapters/registry.py`（RG-4/8/9/10/11） |
| `canonical_interop.assert_cross_language_safe` | `contracts.parse_contract`（M29 断掉即红）+ golden 生成器 + TS 侧 spec |
| `entry_profile.py` | `adapters/registry.register()`（RG-14 ~ RG-17） |
| `adapters/registry.py` → **`RegistryReport`** | **`check_workpaper_sync_closure.py`**（阻断门，AC 1.4/1.8）；M43/M61/M62 三条变异分别锁「传参」「进 issue map」「新事实必须登记」 |
| `adapters/base.py` 的 protocol 类型（`SyncContext` / `Projection` / `ProjectionMutation` / `MaterializeResult` / `UnmanagedRegionReport`） | **显式登记的延后**：engine 由 Tasks 36~38（Excel）/ 59~61（Word）实现，per-entry 注册由 Tasks 40~57 / 62~64 承接。`TestTask13ScopeBoundary` 把这条延后变成**可验证**的边界（无载体库 import、无 engine 子包、无 representation finalize 调用），一旦有人提前接线，边界守卫立即打红并要求同步更新 |

`build_production_registry()` 当前刻意返回**零注册**（`test_production_registry_starts_empty`），
`available_contract_ids()` 当前为空清册（`test_contract_directory_holds_no_production_contract_yet`）
—— 二者都是**可见欠账**而非豁免：放进生产契约却不注册 adapter 时
`RegistryReport.contract_files_without_adapter` 立刻报出并计入阻断总数。

---

## 6. 本任务实测到的判据设计教训（已固化）

1. **「名单里写着」≠「正在调用」**：`base.py` 的 `FORBIDDEN_SIDE_EFFECT_ATTRS` 恰恰把
   `finalize_candidate` / `set_entry_pointer` 写成禁用名单**字符串**。按词出现判会把
   「明令禁止」误判成「正在调用」（首轮实测假红）。判据改成 `name` 后跟 `(`，并加
   `test_scope_judgement_distinguishes_denylist_from_call` 双向自检。
2. **TS 源码必须先剥注释**：`canonicalJson.ts` 的模块注释里正解释「不能用
   `Array.prototype.sort()`」，直接扫全文必假红。剥注释器手写字符级扫描（正则会把
   `"http://x"` 里的 `//` 当注释），并自带三向自检（注释确被剥、代码未被误剥、
   字符串里的 `//` 不被当注释）。
3. **禁用正则截函数体**：`(?:(?:\s{4}.*)?\n)+?` 这类「可选组套在重复里」的写法灾难性
   回溯，实测让整个 pytest 挂到 5 分钟超时。改行级 + 缩进判定（`_func_body`）。
4. **同类型异常会互相遮蔽 —— 反例必须断言到「自己的那句话」**：首轮变异实测三条 GREEN
   全是这个成因：
   * M04（RFC 6901 `~` 转义）被「行域字段缺 `{row_uuid}`」遮蔽（两句都含「JSON Pointer」）
     → 反例改挂**非行域**字段，并断言各自专属文案；
   * M21 / M22（probe **blocklist**）被兜底 **allowlist** 分支遮蔽（同异常类型、都带载体名）
     → 断言 `blocklist` 字样。
   三条修好后全部转 RED。
5. **float 与「域外整数」是两条不同判据**：`header_rows=2.0` 被更早的跨语言门（XL-6 禁
   float）拦下，异常类型也不同（`CrossLanguageCanonicalError` 而非 `ContractSchemaError`）。
   合并断言会让其中一条永不被测到，故拆成两条测试并各自说明顺序语义。
6. **多行 `raise` 不可被整行替换**（会破坏续行语法 ⇒ 文件级 collect ERROR ⇒ 判定退化）。
   M17 / M45 / M55 首轮都写成了替换 `raise ...(` 行，改为变异其 `if` 条件或做语义化
   fail-open 替换。

---

## 7. 已知欠账（本任务范围外，已登记）

| 欠账 | owner | 现状 |
|---|---|---|
| manifest 缺 `editability` / `room_model` / `scenario_profile` 三个 source-backed 字段（142 条独立可达 entry 全缺） | **Task 1**（AC 1.2），最终 reconcile **Task 67** | `EntryProfileMissingError` + `RegistryReport.missing_profile=142` 已进闭合门阻断总数；不变式「要么有完整合法 profile，要么不可能注册 adapter」在补齐前后都成立，故守卫不锁 142 这个数字 |
| room `doc_key` 仍含文件 mtime（`wp_onlyoffice_router._generate_doc_key()` = `hash(wp_code + st_mtime_ns)`） | **Task 21** | `RoomFacts.doc_key_includes_mtime=True` 时 registry 直接拒绝注册（M60 锁死） |
| 逐 entry contract 与 adapter 注册 | Tasks 36 / 40~57 / 62~64 | 契约目录空清册；registry 零注册 |
| Excel / Word engine | Tasks 36~38 / 59~61 | `TestTask13ScopeBoundary` 锁边界 |
| 本 spec 尚未挂 CI job | 与 Tasks 1~12 一致（该 spec 全程未新增 workflow job） | 守卫可用单条命令复现；是否统一挂 CI 由收口任务决定 |
