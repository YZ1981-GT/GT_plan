/**
 * 后台合并登记（按 wpId）—— 页面级渲染器（只读 + 横幅）与持久化层（拒写）的**单一**数据源。
 *
 * spec: oo-return-to-form-dead-end-and-save-speed · R4.4
 *
 * 桥在 `continueInBackground()` 时登记、落地 / 关闭提示 / 卸载时注销；`GtWpRenderer` 据此把整张
 * 底稿设成只读并挂横幅，`useChecklistPersistence` 据此拒写。不逐个改宿主：各循环底稿都经这两处。
 */
import { reactive } from 'vue'

export type BackgroundMergeStatus = 'merging' | 'failed'

export interface BackgroundMergeEntry {
  readonly wpId: string
  status: BackgroundMergeStatus
  /** 横幅正文（中文）。 */
  message: string
  /** 失败后能否「重试回写」（服务端重新合并同一份已耐久文件）。 */
  canRetry: boolean
  readonly retry: () => Promise<void>
  readonly refresh: () => Promise<void>
  readonly dismiss: () => Promise<void>
}

/** 持久化层在合并期间拒写时给的原因。 */
export const BACKGROUND_MERGE_WRITE_REFUSED_MESSAGE =
  '正在合并在线编辑的改动，表单暂不可修改，合并完成后会自动刷新'

const entries = reactive(new Map<string, BackgroundMergeEntry>())

/** 登记（同一 wpId 后来者覆盖）；返回只注销**本条**的函数（不误删后来者）。 */
export function registerBackgroundMerge(entry: BackgroundMergeEntry): {
  readonly entry: BackgroundMergeEntry
  readonly unregister: () => void
} {
  entries.set(entry.wpId, entry)
  const stored = entries.get(entry.wpId) as BackgroundMergeEntry
  return {
    entry: stored,
    unregister: () => {
      if (entries.get(entry.wpId) === stored) entries.delete(entry.wpId)
    },
  }
}

export function backgroundMergeOf(wpId: string | null | undefined): BackgroundMergeEntry | null {
  if (!wpId) return null
  return entries.get(wpId) ?? null
}

/** 合并进行中（表单只读、持久化拒写）。失败态不算：表单解除只读。 */
export function isBackgroundMerging(wpId: string | null | undefined): boolean {
  return backgroundMergeOf(wpId)?.status === 'merging'
}

/** 测试隔离用。 */
export function clearBackgroundMerges(): void {
  entries.clear()
}
