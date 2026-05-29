# Implementation Plan: Report Module Enhancement

## Overview

将报表模块从 ~85% 完成度推进到生产就绪。涵盖 5 大领域：种子数据公式补全、审计日志路由注册、覆盖率验证脚本、CFS 自动调整规则扩展、报表 API 测试基础设施修复。所有变更仅涉及后端代码（backend/app/、backend/tests/、backend/data/、backend/scripts/）。

## Tasks

- [x] 1. 审计日志路由注册修复
  - [x] 1.1 在 router_registry/system.py 注册 audit_logs router
    - 在 `register_system_routers()` 中添加 `from app.routers.audit_logs import router as audit_logs_router`
    - 调用 `app.include_router(audit_logs_router, prefix="/api", tags=["audit-logs"])`
    - 确保注册位置不影响现有路由（放在 §120 之后新建 §127 区块）
    - _Requirements: 2.1, 2.3, 2.4_

  - [ ]* 1.2 编写 audit_logs 路由注册单元测试
    - 新建 `backend/tests/test_audit_logs_registration.py`
    - 使用 override_auth + in-memory SQLite 验证 GET /api/audit-logs/verify-chain 返回 200（非 404）
    - 验证已认证用户（admin 角色）可正常访问
    - _Requirements: 2.2_

- [x] 2. CFS 自动调整规则扩展
  - [x] 2.1 扩展 AUTO_ADJUSTMENT_RULES 列表
    - 在 `backend/app/services/cfs_worksheet_engine.py` 的 `AUTO_ADJUSTMENT_RULES` 中新增 10 条规则
    - 新增规则：资产减值损失(6702/CF-S04)、处置长期资产损失(6115/CF-S11)、固定资产报废损失(6711/CF-S11)、存货跌价准备(1471/CF-S04)、坏账准备(1231/CF-S04)、存货的减少(1401/CF-S12)、经营性应收项目的减少(1122/CF-S13)、经营性应付项目的增加(2202/CF-S14)、递延所得税资产减少(1811/CF-S10)、递延所得税负债增加(2901/CF-S15)
    - 注意：递延所得税资产(1811)已存在，需检查是否需要更新 cf_row_code
    - 每条规则包含 description、account_code、keywords、category、line_item、cf_row_code 字段
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [ ]* 2.2 编写 Property 8: Auto-adjustment rules have valid metadata
    - 新建 `backend/tests/test_cfs_adjustment_rules.py`
    - 遍历所有 AUTO_ADJUSTMENT_RULES，验证 category 是有效 CashFlowCategory 枚举值
    - 验证 cf_row_code 匹配正则 `CF-S\d{2}`
    - 验证所有 Requirement 4.1-4.3 列出的调整项都存在于规则列表中
    - **Property 8: Auto-adjustment rules have valid metadata**
    - **Validates: Requirements 4.5**

  - [ ]* 2.3 编写 Property 7: Auto-adjustment calculation correctness
    - 在 `backend/tests/test_cfs_adjustment_rules.py` 中添加 hypothesis 属性测试
    - 使用 `@settings(max_examples=15)` 控制速度
    - 生成随机 opening_balance 和 closing_balance（Decimal），验证调整金额 = abs(closing - opening)
    - 验证科目不存在时跳过规则不报错
    - 使用 AsyncMock 模拟 db session 和试算表查询
    - **Property 7: Auto-adjustment calculation correctness**
    - **Validates: Requirements 4.4, 4.6**

- [x] 3. Checkpoint - 确保路由注册和 CFS 规则测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 报表公式 DSL 解析器健壮性验证
  - [ ]* 4.1 编写 Property 6: Missing account returns zero
    - 在 `backend/tests/test_report_engine_properties.py` 中新建属性测试
    - 使用 hypothesis 生成随机 4 位科目编码（不在 TB fixture 中）
    - 验证 ReportFormulaParser.execute() 对 TB('random_code','期末余额') 返回 Decimal("0")
    - 使用 in-memory SQLite + seeded_db fixture
    - `@settings(max_examples=15)`
    - **Property 6: Missing account returns zero**
    - **Validates: Requirements 6.6**
    - _Requirements: 6.6_

  - [ ]* 4.2 编写 Property 1: Formula DSL round-trip
    - 新建 `backend/tests/test_formula_parser_roundtrip.py`
    - 使用 hypothesis `st.recursive` 生成合法 Formula DSL AST（TB/SUM_TB/ROW/SUM_ROW + 算术运算）
    - 序列化 → 解析 → 再序列化，验证语义等价
    - `@settings(max_examples=15)`
    - **Property 1: Formula DSL round-trip**
    - **Validates: Requirements 3.6, 6.9**
    - _Requirements: 3.6, 6.9_

