/**
 * ReportView.filesize-invariant.spec.ts — File Size Invariant property test
 *
 * Feature: report-view-slimdown, Property 2: File Size Invariant
 *
 * 静态检查：遍历所有抽取文件路径，断言每个文件 ≤1500 行。
 * 使用 fast-check 对路径列表随机排列验证，确保无论检查顺序如何，
 * 所有文件均满足行数上限约束。
 *
 * Validates: Requirements 2.1, 2.4
 */
import { describe, test, expect } from 'vitest'
import fc from 'fast-check'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// ─── Constants ──────────────────────────────────────────────────────────────

const MAX_LINES = 1500

// All extracted file paths (relative to audit-platform/frontend/)
const EXTRACTED_FILE_PATHS = [
  'src/views/ReportView.vue',
  'src/views/composables/useReportColumns.ts',
  'src/views/composables/useReportData.ts',
  'src/views/composables/useReportMapping.ts',
  'src/views/composables/useReportCrossCheck.ts',
  'src/views/composables/useReportExport.ts',
  'src/views/composables/useReportCellActions.ts',
  'src/components/report/ReportEquityTable.vue',
  'src/components/report/ReportImpairmentTable.vue',
  'src/components/report/ReportDialogs.vue',
  'src/views/report-view.css',
] as const

// Resolve to absolute paths from the frontend root
// __dirname = .../frontend/src/views/__tests__, go up 3 levels to reach frontend/
const FRONTEND_ROOT = resolve(__dirname, '../../..')
const resolvedPaths = EXTRACTED_FILE_PATHS.map(p => ({
  relativePath: p,
  absolutePath: resolve(FRONTEND_ROOT, p),
}))

// ─── Helper ─────────────────────────────────────────────────────────────────

function countLines(filePath: string): number {
  const content = readFileSync(filePath, 'utf-8')
  return content.split('\n').length
}

// ─── Tests ──────────────────────────────────────────────────────────────────

// Feature: report-view-slimdown, Property 2: File Size Invariant
describe('ReportView File Size Invariant', () => {
  test('all extracted files exist and are readable', () => {
    for (const { relativePath, absolutePath } of resolvedPaths) {
      expect(() => readFileSync(absolutePath, 'utf-8'), `File should exist: ${relativePath}`).not.toThrow()
    }
  })

  test('each extracted file is ≤1500 lines', () => {
    const violations: { path: string; lines: number }[] = []
    for (const { relativePath, absolutePath } of resolvedPaths) {
      const lines = countLines(absolutePath)
      if (lines > MAX_LINES) {
        violations.push({ path: relativePath, lines })
      }
    }
    expect(violations, `Files exceeding ${MAX_LINES} lines`).toEqual([])
  })

  // Feature: report-view-slimdown, Property 2: File Size Invariant
  // **Validates: Requirements 2.1, 2.4**
  test('PBT: random permutation of file paths all satisfy ≤1500 line constraint', () => {
    fc.assert(
      fc.property(
        fc.shuffledSubarray([...EXTRACTED_FILE_PATHS], {
          minLength: EXTRACTED_FILE_PATHS.length,
          maxLength: EXTRACTED_FILE_PATHS.length,
        }),
        (shuffledPaths) => {
          for (const relativePath of shuffledPaths) {
            const absolutePath = resolve(FRONTEND_ROOT, relativePath)
            const lines = countLines(absolutePath)
            expect(lines).toBeLessThanOrEqual(MAX_LINES)
          }
        },
      ),
      { numRuns: 5 },
    )
  })
})
