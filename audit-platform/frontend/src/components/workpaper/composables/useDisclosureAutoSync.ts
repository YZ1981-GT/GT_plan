/**
 * useDisclosureAutoSync — 披露表保存后自动同步到附注（单一共享封装）
 *
 * Spec: .kiro/specs/disclosure-note-linkage-completion (Req1)
 * 对齐 GtConfirmationSummary._autoSyncAfterSave 已 proven 范式。
 *
 * 各披露 tab 在其"保存成功"分支一行接入 `scheduleAutoSync(syncToDisclosureNotes)`：
 * - 防抖（合并短时间内多次保存为一次同步，默认 800ms）
 * - 非阻塞（不等待同步完成即返回）
 * - 失败静默（`.catch(()=>{})`，绝不打断保存或弹阻断错误）
 * - 只读态 gate（EQCR/归档/无编辑权 → 不触发）
 *
 * `syncFn` = 各 tab 既有 `syncToDisclosureNotes`（本身已走 canonical URL + buildXSyncPayload），
 * 自动同步不新造 payload，与手动按钮同源（幂等）。
 */

export interface DisclosureAutoSyncOptions {
  /** 只读态返回 true 则不触发（EQCR/归档/无编辑权） */
  isReadonly?: () => boolean
  /** 防抖毫秒，默认 800 */
  debounceMs?: number
}

export interface DisclosureAutoSync {
  /** 防抖调度一次自动同步（非阻塞、失败静默）。连续调用在 debounceMs 内合并为一次。 */
  scheduleAutoSync: (syncFn: () => Promise<void> | void) => void
  /** 清除待触发定时器（onBeforeUnmount 调用） */
  cancelPending: () => void
}

const DEFAULT_DEBOUNCE_MS = 800

export function useDisclosureAutoSync(opts?: DisclosureAutoSyncOptions): DisclosureAutoSync {
  const debounceMs =
    typeof opts?.debounceMs === 'number' && opts.debounceMs >= 0 ? opts.debounceMs : DEFAULT_DEBOUNCE_MS
  let timer: ReturnType<typeof setTimeout> | null = null

  function scheduleAutoSync(syncFn: () => Promise<void> | void): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      // 只读态到点跳过（EQCR/归档/无编辑权）
      try {
        if (opts?.isReadonly && opts.isReadonly()) return
      } catch {
        // isReadonly 判定异常时保守跳过，绝不因它抛错
        return
      }
      // 非阻塞 + 失败静默：绝不向上抛，绝不打断保存流程
      try {
        Promise.resolve(syncFn()).catch(() => {})
      } catch {
        // syncFn 同步抛出也吞掉
      }
    }, debounceMs)
  }

  function cancelPending(): void {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  return { scheduleAutoSync, cancelPending }
}
