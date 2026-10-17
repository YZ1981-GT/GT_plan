/**
 * 附注目录 hover 预取（DisclosureEditor 用）：鼠标停留 `delayMs` 后把章节详情静默取进缓存。
 *
 * 预取与「点击取当前章」发的是同一个 GET，`http` 的 GET 去重会取消先发的那一个。原实现点击后不掐预取：
 * 鼠标移入后 200ms 内点击、且点击的请求 200ms 内没回（后端慢）时，晚到的预取把点击的请求取消，编辑器当失败置空，
 * 中间栏回到「请从左侧目录选择章节」（spec disclosure-note-template-word-realignment Task 27 浏览器实测）。
 * ⇒ 调用方开始取当前章时先 `cancel()`；预取到点时再查一次缓存。
 */
export function createNoteDetailPrefetch<T>(
  load: (noteSection: string) => Promise<T>,
  cache: Map<string, T>,
  keyOf: (noteSection: string) => string,
  delayMs = 200,
) {
  let timer: ReturnType<typeof setTimeout> | null = null

  function cancel(): void {
    if (timer) { clearTimeout(timer); timer = null }
  }

  function schedule(noteSection: string): void {
    const key = keyOf(noteSection)
    if (cache.has(key)) return
    cancel()
    timer = setTimeout(async () => {
      timer = null
      if (cache.has(key)) return
      try {
        cache.set(key, await load(noteSection))
      } catch { /* 预取失败静默忽略 */ }
    }, delayMs)
  }

  return { schedule, cancel }
}
