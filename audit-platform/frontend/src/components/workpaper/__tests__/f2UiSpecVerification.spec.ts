/**
 * F2 UI Specification Verification Test
 *
 * Structural verification that F2 components comply with UI铁律:
 * - 13px font-size globally
 * - AI+复核 buttons right-aligned in section headers
 * - Formula columns: dashed underline + cursor:help + el-tooltip
 * - min-width adaptive columns (not fixed width only)
 * - Audit notes/conclusions wrapped in el-card
 * - 编制提示 uses <details> fold element
 *
 * Validates: Requirements 20.1~20.4
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

const F2_DIR = path.resolve(__dirname, '../f2')

function readVueFile(relativePath: string): string {
  const fullPath = path.join(F2_DIR, relativePath)
  return fs.readFileSync(fullPath, 'utf-8')
}

// Key components to verify
const CORE_COMPONENTS = [
  'core/F2TabAdjudication.vue',
  'core/F2TabDetailSummary.vue',
  'core/F2AdjudicationBlockTable.vue',
  'detail/F2DetailSheet.vue',
  'inspection/F2CutoffSheet.vue',
  'analysis/F2TabOverallAnalysis.vue',
  'analysis/F2TabPolicy.vue',
  'analysis/F2TabProductionSales.vue',
  'analysis/F2TabCostComparison.vue',
]

describe('F2 UI Specification Verification', () => {
  describe('Requirement 20.1: 13px font-size globally', () => {
    it.each(CORE_COMPONENTS)('%s uses font-size: 13px', (component) => {
      const content = readVueFile(component)
      // Literal 13px or CSS var fallback (--wp-font-size, 13px)
      expect(content).toMatch(/font-size:\s*13px|font-size:\s*var\(--wp-font-size,\s*13px\)/)
    })
  })

  describe('Requirement 20.1: AI+复核 buttons right-aligned in section headers', () => {
    const COMPONENTS_WITH_AI = [
      'core/F2TabAdjudication.vue',
      'inspection/F2CutoffSheet.vue',
      'analysis/F2TabOverallAnalysis.vue',
      'analysis/F2TabPolicy.vue',
      'analysis/F2TabProductionSales.vue',
      'analysis/F2TabCostComparison.vue',
    ]

    it.each(COMPONENTS_WITH_AI)('%s has right-aligned header actions (flex space-between)', (component) => {
      const content = readVueFile(component)
      // Must use flex justify-content:space-between or equivalent pattern for header alignment
      const hasFlexPattern =
        content.includes('justify-content: space-between') ||
        content.includes('header-actions') ||
        content.includes('note-actions')
      expect(hasFlexPattern).toBe(true)
    })

    it.each(COMPONENTS_WITH_AI)('%s has AI generation button', (component) => {
      const content = readVueFile(component)
      expect(content).toContain('AI 生成')
    })
  })

  describe('Requirement 20.2: Formula columns with dashed underline + cursor:help + tooltip', () => {
    it('F2AdjudicationBlockTable has formula-cell with dashed border and cursor:help', () => {
      const content = readVueFile('core/F2AdjudicationBlockTable.vue')
      expect(content).toContain('border-bottom: 1px dashed')
      expect(content).toContain('cursor: help')
      expect(content).toContain('formula-cell')
    })

    it('F2AdjudicationBlockTable wraps formula cells in el-tooltip with formula source', () => {
      const content = readVueFile('core/F2AdjudicationBlockTable.vue')
      expect(content).toContain('el-tooltip')
      expect(content).toMatch(/content="公式[：:]/)
    })

    it('F2DetailSheet has formula-cell styling for computed columns', () => {
      const content = readVueFile('detail/F2DetailSheet.vue')
      expect(content).toContain('formula-cell')
      expect(content).toContain('border-bottom: 1px dashed')
      expect(content).toContain('cursor: help')
    })

    it('F2DetailSheet uses el-tooltip on formula columns (期末/单价)', () => {
      const content = readVueFile('detail/F2DetailSheet.vue')
      expect(content).toContain('el-tooltip')
      // Should have tooltip for closing balance formula
      expect(content).toContain('期初金额 + 增加 - 减少')
      // Should have tooltip for unit price formula
      expect(content).toContain('金额 ÷ 数量')
    })

    it('F2TabDetailSummary has formula-cell and el-tooltip for computed columns', () => {
      const content = readVueFile('core/F2TabDetailSummary.vue')
      expect(content).toContain('formula-cell')
      expect(content).toContain('el-tooltip')
      expect(content).toContain('cursor: help')
    })
  })

  describe('Requirement 20.3: min-width adaptive columns', () => {
    it('F2AdjudicationBlockTable uses min-width for data columns', () => {
      const content = readVueFile('core/F2AdjudicationBlockTable.vue')
      expect(content).toContain('min-width="110"')
    })

    it('F2DetailSheet uses min-width for columns', () => {
      const content = readVueFile('detail/F2DetailSheet.vue')
      expect(content).toContain('min-width="')
    })

    it('F2TabDetailSummary uses min-width for columns', () => {
      const content = readVueFile('core/F2TabDetailSummary.vue')
      expect(content).toContain('min-width="')
    })
  })

  describe('Requirement 20.3: Audit notes/conclusions wrapped in el-card', () => {
    it('F2TabAdjudication wraps audit notes in el-card', () => {
      const content = readVueFile('core/F2TabAdjudication.vue')
      // Should have el-card wrapping the audit notes section
      expect(content).toContain('audit-note-card')
      expect(content).toMatch(/<el-card[^>]*class="[^"]*audit-note-card[^"]*"/)
    })

    it('F2CutoffSheet wraps conclusion in section card', () => {
      const content = readVueFile('inspection/F2CutoffSheet.vue')
      expect(content).toContain('ct-card-conclusion')
      expect(content).toContain('审计结论')
    })

    it('F2TabOverallAnalysis conclusion section uses el-card', () => {
      const content = readVueFile('analysis/F2TabOverallAnalysis.vue')
      // The analysis conclusion is in an el-card
      expect(content).toContain('<el-card')
      expect(content).toContain('分析结论')
    })

    it('F2TabPolicy conclusion uses el-card', () => {
      const content = readVueFile('analysis/F2TabPolicy.vue')
      expect(content).toContain('<el-card')
      expect(content).toContain('政策评价结论')
    })
  })

  describe('Requirement 20.4: 编制提示 uses <details> element', () => {
    const COMPONENTS_WITH_GUIDANCE = [
      'core/F2TabAdjudication.vue',
      'detail/F2DetailSheet.vue',
      'inspection/F2CutoffSheet.vue',
      'analysis/F2TabOverallAnalysis.vue',
      'analysis/F2TabPolicy.vue',
      'analysis/F2TabProductionSales.vue',
      'analysis/F2TabCostComparison.vue',
    ]

    it.each(COMPONENTS_WITH_GUIDANCE)('%s has <details> for 编制提示', (component) => {
      const content = readVueFile(component)
      expect(content).toContain('<details')
      expect(content).toContain('guidance-details')
      expect(content).toContain('编制提示')
    })
  })
})
