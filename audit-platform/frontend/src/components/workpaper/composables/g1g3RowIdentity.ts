/**
 * G1 / G3 行身份铸造 —— BP-7（下标派生行身份）+ Req 1.3（timestamp 无随机后缀）的单点修复。
 *
 * spec: g-cycle-single-region-detail-lanes · Task 7 · Requirements 1.3
 *       · Property 2（G1R-P2：timestamp 型 id 有随机后缀或已修）
 *
 * ═══ 为什么只修 G1 / G3 两条 ═══
 *
 * slice `workpaper_sync_g_cycle_manifest_slice.json` 给 **六条** entry 标了 BP-7
 * （G1 / G3 / G10 / G11 / G12 / G13），但 BP-7 正文只展开 `useG6SppiFairValue.ts` 一处。
 * Task 2 按值 grep 九条主表 composable 实测（证据 `evidence/task2-geometry-and-field-probes.md` §3）：
 *
 * | entry | 下标派生 id | timestamp 无随机后缀 | 判定 |
 * |---|---|---|---|
 * | **G1** | `useG1Detail.ts:442` | `useG1Detail.ts:704` | 🔴 真命中 |
 * | **G3** | `useG3Detail.ts:288` | `useG3Detail.ts:358` | 🔴 真命中 |
 * | G10 / G11 / G12 / G13 | 无（`i+1` 只喂 `seq`） | 无（id 生成均带 `Math.random()`） | slice 误标 |
 *
 * ⇒ 本模块只服务 G1 / G3。四条误标的反证已登记，**未伪造缺陷、未静默抹掉 slice 标记**。
 *
 * ═══ 三种旧形态与各自处置（逐字对应，不泛化猜测）═══
 *
 * | 旧形态 | 出处 | 处置 | 理由 |
 * |---|---|---|---|
 * | `String(i + 1)` → `"1"`/`"2"`… | `useG1Detail:442` `useG3Detail:288` | **重铸** | 纯下标：删中间一行后其后所有行身份整体前移 |
 * | `emptyRow('1', 1)` 空表兜底 | 两文件各 3 处 | **重铸** | 不同底稿的第一行 id 都是 `'1'` |
 * | `` `row-${Date.now()}` `` | `useG1Detail:704` `useG3Detail:358` | **保留，仅去重时重铸** | 它已近似唯一；无条件重铸会让每次载入都换身份（比原缺陷更糟） |
 *
 * 🔴 **`row-<ts>` 不无条件重铸**是刻意的：F5 的同族修复（`f5RowIdentity.ts`）把旧形态一律重铸，
 * 那是因为它的三处旧形态**都含下标**。G1/G3 的 timestamp 形态不含下标，唯一风险是
 * **同毫秒连加两行撞 id** ⇒ 正确的修法是「生成端加随机后缀」+「载入端同载荷内去重」，
 * 而不是「载入端一律重铸」。
 *
 * ═══ 回写义务 ═══
 *
 * 铸造次数经 `RowIdentityMintStats.minted` 回传，调用方 `loadRows()` 须据此**立即回写**
 * —— 不回写则 store 里仍是旧 id，下次载入又铸一批新的 ⇒ 身份每次都变（同 F5 的教训）。
 */

/** 铸造计数（出参）。`loadRows()` 据此决定是否立即回写。 */
export interface RowIdentityMintStats {
  /** 本次载入铸了几个新身份 */
  minted: number
  /** 其中因「同载荷内 id 重复」而重铸的个数（`row-<ts>` 撞 id 的实证计数） */
  deduped: number
}

export function createMintStats(): RowIdentityMintStats {
  return { minted: 0, deduped: 0 }
}

/**
 * 纯数字 id ⇒ 下标派生（`String(i + 1)` 与 `emptyRow('1', 1)` 两种旧写法的共同形态）。
 *
 * 🔴 逐字对应旧写法，不是泛化猜测：两文件里产生 id 的地方只有三处
 * （`String(i + 1)` / 字面量 `'1'` / `` `row-${Date.now()}` ``），前两处产出的都是纯数字串。
 */
const ORDINAL_ID_PATTERN = /^\d+$/

/**
 * `` `row-${Date.now()}` `` 形态（`row-` + 10 位以上毫秒时间戳，**无随机后缀**）。
 *
 * 命中**不重铸**（见模块头「三种旧形态」表），只在同载荷内撞 id 时对后来者重铸。
 */
const BARE_TIMESTAMP_ID_PATTERN = /^row-\d{10,}$/

export function isOrdinalRowId(value: unknown): boolean {
  return ORDINAL_ID_PATTERN.test(String(value ?? '').trim())
}

export function isBareTimestampRowId(value: unknown): boolean {
  return BARE_TIMESTAMP_ID_PATTERN.test(String(value ?? '').trim())
}

/**
 * 铸一段**不含前缀**的唯一后缀。优先 `crypto.randomUUID()`，不可用时退时间戳 + 随机。
 *
 * 🔴 为什么本模块只出后缀、不出整个 id：前缀（`g1d` / `g3d`）必须**内联在消费方的铸造点**
 * ——「行身份形态回源码核对」的判据要在声明 `id: string` 行模型的那个文件里逐字找到
 * `` `g1d-${…}` ``。若前缀常量存在本模块（原 `G_ROW_ID_PREFIX`），前缀字面量就跨文件了：
 * 消费方源码里只剩 `newRowId(G_ROW_ID_PREFIX.g1Detail)`，形态无法回源。让消费方持有前缀
 * 还顺带消掉了「同一个 `'g1d'` 字面量两处声明」的漂移面（本模块的常量表 vs 铸造点）。
 */
export function mintRowIdSuffix(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/**
 * 批量解析一批载荷行的稳定行身份。
 *
 * 🔴 **必须批量**（而非逐行）：去重需要看到同一载荷里的其它 id。逐行 API 无法发现
 * `` `row-${Date.now()}` `` 同毫秒撞出的两个相同 id。
 *
 * @param rawList 原始行数组（`JSON.parse` 的结果）
 * @param mint    铸造器（消费方的 `genRowId`，前缀内联在那边，见 `mintRowIdSuffix` 注释）
 * @param stats   铸造计数出参
 * @returns 与 `rawList` 等长、逐位对应的行身份数组（保证两两不同且非空）
 */
export function resolveStableRowIds(
  rawList: readonly unknown[],
  mint: () => string,
  stats?: RowIdentityMintStats,
): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of rawList) {
    const source = (raw ?? {}) as Record<string, unknown>
    const candidate = String(source.id ?? '').trim()
    let resolved: string
    if (!candidate || isOrdinalRowId(candidate)) {
      // 缺 id 或下标派生 ⇒ 重铸
      resolved = mint()
      if (stats) stats.minted += 1
    } else if (seen.has(candidate)) {
      // 同载荷内撞 id（`row-<ts>` 同毫秒连加的实证形态）⇒ 后来者重铸
      resolved = mint()
      if (stats) {
        stats.minted += 1
        stats.deduped += 1
      }
    } else {
      resolved = candidate
    }
    seen.add(resolved)
    out.push(resolved)
  }
  return out
}

// 🔴 这里原先还有 `newRowId(prefix)` + `G_ROW_ID_PREFIX = { g1Detail: 'g1d', g3Detail: 'g3d' }`。
//    两者已删：前缀改由消费方内联持有（`useG1Detail.genRowId` / `useG3Detail.genRowId`），
//    理由见 `mintRowIdSuffix` 的注释（形态要能在声明行模型的那个文件里逐字回源）。
