/**
 * Property Test P10: 目录顺序等价
 *
 * 对任意 render-config sheet 序列，通用目录层保留全部有效 sheet 的原始顺序。
 *
 * 即：buildSheetMetas 的输出是输入有效条目的顺序保持子序列——
 * 不会重排、不会插入、不会丢弃有效 sheet。
 *
 * **Validates: Requirements 6.3, 6.5**
 *
 * 实施方案：vitest + fast-check (numRuns: 20)
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  buildSheetMetas,
  extractIndexRef,
  isValidIndexSheet,
  type RenderConfigSheet,
  type SheetMeta,
} from '../useWorkpaperIndexMetadata'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 有效的 componentType 池（非排除类型） */
const VALID_COMPONENT_TYPES = [
  'a-program-console',
  'c-note-table',
  'd-form-table',
  'd-form-paragraph',
  'd-form-qa',
  'd-form-confirmation',
  'd-form-review',
  'h-static-doc',
  'univer',
] as const

/** 排除的 componentType */
const EXCLUDED_TYPES = ['b-index', 'skip']

/** 所有 componentType（含排除类型，模拟真实 render-config 含目录 sheet 的情况） */
const ALL_COMPONENT_TYPES = [...VALID_COMPONENT_TYPES, ...EXCLUDED_TYPES]

/** 生成有效 sheet 名称（含编码后缀） */
const validSheetNameArb = fc.tuple(
  fc.constantFrom('审定表', '明细表', '检查表', '调整分录', '附注披露', '分析表', '情况表', '程序表'),
  fc.constantFrom('D2', 'J1', 'K3', 'H5', 'G4', 'F1', 'L2', 'M1', 'N2', 'I3'),
  fc.constantFrom('-1', '-2', '-3', '-4', '-5', '-6', '-7', '-8', '-9', '-10', '-11', 'A', ''),
).map(([prefix, code, suffix]) => `${prefix}${code}${suffix}`)

/** 生成 render-config sheet 条目 */
const renderConfigSheetArb: fc.Arbitrary<RenderConfigSheet> = fc.oneof(
  // 有效条目
  fc.tuple(validSheetNameArb, fc.constantFrom(...VALID_COMPONENT_TYPES)).map(
    ([name, ct]) => ({
      sheet_name: name,
      component_type: ct,
    }),
  ),
  // 排除类型（b-index / skip）
  fc.tuple(
    fc.constantFrom('底稿目录', '选项清单', '示例'),
    fc.constantFrom(...EXCLUDED_TYPES),
  ).map(([name, ct]) => ({
    sheet_name: name,
    component_type: ct,
  })),
  // 空名称（应被过滤）
  fc.constant({ sheet_name: '', component_type: 'd-form-table' }),
  fc.constant({ sheet_name: '   ', component_type: 'd-form-table' }),
)

/** 生成 render-config sheets 数组（1~30 个条目） */
const sheetsArrayArb = fc.array(renderConfigSheetArb, { minLength: 1, maxLength: 30 })

// ─── Property Tests ─────────────────────────────────────────────────────────

