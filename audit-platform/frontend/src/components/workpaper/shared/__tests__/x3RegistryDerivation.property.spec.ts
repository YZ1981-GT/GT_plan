/**
 * x3RegistryDerivation.property.spec.ts — Property 7: registry 派生确定且 MANUAL 不受污染
 *
 * spec: x3-adjustment-entry-import-export / 任务 11.3*
 * Validates: Requirements 6.1, 6.2, 6.4
 *
 * Property 7 定义：
 *   (a) 16 个 X-3 短前缀在 GENERATED_IMPORT_EXPORT 中均存在
 *   (b) 每个 X-3 前缀的 sheets 恰含一个 `{CYCLE}-3` 条目
 *   (c) MANUAL_OVERRIDES 的键与 X-3 前缀无交集
 *   (d) GENERATED_PREFIX_COUNT 与实际 generated 键数一致
 *   (e) GENERATED + MANUAL = CATALOG_PREFIX_TOTAL
 *   (f) 对任意 X-3 前缀子集属性成立（fast-check）
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  GENERATED_IMPORT_EXPORT,
  CATALOG_PREFIX_TOTAL,
  GENERATED_PREFIX_COUNT,
} from '../cycleImportExportRegistry.generated'
import { MANUAL_OVERRIDES } from '../cycleImportExportRegistry'

// X-3 的 16 个短前缀
const X3_PREFIXES = [
  'l2', 'l6', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6',
  'm7', 'm8', 'm9', 'm10', 'n1', 'n2', 'n3', 'n5',
] as const

const generatedKeys = Object.keys(GENERATED_IMPORT_EXPORT)
const manualKeys = Object.keys(MANUAL_OVERRIDES)

// ─── 测试 ────────────────────────────────────────────────────────────────────

describe('Property 7: X-3 registry 派生确定且 MANUAL 不受污染', () => {
  it('(a) 16 个 X-3 短前缀在 GENERATED_IMPORT_EXPORT 中均存在', () => {
    for (const prefix of X3_PREFIXES) {
      expect(generatedKeys).toContain(prefix)
    }
  })

  it('(b) 每个 X-3 前缀的 sheets 恰含一个 {CYCLE}-3 条目', () => {
    for (const prefix of X3_PREFIXES) {
      const cycle = prefix.toUpperCase()
      const sheetCode = `${cycle}-3`
      const entry = (GENERATED_IMPORT_EXPORT as any)[prefix]
      expect(entry, `${prefix} 在 registry 中缺失`).toBeDefined()
      expect(entry.sheets).toContain(sheetCode)
      expect(entry.sheets.length).toBe(1)
    }
  })

  it('(c) MANUAL_OVERRIDES 与 X-3 前缀无交集', () => {
    const overlap = manualKeys.filter((k) => (X3_PREFIXES as readonly string[]).includes(k))
    expect(overlap).toEqual([])
  })

  it('(d) GENERATED_PREFIX_COUNT 与实际 generated 键数一致', () => {
    expect(generatedKeys.length).toBe(GENERATED_PREFIX_COUNT)
  })

  it('(e) GENERATED + MANUAL = CATALOG_PREFIX_TOTAL', () => {
    expect(GENERATED_PREFIX_COUNT + manualKeys.length).toBe(CATALOG_PREFIX_TOTAL)
  })

  it('(f) Property 7 对任意 X-3 前缀子集成立（fast-check 100 runs）', () => {
    fc.assert(
      fc.property(
        fc.subarray([...X3_PREFIXES], { minLength: 1 }),
        (subset) => {
          for (const p of subset) {
            if (!generatedKeys.includes(p)) return false
            if (manualKeys.includes(p)) return false
          }
          return true
        },
      ),
      { numRuns: 100 },
    )
  })
})
