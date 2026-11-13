import { getCurrentScope, onScopeDispose, watch } from 'vue'

/** 同步观察每次上下文跃迁（包括 A→B→A），各请求通道只允许最后一次完成写回。 */
export function useReportRequestFence(context: () => readonly unknown[], invalidate: () => void) {
  let epoch = 0
  let disposed = false
  const sequences = new Map<string, number>()
  const stop = watch(context, () => {
    epoch++
    sequences.clear()
    invalidate()
  }, { flush: 'sync' })
  if (getCurrentScope()) onScopeDispose(() => {
    disposed = true
    epoch++
    stop()
    invalidate()
  })
  function begin(lane = 'default') {
    const capturedEpoch = epoch
    const sequence = (sequences.get(lane) ?? 0) + 1
    sequences.set(lane, sequence)
    return { isCurrent: () => !disposed && epoch === capturedEpoch && sequences.get(lane) === sequence }
  }
  return { begin }
}
export type ReportRequest = ReturnType<ReturnType<typeof useReportRequestFence>['begin']>
