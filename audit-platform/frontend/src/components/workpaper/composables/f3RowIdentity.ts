/**
 * F3 行身份铸造 —— 「铸新但不回写」的单点修复（四处共用）。
 *
 * spec: f3-sync-coverage-and-first-canary · Task 13 / Task 14 / Task 15
 *
 * ═══ 问题形态（与 F5 的 BP-7 同型危害、不同成因）═══
 *
 * F3 四张受管 sheet 的载入路径都写着：
 *
 *     rowId: raw.rowId || raw.id || generateRowId()
 *
 * 缺 id 时铸一个新 UUID —— 这步本身没错，错在**铸完不回写 store**：
 * `loadRows()` / `loadSection()` 只把结果放进 ref，没有 persist。于是下次载入
 * 再铸一个新的 ⇒ **同一逻辑行的身份每次都变**。
 *
 * OO↔HTML roundtrip 按行身份配对 stable field key，身份漂移的后果与 BP-7
 * （下标派生身份）完全一样：把 A 行的值合并进 B 行。
 *
 * 与 F5 的差别：F5 的旧 id **本身含数组下标**（`m-<ts>-<i>` 等），所以还需要
 * `isLegacyOrdinalRowId()` 把存量下标身份重铸；F3 的 `generateRowId()` 产出
 * `<prefix>-<ts36>-<rand>` 不含下标，存量 id 是稳定的 ⇒ **不需要重铸已有 id**，
 * 只需「缺 id 才铸 + 铸了就回写」。故本模块**刻意没有** legacy pattern 检测 ——
 * 加一个会把正常的存量身份误判重铸，那才是引入身份漂移。
 *
 * ═══ 适用边界（诚实声明）═══
 *
 * 「铸新不回写」是**平台级反模式**，全仓 `|| generateRowId()` 有数十处，遍布
 * D1/D2/D3/D4/D5/E0 等循环。本模块只覆盖 **F3 已接入/即将接入 sync 受管清单的四张**：
 *
 *     F3-5 逾期票据检查   F3-6 关联方及交易检查   F3-7 检查表三区   F3-2 期末明细
 *
 * 理由：未接 sync 的 sheet，行身份只在前端会话内使用，不回写的危害小得多；
 * 而受管 sheet 的行身份是 roundtrip 的锚，必须稳定。其余各处由各自 spec 处置，
 * 不在本 spec 假装一次修完全仓。
 */

/** 铸造计数（出参）。载入路径据此决定是否立即回写 store。 */
export interface F3RowIdentityMintStats {
  minted: number
}

/** 行身份铸造前缀（逐表固定，便于从 id 反查来源表）。 */
export const F3_ROW_ID_PREFIX = {
  overdue: 'f3o',
  relatedParty: 'f3rp',
  voucher: 'f3v',
  detail: 'f3d',
} as const

/** 铸一个稳定行身份。优先 `crypto.randomUUID()`，不可用时退时间戳+随机。 */
export function mintF3RowId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/**
 * 从原始载荷行解析稳定行身份。
 *
 * 语义：
 *   1. `rowId` 或 legacy `id` 非空（trim 后）⇒ **原样保留**（存量身份是稳定的）
 *   2. 两者都缺/为空白 ⇒ 铸新身份，并令 `stats.minted` 自增
 *
 * @param raw    原始行对象（`JSON.parse` 结果的元素）
 * @param prefix 铸造前缀，取 `F3_ROW_ID_PREFIX` 之一
 * @param stats  铸造计数出参；`minted > 0` 时调用方**必须**立即回写 store
 */
export function resolveF3RowId(
  raw: unknown,
  prefix: string,
  stats?: F3RowIdentityMintStats,
): string {
  const source = (raw ?? {}) as Record<string, unknown>
  const existing = String(source.rowId ?? source.id ?? '').trim()
  if (existing) return existing
  if (stats) stats.minted += 1
  return mintF3RowId(prefix)
}
