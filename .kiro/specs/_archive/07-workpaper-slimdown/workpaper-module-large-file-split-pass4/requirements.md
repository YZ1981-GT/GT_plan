# 需求文档：底稿模块大文件拆分 pass4（P1）

## 简介

pass3 已将 router/service 三大主干（working_paper/workpaper_fill_service/auto_data_resolvers）降到 ≤800 行。复查发现底稿模块仍有 3 个**服务层**文件超 800 行红线（`backend/scripts/check/check_file_size.py`）：

| 文件 | 当前行数 | 性质 |
|------|---------|------|
| `backend/app/services/wp_template_init_service.py` | 1208 | 纯函数集合（模板查找 + 初始化/预填 + xlsx 单元格 helper） |
| `backend/app/services/wp_standard_conversion_service.py` | 934 | 单一 class `WpStandardConversionService`（分类/预览/转换/生成） |
| `backend/app/services/wp_fine_rule_engine.py` | 892 | 纯函数（规则加载 + 网格/工作表提取 + 审计检查） |

这些是底稿模板初始化、新旧准则转换、精细规则提取的主干服务。文件越大改动面越广、合并冲突越频繁、定位越慢。

本 spec 延续 pass2/pass3 验证过的拆分模式（按内聚边界拆到子包/子模块），将 3 文件全部降到 **≤800 行**，**行为零变更、对外入口不变**，并以测试 + 文件大小守卫防回归。

### 严格约束（沿用 pass3 铁律）

- **不动已达标文件**：pass2/pass3 已瘦身的 render/classification/template_files/strategies/working_paper/wp_fill/auto_data_resolvers 等**一律不动**。
- **不过度拆分**：每文件拆到 ≤800 即止，按"职责/域"内聚拆，不机械按行数切割。
- **零行为变更**：纯结构调整，不改任何函数签名、对外入口、SQL、xlsx 提取逻辑。
- **本轮不含 `workpaper_models.py`**：ORM 拆分循环导入风险高、收益低（仅略超 800），留待后续单独评估。

## 需求

### 需求 1：`wp_template_init_service.py` 按职责拆分（≤800 行）

**用户故事：** 作为维护者，我希望模板初始化服务按"模板查找/初始化预填/xlsx 单元格操作"三类职责拆到子模块，便于定位。

#### 验收准则

1. WHEN 拆分完成 THEN `wp_template_init_service.py` SHALL ≤800 行
2. WHERE 函数按职责分组 THEN SHALL 拆出子模块（如 `_template_finder.py` 模板查找 find_*/`_xlsx_cell_ops.py` 单元格 helper _find_*/_mark_*/_extract_*），主文件保留 init/prefill 主流程
3. WHEN 拆分后 THEN 全部对外公开函数（`init_workpaper_from_template`/`prefill_workpaper_xlsx`/`find_template_file*`/`get_workpaper_file`/`list_available_templates` 等）的导入路径 SHALL 保持不变（主文件 re-export 或调用方无需改）
4. WHEN 拆分完成 THEN 涉及本服务的现有测试 SHALL 全部通过

### 需求 2：`wp_standard_conversion_service.py` 按职责拆分（≤800 行）

**用户故事：** 作为维护者，我希望准则转换服务的大 class 按"分类/转换执行/底稿生成"职责拆分，降低单 class 复杂度。

#### 验收准则

1. WHEN 拆分完成 THEN `wp_standard_conversion_service.py` SHALL ≤800 行
2. WHERE 职责分组 THEN SHALL 按职责拆分（如底稿生成 `_generate_one_workpaper`/`_copy_template_file`/`_populate_parsed_data`/`_load_template_library` 抽到独立模块或 mixin），class `WpStandardConversionService` 对外方法保持挂在实例上
3. WHEN 拆分后 THEN `WpStandardConversionService` 对外公开方法（`classify_workpapers`/`preview_conversion`/`convert_workpapers`/`check_preconditions`）的调用方 SHALL 无需修改
4. WHEN 拆分完成 THEN 涉及本服务的现有测试 SHALL 全部通过

### 需求 3：`wp_fine_rule_engine.py` 按职责拆分（≤800 行）

**用户故事：** 作为维护者，我希望精细规则引擎按"规则加载/数据提取/审计检查"拆分，便于扩展新规则与检查项。

#### 验收准则

1. WHEN 拆分完成 THEN `wp_fine_rule_engine.py` SHALL ≤800 行
2. WHERE 函数按职责分组 THEN SHALL 拆出子模块（如 `_audit_checks.py` 审计检查 _run_audit_checks/_check_*/`_grid_extract.py` 网格提取 _extract_*_grid），主文件保留 load_fine_rule/list_fine_rules/extract_with_fine_rule 主入口
3. WHEN 拆分后 THEN 对外公开函数（`load_fine_rule`/`list_fine_rules`/`extract_with_fine_rule`）的导入路径 SHALL 保持不变
4. WHEN 拆分完成 THEN 涉及本服务的现有测试 SHALL 全部通过

### 需求 4：全程零回归 + 文件大小守卫

**用户故事：** 作为维护者，我希望这次纯结构拆分不破坏任何功能，并防止未来再超标。

#### 验收准则

1. WHEN 全部拆分完成 THEN `check_file_size.py` 对这 3 个文件 SHALL 不再报超限
2. WHEN 全部拆分完成 THEN 复用 pass3 守卫 `test_wp_large_file_size_guard.py`（新增对这 3 文件 ≤800 的断言）SHALL 全绿
3. WHEN 全部拆分完成 THEN 底稿主链路测试（`test_render_config_smoke.py` + 模板/转换/精细规则相关测试 + pass2/pass3 核心）SHALL 全部通过
4. WHEN 全部拆分完成 THEN `app.main` 导入无误、路由总数 1522 不变
5. WHERE 拆分触及 import THEN SHALL 用 codegraph 核对全部调用点，无遗漏、无循环导入
6. WHEN 拆分完成 THEN 已达标的 pass2/pass3 文件行数 SHALL 保持不变（未被误拆）
