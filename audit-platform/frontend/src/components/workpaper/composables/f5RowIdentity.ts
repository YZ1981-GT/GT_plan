/**
 * F5 行身份铸造 —— BP-7（下标派生行身份）的单点修复。
 *
 * spec: f5-sync-coverage-and-first-canary · Task 6 · Requirements 3.1 / 3.2 / 3.3
 *       · Property 9（裁决 F5-H6：三处一次修完，不分 spec）
 *
 * ═══ BP-7 是什么 ═══
 *
 * slice `workpaper_sync_f_cycle_manifest_slice.json` 的 BP-7 原文点名两条 entry：
 * 「把 `xlsx/gt-f2-inventory-main` 或 `xlsx/gt-f5-cost-of-sales` 标 bidirectional 之前
 * （也在 step 6 为这两条发布 contract 之前）」必须先修。
 * `consequence` 原文：「行身份一旦由位置派生……⇒ stable field key 在 roundtrip 中无法保持」。
 *
 * F5 侧实测三处（slice 原文只登记了第一处，后两处是本 spec 触类旁通所得）：
 *
 * | 键 | 位置 | 改造前写法 |
 * |---|---|---|
 * | `F5-2-monthly-rows`      | `useF5MonthlyDetail.ts:133` | `String(r?.id ?? r?.rowId ?? \`m-${Date.now()}-${i}\`)` |
 * | `F5-3-other-cost-rows`   | `useF5OtherCost.ts:146`     | `String(r?.id ?? r?.rowId ?? \`oc-migrated-${i}\`)`     |
 * | `F5-5-comparison-rows`   | `useF5Comparison.ts:128`    | `String(r?.id ?? r?.rowId ?? \`cmp-migrated-${i}\`)`    |
 *
 * 三者都含数组下标 `${i}`（F5-2 还混时间戳）⇒ 插删行后同一逻辑行换身份，
 * OO↔HTML roundtrip 会把 A 行的值合并进 B 行。
 *
 * ═══ 修复语义 ═══
 *
 * 1. **缺 id** ⇒ 铸稳定 UUID
 * 2. **id 匹配旧下标模式** ⇒ 同样重铸（存量数据迁移，需求 3.3）
 * 3. 铸造次数经 `RowIdentityMintStats` 回传调用方，由 `loadRows()` **立即回写**
 *    （不回写的话 store 里仍无 id，下次载入又铸一个新的 ⇒ 身份每次都变）
 */

/** 铸造计数（出参）。`loadRows()` 据此决定是否立即回写。 */
export interface RowIdentityMintStats {
  minted: number
}

/**
 * 改造前三处产出的「下标派生身份」形态。命中即重铸。
 *
 * 🔴 逐字对应三处旧写法，不是泛化猜测：
 *   - `m-<时间戳>-<下标>`     ← useF5MonthlyDetail
 *   - `oc-migrated-<下标>`    ← useF5OtherCost
 *   - `cmp-migrated-<下标>`   ← useF5Comparison
 */
const LEGACY_ORDINAL_ID_PATTERN = /^(m-\d+-\d+|oc-migrated-\d+|cmp-migrated-\d+)$/

export function isLegacyOrdinalRowId(value: unknown): boolean {
  return LEGACY_ORDINAL_ID_PATTERN.test(String(value ?? ''))
}

/** 铸一个稳定行身份。优先 `crypto.randomUUID()`，不可用时退时间戳+随机。 */
export function mintStableRowId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/**
 * 从原始载荷行解析稳定行身份。
 *
 * @param raw    原始行对象（JSON.parse 的结果元素）
 * @param prefix 铸造前缀（`f5m` / `f5oc` / `f5cmp`）
 * @param stats  铸造计数出参；有铸造时 `minted` 自增，调用方据此立即回写
 */
export function resolveStableRowId(
  raw: unknown,
  prefix: string,
  stats?: RowIdentityMintStats,
): string {
  const source = (raw ?? {}) as Record<string, unknown>
  const candidate = String(source.id ?? source.rowId ?? '').trim()
  if (candidate && !isLegacyOrdinalRowId(candidate)) {
    return candidate
  }
  if (stats) stats.minted += 1
  return mintStableRowId(prefix)
}

/** 行身份铸造前缀（逐表固定，便于排查来源）。 */
export const F5_ROW_ID_PREFIX = {
  monthlyDetail: 'f5m',
  otherCost: 'f5oc',
  comparison: 'f5cmp',
} as const
