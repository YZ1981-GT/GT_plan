/**
 * HTML 底稿编辑器的「未保存草稿」访问器（draft overlay 前端一半）。
 *
 * Feature: chat-host-draft-overlay / Task 4（design §5 前端要点 1）
 *
 * ## 未保存状态从哪来（不另建第二套真源）
 *
 * HTML 底稿的未保存内容在**当前 sheet 宿主组件**里，而不是外壳：外壳只渲染
 * `GtWpRenderer`，由它按 `componentType` 分发到 160+ 个宿主之一。宿主里已经统一走
 * `useChecklistPersistence`（K/J 两个循环 16 个宿主）或自己的 `flushPendingSave`
 * 防抖，`pending` 就是「改了但还没落库」的唯一真源。
 *
 * 因此这里**不读任何新标记**，只汇总 `readHtmlDraft(wpId)` —— 那是
 * `useChecklistPersistence` 一处 `publishHtmlDraftSource` 登记出来的草稿源。
 * 新宿主接入共享适配器即自动被覆盖，不必逐个改宿主。
 *
 * ## 基线版本
 *
 * `wpDetail.updated_at`（后端 `WORKPAPER_BUSINESS_VERSION_SOURCE`）。`useWorkpaperDraftAccessor`
 * 只取首次非空的那一个并永久冻结 —— 保存后 `wpDetail` 会被重取、`updated_at` 前进，
 * 跟着变就等于把「草稿基于旧版本」的检测关掉。
 *
 * ## 为什么 `enabled` 传 `useHtmlRenderer`
 *
 * 外壳同时挂着 HTML 与 Univer 两条渲染路径（`v-if` / `v-else-if`，同一时刻只挂一条），
 * 但本 composable 在 `setup` 期无条件执行。Univer 路径有自己的访问器
 * （`UniverEditorCore` 里登记），若这里也报告内容，同一个 wpId 就会出现两个源。
 * 用 `enabled` 让 HTML 路径关闭时如实回答「没有未保存修改」。
 */

import {
  readHtmlDraft,
  useWorkpaperDraftAccessor,
} from '@/composables/workpaper/workpaperDraftOverlay'

export interface UseHtmlWorkpaperDraftAccessorOptions {
  /** 当前底稿 ID（响应式取值）。 */
  wpId: () => string
  /** 当前底稿详情里的 `updated_at`（`null` = 详情还没到 / 底稿没有该值）。 */
  currentBusinessVersion: () => unknown
  /** 当前是否走 HTML 渲染路径（Univer 路径由 `UniverEditorCore` 自己登记）。 */
  enabled: () => boolean
}

export function useHtmlWorkpaperDraftAccessor(
  options: UseHtmlWorkpaperDraftAccessorOptions,
): () => void {
  return useWorkpaperDraftAccessor({
    wpId: options.wpId,
    currentBusinessVersion: options.currentBusinessVersion,
    isDirty: () => (options.enabled() ? readHtmlDraft(options.wpId()).hasUnsaved : false),
    collectContent: () => (options.enabled() ? readHtmlDraft(options.wpId()).content : null),
  })
}
