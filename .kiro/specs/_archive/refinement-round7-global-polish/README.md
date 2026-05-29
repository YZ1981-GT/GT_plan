# Round 7：全局打磨（Global Polish）

基于 `docs/GLOBAL_REFINEMENT_PROPOSAL_v1.md` 的 35 项路线图，拆分为 3 个 Sprint：

- **Sprint 1（P0）**：零风险快速修复，9 项，1 天
- **Sprint 2（P1）**：中风险核心改造，12 项，2 周
- **Sprint 3（P2）**：需 spec 三件套的大改造，11 项，1 个月

每个 Sprint 独立三件套：requirements.md / design.md / tasks.md

## 跨 Sprint 依赖

- Sprint 2 的"侧栏动态化"依赖 Sprint 1 的"/confirmation 路由修复"
- Sprint 3 的"全局组件铺设"依赖 Sprint 2 的"useEditMode 接入"
- Sprint 3 的"statusMaps 收敛"依赖 Sprint 2 的"GtStatusTag 替换"

## 验收标准

- 每个 Sprint 完成后跑 5 角色 UAT 穿刺清单（见 GLOBAL_REFINEMENT_PROPOSAL_v1.md §五）
- vue-tsc 0 错误
- pytest collection 0 errors
- CI 基线不恶化
