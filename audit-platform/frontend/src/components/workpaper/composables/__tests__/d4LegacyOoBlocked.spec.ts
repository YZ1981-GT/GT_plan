/**
 * D4 legacy OnlyOffice 通道禁入名单守卫
 *
 * 背景：`GtOnlyOfficeSheet` 是 legacy 单向通道（平台口径「假双向」）。对「有结构化 store
 * 载荷、却尚未接双向同步桥」的表，进这条通道 = 用户能编辑但改动不回 HTML store（静默丢失）。
 *
 * 本守卫钉死两个方向（缺一即无效）：
 *   ① 正向：禁入表确实被挡（D4-4）；
 *   ② 反向（变异证明）：非禁入表**仍然放行** —— 否则「把 legacy 通道整个堵死」也能让①变绿，
 *      而那会破坏 D4 / D4A / D4-22A / D4-31T 这些无 store 载荷表「看原册」的合理用途。
 */
import { describe, it, expect } from 'vitest'
import { D4_LEGACY_OO_BLOCKED_SHEETS, isD4LegacyOoBlocked } from '../d4Constants'

// 宿主 GtD4OperatingRevenue 的两个桥名单（与其源码保持同步，用于推导 legacy 命中集）
const HOST_BRIDGE_SHEETS = ['D4-2', 'D4-3', 'D4-6', 'D4-7', 'D4-30', 'D4-31', 'D4-32']
const DEDICATED_SYNC_SHEETS = [
  // 'D4-4' 于 2026-09-28 接入真双向（spec d4-4-adjustment-summary-bidirectional-writeback）
  'D4-1', 'D4-4', 'D4-5', 'D4-6', 'D4-7', 'D4-8', 'D4-9', 'D4-10', 'D4-11', 'D4-12', 'D4-13',
  'D4-14', 'D4-15', 'D4-16', 'D4-17', 'D4-18', 'D4-19', 'D4-20', 'D4-21', 'D4-22',
  'D4-23', 'D4-24', 'D4-25', 'D4-26', 'D4-27', 'D4-28', 'D4-29', 'D4-30', 'D4-31',
  'D4-32', 'D4-33', 'D4-34', 'D4-35', 'D4-36',
]
// 宿主 KNOWN_HTML_SHEETS 全集（38 码）
const KNOWN_HTML_SHEETS = [
  'D4', 'D4A', 'D4-22A', 'D4-31T',
  ...Array.from({ length: 36 }, (_, i) => `D4-${i + 1}`),
]

