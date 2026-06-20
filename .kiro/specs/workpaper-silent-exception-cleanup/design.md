# 设计文档：底稿模块静默吞异常治理（P1）

## 概述

对底稿模块 **70 处宽异常静默 handler** 逐一补分级日志，行为零变更。同时新增一个 CI 守卫测试防止回归。本质是一次"触类旁通"的留痕整改，不改控制流、不改返回值、不拆文件。

## 影响面（实测，2026-06-20 AST 扫描）

70 处分布在约 30 个文件，按所属层与循环归组：

| 组 | 文件 | 处数 | 典型场景 |
|----|------|------|----------|
| A. 底稿主 router | `working_paper.py` | 9 | 后台 auto-parse task、commit、rollback 吞掉 |
| B. 模板/网格 service | `wp_template_init_service.py`(4) `wp_grid_extract.py`(4) `wp_template_xlsx.py`(5) `wp_xlsx_export_service.py`(1) `wp_structure_bridge.py`(1) `wp_header_service.py`(1) | 16 | xlsx 样式/批注/维度/条件格式提取、结构桥接 |
| C. 交叉核对/审计轨迹 | `wp_cross_check_service.py`(4) `wp_audit_trail_service.py`(1) | 5 | TB 取数、token 解析、规则加载吞掉返回空 |
| D. 离线导入导出 | `wp_offline_export_service.py`(2) `wp_offline_import_service.py`(1) | 3 | parsed_data 提取、sheet 解析吞掉 |
| E. 各循环计算 router（D~N） | `wp_f2_impairment/wp_f2_valuation/wp_g_classification/wp_g_ecl/wp_g_fair_value/wp_h_depreciation/wp_h_impairment/wp_i_amortization/wp_i_capitalization/wp_i_goodwill/wp_j_payroll_calc/wp_j_share_payment/wp_k_expense_analysis/wp_k_impairment_summary/wp_l_bond_amortization/wp_l_interest_calc/wp_m_equity_movement/wp_n_income_tax_calc` 各 1 | 18 | `UUID(wp_id)` 解析失败 return None / 取数 return-empty |
| F. render 链路 | `wp_render_config.py`(4) `wp_render_strategies/_a_program.py`(1) | 5 | schema 加载、auto-fill、年度查询吞掉 |
| G. 其它 router | `wp_business_pattern/wp_export_import_router/wp_fine_rules/wp_guidance_chat/wp_health_dashboard/wp_mapping/wp_prerequisite_status/wp_search/wp_structure/wp_template` 各 1 | 10 | 缓存失效、LLM 降级、库加载吞掉 |
| H. 填充/下载/通用 | `workpaper_fill_service.py`(1) `wp_download_service.py`(1) `wp_generic_processor.py`(1) | 3 | TSJ prompt 回退、task 状态更新、规则缓存 |
| **合计** | **~30 文件** | **70** | |

> 注：F 组 render 链路虽在 pass2 已瘦身，但本 spec 只**加日志行**，不拆文件、不改结构，符合"800 行以下链路别再拆"约束。

## 日志分级规则

| 副作用类型 | 级别 | 理由 |
|-----------|------|------|
| DB 查询/写入/commit/rollback 吞掉 | `warning` | 影响数据正确性，必须可见 |
| 联动事件发布/缓存失效吞掉 | `warning` | 影响联动链路 |
| 模板文件 IO 加载/解析吞掉 | `warning` | 影响渲染数据来源 |
| 取数函数 return 空（cross_check/offline） | `warning` | 前端无法区分真空/故障 |
| `UUID(wp_id)` 解析失败 return None | `debug` | 入参非法属预期校验，低价值 |
| cell 样式/字体/颜色/批注/维度提取（常在逐 cell 循环内） | `debug` | 装饰性、高频、不影响数据 |
| LLM 不可用降级到规则文本 | `debug` | 已有显式降级路径，预期内 |

消息格式统一：`logger.warning("<操作中文描述>失败: %s", e)`，循环内或装饰性用 `logger.debug`。需捕获异常对象时 handler 改为 `except Exception as e:`（原先无 `as e` 的补上）。

## 守卫测试设计

新建 `backend/tests/test_wp_silent_exception_guard.py`：

```
扫描目录: backend/app/services/{wp_*,workpaper_*,auto_data_resolvers}.py
         backend/app/routers/{wp_*.py, working_paper.py, wp_render_strategies/*.py}
用 ast 遍历所有 ExceptHandler:
  - 仅检查"宽异常": type 为 None(裸) / Name=='Exception' / 'BaseException'
  - body 为纯 pass 或 return 空(None/{}/[]/""/0)
  - handler 内 ast.walk 无 logger.* 调用
  → 违规
排除: _SILENT_EXCEPTION_WHITELIST = {(相对路径, 函数名或行特征)} 含理由注释
断言: 违规集合 ⊆ 白名单, 否则 fail 并打印 文件:行号
```

白名单初始为空（70 处全部整改），保留机制供未来极少数确需静默的场景。

## 测试与验证策略

- 整改后跑 `test_render_config_smoke.py`(1096) + `test_auto_data_resolvers.py`(28) + pass2 核心(26) 确认零回归
- `python -c "from app.main import app"` 确认导入无误、路由数仍 1522
- 新守卫测试自身通过（违规=0）

## 不做的事

- 不改任何 handler 的返回值/控制流
- 不拆分任何文件（含已达标的 render/classification/template 链路）
- 不动 18 处窄类型异常降级
- 不引入新依赖
