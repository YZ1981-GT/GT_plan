/**
 * 受限资产共享表勾稽 + 段级溯源（`restrictedAssetsConsistency.ts`）。
 *
 * **Validates: restricted-assets-note-row-scope-rollout Requirements 4.1~4.4
 * / Properties 11, 12, 13**
 */
import { describe, expect, it } from 'vitest'

import {
  computeRestrictedAssetsConsistency,
  describeRestrictedRowProvenance,
  isRestrictedTotalRow,
  resolveRestrictedRowOwner,
  RESTRICTED_ASSETS_OWNER_WP,
  RESTRICTED_TOLERANCE,
  summarizeRestrictedChecks,
  type RestrictedAssetsNoteRow,
} from '../restrictedAssetsConsistency'
import {
  RESTRICTED_ASSETS_OWNERS,
  RESTRICTED_ASSETS_SOE_ONLY_OWNERS,
  type RestrictedAssetsOwner,
} from '../restrictedAssetsNoteSectionMap'
import { RESTRICTED_ASSETS_SOURCES } from '../restrictedAssetsSources'

function listedRows(): RestrictedAssetsNoteRow[] {
  return [
    { label: '货币资金', end_amount: 100 },
    { label: '应收票据', end_amount: 200 },
    { label: '应收账款', end_amount: 300 },
    { label: '存货', end_amount: 0 },
    { label: '固定资产', end_amount: 400 },
    { label: '无形资产', end_amount: 0 },
    { label: '合  计', end_amount: 1000, is_total: true },
  ]
}

function soeRows(): RestrictedAssetsNoteRow[] {
  return [
    { label: '货币资金', end_carrying: 100, reason: '保证金' },
    { label: '应收票据', end_carrying: 200, reason: '已质押' },
    { label: '应收账款', end_carrying: 0, reason: '' },
    { label: '应收款项融资', end_carrying: 0, reason: '' },
    { label: '存货', end_carrying: 0, reason: '' },
    { label: '固定资产', end_carrying: 400, reason: '抵押/担保' },
    { label: '在建工程', end_carrying: 50, reason: '抵押/担保' },
    { label: '无形资产', end_carrying: 0, reason: '' },
    // soe 末行「其他」= 无主行（模板标 row_type: unowned），参与合计但不属任何 owner
    { label: '其他', end_carrying: 25, reason: '其他受限' },
  ]
}

describe('段级溯源 resolveRestrictedRowOwner', () => {
  it('_seg 段戳优先', () => {
    expect(resolveRestrictedRowOwner({ label: '随便改的名字', _seg: 'BS-028' })).toBe('BS-028')
  })

  it('无 _seg 时按行标签反查', () => {
    for (const [code, label] of Object.entries(RESTRICTED_ASSETS_OWNERS)) {
      expect(resolveRestrictedRowOwner({ label })).toBe(code)
    }
  })

  it('无主行 / 合计行 / 非法 _seg → null（不硬塞给某个 owner）', () => {
    expect(resolveRestrictedRowOwner({ label: '其他' })).toBeNull()
    expect(resolveRestrictedRowOwner({ label: '合  计', is_total: true })).toBeNull()
    expect(resolveRestrictedRowOwner({ label: '货币资金x', _seg: 'BS-999' })).toBeNull()
    expect(resolveRestrictedRowOwner({})).toBeNull()
  })
})

describe('段级溯源 describeRestrictedRowProvenance（Req 4.4）', () => {
  it('全 8 段都能推出归属循环', () => {
    expect(Object.keys(RESTRICTED_ASSETS_OWNER_WP).sort()).toEqual(
      Object.keys(RESTRICTED_ASSETS_OWNERS).sort(),
    )
    for (const [code, label] of Object.entries(RESTRICTED_ASSETS_OWNERS)) {
      const p = describeRestrictedRowProvenance({ label })
      expect(p.owner).toBe(code)
      expect(p.wpCode).toBe(RESTRICTED_ASSETS_OWNER_WP[code as RestrictedAssetsOwner])
      expect(p.text).toContain(p.wpCode!)
    }
  })

  it('🔴 与声明表的 wpCode 交叉锁死（改一侧漏一侧必红）', () => {
    for (const s of RESTRICTED_ASSETS_SOURCES) {
      expect(RESTRICTED_ASSETS_OWNER_WP[s.owner], `${s.owner} 两处 wp_code 不一致`).toBe(s.wpCode)
    }
  })

  it('无主行与合计行明确标注「不属任何底稿」', () => {
    expect(describeRestrictedRowProvenance({ label: '其他' })).toMatchObject({
      owner: null,
      wpCode: null,
    })
    expect(describeRestrictedRowProvenance({ label: '其他' }).text).toContain('无主行')
    expect(
      describeRestrictedRowProvenance({ label: '合  计', is_total: true }).text,
    ).toContain('合计行')
  })
})

