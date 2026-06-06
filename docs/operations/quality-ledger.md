# 质量账

> 登记平台测试体系、PBT 覆盖、压测基线、线上缺陷和回归范围。确保质量可追溯、可度量。

## 登记规则

- 新增模块必须配对测试文件
- PBT（Property-Based Testing）覆盖核心不变量
- 线上缺陷必须登记回归测试范围
- 压测基线每季度更新

## 测试体系总览

| 测试类型 | 框架 | 位置 | 用途 |
|----------|------|------|------|
| 后端单元测试 | pytest | `backend/tests/` | service/router 逻辑 |
| 后端 PBT | hypothesis | `backend/tests/` | 核心不变量验证 |
| API 契约测试 | schemathesis | `backend/tests/test_api_schemathesis.py` | 全端点无 5xx |
| SQL schema 契约 | pytest + sqlglot | `backend/tests/test_raw_sql_*_contract.py` | 列/表引用正确性 |
| 前端单元测试 | vitest | `frontend/src/**/*.spec.ts` | composable/组件逻辑 |
| 前端 E2E | playwright | `frontend/e2e/` | 页面流程验证 |
| 检查脚本 | pytest | `backend/tests/scripts/` | CI 卡点脚本测试 |

## 高频测试套件

| 套件 | 文件 | 覆盖范围 | 状态 |
|------|------|----------|------|
| 附注单元格合并 PBT | `test_note_cell_merge_pbt.py` | 列增减/行对齐/幂等性 | ✅ |
| 附注单元格合并单测 | `test_note_cell_merge.py` | 14 场景边界 | ✅ |
| 公式追踪 | `test_note_cell_trace.py` | 公式展开/来源解析 | ✅ |
| AI 内容门禁 | `test_ai_content_gate_rule.py` | AI 输出必须人工确认 | ✅ |
| JWT 配置 | `test_config_jwt_validation.py` | 环境×密钥强度组合 | ✅ |
| API 无 5xx | `test_api_schemathesis.py` | 全 GET 端点 | ✅ |
| SQL 列契约 | `test_raw_sql_column_contract.py` | 裸 SQL 列引用 | ✅ |
| SQL 表契约 | `test_raw_sql_schema_contract.py` | 裸 SQL 表引用 | ✅ |
| 迁移幂等 | `test_migration_idempotent.py` | 迁移脚本重跑不报错 | ✅ |
| 底稿渲染 | `test_wp_render_config.py` | 模板路径/程序表生成 | ✅ |

## 线上缺陷回归

| 缺陷 | 根因 | 回归测试 | 修复日期 |
|------|------|----------|----------|
| 明细账月小计 off-by-one | 累加在边界判断前 | `test_ledger_display.spec.ts` 5 条 | 2026-06-02 |
| 底稿目录 No Data | B-Index 只查当前 wp | `test_wp_cycle_directory.py` 5 条 | 2026-06-06 |
| schema drift 500 | ORM↔DDL 不一致 | `test_raw_sql_*_contract.py` | 2026-05-30 |

## 变更历史

| 日期 | 变更 | PR |
|------|------|----|
| 2025-01-01 | 初始骨架创建 | — |
