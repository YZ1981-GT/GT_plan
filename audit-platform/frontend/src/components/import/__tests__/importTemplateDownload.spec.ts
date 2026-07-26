/**
 * 导入弹窗模板下载计划（adjustment-import-export-contract Task 1.5 / Requirement 4）
 *
 * 覆盖：
 * - adjustments + 有项目上下文 → 项目感知富模板端点（含 year）
 * - adjustments + 无项目上下文 → 通用裸模板端点 + rich=false（调用方据此提示无下拉）
 * - 其他 importType → 一律通用裸模板，行为不变
 */
import { describe, it, expect } from 'vitest'
import {
  resolveTemplateDownloadPlan,
  BARE_TEMPLATE_WARNING,
} from '../importTemplateDownload'

describe('resolveTemplateDownloadPlan', () => {
  it('adjustments + projectId + year → 富模板端点（不带 template_type，由后端按项目派生）', () => {
    const plan = resolveTemplateDownloadPlan({
      importType: 'adjustments',
      typeLabel: '调整分录',
      projectId: 'proj-1',
      year: 2025,
    })
    expect(plan.url).toBe('/api/projects/proj-1/adjustments/export-template?year=2025')
    expect(plan.url).not.toContain('template_type')
    expect(plan.rich).toBe(true)
    expect(plan.filename).toBe('调整分录导入模板_2025.xlsx')
  })

  it('adjustments 无 projectId → 降级裸模板端点，rich=false', () => {
    const plan = resolveTemplateDownloadPlan({
      importType: 'adjustments',
      typeLabel: '调整分录',
      year: 2025,
    })
    expect(plan.url).toBe('/api/import-templates/adjustments/download')
    expect(plan.rich).toBe(false)
    expect(plan.filename).toBe('调整分录导入模板.xlsx')
  })

  it('adjustments 有 projectId 但无 year → 降级裸模板（富模板端点 year 必填）', () => {
    const plan = resolveTemplateDownloadPlan({
      importType: 'adjustments',
      typeLabel: '调整分录',
      projectId: 'proj-1',
    })
    expect(plan.url).toBe('/api/import-templates/adjustments/download')
    expect(plan.rich).toBe(false)
  })

  it.each([
    ['report', '报表数据'],
    ['workpaper', '底稿数据'],
    ['staff', '人员库'],
    ['trial_balance', '试算表'],
    ['disclosure_note', '附注数据'],
    ['formula', '公式'],
  ])('其他 importType=%s 仍走裸模板且文件名不变', (importType, typeLabel) => {
    const plan = resolveTemplateDownloadPlan({
      importType,
      typeLabel,
      projectId: 'proj-1',
      year: 2025,
    })
    expect(plan.url).toBe(`/api/import-templates/${importType}/download`)
    expect(plan.rich).toBe(false)
    expect(plan.filename).toBe(`${typeLabel}导入模板.xlsx`)
  })

  it('降级提示文案明确无科目下拉', () => {
    expect(BARE_TEMPLATE_WARNING).toContain('无科目下拉')
  })
})
