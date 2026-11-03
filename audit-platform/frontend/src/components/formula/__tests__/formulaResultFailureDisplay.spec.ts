import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const HERE = resolve(__dirname, '..')

function source(name: string): string {
  return readFileSync(resolve(HERE, name), 'utf8')
}

describe('公式失败结果展示（ADR-FGR-03）', () => {
  it('公式管理中心保留零值，并把 null 显示为短横线和失败原因', () => {
    const text = source('FormulaManagerDialog.vue')
    expect(text).toContain("typeof formulaResults[row.row_code || row.id]?.value === 'number'")
    expect(text).toContain(": '—'")
    expect(text).toContain('formulaFailureReason')
    expect(text).toContain('formula-result-error')
    expect(text).toContain('errors')
  })

  it('公式调试面板显示失败原因并将失败值显示为短横线', () => {
    const text = source('FormulaDebugPanel.vue')
    expect(text).toContain('data-testid="formula-debug-failure-reason"')
    expect(text).toContain('failureReason(result)')
    expect(text).toContain("result.value ?? '—'")
    expect(text).toContain('result.errors')
  })
})
