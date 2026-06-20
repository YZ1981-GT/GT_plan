# 实施计划：底稿模块大文件拆分（P0 / pass3）

## 概述

3 个超标文件按内聚边界拆到 ≤800 行，零行为变更。每个文件独立 Sprint，互不阻塞，每 Sprint 末验证零回归。语言：Python（FastAPI + SQLAlchemy + pytest）。

## Tasks

- [x] 1. 先建文件大小守卫测试（红灯起步）
  - [x] 1.1 创建 `backend/tests/test_wp_large_file_size_guard.py`
    - 断言 3 个目标文件（`working_paper.py`/`workpaper_fill_service.py`/`auto_data_resolvers.py` 或其包 `__init__.py`）≤800 行
    - 同时断言 pass2 已达标文件（render_config/classification/template_files）行数未回升超 800
    - 此时预期红灯（3 文件超标），确认守卫准确
    - _Requirements: 4.1, 4.5_

- [x] 2. Sprint A：`auto_data_resolvers.py` → 域子包（Req 1）
  - [x] 2.1 建包骨架 `auto_data_resolvers/__init__.py`
    - 将同名模块转为包；`__init__.py` 保留 `auto_resolver` 装饰器、`_REGISTRY`、`resolve_auto_data_source`、`get_registered_sources`、`_inc_resolver_failure`/`get_resolver_failure_counts`
    - _Requirements: 1.1, 1.2_
  - [x] 2.2 迁移 resolver 到 6 个域子模块
    - `_adjustments.py`/`_consol.py`/`_control_b.py`/`_cycle.py`/`_completion.py`/`_tax_income.py`（分组见 design）
    - 每个 resolver 的 `@auto_resolver("source_name")` 名**逐字不变**；共享 helper 就近放置或入 `_shared.py`
    - _Requirements: 1.2, 1.3_
  - [x] 2.3 `__init__.py` 末尾导入全部子模块触发注册
    - `from . import _adjustments, _consol, _control_b, _cycle, _completion, _tax_income`
    - _Requirements: 1.4_
  - [x] 2.4 修复 `test_k_cycle_special_procedures.py` 的 `inspect.getsource` 断言
    - 原断言查模块源码文本 → 改为查 `get_registered_sources()` 含目标 source（不依赖源码在单文件）
    - _Requirements: 1.5_
  - [x] 2.5 验证 Sprint A 零回归
    - `auto_data_resolvers/__init__.py` 97 行；`get_registered_sources()` 51 source 与拆分前快照完全相同
    - 跑 442 测试全绿（auto_data 28 + resolver_mock + 各 cycle 注册）
    - _Requirements: 1.5, 4.2_

- [x] 3. Sprint A 检查点
  - resolver registry 完整(51)、442 测试通过。

- [x] 4. Sprint B：`workpaper_fill_service.py` → Mixin 组合（Req 3）
  - [x] 4.1 建 `wp_fill/` 包 + 5 个 Mixin 文件
    - `_fill_task.py`/`_analytical_review.py`/`_data_gen.py`/`_note_draft.py`/`_review_prompt.py`（分组见 design）
    - 每个 Mixin 为普通 class，方法含 `self`，逐字搬运方法体
    - _Requirements: 3.2_
  - [x] 4.2 主文件改为 Mixin 组合
    - `class WorkpaperFillService(FillTaskMixin, AnalyticalReviewMixin, DataGenMixin, NoteDraftMixin, ReviewPromptMixin)`，保留 `__init__`
    - 确认 `self.db` 等实例属性在 mixin 内可正常访问
    - _Requirements: 3.1, 3.3_
  - [x] 4.3 验证 Sprint B 零回归
    - `workpaper_fill_service.py` ≤800 行；`test_workpaper_fill.py` + `test_ai_services.py`（`service._method` 访问）全通过
    - _Requirements: 3.1, 3.4, 4.2_

- [x] 5. Sprint B 检查点
  - 确保 WorkpaperFillService 对外方法零变更、相关测试通过，如有问题向用户确认。

- [x] 6. Sprint C：`working_paper.py` → 功能域子 router（Req 2）
  - [x] 6.1 共享请求模型与 helper 归位
    - `UploadRequest`/`StatusUpdateRequest`/`AssignRequest`/`ReviewStatusRequest` 移 `schemas/` 或主文件保留供子 router import
    - _Requirements: 2.4_
  - [x] 6.2 拆出 `wp_editor_router.py`
    - online_edit_session/univer_data(get/save)/onlyoffice_config/prefill/parse/export_pdf/sign_status + `_prefill_word_template`
    - _Requirements: 2.2_
  - [x] 6.3 拆出 `wp_review_router.py`（复核+分配）
    - assign_workpaper（+ `_send_reassignment_notifications` 同模块）/submit_review/update_review_status
    - _Requirements: 2.2_
  - [x] 6.4 拆出 `wp_batch_router.py` + `wp_relation_router.py`
    - batch: kanban/batch_assign/batch_submit/batch_export/edit_time
    - relation: list_wp_index/cross_refs/cross_links/relation_graph/sync_procedure_status
    - _Requirements: 2.2_
  - [x] 6.5 在 `router_registry/workpaper.py` 注册 4 个子 router
    - 同前缀 include_router；确认静态路径在通配前
    - _Requirements: 2.3_
  - [x] 6.6 验证 Sprint C 零回归
    - `working_paper.py` ≤800 行；`app.main` 导入无误、路由总数 1522 不变；端点 (path,method) 全集不变；`test_router_registry_completeness.py` 通过
    - _Requirements: 2.1, 2.3, 2.5, 4.3_

- [x] 7. Sprint C 检查点
  - 确保端点全集不变、registry 完整，如有问题向用户确认。

- [x] 8. 终验：守卫转绿 + 全量零回归
  - [x] 8.1 `test_wp_large_file_size_guard.py` 全绿（3 文件 ≤800 且 pass2 文件未回升）
  - [x] 8.2 跑 `test_render_config_smoke.py`(1096) + `test_auto_data_resolvers.py`(28) + `test_wp_silent_exception_guard.py` + pass2 核心 + workpaper_fill/router registry
  - [x] 8.3 `python -c "from app.main import app; print(len(app.routes))"` = 1522
  - [x] 8.4 codegraph 核对无循环导入、无遗漏调用点
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 9. 最终检查点
  - 3 文件全部 ≤800、守卫绿、零回归、端点/source 全集不变。如有问题向用户确认。

## Notes

- 三个 Sprint 互不阻塞，可独立提交；每 Sprint 末必验证零回归
- **铁律**：source 名/端点路径/方法签名逐字不变；mixin 保方法挂实例上（测试 `service._x()` 依赖）
- **绝不动** pass2 已达标文件（render_config/classification/template/strategies/xlsx/docx）
- 转包时注意 `app.services.auto_data_resolvers` 导入路径不变（模块→包同名）
- 每文件 ≤800 即停，不过度碎片化
