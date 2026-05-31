# 实施计划：wp-ai-review-ux-fix（底稿 AI 复核弹窗 UX 缺陷修复）

> Bug 条件：#[[file:.kiro/specs/wp-ai-review-ux-fix/bugfix.md]]
> 设计：#[[file:.kiro/specs/wp-ai-review-ux-fix/design.md]]
> 工作流：Requirements-First（bugfix）| ~1 天 | 复用 useCellLocate（已就绪）
> 铁律：先 readCode 核实 useCellLocate 真实签名；既有测试零回归

## 任务

- [ ] 1. 核实 useCellLocate 真实签名（已复盘实证）
  - ✅ 已确认：`locateCell(target: LocateTarget): boolean`，LocateTarget = snake_case `{ wp_code, wp_id?, sheet_name, cell_ref, component_type }`
  - ⚠️ `component_type` 必传（决定定位策略）→ findings emit 的 target 需扩展带 componentType（从当前底稿上下文取）
  - _Bug 条件: C2_

- [ ] 2. 修复 C1：复核发现卡片显示底稿编号
  - TsjReviewFindings.vue 卡片头部加 `📋 {{ wpCode }}` tag（el-tag type=primary effect=plain）
  - TsjFinding interface 扩展 wp_code? / wp_name?
  - _Bug 条件: C1_ _属性: G1_

- [ ] 3. 修复 C2：定位跳转接入 useCellLocate
  - SideStandardsTab.vue onLocateCell 改调 `locateCell({ wp_code, sheet_name, cell_ref, component_type })`（snake_case + 带 component_type）
  - TsjReviewFindings emit 的 locate-cell target 扩展 componentType
  - 删除 TODO 注释
  - _Bug 条件: C2_ _属性: G2_

- [ ] 4. 修复 C3：复核按钮显示底稿名
  - SideStandardsTab.vue 复核按钮文案改 `🤖 复核 {{ wpCode || '当前底稿' }}`
  - _Bug 条件: C3_

- [ ] 5. 后端配合：TsjReviewItem 补底稿标识
  - tsj_structured_output_service.py TsjReviewItem 加 wp_code / wp_name（可选）
  - wp_ai.py tsj-review 端点从 wpId 查 WorkingPaper.wp_code + name 注入返回
  - _Bug 条件: C1_ _属性: G1_

- [ ] 6. vitest 验证 + 零回归
  - TsjReviewFindings 渲染底稿编号 tag（C1）
  - SideStandardsTab 复核按钮含底稿名（C3）+ onLocateCell 调 useCellLocate（C2 mock）
  - 既有测试零回归（确认/驳回 + cycle 推断 + Markdown 渲染）+ vue-tsc 0
  - _Bug 条件: C1, C2, C3_ _属性: G1, G2, G3_

- [ ] 7. 收尾
  - 更新 INDEX.md + memory；单 commit（git status 确认无其他 staged）
  - _Bug 条件: C1, C2, C3_

- [ ]* 8. Playwright 实测（待 start-dev.bat）
  - 点"📍 定位"真实跳转到对应 sheet/cell + 高亮
  - 复核发现卡片显示底稿编号
  - 显式标"待环境"不伪绿
  - _Bug 条件: C2_ _属性: G2_
