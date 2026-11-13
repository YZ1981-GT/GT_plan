/**
 * 披露表保存后自动同步到附注的统一调度器。
 *
 * D4：原实现是防抖后 fire-and-forget，失败被吞、同步中有新编辑时会启动并发请求，
 * 用户既看不到失败也无法重试。现在以本地 edit revision 为单一排序键：
 *
 * - 同一时刻最多一个 syncFn 在飞；
 * - 飞行期间的新编辑只保留最新 closure（latest pending），旧 payload 不会在稍后覆盖新内容；
 * - 失败不向保存调用方抛出，但写入 errorMessage、发中文提示，并可 retry()；
 * - 回调仍接收各 Tab 的既有 syncToDisclosureNotes，故手动/自动载荷同源。
 */

import { ElMessage } from 'element-plus'
import { readonly, ref, type Ref } from 'vue'

export interface DisclosureAutoSyncOptions {
  /** 只读态返回 true 则不触发（EQCR/归档/无编辑权） */
  isReadonly?: () => boolean
  /** 防抖毫秒，默认 800 */
  debounceMs?: number
  /** 页面需要局部提示时可订阅；默认仍会发一次全局中文提示。 */
  onFailed?: (message: string, error: unknown, revision: number) => void
}

export interface DisclosureAutoSync {
  /** 防抖调度一次同步。连续编辑只保留最新 revision。 */
  scheduleAutoSync: (syncFn: () => Promise<void> | void) => void
  /** 清除尚未开始的同步；不会中断已发出的请求。 */
  cancelPending: () => void
  /** 重试最后一个失败 revision；无失败/只读态时返回 false。 */
  retry: () => Promise<boolean>
  /** 当前是否有实际网络同步在飞。 */
  syncing: Readonly<Ref<boolean>>
  /** 是否有已排队、尚未运行的最新 revision。 */
  pending: Readonly<Ref<boolean>>
  /** 最近失败的用户可见中文原因；成功/新编辑后清空。 */
  errorMessage: Readonly<Ref<string>>
  /** 单调本地编辑 revision，页面可用于诊断或局部状态展示。 */
  syncRevision: Readonly<Ref<number>>
}

interface SyncJob {
  revision: number
  syncFn: () => Promise<void> | void
}

const DEFAULT_DEBOUNCE_MS = 800

function failureMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return `披露自动同步失败：${error.message.trim()}。请手动点击同步重试。`
  }
  return '披露自动同步失败，请手动点击同步重试。'
}

export function useDisclosureAutoSync(opts?: DisclosureAutoSyncOptions): DisclosureAutoSync {
  const debounceMs = typeof opts?.debounceMs === 'number' && opts.debounceMs >= 0
    ? opts.debounceMs
    : DEFAULT_DEBOUNCE_MS
  const syncing = ref(false)
  const pending = ref(false)
  const errorMessage = ref('')
  const syncRevision = ref(0)

  let timer: ReturnType<typeof setTimeout> | null = null
  let latest: SyncJob | null = null
  let failed: SyncJob | null = null
  let inFlight: Promise<boolean> | null = null
  let lastNotifiedRevision = 0

  function clearTimer(): void {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  function readonlyNow(): boolean {
    try {
      return opts?.isReadonly?.() === true
    } catch {
      // 门控本身出错时 fail closed：不能在未知只读态下写附注。
      return true
    }
  }

  function reportFailure(job: SyncJob, error: unknown): void {
    const message = failureMessage(error)
    errorMessage.value = message
    failed = job
    try {
      opts?.onFailed?.(message, error, job.revision)
    } catch {
      // 页面自定义通知失败不应再掩盖原始同步失败。
    }
    if (lastNotifiedRevision !== job.revision) {
      lastNotifiedRevision = job.revision
      ElMessage.warning(message)
    }
  }

  async function runPending(): Promise<boolean> {
    let allSucceeded = true
    while (latest !== null) {
      const job = latest
      latest = null
      pending.value = false
      if (readonlyNow()) continue

      syncing.value = true
      try {
        await job.syncFn()
        // 只清除本 revision 的错误：若飞行期间已有更新，它会由下一轮接管。
        if (failed?.revision === job.revision) failed = null
        if (syncRevision.value === job.revision) errorMessage.value = ''
      } catch (error) {
        allSucceeded = false
        reportFailure(job, error)
      } finally {
        syncing.value = false
      }
      // latest 在飞行期间可能被替换，循环只执行它而非旧 closure。
    }
    pending.value = latest !== null
    return allSucceeded && !errorMessage.value
  }

  async function drain(): Promise<boolean> {
    clearTimer()
    if (inFlight !== null) return inFlight
    const flight = runPending()
    inFlight = flight
    try {
      return await flight
    } finally {
      if (inFlight === flight) inFlight = null
      // timer 触发时刚好观察到旧 flight 的边界，新编辑仍不能丢失。
      if (latest !== null && timer === null) void drain()
    }
  }

  function scheduleAutoSync(syncFn: () => Promise<void> | void): void {
    const revision = syncRevision.value + 1
    syncRevision.value = revision
    latest = { revision, syncFn }
    pending.value = true
    // 用户继续编辑即代表愿意以最新状态重试；旧错误不再阻塞保存流程。
    errorMessage.value = ''
    failed = null
    if (readonlyNow()) {
      clearTimer()
      latest = null
      pending.value = false
      return
    }
    clearTimer()
    timer = setTimeout(() => { timer = null; void drain() }, debounceMs)
  }

  function cancelPending(): void {
    clearTimer()
    latest = null
    pending.value = false
  }

  async function retry(): Promise<boolean> {
    if (failed === null || readonlyNow()) return false
    const retryJob: SyncJob = {
      revision: syncRevision.value + 1,
      syncFn: failed.syncFn,
    }
    syncRevision.value = retryJob.revision
    latest = retryJob
    pending.value = true
    errorMessage.value = ''
    failed = null
    return drain()
  }

  return {
    scheduleAutoSync,
    cancelPending,
    retry,
    syncing: readonly(syncing),
    pending: readonly(pending),
    errorMessage: readonly(errorMessage),
    syncRevision: readonly(syncRevision),
  }
}