- [ ] 5. 种子数据公式补全增强
  - [x] 5.1 补充 ReportFormulaService 的特殊公式映射
    - 检查 `_BS_SPECIAL` / `_IS_SPECIAL` / `_CFS_INDIRECT_SPECIAL` 中缺失的行名映射
    - 确保 `_CFS_INDIRECT_SPECIAL` 覆盖 Requirement 4 中列出的所有间接法调整项（资产减值损失、处置固定资产损失等）
    - 确保标题行识别逻辑正确：`row_name.endswith("：") or row_name.endswith(":")`
    - _Requirements: 1.5, 1.6, 1.7, 1.8, 1.9_

  - [ ]* 5.2 编写 Property 2: Formula column matches report type
    - 在 `backend/tests/test_report_formula_service.py` 中新建属性测试（或扩展已有文件）
    - 使用 hypothesis `st.sampled_from` 从 `_BS_SPECIAL.keys()` 和 `_IS_SPECIAL.keys()` 采样
    - 验证 BS 行公式包含 `'期末余额'`，IS 行公式包含 `'本期发生额'`
    - `@settings(max_examples=15)`
    - **Property 2: Formula column matches report type**
    - **Validates: Requirements 1.5, 1.6**

  - [ ]* 5.3 编写 Property 3: Total rows use ROW/SUM_ROW references
    - 在同一测试文件中添加属性测试
    - 生成 is_total_row=True 的行配置，验证生成的公式仅包含 ROW()/SUM_ROW()
    - `@settings(max_examples=15)`
    - **Property 3: Total rows use ROW/SUM_ROW references**
    - **Validates: Requirements 1.7**

  - [ ]* 5.4 编写 Property 4: Title rows are skipped
    - 验证 row_name 以 "：" 或 ":" 结尾的行，fill_all_formulas 不填充公式
    - 使用 hypothesis `st.text() + st.sampled_from(["：", ":"])` 生成标题行名
    - `@settings(max_examples=15)`
    - **Property 4: Title rows are skipped**
    - **Validates: Requirements 1.8**

  - [ ]* 5.5 编写 Property 5: Formula fill idempotence
    - 验证已有 formula 的行不被 fill_all_formulas 覆盖
    - 使用 hypothesis 生成随机非空 formula 字符串
    - `@settings(max_examples=15)`
    - **Property 5: Formula fill idempotence**
    - **Validates: Requirements 1.9**

- [x] 6. Checkpoint - 确保公式补全和属性测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 多标准公式覆盖验证脚本
  - [x] 7.1 创建验证脚本 validate_formula_coverage.py
    - 新建 `backend/scripts/validate_formula_coverage.py`
    - 实现 `async def validate_coverage(standard, verbose)` 函数
    - 扫描 report_config 表中 4 个标准的所有行次，统计公式覆盖率
    - 输出每个标准每种报表类型的覆盖率百分比
    - 列出所有 formula 为 null 且非标题行的行次（row_code + row_name）
    - CLI 参数：`--standard`（默认 all）、`--verbose`
    - 覆盖率 < 95% 时以非零退出码退出
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 7.2 编写 Property 11: Validation script correctly identifies missing formulas
    - 新建 `backend/tests/test_report_config_consistency.py`
    - 生成混合行次（有/无 formula、标题/非标题），验证脚本正确识别缺失行
    - 缺失 = formula IS NULL AND row_name 不以 "："/":" 结尾
    - `@settings(max_examples=15)`
    - **Property 11: Validation script correctly identifies missing formulas**
    - **Validates: Requirements 3.3**

- [x] 8. 报表 API 测试基础设施修复
  - [x] 8.1 修复 test_report_engine.py 测试基础设施
    - 确保测试路径与生产路由定义一致
    - 使用 override_auth 模式统一注入 get_current_user 和 get_db
    - 通过 fixture 预先 seed report_config 数据
    - 通过 `app.dependency_overrides` mock prerequisite_checker 绕过前置检查
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 8.2 编写报表 API 端点集成测试
    - 新建或扩展 `backend/tests/test_report_api_infrastructure.py`
    - 验证 GET /api/reports/{project_id}/{year}/{report_type} 路径可达（非 404）
    - 验证 POST /api/reports/generate 正确注入依赖
    - 使用 override_auth + in-memory SQLite
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 9. 跨标准一致性验证
  - [ ]* 9.1 编写 Property 9: Cross-standard row count consistency
    - 在 `backend/tests/test_report_config_consistency.py` 中添加
    - 从 report_config_seed.json 加载数据，比较 4 个标准的 balance_sheet 和 income_statement 行次数量
    - 验证任意两个标准的行次数量差异不超过 20%（max_count / min_count <= 1.2）
    - 数据驱动测试（非随机）
    - **Property 9: Cross-standard row count consistency**
    - **Validates: Requirements 7.4, 7.5**
    - _Requirements: 7.4, 7.5_

  - [ ]* 9.2 编写 Property 10: Cross-standard shared rows produce same results
    - 在同一文件中添加
    - 找出 soe_consolidated 和 listed_consolidated 中相同 row_code + 相同 formula 的行
    - 使用相同试算表数据执行公式，验证结果一致
    - 使用 hypothesis 生成随机试算表数据
    - `@settings(max_examples=15)`
    - **Property 10: Cross-standard shared rows produce same results**
    - **Validates: Requirements 7.3**
    - _Requirements: 7.3_

- [x] 10. Final checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 所有 hypothesis 属性测试使用 `max_examples=15`（项目约定，保证速度）
- 测试使用现有模式：override_auth、in-memory SQLite、AsyncMock
- 使用 `python`（非 `python3`）执行命令，命令间用 `;` 分隔（非 `&&`）
- pytest 超时设为 120000ms
- 仅修改后端代码：backend/app/、backend/tests/、backend/data/、backend/scripts/
