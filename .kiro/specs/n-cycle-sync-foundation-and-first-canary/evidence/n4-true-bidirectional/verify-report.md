# N4 税金及附加 真双向改线 — 独立验证报告

> 本报告由独立验证步骤产出（只跑验证+写报告，**未改任何生产代码**）。
> 验证对象 = N4 canary（`xlsx/gt-n4-taxes-and-surcharges`）真双向实现。
> 实施计划 = `.kiro/specs/n-cycle-sync-foundation-and-first-canary/.agents/n4-plan.md`。
> 环境：Windows / PowerShell；Python `d:\GT_plan\.venv\Scripts\python.exe`；仓库根 `d:\GT_plan`。
> 执行时间：2026-10-01（会话时点）。

## 环境前置事实

- Docker `audit-onlyoffice` 容器实测 **running (healthy)**（13h uptime）⇒ 按计划纪律，**OO evidence 不标 `*`**，直接跑真引擎。
- Docker `audit-postgres` **running** ⇒ 五环发布真库证据可查，无需 skip。
- git HEAD = `c917b65d2`（分支 `work/2026-10-01-i-cycle-classification-convergence`）；N4 全部实现产物在**未提交工作树**（`phase5_n4_sheets.py` / `phase5_n4_taxes_and_surcharges.py` / `n4.taxes_and_surcharges.json` / `verify_n4_oo94_roundtrip.py` / `test_n4_adapter_registration.py` 等均为 `??` 或 `M`）。

## 总结论

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | 真 OnlyOffice 9.4 roundtrip | ✅ PASS（exit 0，真容器） |
| 2 | 五环发布真库三表证据 | ✅ PASS（三表齐、互相闭合） |
| 3 | golden digest + sheet specs 注册 | ✅ PASS（含 N4 无 SKIP） |
| 4 | N4 守卫 + N 迁移 + foundation canary pytest | ✅ PASS（246 passed / 1 skipped / 0 failed） |
| 5 | 后端 import 冒烟 | ✅ PASS |
| 6 | 既有红归因 | ✅ 无红可归（在场三套件全绿） |

**整体：全部 PASS。无发现需复核步骤处置的失败。** 唯一 1 处 skip 为良性条件跳过（见项 4）。

---

## 项 1：真 OnlyOffice 9.4 roundtrip — PASS

**命令**（同步捕获退出码）：
```
[Console]::OutputEncoding=UTF8; $env:PYTHONIOENCODING="utf-8"
& d:\GT_plan\.venv\Scripts\python.exe backend/scripts/e2e/verify_n4_oo94_roundtrip.py
```
**退出码：`EXITCODE=0`**（独立同步跑一次确认；此前后台跑亦打印最终成功行）。

**真引擎确认**（非合成降级）：
- 脚本头 11 行明文「链路每一步都是生产代码，无合成替身；真 ConvertService xlsx→xlsx 重存」。
- `OO_URL = http://localhost:8080`（环境变量 `N4_OO_URL` 可覆盖），`HOST_FROM_CONTAINER = host.docker.internal`，经 `ConvertService.ashx` 转换。
- 运行期 stderr 可见本地 HTTP 文件服务返回 `GET /n4-materialized.xlsx HTTP/1.1 200`，`[⑤] OO resave OK size=50650 percent=100` ⇒ 真实发生了容器内转换。

**关键输出摘录**（utf-8 解码）：
```
[0] wp=4e5fdd29 project=14fb8c10 真库 N4-2-detail-rows 分母=0 行（0=如实空分母，往返用合成 2 行）
[①] attach=('n4.taxes_and_surcharges',)
[②] generation=1 substrate=000000001-8a4c6cd49a7a.xlsx
[③] projection values=16 rows=2
[④] materialize size=47503
[⑤] OO resave OK size=50650 percent=100
[⑥] extract values=54 · G1 等值门 OK
[⑦] N4-2-detail-rows 往返：我的 2 行逐字段相等（rowKey 稳定） + 8 条预印具名行保留
    (['消费税','城市维护建设税','教育费附加','资源税','房产税','土地使用税','车船使用税','印花税'])；无错配身份
[⑧a] OO 重存后受管行 [19, 20] 的 E/I/K 6 格全部仍是公式
[⑧b] 税金及附加审定表N4-1 R7~R15×A..M 117 格：OO 引擎改写 0 格；
     materialize 只中性化裸 IF 18 格 ['K7'..'K15','M7'..'M15']（GC-2 挂载的 OO 崩溃中性化，预期）
[⑨] N4-2-detail-rows 0 行快照 digest 不变（脚本不写库）
✅ N4 真 OO 引擎往返全绿（HTML→OO→HTML）
```

