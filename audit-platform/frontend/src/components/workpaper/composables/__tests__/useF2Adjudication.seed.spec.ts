import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF2Adjudication, type TbValuesEntry } from '../useF2Adjudication'

/**
 * 辅助：构建最小 UseF2AdjudicationOptions 用于测试 seedFromTbValues
 */
function buildOpts(
  tbValues: Record<string, TbValuesEntry>,
  existingResponses?: Map<string, any>,
) {
  const map = existingResponses ?? new Map<string, any>()
  return {
    wpId: ref('wp-test'),
    projectId: ref('proj-test'),
    allResponses: ref(map),
    debouncedSave: () => {},
    isReadonly: ref(false),
    tbValues: ref(tbValues as Record<string, TbValuesEntry> | null),
  }
}

describe('seedFromTbValues', () => {
  it('test_seed_new_structure_direct_fill — 灰度开(含 increase/decrease)直接填三字段', () => {
    const tbValues: Record<string, TbValuesEntry> = {
      'raw-materials': { opening: 100, closing: 150, increase: 80, decrease: 30 },
    }
    const opts = buildOpts(tbValues)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    // opening 直填
    expect(map.get('F2-1-gross-raw-materials-opening')?.conclusion).toBe('100')
    // increase 直填(不是 closing - opening = 50)
    expect(map.get('F2-1-gross-raw-materials-increase')?.conclusion).toBe('80')
    // decrease 直填
    expect(map.get('F2-1-gross-raw-materials-decrease')?.conclusion).toBe('30')
  })

  it('test_seed_old_structure_guess — 灰度关(只有 opening/closing)粗猜 increase', () => {
    const tbValues: Record<string, TbValuesEntry> = {
      'raw-materials': { opening: 100, closing: 150 },
    }
    const opts = buildOpts(tbValues)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    // opening 填入
    expect(map.get('F2-1-gross-raw-materials-opening')?.conclusion).toBe('100')
    // 粗猜 increase = closing - opening = 50 > 0 → 填 increase
    expect(map.get('F2-1-gross-raw-materials-increase')?.conclusion).toBe('50')
    // decrease 不填（inc > 0）
    expect(map.has('F2-1-gross-raw-materials-decrease')).toBe(false)
  })

  it('test_seed_old_structure_guess_decrease — 灰度关 closing < opening → 填 decrease', () => {
    const tbValues: Record<string, TbValuesEntry> = {
      'finished-goods': { opening: 200, closing: 120 },
    }
    const opts = buildOpts(tbValues)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    expect(map.get('F2-1-gross-finished-goods-opening')?.conclusion).toBe('200')
    // inc = 120 - 200 = -80 < 0 → 填 decrease = 80
    expect(map.has('F2-1-gross-finished-goods-increase')).toBe(false)
    expect(map.get('F2-1-gross-finished-goods-decrease')?.conclusion).toBe('80')
  })

  it('test_seed_does_not_overwrite_existing — 已有值不覆盖(Property 4)', () => {
    // 当 allResponses 中已有 F2-1 区块数据时，整个 seed 被跳过
    const tbValues: Record<string, TbValuesEntry> = {
      'raw-materials': { opening: 999, closing: 1000, increase: 50, decrease: 49 },
    }
    const existing = new Map<string, any>()
    existing.set('F2-1-gross-raw-materials-opening', {
      item_id: 'F2-1-gross-raw-materials-opening',
      conclusion: '500',
      remark: null,
    })
    const opts = buildOpts(tbValues, existing)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    // 已有 F2-1-gross-* 键 → 整个 seed 跳过，opening 保持不变
    expect(map.get('F2-1-gross-raw-materials-opening')?.conclusion).toBe('500')
    // increase/decrease 不会被填入（seed 整体跳过）
    expect(map.has('F2-1-gross-raw-materials-increase')).toBe(false)
    expect(map.has('F2-1-gross-raw-materials-decrease')).toBe(false)
  })

  it('test_seed_impairment_new_structure — 跌价 impairment block 新结构直填', () => {
    const tbValues: Record<string, TbValuesEntry> = {
      'impairment-provision': { opening: 50, closing: 80, increase: 40, decrease: 10 },
    }
    const opts = buildOpts(tbValues)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    // impairment-provision 走 impairment block
    expect(map.get('F2-1-impairment-impairment-provision-opening')?.conclusion).toBe('50')
    expect(map.get('F2-1-impairment-impairment-provision-increase')?.conclusion).toBe('40')
    expect(map.get('F2-1-impairment-impairment-provision-decrease')?.conclusion).toBe('10')
    // 不应走 gross block
    expect(map.has('F2-1-gross-impairment-provision-opening')).toBe(false)
  })

  it('test_seed_impairment_old_structure — 跌价旧结构粗猜', () => {
    const tbValues: Record<string, TbValuesEntry> = {
      'impairment-provision': { opening: 50, closing: 80 },
    }
    const opts = buildOpts(tbValues)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    expect(map.get('F2-1-impairment-impairment-provision-opening')?.conclusion).toBe('50')
    // inc = 80 - 50 = 30 > 0 → increase
    expect(map.get('F2-1-impairment-impairment-provision-increase')?.conclusion).toBe('30')
    expect(map.has('F2-1-impairment-impairment-provision-decrease')).toBe(false)
  })

  it('test_seed_skipped_when_adjudication_data_exists — 已有 F2-adjudication-data 则跳过', () => {
    const tbValues: Record<string, TbValuesEntry> = {
      'raw-materials': { opening: 100, closing: 200, increase: 120, decrease: 20 },
    }
    const existing = new Map<string, any>()
    existing.set('F2-adjudication-data', { item_id: 'F2-adjudication-data', conclusion: '{}', remark: null })
    const opts = buildOpts(tbValues, existing)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    // 不应新增任何 seed
    expect(map.has('F2-1-gross-raw-materials-opening')).toBe(false)
  })

  it('test_seed_zero_values_not_written — 零值不写入', () => {
    const tbValues: Record<string, TbValuesEntry> = {
      'raw-materials': { opening: 0, closing: 0, increase: 0, decrease: 0 },
    }
    const opts = buildOpts(tbValues)
    useF2Adjudication(opts)

    const map = opts.allResponses.value
    expect(map.has('F2-1-gross-raw-materials-opening')).toBe(false)
    expect(map.has('F2-1-gross-raw-materials-increase')).toBe(false)
    expect(map.has('F2-1-gross-raw-materials-decrease')).toBe(false)
  })
})
