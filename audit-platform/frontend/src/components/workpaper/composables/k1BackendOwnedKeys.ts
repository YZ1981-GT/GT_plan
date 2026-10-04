/**
 * K1-1 后端公式推送独占键。
 *
 * 公式推送是这些系统值的唯一持久化写入方。K1 页面仍可在内存中读取和计算
 * 它们，但普通字段保存不能把页面打开期间的旧值回写到 checklist_responses。
 *
 * spec: chain-closure-phase3-push-rollout · design §六 · 需求 6.3
 */
const BACKEND_OWNED = [
  // 性质分布与组合行的期初、未审数。
  /^K1-1-(?:nature-(?:gross|prov)-n[0-4]|(?:receivable|baddebt)-r[0-3])-(?:begin|unadj)$/,
  // 与财务报表核对区的三项系统值。
  /^K1-1-fs-(?:interest|dividend|other-total)$/,
  // 后端按推送算式派生的审定合计。
  /^K1-1-audited-(?:receivable|baddebt|net)$/,
] as const

export function isK1BackendOwnedKey(itemId: string): boolean {
  return BACKEND_OWNED.some((re) => re.test(itemId))
}

/** K1 宿主保存集合：保留所有用户键，只过滤公式推送独占键。 */
export function k1SaveItemIds(itemIds: Iterable<string>): string[] {
  return [...itemIds].filter((id) => !isK1BackendOwnedKey(id))
}

/** K1-1 审定表保存集合：K1-1 键中排除后端独占键。 */
export function k1AdjudicationSaveItemIds(itemIds: Iterable<string>): string[] {
  return [...itemIds].filter(
    (id) => id.startsWith('K1-1-') && !isK1BackendOwnedKey(id),
  )
}
