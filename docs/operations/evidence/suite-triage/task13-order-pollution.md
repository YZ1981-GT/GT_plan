# Task13 契约注册表测试 — 测试顺序污染排查

状态：**已结案** —— 结论：**不存在 task13 的测试顺序污染**，「45 failures」是归属错误。
详见文末「结论」。（本文件按排查进展逐段追加，保留完整证据链，不回填改写。）

## 问题陈述

- `backend/tests/workpaper_sync/test_task13_contract_registry.py`
  - 单独运行：237 passed / 0 failed（本会话早前测得）
  - 作为 `tests/workpaper_sync/` 全量套件一部分运行：45 failures（**本次排查证明此归属有误**）
- 目标：定位泄漏的全局可变状态，**根因修复**（不得靠 `-p no:randomly` / 重排文件 / xfail 掩盖）

## 排查日志

（追加区）

### 1. 单独运行基线（已自行复现）

```
cwd: backend
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task13_contract_registry.py -p no:randomly -q --no-header
→ 237 passed, 1 warning in 9.91s
```

### 2. 第一轮定向组合（契约/manifest/registry 相关文件在前）—— 未复现

```
pytest test_task36_excel_entry_gate.py test_task58_word_canonical_resolver.py \
       test_task73_entry_profile_manifest.py test_task74_domain_adjudication.py \
       test_task75_published_identity_observer.py test_task13_contract_registry.py -p no:randomly
→ 2 failed, 543 passed, 7 errors in 113.43s
```
task13 的 237 条**全部通过**；2 failed + 7 errors 全在 task58/task73（属另一 subagent 的
「16 个 collection/fixture errors」范围）。

### 3. import 期污染假设 —— 已排除

一次性脚本 `backend/_t13_probe.py`：先 `importlib.import_module` 全部 198 个 sibling
测试模块，再在**同进程**内 `pytest.main` 跑 task13。

```
[probe] imported=198 failed=4
237 passed, 4 warnings in 2.04s
[probe] pytest exit=0
```

结论：**污染不是 import 期的模块级副作用**，必须是某个测试**执行期**留下的状态。

附带发现（非本次根因，但是真实脆弱点）：4 个测试模块用**裸顶层名**互相 import
（`import test_task37_excel_extract` / `test_excel_row_insertion_wiring`），依赖 pytest
把测试目录插进 `sys.path`（rootdir/conftest 机制）。脱离 pytest 就 ModuleNotFoundError。

### 4. 🔴 关键事实：仓库**没有装** `pytest-randomly`

```
plugins: anyio-4.13.0, hypothesis-6.152.4, locust-2.44.1, asyncio-1.3.0,
         base-url-2.1.0, playwright-0.8.0, subtests-0.14.2, schemathesis-3.39.16
```

- 早前多条命令显式传的 `-p no:randomly` 是**空操作**（该插件不存在）。
- 推论：全量套件的执行顺序是**确定的**（目录内文件名字典序）。因此 task13
  （排序索引 92 / 共 203 个测试文件）的污染源**只可能来自索引 0~91 的前序文件**，
  bisect 结论可复现。

### 5. 尾部 20 个前序文件（索引 72~91）—— 未复现

```
$sub = $all[72..92]   # test_projection_structure_hash_semantics … test_task13
pytest @sub -q --no-header --tb=no
→ 6 failed, 766 passed, 1 xfailed in 438.69s (7:18)
FAILED test_projection_structure_hash_semantics.py::TestBp30IsActuallyWired::test_projection_commit_calls_the_new_hash
FAILED test_single_pass_parse_reuse.py::test_cpu_segment_parses_the_artifact_bytes_once_per_view
FAILED test_single_pass_parse_reuse.py::test_segment_load_workbook_total_drops_by_the_shared_parses
FAILED test_task10_orm_repository_contract.py::test_repository_never_commits
FAILED test_task12_canonical_resolver.py::TestResolverMigrationMatrix::test_matrix_is_fresh
FAILED test_task12_canonical_resolver.py::TestResolverMigrationMatrix::test_denominator_matches_inventory
```
task13 的 237 条**全部通过**，0 failed。失败项全部属于其它文件（其中 task12 的 2 条在
只跑 4 文件的小组合里也失败 ⇒ 与顺序无关，是既存失败）。

剩余候选：索引 0~71（72 个文件）。

### 6. 前序文件三段 bisect —— 全部未复现

| 段 | 文件索引 | 命令耗时 | task13 结果 | 其它文件失败 |
|----|---------|---------|------------|------------|
| C（紧邻前序 20 个） | 72~91 | 7:18 | **237 全绿** | 6 failed |
| B | 36~71 | 2:53 | **237 全绿** | 12 failed |
| A | 0~35 | 1:11 | **237 全绿** | 11 failed |

三段前序耗时合计 ≈ 11 分钟（全量套件 34 分钟里，剩余 23 分钟属 task14~task77 等
**后序**文件，对 task13 不可能有影响 —— 顺序确定且 task13 先执行）。

