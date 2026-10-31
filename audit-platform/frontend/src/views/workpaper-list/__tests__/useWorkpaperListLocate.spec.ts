/**
 * useWorkpaperListLocate：列表页按编码定位底稿（spec wp-deeplink-locate-residual-closure 需求 2.1）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, nextTick, ref } from 'vue'
import {
  nearestListedParent,
  useWorkpaperListLocate,
  useWorkpaperListLocateInView,
  wpFilteredOutMessage,
  wpNotGeneratedMessage,
  wpNotInProjectMessage,
  wpParentFallbackMessage,
  type WpListLocateRow,
  type WpListLocateTarget,
} from '../useWorkpaperListLocate'
import { GT_LOCATE_HIGHLIGHT_CLASS } from '@/composables/useCellLocate'

vi.mock('element-plus', () => ({ ElMessage: { info: vi.fn(), warning: vi.fn() } }))

const rowsOf = (codes: string[]): WpListLocateRow[] => codes.map((c) => ({ id: `id-${c}`, wp_code: c }))

function world(codes: string[], opts: { pageSize?: number; stale?: boolean; index?: string[]; generated?: string[] } = {}) {
  const target = ref<WpListLocateTarget | null>(null)
  const loaded = ref(false)
  const loading = ref(false)
  const rows = ref(rowsOf(codes))
  const cycle = ref('')
  const cycleRows = computed(() => (cycle.value ? rows.value.filter((r) => r.wp_code[0] === cycle.value) : rows.value))
  const page = ref(1)
  const pageSize = ref(opts.pageSize ?? 50)
  const el = document.createElement('div')
  el.innerHTML = '<div class="el-table__body-wrapper"><table><tbody></tbody></table></div>'
  document.body.appendChild(el)
  const renderPage = () => {
    const tbody = el.querySelector('tbody')!
    tbody.innerHTML = ''
    const start = (page.value - 1) * pageSize.value
    for (const r of cycleRows.value.slice(start, start + pageSize.value)) {
      const tr = document.createElement('tr')
      tr.className = 'el-table__row'
      tr.dataset.id = r.id
      tbody.appendChild(tr)
    }
  }
  const table = ref({ setCurrentRow: vi.fn(() => renderPage()), $el: el })
  const notify = { info: vi.fn(), warning: vi.fn() }
  const scope = effectScope()
  const api = scope.run(() => useWorkpaperListLocate({
    target, loaded, loading, rows, cycleRows, page, pageSize, table,
    generatedCodes: () => opts.generated ?? codes,
    indexCodes: () => opts.index ?? codes,
    staleFilterOn: () => !!opts.stale,
    selectCycle: (c) => { cycle.value = c },
    notify,
  }))!
  return { target, loaded, loading, rows, cycle, page, table, el, notify, scope, api }
}

afterEach(() => { document.body.innerHTML = '' })

const flush = async () => { for (let i = 0; i < 4; i++) await nextTick() }

describe('useWorkpaperListLocate', () => {
  it('精确命中：选中所在循环、翻到所在页、设当前行并高亮；只执行一次', async () => {
    const codes = [...Array.from({ length: 60 }, (_, i) => `D${i + 1}`), 'E1']
    const w = world(codes, { pageSize: 50 })
    w.target.value = { code: 'd55', seq: 1 }
    await flush()
    expect(w.table.value.setCurrentRow).not.toHaveBeenCalled() // 列表还没取到
    w.loaded.value = true
    await flush()
    expect(w.cycle.value).toBe('D')
    expect(w.page.value).toBe(2)
    expect(w.table.value.setCurrentRow).toHaveBeenCalledWith({ id: 'id-D55', wp_code: 'D55' })
    const tr = w.el.querySelector('tr[data-id="id-D55"]')!
    expect(tr.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(w.notify.info).not.toHaveBeenCalled()
    // 列表刷新（行数变化）不再跳回
    w.page.value = 1
    w.rows.value = rowsOf([...codes, 'F1'])
    await flush()
    expect(w.page.value).toBe(1)
    expect(w.table.value.setCurrentRow).toHaveBeenCalledTimes(1)
    w.scope.stop()
  })

  it('加载中不执行，加载完再执行', async () => {
    const w = world(['A1', 'B1'])
    w.loaded.value = true
    w.loading.value = true
    w.target.value = { code: 'B1', seq: 1 }
    await flush()
    expect(w.table.value.setCurrentRow).not.toHaveBeenCalled()
    w.loading.value = false
    await flush()
    expect(w.table.value.setCurrentRow).toHaveBeenCalledTimes(1)
    w.scope.stop()
  })

  it('没有该编码：回落最近的上级底稿并提示', async () => {
    const w = world(['D2', 'D2-1', 'E1'])
    w.loaded.value = true
    w.target.value = { code: 'D2-1-3', seq: 1 }
    await flush()
    expect(w.table.value.setCurrentRow).toHaveBeenCalledWith({ id: 'id-D2-1', wp_code: 'D2-1' })
    expect(w.notify.info).toHaveBeenCalledWith(wpParentFallbackMessage('D2-1-3', 'D2-1'))
    expect(nearestListedParent('D2-9', new Set(['D2']))).toBe('D2')
    expect(nearestListedParent('D2', new Set(['D']))).toBe('')
    w.scope.stop()
  })

  it('找不到时按原因提示：被筛掉（待重算 / 其他）、尚未生成、本项目没有', async () => {
    const cases: Array<[Parameters<typeof world>[1], string]> = [
      [{ generated: ['E1', 'Z9'], stale: true }, wpFilteredOutMessage('Z9', true)],
      [{ generated: ['E1', 'Z9'] }, wpFilteredOutMessage('Z9', false)],
      [{ generated: ['E1'], index: ['E1', 'Z9'] }, wpNotGeneratedMessage('Z9')],
      [{ generated: ['E1'], index: ['E1'] }, wpNotInProjectMessage('Z9')],
    ]
    for (const [opts, message] of cases) {
      const w = world(['E1'], opts)
      w.loaded.value = true
      w.target.value = { code: 'Z9', seq: 1 }
      await flush()
      expect(w.notify.warning).toHaveBeenCalledWith(message)
      expect(w.table.value.setCurrentRow).not.toHaveBeenCalled()
      w.scope.stop()
      document.body.innerHTML = ''
    }
  })

  it('列表视图没显示时等着，切到列表再执行', async () => {
    const shown = ref(false)
    const target = ref<WpListLocateTarget | null>({ code: 'B1', seq: 1 })
    const rows = ref(rowsOf(['A1', 'B1']))
    const table = ref({ setCurrentRow: vi.fn(), $el: null })
    const scope = effectScope()
    scope.run(() => useWorkpaperListLocate({
      target, loaded: ref(true), loading: ref(false), rows, cycleRows: rows, page: ref(1), pageSize: ref(50), table,
      generatedCodes: () => [], indexCodes: () => [], staleFilterOn: () => false, active: () => shown.value,
      selectCycle: () => {}, notify: { info: vi.fn(), warning: vi.fn() },
    }))
    await flush()
    expect(table.value.setCurrentRow).not.toHaveBeenCalled()
    shown.value = true
    await flush()
    expect(table.value.setCurrentRow).toHaveBeenCalledWith({ id: 'id-B1', wp_code: 'B1' })
    scope.stop()
  })

  it('上下文版（工作台 SFC 用）：只在列表视图执行；已生成编码按 codeOf 取自上下文；表格引用由它建', async () => {
    const ctx = {
      locateTarget: ref<WpListLocateTarget | null>({ code: 'Z9', seq: 1 }),
      listLoaded: ref(true), loading: ref(false), filterStale: ref(true), viewMode: ref('workbench'),
      wpList: ref([{ idx: 'z' }, { idx: 'b' }]), wpIndex: ref([{ wp_code: 'Z9' }, { wp_code: 'B1' }]),
    }
    const rows = ref(rowsOf(['B1']))
    const notify = { info: vi.fn(), warning: vi.fn() }
    const scope = effectScope()
    const api = scope.run(() => useWorkpaperListLocateInView(ctx, (w) => (w.idx === 'z' ? 'Z9' : 'B1'), {
      rows, cycleRows: rows, page: ref(1), pageSize: ref(50), selectCycle: () => {}, notify,
    }))!
    const setCurrentRow = vi.fn()
    api.table.value = { setCurrentRow, $el: null }
    await flush()
    expect(notify.warning).not.toHaveBeenCalled() // 工作台视图：等着
    ctx.viewMode.value = 'list'
    await flush()
    expect(notify.warning).toHaveBeenCalledWith(wpFilteredOutMessage('Z9', true)) // Z9 已生成（codeOf）但被「仅看待重算」筛掉
    ctx.locateTarget.value = { code: 'b1', seq: 2 }
    await flush()
    expect(setCurrentRow).toHaveBeenCalledWith({ id: 'id-B1', wp_code: 'B1' })
    scope.stop()
  })

  it('新的 seq 再执行；视图内 locateCode 也能定位（手册视图点底稿）', async () => {
    const w = world(['A1', 'B1', 'C1'])
    w.loaded.value = true
    w.target.value = { code: 'A1', seq: 1 }
    await flush()
    w.target.value = { code: 'C1', seq: 2 }
    await flush()
    expect(w.table.value.setCurrentRow).toHaveBeenLastCalledWith({ id: 'id-C1', wp_code: 'C1' })
    w.api.locateCode('B1')
    await flush()
    expect(w.table.value.setCurrentRow).toHaveBeenLastCalledWith({ id: 'id-B1', wp_code: 'B1' })
    expect(w.table.value.setCurrentRow).toHaveBeenCalledTimes(3)
    w.scope.stop()
  })
})
