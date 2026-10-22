# 公式管理深度优化 — design.md

> spec: `formula-management-deep-optimization`
> 依赖: `formula_push/` · `formula_settings/` · `formula_management/` · `formula_engine.py` · `report_engine.py`
> 最高迁移: V201（本 spec 无新 DDL 迁移——全部复用现有表结构）

## §1 现状 grep 确认

### 1.1 推送跳过项（R1）
- `find_row` 定义于 `formula_push/note_writer.py:405`，三级匹配：精确→去"小计"后缀→包含（唯一命中）
- `FALLBACK_TO_TOTAL` 定义于 `results.py:16`，engine.py L714/L763 使用
- 真库棘轮：`_MAX_SKIPPED=85` / `_MIN_COVERAGE=295`（`test_formula_push_note_skip_pg.py`）
- 跳过原因：附注表中没有目标行名（公式推送不新建行）

### 1.2 健康度总览（R2）
- 覆盖率已有：`formula_push/coverage.py` 的 `compute()` 纯函数
- 过期汇总已有：`stale_summary_aggregate.py`
- 待确认查询已有：`formula_settings/pending.py`
- 公式配置率需新算：报表行有公式比例从 `report_config` 表算
- **无现有聚合端点**——需新建

### 1.3 调试模拟器（R3）
- `formula_engine.execute(formula, ctx) → FormulaResult`，FormulaResult 含 `.trace` 列表
- `FormulaContext` 可从 `from_simple_map(tb_data, row_cache, ...)` 构造轻量上下文
- `FormulaEditDialog.vue` 无现有「调试」按钮
- **需新增端点 + 前端调试面板**

### 1.4 表间审核（R4）
- `cross_check_rules._evaluate` 调 `evaluate_formula_result`（`report_engine.py:822`）
- `evaluate_formula_result` 对 PREV 硬替换 `"0"`（L872-877 `_PREV_PATTERN.finditer → replace("0")` ）
- AUX 同理硬替换 `"0"`
- `function_support_matrix.py` 确认 PREV/AUX 在 `report_path` 为 `False`
- **扩展需在 evaluate_formula_result 中对 PREV/AUX 预载数据而非硬置 0**

### 1.5 反向校验（R5）
- `FormulaPushState` 存于 `formula_push_states` 表（engine.py `_load_states` / `_save_states`）
- `PushItem` 含 rule_id/stage/domain/addr_id/action/reason/old_value/new_value
- `FormulaPushPanel.vue` 已有差异展示（pending diffs）
- **需新增反向校验端点 + 面板按钮**

### 1.6 版本时间轴（R6）
- 公式审计日志：`audit_log_entries WHERE action_type='formula.changed'`（`formula_audit_log.py` 路由查询）
- 全局发布历史：`formula_publishes` 表（`formula_settings/publish.py` 的 `list_publishes`）
- 模板更新：`formula_template_versions` 表
- 推送触发：`formula_push_runs` 表（engine.py `_save_states`）
- **需聚合端点合并多表查询**

## §2 技术方案

### R1 推送跳过项收窄

**方案**：在 `find_row` 中增加第四级匹配——别名表查找。

```
find_row 匹配链：
  ① 精确匹配 → ② 去"小计"后缀 → ③ 包含匹配（唯一） → ④ 别名表映射 [新增]
```

**文件改动**：
1. `backend/data/formula_push_note_row_aliases.json` — 新增别名表
2. `backend/app/services/formula_push/note_writer.py` — `find_row` 增加第四级
3. `backend/tests/test_formula_push_note_skip.py` — 增加别名匹配测试

**别名表结构**：
```json
{
  "_schema_version": 1,
  "_description": "附注行标签别名映射：推送规则的 note_label 在附注表中可能有不同写法",
  "aliases": {
    "长期股权投资": ["长期股权投资—对子公司投资", "长期股权投资——对子公司投资"],
    "应交税费": ["应交税费—应交增值税", "应交税费—应交所得税"]
  }
}
```

**棘轮策略**：真库跑完新 find_row 后重定基线，`_MAX_SKIPPED` 只许下调。

### R2 项目级公式健康度总览

**方案**：新建 service + 路由 + 前端面板。

