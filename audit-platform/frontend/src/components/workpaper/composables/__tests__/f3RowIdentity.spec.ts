import { describe, expect, it } from 'vitest'

import {
  F3_ROW_ID_PREFIX,
  mintF3RowId,
  resolveF3RowId,
  type F3RowIdentityMintStats,
} from '../f3RowIdentity'
import { safeParseOverdueRows } from '../useF3OverdueCheck'
import { safeParseRelatedPartyRows } from '../useF3RelatedParty'
import { safeParseVoucherRows } from '../useF3VoucherCheck'

/**
 * f3RowIdentity —— F3 四张受管 sheet 的行身份单源。
 *
 * spec: f3-sync-coverage-and-first-canary · Task 13 / 14 / 15
 *
 * 被修的缺陷：`rowId: raw.rowId || raw.id || generateRowId()` 铸新身份却不回写 store，
 * 下次载入再铸一个新的 ⇒ 同一逻辑行身份每次都变，OO↔HTML roundtrip 会把 A 行的值
 * 并进 B 行（与 BP-7 下标派生同型危害）。
 */
describe('f3RowIdentity 单源语义', () => {
  it('已有 rowId 原样保留，不计数', () => {
    const stats: F3RowIdentityMintStats = { minted: 0 }
    expect(resolveF3RowId({ rowId: 'f3o-keep' }, F3_ROW_ID_PREFIX.overdue, stats)).toBe('f3o-keep')
    expect(stats.minted).toBe(0)
  })

  it('兼容 legacy `id` 字段（视为已有身份）', () => {
    const stats: F3RowIdentityMintStats = { minted: 0 }
    expect(resolveF3RowId({ id: 'legacy-9' }, F3_ROW_ID_PREFIX.detail, stats)).toBe('legacy-9')
    expect(stats.minted).toBe(0)
  })

  it('rowId 优先于 id（两者都有时取 rowId）', () => {
    expect(resolveF3RowId({ rowId: 'r1', id: 'i1' }, F3_ROW_ID_PREFIX.voucher)).toBe('r1')
  })

  it('缺身份时铸新并计数，带表级前缀', () => {
    const stats: F3RowIdentityMintStats = { minted: 0 }
    const id = resolveF3RowId({ foo: 1 }, F3_ROW_ID_PREFIX.relatedParty, stats)
    expect(id.startsWith('f3rp-')).toBe(true)
    expect(stats.minted).toBe(1)
  })

  it('空串与纯空格算缺身份', () => {
    const stats: F3RowIdentityMintStats = { minted: 0 }
    resolveF3RowId({ rowId: '' }, F3_ROW_ID_PREFIX.overdue, stats)
    resolveF3RowId({ rowId: '   ' }, F3_ROW_ID_PREFIX.overdue, stats)
    resolveF3RowId({ id: '\t' }, F3_ROW_ID_PREFIX.overdue, stats)
    expect(stats.minted).toBe(3)
  })

  it('null / undefined / 非对象入参不抛', () => {
    for (const raw of [null, undefined, 42, 'x', []]) {
      expect(() => resolveF3RowId(raw, F3_ROW_ID_PREFIX.detail)).not.toThrow()
    }
  })

  it('stats 省略时照样铸新（向后兼容）', () => {
    expect(resolveF3RowId({}, F3_ROW_ID_PREFIX.voucher).startsWith('f3v-')).toBe(true)
  })

  it('铸出的身份互不相同', () => {
    const ids = new Set(Array.from({ length: 50 }, () => mintF3RowId('f3x')))
    expect(ids.size).toBe(50)
  })

  it('🔴 刻意不做 legacy 下标形态重铸 —— 那会把稳定的存量身份误判', () => {
    // F5 的 BP-7 需要重铸 `m-<ts>-<i>` 这类含下标的旧 id；F3 的 generateRowId
    // 产出 `<prefix>-<ts36>-<rand>` 不含下标，存量 id 是稳定的。
    // 若这里也加 legacy 检测，会把正常身份重铸 —— 那才是引入身份漂移。
    const stats: F3RowIdentityMintStats = { minted: 0 }
    const legacyLooking = 'f3o-m9x2-ab12cd'
    expect(resolveF3RowId({ rowId: legacyLooking }, F3_ROW_ID_PREFIX.overdue, stats)).toBe(
      legacyLooking,
    )
    expect(stats.minted).toBe(0)
  })

  it('四个表级前缀互不相同（便于从 id 反查来源表）', () => {
    const prefixes = Object.values(F3_ROW_ID_PREFIX)
    expect(new Set(prefixes).size).toBe(prefixes.length)
    expect(prefixes).toEqual(['f3o', 'f3rp', 'f3v', 'f3d'])
  })
})

describe('F3 四张受管 sheet 的载入路径都会上报铸造数', () => {
  // 🔴 这组判据锁的是"四处都接了单源"，防止其中一处回退成内联写法后无人发现。
  it('F3-5 逾期票据：缺 rowId 的行铸新并计数', () => {
    const stats: F3RowIdentityMintStats = { minted: 0 }
    const rows = safeParseOverdueRows(
      JSON.stringify([{ ticketNo: 'T-1', faceValue: 100 }]),
      stats,
    )
    expect(rows.length).toBeGreaterThan(0)
    expect(stats.minted).toBe(1)
    expect(rows[0].rowId.startsWith('f3o-')).toBe(true)
  })

  it('F3-6 关联方：缺 rowId 的行铸新并计数', () => {
    const stats: F3RowIdentityMintStats = { minted: 0 }
    const rows = safeParseRelatedPartyRows(
      JSON.stringify([{ partyName: '甲', creditMovement: 100 }]),
      stats,
    )
    expect(stats.minted).toBe(1)
    expect(rows[0].rowId.startsWith('f3rp-')).toBe(true)
  })

  it('F3-7 三区：每个区各自上报（区间互不影响）', () => {
    for (const section of ['debit', 'credit', 'subsequent'] as const) {
      const stats: F3RowIdentityMintStats = { minted: 0 }
      const rows = safeParseVoucherRows(
        JSON.stringify([{ voucherNo: `V-${section}`, amount: 1 }]),
        section,
        stats,
      )
      expect(stats.minted).toBe(1)
      expect(rows[0].rowId.startsWith('f3v-')).toBe(true)
    }
  })

  it('已有身份时四处都不计数（不会误重铸）', () => {
    const overdue: F3RowIdentityMintStats = { minted: 0 }
    safeParseOverdueRows(JSON.stringify([{ rowId: 'f3o-x', ticketNo: 'T' }]), overdue)
    expect(overdue.minted).toBe(0)

    const related: F3RowIdentityMintStats = { minted: 0 }
    safeParseRelatedPartyRows(
      JSON.stringify([{ rowId: 'f3rp-x', partyName: '甲', creditMovement: 1 }]),
      related,
    )
    expect(related.minted).toBe(0)

    const voucher: F3RowIdentityMintStats = { minted: 0 }
    safeParseVoucherRows(
      JSON.stringify([{ rowId: 'f3v-x', voucherNo: 'V', amount: 1 }]),
      'debit',
      voucher,
    )
    expect(voucher.minted).toBe(0)
  })
})
