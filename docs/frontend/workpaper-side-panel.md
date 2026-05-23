# WorkpaperSidePanel 使用指南

**版本**：v1.0（R10 Spec C / Sprint 2.5.1）
**最后更新**：2026-05-16
**适用对象**：底稿编辑器 (`WorkpaperEditor.vue`)、子编辑器 (`WorkpaperFormEditor.vue` / `WorkpaperWordEditor.vue` / `WorkpaperTableEditor.vue` / `WorkpaperHybridEditor.vue`)

---

## 1. 总体定位

`WorkpaperSidePanel` 是底稿编辑器的统一右栏面板，通过 `el-drawer`（默认 400px 宽度）从右侧滑入，承担"编辑器主区不放、但与当前底稿强相关"的全部辅助功能。

**职责边界**：
- ✅ 涵盖：AI 辅助、附件、版本、批注、程序、依赖、自检、提示等 10 类
- ❌ 不涵盖：底稿主体内容编辑（在主编辑区做）/ 跨底稿汇总（在工作台或列表做）

---

## 2. 数据流图

```
┌───────────────────────────────────────────────┐
│      WorkpaperEditor.vue（路由分发）           │
│   - component_type=univer → 自渲染 Univer     │
│   - component_type=form/word/... → 子编辑器   │
└───────────────────────────────────────────────┘
                    │
                    ▼ showSidePanel = true
┌───────────────────────────────────────────────┐
│     <el-drawer> WorkpaperSidePanel             │
│     :project-id  :wp-id  :wp-code              │
└───────────────────────────────────────────────┘
                    │
              ┌─────┴─────┐
              ▼           ▼
       10 个 el-tabs   eventBus（双向）
              │             │
              ▼             ▼
   各 Tab 异步加载数据   workpaper:locate-cell
   通过 axios → API     workpaper:saved
                        finecheck-update emit
```

---

## 3. 10 个 Tab 详解

### Tab 1：AI 助手（`ai`）

- **用途**：在编辑底稿时调用 AI 模型回答审计问题、生成审计说明、解释科目变动
- **数据来源**：`POST /api/projects/{pid}/ai/chat`（流式返回）
- **与编辑器交互**：用户在编辑器主区选中单元格后，可在 AI Tab 提问"这个数字偏离去年很多，可能原因？"AI 回复中含 `[底稿引用]` 标签时点击可跳回主区
- **已知限制**：vLLM 不可用时降级为纯文本提示，无法跨底稿引用

### Tab 2：附件（`attachments`）

- **用途**：管理与当前底稿关联的支撑性证据（合同、银行回单、发票等）
- **数据来源**：`GET /api/attachments/search?wp_code=xxx`
- **与编辑器交互**：上传附件后通过 `eventBus.emit('attachment:linked')` 通知编辑器刷新关联标记；点击附件可在新窗口预览
- **已知限制**：单文件 ≤ 50MB；OCR 状态异步更新，不阻塞上传

### Tab 3：版本（`versions`）

- **用途**：查看底稿历史版本、回滚、对比
- **数据来源**：`GET /api/projects/{pid}/workpapers/{wpId}/versions`
- **与编辑器交互**：选择版本后弹"是否回滚到 vX？"二次确认 → 调 `POST /restore` → emit `workpaper:saved` → 编辑器重新加载
- **已知限制**：版本快照仅保存最近 30 个；超过自动归档到 archived storage

### Tab 4：批注（`annotations`）

- **用途**：单元格级批注（用户在主区右键加批注后此 Tab 显示历史）
- **数据来源**：`GET /api/cell-annotations?wp_id=xxx`
- **与编辑器交互**：点击批注列表项 → emit `workpaper:locate-cell` → 编辑器主区滚动+高亮目标单元格
- **已知限制**：批注内容支持纯文本，富文本/图片需走 R11+ 升级

### Tab 5：程序（`procedures`）

- **用途**：当前底稿应执行的审计程序步骤清单（来自 wp_template_metadata.procedure_steps）
- **数据来源**：`GET /api/projects/{pid}/workpapers/{wpId}/procedures`
- **与编辑器交互**：勾选完成的程序 → 写入 wp_index.completed_procedures JSONB；自检 Tab 自动重算覆盖率
- **已知限制**：D-N 89 个底稿全有程序步骤，B/C/A/S 类元数据较稀疏

### Tab 6：程序要求（`requirements`）

- **用途**：本底稿对应的审计准则要求（来自 wp_template_metadata.audit_objective）
- **数据来源**：纯前端展示（来自 wp_index 元数据，无独立 API）
- **与编辑器交互**：只读展示，作为审计助理编制底稿时的提示

