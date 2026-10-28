/**
 * ConsolNoteMappingDialog —— 同名多行按出现序映射（spec note-pull-followup-closure R11）
 *
 * 来源表里同一行名出现多次时后端按出现序号逐个给建议（`source_occurrence`）：弹窗逐行显示「（同名第 N 行）」，
 * 确认时把序号原样带回（只出现一次的行名不带，兼容旧规则）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  previewDetailRefresh: vi.fn(),
  confirmDetailMapping: vi.fn(),
  applyDetailRefresh: vi.fn(),
  getDetailTemplate: vi.fn(),
  getDetailTemplateBinding: vi.fn(),
  bindDetailTemplate: vi.fn(),
  listDetailTemplates: vi.fn(),
}))
vi.mock('@/services/consolidationApi', () => api)
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() }, ElMessageBox: {} }))

import ConsolNoteMappingDialog from '../ConsolNoteMappingDialog.vue'

const stubs: Record<string, any> = {
  'el-dialog': { template: '<div class="el-dialog"><slot /><slot name="footer" /></div>', props: ['modelValue'] },
  'el-table': {
    template: '<table class="el-table"><slot /></table>',
    props: ['data'],
    provide() {
      const self = this as any
      return { getTableData: () => self.data }
    },
  },
  'el-table-column': {
    inject: ['getTableData'],
    props: ['label', 'type'],
    template: '<td :data-label="label"><span v-for="(row, i) in getTableData()" :key="i" class="cell" :data-row="i"><slot :row="row" /></span></td>',
  },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-select': { template: '<div class="el-select"><slot /></div>', props: ['modelValue'] },
  'el-option': true,
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-alert': { template: '<div class="el-alert">{{ title }}<slot /></div>', props: ['title'] },
  'el-input': true,
  'el-progress': true,
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-badge': true,
  ConsolNoteDetailTemplateEditor: true,
}

const HASH = 'a'.repeat(64)

function preview() {
  const target = (id: string, name: string) => ({ target_row_id: id, canonical_name: name })
  return {
    preview_token: 'tok', project_id: 'p', section_id: '五-1-2', year: 2025, template_version_id: 'tv-1',
    template_rows: [target('t0', '一年以内（1）'), target('t1', '一年以上（1）'), target('t2', '（2）')],
    groups: [{
      hash: HASH, section_id: '五-1-2', has_rule: false, rule_id: null, all_confirmed: false,
      source_rows: [{ label: '（1）', row_type: 'data', key: '（1）#0', occurrence: 0 },
        { label: '（2）', row_type: 'data', key: '（2）#0', occurrence: 0 },
        { label: '（1）', row_type: 'data', key: '（1）#1', occurrence: 1 }],
      entities: [{ node_key: 'A:subsidiary', project_id: 'pa', company_name: '甲公司' }],
    }],
    stale_entities: [],
    suggestions: [
      { source_label: '（1）', source_occurrence: 0, suggested_target: target('t0', '一年以内（1）'), confidence: 1,
        match_type: 'exact', candidates: [], auto_confirmable: true },
      { source_label: '（1）', source_occurrence: 1, suggested_target: target('t1', '一年以上（1）'), confidence: 1,
        match_type: 'exact', candidates: [], auto_confirmable: true },
      { source_label: '（2）', suggested_target: target('t2', '（2）'), confidence: 1, match_type: 'exact',
        candidates: [], auto_confirmable: true },
    ],
    entity_count: 1, group_count: 1, stale_count: 0, entity_sources: [],
  }
}

async function open() {
  const w = mount(ConsolNoteMappingDialog, {
    props: { visible: false, projectId: 'p', sectionId: '五-1-2', sectionTitle: '应收股利', year: 2025, templateType: 'soe' },
    global: { stubs, directives: { loading: {} } },
  })
  await w.setProps({ visible: true })
  await flushPromises()
  return w
}

describe('ConsolNoteMappingDialog 同名多行（R11）', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset()
    api.previewDetailRefresh.mockResolvedValue(preview())
    api.confirmDetailMapping.mockResolvedValue({})
  })

  it('同名行逐行显示出现序号，只出现一次的行名不显示', async () => {
    const w = await open()
    const names = w.findAll('td[data-label="来源名称"] .cell').map(c => c.text())
    expect(names).toEqual(['（1）（同名第 1 行）', '（1）（同名第 2 行）', '（2）'])
  })

  it('确认时把序号原样带回；没有序号的行不带该键', async () => {
    const w = await open()
    const confirm = w.findAll('button').find(b => b.text() === '确认映射')!
    await confirm.trigger('click')
    await flushPromises()
    expect(api.confirmDetailMapping).toHaveBeenCalledTimes(1)
    const body = api.confirmDetailMapping.mock.calls[0][1]
    expect(body.source_structure_hash).toBe(HASH)
    expect(body.mappings.map((m: any) => [m.source_label, m.target_row_id, m.source_occurrence])).toEqual([
      ['（1）', 't0', 0], ['（1）', 't1', 1], ['（2）', 't2', undefined]])
    expect('source_occurrence' in body.mappings[2]).toBe(false)
  })
})