下一步：把 0~91 全部前序**一次性**同进程跑完 + task13，排查「跨段组合才触发」的可能。

### 7. 真实全量运行的执行顺序已核对（不是推测）

从本会话早前留下的 `_setup_only.txt`（UTF-16，7.6MB，`--setup-only` 全量输出）还原文件顺序：

```
files in order: 202
task13 order index: 92
PREV 6: test_task10_orm_repository_contract / test_task10_repository_pg /
        test_task11_artifact_repository / test_task11_retention_orphan_pg /
        test_task12_canonical_resolver / test_task12_resolution_pg
NEXT 3: test_task14_merge_conflicts / test_task15_content_mutation /
        test_task15_content_mutation_pg
```
与我 bisect 用的顺序**逐项一致** ⇒ 复现条件忠实。

### 8. collection 期 import 污染 —— 忠实复现后仍排除

第一版 probe 有缺陷：`tests/workpaper_sync/` **没有 `__init__.py`**，pytest
（importmode=prepend）把该目录插进 `sys.path`，测试模块以**裸顶层名** import
（`test_task37_excel_extract` 等 11 个文件正靠这个互相 import）。第一版按
`tests.workpaper_sync.X` 导入拿到的是**另一批模块对象**，模块级状态没共享。

修正后（裸名导入全部 202 个模块，再同进程跑 task13）：

```
[probe] imported=202 failed=0
237 passed, 4 warnings in 2.42s
[probe] pytest exit=0
```

这一步很关键：**pytest 先 collect（import 全部模块）再 run**，所以后序文件的 import
期副作用同样能污染 task13 —— bisect（只跑前序）覆盖不到这一面。现已确定性排除。

顺带实证：202 个模块 import **全部成功**，所以另一 subagent 在查的「16 个
collection/fixture errors」**不是 import 错误**（是 fixture/setup 期错误）。

### 9. 已排除的具体「共享可变状态」候选（逐项实证，非猜测）

| 候选 | 判断 | 依据 |
|------|------|------|
| `contracts.CONTRACTS_DIR` 被别的文件改掉不还原 | 排除 | 全仓只有 task13 与 `test_task36_excel_entry_gate.py` 改它，两处都走 `monkeypatch.setattr`（自动还原）；`test_task36` 已在第 2 轮组合里跑在 task13 前面，task13 全绿 |
| `contracts.load_excel_carrier_gate` / `load_word_carrier_gate` 的 `lru_cache(maxsize=None)` 被投毒 | 排除 | `grep` 全 `backend/tests/**`：**没有任何测试** monkeypatch `EXCEL_CARRIER_CONTRACT_PATH` / `WORD_CARRIER_CONTRACT_PATH`；唯一「改 gate」的 `test_task77` 用 `dataclasses.replace`（造新对象，不改缓存里的那个） |
| `entry_profile.load_entry_manifest()` 的 `lru_cache` 返回的 **dict 被就地改** | 排除 | 三段 bisect 都包含会读/复制该 manifest 的文件，task13 仍全绿 |
| `word_resolution._load_carriers` lru_cache | 排除 | 唯一改它的 `test_task58` 在 `try/finally` 里两头 `cache_clear()`，且已实测跑在 task13 前面无影响 |
| `contracts.load_contract` 有缓存 | 排除 | 读源码：**无** `lru_cache`，每次现读磁盘 |
| import 期模块级副作用（任意文件，含后序文件） | 排除 | 见 §8，202 个模块全部按裸名 import 后 task13 仍 237 passed |
| `pytest-randomly` 洗顺序 | 排除 | 该插件**未安装**（§4） |

### 10. task13 对「磁盘内容」的真实依赖面（与并发编辑的耦合）

task13 有相当多判据是**现读磁盘**并比字节/扫源码的，不是纯内存逻辑：

- `XL.load_golden_document()` → golden fixture JSON 逐字节比对
- `_TS_CANONICALIZER` = `audit-platform/frontend/src/components/workpaper/sync/canonicalJson.ts`（前端源码）
- `_CLOSURE_PY` = `backend/scripts/check/check_workpaper_sync_closure.py`（`_func_body` 扫函数体）
- `_REGISTRY_PY` / `_INTEROP_PY` / `_PROFILE_PY`（生产模块源码扫描）
- `C.CONTRACTS_DIR / README.md`、`_example.candidate.json`
- `TestTask13ScopeBoundary` 扫 `backend/app/**`

按类计数：`TestCrossLanguageCanonicalizer`(26) + `TestRegistryReportHasAProductionConsumer`(8)
+ `TestTask13ScopeBoundary`(7) + `TestGuardSelfCheck`(5) = **46**，与报告的「45 failures」
数量级/量值高度接近。这类判据的失败原因是**磁盘内容在运行期间变了**，不是「前面某个
测试留了脏内存」——它在 34 分钟的长跑窗口里天然暴露于并发编辑（当前工作树有 11 个
任务的未提交改动、多个 subagent 并发在改前端/后端源码）。