describe('isRestrictedTotalRow', () => {
  it('is_total 优先，标签去空白后认「合计/小计」', () => {
    expect(isRestrictedTotalRow({ is_total: true, label: '随便' })).toBe(true)
    expect(isRestrictedTotalRow({ label: '合  计' })).toBe(true)
    expect(isRestrictedTotalRow({ label: '合计' })).toBe(true)
    expect(isRestrictedTotalRow({ label: '小 计' })).toBe(true)
    expect(isRestrictedTotalRow({ label: '固定资产' })).toBe(false)
  })
})

describe('Check 1 合计勾稽', () => {
  it('listed：合计 == 各段之和 → ok', () => {
    const checks = computeRestrictedAssetsConsistency({ variant: 'listed', rows: listedRows() })
    const total = checks[0]
    expect(total.label).toBe('合计勾稽')
    expect(total.level).toBe('ok')
    expect(total.left).toBe(1000)
    expect(total.right).toBe(1000)
  })

  it('listed：合计不平 → error 且给出差额', () => {
    const rows = listedRows()
    rows[rows.length - 1].end_amount = 1234
    const [total] = computeRestrictedAssetsConsistency({ variant: 'listed', rows })
    expect(total.level).toBe('error')
    expect(total.diff).toBe(234)
    expect(total.detail).toContain('234.00')
  })

  it(`容差 ${RESTRICTED_TOLERANCE} 元内视为一致`, () => {
    const rows = listedRows()
    rows[rows.length - 1].end_amount = 1000.01
    expect(computeRestrictedAssetsConsistency({ variant: 'listed', rows })[0].level).toBe('ok')
    rows[rows.length - 1].end_amount = 1000.02
    expect(computeRestrictedAssetsConsistency({ variant: 'listed', rows })[0].level).toBe('error')
  })

  it('🔴 soe 源模板无合计行 → skip（不得凭空要求合计行）', () => {
    const [total] = computeRestrictedAssetsConsistency({ variant: 'soe', rows: soeRows() })
    expect(total.level).toBe('skip')
    expect(total.detail).toContain('无合计行')
    // right 仍给出各段之和供参考（含无主行「其他」25）
    expect(total.right).toBe(775)
  })

  it('无主行「其他」计入合计但不属任何 owner', () => {
    const rows = soeRows()
    const owners = rows.map((r) => resolveRestrictedRowOwner(r))
    expect(owners[owners.length - 1]).toBeNull()
    const [total] = computeRestrictedAssetsConsistency({ variant: 'soe', rows })
    expect(total.right).toBe(775)
  })

  it('listed 续表口径取 prior_amount 列', () => {
    const rows: RestrictedAssetsNoteRow[] = [
      { label: '货币资金', prior_amount: 10 },
      { label: '固定资产', prior_amount: 20 },
      { label: '合计', prior_amount: 30, is_total: true },
    ]
    const [total] = computeRestrictedAssetsConsistency({
      variant: 'listed',
      rows,
      usePriorColumn: true,
    })
    expect(total.level).toBe('ok')
    expect(total.left).toBe(30)
  })
})

