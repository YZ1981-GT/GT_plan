/**
 * 上年附注导入（spec consol-note-header-library-and-node-reaggregate R6.6）：notePriorYearImport 纯函数 / 请求封装 +
 * NotePriorYearImportDialog 接线（预览 → 逐表确认 / 改选上年表 / 逐列指定 → 写入）。
 *
 * - 默认只勾「自动认出」的表；改选上年本节的表时列对应取服务端为它算好的，其他章节的表逐列指定；
 * - 勾了却没选上年表 / 没指定任何列 ⇒ 不能写入并说明是哪张表；
 * - 写入重传同一文件 + 预览给的文件指纹；导入正文（会替换本年正文）先二次确认；
 * - 服务端说要重新预览（文件变了 409 / 附注被改 400）⇒ 预览作废、禁止写入，重新预览后恢复。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

const post = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { post: (...a: unknown[]) => post(...a), get: vi.fn() } }))
const msg = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), confirm: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: { success: msg.success, error: msg.error, warning: msg.warning },
  ElMessageBox: { confirm: msg.confirm },
}))

import NotePriorYearImportDialog from '@/components/disclosure/NotePriorYearImportDialog.vue'
import {
  appliedText, applyPriorYear, columnsText, fillableOf, hasMappedColumn, initialChoices, previewPriorYear,
  previewSummary, priorTableLabel, setColumn, switchPriorTable, toDecisions, type PriorYearPreview, type TablePlanItem,
} from '@/components/disclosure/notePriorYearImport'

function plan(over: Partial<TablePlanItem>): TablePlanItem {
  return {
    key: 'n1:0', note_id: 'n1', note_section: '五、1', section_title: '货币资金', table_index: 0, table_name: '货币资金',
    opening_columns: [{ col: 2, label: '期初余额' }], status: 'auto', reason: null, method: 'name', prior_table_id: 't1',
    col_map: { 2: 1 }, candidates: ['t1'], candidate_maps: { t1: { 2: 1 } }, fillable: 2, candidate_fillable: { t1: 2 },
    ...over,
  }
}

const AGING = plan({
  key: 'n2:0', note_id: 'n2', note_section: '五、3', section_title: '应收账款', table_name: '按账龄披露',
  opening_columns: [{ col: 3, label: '期初余额/账面余额' }, { col: 4, label: '期初余额/坏账准备' }],
  status: 'needs_confirm', reason: '上年该节有 2 张表，没有与「按账龄披露」对应的表', method: null, prior_table_id: null,
  col_map: {}, candidates: ['t2', 't3'], candidate_maps: { t2: { 3: 1 }, t3: { 3: 1, 4: 2 } }, fillable: 0,
  candidate_fillable: { t2: 0, t3: 5 },
})
const CONTRACT = plan({
  key: 'n3:0', note_id: 'n3', note_section: '五、9', section_title: '合同资产', table_name: '合同资产情况',
  status: 'no_source', reason: '上年附注里没有找到「合同资产」这一节', method: null, prior_table_id: null, col_map: {},
  candidates: [], candidate_maps: {}, fillable: 0, candidate_fillable: {},
})

const PREVIEW: PriorYearPreview = {
  status: 'preview', file_sha256: 'f'.repeat(64), matched: 3, unmatched: 1, matched_sections: ['货币资金', '应收账款'],
  unmatched_sections: ['某专项说明'], total_prior_sections: 4, counts: { auto: 1, needs_confirm: 1, no_source: 1 },
  text_sections: 2, tables: [plan({}), AGING, CONTRACT],
  prior_tables: [
    { id: 't1', section: '货币资金', caption: '货币资金', columns: [{ col: 1, label: '期末余额' }, { col: 2, label: '期初余额' }], row_count: 3 },
    { id: 't2', section: '应收账款', caption: '按坏账计提方法分类披露', columns: [{ col: 1, label: '期末余额' }], row_count: 4 },
    { id: 't3', section: '应收账款', caption: '按账龄披露（期末数）',
      columns: [{ col: 1, label: '期末余额/账面余额' }, { col: 2, label: '期末余额/坏账准备' }], row_count: 5 },
    { id: 't4', section: '其他非流动资产', caption: '合同资产情况', columns: [{ col: 1, label: '期末余额' }], row_count: 2 },
  ],
}

const APPLIED = {
  status: 'success' as const, matched: 3, unmatched: 1, matched_sections: [], unmatched_sections: [], total_prior_sections: 4,
  filled_cells: 6, tables_written: 1, text_filled: 2, pending_tables: 0, no_source_tables: 1, changed_sections: ['五、1', '五、3'],
}

beforeEach(() => {
  post.mockReset()
  Object.values(msg).forEach(fn => fn.mockReset())
  msg.confirm.mockResolvedValue('confirm')
})

describe('notePriorYearImport 纯函数', () => {
  it('初始只勾自动认出的表，上年表与列对应取服务端选的', () => {
    const choices = initialChoices(PREVIEW)
    expect(Object.fromEntries(Object.entries(choices).map(([k, c]) => [k, c.include]))).toEqual(
      { 'n1:0': true, 'n2:0': false, 'n3:0': false })
    expect(choices['n1:0']).toEqual({ include: true, priorTableId: 't1', colMap: { 2: 1 }, manual: false })
    expect(choices['n2:0'].colMap).toEqual({ 3: null, 4: null })
  })

  it('改选上年本节的表用服务端算好的列对应；其他章节的表逐列待指定；选「不导入」即取消勾选', () => {
    expect(switchPriorTable(AGING, 't3')).toEqual({ include: true, priorTableId: 't3', colMap: { 3: 1, 4: 2 }, manual: false })
    expect(switchPriorTable(AGING, 't2').colMap).toEqual({ 3: 1, 4: null })
    expect(switchPriorTable(AGING, 't4').colMap).toEqual({ 3: null, 4: null })
    expect(switchPriorTable(AGING, null)).toMatchObject({ include: false, priorTableId: null })
  })

  it('可填格数：候选表取服务端预演值；手动改过列或选了其他章节的表 ⇒ 以写入结果为准（null）', () => {
    const picked = switchPriorTable(AGING, 't3')
    expect(fillableOf(AGING, picked)).toBe(5)
    expect(fillableOf(AGING, setColumn(picked, 4, null))).toBeNull()
    expect(fillableOf(AGING, switchPriorTable(AGING, 't4'))).toBeNull()
    expect(fillableOf(AGING, switchPriorTable(AGING, null))).toBeNull()
  })

  it('提交只含勾选的表与已指定的列；勾了却没选表 / 没指定列 ⇒ 列为问题、不提交', () => {
    const choices = initialChoices(PREVIEW)
    choices['n2:0'] = setColumn(switchPriorTable(AGING, 't3'), 4, null)
    choices['n3:0'] = { ...choices['n3:0'], include: true }
    expect(toDecisions(PREVIEW, choices)).toEqual({
      decisions: [{ key: 'n1:0', prior_table_id: 't1', col_map: { 2: 1 } },
        { key: 'n2:0', prior_table_id: 't3', col_map: { 3: 1 } }],
      problems: ['五、9 合同资产 · 合同资产情况：没有选上年表'],
    })
    choices['n3:0'] = switchPriorTable(CONTRACT, 't4')
    expect(toDecisions(PREVIEW, choices).problems).toEqual(['五、9 合同资产 · 合同资产情况：没有指定任何列'])
  })

  it('上年表下拉项：表名与所在标题相同只写一次；可填格数只给有现成列对应的表；「已指定列」至少一列', () => {
    expect(priorTableLabel(PREVIEW.prior_tables[0], plan({}))).toBe('货币资金 · 3 行 · 可填 2 格')
    expect(priorTableLabel(PREVIEW.prior_tables[2], AGING)).toBe('应收账款 · 按账龄披露（期末数） · 5 行 · 可填 5 格')
    expect(priorTableLabel(PREVIEW.prior_tables[3], AGING)).toBe('其他非流动资产 · 合同资产情况 · 2 行')
    expect(hasMappedColumn(switchPriorTable(AGING, 't4'))).toBe(false)
    expect(hasMappedColumn(switchPriorTable(AGING, 't2'))).toBe(true)
    expect(hasMappedColumn(undefined)).toBe(false)
  })

  it('提示文字：列对应 / 预览概况 / 写入回执（没填进格的表单独说明）', () => {
    expect(columnsText(AGING, setColumn(switchPriorTable(AGING, 't3'), 4, null), PREVIEW.prior_tables[2]))
      .toBe('期初余额/账面余额 ← 期末余额/账面余额；期初余额/坏账准备 ← 不导入')
    expect(previewSummary(PREVIEW)).toBe(
      '章节对上 3 节，上年另有 1 节在本年附注里没有对应；有期初列的表：自动认出 1 张、待确认 1 张、上年没有 1 张')
    expect(appliedText(APPLIED, 2)).toBe('已导入正文 2 节、表格 1 张（6 格）；1 张表没有可填的空格（行名对不上或本年这些格已有值）')
    expect(appliedText({ ...APPLIED, filled_cells: 0, tables_written: 0, text_filled: 0 }, 0)).toBe('没有导入任何内容')
  })

  it('请求：同一端点，预览 / 写入走查询参数 mode，静默全局拦截器；写入重传文件并带指纹与逐表确认', async () => {
    const file = new File(['x'], '上年附注.docx')
    post.mockResolvedValue(PREVIEW)
    await previewPriorYear('p1', 2025, file)
    const [url, form, config] = post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/notes/import-prior-year')
    expect(config).toEqual({ params: { year: 2025, mode: 'preview' }, _silent: true })
    expect((form as FormData).get('file')).toBe(file)
    const decisions = [{ key: 'n1:0', prior_table_id: 't1', col_map: { 2: 1 } }]
    await applyPriorYear('p1', 2025, file, 'f'.repeat(64), decisions, false)
    const [, applyForm, applyConfig] = post.mock.calls[1]
    expect(applyConfig).toEqual({ params: { year: 2025, mode: 'apply' }, _silent: true })
    expect(JSON.parse(String((applyForm as FormData).get('decisions')))).toEqual(decisions)
    expect([(applyForm as FormData).get('file_sha256'), (applyForm as FormData).get('import_text')])
      .toEqual(['f'.repeat(64), 'false'])
  })
})

// ── 弹窗接线 ───────────────────────────────────────────────────────────────

const stubs = {
  'el-dialog': { props: ['modelValue', 'title'], template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-button': { props: ['disabled', 'loading', 'type', 'size', 'link'], emits: ['click'],
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' },
  'el-tag': { props: ['type', 'effect', 'size'], template: '<span class="el-tag" :data-type="type"><slot /></span>' },
  'el-alert': { props: ['title', 'type'], template: '<div class="el-alert" :data-type="type">{{ title }}</div>' },
  'el-checkbox': { name: 'ElCheckboxStub', props: ['modelValue', 'disabled'], emits: ['update:modelValue'],
    template: '<label class="el-checkbox" :data-checked="modelValue ? 1 : 0" :data-disabled="disabled ? 1 : 0"><slot /></label>' },
  'el-radio-group': { name: 'ElRadioGroupStub', props: ['modelValue'], emits: ['update:modelValue'],
    template: '<div class="el-radio-group" :data-value="modelValue"><slot /></div>' },
  'el-radio-button': { props: ['value'], template: '<span class="el-radio-button"><slot /></span>' },
  'el-select': { name: 'ElSelectStub', props: ['modelValue', 'disabled', 'placeholder'], emits: ['update:modelValue'],
    template: '<div class="el-select" :data-value="modelValue == null ? \'\' : String(modelValue)" :data-disabled="disabled ? 1 : 0"><slot /></div>' },
  'el-option-group': { props: ['label'], template: '<div class="el-option-group" :data-label="label"><slot /></div>' },
  'el-option': { props: ['value', 'label'], template: '<span class="el-option" :data-value="value">{{ label }}</span>' },
}

type Wrapper = VueWrapper<InstanceType<typeof NotePriorYearImportDialog>>

async function upload(wrapper: Wrapper, name = '上年附注.docx', size = 10) {
  const input = wrapper.find('input[type="file"]')
  const file = new File(['x'.repeat(size)], name)
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
  return file
}

async function mountWithPreview(preview: unknown = PREVIEW) {
  post.mockResolvedValueOnce(preview)
  const wrapper = mount(NotePriorYearImportDialog, { props: { visible: true, projectId: 'p1', year: 2025 }, global: { stubs } })
  const file = await upload(wrapper)
  return { wrapper, file }
}

const button = (w: Wrapper, text: string) => w.findAll('button').find(b => b.text().includes(text))!
const item = (w: Wrapper, key: string) => w.find(`.gt-npy-item[data-key="${key}"]`)
const selects = (w: Wrapper) => w.findAllComponents({ name: 'ElSelectStub' })
const textCheckbox = (w: Wrapper) => w.findAllComponents({ name: 'ElCheckboxStub' }).find(c => c.classes('gt-npy-text'))!

async function showAll(wrapper: Wrapper) {
  wrapper.findComponent({ name: 'ElRadioGroupStub' }).vm.$emit('update:modelValue', 'all')
  await flushPromises()
}

describe('NotePriorYearImportDialog', () => {
  it('选文件即预览；有待确认的表时先只列待确认的，自动认出的已默认勾选', async () => {
    const { wrapper } = await mountWithPreview()
    expect(post.mock.calls[0][2]).toEqual({ params: { year: 2025, mode: 'preview' }, _silent: true })
    expect(wrapper.find('.gt-npy-summary').text()).toContain('待确认 1 张')
    expect(wrapper.findAll('.gt-npy-item').map(i => i.attributes('data-key'))).toEqual(['n2:0'])
    expect(item(wrapper, 'n2:0').find('.gt-npy-reason').text()).toContain('没有与「按账龄披露」对应的表')
    expect(button(wrapper, '确认写入').text()).toContain('1 张表')
    await showAll(wrapper)
    expect(item(wrapper, 'n1:0').find('.el-checkbox').attributes('data-checked')).toBe('1')
    expect(item(wrapper, 'n1:0').text()).toContain('可填 2 格')
  })

  it('待确认的表：改选上年表（列对应取服务端算好的）→ 改一列 → 写入只提交确认的内容；导入正文先二次确认', async () => {
    const { wrapper, file } = await mountWithPreview()
    await button(wrapper, '调整').trigger('click')
    const [tableSelect] = selects(wrapper)
    expect(tableSelect.findAll('.el-option-group').map(g => g.attributes('data-label'))).toEqual(
      ['上年本节的表', '上年其他章节的表（需逐列指定）'])
    tableSelect.vm.$emit('update:modelValue', 't3')
    await flushPromises()
    expect(item(wrapper, 'n2:0').find('.el-checkbox').attributes('data-checked')).toBe('1')
    expect(item(wrapper, 'n2:0').text()).toContain('可填 5 格')
    selects(wrapper)[2].vm.$emit('update:modelValue', undefined)  // 清空「期初余额/坏账准备」⇒ 这一列不导入
    await flushPromises()
    expect(item(wrapper, 'n2:0').text()).toContain('可填格数以写入结果为准')
    expect(item(wrapper, 'n2:0').find('.gt-npy-map').text()).toContain('期初余额/坏账准备 ← 不导入')

    post.mockResolvedValueOnce(APPLIED)
    await button(wrapper, '确认写入（2 张表）').trigger('click')
    await flushPromises()
    expect(String(msg.confirm.mock.calls[0][0])).toContain('替换本年 2 节附注的正文')
    const [, form, config] = post.mock.calls[1]
    expect(config).toEqual({ params: { year: 2025, mode: 'apply' }, _silent: true })
    expect((form as FormData).get('file')).toBe(file)
    expect(JSON.parse(String((form as FormData).get('decisions')))).toEqual([
      { key: 'n1:0', prior_table_id: 't1', col_map: { 2: 1 } }, { key: 'n2:0', prior_table_id: 't3', col_map: { 3: 1 } }])
    expect([(form as FormData).get('file_sha256'), (form as FormData).get('import_text')]).toEqual(['f'.repeat(64), 'true'])
    expect(msg.success).toHaveBeenCalledWith(expect.stringContaining('已导入正文 2 节、表格 1 张（6 格）'))
    expect(wrapper.emitted('applied')?.[0]?.[0]).toEqual(APPLIED)
    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
  })

  it('二次确认取消 ⇒ 不写入；不导入正文时不弹确认', async () => {
    const { wrapper } = await mountWithPreview()
    msg.confirm.mockRejectedValueOnce('cancel')
    await button(wrapper, '确认写入').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    textCheckbox(wrapper).vm.$emit('update:modelValue', false)
    post.mockResolvedValueOnce({ ...APPLIED, text_filled: 0 })
    await button(wrapper, '确认写入').trigger('click')
    await flushPromises()
    expect(msg.confirm).toHaveBeenCalledTimes(1)
    expect((post.mock.calls[1][1] as FormData).get('import_text')).toBe('false')
  })

  it('上年没有的表可从其他章节选表，但须逐列指定；没指定列不能写入并说明是哪张表', async () => {
    const { wrapper } = await mountWithPreview()
    wrapper.findComponent({ name: 'ElRadioGroupStub' }).vm.$emit('update:modelValue', 'no_source')
    await flushPromises()
    await button(wrapper, '调整').trigger('click')
    const [tableSelect] = selects(wrapper)
    expect(tableSelect.findAll('.el-option-group').map(g => g.attributes('data-label'))).toEqual(
      ['上年其他章节的表（需逐列指定）'])
    tableSelect.vm.$emit('update:modelValue', 't4')
    await flushPromises()
    expect(item(wrapper, 'n3:0').text()).toContain('未指定列')  // 不报「可填 0 格」：没有列可填不是行名对不上
    expect(wrapper.find('.gt-npy-problem').text()).toContain('五、9 合同资产 · 合同资产情况：没有指定任何列')
    expect(button(wrapper, '确认写入').attributes('disabled')).toBeDefined()
    selects(wrapper)[1].vm.$emit('update:modelValue', 1)
    await flushPromises()
    expect(wrapper.find('.gt-npy-problem').exists()).toBe(false)
    expect(button(wrapper, '确认写入（2 张表）').attributes('disabled')).toBeUndefined()
  })

  it('服务端要求重新预览（文件变了 409）⇒ 预览作废、禁止写入；重新预览后恢复', async () => {
    const { wrapper } = await mountWithPreview()
    textCheckbox(wrapper).vm.$emit('update:modelValue', false)
    post.mockRejectedValueOnce(Object.assign(new Error('409'), {
      response: { status: 409, data: { detail: '上传的文件与预览时的文件不同，请重新预览' } } }))
    await button(wrapper, '确认写入').trigger('click')
    await flushPromises()
    expect(msg.error).toHaveBeenCalledWith('上传的文件与预览时的文件不同，请重新预览')
    expect(wrapper.findAll('.el-alert').map(a => a.text()).join()).toContain('预览已过期')
    expect(button(wrapper, '确认写入').attributes('disabled')).toBeDefined()
    expect(wrapper.emitted('applied')).toBeUndefined()
    post.mockResolvedValueOnce(PREVIEW)
    await button(wrapper, '重新预览').trigger('click')
    await flushPromises()
    expect(post.mock.calls[2][2]).toEqual({ params: { year: 2025, mode: 'preview' }, _silent: true })
    expect(wrapper.findAll('.el-alert')).toHaveLength(0)
    expect(button(wrapper, '确认写入').attributes('disabled')).toBeUndefined()
  })

  it('文档解析不出内容 / 本年附注未生成（200 + status=error）：显示原因，不列表格', async () => {
    const { wrapper } = await mountWithPreview({ status: 'error', message: '本年附注尚未生成，请先生成附注再导入上年数据' })
    expect(wrapper.find('.el-alert').text()).toBe('本年附注尚未生成，请先生成附注再导入上年数据')
    expect(wrapper.find('.gt-npy-list').exists()).toBe(false)
    expect(button(wrapper, '确认写入').attributes('disabled')).toBeDefined()
  })

  it('前端拒收非 .docx 与超过 50MB 的文件（不发请求）；扩展名大小写不敏感', async () => {
    const wrapper = mount(NotePriorYearImportDialog, { props: { visible: true, projectId: 'p1', year: 2025 }, global: { stubs } })
    await upload(wrapper, '上年附注.doc')
    expect(post).not.toHaveBeenCalled()
    expect(msg.error).toHaveBeenCalledWith(expect.stringContaining('上年附注.doc：仅支持 .docx'))
    const input = wrapper.find('input[type="file"]')
    const big = new File(['x'], '大.docx')
    Object.defineProperty(big, 'size', { value: 50 * 1024 * 1024 + 1 })
    Object.defineProperty(input.element, 'files', { value: [big], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(post).not.toHaveBeenCalled()
    post.mockResolvedValueOnce(PREVIEW)
    await upload(wrapper, '上年附注.DOCX')
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('调整过勾选 / 对应后关闭先确认，取消则留在弹窗', async () => {
    const { wrapper } = await mountWithPreview()
    await showAll(wrapper)
    item(wrapper, 'n1:0').findComponent({ name: 'ElCheckboxStub' }).vm.$emit('update:modelValue', false)
    await flushPromises()
    msg.confirm.mockRejectedValueOnce('cancel')
    await button(wrapper, '取消').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:visible')).toBeUndefined()
    await button(wrapper, '取消').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
  })
})