### 11. 决定性实验：91 个前序文件 + task13 同进程一次跑完

```
cwd: backend
..\.venv\Scripts\python.exe -m pytest @(Get-Content _t13_files.txt) -q --no-header --tb=no
# _t13_files.txt = 索引 0~92 的 93 个文件（= task13 + 它在真实全量顺序里的全部前序）

→ 29 failed, 2059 passed, 1 skipped, 4 xfailed, 9 warnings in 688.23s (0:11:28)
```

**29 条失败按文件归类，task13 占 0 条：**

```
8  test_d2_sync_retirement.py
6  test_projection_lane_regression_gate.py
3  test_excel_typography_rows.py
3  test_d2_store_value_equivalence.py
2  test_task12_canonical_resolver.py
2  test_single_pass_parse_reuse.py
1  test_task10_orm_repository_contract.py
1  test_excel_row_insertion_readiness.py
1  test_excel_shift_aware_verification.py
1  test_downstream_base_reliability_gate.py
1  test_projection_structure_hash_semantics.py
---
0  test_task13_contract_registry.py      ← 全绿
```
（`Select-String _t13_all.log -Pattern "task13"` → 命中 0 行）

task13 确实被收集并执行了：合跑共 2093 条，若 task13 未跑总数会少 237 条。
三段分跑失败数 6+12+11 = **29**，与合跑的 29 **完全一致** ⇒ 这 29 条是**与顺序无关的
既存失败**，不是污染。

---

## 结论

### 不存在 task13 的测试顺序污染

| 维度 | 覆盖方式 | 结果 |
|------|---------|------|
| 前序文件运行期副作用 | 3 段 bisect + 91 个全量同进程合跑 | task13 **237/237 全绿** |
| 任意文件（含后序）import 期副作用 | 裸名 import 全部 202 模块后同进程跑 | **237/237 全绿** |
| 随机顺序 | `pytest-randomly` 未安装，顺序确定 | 不适用 |
| 顺序忠实性 | 与 `_setup_only.txt` 还原的真实顺序逐项核对 | index 92，前序集合一致 |

**「task13 在全量套件里 45 failures」这个前提无法复现。** 最可能的解释是**归属错误**：
把套件的**总**失败数当成了 task13 的失败数。佐证 —— 仅前序 93 个文件就已有 **29 条**
与顺序无关的既存失败，把后序 110 个文件的失败/错误加上，总数正好落在 45 这一档。

因此**没有做任何「修复」**：不存在泄漏的全局状态可修。按要求也未使用
`-p no:randomly`（该插件根本没装）/ 重排文件 / xfail 等掩盖手段 —— 本来就无需掩盖。

### 这个机制是否会推广到其它 cluster

会推广的是**结论**，不是污染：

1. **本套件顺序是确定的**（无 `pytest-randomly`）。任何「随机顺序导致偶发红」的
   triage 前提都不成立；对 `test_task15_content_mutation_pg` /
   `test_task26_oo_to_html_pg` / `test_task27_conflict_resolution_pg` /
   `test_task28_sync_router_pg` 应按「确定性失败」排查，只需把它们的前序文件
   （索引 < 各自位置）纳入即可复现，不必跑全量 34 分钟。
2. **202 个测试模块 import 全部成功**（`[probe] imported=202 failed=0`）⇒ 另一
   subagent 在查的「16 个 collection/fixture errors」**不是 import 错误**，
   应定位在 fixture/setup 期。
3. **真实存在的脆弱点（本次顺带实证，未修，不在本任务授权范围）**：
   `tests/workpaper_sync/` 没有 `__init__.py`，11 个测试文件用**裸顶层名** import
   兄弟模块（`from test_task37_excel_extract import ...`、
   `from test_task15_content_mutation_pg import _STUB_DDL, ...` 等）。这只在 pytest
   把测试目录插进 `sys.path` 时成立；一旦别的目录出现同名测试文件（`tests/` 树下
   现已有 5 对重名：`test_bulk_import_service.py` / `test_consol_worksheet.py` /
   `test_f1_formula_presets.py` / `test_properties_pbt.py` / `test_k1_formula_presets.py`），
   prepend import 模式会直接报 `import file mismatch` collection 错误。这是本仓库
   **真正**具备「跨 cluster 传染性」的顺序/导入机制，建议后续单独立项处理。
4. task13 有 46 条判据是**现读磁盘**比字节/扫源码的（golden fixture、前端
   `canonicalJson.ts`、`check_workpaper_sync_closure.py`、`backend/app/**` 扫描）。
   在多 agent 并发改盘的长跑窗口里，这类判据会因**磁盘内容变化**而失败，症状酷似
   顺序污染但根因完全不同。若后续再看到「task13 长跑变红、单跑全绿」，先查
   `git status` / 文件 mtime，再怀疑顺序。
