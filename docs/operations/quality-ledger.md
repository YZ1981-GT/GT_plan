# 质量账

> 登记测试覆盖、PBT（Property-Based Testing）、压测、线上缺陷和回归范围。

## 使用说明

- 新增模块必须说明测试策略
- PBT 测试记录对应的不变量（Property）
- 线上缺陷记录根因和修复 PR
- 回归范围记录关键路径的测试文件

## 测试规模概览

| 类别 | 数量 | 位置 |
|------|------|------|
| 后端测试文件 | 400+ | `backend/tests/` |
| PBT 测试 | 50+ | `backend/tests/test_*_pbt.py` / `test_*_property*.py` |
| 前端单测 | 100+ | `audit-platform/frontend/src/**/__tests__/` |
| E2E 测试 | 10+ | `audit-platform/frontend/e2e/` |
| 压测 | 1 | `backend/tests/load_test.py` |
| Schema 契约测试 | 2 | `test_raw_sql_schema_contract.py` / `test_raw_sql_column_contract.py` |

## 高频 PBT 测试登记

| # | 测试文件 | 守护的不变量 | 模块 |
|---|---------|------------|------|
| 1 | `test_formula_engine_phase0_pbt.py` | 公式求值确定性、解析往返一致 | 公式引擎 |
| 2 | `test_property_decimal_precision.py` | 金额计算 Decimal 精度不丢失 | 全局金额 |
| 3 | `test_raw_sql_column_contract.py` | ORM/裸 SQL 引用列在 DB 中存在 | Schema 契约 |
| 4 | `test_eqcr_state_machine_properties.py` | EQCR 状态机转换合法性 | 质控 |
| 5 | `test_archive_completeness_pbt.py` | 归档文件完整性 | 归档 |
| 6 | `test_linkage_panorama_pbt.py` | 穿透路径可达、无环 | 联动穿透 |
| 7 | `test_report_stale_property.py` | 报表 stale 传播完整性 | 报表 |
| 8 | `test_wp_formula_roundtrip_pbt.py` | 底稿公式序列化/反序列化一致 | 底稿公式 |
| 9 | `test_password_verification_pbt.py` | 密码校验安全性 | 认证 |
| 10 | `test_project_permissions_pbt.py` | 权限矩阵一致性 | 权限 |

## 回归范围（关键路径）

| 关键路径 | 测试文件 | 触发条件 |
|---------|---------|---------|
| 报表金额正确性 | `test_report_engine.py`, `test_report_line_mapping.py` | TB/调整变更 |
| 穿透链路完整 | `test_drilldown.py`, `test_ledger_penetration.py` | 报表行点击 |
| 导入数据一致 | `test_import_engine.py`, `test_ledger_import_*.py` | 文件导入 |
| 公式求值 | `test_formula_engine.py`, `test_wp_eval_cell.py` | 底稿公式执行 |
| 权限隔离 | `test_auth_permission.py`, `test_project_permissions.py` | 多角色访问 |
| 归档完整 | `test_archive_orchestrator.py`, `test_archive_completeness_*.py` | 项目归档 |

## 线上缺陷登记

| # | 日期 | 缺陷描述 | 根因 | 修复文件 | 回归测试 |
|---|------|---------|------|---------|---------|
| 1 | 2026-06-02 | 明细账月小计 off-by-one | 累加在月界判断之前 | `LedgerPenetration.vue` | 5 条回归用例 |
| 2 | 2026-06-02 | doc-chat GET history 返回 0 | ResponseWrapperMiddleware 信封未解 | `useDocAiChat.ts` | mock 信封测试 |
| 3 | 2026-06-04 | 审计程序表"暂无审计程序" | file_path 为空无模板回退 | `wp_render_config.py` | 3 条回退回归 |
| 4 | 2026-06-06 | editing_locks 缺 TimestampMixin 列 | DDL 未同步 ORM mixin | `V057__editing_locks.sql` | schema drift 检测 |
| （后续补登）| | | | | |

## 压测记录

| 日期 | 场景 | 并发 | 结果 | 工具 |
|------|------|------|------|------|
| （待执行） | 目标并发 6000 | — | — | locust / k6 |

## CI 检查脚本

| 脚本 | 路径 | 作用 | CI 状态 |
|------|------|------|--------|
| check_hotspot_files | `backend/scripts/check/check_hotspot_files.py` | 超大文件检测 | ✅ 接入 |
| check_router_registration | `backend/scripts/check/check_router_registration.py` | 路由注册检查 | ✅ 接入 |
| check_no_float_amount | `backend/scripts/check/check_no_float_amount.py` | 禁止 float 金额 | ✅ 接入 |
| check_migrations | `backend/scripts/check/check_migrations.py` | 迁移文件一致性 | ✅ 接入 |
| check_property_coverage | `backend/scripts/check/check_property_coverage.py` | PBT 覆盖率 | ✅ 接入 |
| gitleaks | `.gitleaks.toml` + pre-commit | 密钥泄漏扫描 | ✅ 接入 |
| SQLFluff | `.sqlfluff` | SQL 规范（baseline 1718） | ⚠️ warning 级 |

## 变更记录

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-06 | 初始化 | 创建账本骨架，登记 10 条 PBT + 缺陷 + 回归范围 |
