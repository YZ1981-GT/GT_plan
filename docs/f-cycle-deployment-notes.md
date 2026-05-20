# F 采购存货循环 — 部署注意事项

> Spec: `workpaper-f-purchase-inventory` / Sprint 2 / Tasks 2.15~2.17

## 1. cross_wp_references 35 条新增 (CW-176~CW-210)

Sprint 2 Task 2.15 已通过一次性脚本追加 35 条 F 循环跨底稿引用条目（用完即删，
脚本已删除）。最终状态：

- `backend/data/cross_wp_references.json` 总条目 **210**（基线 175 + 新增 35）
- F 循环条目 **43**（基线 8 + 新增 35）
- ref_id 区间 **CW-176 ~ CW-210**，全局唯一性已通过 `test_f_cross_wp_refs.py` 校验
- 6 个分组覆盖：F0 内部 5 / F2 内部 4 / F 跨底稿 8 / F→A 8 / F→T1 IPE 4 / F→附注 6

## 2. Linkage-bus 依赖图重建 (Task 2.17)

新增条目通过 `LinkageGraphBuilder` 加载到统一依赖图。**生产部署后必须重建依赖图
缓存**，否则前端 `WorkpaperEditor` 看不到新增的 stale 传播链路。

**重建方式**（任选其一）：

1. **API 触发**（推荐，运维可现场执行）：
   ```
   GET /api/linkage-bus/graph?rebuild=true
   ```
   该端点会从 6 个数据源重新构建依赖图并写回
   `backend/data/unified_dependency_graph.json`。

2. **删除缓存文件**（备用）：
   ```
   del backend\data\unified_dependency_graph.json
   ```
   下一次 `GET /api/linkage-bus/graph`（不带 `rebuild=true`）会发现缓存缺失并自动
   重建。

## 3. 首次部署 / 数据迁移检查清单

- [ ] 确认 `backend/data/cross_wp_references.json` 总条目 ≥ 210
- [ ] 确认 `backend/data/f_cycle_validation_rules.json` 存在且含 4 条 VR-F5/F2 规则
- [ ] 部署后调用 `GET /api/linkage-bus/graph?rebuild=true` 重建依赖图
- [ ] 跑回归测试：`python -m pytest backend/tests/test_f_cross_wp_refs.py
      backend/tests/test_f5_validation_rules.py
      backend/tests/test_f0_f2_confirmation_callback.py -v`

## 4. F-F8 反向回填触发链路

CW-176 (`F0→F2 函证已回函金额合计 → F2-1 已函证金额`) 配置了
`trigger: "eventBus confirmation:received"`. 端到端链路：

1. `apply_confirmation_result()` → `event_bus.publish_immediate(CONFIRMATION_RECEIVED)`
2. stale_engine 订阅 `CONFIRMATION_RECEIVED` → 沿 cross_wp_references 中 source_wp=F0
   的所有条目向下游传播 stale
3. 前端 `WorkpaperEditor` 订阅 `cross-ref:updated` → 触发 F2-1 公式重新计算

如果发现 F0 函证回函后 F2 没有刷新，先排查：依赖图是否已重建（参见 §2）。