### Tab 7：依赖（`dependencies`）

- **用途**：跨底稿引用关系（如 K8 折旧分摊依赖 H1 固定资产明细）
- **数据来源**：`GET /api/projects/{pid}/workpapers/{wpId}/dependencies`
- **与编辑器交互**：点击依赖底稿 → 路由跳到该底稿编辑器
- **已知限制**：依赖关系来自 cross_wp_references.json 静态配置（20 条）

### Tab 8：一致性（`consistency`）

- **用途**：跨底稿核对结果（如审定数 vs 试算表期末余额）
- **数据来源**：`GET /api/projects/{pid}/workpapers/{wpId}/cross-check`
- **与编辑器交互**：失败的核对项点击"定位"按钮 → emit `workpaper:locate-cell`

### Tab 9：自检（`finecheck`）

- **用途**：精细化审计检查清单（CHK-01~05 等代码化检查）
- **数据来源**：`POST /api/projects/{pid}/workpapers/{wpId}/fine-extract`
- **与编辑器交互**：检查失败时通过 `@finecheck-update="fineCheckFailCount = $event"` 上报数量到主工具栏 badge
- **已知限制**：每次 Tab 切换重新拉取，不缓存

### Tab 10：提示（`tsj`）

- **用途**：TSJ 提示词库（按科目名查询 risk_areas / checklist / tips）
- **数据来源**：`GET /api/projects/{pid}/workpapers/wp-mapping/{accountName}/tsj`
- **与编辑器交互**：纯只读展示，作为审计助理参考

---

## 4. 与编辑器主区的交互模式

### 4.1 通过 props 单向传入

```vue
<WorkpaperSidePanel
  :project-id="projectId"
  :wp-id="wpId"
  :wp-code="wpDetail?.wp_code"
  @finecheck-update="fineCheckFailCount = $event"
/>
```

### 4.2 通过 eventBus 双向通信

| 事件 | 方向 | 说明 |
|------|------|------|
| `workpaper:locate-cell` | Panel → Editor | 自检/批注/一致性 Tab 点击"定位" → 编辑器滚动到目标单元格 |
| `workpaper:saved` | Panel → Editor | 版本回滚后通知编辑器重新加载 |
| `attachment:linked` | Panel → Editor | 附件上传成功通知主区刷新关联标记 |
| `finecheck-update` | Panel → Editor (Vue emit) | 自检失败数同步到主工具栏 badge |

### 4.3 不通过事件的状态同步

WorkpaperEditor 自动保存周期（60s）会 emit `workpaper:saved`，Panel 中的"版本"/"附件"等 Tab 监听后重新拉取数据。

---

## 5. 性能要点

- **懒加载**：Tab 切换时按需加载，已加载的 Tab 不重新拉取（除非显式刷新）
- **抽屉模式**：`el-drawer` 默认 `:modal="false"` 不阻塞主区交互，支持边编辑边查看
- **并发请求**：每个 Tab 独立 axios 调用，互不阻塞

---

## 6. 已知限制与未来增强

| 限制 | 影响 | 计划 |
|------|------|------|
| 10 Tab 全部右栏，宽度固定 400px | 数据较多时滚动较多 | R11 评估自适应宽度 |
| 移动端不可见 | 仅桌面端 | 不计划，移动端已是 R8 不做项 |
| 跨底稿 Tab（如"全项目自检汇总"）需另开页 | UX 多次跳转 | R11 评估 |

---

## 7. 调试与扩展

### 7.1 添加新 Tab

1. 在 `WorkpaperSidePanel.vue` 模板添加 `<el-tab-pane label="新 Tab" name="new">`
2. 在 script setup 添加 `loadNewTabData()` 异步方法
3. 在 `watch(activeTab, ...)` 中按需触发加载
4. 后端补对应 API + 前端走 `@/services/apiPaths.ts` 集中管理

### 7.2 调试事件流

```js
// 在 main.ts 启用 debug
import { eventBus } from '@/utils/eventBus'
window.__GT_BUS = eventBus
// 控制台：__GT_BUS.on('workpaper:locate-cell', console.log)
```

---

**关联文件**：
- `audit-platform/frontend/src/components/workpaper/WorkpaperSidePanel.vue`
- `audit-platform/frontend/src/views/WorkpaperEditor.vue`
- `audit-platform/frontend/src/utils/eventBus.ts`

**关联 spec**：R8-S2-01 / R10 Spec C 文档化任务（Sprint 2.5）
