import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, inject, provide } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const { api, service, message, confirm, bus, excel, confirmBatch, confirmDangerous, acnr, routerPush } = vi.hoisted(() => ({
  api: { get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn() },
  service: { getConsolNoteBreakdown: vi.fn(), listConsolNoteFormulas: vi.fn(), fillConsolNoteByFormula: vi.fn() },
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  confirm: vi.fn(), bus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
  excel: { exportMultiSheetData: vi.fn(), readSheetAoa: vi.fn(), readWorkbookAoa: vi.fn() },
  confirmBatch: vi.fn(), confirmDangerous: vi.fn(), acnr: { resolveIndex: vi.fn() }, routerPush: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/services/consolidationApi', () => service)
vi.mock('element-plus', () => ({ ElMessage: message, ElMessageBox: { confirm } }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPush }) }))
vi.mock('@/services/acnr/useAcnr', () => ({ useAcnr: () => acnr }))
vi.mock('@/utils/confirm', () => ({ confirmBatch, confirmDangerous }))
vi.mock('@/utils/eventBus', () => ({ eventBus: bus }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/composables/useExcelIO', () => excel)
import ConsolNoteTab from '../ConsolNoteTab.vue'

function section(standard: string, id = '五-5-2') {
  const all = JSON.parse(readFileSync(resolve(process.cwd(), `../../backend/data/consol_note_sections_${standard}.json`), 'utf8'))
  return { ...all.find((s: any) => s.section_id === id), template_type: standard }
}
function deferred<T = any>() {
  let resolve!: (v: T) => void, reject!: (v: any) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const Table = defineComponent({
  props: ['data'],
  setup(p, { slots, attrs }) {
    provide('note-rows', () => p.data || [])
    return () => h('div', { class: 'fixture-table', ...attrs }, slots.default?.())
  },
})
// Unlike an empty table-column stub, this keeps group slots and renders leaf cells.
const Column = defineComponent({
  props: ['label', 'prop', 'type'],
  setup(p, { slots }) {
    const rows = inject<() => any[]>('note-rows', () => [])
    return () => h('div', { 'data-label': p.label, 'data-prop': p.prop }, p.prop !== undefined
      ? rows().map((row, $index) => h('div', { class: 'fixture-cell', 'data-row': $index }, slots.default?.({ row, $index })))
      : p.type ? [] : slots.default?.())
  },
})
const Pass = defineComponent({ setup(_, { slots }) { return () => h('div', slots.default?.()) } })
const Dialog = defineComponent({ props: ['modelValue'], setup(p, { slots }) { return () => p.modelValue ? h('div', slots.default?.()) : null } })
const Button = defineComponent({ setup(_, { slots, attrs }) { return () => h('button', attrs, slots.default?.()) } })
const wrappers: ReturnType<typeof mount>[] = []
function mountTab(extra: Record<string, unknown> = {}) {
  const wrapper = mount(ConsolNoteTab, {
    props: { projectId: 'fixture-project', year: 2025, standard: 'soe', currentEntity: { nodeKey: 'G:consol', code: 'G' }, groupTree: [], consolNoteTree: [], ...extra } as any,
    global: { directives: { loading: {} }, stubs: {
      'el-table': Table, 'el-table-column': Column, 'el-dialog': Dialog, 'el-button': Button, 'el-tooltip': Pass,
      'el-button-group': Pass, 'el-empty': true, 'el-input': true, 'el-select': Pass, 'el-option': true, 'el-alert': true,
      'el-divider': true, 'el-tag': Pass, 'el-radio-group': Pass, 'el-radio-button': Pass, 'el-tree': true,
      teleport: true, 'el-radio': true,
      CellContextMenu: true, CommentTooltip: Pass, SelectionBar: true, GtAmountCell: true,
    } },
  })
  wrappers.push(wrapper)
  return wrapper
}
const state = (w: any) => w.vm.$.setupState as any
const exposed = (w: any) => w.vm as any
async function loaded(extra: Record<string, unknown> = {}) {
  const w = mountTab(extra)
  await exposed(w).onNoteNodeClick({ section_id: '五-5-2' })
  await flushPromises()
  return w
}
function markDirty(w: any) {
  const s = state(w)
  s.noteEditMode = true
  s.onNoteCellInput(s.selectedNoteSection.editRows[2], 1)
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset())
  Object.values(service).forEach((f) => f.mockReset())
  Object.values(message).forEach((f) => f.mockClear())
  Object.values(excel).forEach((f) => f.mockReset())
  acnr.resolveIndex.mockReset().mockResolvedValue({ found: false })
  routerPush.mockReset()
  confirmBatch.mockReset().mockResolvedValue(true)
  confirmDangerous.mockReset().mockResolvedValue(true)
  confirm.mockReset().mockResolvedValue('confirm')
  bus.emit.mockClear()
  sessionStorage.clear()
  api.get.mockImplementation(async (url: string) => {
    if (url.includes('/cell-comments/')) return []
    if (url.includes('/data/')) return { content: {}, node_key: 'G:consol' }
    return section(url.includes('/listed/') ? 'listed' : 'soe', decodeURIComponent(url.split('/').at(-1)!))
  })
  api.put.mockResolvedValue({ ok: true, node_key: 'G:consol' })
})
afterEach(() => { wrappers.splice(0).forEach((w) => w.unmount()) })

 describe('CP04/05 actual note component', () => {
  it.each(['soe', 'listed'])('renders %s nested groups and distinct leaf amounts in normal and fullscreen tables', async (standard) => {
    const config = section(standard), width = config.headers.length
    const body = config._header_row_indexes?.length ? 2 : 0
    config.rows[body] = ['独特金额', ...Array.from({ length: width - 1 }, (_, i) => String((i + 1) * 101))]
    api.get.mockImplementation(async (url: string) => url.includes('/data/') ? { content: {}, node_key: 'G:consol' } : config)
    const w = await loaded({ standard })
    const s = state(w)
    expect(s.parsedMultiHeader[1].children.map((c: any) => c.label)).toEqual(['账面余额', '坏账准备', '账面价值'])
    expect(w.findAll('[data-prop]')).toHaveLength(width)
    for (let c = 1; c < width; c++) expect(w.find(`[data-prop="${c}"] .fixture-cell`).text()).toBe(String(c * 101))
    if (standard === 'listed') expect(s.noteVisibleRows).toHaveLength(9)
    s.noteFullscreen = true
    await flushPromises()
    expect(w.findAll('[data-prop]')).toHaveLength(2 * width)
    for (let c = 1; c < width; c++) expect(w.findAll(`[data-prop="${c}"] .fixture-cell`)[config.rows.length - body].text()).toBe(String(c * 101))
  })

  it('switch reloads same section immediately; freezes variant; does not PUT or POST', async () => {
    const w = await loaded()
    const pending = deferred()
    api.get.mockImplementation((url: string) => url.includes('/listed/') ? pending.promise : Promise.resolve({ content: {}, node_key: 'G:consol' }))
    await w.setProps({ standard: 'listed' })
    expect(exposed(w).selectedNoteSection).toBeNull()
    expect(await exposed(w).saveNoteData()).toBe(false)
    pending.resolve(section('listed'))
    await flushPromises()
    expect(exposed(w).selectedNoteSection.headers).toHaveLength(6)
    expect(exposed(w).loadedNoteContext.variant).toBe('listed')
    expect(api.put).not.toHaveBeenCalled()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('dirty section cancellation restores identical edited object without any network write', async () => {
    const w = await loaded()
    markDirty(w)
    const original = exposed(w).selectedNoteSection
    const decision = deferred()
    confirm.mockReturnValue(decision.promise)
    const switching = exposed(w).onNoteNodeClick({ section_id: '五-5-3' })
    expect(exposed(w).selectedNoteSection).toBeNull()
    expect(await exposed(w).saveNoteData()).toBe(false)
    decision.reject('cancel')
    expect((await switching).status).toBe('skipped')
    expect(exposed(w).selectedNoteSection).toBe(original)
    expect(exposed(w).noteDirty).toBe(true)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('dirty template cancellation emits full rollback identity; remains non-saveable until parent restores props', async () => {
    const w = await loaded()
    markDirty(w)
    const original = exposed(w).selectedNoteSection
    confirm.mockRejectedValue('cancel')
    await w.setProps({ standard: 'listed' })
    await flushPromises()
    expect(w.emitted('restore-note-context')?.[0]?.[0]).toEqual({ projectId: 'fixture-project', year: 2025, nodeKey: 'G:consol', variant: 'soe', sectionId: '五-5-2' })
    expect(exposed(w).selectedNoteSection).toBeNull()
    expect(await exposed(w).saveNoteData()).toBe(false)
    await w.setProps({ standard: 'soe' })
    expect(exposed(w).selectedNoteSection).toBe(original)
    expect(exposed(w).noteDirty).toBe(true)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('dirty accept discards only after explicit confirmation, loads new variant without saving', async () => {
    const w = await loaded()
    markDirty(w)
    await w.setProps({ standard: 'listed' })
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('未保存'), '切换附注', expect.objectContaining({ confirmButtonText: '放弃修改并切换' }))
    expect(exposed(w).selectedNoteSection.headers).toHaveLength(6)
    expect(exposed(w).noteDirty).toBe(false)
    expect(api.put).not.toHaveBeenCalled()
  })
})

describe('CP05 late response and save boundaries', () => {
  it.each(['detail', 'saved'])('A-B-A discards old %s successes even if cancellation is ignored', async (stage) => {
    const w = mountTab(), pending = deferred()
    let first = true
    let signal: AbortSignal | undefined
    api.get.mockImplementation((url: string, options?: any) => {
      if (url.includes('/cell-comments/')) return Promise.resolve([])
      const saved = url.includes('/data/')
      if (first && saved === (stage === 'saved')) {
        first = false; signal = options.signal
        return pending.promise
      }
      return Promise.resolve(saved ? { content: {}, node_key: 'G:consol' } : section(url.includes('/listed/') ? 'listed' : 'soe'))
    })
    const old = exposed(w).onNoteNodeClick({ section_id: '五-5-2' })
    await flushPromises()
    await w.setProps({ standard: 'listed' }); await flushPromises()
    await w.setProps({ standard: 'soe' }); await flushPromises()
    const current = exposed(w).selectedNoteSection
    expect(signal?.aborted).toBe(true)
    const obsolete = section('soe'); obsolete.title = '旧标题不应复活'
    pending.resolve(stage === 'detail' ? obsolete : { content: { headers: obsolete.headers, rows: [['旧金额', '98765']] }, node_key: 'G:consol' })
    expect((await old).status).toBe('stale')
    expect(exposed(w).selectedNoteSection).toBe(current)
    expect(current.title).not.toBe(obsolete.title)
    expect(api.put).not.toHaveBeenCalled()
  })

  it.each(['detail', 'saved'])('old %s failures stay silent after a template switch', async (stage) => {
    const w = mountTab(), pending = deferred()
    let first = true
    api.get.mockImplementation((url: string) => {
      if (url.includes('/cell-comments/')) return Promise.resolve([])
      const saved = url.includes('/data/')
      if (first && saved === (stage === 'saved')) { first = false; return pending.promise }
      return Promise.resolve(saved ? { content: {}, node_key: 'G:consol' } : section(url.includes('/listed/') ? 'listed' : 'soe'))
    })
    const old = exposed(w).onNoteNodeClick({ section_id: '五-5-2' }); await flushPromises()
    await w.setProps({ standard: 'listed' }); await flushPromises()
    pending.reject(new Error('旧请求错误'))
    expect((await old).status).toBe('stale')
    expect(message.error).not.toHaveBeenCalled()
    expect(exposed(w).loadedNoteContext.variant).toBe('listed')
  })

  it.each([
    { year: 2026 }, { projectId: 'next-project' }, { currentEntity: { nodeKey: 'H:consol', code: 'H' } },
  ])('scope change %j aborts old reads, closes dialogs and keeps writes disabled until reload', async (change) => {
    const w = await loaded(), s = state(w), pending = deferred()
    s.showFillResultDialog = true; s.showNoteBreakdownDialog = true
    api.get.mockImplementation((url: string) => url.includes('/cell-comments/') ? Promise.resolve([]) : pending.promise)
    await w.setProps(change)
    expect(exposed(w).selectedNoteSection).toBeNull()
    expect(s.showFillResultDialog).toBe(false); expect(s.showNoteBreakdownDialog).toBe(false)
    expect(await exposed(w).saveNoteData()).toBe(false)
    expect(api.put).not.toHaveBeenCalled()
    w.unmount(); pending.resolve(section('soe')); await flushPromises()
  })

  it('unmount aborts pending section load and suppresses its late failure', async () => {
    const w = mountTab(), pending = deferred()
    let signal!: AbortSignal
    api.get.mockImplementation((_url: string, opts: any) => { signal = opts.signal; return pending.promise })
    const old = exposed(w).onNoteNodeClick({ section_id: '五-5-2' })
    w.unmount(); expect(signal.aborted).toBe(true)
    pending.reject(new Error('已卸载'))
    expect((await old).status).toBe('stale')
    expect(message.error).not.toHaveBeenCalled()
  })
})

describe('CP05 pending mutations', () => {
  it.each(['success', 'failure'])('old save %s cannot clear new dirty state after A-B-A', async (outcome) => {
    const w = await loaded(), pending = deferred()
    markDirty(w)
    api.put.mockReturnValue(pending.promise)
    const saving = exposed(w).saveNoteData()
    expect(api.put.mock.calls[0][0]).toContain('fixture-project/2025/五-5-2')
    expect(api.put.mock.calls[0][1].data.template_variant).toBe('soe')
    await w.setProps({ standard: 'listed' }); await flushPromises()
    await w.setProps({ standard: 'soe' }); await flushPromises()
    const current = exposed(w).selectedNoteSection
    markDirty(w)
    if (outcome === 'success') pending.resolve({ ok: true, node_key: 'G:consol' })
    else pending.reject(new Error('旧保存错误'))
    expect(await saving).toBe(false)
    expect(exposed(w).selectedNoteSection).toBe(current)
    expect(exposed(w).noteDirty).toBe(true)
    expect(message.success).not.toHaveBeenCalled()
  })

  it('save preserves edits made during PUT and persists manual/locked coordinates unchanged', async () => {
    const cfg = section('listed'), pending = deferred()
    api.get.mockImplementation(async (url: string) => url.includes('/cell-comments/') ? [] : url.includes('/data/') ? {
      content: { headers: cfg.headers, rows: cfg.rows, manual_cells: [{ row: 2, col: 5 }], locked_cells: ['2:5'], template_variant: 'listed' }, node_key: 'G:consol',
    } : cfg)
    const w = await loaded({ standard: 'listed' }), sec = exposed(w).selectedNoteSection
    sec.editRows[2][5] = '101'
    markDirty(w)
    api.put.mockReturnValue(pending.promise)
    const saving = exposed(w).saveNoteData()
    const data = api.put.mock.calls[0][1].data
    expect(data.rows).toHaveLength(cfg.rows.length)
    expect(data.rows[0]).toEqual(cfg.rows[0]); expect(data.rows[2][5]).toBe('101')
    expect(data.manual_cells).toContainEqual({ row: 2, col: 5 })
    expect(data.locked_cells).toEqual(['2:5'])
    sec.editRows[2][5] = '303'; state(w).onNoteCellInput(sec.editRows[2], 5)
    pending.resolve({ ok: true, node_key: 'G:consol', section_id: '五-5-2' })
    expect(await saving).toBe(true)
    expect(exposed(w).noteDirty).toBe(true)
    expect(sec.editRows[2][5]).toBe('303')
    expect(sec.savedData.rows[2][5]).toBe('101')
  })

  it('mismatched save response cannot clear dirty', async () => {
    const w = await loaded(); markDirty(w)
    api.put.mockResolvedValue({ ok: true, node_key: 'OTHER:consol' })
    expect(await exposed(w).saveNoteData()).toBe(false)
    expect(exposed(w).noteDirty).toBe(true)
  })

  it('mismatched loaded variant or section rejects save before PUT', async () => {
    const w = await loaded(), s = state(w)
    s.loadedNoteContext = { ...s.loadedNoteContext, variant: 'listed' }
    expect(await exposed(w).saveNoteData()).toBe(false)
    s.loadedNoteContext = { ...s.loadedNoteContext, variant: 'soe', sectionId: '五-5-3' }
    expect(await exposed(w).saveNoteData()).toBe(false)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('late leave-edit confirmation cannot clear a newly loaded dirty note', async () => {
    const w = await loaded(), decision = deferred(); markDirty(w)
    confirm.mockReturnValueOnce(decision.promise).mockResolvedValue('confirm')
    const leaving = state(w).leaveNoteEdit()
    await w.setProps({ standard: 'listed' }); await flushPromises(); markDirty(w)
    decision.resolve('confirm'); await leaving
    expect(exposed(w).noteDirty).toBe(true)
    expect(state(w).noteEditMode).toBe(true)
    expect(exposed(w).loadedNoteContext.variant).toBe('listed')
  })

  it('new editing during save prevents formula fill from overwriting it', async () => {
    const w = await loaded(), pending = deferred(); markDirty(w)
    api.put.mockReturnValue(pending.promise)
    const fill = exposed(w).fillCurrentByFormula()
    state(w).selectedNoteSection.editRows[2][1] = '809'; markDirty(w)
    pending.resolve({ ok: true, node_key: 'G:consol' })
    expect((await fill).status).toBe('skipped')
    expect(service.fillConsolNoteByFormula).not.toHaveBeenCalled()
    expect(exposed(w).noteDirty).toBe(true)
  })

  it('late file parsing never mutates the new variant or its dirty state', async () => {
    const w = await loaded(), pending = deferred(), original = exposed(w).selectedNoteSection
    excel.readSheetAoa.mockReturnValue(pending.promise)
    const importing = state(w).onNoteFileSelected({ target: { files: [new File([''], 'test.xlsx')] } })
    await w.setProps({ standard: 'listed' }); await flushPromises()
    pending.resolve({ rows: [['迟到业务行', '100']] }); await importing
    expect(original.editRows.some((r: any) => r[0] === '迟到业务行')).toBe(false)
    expect(exposed(w).noteDirty).toBe(false)
    expect(api.put).not.toHaveBeenCalled()
  })
})

describe('CP04 stored coordinates and asynchronous readers', () => {
  it('projected cells, comments, copy and Excel retain the original amount columns', async () => {
    const w = await loaded({ standard: 'listed' }), s = state(w), sec = exposed(w).selectedNoteSection
    sec.editRows[2][5] = '505'
    s.onNoteCellClick(sec.editRows[2], { property: '5' }, document.createElement('td'), new MouseEvent('click'))
    expect(exposed(w).selectedCells[0]).toEqual({ row: 2, col: 5, value: '505' })
    expect(exposed(w).drillDownCell.rowIdx).toBe(2); expect(exposed(w).drillDownCell.colIdx).toBe(5)
    const copy = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: copy } })
    s.copyEntireNoteTable()
    const text = copy.mock.calls[0][0]
    expect(text.split('\n')).toHaveLength(10)
    expect(text.split('\n')[1].split('\t')[5]).toBe('505')
    expect(text).not.toContain('账面余额\t坏账准备')
    await s.exportNoteData()
    const rows = excel.exportMultiSheetData.mock.calls[0][0].sheets[0].rows
    expect(rows).toHaveLength(10); expect(rows[1][5]).toBe('505')
  })

  it('batch import restores exact listed header slots and manual coordinates', async () => {
    const w = await loaded({ standard: 'listed' }), cfg = section('listed')
    excel.readWorkbookAoa.mockResolvedValue({ sheetNames: [cfg.title], sheets: { [cfg.title]: [cfg.headers, ['人工业务', '101', '202', '303', '404', '505'], ['', '', '', '', '', '']] } })
    api.get.mockImplementation(async (url: string) => url.endsWith('/listed') ? [{ children: [{ title: cfg.title, section_id: cfg.section_id }] }] : url.includes('/cell-comments/') ? [] : cfg)
    await state(w).onNoteBatchImport({ target: { files: [new File([''], 'test.xlsx')] } })
    const data = api.put.mock.calls[0][1].data
    expect(data.rows.slice(0, 2)).toEqual(cfg.rows.slice(0, 2))
    expect(data.rows[2][5]).toBe('505'); expect(data.rows[3]).toEqual(['', '', '', '', '', ''])
    expect(data.manual_cells).toContainEqual({ row: 2, col: 5 })
    expect(data.manual_cells.every((c: any) => c.row >= 2)).toBe(true)
    expect(data.template_variant).toBe('listed')
  })

  it('late breakdown response is cancelled and cannot reopen after template switch', async () => {
    const w = await loaded(), pending = deferred()
    service.getConsolNoteBreakdown.mockReturnValue(pending.promise)
    const old = exposed(w).openNoteBreakdown()
    const opts = service.getConsolNoteBreakdown.mock.calls[0][3]
    await w.setProps({ standard: 'listed' }); await flushPromises()
    expect(opts.signal.aborted).toBe(true)
    pending.resolve({ node_key: 'G:consol', section_id: '五-5-2', cells: [] }); await old
    expect(state(w).noteBreakdown).toBeNull()
    expect(state(w).showNoteBreakdownDialog).toBe(false)
  })

  it('late audit result cannot reopen new view or clear its loading', async () => {
    const w = await loaded(), pending = deferred()
    api.post.mockReturnValue(pending.promise)
    const auditing = state(w).auditCurrentNote()
    await w.setProps({ standard: 'listed' }); await flushPromises()
    state(w).noteSingleAuditLoading = true
    pending.resolve({ results: [{ level: 'error', message: '旧审核' }] }); await auditing
    expect(state(w).noteAuditResults).toEqual([])
    expect(state(w).showNoteAuditDialog).toBe(false)
    expect(state(w).noteSingleAuditLoading).toBe(true)
  })

  it('late comments remain attached to the old instance, not the new template', async () => {
    const pending = deferred(); let reads = 0
    api.get.mockImplementation(async (url: string) => {
      if (url.includes('/cell-comments/')) return ++reads === 1 ? pending.promise : []
      return url.includes('/data/') ? { content: {}, node_key: 'G:consol' } : section(url.includes('/listed/') ? 'listed' : 'soe')
    })
    const w = await loaded()
    await w.setProps({ standard: 'listed' }); await flushPromises()
    pending.resolve([{ id: 'old', sheet_key: '五-5-2', row_idx: 2, col_idx: 5, comment_type: 'comment', comment: '旧模板批注' }])
    await flushPromises()
    expect(state(w).cellComments.getComment('五-5-2', 2, 5)).toBeUndefined()
  })

  it('late delete confirmation never deletes a new chapter selection', async () => {
    const w = await loaded(), decision = deferred(), s = state(w)
    s.noteSelectedRows = [s.selectedNoteSection.editRows[2]]
    confirmBatch.mockReturnValue(decision.promise)
    const deleting = s.deleteNoteRows(); await flushPromises()
    await w.setProps({ standard: 'listed' }); await flushPromises()
    const sec = exposed(w).selectedNoteSection, count = sec.editRows.length
    s.noteSelectedRows = [sec.editRows[2]]
    decision.resolve(true); await deleting
    expect(sec.editRows.length).toBe(count)
    expect(exposed(w).noteDirty).toBe(false)
  })
})

describe('CP05 remaining async scope boundaries', () => {
  it('new editing during PUT prevents batch formula writes', async () => {
    const w = await loaded(), pending = deferred(); markDirty(w)
    api.put.mockReturnValue(pending.promise)
    const filling = state(w).fillAllByFormula()
    state(w).selectedNoteSection.editRows[2][1] = '909'; markDirty(w)
    pending.resolve({ ok: true, node_key: 'G:consol' }); await filling
    expect(service.listConsolNoteFormulas).not.toHaveBeenCalled()
    expect(service.fillConsolNoteByFormula).not.toHaveBeenCalled()
    expect(exposed(w).noteDirty).toBe(true)
  })

  it('late formula catalog cannot fill or clear the new template loading', async () => {
    const w = await loaded(), pending = deferred()
    service.listConsolNoteFormulas.mockReturnValue(pending.promise)
    const filling = state(w).fillAllByFormula()
    const signal = service.listConsolNoteFormulas.mock.calls[0][2]
    await w.setProps({ standard: 'listed' }); await flushPromises()
    state(w).noteBatchLoading = true
    expect(signal.aborted).toBe(true)
    pending.resolve([{ section_id: '五-5-2' }]); await filling
    expect(service.fillConsolNoteByFormula).not.toHaveBeenCalled()
    expect(state(w).noteBatchLoading).toBe(true)
  })

  it.each(['success', 'failure'])('late formula file %s stays silent and does not clear new loading', async (outcome) => {
    const w = await loaded(), pending = deferred()
    excel.readSheetAoa.mockReturnValue(pending.promise)
    const importing = state(w).onNoteFormulaImport({ target: { files: [new File([''], 'formula.xlsx')] } })
    await w.setProps({ standard: 'listed' }); await flushPromises(); state(w).noteBatchLoading = true
    if (outcome === 'success') pending.resolve({ rows: [['header'], ['rule']] })
    else pending.reject(new Error('旧公式文件错误'))
    await importing
    expect(message.success).not.toHaveBeenCalled()
    expect(state(w).noteBatchLoading).toBe(true)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('late formula export is cancelled, creates no file and leaves new loading alone', async () => {
    const w = await loaded(), pending = deferred(); let signal!: AbortSignal
    api.get.mockImplementation((url: string, opts?: any) => {
      if (url.endsWith('/soe')) { signal = opts.signal; return pending.promise }
      return Promise.resolve(url.includes('/cell-comments/') ? [] : url.includes('/data/') ? { content: {}, node_key: 'G:consol' } : section('listed'))
    })
    const exporting = state(w).exportNoteFormulas()
    await w.setProps({ standard: 'listed' }); await flushPromises(); state(w).noteBatchLoading = true
    expect(signal.aborted).toBe(true)
    pending.resolve([{ children: [{ section_id: '五-5-2', title: '旧模板' }] }]); await exporting
    expect(excel.exportMultiSheetData).not.toHaveBeenCalled()
    expect(state(w).noteBatchLoading).toBe(true)
  })

  it.each([true, false])('late ACNR result found=%s neither navigates nor loads old section', async (found) => {
    const w = await loaded(), pending = deferred()
    acnr.resolveIndex.mockReturnValue(pending.promise)
    const navigating = state(w).jumpToNoteSection('五-5-3')
    await w.setProps({ standard: 'listed' }); await flushPromises()
    const current = exposed(w).selectedNoteSection
    api.get.mockClear()
    pending.resolve({ found, jump_route: found ? '/old-scope' : undefined }); await navigating
    expect(routerPush).not.toHaveBeenCalled()
    expect(api.get).not.toHaveBeenCalled()
    expect(exposed(w).selectedNoteSection).toBe(current)
  })

  it('late aggregate confirmation never posts into the new selection', async () => {
    const w = await loaded(), s = state(w), pending = deferred()
    const sec = exposed(w).selectedNoteSection
    s.onNoteCellClick(sec.editRows[2], { property: '5' }, document.createElement('td'), new MouseEvent('click'))
    confirmDangerous.mockReturnValue(pending.promise)
    const aggregating = s.confirmAndExecuteAggregate(); await flushPromises()
    await w.setProps({ standard: 'listed' }); await flushPromises()
    pending.resolve(true); await aggregating
    expect(api.post).not.toHaveBeenCalled()
    expect(exposed(w).noteDirty).toBe(false)
  })

  it('DOM drag ranges use projected storage rows and original leaf columns', async () => {
    const w = await loaded({ standard: 'listed' }), s = state(w), sec = exposed(w).selectedNoteSection
    sec.editRows[2][5] = '505'; sec.editRows[3][5] = '606'
    const table = document.createElement('table'), tbody = table.createTBody()
    for (let r = 0; r < 2; r++) { const tr = tbody.insertRow(); for (let c = 0; c < 6; c++) tr.insertCell().className = 'el-table__cell' }
    const start = new MouseEvent('mousedown', { button: 0, cancelable: true })
    Object.defineProperty(start, 'target', { value: tbody.rows[0].cells[5] })
    s.onNoteDragStart(start)
    const move = new MouseEvent('mouseover')
    Object.defineProperty(move, 'target', { value: tbody.rows[1].cells[5] })
    s.onNoteDragMove(move)
    expect(start.defaultPrevented).toBe(true)
    expect(exposed(w).selectedCells).toEqual([{ row: 2, col: 5, value: '505' }, { row: 3, col: 5, value: '606' }])
  })
})


describe('CP05 reload, response identity and latest navigation', () => {
  it.each(['fill', 'aggregate'])('late %s persisted reload cannot notify or overwrite the new dirty view', async (operation) => {
    const w = await loaded(), pending = deferred()
    service.fillConsolNoteByFormula.mockResolvedValue({ filled: 1, kept: 0, blank: [], details: [] })
    api.post.mockResolvedValue({ sections_updated: 1, sections_processed: 1 })
    let oldReload = true
    api.get.mockImplementation((url: string) => {
      if (url.includes('/cell-comments/')) return Promise.resolve([])
      if (url.includes('/data/')) {
        if (oldReload) { oldReload = false; return pending.promise }
        return Promise.resolve({ content: {}, node_key: 'G:consol' })
      }
      return Promise.resolve(section('listed'))
    })
    const refreshing = operation === 'fill' ? exposed(w).fillCurrentByFormula() : exposed(w).handleReaggregate()
    await flushPromises()
    expect(oldReload).toBe(false)
    await w.setProps({ standard: 'listed' }); await flushPromises(); markDirty(w)
    const current = exposed(w).selectedNoteSection
    message.warning.mockClear(); message.success.mockClear()
    pending.resolve({ content: { headers: section('soe').headers, rows: [['迟到', '999']] }, node_key: 'G:consol' })
    expect((await refreshing).status).toBe('stale')
    expect(exposed(w).selectedNoteSection).toBe(current)
    expect(exposed(w).noteDirty).toBe(true)
    expect(message.warning).not.toHaveBeenCalled(); expect(message.success).not.toHaveBeenCalled()
  })

  it.each([
    ['template', 'detail'], ['section', 'detail'], ['node', 'saved'], ['variant', 'saved'], ['width', 'saved'],
  ])('rejects mismatched %s identity at the %s load boundary without accepting template fallback', async (kind, stage) => {
    const w = mountTab()
    api.get.mockImplementation(async (url: string) => {
      if (url.includes('/cell-comments/')) return []
      if (url.includes('/data/')) {
        if (stage !== 'saved') return { content: {}, node_key: 'G:consol' }
        if (kind === 'node') return { content: {}, node_key: 'OTHER:consol' }
        if (kind === 'variant') return { content: { template_variant: 'listed' }, node_key: 'G:consol' }
        return { content: { headers: section('listed').headers, rows: [] }, node_key: 'G:consol' }
      }
      const config = section('soe')
      if (kind === 'template') config.template_type = 'listed'
      if (kind === 'section') config.section_id = '五-5-3'
      return config
    })
    expect((await exposed(w).onNoteNodeClick({ section_id: '五-5-2' })).status).toBe('failed')
    expect(exposed(w).selectedNoteSection).toBeNull()
    expect(exposed(w).loadedNoteContext).toBeNull()
    expect(message.error).toHaveBeenCalled()
    expect(await exposed(w).saveNoteData()).toBe(false)
    expect(api.put).not.toHaveBeenCalled()
  })

  it('late batch workbook parsing leaves the new input, dialog and loading state untouched', async () => {
    const w = await loaded(), pending = deferred(), s = state(w)
    excel.readWorkbookAoa.mockReturnValue(pending.promise)
    const importing = s.onNoteBatchImport({ target: { files: [new File([''], 'batch.xlsx')] } })
    await w.setProps({ standard: 'listed' }); await flushPromises()
    s.noteBatchLoading = true; s.showNoteBatchDialog = true
    await flushPromises()
    const input = w.findAll('input[type="file"]')[1].element as HTMLInputElement
    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'new-file' })
    expect(s.noteBatchFileRef).toBe(input)
    api.get.mockClear()
    pending.resolve({ sheetNames: ['旧数据'], sheets: { 旧数据: [['头'], ['值']] } }); await importing
    expect(s.noteBatchLoading).toBe(true); expect(s.showNoteBatchDialog).toBe(true)
    expect(input.value).toBe('new-file')
    expect(api.get).not.toHaveBeenCalled(); expect(api.put).not.toHaveBeenCalled()
    expect(message.success).not.toHaveBeenCalled()
  })

  it('latest ACNR navigation wins even when two requests share the same page epoch', async () => {
    const w = await loaded(), first = deferred(), latest = deferred()
    acnr.resolveIndex.mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise)
    const old = state(w).jumpToNoteSection('五-5-3')
    const current = state(w).jumpToNoteSection('五-5-4')
    latest.resolve({ found: true, jump_route: '/latest' }); await current
    first.resolve({ found: true, jump_route: '/obsolete' }); await old
    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith('/latest')
  })
})


describe('CP05 equivalent props and shared dirty decision', () => {
  it('equivalent node object does not invalidate or prompt an unchanged dirty context', async () => {
    const w = await loaded(); markDirty(w)
    const original = exposed(w).selectedNoteSection
    api.get.mockClear(); confirm.mockClear()
    await w.setProps({ currentEntity: { nodeKey: 'G:consol', code: 'G', name: '同节点新对象' } })
    await flushPromises()
    expect(exposed(w).selectedNoteSection).toBe(original)
    expect(exposed(w).noteDirty).toBe(true)
    expect(confirm).not.toHaveBeenCalled(); expect(api.get).not.toHaveBeenCalled()
  })

  it('batched variant and equivalent node props produce exactly one dirty confirmation', async () => {
    const w = await loaded(), decision = deferred(); markDirty(w)
    confirm.mockReturnValue(decision.promise)
    await w.setProps({ standard: 'listed', currentEntity: { nodeKey: 'G:consol', code: 'G' } })
    expect(confirm).toHaveBeenCalledTimes(1)
    decision.resolve('confirm'); await flushPromises()
    expect(exposed(w).loadedNoteContext.variant).toBe('listed')
    expect(api.put).not.toHaveBeenCalled()
  })

  it.each(['accept', 'cancel'])('concurrent chapter changes share one %s decision and only latest can commit', async (outcome) => {
    const w = await loaded(), decision = deferred(); markDirty(w)
    const original = exposed(w).selectedNoteSection
    confirm.mockReturnValue(decision.promise)
    const first = exposed(w).onNoteNodeClick({ section_id: '五-5-3' })
    const latest = exposed(w).onNoteNodeClick({ section_id: '五-5-4' })
    expect(confirm).toHaveBeenCalledTimes(1)
    if (outcome === 'accept') decision.resolve('confirm')
    else decision.reject('cancel')
    expect((await first).status).toBe('stale')
    await latest
    if (outcome === 'accept') expect(exposed(w).loadedNoteContext.sectionId).toBe('五-5-4')
    else {
      expect(exposed(w).selectedNoteSection).toBe(original)
      expect(exposed(w).noteDirty).toBe(true)
    }
    expect(api.put).not.toHaveBeenCalled()
  })
})
