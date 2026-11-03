/**
 * 按键建索引，同键只保留第一个 —— 与 `items.find(i => key(i) === k)` 命中同一项。
 *
 * 用来替换「循环里再 find」的 O(n²) 查找（底稿列表 929 × 929，spec platform-perf-hotspots R7）。
 * 用 `new Map(items.map(...))` 会保留最后一个，同键重复时与原先的 find 结果不同。
 */
export function indexFirstBy<T, K>(items: readonly T[], key: (item: T) => K): Map<K, T> {
  const out = new Map<K, T>()
  for (const item of items) {
    const k = key(item)
    if (!out.has(k)) out.set(k, item)
  }
  return out
}
