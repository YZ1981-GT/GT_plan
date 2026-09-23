# Task13 契约注册表测试 — 测试顺序污染排查

状态：**进行中**（本文件随排查进展追加，不等结论一次性写入）

## 问题陈述

- `backend/tests/workpaper_sync/test_task13_contract_registry.py`
  - 单独运行：237 passed / 0 failed（本会话早前测得）
  - 作为 `tests/workpaod_sync/` 全量套件一部分运行：45 failures
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
