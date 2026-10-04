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

/**
 * 🔴 Per-file 上限覆盖（2026-09-28）。
 *
 * `ReportView.vue` 当前 1950 行（`split('\n')` 口径），超出通用 1500。
 * 给它单独上限而**不是**全局放松 MAX_LINES —— 其余 10 个文件现算最大仅
 * 555 行，把 MAX_LINES 提到 1950 会一次性放松它们全部的约束。
 *
 * 行数史（实证）：2026-06-12 曾 1104 行，随后 2026-07-27「调整分录集中登记」
 * 功能 +743 行到 1941，2026-08-22 达 1949，2026-09-13 被误删成 0 字节
 * （路由页白屏 3 个月），本次恢复。
 *
 * 🔴 0 字节期间本测试是**假绿**的：`countLines('')` 返 1，"满足" ≤1500。
 * 守卫只查上限不查下限 ⇒ 文件被删空反而通过。下方
 * `non-empty` 用例补上了这一侧。
 *
 * 与后端门禁 `backend/scripts/check/check_file_size.py` 的
 * `HARD_CAPS` 对应，但那里填 **1949**（`splitlines()` 口径恒少 1）。
 * 两个数字差 1 是口径差异，不是笔误。
 */
const PER_FILE_MAX_LINES: Record<string, number> = {
  'src/views/ReportView.vue': 1950,
}

function maxLinesFor(relativePath: string): number {
  return PER_FILE_MAX_LINES[relativePath] ?? MAX_LINES
}

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

  test('each extracted file is within its line cap', () => {
    const violations: { path: string; lines: number; cap: number }[] = []
    for (const { relativePath, absolutePath } of resolvedPaths) {
      const lines = countLines(absolutePath)
      const cap = maxLinesFor(relativePath)
      if (lines > cap) {
        violations.push({ path: relativePath, lines, cap })
      }
    }
    expect(violations, 'Files exceeding their line cap').toEqual([])
  })

  // 🔴 下限侧：0 字节文件曾让上面那条假绿（`countLines('')` 返 1，"满足" ≤1500）。
  // ReportView.vue 在 2026-09-13~2026-09-28 间就是 0 字节，路由页白屏 3 个月
  // 而本守卫全绿。只查上限的文件大小守卫必须配下限。
  test('no extracted file is empty or near-empty', () => {
    const suspicious: { path: string; lines: number }[] = []
    for (const { relativePath, absolutePath } of resolvedPaths) {
      const lines = countLines(absolutePath)
      if (lines < 20) {
        suspicious.push({ path: relativePath, lines })
      }
    }
    expect(
      suspicious,
      'Files suspiciously small (deleted/emptied?) — 上限守卫对空文件是假绿的',
    ).toEqual([])
  })

  test('per-file overrides do not silently relax the shared cap', () => {
    // 覆盖表只该含确有必要的条目；其余文件必须仍受 MAX_LINES 约束。
    const overridden = Object.keys(PER_FILE_MAX_LINES)
    expect(overridden).toEqual(['src/views/ReportView.vue'])
    for (const { relativePath, absolutePath } of resolvedPaths) {
      if (overridden.includes(relativePath)) continue
      expect(
        countLines(absolutePath),
        `${relativePath} 应受通用上限约束`,
      ).toBeLessThanOrEqual(MAX_LINES)
    }
  })

  // Feature: report-view-slimdown, Property 2: File Size Invariant
  // **Validates: Requirements 2.1, 2.4**
  test('PBT: random permutation of file paths all satisfy their line cap', () => {
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
            expect(lines).toBeLessThanOrEqual(maxLinesFor(relativePath))
          }
        },
      ),
      { numRuns: 5 },
    )
  })
})
