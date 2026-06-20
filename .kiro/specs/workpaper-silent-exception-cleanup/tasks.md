# 实施计划：底稿模块静默吞异常治理（P1）

## 概述

为 70 处宽异常静默 handler 补分级日志（行为零变更），并新增 CI 守卫防回归。按文件组分批，每组完成即可跑测试。语言：Python。

## Tasks

- [x] 1. 先建守卫测试（红灯起步）
  - [x] 1.1 创建 `backend/tests/test_wp_silent_exception_guard.py`
    - ast 扫描底稿 service + router + wp_render_strategies
    - 检测宽异常（裸 except / Exception / BaseException）+ body 纯 pass/return 空 + 无 logger
    - `_SILENT_EXCEPTION_WHITELIST` 初始为空
    - 断言违规⊆白名单，失败打印 文件:行号
    - 此时预期红灯（70 违规），确认扫描器准确
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 2. A 组：底稿主 router `working_paper.py`（9 处）
  - [x] 2.1 为 9 处补日志：后台 task/commit/rollback 用 warning，入参校验类用 debug
    - 行 376/430/434/532/598/760/1108/1242/1304
    - _Requirements: 1.1, 1.3, 1.4_

- [x] 3. B 组：模板/网格 service（16 处）
  - [x] 3.1 `wp_template_init_service.py`(4)：rollback/写入 warning，样式/批注 debug
  - [x] 3.2 `wp_grid_extract.py`(4)：均在逐 cell 提取，用 debug
  - [x] 3.3 `wp_template_xlsx.py`(5)：条件格式/数据验证/图片/字体提取 debug
  - [x] 3.4 `wp_xlsx_export_service.py`(1) + `wp_structure_bridge.py`(1) + `wp_header_service.py`(1)：IO/结构加载 warning，维度计算 debug
    - _Requirements: 1.1, 1.2, 1.5_

- [x] 4. C+D 组：交叉核对 + 离线导入导出（8 处）
  - [x] 4.1 `wp_cross_check_service.py`(4)：TB 取数/规则加载 return 空 → warning；token 解析 debug
  - [x] 4.2 `wp_audit_trail_service.py`(1)：轨迹查询 return [] → warning
  - [x] 4.3 `wp_offline_export_service.py`(2) + `wp_offline_import_service.py`(1)：parsed_data/sheet 解析 → warning
    - _Requirements: 1.1, 1.3_

- [x] 5. E 组：各循环计算 router D~N（18 处）
  - [x] 5.1 统一处理 18 个 `wp_{f2,g,h,i,j,k,l,m,n}_*.py`
    - `UUID(wp_id)` 解析失败 return None → debug（入参校验）
    - 取数 return-empty → warning
    - _Requirements: 1.1, 1.3_

- [x] 6. F+G+H 组：render 链路 + 其它 router + 填充/下载（18 处）
  - [x] 6.1 F: `wp_render_config.py`(4) + `wp_render_strategies/_a_program.py`(1)：schema 加载/auto-fill/年度查询 → warning（不拆文件，仅加行）
  - [x] 6.2 G: 10 个其它 router：缓存失效/库加载 warning，LLM 降级 debug
  - [x] 6.3 H: `workpaper_fill_service.py`(1) + `wp_download_service.py`(1) + `wp_generic_processor.py`(1)
    - _Requirements: 1.1, 1.2_

- [x] 7. 守卫转绿 + 零回归验证
  - [x] 7.1 跑 `test_wp_silent_exception_guard.py` 确认违规=0（绿灯）
  - [x] 7.2 跑 `test_render_config_smoke.py`(1096) + `test_auto_data_resolvers.py`(28) + pass2 核心(26) 确认零回归
  - [x] 7.3 `python -c "from app.main import app; print(len(app.routes))"` 确认导入无误、路由数 1522 不变
    - _Requirements: 2.1, 2.2, 2.3, 3.1_

- [x] 8. 最终检查点
  - 全部 70 处留痕、守卫绿、零回归。如有问题向用户确认。

## Notes

- 每处仅新增日志行 + 必要时 `except Exception as e:`，严禁改 return/pass 后语义
- 高频循环内一律 debug 防日志洪泛
- 已达标的 render/classification/template 链路只加日志不拆分
- 分组顺序按影响面从大到小，可分批原子提交
