/**
 * stableRowIdentity —— 动态行表「稳定行身份」的平台正面样板（唯一一处实现）。
 *
 * spec: `.kiro/specs/n-cycle-sync-foundation-and-first-canary` Task 14
 * 共同判据: NC-6（行身份正面样板可抄）· AC 6.5 / Property 23
 *
 * ═══ 为什么要把它提成正式模块 ═══════════════════════════════════════════════
 *
 * N 循环现算有 **176 处** 按 `rowKey`/`rowId`/`.id` 寻址的稳定身份用法（E 族），
 * 其中 18 处位于 `useN4AdjudicationV2.ts` / `useN4DetailV2.ts` 两个**零生产边
 * orphan** 里。按 AC 1.7 这两个文件要删 —— 但它们恰好是本循环最完整的正面样板。
 *
 * ⇒ tasks.md 的硬约束是「**先把形态提取到正式模块，再删 orphan**」。反序会丢样板，
 *   下一个写动态行表的人只剩位置化下标那一类可抄（那正是 BP-8 的来源）。
 *
 * ═══ 判据（Property 23 的正面侧） ═══════════════════════════════════════════
 *
 * 1. 行身份字段**随行一起落库**，不是渲染期重算的数组下标；
 * 2. 已落库的身份**优先采用**（`adoptRowKey`），不得每次 load 重新生成 ——
 *    重新生成等于每次都是新行，历史 remark 会错位；
 * 3. 有业务语义键时用它（`semanticRowKey`，如 `row-消费税`），没有才退到熵键
 *    （`generatedRowKey`）；语义键让「删除 → 重新新增同一税种」仍能对上历史数据；
 * 4. 增删改一律**按身份寻址**（`findRowByKey` / `removeRowByKey` / `updateRowByKey`），
 *    不得按数组下标。
 *
 * 🔴 `isPositionalRowKey` 是**反向**判据：谁把 `row-0` / `row-${idx}` 这类下标派生值
 *    当身份塞进来，这里能当场判出来，而不是等数据串行了才发现。
 */

/** 稳定行身份的类型别名 —— 读到 `StableRowKey` 就知道「这不是下标」。 */
export type StableRowKey = string

/** 带稳定行身份的行对象最小约束。 */
export interface RowWithStableKey {
  rowKey: StableRowKey
}

/** 语义键前缀。与既有 N3/N4 生产形态保持一致（`row-消费税` / `row-<uuidish>`）。 */
export const STABLE_ROW_KEY_PREFIX = 'row'

/**
 * 业务语义键 —— 首选形态。
 *
 * `semanticRowKey('消费税')` ⇒ `'row-消费税'`。
 * 语义 token 为空时返回空串，由调用方决定退到 {@link generatedRowKey}
 * （🔴 不在这里偷偷兜底成熵键：那会让「语义键缺失」这件事无声消失）。
 */
export function semanticRowKey(token: string | null | undefined): StableRowKey {
  const t = (token ?? '').toString().trim()
  return t ? `${STABLE_ROW_KEY_PREFIX}-${t}` : ''
}

/**
 * 熵键 —— 无业务语义可用时的兜底形态（时间戳 + 随机段，同一 tick 内也不碰撞）。
 */
