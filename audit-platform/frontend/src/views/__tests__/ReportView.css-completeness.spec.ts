/**
 * ReportView.css-completeness.spec.ts — CSS 选择器完备性 property test
 *
 * Feature: report-view-slimdown, Property 4: CSS Selector Completeness
 *
 * 静态分析：提取 `report-view.css` 所有选择器集合，验证所有选择器都存在且非空。
 * Since the CSS was already extracted (the original `<style scoped>` block is now externalized),
 * we verify that report-view.css contains all the key selectors that were in the original.
 *
 * Validates: Requirements 5.3, 5.4
 */
import { describe, it, expect, test } from 'vitest'
import fc from 'fast-check'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// ─── Read the externalized CSS file ─────────────────────────────────────────

const CSS_FILE_PATH = resolve(__dirname, '../report-view.css')
const cssContent = readFileSync(CSS_FILE_PATH, 'utf-8')

/**
 * Extract all CSS selectors from the file content.
 * Selectors are lines that end with `{` (opening a rule block),
 * or class/pseudo selectors found before `{`.
 */
function extractSelectors(css: string): string[] {
  const selectors: string[] = []
  // Remove comments
  const noComments = css.replace(/\/\*[\s\S]*?\*\//g, '')
  // Remove @keyframes blocks entirely (their internal selectors like "0%, 100%" are not real selectors)
  const noKeyframes = noComments.replace(/@keyframes\s+[\w-]+\s*\{[^}]*\{[^}]*\}[^}]*\}/g, '')

  // Match selectors: everything before `{` on non-empty lines
  const selectorRegex = /([^{}]+)\{/g
  let match: RegExpExecArray | null
  while ((match = selectorRegex.exec(noKeyframes)) !== null) {
    const raw = match[1].trim()
    if (raw && !raw.startsWith('@')) {
      // Split comma-separated selectors
      const parts = raw.split(',').map(s => s.trim()).filter(Boolean)
      selectors.push(...parts)
    }
  }
  return selectors
}

const allSelectors = extractSelectors(cssContent)

// ─── Key selectors that MUST exist in the externalized CSS ──────────────────
// These are the critical selectors from the original <style scoped> block

const KEY_SELECTORS = [
  '.gt-report-view',
  '.gt-rv-sticky-header',
  '.gt-rv-table-area',
  '.gt-rv-mode-radio :deep(.el-radio-button__inner)',
  ':deep(.el-table)',
  ':deep(.el-table th.el-table__cell)',
  ':deep(.el-table td.el-table__cell)',
  '.gt-rv-category',
  '.gt-rv-amount-cell',
  '.gt-rv-amount-cell-readonly',
  '.gt-rv-adjustment',
  ':deep(.diff-row)',
  '.gt-rv-change-rate',
  ':deep(.gt-rv-audit-fail-row)',
  '.gt-rv-check-item',
  '.gt-rv-drilldown-content .gt-rv-dd-section',
  '.gt-rv-equity-matrix',
  ':deep(.gt-rv-eq-total-row td)',
  ':deep(.gt-rv-eq-category td)',
  '.gt-rv-eq-hint',
  '.gt-rv-audit-summary',
  '.gt-rv-audit-stat',
  '.gt-rv-trace-bar',
  ':deep(.report-row--header)',
  ':deep(.report-row--total)',
  ':deep(.report-row--zero)',
  ':deep(.report-row--special)',
  '.report-amount',
  '.report-amount--negative',
  '.report-indent-0',
  '.report-indent-1',
  '.report-indent-2',
  '.gt-rv-gt-header',
  '.gt-rv-coverage-summary',
  '.gt-rv-line-comp-content',
  '.gt-rv-note-refs',
] as const

// ─── Tests ──────────────────────────────────────────────────────────────────

// Feature: report-view-slimdown, Property 4: CSS Selector Completeness
describe('ReportView CSS Selector Completeness', () => {
  it('report-view.css file exists and is non-empty', () => {
    expect(cssContent.length).toBeGreaterThan(0)
  })

  it('extracted selector set is non-empty', () => {
    expect(allSelectors.length).toBeGreaterThan(0)
    // Original <style scoped> had ~100+ selectors, externalized should have similar
    expect(allSelectors.length).toBeGreaterThan(50)
  })

  it('all key selectors exist in the externalized CSS file', () => {
    const missing: string[] = []
    for (const key of KEY_SELECTORS) {
      const found = allSelectors.some(s => s === key || s.includes(key))
      if (!found) {
        // Also check raw content as a fallback (selector may span multiple lines)
        const inRaw = cssContent.includes(key)
        if (!inRaw) {
          missing.push(key)
        }
      }
    }
    expect(missing).toEqual([])
  })

  it('no empty selector rules (all selectors have declarations)', () => {
    // Check that there are no empty blocks `selector { }`
    const emptyBlockRegex = /([^{}]+)\{\s*\}/g
    const emptyBlocks: string[] = []
    const noComments = cssContent.replace(/\/\*[\s\S]*?\*\//g, '')
    let match: RegExpExecArray | null
    while ((match = emptyBlockRegex.exec(noComments)) !== null) {
      const selector = match[1].trim()
      // Skip intentional empty rules (like .report-row--data and .report-row--manual with comments)
      if (selector && !selector.startsWith('@')) {
        emptyBlocks.push(selector)
      }
    }
    // Allow intentionally empty rules (documented with comments in the original)
    // .report-row--data and .report-row--manual are intentionally empty
    const unexpectedEmpty = emptyBlocks.filter(
      s => !s.includes('report-row--data') && !s.includes('report-row--manual')
    )
    expect(unexpectedEmpty).toEqual([])
  })

  // Feature: report-view-slimdown, Property 4: CSS Selector Completeness
  // **Validates: Requirements 5.3, 5.4**
  test('PBT: random subset of key selectors all exist in CSS', () => {
    fc.assert(
      fc.property(
        fc.shuffledSubarray([...KEY_SELECTORS], { minLength: 3, maxLength: KEY_SELECTORS.length }),
        (subset) => {
          for (const selector of subset) {
            const foundInParsed = allSelectors.some(s => s === selector || s.includes(selector))
            const foundInRaw = cssContent.includes(selector)
            expect(foundInParsed || foundInRaw).toBe(true)
          }
        },
      ),
      { numRuns: 5 },
    )
  })

  test('PBT: random subset of all extracted selectors are non-empty strings', () => {
    fc.assert(
      fc.property(
        fc.shuffledSubarray(allSelectors, { minLength: 1, maxLength: Math.min(20, allSelectors.length) }),
        (subset) => {
          for (const selector of subset) {
            expect(selector.trim().length).toBeGreaterThan(0)
          }
        },
      ),
      { numRuns: 5 },
    )
  })
})