describe('P10: 目录顺序等价', () => {
  it('buildSheetMetas 保留有效 sheet 的原始顺序（顺序不变量）', () => {
    fc.assert(
      fc.property(sheetsArrayArb, (sheets) => {
        const metas = buildSheetMetas(sheets)

        // 1. 提取输入中全部有效条目的索引（保持原始顺序）
        const validInputIndices: number[] = []
        for (let i = 0; i < sheets.length; i++) {
          if (isValidIndexSheet(sheets[i], ['b-index', 'skip'])) {
            validInputIndices.push(i)
          }
        }

        // 2. 输出数量 === 有效输入数量（不丢弃、不插入）
        expect(metas.length).toBe(validInputIndices.length)

        // 3. 输出顺序与输入有效条目顺序一致（sheet_name 逐位对齐）
        for (let j = 0; j < metas.length; j++) {
          const inputIdx = validInputIndices[j]
          const inputSheet = sheets[inputIdx]
          expect(metas[j].sheetName).toBe((inputSheet.sheet_name ?? '').trim() ? inputSheet.sheet_name : '')
        }

        // 4. seq 单调递增从 1 开始
        for (let j = 0; j < metas.length; j++) {
          expect(metas[j].seq).toBe(j + 1)
        }
      }),
      { numRuns: 20 },
    )
  })

  it('buildSheetMetas 不重排有效 sheet（相对顺序保持）', () => {
    fc.assert(
      fc.property(sheetsArrayArb, (sheets) => {
        const metas = buildSheetMetas(sheets)

        // 对任意两个输出元素 metas[i] 和 metas[j]（i < j），
        // 它们在原始输入中的位置也满足 pos(i) < pos(j)。
        // 由于我们的实现是顺序过滤，这自然成立——但显式验证。
        const inputNames = sheets
          .filter((s) => isValidIndexSheet(s, ['b-index', 'skip']))
          .map((s) => s.sheet_name ?? '')

        const outputNames = metas.map((m) => m.sheetName)
        expect(outputNames).toEqual(inputNames)
      }),
      { numRuns: 20 },
    )
  })

  it('排除类型的 sheet 不出现在输出中', () => {
    fc.assert(
      fc.property(sheetsArrayArb, (sheets) => {
        const metas = buildSheetMetas(sheets)

        for (const meta of metas) {
          expect(EXCLUDED_TYPES).not.toContain(meta.componentType)
        }
      }),
      { numRuns: 20 },
    )
  })

  it('空名称 sheet 不出现在输出中', () => {
    fc.assert(
      fc.property(sheetsArrayArb, (sheets) => {
        const metas = buildSheetMetas(sheets)

        for (const meta of metas) {
          expect(meta.sheetName.trim().length).toBeGreaterThan(0)
        }
      }),
      { numRuns: 20 },
    )
  })

  it('ACNR catalogIndex 不影响顺序（只丰富 canonical/addr 字段）', () => {
    fc.assert(
      fc.property(sheetsArrayArb, (sheets) => {
        // 构造一个 catalog
        const catalog = new Map<string, { sheet_name: string; addr_id: string; order: number }>()
        catalog.set('J1-1', { sheet_name: '应付职工薪酬审定表', addr_id: 'J1/J1-1/main', order: 0 })
        catalog.set('K3-7', { sheet_name: '其他应付款检查表', addr_id: 'K3/K3-7/check', order: 5 })

        const withoutCatalog = buildSheetMetas(sheets)
        const withCatalog = buildSheetMetas(sheets, { catalogIndex: catalog })

        // 顺序相同
        expect(withCatalog.length).toBe(withoutCatalog.length)
        for (let i = 0; i < withCatalog.length; i++) {
          expect(withCatalog[i].sheetName).toBe(withoutCatalog[i].sheetName)
          expect(withCatalog[i].seq).toBe(withoutCatalog[i].seq)
          expect(withCatalog[i].componentType).toBe(withoutCatalog[i].componentType)
        }
      }),
      { numRuns: 20 },
    )
  })
})

// ─── Unit Tests（extractIndexRef 边界覆盖） ──────────────────────────────────

describe('extractIndexRef', () => {
  it('从审定表名提取编码', () => {
    expect(extractIndexRef('审定表J1-1')).toBe('J1-1')
    expect(extractIndexRef('明细表K3-2')).toBe('K3-2')
    expect(extractIndexRef('检查表J1-10')).toBe('J1-10')
  })

  it('从程序表名提取编码（头部匹配）', () => {
    expect(extractIndexRef('J1A 应付职工薪酬实质性程序表')).toBe('J1A')
  })

  it('尾部编码优先于头部', () => {
    expect(extractIndexRef('应付职工薪酬实质性程序表 J1A')).toBe('J1A')
  })

  it('空字符串返回空', () => {
    expect(extractIndexRef('')).toBe('')
  })

  it('无编码返回空', () => {
    expect(extractIndexRef('底稿目录')).toBe('')
    expect(extractIndexRef('选项清单')).toBe('')
  })
})
