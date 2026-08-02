/**
 * 语义科目定位溯源视图模型守卫（平台共用件）
 *
 * 被守卫对象 = `composables/shared/semanticAccountSource.ts`，消费后端
 * `four_table/semantic_account_resolver.SemanticAccountResult.as_dict()`。
 *
 * 核心不变量：
 * - `found=false` 的槽必须**照样列出**并标记未命中 —— 面板要显式说「本项目无此科目」，
 *   而不是把该槽从表里删掉（用户看不到就会以为取数覆盖完整）
 * - `exact=false`（包含匹配）必须可辨识 → 要求审计师复核
 * - `report_config` 与按名称定位的冲突必须暴露（平台实证 `report_config` 有错码）
 * - 旧准则同族科目进「待人工映射」，平台不猜跨准则拆分
 * - 父子自检差异 ≤0.01 视为无差异（金额两位小数）
 *
 * 反向自检：字段名与后端 `as_dict()` 的键逐字比对（读 Python 源码），
 * 任一侧改名另一侧必红。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  hasSemanticAccountSource,
  normalizeSemanticAccountSource,
  semanticCodeListText,
  semanticConflictRows,
  semanticParentDiffCount,
  semanticResolvedFromLabel,
  semanticResolvedFromTagType,
  semanticSlotRows,
  semanticUnmappedRows,
} from '../shared/semanticAccountSource'

const RESOLVER_PY = resolve(
  __dirname,
  '../../../../../../../backend/app/services/four_table/semantic_account_resolver.py',
)

const ORDER = ['cash', 'bank', 'other', 'finance_co', 'digital']

function sample() {
  return {
    row_code: 'BS-002',
    formula: "TB('1001') + TB('1002') + TB('1012')",
    report_config_codes: ['1001', '1002', '1012'],
    conflicts: [['other', '1012', '1012.09']],
    unmapped_candidates: [['1501', '持有至到期投资']],
    chart_available: true,
    slots: {
      cash: {
        key: 'cash',
        label: '库存现金',
        codes: ['1001'],
        standard_codes: ['1001'],
        matched: [['1001', '库存现金']],
        resolved_from: 'account_chart_client',
        exact: true,
        found: true,
      },
      bank: {
        key: 'bank',
        label: '银行存款',
        codes: ['1002'],
        standard_codes: ['1002'],
        matched: [['1002', '银行存款']],
        resolved_from: 'account_chart_standard',
        exact: false,
        found: true,
      },
      other: {
        key: 'other',
        label: '其他货币资金',
        codes: ['1012'],
        standard_codes: ['1012'],
        matched: [['1012', '其他货币资金']],
        resolved_from: 'fallback',
        exact: false,
        found: true,
      },
      finance_co: {
        key: 'finance_co',
        label: '存放财务公司款项',
        codes: [],
        standard_codes: [],
        matched: [],
        resolved_from: 'none',
        exact: false,
        found: false,
      },
      digital: {
        key: 'digital',
        label: '数字货币',
        codes: [],
        standard_codes: [],
        matched: [],
        resolved_from: 'none',
        exact: false,
        found: false,
      },
    },
    parent_check: {
      '1002': { slot: 'bank', parent_closing: 1000, leaf_closing: 1000, diff: 0 },
      '1012': { slot: 'other', parent_closing: 500, leaf_closing: 460, diff: -40 },
    },
  }
}

describe('normalizeSemanticAccountSource', () => {
  it('整体缺失 / 非对象 → 结构完整的空对象（不崩）', () => {
    for (const raw of [undefined, null, 'bad', 42, []]) {
      const s = normalizeSemanticAccountSource(raw)
      expect(s.slots).toEqual({})
      expect(s.conflicts).toEqual([])
      expect(s.chart_available).toBe(false)
    }
  })

  it('保留后端字段（不改名不丢字段）', () => {
    const s = normalizeSemanticAccountSource(sample())
    expect(s.row_code).toBe('BS-002')
    expect(s.formula).toContain("TB('1001')")
    expect(Object.keys(s.slots || {})).toHaveLength(5)
    expect(Object.keys(s.parent_check || {})).toEqual(['1002', '1012'])
  })
})

describe('semanticSlotRows', () => {
  const rows = semanticSlotRows(normalizeSemanticAccountSource(sample()), ORDER)

  it('🔴 未命中的槽照样列出并标 found=false（不能从表里删掉）', () => {
    expect(rows).toHaveLength(5)
    expect(rows.map((r) => r.key)).toEqual(ORDER)
    const fin = rows.find((r) => r.key === 'finance_co')!
    expect(fin.found).toBe(false)
    expect(fin.codesText).toBe('—')
    expect(fin.matchedNames).toBe('—')
  })

  it('中文化命中来源 + 标签色（客户表 success / 兜底 warning / 未命中 info）', () => {
    expect(rows.find((r) => r.key === 'cash')!.resolvedFromLabel).toBe('客户科目表')
    expect(rows.find((r) => r.key === 'cash')!.resolvedFromTag).toBe('success')
    expect(rows.find((r) => r.key === 'bank')!.resolvedFromLabel).toBe('标准科目表')
    expect(rows.find((r) => r.key === 'other')!.resolvedFromTag).toBe('warning')
    expect(rows.find((r) => r.key === 'digital')!.resolvedFromTag).toBe('info')
  })

  it('exact=false 可辨识（面板据此提示复核）', () => {
    expect(rows.find((r) => r.key === 'cash')!.exact).toBe(true)
    expect(rows.find((r) => r.key === 'bank')!.exact).toBe(false)
  })

  it('父子差异只在 |diff| > 0.01 时挂到对应槽', () => {
    expect(rows.find((r) => r.key === 'bank')!.parentDiffs).toEqual([])
    const other = rows.find((r) => r.key === 'other')!.parentDiffs
    expect(other).toHaveLength(1)
    expect(other[0]).toEqual({ code: '1012', leaf: 460, parent: 500, diff: -40 })
  })

  it('order 为空时回退到后端给的槽顺序', () => {
    const r = semanticSlotRows(normalizeSemanticAccountSource(sample()), [])
    expect(r).toHaveLength(5)
  })

  it('label 缺失时用调用方兜底名，再兜底 key', () => {
    const src = normalizeSemanticAccountSource({
      slots: { x: { key: 'x', found: true, codes: ['9'], resolved_from: 'fallback' } },
    })
    expect(semanticSlotRows(src, ['x'], { x: '兜底名' })[0].label).toBe('兜底名')
    expect(semanticSlotRows(src, ['x'])[0].label).toBe('x')
  })

  it('纯函数：同输入同输出', () => {
    const a = semanticSlotRows(normalizeSemanticAccountSource(sample()), ORDER)
    const b = semanticSlotRows(normalizeSemanticAccountSource(sample()), ORDER)
    expect(a).toEqual(b)
  })
})

describe('冲突 / 待映射 / 自检', () => {
  const src = normalizeSemanticAccountSource(sample())

  it('冲突条目结构化暴露（报表码 ↔ 实际码）', () => {
    expect(semanticConflictRows(src)).toEqual([
      { slotKey: 'other', reportCode: '1012', actualCode: '1012.09' },
    ])
  })

  it('旧准则科目进「待人工映射」', () => {
    expect(semanticUnmappedRows(src)).toEqual([{ code: '1501', name: '持有至到期投资' }])
  })

  it('父子差异计数只算超容差项', () => {
    expect(semanticParentDiffCount(src)).toBe(1)
  })

  it('hasSemanticAccountSource：无命中槽且无报表行 → 不渲染面板', () => {
    expect(hasSemanticAccountSource(src)).toBe(true)
    expect(hasSemanticAccountSource(normalizeSemanticAccountSource({}))).toBe(false)
    expect(
      hasSemanticAccountSource(
        normalizeSemanticAccountSource({ row_code: 'BS-002', slots: {} }),
      ),
    ).toBe(true)
  })

  it('semanticCodeListText 空集显示占位符', () => {
    expect(semanticCodeListText([])).toBe('—')
    expect(semanticCodeListText(undefined)).toBe('—')
    expect(semanticCodeListText(['1001', '1002'])).toBe('1001、1002')
  })
})

describe('🔴 与后端 as_dict() 字段交叉锁死', () => {
  const py = readFileSync(RESOLVER_PY, 'utf-8')

  it('反向自检：能读到后端 as_dict 实现（否则断言空转）', () => {
    expect(py).toContain('def as_dict')
    expect(py.length).toBeGreaterThan(2000)
  })

  it('顶层字段名逐字一致', () => {
    for (const key of [
      'row_code',
      'formula',
      'report_config_codes',
      'conflicts',
      'unmapped_candidates',
      'chart_available',
      'slots',
    ]) {
      expect(py, `后端 as_dict 缺字段 ${key}`).toContain(`"${key}"`)
    }
  })

  it('槽字段名逐字一致', () => {
    for (const key of ['codes', 'standard_codes', 'matched', 'resolved_from', 'exact', 'found']) {
      expect(py, `后端槽序列化缺字段 ${key}`).toContain(`"${key}"`)
    }
  })

  it('命中来源枚举值逐字一致（中文化映射不得漏项）', () => {
    for (const v of [
      'account_chart_client',
      'account_chart_standard',
      'report_config',
      'fallback',
      'none',
    ]) {
      expect(py, `后端缺 RESOLVED_FROM 值 ${v}`).toContain(v)
      expect(semanticResolvedFromLabel(v)).not.toBe('')
      expect(['success', 'primary', 'warning', 'info']).toContain(semanticResolvedFromTagType(v))
    }
    // 未登记的值走「未命中」兜底而不是抛错
    expect(semanticResolvedFromLabel('brand_new')).toBe('未命中')
  })
})
