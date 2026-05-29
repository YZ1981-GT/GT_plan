# Pytest Residual Failures Cleanup — Bugfix Design

## Overview

全套 pytest 运行报告 259 failed / 14 errors（通过率 96.5%），目标 ≤50 failed / 0 errors / ≥99% pass rate。根因全部在测试基础设施层（fixture / assertion / mock），不涉及生产代码变更。修复策略按根因分 6 批次（Batch），每批独立可验证。

## Glossary

- **Bug_Condition (C)**: 测试套件运行结果超出可接受阈值（failed > 50 OR errors > 0）
- **Property (P)**: 修复后测试套件达到 ≤50 failed / 0 errors / ≥99% pass rate
- **Preservation**: 当前 8436 个通过的测试不回归 + 生产代码零变更
- **override_auth**: `_test_auth_helper.py` 提供的统一 dep_overrides 注入上下文管理器，解决 401 Unauthorized
- **schema drift**: 测试调用/断言引用了已过时的 API 签名、参数列表或返回值结构
- **stale assertion**: 测试期望值与当前业务逻辑输出不匹配（字段名、枚举值、格式变化）
- **fixture alignment**: 测试 fixture 创建的数据缺少必填字段或使用了已删除的枚举值

## Bug Details

### Bug Condition

测试套件整体健康度低于可接受阈值。259 个失败分布在 50+ 文件中，14 个 errors 来自 `test_smoke_e2e.py` 需要真实后端服务但未做探活跳过。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type PytestFullRunResult
  OUTPUT: boolean

  RETURN input.failed_count > 50
         OR input.error_count > 0
