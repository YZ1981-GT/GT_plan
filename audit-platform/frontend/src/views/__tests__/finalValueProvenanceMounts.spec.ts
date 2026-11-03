import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const sourceRoot = resolve(__dirname, '..')

function read(name: string): string {
  return readFileSync(resolve(sourceRoot, name), 'utf-8')
}

describe('最终值来源信封挂载守卫', () => {
  it('报表本期金额列挂载来源信封，不触碰上期金额列', () => {
    const source = read('ReportView.vue')
    expect(source).toContain("import ReportProvenanceTooltip from '@/components/report/ReportProvenanceTooltip.vue'")
    const currentStart = source.indexOf('<el-table-column label="本期金额"')
    const priorStart = source.indexOf('<el-table-column label="上期金额"', currentStart)
    expect(currentStart).toBeGreaterThan(-1)
    expect(priorStart).toBeGreaterThan(currentStart)
    const currentColumn = source.slice(currentStart, priorStart)
    const priorColumn = source.slice(priorStart, source.indexOf('</el-table-column>', priorStart) + 18)
    expect(currentColumn).toContain('<ReportProvenanceTooltip')
    expect(currentColumn).toContain(':value="row.current_period_amount"')
    expect(priorColumn).toContain(':value="row.prior_period_amount"')
    expect(priorColumn).not.toContain('ReportProvenanceTooltip')
  })

  it('附注最终来源响应携带双层 provenance，弹窗显示采用状态', () => {
    const source = read('DisclosureEditor.vue')
    const cellTrace = read('../components/notes/CellTraceDialog.vue')
    const cellSources = read('../components/notes/cellSources.ts')
    expect(source).toContain('CellTraceDialog')
    expect(cellSources).toContain('formula_provenance')
    expect(cellTrace).toContain('公式来源信封')
    expect(cellTrace).toContain('calculation_applied')
    expect(cellTrace).not.toContain('<GtFormulaSourceTooltip')
    expect(cellTrace).not.toContain('<ReportProvenanceTooltip')
  })
})
