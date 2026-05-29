# pytest 剩余失败清理 spec（pytest-residual-failures-cleanup）

> 状态：📌 起草中（2026-05-28）
> 优先级：P1
> 预估：3-5 个 Sprint

## 背景

`fullrun-final.log`（2026-05-28，4 个 PG-only 根因修复 + _test_auth_helper 批量接入后）：
- **8319 passed / 0 errors / 390 failed / 41 skipped**（通过率 95.1%）
- 本 spec 起草前已通过 `_test_auth_helper.py` + `qc_rule_definition_service.py is_deleted` + `WorkHour.is_overtime` 解锁约 115+ 测试，预计剩余 **~275 failed**

## 已完成（不在本 spec 范围）

- ✅ 4 个 PG-only 根因（`'::jsonb'` cast / `ARRAY` 类型 / `set_config` / `pg_advisory_xact_lock`）
- ✅ `_test_auth_helper.py` 创建 + 接入 7 个文件（metabase_attachments / t_accounts / wopi / sampling / regulatory_service / template_engine / pdf_export / signature_prerequisite / extension_services）
- ✅ `WorkHour.is_overtime` / `WorkHourEntry.is_overtime` @property 补回
- ✅ `QcRuleDefinition` model 加 SoftDeleteMixin
- ✅ 删 `test_disclosure_notes.py`（v2 重构遗留死代码）
- ✅ 修 `test_migration_002.py` cwd 路径

## 本 spec 待办分桶

### Sprint 1: 业务方法/字段重构未同步测试（P0 高密度）

- [ ] **test_audit_report.py 13 fail** — 段落名称重构（"审计师责任段" → "注册会计师对财务报表审计的责任段"）/ KeyError 'id'；逐条对齐生产代码 reportstandards
- [ ] **test_contract_analysis.py 13 fail** — 业务方法重命名（cross_check / analyze_risk / _call_llm 等不存在）；要么更新测试调新方法，要么旧方法补回
- [ ] **test_custom_dsl_coding.py 16 fail** — `FormulaEngine.register_custom_function(param_names=...)` 参数已废弃；KeyError 'type' / 'id'
- [ ] **test_workpaper_fill.py 11 fail** — confidence_level / book_data 业务字段约定改动
- [ ] **test_wopi_working_paper_qc_review.py 11 fail** — file path / QC rule 数量等业务断言

### Sprint 2: 测试间状态污染（独立调查）

- [ ] **test_formula_parser.py** — 单独跑 28/28 通过 / 全套跑 9 fail；典型测试污染
- [ ] **test_event_bus.py** — handler awaited 0 times（mock 状态在 conftest 中泄露）
- [ ] 定位策略 = `pytest --forked` 隔离 OR 二分查找污染源 OR 全套加 `gc.collect()` + 模块级 singleton autouse cleanup
- [ ] 修复策略 = 找到污染源后改 fixture autouse cleanup

### Sprint 3: PG-only 测试隔离（pytest.mark.pg_only 标记）

- [ ] **test_signed_report_rollback_protection.py 5 fail** — asyncpg 真 PG 连接 + AttributeError
- [ ] **test_template_engine.py 3 fail** — asyncpg 'NoneType' has no attribute 'send'
- [ ] **test_smoke_e2e.py 14 fail** — 走真实 HTTP 到 localhost:9980（已加 trust_env=False，但需后端启动）
- [ ] 策略 = 给依赖真 PG / 真后端的测试加 `pytest.mark.pg_only` + conftest.py `pytest_collection_modifyitems` 已有跳过逻辑（DATABASE_URL=sqlite 时 skip）

### Sprint 4: 业务断言类（PasswordConfirm / Decimal 符号 / 枚举）

- [ ] **test_signature_prerequisite.py 10 fail** — 全部 403 confirmation_token_missing（敏感操作需 password 二次确认 token）；测试 fixture 注入 confirm_token
- [ ] **Decimal 符号问题（多处）**：`Decimal('-100500.00') == Decimal('99500')` 类断言失败；业务侧借贷方向约定改动，逐条对齐
- [ ] **WpFileStatus 枚举集合断言**（test_workpaper_models）：业务新增 `level1_passed / level2_passed` 等枚举值，测试期望集合需更新

### Sprint 5: 死代码清理 + 文档

- [ ] grep 全仓 `validate_balance` / `cross_check` 等已删 API，扫剩余引用
- [ ] 测试断言用 hardcoded 报告段落名的，改为引用 `app.constants.REPORT_SECTION_NAMES`
- [ ] 文档：把"业务字段重命名时必须同步测试"列入 conventions.md 铁律

## 验收标准

- 全套 pytest 失败数 ≤ 50（vs 当前 ~275，减少 80%+）
- 通过率 ≥ 99%（vs 当前 95.1%）
- CI 卡点 = pytest 0 errors（已达成）+ failed ≤ 50
- baseline.json 记录每个 Sprint 验收数

## 不在本 spec 范围

- 业务功能新增 / 修改
- 真 PG 端到端 / 6000 并发压测（属于 phase3 UAT）
- vLLM/httpx 链路 3 bug 修复（独立 spec `vllm-httpx-bugfix`）
- vue-tsc / vitest 测试债（已在 V3 spec 收尾完成）
