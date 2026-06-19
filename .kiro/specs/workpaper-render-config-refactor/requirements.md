# 底稿渲染配置重构

## 变更记录

| 版本 | 日期 | 摘要 | 触发 |
|------|------|------|------|
| v1.0 | 2026-06-19 | 初始版本 | codegraph 分析 P0~P3 |

## 背景

A~S 全循环底稿开发完成后（568 任务/3553 测试），底稿渲染入口 `wp_render_config.py` 膨胀到 1474 行，`get_render_config` 单函数 475 行含 7 个 componentType 分支。同时存在重复函数、残留死代码、未覆盖测试等技术债。本 spec 做代码健康度治理，不加新功能。

## 现状量化（2026-06-19 codegraph 实测）

| 指标 | 当前值 | 目标 |
|------|--------|------|
| wp_render_config.py 总行数 | 1474 | ≤800（拆出 ~700 行到策略文件） |
| get_render_config 函数体 | 475 行 | ≤120 行（dispatch+公共逻辑） |
| componentType 分支数 | 7 个 if/elif | 0（策略 dict dispatch） |
| _resolve_legacy_source 残留 | 1 个分支 | 0（迁入 registry 后删） |
| derive_component_type 重复实现 | 2 份（scripts/service） | 1 份共享 |
| cycle_linkage_handlers 测试 | 0 | ≥3 个集成测试 |
| _WP_CODE_OVERRIDE 分组注释 | 0 | 按循环分区域 |

## 需求

### Req-1 策略模式拆分（P0）

`get_render_config` 的 7 个 componentType 分支拆为独立策略函数/文件：

- `_render_b_index` → B-Index 自动生成
- `_render_a_program` → A-程序表中控台
- `_render_audit_sheet` → 审定表 TB 取数
- `_render_checklist` → 核对表模板+响应
- `_render_analytical_review` → 分析性复核取数
- `_render_c_note` → C-附注披露兜底网格
- `_render_univer_grid` → Univer 网格提取

每个策略函数接收统一上下文 dataclass，返回 `sheet_html_data`。主函数只做 classification 解析 + dispatch。

验收准则：
- get_render_config 函数体 ≤120 行
- 1096 render-config 冒烟测试全绿（零回归）
- 新增策略函数各有独立单元测试

### Req-2 联动 Handler 集成测试（P1）

为 `event_handlers_cycle_linkage.py` 的 5 个 handler 补集成测试：
- `_on_c_control_test_saved`：发送 WORKPAPER_SAVED + wp_code=C2-1 → 验证 field_overrides 写入
- `_on_d_audit_determination_saved`：发送 WORKPAPER_SAVED + wp_code=D1-1 + rows → 验证 trial_balance.audited_amount 回写
- `_on_f_workpaper_conclusion_saved`：验证 field_overrides scope=f_procedure_status 写入

验收准则：≥3 个 pytest 集成测试（mock DB session，真调 handler 函数）

### Req-3 Legacy Resolver 清理（P1）

`_resolve_legacy_source` 的 `control_deficiency_count` 迁入 `_REGISTRY`，然后删除整个 `_resolve_legacy_source` 方法和 fallback 调用路径。

验收准则：
- `_REGISTRY` 从 51→52 条
- `_resolve_legacy_source` 方法不再存在
- 25 auto_data_resolvers 测试全绿

### Req-4 derive_component_type 单一真源（P2）

`generate_wp_render_schema.py:215` 的 `derive_component_type(class_code: str)` 和 `wp_classification_service.py:1368` 的 `derive_component_type(classification: ClassificationResult)` 抽共享核心：

```python
def _class_code_to_component(class_code: str) -> str | None:
    """纯函数：class_code → componentType，None 表示未匹配"""
```

两处调用方各自包装（scripts 版 fallback "univer"，service 版抛异常）。

验收准则：grep `def derive_component_type` 只有 2 处（各自 wrapper），核心映射逻辑只有 1 份

### Req-5 _WP_CODE_OVERRIDE 分组（P3）

910 条映射按循环分区域注释：

```python
# ═══ A 循环（完成阶段）═══════════════════════
"A1": "a-program-console",
...
# ═══ B 循环（计划了解）═══════════════════════
"B1": "a-program-console",
...
```

或拆为 `_A_OVERRIDES`/`_B_OVERRIDES`/.../`_S_OVERRIDES` 合并 dict。

验收准则：每个循环有可定位的区域标识（注释或子 dict 名）

## 非目标（不做）

- 不改 componentType 语义
- 不加新底稿类型
- 不改前端组件
- 不改 render-config API 响应结构
