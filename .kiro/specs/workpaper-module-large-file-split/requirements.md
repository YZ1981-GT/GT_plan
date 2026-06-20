# 需求文档：底稿模块大文件拆分（P0 / pass3）

## 简介

底稿模块仍有 3 个核心文件远超项目 800 行红线（`backend/scripts/check/check_file_size.py`）：

| 文件 | 当前行数 | 性质 |
|------|---------|------|
| `backend/app/routers/working_paper.py` | 1937 | 底稿主 router（~30 端点 + 4 请求模型 + 4 私有 helper） |
| `backend/app/services/workpaper_fill_service.py` | 1819 | 单一巨型 class `WorkpaperFillService`（~45 方法，5 大职责） |
| `backend/app/services/auto_data_resolvers.py` | 1626 | 注册表模式（~55 个 `@auto_resolver`，按审计循环/主题分组） |

这些是底稿读写、AI 填充、联动取数的主干。文件越大，改动面越广、合并冲突越频繁、新人定位越慢，且在 6000 并发演进中持续放大风险。

本 spec 延续 pass2 已验证的拆分模式（router 子包 + service 抽取 + registry 子模块），将 3 文件全部降到 **≤800 行**，**行为零变更、端点路径不变、注册表 source 名不变**，并以测试 + 文件大小守卫防回归。

### 严格约束（用户明确要求）

- **已达标链路绝不重拆**：`wp_render_config.py`(747)、`wp_classification_service.py`(310)、`wp_template_files.py`(301) 及 `wp_render_strategies/`、`wp_template_xlsx/docx.py` 等 pass2 已瘦身文件**一律不动**。
- **不过度拆分**：每个文件拆到 ≤800 即可，不为追求更小而制造碎片化跳转。优先按"职责/域"内聚拆分，不机械按行数切割。
- **零行为变更**：拆分纯结构调整，不改任何端点路径、请求/响应契约、resolver source 名、SQL 逻辑。

## 需求

### 需求 1：`auto_data_resolvers.py` 按域拆分（≤800 行）

**用户故事：** 作为维护者，我希望 55 个 resolver 按审计循环/主题分组到子模块，便于定位和并行编辑。

#### 验收准则

1. WHEN 拆分完成 THEN `auto_data_resolvers.py` 主文件 SHALL ≤800 行，仅保留：装饰器 `auto_resolver`、注册表 `_REGISTRY`、`resolve_auto_data_source`、`get_registered_sources`、失败计数器、子模块导入触发
2. WHEN resolver 迁入子模块 THEN 每个 resolver 的 `@auto_resolver("source_name")` 注册 source 名 SHALL 与拆分前**完全一致**
3. WHERE resolver 按域分组 THEN SHALL 建立 `auto_data_resolvers/` 包，按主题分文件（如 `_adjustments.py` 调整分录、`_consol.py` 合并、`_control_b.py` B 控制了解、`_cycle.py` D~N 循环、`_completion.py` 完成度、`_tax_income.py` 税费收入）
4. WHEN 应用启动 THEN 全部子模块 SHALL 被导入以触发装饰器注册（registry 完整性不丢失）
5. WHEN 拆分完成 THEN `test_auto_data_resolvers.py`(28) + resolver docstring PBT SHALL 全部通过，`get_registered_sources()` 返回的 source 集合与拆分前**完全相同**

### 需求 2：`working_paper.py` 按功能域拆分（≤800 行）

**用户故事：** 作为维护者，我希望底稿 router 按功能域（CRUD/编辑/复核/批量/关系）拆到子模块，主文件保持核心 CRUD。

#### 验收准则

1. WHEN 拆分完成 THEN `working_paper.py` SHALL ≤800 行
2. WHERE 端点按域分组 THEN SHALL 拆出子 router 模块（如 `wp_editor_router.py` 在线编辑/univer 保存/onlyoffice、`wp_review_router.py` 复核流转/提交/签字、`wp_batch_router.py` 批量分配/提交/导出/看板、`wp_relation_router.py` 交叉引用/关系图/穿透）
3. WHEN 子 router 创建 THEN SHALL 在 `router_registry/workpaper.py` 注册，且所有端点 (path, method) 集合与拆分前**完全一致**
4. WHEN 拆分完成 THEN 共享的请求模型（`UploadRequest` 等）和私有 helper SHALL 放在合理位置（共享模型可入 schemas，helper 随主用例迁移），无重复定义
5. WHEN 拆分完成 THEN `app.main` 导入无误、路由总数不变、`test_router_registry_completeness.py` 通过

### 需求 3：`workpaper_fill_service.py` 按职责拆分（≤800 行）

**用户故事：** 作为维护者，我希望巨型 `WorkpaperFillService` 按职责（AI 填充任务/分析复核/数据生成/附注草稿/AI 复核）拆分，降低单 class 复杂度。

#### 验收准则

1. WHEN 拆分完成 THEN `workpaper_fill_service.py` SHALL ≤800 行
2. WHERE 职责分组 THEN SHALL 按以下职责拆分到独立 service 或 mixin：AI 填充任务（create/execute/fill_*）、分析复核（generate_analytical_review + TB/交易/辅助取数）、底稿数据生成（generate_workpaper_data + tb/inventory/confirmation）、附注草稿（generate_note_draft）、AI 复核（review_workpaper_with_prompt/load_review_prompt）
3. WHEN 拆分后 THEN `WorkpaperFillService` 对外公开方法的调用方 SHALL 无需修改（保持向后兼容的入口，或同步更新全部调用点）
4. WHEN 拆分完成 THEN 涉及 `workpaper_fill_service` 的现有测试 SHALL 全部通过

### 需求 4：全程零回归 + 文件大小守卫

**用户故事：** 作为维护者，我希望这次纯结构拆分不破坏任何功能，并防止未来再超标。

#### 验收准则

1. WHEN 全部拆分完成 THEN `check_file_size.py` 对这 3 个文件 SHALL 不再报超限
2. WHEN 全部拆分完成 THEN 底稿主链路测试（`test_render_config_smoke.py` 1096 + `test_auto_data_resolvers.py` 28 + pass2 核心 + silent-cleanup 守卫）SHALL 全部通过
3. WHEN 全部拆分完成 THEN `app.main` 导入无误、路由总数 1522 不变
4. WHERE 拆分触及 import THEN SHALL 用 codegraph 核对全部调用点，无遗漏、无循环导入
5. WHEN 拆分完成 THEN 已达标的 render/classification/template 链路文件行数 SHALL 保持不变（未被误拆）
