/**
 * J2/J3 行身份铸造 —— JN-4（non_entry 位置化行身份）的单点修复。
 *
 * spec: `j2-j3-non-entry-hosts-and-orphan-cleanup` · Task 11 / Task 12
 *       · JN-P19 / JN-P20 · 口径引 JC-6（不复述正文）
 *
 * ═══ 为什么不复用 `f5RowIdentity.ts` / `hSeedRowIdentity.ts` ═══
 *
 * 那两套铸 **string**（`f5m-<uuid>`）。J2/J3 五处的 `id` 是 **number**，并且宿主用
 * `seq = Math.max(0, ...rows.map(r => r.id)) + 1` 做自增游标、用 `r.id === row.id`
 * 做行定位。换成 string 会同时打断：
 *   ① `Math.max(...)` 在 string 上返回 `NaN` ⇒ 之后每次新增都是 `NaN`
 *   ② `SbpRow.id: number` 等类型声明（5 处宿主共 4 个行接口）
 *   ③ 已落库数据的类型（真库实证：`J2-3-entries` 与 `J3-2-variation` 的 `"id":1` 是数字）
 * ⇒ 本文件铸 **number**，保持与既有自增/定位/类型三者兼容。
 *
 * ═══ 缺陷形态（现算，五处） ═══
 *
 * | 族 | 位置 | 改造前写法 |
 * |---|---|---|
 * | family_a | `j2/J2TabAdjustment.vue#L104`    | `id: i + 1`（htmlData 派生，**无**上游兜底） |
 * | family_b | `j2/J2TabAdjustment.vue#L111`    | `id: e.id ?? i + 1` |
 * | family_b | `j3/core/J3TabCheck.vue#L103`    | `id: r.id ?? i + 1` |
 * | family_b | `j3/core/J3TabCheck.vue#L105`    | `id: r.id ?? i + 1` |
 * | family_b | `j3/core/J3TabDetail.vue#L126`   | `id: p.id ?? i + 1` |
 *
 * 危害：删中间一行再新增 ⇒ 后续行 id 左移，备注/结论串行到别的行上。
 *
 * ═══ grandfather：已落库的 1..N 一律不重写 ═══
 *
 * 🔴 真库实证**两族都有**已落库的下标身份（不只 family_a）：
 *   · `J2-3-entries`    171 B — `[{"id":1,"description":"重分类一年内到期辞退福利",…}]`
 *   · `J3-2-variation`  288 B — `[{"id":1,"category":"","time":"2024年度",…}]`
 * 后者由 family_b 的回落分支产生 ⇒ **若只对 family_a 做 grandfather，修 family_b 时会
 * 重写 `J3-2-variation` 的 id = 换身份**。所以本文件的策略对两族一致：
 * **上游有 id 就原样保留**（含 `1`），只在**确实缺 id** 时才铸新的。
 *
 * 这与 `f5RowIdentity.ts` 的「id 命中旧下标模式 ⇒ 重铸」**刻意相反**：
 * F5 侧旧 id 带可识别前缀（`oc-migrated-3`）能安全区分「旧格式」与「真身份」；
 * J 侧旧 id 就是裸数字 `1`，**无法**区分「历史下标 1」与「合法身份 1」
 * ⇒ 重铸必然误伤，只能 grandfather。
 */

/** 铸造计数（出参）。调用方据此决定是否立即回写 store。 */
export interface JRowIdentityMintStats {
  minted: number
}

/**
 * 铸一个安全的 number 行身份。
 *
 * 形态 `<毫秒时间戳><3 位随机>`：
 *   · 含 `Math.random()` ⇒ 同一毫秒内连续新增也不撞（JC-6 要求）
 *   · **不含数组下标** ⇒ 插删行不改变已有行身份
 *   · 仍是 number ⇒ `Math.max(...)` 自增游标与 `r.id === row.id` 定位都不变
 *   · 量级 ~1.7e15 < `Number.MAX_SAFE_INTEGER`(9.0e15) ⇒ 不丢精度
 *
 * @param existing 现有行的 id 列表；用于保证新 id 严格大于所有现存 id
 *                 （宿主的 `seq` 游标语义是「下一个更大的数」，保持该不变式）
 */
export function mintJRowId(existing: readonly number[] = []): number {
  const stamp = Date.now() * 1000 + Math.floor(Math.random() * 1000)
  let max = 0
  for (const v of existing) {
    if (typeof v === 'number' && Number.isFinite(v) && v > max) max = v
  }
  return stamp > max ? stamp : max + 1
}

/**
 * 解析行身份：上游有就用（**grandfather**），缺了才铸。
 *
 * 🔴 判「缺」只看 `null` / `undefined` / 空串 / 非有限数 —— **不**把 `1..N` 当旧格式重铸
 * （理由见文件头：J 侧裸数字 id 无法区分历史下标与合法身份）。
 *
 * @param raw      原始行对象（JSON.parse 结果元素，或 htmlData 派生对象）
 * @param existing 现有行 id 列表（铸造时用于保证单调）
 * @param stats    铸造计数出参
 */
export function resolveJRowId(
  raw: unknown,
  existing: readonly number[] = [],
  stats?: JRowIdentityMintStats,
): number {
  const source = (raw ?? {}) as Record<string, unknown>
  const candidate = source.id
  if (typeof candidate === 'number' && Number.isFinite(candidate)) {
    return candidate
  }
  if (typeof candidate === 'string' && candidate.trim() !== '') {
    const parsed = Number(candidate)
    if (Number.isFinite(parsed)) return parsed
  }
  if (stats) stats.minted += 1
  return mintJRowId(existing)
}

/**
 * 给一批行补齐身份，返回新数组（不改入参）。
 *
 * 🔴 逐行**累积**已用 id，避免同一批内互撞（`mintJRowId` 只看传入的 existing）。
 */
export function withJRowIds<T extends { id?: unknown }>(
  rows: readonly T[],
  seed: readonly number[] = [],
  stats?: JRowIdentityMintStats,
): Array<T & { id: number }> {
  const used: number[] = [...seed]
  const out: Array<T & { id: number }> = []
  for (const row of rows) {
    const id = resolveJRowId(row, used, stats)
    used.push(id)
    out.push({ ...(row as T), id })
  }
  return out
}