END FUNCTION
```

### Examples

- `test_wopi_working_paper_qc_review::test_create_working_paper` → 401 Unauthorized（缺 override_auth 注入 get_current_user）
- `test_workpaper_fill::test_generate_analytical_review` → AttributeError（WorkpaperFillService 签名已变，缺少 `year` 参数）
- `test_report_engine::test_generate_balance_sheet` → AssertionError（返回值新增 `metadata` 字段，旧断言未覆盖）
- `test_smoke_e2e::test_health_check` → ConnectionRefusedError（后端未启动，无 module-level skipif）
- `test_consol_scope::test_create_scope` → IntegrityError（fixture 缺 `client_name` NOT NULL 字段）
- `test_phase0_property::test_logout_token_invalidation` → ImportError（引用已重命名的函数）

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- 当前 8436 个通过的测试必须继续全部通过
- 生产代码（`backend/app/`）零变更，hash 不变
- `_test_auth_helper.override_auth` 上下文管理器接口不变
- `conftest.py` 共享 fixture（db_session, test_engine）行为不变
- pytest markers（pg_only, skipif）继续按环境正确跳过
- CI pipeline 现有质量门（ruff, vue-tsc, vitest）不受影响

**Scope:**
所有不涉及测试基础设施修改的测试行为应完全不受影响。修复仅限于：
- 测试文件中的 fixture 定义
- 测试文件中的 assertion 语句
- 测试文件中的 mock/patch 配置
- 测试文件中的 import 路径

## Hypothesized Root Cause

基于 fullrun-after2.log 分析，259 failed / 14 errors 的根因分为 6 类：

1. **缺失 override_auth（~34 tests, 4 files）**: `test_wopi_working_paper_qc_review`、`test_signature_prerequisite`、`test_extension_services`、`test_sla_worker_q_ticket` 的 `client` fixture 未注入 `get_current_user` override，API 调用返回 401
   - 已有 `_test_auth_helper.override_auth` 模式，机械接入即可

2. **Schema drift（~36 tests, 4 files）**: `test_workpaper_fill`、`test_contract_analysis`、`test_chain_orchestrator`、`test_phase10_step0_step1` 调用的 service 方法签名已变更（新增必填参数、返回类型变化、方法重命名）
   - 需读取当前 service 代码确认新签名后更新测试调用

3. **Stale assertions（~32 tests, 6 files）**: `test_report_engine`、`test_event_bus`、`test_prefill_provenance`、`test_prefill_snapshot_diff_endpoint`、`test_ai_content_confirm_flow`、`test_ai_content_structured` 的断言引用了过时的字段名/值
   - 需读取当前 service 返回值结构后更新 expected values

4. **Deeper fixture alignment（~50+ tests, 10+ files）**: `test_audit_report`、`test_report_config`、`test_cfs_worksheet`、`test_custom_dsl_coding`、`test_custom_templates`、`test_consol_*` 系列在 auth 修复后暴露更深的 fixture 问题（缺必填字段、枚举值已删除、外键约束不满足）
   - 需逐文件对齐 fixture 数据与当前 ORM model 定义

5. **PBT/Property test outdated（~7 tests, 5 files）**: `test_phase0_property`、`test_phase4_pbt`、`test_batch_review_pass`、`test_manager_dashboard_pbt`、`test_router_registry_split_pbt` 的 generators/oracles 引用了过时的 schema
   - 需更新 hypothesis strategies 和 oracle 函数

6. **Miscellaneous（~100+ tests, 20+ files）**: 混合 auth + schema + assertion 问题，包括 `test_audit_log_enhanced`（chain verify 签名变）、`test_formula_parser`（event loop 污染已修）、各循环测试的 fixture 对齐等
   - 逐文件诊断，按根因归类到上述 5 类之一处理

## Correctness Properties

Property 1: Bug Condition - Test Suite Health Recovery

_For any_ full pytest run on `backend/tests/` after applying all batches, the fixed test suite SHALL report ≤50 failed tests AND 0 errors AND pass rate ≥99%.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - No Regression on Passing Tests

_For any_ test that currently passes (8436 tests) in the unfixed suite, the fixed test suite SHALL continue to pass that test without modification, preserving all existing correct test behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

约束：仅修改 `backend/tests/` 下的文件，绝不修改 `backend/app/` 生产代码。

**Batch 1: override_auth 接入（~34 tests, 4 files）**

**Files**: `test_wopi_working_paper_qc_review.py`, `test_signature_prerequisite.py`, `test_extension_services.py`, `test_sla_worker_q_ticket.py`

**Changes**:
1. 添加 `from tests._test_auth_helper import override_auth` import
2. 将 `client` fixture 改为 `async with override_auth(app, db_session=db_session) as c: yield c`
3. 删除手动 `app.dependency_overrides` 设置（如有）
4. 确保 `seeded_db` fixture 在 `client` 之前执行（fixture 依赖链正确）

**Batch 2: Schema drift 修复（~36 tests, 4 files）**

**Files**: `test_workpaper_fill.py`, `test_contract_analysis.py`, `test_chain_orchestrator.py`, `test_phase10_step0_step1.py`

**Changes**:
1. 读取对应 service 当前签名（参数列表、返回类型）
2. 更新测试中的 service 调用（添加新必填参数、更新方法名）
3. 更新 mock return values 匹配当前返回结构
4. 更新 assertions 匹配新的返回字段

**Batch 3: Stale assertion 更新（~32 tests, 6 files）**

**Files**: `test_report_engine.py`, `test_event_bus.py`, `test_prefill_provenance.py`, `test_prefill_snapshot_diff_endpoint.py`, `test_ai_content_confirm_flow.py`, `test_ai_content_structured.py`

**Changes**:
1. 读取当前 service 返回值结构
2. 更新 `assert result["field"]` 中的字段名
3. 更新期望值（枚举值、格式、新增字段）
4. 对新增必填字段添加 assert 覆盖

**Batch 4: Deeper fixture alignment（~50+ tests, 10+ files）**

**Files**: `test_audit_report.py`, `test_report_config.py`, `test_cfs_worksheet.py`, `test_custom_dsl_coding.py`, `test_custom_templates.py`, `test_consol_scope.py`, `test_minority_interest.py`, `test_elimination.py`, `test_goodwill.py`, `test_forex.py`, `test_component_auditor.py`

**Changes**:
1. 为 `Project` fixture 添加 `client_name="Test Client"` 必填字段
2. 将 `status="active"` 字符串改为 `ProjectStatus.execution` 枚举
3. 修复已删除的枚举值引用（如 `ScopeCompanyType.PARENT` → 当前有效值）
4. 添加新增 required 字段（如 `ForexRates.functional_currency`）
5. 确保外键引用的实体在 fixture 中已创建

**Batch 5: PBT/Property test 更新（~7 tests, 5 files）**

**Files**: `test_phase0_property.py`, `test_phase4_pbt.py`, `test_batch_review_pass.py`, `test_manager_dashboard_pbt.py`, `test_router_registry_split_pbt.py`

**Changes**:
1. 更新 hypothesis strategies 生成当前有效的输入
2. 更新 oracle 函数匹配当前业务规则
3. 修复 import 路径（已重命名的函数/类）
4. 调整 `max_examples` 避免超时

**Batch 6: Miscellaneous remaining（~100+ tests, 20+ files）**

**Changes**:
1. `test_smoke_e2e.py`: 确认 module-level skipif 已生效（14 errors → 0）
2. `test_formula_parser.py`: 确认 `asyncio.new_event_loop()` 修复已生效
3. 逐文件诊断剩余失败，按根因归类处理
4. 对无法在当前环境修复的测试（需真实 PG / 外部服务）添加 `pytest.mark.skipif` 守卫

## Testing Strategy

### Validation Approach

测试策略分两阶段：先在未修复代码上确认失败模式（已由 fullrun-after2.log 完成），再逐批修复并验证。每批修复后运行受影响文件的 pytest 确认 delta。

### Exploratory Bug Condition Checking

**Goal**: 确认 259 failed / 14 errors 的根因分类正确。已由 fullrun-after2.log 完成。

**Test Plan**: 对每批涉及的文件单独运行 pytest，观察失败模式。

**Test Cases**:
1. **Batch 1 探索**: `python -m pytest backend/tests/test_wopi_working_paper_qc_review.py --tb=short -q`（预期 ~11 个 401 Unauthorized）
2. **Batch 2 探索**: `python -m pytest backend/tests/test_workpaper_fill.py --tb=short -q`（预期 AttributeError / TypeError）
3. **Batch 3 探索**: `python -m pytest backend/tests/test_report_engine.py --tb=short -q`（预期 AssertionError）
4. **Batch 4 探索**: `python -m pytest backend/tests/test_consol_scope.py --tb=short -q`（预期 IntegrityError）

**Expected Counterexamples**:
- 401 Unauthorized（缺 get_current_user override）
- AttributeError: 'X' has no attribute 'Y'（方法重命名）
- TypeError: missing required argument（签名变更）
- AssertionError: 'expected_field' not in result（字段名变化）
- IntegrityError: NOT NULL constraint failed（fixture 缺必填字段）

### Fix Checking

**Goal**: 验证每批修复后，该批涉及的测试全部通过（或降至可接受水平）。

**Pseudocode:**
```
FOR ALL batch IN [1, 2, 3, 4, 5, 6] DO
  apply_batch_fix(batch)
  result := run_pytest(batch.affected_files)
  ASSERT result.failed_count <= batch.acceptable_remaining
  ASSERT result.error_count == 0