**断言落实**：
- 受管公式往返：E/I/K 共 6 格（行 19/20）往返后**仍是公式** ⇒ formula_mask 真生效。✅
- 派生表只读：`税金及附加审定表N4-1` R7~R15×A..M 共 117 格 **OO 引擎改写 0 格**（只读投影未被污染）；materialize 只中性化裸 IF 18 格（GC-2 预期）。✅
- store-row 等值：合成 2 行逐字段相等、rowKey 稳定；8 条预印具名税种行保留、**无骨架行翻倍**（ghost anchor=taxType 挡住预印行，J1 翻倍教训已规避）。✅
- 真库快照：N4-2-detail-rows 真库 **分母=0 行**，脚本**如实声明空分母**（空≠通过），往返用固定 UUID 合成载荷，前后 digest 不变（脚本不写库）。✅

---

## 项 2：五环发布真库证据 — PASS

**DSN**：`postgresql://postgres:postgres@localhost:5432/audit_platform`（经 postgres MCP 查，库在线）。

**entry_state**：
```sql
SELECT entry_id, current_representation_id, representation_generation, updated_at
FROM working_paper_sync_entry_state WHERE entry_id = 'xlsx/gt-n4-taxes-and-surcharges';
```
→ **1 行**：`current_representation_id = 22a3e9bd-bad9-4cdd-ab65-6ff26e648c4b`（**非空**），`representation_generation = 1`，`updated_at = 2026-10-01 12:34:34 UTC`。

**content_representation**：
```sql
SELECT id, wp_id, content_version_id, generation, document_type, adapter_id, reason, created_at
FROM working_paper_content_representation WHERE entry_id = 'xlsx/gt-n4-taxes-and-surcharges';
```
→ **1 行**：`id=22a3e9bd…`（与 entry_state 的 current_representation_id 一致）、`wp_id=4e5fdd29-9dc3-45c5-abad-640d522af188`、`content_version_id=753bb589-0ec0-4fae-88c9-21eae1b6fc13`、`generation=1`、`document_type=xlsx`、`adapter_id=n4.taxes_and_surcharges`、`artifact_sha=8a4c6cd49a7a…`、`adapter_build_digest=1585ae435254…`、`reason=content_commit`。

**content_version**：
```sql
SELECT id, wp_id, revision, source, projection_sha256, created_at
FROM working_paper_content_version WHERE wp_id = '4e5fdd29-9dc3-45c5-abad-640d522af188';
```
→ **1 行**：`id=753bb589…`（与 representation 的 content_version_id 一致）、`revision=1`、`source=html`、`proj_sha=2ea359f26160…`。

**三表闭合校验**：entry_state.current_representation_id → representation.id ✅；representation.content_version_id → content_version.id ✅；三表 wp_id 均 `4e5fdd29`、时间戳同为 `12:34:34`。五环发布（authority/template/instrumentation/contract/bundle→representation）在真库留痕完整，generation=1 即首版，与计划 Task 7d 预期一致。

> 说明：`working_paper` 无 `wp_code` 列（在 `wp_index`，须 JOIN），故 wp_code 口径未额外 JOIN 核对；entry_id 与 adapter_id 已唯一锁定 N4 底稿，证据充分。

---

## 项 3：golden digest + sheet specs 注册 — PASS

