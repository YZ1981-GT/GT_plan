/**
 * useWorkpaperVersionToolbar — 底稿组件内版本历史工具栏集成
 *
 * 提供：版本历史按钮 + GtWpVersionTrail 引用 + 保存后自动快照（debounce）
 */
import { ref, type Ref } from 'vue'
import http from '@/utils/http'

export interface UseWorkpaperVersionToolbarOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  debounceMs?: number
}

export function useWorkpaperVersionToolbar(options: UseWorkpaperVersionToolbarOptions) {
  const { wpId, projectId, debounceMs = 3000 } = options
  const versionTrailRef = ref<{ openDrawer: () => void } | null>(null)
  let autoTimer: ReturnType<typeof setTimeout> | null = null

  function openVersionHistory(): void {
    versionTrailRef.value?.openDrawer()
  }

  async function postSnapshot(
    snapshotType: string,
    description: string,
  ): Promise<void> {
    if (!wpId.value || !projectId.value) return
    await http.post(
      `/api/projects/${projectId.value}/workpapers/${wpId.value}/versions`,
      { snapshot_type: snapshotType, description },
      { _silent: true } as any,
    )
  }

  /** 编辑后自动快照（非 manual，可被生命周期淘汰） */
  async function createAutoSnapshot(): Promise<void> {
    try {
      await postSnapshot('auto', '编辑后自动快照')
    } catch {
      // 自动快照失败不阻塞编辑
    }
  }

  /** 导入前快照 */
  async function createImportSnapshot(): Promise<void> {
    try {
      await postSnapshot('auto_import', '导入前快照')
    } catch {
      // 导入快照失败不阻塞导入
    }
  }

  function scheduleAutoSnapshot(): void {
    if (autoTimer) clearTimeout(autoTimer)
    autoTimer = setTimeout(() => {
      autoTimer = null
      void createAutoSnapshot()
    }, debounceMs)
  }

  function wrapSaveImmediate<T extends (...args: any[]) => Promise<void>>(fn: T): T {
    return (async (...args: any[]) => {
      await fn(...args)
      scheduleAutoSnapshot()
    }) as T
  }

  return {
    versionTrailRef,
    openVersionHistory,
    scheduleAutoSnapshot,
    createAutoSnapshot,
    createImportSnapshot,
    wrapSaveImmediate,
  }
}