export function generatedRowKey(prefix: string = STABLE_ROW_KEY_PREFIX): StableRowKey {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * 从落库原始行采纳身份：**已落库的优先**，其次语义键，最后熵键。
 *
 * @param raw 从 `checklist_responses` 整表 JSON 反序列化出来的原始行
 * @param semanticToken 该行的业务语义 token（如税种名称），可空
 */
export function adoptRowKey(
  raw: { rowKey?: unknown; rowId?: unknown; id?: unknown } | null | undefined,
  semanticToken?: string | null,
): StableRowKey {
  const persisted = raw?.rowKey ?? raw?.rowId ?? raw?.id
  if (typeof persisted === 'string' && persisted.trim()) return persisted
  return semanticRowKey(semanticToken) || generatedRowKey()
}

/**
 * 反向判据：这个 key 是不是「下标伪装成身份」？
 *
 * 命中形态：`row-0` / `row-12` / `manual-3` / 纯数字。它们在删中间一行后会整体左移，
 * 把历史数据串到另一行上 —— 正是 BP-8 登记的那类缺陷。
 */
export function isPositionalRowKey(key: unknown): boolean {
  if (typeof key !== 'string') return false
  return /^(?:[A-Za-z][\w-]*-)?\d+$/.test(key.trim())
}

/** 按身份找行（找不到返回 `undefined`，不抛）。 */
export function findRowByKey<T extends RowWithStableKey>(
  rows: readonly T[],
  rowKey: StableRowKey,
): T | undefined {
  return rows.find(r => r.rowKey === rowKey)
}

/**
 * 按身份删行 —— 返回新数组（不原地改），命中 0 条时原样返回。
 *
 * 🔴 调用方 SHALL NOT 改回 `splice(index, 1)`：那会让「删第 3 行」在并发/过滤视图下
 * 删掉另一行。守卫按 `removeRow(rowKey: string)` 的签名形态锁定（NC-7 by_rowid）。
 */
export function removeRowByKey<T extends RowWithStableKey>(
  rows: readonly T[],
  rowKey: StableRowKey,
): T[] {
  return rows.filter(r => r.rowKey !== rowKey)
}

/** 按身份改行 —— 返回新数组，未命中时原样返回。 */
export function updateRowByKey<T extends RowWithStableKey>(
  rows: readonly T[],
  rowKey: StableRowKey,
  patch: (row: T) => T,
): T[] {
  return rows.map(r => (r.rowKey === rowKey ? patch(r) : r))
}

/**
 * 批量采纳身份 —— 用于 `computed` 里从整表 JSON 派生行的场景。
 *
 * 🔴 为什么不能在 computed 里逐行调 {@link adoptRowKey}：缺身份的旧数据会每次重算都
 * 拿到一个**新的熵键**，同一会话里「先读出 key、再按 key 删」就对不上了。
 * 这里改为**确定性**派生：已落库身份 > 语义 token > `row-<序号>` 兜底；
 * 派生结果重复时按出现顺序追加 `#2`、`#3`。旧数据第一次保存后身份即随行落库固定，
 * 此后与顺序无关。
 */
export function assignStableRowKeys<R>(
  raws: readonly R[],
  tokenOf: (raw: R, index: number) => string | null | undefined,
): StableRowKey[] {
  const seen = new Map<StableRowKey, number>()
  return raws.map((raw, i) => {
    const r = raw as unknown as { rowKey?: unknown; rowId?: unknown; id?: unknown } | null
    const persisted = r?.rowKey ?? r?.rowId ?? r?.id
    let key: StableRowKey =
      typeof persisted === 'string' && persisted.trim()
        ? persisted
        : semanticRowKey(tokenOf(raw, i)) || `${STABLE_ROW_KEY_PREFIX}-legacy-${i + 1}`
    const n = (seen.get(key) ?? 0) + 1
    seen.set(key, n)
    if (n > 1) key = `${key}#${n}`
    return key
  })
}

/**
 * {@link assignStableRowKeys} 的配对形态：直接返回 `{ raw, rowKey }`，调用方
 * `keyed.map(({ raw, rowKey }) => …)` 即可 —— 不必再写 `keys[i]` 这种「按位置取身份」的
 * 写法（语义上没错，但读起来与位置化身份同形，扫描器与人都会误判）。
 */
export function withStableRowKeys<R>(
  raws: readonly R[],
  tokenOf: (raw: R, index: number) => string | null | undefined,
): Array<{ raw: R; rowKey: StableRowKey }> {
  const keys = assignStableRowKeys(raws, tokenOf)
  return raws.map((raw, n) => ({ raw, rowKey: keys[n] }))
}

/** 身份唯一性自检：重复身份等于两行共用历史数据，必须能被查出来。 */
export function duplicateRowKeys(rows: readonly RowWithStableKey[]): StableRowKey[] {
  const seen = new Set<StableRowKey>()
  const dup = new Set<StableRowKey>()
  for (const r of rows) {
    if (seen.has(r.rowKey)) dup.add(r.rowKey)
    seen.add(r.rowKey)
  }
  return [...dup]
}