**命令 A**：`d:\GT_plan\.venv\Scripts\python.exe backend/scripts/check/check_sync_provider_golden_digest.py`
- **退出码：0**。
- 摘录：`✅ golden digest 零回归：161 个 digest 逐个不变（覆盖 25 家，零跳过）` ⇒ **无 `[SKIP]`**。
- N4 入基线确认：`backend/scripts/check/_sync_provider_golden_digest.json` 含 `"label":"n4"` / `"adapter_id":"n4.taxes_and_surcharges"` / `"n42-managed":"d68acdfd1f678733959764d332e0d9514b5cd580978699f9353629a019f48b80"`。

**命令 B**：`d:\GT_plan\.venv\Scripts\python.exe backend/scripts/check/check_sheet_specs_fully_registered.py`
- **退出码：0**。
- 摘录：`✅ sheet spec 全部接入注册表：54 个 adapter 已注册`。

---

## 项 4：N4 守卫 + N 迁移 + foundation canary pytest — PASS

**命令**（设 `PYTHONIOENCODING=utf-8`，后台 `Start-Process` + 读文件）：
```
python -m pytest backend/tests/workpaper_sync/test_n4_adapter_registration.py \
  backend/tests/workpaper_sync/test_task56_n_cycle_migration.py \
  backend/tests/workpaper_sync/test_n_cycle_foundation_canary.py -v --tb=short
```
**结果**：`================= 246 passed, 1 skipped, 1 warning in 43.46s =================`
- **0 failed / 0 error**（匹配到的 "ERROR" 行均为 schemathesis `DeprecationWarning`，非测试失败）。

**1 处 skip（良性条件跳过，非失败）**：
`test_n4_adapter_registration.py::TestAdapterRegistration::test_oo_crash_fn_resolves_to_shared_object`
- 原因：该用例断言 N4 的 OO 崩溃中性化函数与 g7 解析到**同一函数对象**（`is`），但依赖私有符号 `_resolve_oo_crash_neutralization_fn`；若该私有符号不可 import 则 `pytest.skip("… 不是公开符号 ⇒ 跳过 is 判据")`。本次因该私有符号未暴露而跳过。
- 影响：`is`-同一性这一额外判据未跑；但同套件内 N4 adapter 注册、几何、provider 接口、contract 交付等判据均 PASS，且项 1 roundtrip 已实证 GC-2 中性化行为正确 ⇒ 该 skip 不构成缺口。

---

## 项 5：后端 import 冒烟 — PASS

**命令**：`python -c "import app.main"`（cwd=backend，设 PYTHONIOENCODING=utf-8）
- 输出 `IMPORT_OK`，退出码 0（仅伴随 JWT 弱密钥警告与模型源检查跳过提示，均非错误）。

---

## 项 6：既有红归因 — 无红可归

- 在场三套件（test_n4_adapter_registration / test_task56_n_cycle_migration / test_n_cycle_foundation_canary）**全绿**，无任何 FAILED/ERROR ⇒ **无需对任何红做归因**。
- 计划提及的 task48（F positional-defects / Property21）、task51（I frozen-label）为**其他套件的已知非本轮**失败，**不在本次验证的三套件范围内**，未触发，故不涉及。
- 并发脏树下 `git stash` 不可用；本项结论基于「在场套件零红」直接成立，无需对比 HEAD。

---

## 疑点 spot-check（窄范围）

1. **OO 是否真容器而非合成降级**：已核（见项 1 真引擎确认）。`percent=100` + 容器 HTTP 200 + 脚本头明文 ⇒ 真 ConvertService 转换。✅
2. **受管公式列 E/I/K 口径**：roundtrip ⑧a 实证行 19/20 的 E/I/K 往返后仍是公式，与计划 §0.3 `FORMULA_COLUMNS=("E","I","K")` 一致。✅
3. **派生表 N4-1 只读**：⑧b 实证 OO 改写 0 格，与 §0.2 「审定表为只读投影」裁决一致。✅

无其余可 articulate 的疑点。

## 临时文件清理

本步骤创建的临时输出（`_golden.txt` / `_sheetspecs.txt` / `_n4rt_*.txt` / `_n4pytest*.txt` / `_n4rt_pid.txt` 等）已全部删除；未新增任何生产代码或仓库残留。