END FOR

// Final validation
final_result := run_pytest("backend/tests/")
ASSERT final_result.failed_count <= 50
ASSERT final_result.error_count == 0
ASSERT final_result.pass_rate >= 0.99
```

### Preservation Checking

**Goal**: 验证每批修复不引入回归（已通过的测试继续通过）。

**Pseudocode:**
```
FOR ALL batch IN [1, 2, 3, 4, 5, 6] DO
  apply_batch_fix(batch)
  result := run_pytest("backend/tests/")
  ASSERT result.passed_count >= 8436  // 不低于修复前通过数
  ASSERT no_new_failures(result, baseline)
END FOR
```

**Testing Approach**: 每批修复后运行全套 pytest（`python -m pytest backend/tests/ --tb=no -q`），对比 passed/failed 计数确保 passed 不减少。

**Test Cases**:
1. **Batch 1 保持**: 修复 override_auth 后，原 8436 passed 不减少
2. **Batch 2 保持**: 修复 schema drift 后，Batch 1 修复的测试继续通过
3. **Batch 3 保持**: 修复 stale assertions 后，前两批修复不回归
4. **Full suite 保持**: 所有批次完成后，`passed >= 8436 + recovered_tests`

### Unit Tests

- 每批修复后对受影响文件运行 `python -m pytest backend/tests/{file} -v --tb=short`
- 验证 override_auth 注入后 API 调用返回 200/201（非 401）
- 验证 schema drift 修复后 service 调用不抛 TypeError/AttributeError
- 验证 fixture alignment 后 ORM 对象成功 flush 到 SQLite

### Property-Based Tests

- Batch 5 专门修复 PBT 测试本身（更新 strategies + oracles）
- 修复后运行 `python -m pytest backend/tests/test_phase0_property.py backend/tests/test_phase4_pbt.py -v`
- 验证 hypothesis 不再报 InvalidArgument / ImportError

### Integration Tests

- 全套运行 `python -m pytest backend/tests/ --tb=no -q` 作为最终集成验证
- 对比 fullrun-after2.log baseline（259 failed / 14 errors）确认改善
- 目标：≤50 failed / 0 errors / ≥99% pass rate（≥8600 passed out of ~8700 total）
