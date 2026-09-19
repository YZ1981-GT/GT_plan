/**
 * 底稿持久化前端开发诊断（wp_persistence_dirty_items）。
 *
 * 仅在开发环境生效，生产环境为空操作。
 * 提供全局 dirty item 计数，供 DevTools / 控制台实时观察。
 *
 * Design §10: wp_persistence_dirty_items（前端埋点/开发诊断）
 * Requirements: 8.1
 */

import { ref, readonly, type Ref } from 'vue'

interface PersistenceMetrics {
  /** 当前全局待保存（dirty）item 计数 */
  dirtyCount: Readonly<Ref<number>>
  /** 保存成功次数 */
  saveSuccessCount: Readonly<Ref<number>>
  /** 保存失败次数 */
  saveErrorCount: Readonly<Ref<number>>
  /** 409 冲突次数 */
  conflictCount: Readonly<Ref<number>>
  /** 注册 dirty item（内部使用） */
  trackDirty(itemId: string): void
  /** 注销 dirty item（内部使用） */
  untrackDirty(itemId: string): void
  /** 记录保存成功 */
  recordSaveSuccess(): void
  /** 记录保存失败 */
  recordSaveError(): void
  /** 记录冲突 */
  recordConflict(): void
  /** 重置（测试用） */
  reset(): void
}

const _dirtyItems = new Set<string>()
const dirtyCount = ref(0)
const saveSuccessCount = ref(0)
const saveErrorCount = ref(0)
const conflictCount = ref(0)

const isDev = import.meta.env.DEV

function trackDirty(itemId: string): void {
  if (!isDev) return
  _dirtyItems.add(itemId)
  dirtyCount.value = _dirtyItems.size
}

function untrackDirty(itemId: string): void {
  if (!isDev) return
  _dirtyItems.delete(itemId)
  dirtyCount.value = _dirtyItems.size
}

function recordSaveSuccess(): void {
  if (!isDev) return
  saveSuccessCount.value++
}

function recordSaveError(): void {
  if (!isDev) return
  saveErrorCount.value++
}

function recordConflict(): void {
  if (!isDev) return
  conflictCount.value++
}

function reset(): void {
  _dirtyItems.clear()
  dirtyCount.value = 0
  saveSuccessCount.value = 0
  saveErrorCount.value = 0
  conflictCount.value = 0
}

export const persistenceMetrics: PersistenceMetrics = {
  dirtyCount: readonly(dirtyCount),
  saveSuccessCount: readonly(saveSuccessCount),
  saveErrorCount: readonly(saveErrorCount),
  conflictCount: readonly(conflictCount),
  trackDirty,
  untrackDirty,
  recordSaveSuccess,
  recordSaveError,
  recordConflict,
  reset,
}

// 开发环境挂载到 window 供 DevTools 实时观察
if (isDev && typeof window !== 'undefined') {
  ;(window as any).__wp_persistence_metrics = persistenceMetrics
}

export default persistenceMetrics
