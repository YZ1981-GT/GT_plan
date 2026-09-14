# 上下文：为什么 D 循环长这样

## 渲染链路（所有 D 科目共同）

```
WorkpaperEditor.vue
  → useEditorMode 判定 componentType ∈ HTML_COMPONENT_TYPE_SET
  → GtWpRenderer.vue（统一渲染器 + Runtime Boundary）
      ├─ 按 componentType 查 htmlRendererRegistry.ts → GtDxXxx.vue
      └─ provide 全局能力：openReviewDialog / generateAiText / version.scheduleAutoSnapshot
  → GtDxXxx.vue 按 sheetName v-if 分发到 dX/**/DxTabXxx.vue
```

后端侧：`GET /api/workpapers/{wp_id}/render-config` → `wp_render_config.py` 解析
`workpaper_sheet_classification` + `wp_code_overrides.json` 得 componentType
→ `RENDERER_DISPATCH['dX-...']` → `_dX_xxx.py::render()` 返回
`{component_type, html_data:{project_context, responses_snapshot, ...}}`。

**整册专属组件会被折叠为单 sheet 并清空 `html_data.cells`**（`_SELF_CONTAINED_DEDICATED`），
否则模板 grid cells 会触发 `noRendererGridFallback` 用 `GtGridSheet` 遮蔽专属组件。

## 持久化

- 端点：`PUT /api/workpapers/{wp_id}/checklist-responses`
- 结构：`item_id`（如 `D2-detail-rows` / `D2-adj-tb-amount`）+ `remark`（JSON 字符串）
- 前端：`useDxFormData` 维护 `allResponses: Ref<Map>` + 防抖 PUT + `scheduleAutoSnapshot` 版本快照
- **跨表联动靠共享 item_id 键**：明细表写 `Dx-2-*`，审定表读同键聚合；键名不一致就是"死链"

## 跨底稿事件（`crossWpEventBridge` 双向桥接 window CustomEvent ⇄ mitt eventBus）

| 事件 | 生产者 | 消费者 |
|------|--------|--------|
| `substantive:adjudicated` | 审定表回写后 | 附注披露 tab 自动刷新、下游科目 |
| `adjustment:created` | 调整分录保存 | 审定表 AJE/RJE 合计、集中登记刷新信号 |
| `a13:push-misstatement` | 各检查表异常/跨期 | `useA13MisstatementBridge`（挂 WorkpaperEditor，唯一消费者） |
| `confirmation:received` | 函证中心状态推进到终态 | 明细表 `isConfirmed` 回写、下游 stale |
| `disclosure:note-text-updated` | 披露 tab 保存叙述 | 附注编辑器定向刷新当前章节 |
| `aging-config:changed` | 项目账龄配置 PUT | 各明细表账龄列重建 |

## 共享能力（不在 D 循环内实现，D 只是消费方）

- 抽凭引擎 `GtVoucherSamplingEngine`（`account-code` + `phase=final` + `workpaper-id` + `year`，emit `filled` 返回 `{samples,...}`）
- 截止测试 `useCycleCutoff` + `cutoffCanonical`（跨期判定单一真源，双模式 cutoff-boundary / natural-month）
- 账龄配置 `useAgingConfig` + `AgingConfigDialog`
- 集中调整 `useAdjustmentCentralSync`（`POST /adjustments/sync-from-workpaper`，幂等 `source_ref={wp_id}:{item_id}`）
- 附注联动 `noteDisclosureJump` / `noteDisclosureReverseJump` / `useNoteRefresh`
- 版本链 `useWorkpaperVersionToolbar` + `GtWpVersionTrail`
- 复核 `GtReviewTrigger` + `GtReviewDot`（需主入口 provide `getThreadDot`/`getRowDot`）
