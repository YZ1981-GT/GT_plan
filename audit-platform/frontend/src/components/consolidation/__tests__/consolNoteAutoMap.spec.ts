/**
 * 合并附注「⚡ 自动映射」与映射弹窗的就绪判定 / 匹配方式中文名（spec note-pull-header-formula-closure R6.2 / R6.3）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const h = vi.hoisted(() => ({
  confirm: vi.fn(), alert: vi.fn(), warning: vi.fn(), success: vi.fn(), error: vi.fn(), autoMap: vi.fn(),
}))
vi.mock('element-plus', () => ({
  ElMessage: { warning: h.warning, success: h.success, error: h.error },
  ElMessageBox: { confirm: h.confirm, alert: h.alert },
}))
vi.mock('@/services/consolidationApi', () => ({ autoMapDetail: h.autoMap }))

import { autoMapReport, runConsolNoteAutoMap } from '../composables/consolNoteAutoMap'
import { matchTypeLabel, matchTypeTagType, suggestionStatus } from '../composables/consolNoteMappingLabels'
import type { AutoMapResult } from '@/services/consolidationApi'

function result(sections: AutoMapResult['sections'], summary: Partial<AutoMapResult['summary']> = {}): AutoMapResult {
  return {
    template_type: 'soe', sections,
    summary: { sections: sections.length, mapped: 0, partial: 0, pending: 0, skipped: 0, failed: 0, templates_created: 0,
      confirmed_entities: 0, pending_entities: 0, ...summary },
  }
}
const sec = (over: Partial<AutoMapResult['sections'][number]>) => ({
  section_id: '五-1-1', status: 'mapped' as const, reason: null, template_action: 'created' as const,
  confirmed: [], already: [], pending: [], ...over,
})

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.alert.mockResolvedValue('confirm')
})

describe('runConsolNoteAutoMap', () => {
  it('「全部章节」：section_ids 为 null；全部确认 ⇒ 成功提示带下一步', async () => {
    h.confirm.mockResolvedValue('confirm')
    h.autoMap.mockResolvedValue(result([sec({ confirmed: [{ node_key: 'A', company_name: '甲' }] })],
      { mapped: 1, confirmed_entities: 1, templates_created: 1 }))
    const busy = ref(false)
    let during = false
    h.autoMap.mockImplementationOnce(async () => {
      during = busy.value
      return result([sec({})], { mapped: 1, confirmed_entities: 1 })
    })
    await runConsolNoteAutoMap('p-1', 2025, '五-1-1', busy)
    expect(h.autoMap).toHaveBeenCalledWith('p-1', { year: 2025, section_ids: null })
    expect(during).toBe(true)
    expect(busy.value).toBe(false)
    expect(h.success).toHaveBeenCalledWith(expect.stringContaining('重新汇总'))
    expect(h.alert).not.toHaveBeenCalled()
  })

  it('「仅当前章节」= 取消按钮；没选章节时提示、不发请求；点 × 什么都不做', async () => {
    h.confirm.mockRejectedValue('cancel')
    h.autoMap.mockResolvedValue(result([sec({})], { mapped: 1 }))
    await runConsolNoteAutoMap('p-1', 2025, '五-5-1', ref(false))
    expect(h.autoMap).toHaveBeenCalledWith('p-1', { year: 2025, section_ids: ['五-5-1'] })

    h.autoMap.mockClear()
    await runConsolNoteAutoMap('p-1', 2025, undefined, ref(false))
    expect(h.warning).toHaveBeenCalledWith('请先选择附注章节')
    h.confirm.mockRejectedValue('close')
    await runConsolNoteAutoMap('p-1', 2025, '五-5-1', ref(false))
    expect(h.autoMap).not.toHaveBeenCalled()
  })

  it('有待确认企业：弹窗列出企业与对不上的行名，不报成功；请求失败显示后端原因', async () => {
    h.confirm.mockResolvedValue('confirm')
    h.autoMap.mockResolvedValue(result([sec({ status: 'partial', pending: [
      { node_key: 'B', company_name: '乙公司', labels: ['银行存款户', '其他'] }] })], { partial: 1, pending_entities: 1 }))
    await runConsolNoteAutoMap('p-1', 2025, '五-1-1', ref(false))
    expect(h.success).not.toHaveBeenCalled()
    const message = h.alert.mock.calls[0][0]
    expect(message.children).toContain('五-1-1 乙公司：银行存款户、其他')
    expect(message.props.style).toContain('white-space: pre-line')

    h.autoMap.mockRejectedValue({ response: { data: { message: '项目已被合并锁定，无法修改' } } })
    const busy = ref(false)
    await runConsolNoteAutoMap('p-1', 2025, '五-1-1', busy)
    expect(h.error).toHaveBeenCalledWith('项目已被合并锁定，无法修改')
    expect(busy.value).toBe(false)
  })
})

describe('autoMapReport', () => {
  it('只跳过一个章节：写明原因、不算成功；部分章节跳过：只报个数', () => {
    const one = autoMapReport(result([sec({ status: 'skipped', reason: '没有读到任何子企业的单体附注' })], { skipped: 1 }))
    expect(one.ok).toBe(false)
    expect(one.text).toContain('未映射：没有读到任何子企业的单体附注')
    const many = autoMapReport(result([sec({}), sec({ section_id: '五-2', status: 'skipped', reason: 'x' })],
      { mapped: 1, skipped: 1, confirmed_entities: 2 }))
    expect(many.ok).toBe(true)
    expect(many.text).toContain('1 个章节没有读到子企业单体附注，已跳过')
  })

  it('失败章节逐条写原因；超过 8 条截断', () => {
    const failed = Array.from({ length: 10 }, (_, i) => sec({ section_id: `五-${i}`, status: 'failed', reason: '写入失败' }))
    const report = autoMapReport(result(failed, { failed: 10 }))
    expect(report.ok).toBe(false)
    expect(report.text).toContain('失败 10 个章节：')
    expect(report.text).toContain('……共 10 条')
    expect(report.text).not.toContain('五-9：')
  })
})

describe('映射弹窗就绪判定与匹配方式', () => {
  it('就绪只认后端 auto_confirmable 且有目标；有建议目标但要看一眼的是待确认', () => {
    expect(suggestionStatus({ auto_confirmable: true, suggested_target: { target_row_id: 't' } })).toBe('ready')
    expect(suggestionStatus({ auto_confirmable: false, suggested_target: { target_row_id: 't' }, match_type: 'fuzzy' }))
      .toBe('pending')
    expect(suggestionStatus({ auto_confirmable: true, suggested_target: null })).toBe('pending')
    expect(suggestionStatus({ suggested_target: { target_row_id: 't' } })).toBe('pending')
  })

  it('匹配方式全中文（含下推行 / 通用别名 / 上年），未知值不露英文代码', () => {
    const types = ['exact_id', 'exact', 'alias', 'global_alias', 'previous_year', 'history', 'fuzzy', 'manual']
    for (const t of types) expect(matchTypeLabel(t)).toMatch(/^[\u4e00-\u9fa5]+$/)
    expect(matchTypeLabel('exact_id')).toBe('下推行')
    expect(matchTypeLabel('previous_year')).toBe('上年')
    expect(matchTypeLabel('weird')).toBe('其他')
    expect(matchTypeLabel(undefined)).toBe('手动')
    expect(matchTypeTagType('exact_id')).toBe('success')
    expect(matchTypeTagType('history')).toBe('primary')
    expect(matchTypeTagType('previous_year')).toBe('warning')
    expect(matchTypeTagType('fuzzy')).toBe('warning')
    expect(matchTypeTagType('manual')).toBe('info')
    // 规则模板一级随 V202 退役（R16）：后端不再给出，旧值按未登记处理
    expect(matchTypeLabel('rule_template')).toBe('其他')
  })
})

describe('接线', () => {
  const src = (rel: string) => readFileSync(resolve(__dirname, rel), 'utf-8')

  it('映射弹窗用共用判定（不再「有建议目标就算就绪」），不另写一份匹配方式中文名', () => {
    const dialog = src('../ConsolNoteMappingDialog.vue')
    expect(dialog).toContain("from './composables/consolNoteMappingLabels'")
    expect(dialog).toContain('_status: suggestionStatus(suggestion),')
    expect(dialog).not.toMatch(/function matchTypeLabel\(/)
    expect(dialog).toContain('@change="onTargetChange(row)"')
  })

  it('合并页报表 / 附注模板随项目口径 template_type（详情接口没有 applicable_standard，上市集团原先恒按国企版）', () => {
    const index = src('../../../views/ConsolidationIndex.vue')
    const start = index.indexOf('async function loadProjectInfo()')
    const body = index.slice(start, index.indexOf('\n}', start))
    expect(body).toMatch(/projectInfo\.standard = p\.template_type === 'listed' \|\| p\.template_type === 'soe'/)
    expect(body).toContain('consolReportTemplateType.value = projectInfo.standard')
    expect(body).toContain('consolNoteTemplateType.value = projectInfo.standard')
  })

  it('合并附注页「⚡ 自动映射」按钮调自动映射', () => {
    const tab = src('../ConsolNoteTab.vue')
    expect(tab).toMatch(/@click="handleAutoMap"[^>]*>⚡ 自动映射</)
    const start = tab.indexOf('function handleAutoMap()')
    expect(start).toBeGreaterThan(0)
    expect(tab.slice(start, tab.indexOf('\n}', start))).toContain(
      'runConsolNoteAutoMap(props.projectId, props.year, selectedNoteSection.value?.section_id, autoMapping)')
  })
})
