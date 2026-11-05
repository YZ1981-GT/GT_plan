import { ElMessageBox } from 'element-plus'

import {
  makeChecklistDraft,
  readChecklistDraft,
  type ChecklistCasItem,
  type ChecklistDraftEnvelope,
} from '@/composables/workpaper/checklistCas'
import { checklistDraftKey, checklistDraftPrefix } from '@/composables/workpaper/checklistDraftStorage'

export interface ChecklistDraftStoreOptions<T extends ChecklistCasItem> {
  /** 同一底稿可能有多个 formData，按命名空间与 item 归属双重隔离。 */
  readonly namespace: string
  readonly wpId: () => string
  readonly ownsItem: (itemId: string) => boolean
  /** 只保存服务端已确认的版本，绝不编造当前版本。 */
  readonly versionOf: (itemId: string) => string | undefined
}

export interface ChecklistDraftStore<T extends ChecklistCasItem> {
  store(items: readonly T[]): void
  /** 将被原子拒绝批次中的最新 payload 标为需要用户决定，禁止下次自动重放。 */
  markRecoveryRequired(items: readonly T[]): void
  clear(items: readonly T[]): void
  restore(): ChecklistDraftEnvelope<T>[]
}

/**
 * strict CAS 的本地草稿仓。
 *
 * queue 的 pending 可保护同一组件生命周期内的编辑；页面刷新或路由卸载后仍需保存
 * `{ payload, baseVersion }`。恢复时调用方必须继续用 baseVersion 发起 CAS，不能用新 GET
 * 版本为旧 payload 背书，否则会静默覆盖其他用户已经保存的内容。
 */
export function createChecklistDraftStore<T extends ChecklistCasItem>(
  options: ChecklistDraftStoreOptions<T>,
): ChecklistDraftStore<T> {
  function prefix(): string | null {
    return checklistDraftPrefix(options.namespace, options.wpId())
  }

  function key(itemId: string): string | null {
    return checklistDraftKey(options.namespace, options.wpId(), itemId)
  }

  function write(items: readonly T[], requiresConfirmation: boolean): void {
    if (!options.wpId()) return
    try {
      for (const item of items) {
        if (!options.ownsItem(item.item_id)) continue
        const draftKey = key(item.item_id)
        if (!draftKey) continue
        localStorage.setItem(
          draftKey,
          JSON.stringify(makeChecklistDraft(
            item,
            options.versionOf(item.item_id),
            requiresConfirmation,
          )),
        )
      }
    } catch {
      // localStorage 不可用时，queue.pending 仍保留在当前页面，不能伪装成保存成功。
    }
  }

  function store(items: readonly T[]): void {
    write(items, false)
  }

  function markRecoveryRequired(items: readonly T[]): void {
    write(items, true)
  }

  function clear(items: readonly T[]): void {
    if (!options.wpId()) return
    try {
      for (const item of items) {
        // 多个 formData 共用 namespace 时，不能由错误调用方删掉别人的失败草稿。
        if (!options.ownsItem(item.item_id)) continue
        const draftKey = key(item.item_id)
        if (draftKey) localStorage.removeItem(draftKey)
      }
    } catch { /* ignore unavailable storage */ }
  }

  function restore(): ChecklistDraftEnvelope<T>[] {
    const currentPrefix = prefix()
    if (!currentPrefix) return []
    const found: ChecklistDraftEnvelope<T>[] = []
    try {
      for (let index = 0; index < localStorage.length; index++) {
        const storedKey = localStorage.key(index)
        if (!storedKey?.startsWith(currentPrefix)) continue
        try {
          const itemId = storedKey.slice(currentPrefix.length)
          const draft = readChecklistDraft<T>(JSON.parse(localStorage.getItem(storedKey) || ''))
          if (!draft || draft.item.item_id !== itemId || !options.ownsItem(itemId)) continue
          found.push(draft)
        } catch {
          // 单条损坏草稿不能挡住同范围内其他有效草稿；保留原始值供用户自行清理。
        }
      }
    } catch {
      return found
    }
    return found.sort((left, right) => left.item.item_id.localeCompare(right.item.item_id))
  }

  return { store, markRecoveryRequired, clear, restore }
}


/**
 * 服务器版本已变时，恢复旧草稿必须由用户选择，不能把新的版本令牌套到旧 payload 上自动提交。
 * 保留后仅回显本地草稿；用户下一次明确编辑才会以当前服务器版本作为新的保存基线。
 */
export async function confirmChecklistDraftConflict(): Promise<'keep' | 'discard'> {
  try {
    await ElMessageBox.confirm(
      '服务器已更新此项。可保留本地草稿继续核对，或丢弃本地草稿并使用服务器内容。保留后不会自动提交；再次编辑才会按当前版本保存。',
      '检测到保存冲突',
      {
        type: 'warning',
        confirmButtonText: '保留本地草稿',
        cancelButtonText: '丢弃本地草稿',
        distinguishCancelAndClose: true,
      },
    )
    return 'keep'
  } catch (reason) {
    // 关闭、Esc 或弹窗自身异常都不能默认丢数据；只有用户点击“丢弃本地草稿”才清除。
    return reason === 'cancel' ? 'discard' : 'keep'
  }
}