describe('D4 legacy OnlyOffice 禁入名单', () => {
  it('① D4-4 已摘出名单（2026-09-28 接入真双向，契约已有 d44-managed）', () => {
    // 期望从 true 翻 false：接桥后必须摘出，否则 isLegacyOoBlocked 会让 renderMode 恒
    // 'html'、切换器恒 disabled ⇒ 新做的双向入口被自己的禁入名单挡掉（Task 12）。
    expect(isD4LegacyOoBlocked('D4-4')).toBe(false)
  })

  it('① D4-4 的排除成因是「已接 dedicated 桥」而非「在禁入名单里」', () => {
    // 🔴 钉死成因而不只是结果：下面「推导 legacy 命中集」那条用例的期望值在本次改动
    //    前后**恰好相同**（D4-4 原先被名单挡住、现在被 bridged 排除，两条路径都不进
    //    命中集）。只看结果无法区分这两种状态 —— 若将来 D4-4 从 dedicated 掉出来又
    //    没回名单，它会掉进 legacy 单向通道而命中集用例**也会**打红，但归因会很慢。
    //    这一条让成因本身可见。
    expect(DEDICATED_SYNC_SHEETS).toContain('D4-4')
    expect(D4_LEGACY_OO_BLOCKED_SHEETS.has('D4-4')).toBe(false)
  })

  it('① D4-5 在名单内（历史单点特判 currentSheet !== "D4-5" 收敛至此，行为等价）', () => {
    expect(isD4LegacyOoBlocked('D4-5')).toBe(true)
  })

  it('② 变异证明：无 store 载荷的表仍可走 legacy「看原册」，未被一刀切堵死', () => {
    // 这 4 张是 legacy 通道的合理用途：D4 目录页 / D4A、D4-22A 程序表 / D4-31T 访谈示例
    for (const code of ['D4', 'D4A', 'D4-22A', 'D4-31T']) {
      expect(isD4LegacyOoBlocked(code)).toBe(false)
    }
  })

  it('② 变异证明：已接双向桥的表不靠本名单排除（由 dedicated/host 桥各自处置）', () => {
    // D4-5 是刻意的历史冗余项，其余 dedicated 表一律不应进本名单
    const dedicatedInBlocklist = DEDICATED_SYNC_SHEETS.filter(c => isD4LegacyOoBlocked(c))
    expect(dedicatedInBlocklist).toEqual(['D4-5'])
  })

  it('名单与两个桥名单的交集只允许 D4-5 这一个已知冗余项', () => {
    const bridged = new Set([...HOST_BRIDGE_SHEETS, ...DEDICATED_SYNC_SHEETS])
    const overlap = [...D4_LEGACY_OO_BLOCKED_SHEETS].filter(c => bridged.has(c))
    expect(overlap).toEqual(['D4-5'])
  })

  // 🔴 现算结论：本条期望值在 D4-4 接桥前后**不变**（仍 4 张）。
  //    spec 原文预期它"从 4 张变 5 张"，但那是把「D4-4 摘出名单」单独看的结果 ——
  //    D4-4 同时进了 dedicated，于是被第一个 filter（`!bridged.has`）排除，
  //    仍不进命中集。**期望值不变、成因改变**，由上面「排除成因」那条用例覆盖。
  it('推导 legacy 实际命中集：恰为 4 张无 store 载荷表（D4-4 现由 dedicated 排除）', () => {
    const bridged = new Set([...HOST_BRIDGE_SHEETS, ...DEDICATED_SYNC_SHEETS])
    const legacyHits = KNOWN_HTML_SHEETS
      .filter(c => !bridged.has(c))
      .filter(c => !isD4LegacyOoBlocked(c))
      .sort()
    expect(legacyHits).toEqual(['D4', 'D4-22A', 'D4-31T', 'D4A'])
  })

  it('空值/未知 sheet 不误判为禁入（默认放行，避免挡住新增表）', () => {
    expect(isD4LegacyOoBlocked(null)).toBe(false)
    expect(isD4LegacyOoBlocked(undefined)).toBe(false)
    expect(isD4LegacyOoBlocked('')).toBe(false)
    expect(isD4LegacyOoBlocked('D4-99')).toBe(false)
  })

  it('变异反证：名单里若留着 D4-4，本套用例必须打红（证明判据非恒真）', () => {
    // spec Task 13 要求这条「须实做」。用一个**模拟名单**复现「忘摘 D4-4」的状态，
    // 证明相关判据确实有区分力 —— 而不是无论名单怎样都绿。
    const notYetMigrated: ReadonlySet<string> = new Set(['D4-4', 'D4-5'])
    const stillBlocked = (code: string) => notYetMigrated.has(code)

    // ① 期望翻转那条会红
    expect(stillBlocked('D4-4')).toBe(true) // 与真实现的 false 相反

    // ② 「dedicated 表不进名单」那条会红：D4-4 既在 dedicated 又在名单
    const dedicatedInBlocklist = DEDICATED_SYNC_SHEETS.filter(stillBlocked)
    expect(dedicatedInBlocklist).not.toEqual(['D4-5'])
    expect(dedicatedInBlocklist.sort()).toEqual(['D4-4', 'D4-5'])

    // ③ 「交集只允许 D4-5」那条会红
    const bridged = new Set([...HOST_BRIDGE_SHEETS, ...DEDICATED_SYNC_SHEETS])
    const overlap = [...notYetMigrated].filter((c) => bridged.has(c))
    expect(overlap).not.toEqual(['D4-5'])

    // 而真实名单不含 D4-4（前面各条据此为绿）
    expect(D4_LEGACY_OO_BLOCKED_SHEETS.has('D4-4')).toBe(false)
  })
})