**后端**：
1. `backend/app/services/formula_health_service.py` — 聚合六维度指标
2. `backend/app/routers/formula_health.py` — `GET /api/formula-health/{project_id}/{year}`

**六维度计算**：
```python
async def compute_health(db, project_id, year):
    return {
        "push_coverage": await _push_coverage(),           # 复用 coverage.py
        "push_success_rate": await _last_run_stats(db, project_id, year),  # 查 formula_push_runs
        "formula_config_rate": await _config_coverage(db, project_id, year),  # 报表行有公式比例
        "pending_conflicts": await _pending_count(db, project_id),  # 查 FormulaSyncItem
        "cross_check_pass_rate": await _cross_check_stats(db, project_id, year),  # 查 cross_check_results
        "stale_ratio": await _stale_stats(db, project_id, year),  # 复用 stale_summary_aggregate
    }
```

**前端**：
1. `FormulaHealthPanel.vue` — 六维度卡片组 + 雷达图/仪表盘 + 按循环下钻
2. 嵌入 `FormulaDashboardDialog.vue` 新增 Tab 页「📊 项目健康度」

### R3 公式调试/模拟器

**方案**：新建调试端点 + 前端调试面板。

**后端**：
1. `backend/app/routers/formula_debug.py` — `POST /api/formula/debug`

```python
@router.post("/debug")
async def debug_formula(body: FormulaDebugRequest, db=Depends(get_db),
                        user=Depends(require_project_access("readonly"))):
    # 构造 FormulaContext（从 project_id/year 实时取数据快照）
    ctx = await build_debug_context(db, body.project_id, body.year, body.scope)
    result = execute(body.formula, ctx)
    return {
        "value": str(result.value) if result.value is not None else None,
        "ok": result.ok,
        "trace": result.trace,
        "errors": result.errors,
        "warnings": result.warnings,
    }
```

**前端**：
1. `FormulaDebugPanel.vue` — 调试面板（公式输入 + trace 树形展示 + 错误高亮）
2. 嵌入 `FormulaEditDialog.vue`：底部新增「▶ 调试运行」按钮，点击展开调试面板

**trace 树形可视化**：
```
TB("1001", "未审数") = 1,234,567.89
  ├─ 科目码: 1001
  ├─ 列名: 未审数
  └─ 取数结果: 1,234,567.89
+ ROW("1") = 500,000.00
  ├─ 行次: 1
  └─ 行值: 500,000.00
= 1,734,567.89
```

### R4 表间审核跨模块扩展

**方案**：在 `evaluate_formula_result` 中为 PREV/AUX 预载真实数据（而非硬置 0），
并在表间审核路径注入这些数据。

**后端改动**：
1. `backend/app/services/report_engine.py` — `evaluate_formula_result` 中 PREV/AUX 条件分支：
   - 新增可选参数 `enable_prev: bool = False` / `enable_aux: bool = False`
   - `enable_prev=True` 时通过 resolver 预载上期数据（而非 replace("0")）
   - `enable_aux=True` 时通过 resolver 预载辅助余额（而非 replace("0")）
2. `backend/app/services/formula_settings/cross_check_rules.py` — `_evaluate` 调用时传 `enable_prev=True, enable_aux=True`
3. `backend/app/services/formula_management/function_support_matrix.py` — 更新矩阵：PREV/AUX 在 `report_path` 改为条件支持

**前端改动**：
1. `FormulaCrossCheckPanel.vue` — 规则编辑器增加 PREV/AUX 函数按钮
2. 预置规则模板 JSON：常用跨模块审核规则

**风险控制**：`enable_prev/aux` 默认 `False`，现有报表求值路径零改动；
只有表间审核和调试端点显式传 True。`function_support_matrix.py` 对应更新。

### R5 推送反向校验

**方案**：新建校验端点，重新取源头值对比目标值。

**后端**：
1. `backend/app/services/formula_push/verify.py` — 反向校验逻辑
2. `backend/app/routers/formula_push_verify.py` — `GET /api/formula-push/{project_id}/{year}/verify`