describe('Check 2 逐段比对', () => {
  it('未提供底稿金额的段一律 skip（不 error）', () => {
    const checks = computeRestrictedAssetsConsistency({ variant: 'soe', rows: soeRows() })
    const segs = checks.filter((c) => c.refs.length === 1)
    expect(segs.length).toBe(Object.keys(RESTRICTED_ASSETS_OWNERS).length)
    expect(segs.every((c) => c.level === 'skip')).toBe(true)
    for (const c of segs) expect(c.detail).toContain('未提供')
  })

  it('提供后一致 → ok；不一致 → error 且带差额与追溯 code', () => {
    const checks = computeRestrictedAssetsConsistency({
      variant: 'soe',
      rows: soeRows(),
      ownerAmounts: { 'BS-028': 400, 'BS-029': 30 },
    })
    const fa = checks.find((c) => c.refs[0] === 'BS-028')!
    expect(fa.level).toBe('ok')
    expect(fa.left).toBe(400)
    const cip = checks.find((c) => c.refs[0] === 'BS-029')!
    expect(cip.level).toBe('error')
    expect(cip.diff).toBe(20)
    expect(cip.label).toContain('在建工程')
  })

  it('listed 侧不出 soe 专有段（BS-007 / BS-029）', () => {
    const checks = computeRestrictedAssetsConsistency({ variant: 'listed', rows: listedRows() })
    const codes = checks.flatMap((c) => c.refs)
    for (const soeOnly of RESTRICTED_ASSETS_SOE_ONLY_OWNERS) {
      expect(codes, `listed 不该出现 ${soeOnly}`).not.toContain(soeOnly)
    }
    expect(codes).toContain('BS-002')
  })

  it('段有多行时求和（行级合并允许段内行数 ≠ 模板段行数）', () => {
    const rows: RestrictedAssetsNoteRow[] = [
      { label: '固定资产', _seg: 'BS-028', end_carrying: 100 },
      { label: '固定资产-厂房', _seg: 'BS-028', end_carrying: 250 },
    ]
    const checks = computeRestrictedAssetsConsistency({
      variant: 'soe',
      rows,
      ownerAmounts: { 'BS-028': 350 },
    })
    expect(checks.find((c) => c.refs[0] === 'BS-028')!.level).toBe('ok')
  })
})

describe('Check 3 _seg 泄漏', () => {
  it('行里带 _seg → error（平台缺陷，会渲染出一列垃圾）', () => {
    const checks = computeRestrictedAssetsConsistency({
      variant: 'soe',
      rows: [{ label: '固定资产', _seg: 'BS-028', end_carrying: 1 }],
    })
    const leak = checks.find((c) => c.label === '_seg 段戳泄漏')!
    expect(leak.level).toBe('error')
    expect(leak.diff).toBe(1)
  })

  it('正常读时投影（无 _seg）→ 不产出该条', () => {
    const checks = computeRestrictedAssetsConsistency({ variant: 'soe', rows: soeRows() })
    expect(checks.some((c) => c.label === '_seg 段戳泄漏')).toBe(false)
  })
})

describe('汇总与稳定性', () => {
  it('summarizeRestrictedChecks 分级计数', () => {
    const checks = computeRestrictedAssetsConsistency({
      variant: 'soe',
      rows: soeRows(),
      ownerAmounts: { 'BS-028': 400, 'BS-029': 30 },
    })
    const s = summarizeRestrictedChecks(checks)
    expect(s.total).toBe(checks.length)
    expect(s.ok).toBe(1)
    expect(s.error).toBe(1)
    expect(s.ok + s.error + s.skip).toBe(s.total)
  })

  it('同一输入连续两次结果逐字节相等（纯函数）', () => {
    const input = {
      variant: 'listed' as const,
      rows: listedRows(),
      ownerAmounts: { 'BS-002': 100 } as Partial<Record<RestrictedAssetsOwner, number>>,
    }
    expect(JSON.stringify(computeRestrictedAssetsConsistency(input))).toBe(
      JSON.stringify(computeRestrictedAssetsConsistency(input)),
    )
  })

  it('空行集不崩：合计 skip + 全部段 skip', () => {
    const checks = computeRestrictedAssetsConsistency({ variant: 'listed', rows: [] })
    expect(checks[0].level).toBe('skip')
    expect(checks.every((c) => c.level === 'skip')).toBe(true)
  })

  it('非法金额（null / NaN / 字符串）按 0 处理，不产生 NaN', () => {
    const rows: RestrictedAssetsNoteRow[] = [
      { label: '货币资金', end_amount: null },
      { label: '固定资产', end_amount: Number.NaN },
      { label: '存货', end_amount: 'abc' as unknown as number },
      { label: '合计', end_amount: 0, is_total: true },
    ]
    const [total] = computeRestrictedAssetsConsistency({ variant: 'listed', rows })
    expect(total.right).toBe(0)
    expect(total.level).toBe('ok')
  })
})
