# Characterization 零回归基线（后端）— Task 1.1

> _Requirements: 6.1_ ｜ 基线记录时间：2026-07-26 ｜ 本任务**未修改任何生产代码**（仅跑测试 + 读 config）。
>
> 用途：作为后续各 Wave 的零回归锚点。特别地 —
> - **Property 9**（`CONSOL_NOTES_V2_ENABLED=False` 时零改动，Task 4.2）→ 对照 `test_consol_disclosure_v2` / `test_consol_phase2_v2_contract`。
> - **Property 12**（`DISCLOSURE_NOTE_FORMULA_ENABLED=False` 时零改动，Task 6.2）→ 对照 `test_disclosure_formula_report_sync_characterization` / `test_note_formula_gray_two_state`。

## 一、灰度旗默认值（config.py 实测引用）

两旗均确认默认 `False`（`backend/app/core/config.py`）：

```python
# 行 211
CONSOL_NOTES_V2_ENABLED: bool = False
# 行 291
DISCLOSURE_NOTE_FORMULA_ENABLED: bool = False
```

（旁证：`DISCLOSURE_NOTE_RAG_ENABLED: bool = False` / `DISCLOSURE_NOTE_VALIDATION_STRICT: bool = False` / `CONSOL_CROSS_TEMPLATE_ENABLED: bool = False`，均默认 False。）

这是后续 Wave 的零回归红线：未启用任一新能力时，既有行为必须逐字节等价当前。

## 二、锚点测试基线（全绿）

### 命令 A — 命名锚点集（`test_wp_disclosure_sync*` / `test_consol_disclosure_v2` / `test_note_readiness_and_stale`）

```
cd backend
python -m pytest tests/test_wp_disclosure_sync.py tests/test_wp_disclosure_sync_html_audit.py \
  tests/test_wp_disclosure_sync_html_property.py tests/test_wp_disclosure_sync_revive.py \
  tests/test_wp_disclosure_sync_section_title.py tests/test_wp_disclosure_sync_target_year.py \
  tests/services/test_consol_disclosure_v2.py tests/test_note_readiness_and_stale.py \
  -p no:cacheprovider --tb=line -q
```

结果：**89 passed, 0 failed**（20 warnings，见下 §三）。

| 测试文件 | passed | 备注 |
|---|---|---|
| `tests/test_wp_disclosure_sync.py` | 18 | |
| `tests/test_wp_disclosure_sync_html_audit.py` | 5 | |
| `tests/test_wp_disclosure_sync_html_property.py` | **0 collected** | 仅含 `FakeNote`/`FakeUser`/`FakeDB` 辅助类占位，无 `def test_*` / `@given`（**pre-existing**，非本任务引入） |
| `tests/test_wp_disclosure_sync_revive.py` | 3 | |
| `tests/test_wp_disclosure_sync_section_title.py` | 6 | |
| `tests/test_wp_disclosure_sync_target_year.py` | 11 | |
| `tests/services/test_consol_disclosure_v2.py` | 31 | **Property 9 锚点**（V2 逻辑） |
| `tests/test_note_readiness_and_stale.py` | 15 | 就绪度 + stale 现状 |
| **合计** | **89** | |

### 命令 B — 灰度旗 default-off 控制锚点（Property 9 / 12 对照）

```
cd backend
python -m pytest tests/test_disclosure_formula_report_sync_characterization.py \
  tests/services/test_note_formula_gray_two_state.py \
  tests/services/test_consol_phase2_v2_contract.py \
  -p no:cacheprovider --tb=line -q
```

结果：**28 passed, 0 failed**。

| 测试文件 | passed | 锚定 |
|---|---|---|
| `tests/test_disclosure_formula_report_sync_characterization.py` | 14 | **Property 12** — `DISCLOSURE_NOTE_FORMULA_ENABLED=False` 时 `resolve_formula` 返 None / `sync_report_to_notes` 仅清 is_stale 的现状 |
| `tests/services/test_note_formula_gray_two_state.py` | 4 | 公式灰度两态（关态零改动） |
| `tests/services/test_consol_phase2_v2_contract.py` | 10 | **Property 9** — V2 契约 |
| **合计** | **28** | |

### 基线总计

**命令 A + B 合计：117 passed / 0 failed**（`html_property.py` 0 collected 为 pre-existing 占位文件）。这是后续 Wave 必须保持全绿的锚点集。

## 三、Pre-existing 现象（非本任务引入，非失败）

1. **20 warnings**（命令 A）：`RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited`，来自 mock-DB 单测（`note_validation_engine.py:764/799`、`dataset_query.py:102`、`wp_disclosure_sync_service.py:222`、`consol_disclosure_service.py:1238`）。属既有 AsyncMock 用法告警，不影响通过。
2. `test_wp_disclosure_sync_html_property.py` 只有辅助类无测试函数 → 0 collected（`exit 1` 仅 collect-only 场景，合并跑时不影响总结果）。

## 四、Task 4.2 / 6.2 diff 使用说明

- 后续新增 `test_consol_notes_v2_persist.py`（Wave 3）与 `test_note_formula_gray_service.py`（Wave 4b）落地后，须保证本基线的命令 A + B **仍 117 passed / 0 failed**。
- Property 9：开关关时 `test_consol_disclosure_v2`(31) + `test_consol_phase2_v2_contract`(10) 行为不变。
- Property 12：开关关时 `test_disclosure_formula_report_sync_characterization`(14) + `test_note_formula_gray_two_state`(4) 行为不变。