```python
async def verify_push(db, project_id, year):
    states = await _load_states(db, project_id, year)
    results = []
    for addr, state in states.items():
        source_value = await _resolve_source(db, project_id, year, state.rule_id)
        target_value = await _read_target(db, project_id, state.addr_id)
        status = "consistent" if values_equal(source_value, target_value) else "diverged"
        results.append({
            "addr_id": addr, "source_value": source_value, "target_value": target_value,
            "status": status, "delta": target_value - source_value if both_numeric else None,
        })
    return results
```

**前端**：
1. `FormulaPushPanel.vue` 新增「🔄 反向校验」按钮 + 内嵌结果表格

### R6 公式版本时间轴

**方案**：聚合多数据源，返回统一时间轴。

**后端**：
1. `backend/app/services/formula_timeline_service.py` — 聚合查询
2. `backend/app/routers/formula_timeline.py` — `GET /api/formula-timeline/{project_id}/{year}`

**数据源合并**（按 timestamp 统一排序）：
```python
events = []
events += await _audit_log_events(db, project_id, year)   # formula.changed
events += await _publish_events(db)                         # formula_publishes
events += await _template_events(db, project_id)            # formula_template_versions
events += await _push_events(db, project_id, year)          # formula_push_runs
events += await _conflict_events(db, project_id)            # formula_sync_items
events.sort(key=lambda e: e["timestamp"], reverse=True)
```

**前端**：
1. `FormulaTimelinePanel.vue` — 时间轴组件
   - 竖向时间轴，按日期分组
   - 事件图标按类型着色（🔵发布 / 🟢推送 / 🟡修改 / 🔴冲突 / 🟣模板）
   - 点击事件展开详情（前值→后值 + 影响范围）
2. 嵌入 `FormulaManagerDialog.vue` 的历史 Tab 或独立 Tab

## §3 文件清单

### 新增文件
| 文件 | 说明 |
|------|------|
| `backend/data/formula_push_note_row_aliases.json` | R1 别名表 |
| `backend/app/services/formula_health_service.py` | R2 健康度聚合 |
| `backend/app/routers/formula_health.py` | R2 端点 |
| `backend/app/routers/formula_debug.py` | R3 调试端点 |
| `backend/app/services/formula_push/verify.py` | R5 反向校验 |
| `backend/app/routers/formula_push_verify.py` | R5 端点 |
| `backend/app/services/formula_timeline_service.py` | R6 时间轴聚合 |
| `backend/app/routers/formula_timeline.py` | R6 端点 |
| `frontend/src/components/formula/FormulaHealthPanel.vue` | R2 健康度面板 |
| `frontend/src/components/formula/FormulaDebugPanel.vue` | R3 调试面板 |
| `frontend/src/components/formula/FormulaTimelinePanel.vue` | R6 时间轴 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `backend/app/services/formula_push/note_writer.py` | R1 find_row 第四级 |
| `backend/app/services/report_engine.py` | R4 PREV/AUX 条件预载 |
| `backend/app/services/formula_settings/cross_check_rules.py` | R4 传 enable_prev/aux |
| `backend/app/services/formula_management/function_support_matrix.py` | R4 矩阵更新 |
| `backend/app/router_registry/system.py` | R2/R3/R5/R6 注册新路由 |
| `frontend/src/components/formula/FormulaEditDialog.vue` | R3 调试按钮 |
| `frontend/src/components/formula/FormulaPushPanel.vue` | R5 校验按钮 |
| `frontend/src/components/formula/FormulaDashboardDialog.vue` | R2 健康度 Tab |
| `frontend/src/components/formula/FormulaManagerDialog.vue` | R6 时间轴 Tab |
| `frontend/src/services/apiPaths/formula.ts` | R2/R3/R5/R6 API 路径 |

## §4 偏离记录

- R7（模板市场化）排除：当前单事务所场景 ROI 不足，且架构天然支持未来扩展
- R4 PREV/AUX 扩展采用可选参数 `enable_prev/aux` 而非直接改默认行为：
  避免影响现有报表求值路径（`function_support_matrix.py` 明确标注 PREV/AUX 在报表路径不可用是**设计意图**——上期值走报表 prior 列，辅助核算不进报表），表间审核是独立消费方可独立开启
