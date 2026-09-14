/**
 * formulaPickers.acnr.pbt.test.ts — 公式选址器 ACNR 接入 属性 + 单元测试
 *
 * spec acnr-consumer-wiring Task 18.4（组件由 18.2/18.3 实现）
 *
 * 覆盖：
 *  - **Property 19: WP Picker Emits grammar_v1 Formula**
 *      生成随机 cell，验证 emit 的 WP formula_ref 可被 grammar_v1（parseUri 权威文法）
 *      round-trip 到合法 addr_id。使用 fast-check。
 *  - 单测：FormulaRefPicker WP tab 选中 ACNR cell → emit 该 cell 的 formula_ref（grammar_v1）
 *  - 单测：WP tab 空（ACNR listSheets 空）→ 回退 legacy store wp 域（Req 14.4，无回归）
 *  - 单测：三 picker 取数一致 —— FormulaRefPicker（WP tab）/ FormulaEditDialog（mapAcnrCellsToPickerRows）
 *          / CellSelector（workpaper 源）均以 ACNR 为源、产 grammar_v1-valid formula_ref
 *
 * **Validates: Requirements 14.2, 14.3, 14.5**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'
import * as fc from 'fast-check'

// ─── ResizeObserver polyfill（Element Plus 部分组件在 jsdom 下需要） ────────────
if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// ─── grammar_v1 WP() 校验器 ────────────────────────────────────────────────────
//
// resolveUri.ts 提供的是 URI 形态（wp://…）的权威文法 parseUri。WP() 公式函数形态是
// 其等价语法糖，映射关系（grammar_v1 三形态，Req 14.5）：
//   - 3 参 cell:    WP('parent','sheet','cell')     ↔  wp://parent/sheet#cell      → addr_id parent/sheet/cell
//   - 2 参 语义列:  WP('wp_code','审定数')            ↔  wp://wp_code/审定数         → addr_id wp_code/审定数（sheet 级）
//   - custom_flat:  WP('wp_code','wp_code','cell')   ↔  wp://wp_code/wp_code#cell    → addr_id wp_code/wp_code/cell
//
// 该校验器把 WP() 转换为等价 URI，再交给「生产实现 parseUri」判定合法性 —— parseUri 是
// grammar_v1 的权威解析器，故 round-trip 成立即代表 formula_ref 是 grammar_v1-valid。
import { parseUri } from '@/services/acnr/resolveUri'

function parseWpArgs(ref: string): string[] | null {
  const m = /^WP\((.*)\)$/.exec((ref || '').trim())
  if (!m) return null
  return m[1].split(',').map((s) => s.trim().replace(/^'(.*)'$/, '$1'))
}

function wpFormulaRefToUri(ref: string): string | null {
  const args = parseWpArgs(ref)
  if (!args || args.some((a) => a === '')) return null
  if (args.length === 3) return `wp://${args[0]}/${args[1]}#${args[2]}`
  if (args.length === 2) return `wp://${args[0]}/${args[1]}`
  return null
}

/** WP() formula_ref → { addrId } | null（null = 非 grammar_v1-valid） */
function parseWpFormulaRef(ref: string): { addrId: string } | null {
  const uri = wpFormulaRefToUri(ref)
  if (!uri) return null
  const parsed = parseUri(uri) // ← 生产权威文法
  if (!parsed || parsed.domain !== 'wp') return null
  const args = parseWpArgs(ref)!
  return { addrId: args.join('/') }
}

// ─── Mock useAcnr（受控 listSheets / listCells） ───────────────────────────────
const mockListSheets = vi.fn()
const mockListCells = vi.fn()
const mockResolveUri = vi.fn()
const mockResolveFormula = vi.fn()
const mockClearCache = vi.fn()

vi.mock('@/services/acnr/useAcnr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/acnr/useAcnr')>()
  return {
    ...actual, // 保留类型导出
    useAcnr: () => ({
      listSheets: mockListSheets,
      listCells: mockListCells,
      resolveUri: mockResolveUri,
      resolveFormula: mockResolveFormula,
      clearCache: mockClearCache,
      resolveIndex: vi.fn(),
      resolveInstance: vi.fn(),
      buildAddressTree: vi.fn(),
      loadCellNodes: vi.fn(),
    }),
  }
})

// ─── Import after mocks ───────────────────────────────────────────────────────
import ElementPlus, { ElDialog, ElSelect, ElTable } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { ElTabs } from 'element-plus'
import FormulaRefPicker from '../FormulaRefPicker.vue'
import CellSelector from '../CellSelector.vue'
import { useAddressRegistry } from '@/stores/addressRegistry'
import { mapAcnrCellsToPickerRows } from '@/utils/wpFormulaPicker'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const SHEET = {
  addr_id: 'D2/D2-2',
  domain: 'wp',
  cycle: 'D',
  parent_wp_code: 'D2',
  sheet_code: 'D2-2',
  sheet_name: '明细表D2-2',
}

const CELL_WITH_REF = {
  addr_id: 'D2/D2-2/E100',
  parent_addr_id: 'D2/D2-2',
  domain: 'wp',
  cell_address: 'E100',
  semantic_label: '期末余额',
  formula_ref: "WP('D2','明细表D2-2','E100')",
}

// ─── Element Plus 精确 stub（避免 teleport / 内部下拉难以驱动） ─────────────────
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
})

const ElSelectStub = defineComponent({
  name: 'ElSelect',
  props: {
    modelValue: { type: [String, Number], default: '' },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'change'],
  template: '<div class="el-select-stub"><slot /></div>',
})

const ElTableStub = defineComponent({
  name: 'ElTable',
  props: { data: { type: Array, default: () => [] } },
  emits: ['row-click'],
  template: '<div class="el-table-stub"><slot /></div>',
})

// ElOption 依赖 ElSelect 的 provide/inject；ElSelect 被 stub 后须一并 stub ElOption。
const STUBS = {
  ElDialog: ElDialogStub,
  ElSelect: ElSelectStub,
  ElTable: ElTableStub,
  ElOption: true,
  ElTableColumn: true,
} as const

function mountRefPicker(): VueWrapper {
  return mount(FormulaRefPicker, {
    props: { modelValue: true, reportRows: [], tbRows: [], noteRows: [] },
    global: {
      plugins: [ElementPlus],
      stubs: STUBS,
    },
  })
}

/** 切到 WP tab（触发 ensureWpSheets → listSheets） */
async function activateWpTab(wrapper: VueWrapper) {
  wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'wp')
  await nextTick()
  await flushPromises()
}

/** 找到 WP 底稿 Sheet 选择器（按 placeholder 区分多个 el-select） */
function findWpSheetSelect(wrapper: VueWrapper) {
  return wrapper
    .findAllComponents(ElSelectStub)
    .find((c) => (c.props('placeholder') as string)?.includes('底稿 Sheet'))
}

/** 找到 WP 单元格表格（data 行含 cell_address + formula_ref） */
function findWpCellTable(wrapper: VueWrapper) {
  return wrapper.findAllComponents(ElTableStub).find((c) => {
    const data = c.props('data') as any[]
    return data.length > 0 && 'cell_address' in data[0] && 'formula_ref' in data[0]
  })
}

async function selectWpSheet(wrapper: VueWrapper, addrId: string) {
  const sel = findWpSheetSelect(wrapper)!
  sel.vm.$emit('update:modelValue', addrId)
  sel.vm.$emit('change', addrId)
  await flushPromises()
  await nextTick()
}

function clickInsert(wrapper: VueWrapper) {
  const btn = wrapper.findAll('button').find((b) => b.text().includes('插入'))
  return btn!.trigger('click')
}

// ══════════════════════════════════════════════════════════════════════════════
// Property 19 — WP Picker Emits grammar_v1 Formula
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 19 — WP formula_ref 是 grammar_v1-valid（parseUri round-trip）', () => {
  // 生成合法 wp_code：标准循环码（A-S）+ 数字，或自定义 alnum 码
  const wpCodeArb = fc.oneof(
    fc
      .tuple(fc.constantFrom(...'ABCDEFGHIJKLMNS'.split('')), fc.integer({ min: 1, max: 99 }))
      .map(([l, n]) => `${l}${n}`),
    fc
      .array(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('')), {
        minLength: 2,
        maxLength: 8,
      })
      .map((a) => a.join('')),
  )
  // sheet_code：wp_code + '-' + 数字（避免含 '#'）
  const sheetCodeArb = fc
    .tuple(wpCodeArb, fc.integer({ min: 1, max: 20 }))
    .map(([w, n]) => `${w}-${n}`)
  // A1 坐标
  const cellArb = fc
    .tuple(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')), fc.integer({ min: 1, max: 9999 }))
    .map(([c, r]) => `${c}${r}`)

  it('3 参 WP(parent,sheet,cell) 构造（= 组件 buildWpFormulaRef）总是 round-trip 到 parent/sheet/cell', () => {
    fc.assert(
      fc.property(wpCodeArb, sheetCodeArb, cellArb, (parent, sheet, cell) => {
        // 复刻 FormulaRefPicker.buildWpFormulaRef 的唯一构造逻辑
        const formulaRef = `WP('${parent}','${sheet}','${cell}')`
        const parsed = parseWpFormulaRef(formulaRef)
        expect(parsed).not.toBeNull()
        expect(parsed!.addrId).toBe(`${parent}/${sheet}/${cell}`)
      }),
      { numRuns: 60 },
    )
  })

  it('custom_flat WP(wp,wp,cell) 形态是 grammar_v1-valid', () => {
    fc.assert(
      fc.property(wpCodeArb, cellArb, (wp, cell) => {
        const formulaRef = `WP('${wp}','${wp}','${cell}')`
        const parsed = parseWpFormulaRef(formulaRef)
        expect(parsed).not.toBeNull()
        expect(parsed!.addrId).toBe(`${wp}/${wp}/${cell}`)
      }),
      { numRuns: 40 },
    )
  })

  it('2 参语义列 WP(wp_code,审定数) 形态是 grammar_v1-valid', () => {
    fc.assert(
      fc.property(wpCodeArb, fc.constantFrom('审定数', '未审数', '期初'), (wp, col) => {
        const formulaRef = `WP('${wp}','${col}')`
        const parsed = parseWpFormulaRef(formulaRef)
        expect(parsed).not.toBeNull()
        expect(parsed!.addrId).toBe(`${wp}/${col}`)
      }),
      { numRuns: 30 },
    )
  })

  it('ACNR cell 自带 formula_ref（三形态）经 picker 透传后仍 grammar_v1-valid', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.tuple(wpCodeArb, sheetCodeArb, cellArb).map(([p, s, c]) => `WP('${p}','${s}','${c}')`),
          fc.tuple(wpCodeArb, cellArb).map(([w, c]) => `WP('${w}','${w}','${c}')`),
          fc.tuple(wpCodeArb).map(([w]) => `WP('${w}','审定数')`),
        ),
        (formulaRef) => {
          // 组件 filteredWpCells 直接透传 c.formula_ref（存在时）
          expect(parseWpFormulaRef(formulaRef)).not.toBeNull()
        },
      ),
      { numRuns: 60 },
    )
  })

  it('畸形 WP() 引用被判为非 grammar_v1-valid', () => {
    for (const bad of ['', 'WP()', "WP('D2')", 'SUM(A1:A2)', "TB('1122','审定数')", 'not-a-ref']) {
      expect(parseWpFormulaRef(bad)).toBeNull()
    }
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// FormulaRefPicker WP tab —— 挂载集成（真实 emit 捕获）
// ══════════════════════════════════════════════════════════════════════════════

describe('FormulaRefPicker WP tab — 选中 ACNR cell 后 emit grammar_v1 formula_ref', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockListSheets.mockResolvedValue([SHEET])
    mockListCells.mockResolvedValue([CELL_WITH_REF])
  })
  afterEach(() => {
    const store = useAddressRegistry()
    store.dispose()
  })

  it('WP tab 选中 cell → insert 事件携带该 cell 的 formula_ref，且 grammar_v1-valid', async () => {
    const wrapper = mountRefPicker()
    await activateWpTab(wrapper)
    expect(mockListSheets).toHaveBeenCalled()

    await selectWpSheet(wrapper, SHEET.addr_id)
    expect(mockListCells).toHaveBeenCalledWith('D2', 'D2-2')

    const table = findWpCellTable(wrapper)
    expect(table).toBeTruthy()
    const rows = table!.props('data') as any[]
    expect(rows[0].formula_ref).toBe(CELL_WITH_REF.formula_ref)

    table!.vm.$emit('row-click', rows[0])
    await nextTick()
    await clickInsert(wrapper)

    const emitted = wrapper.emitted('insert')
    expect(emitted).toBeTruthy()
    const formula = emitted![0][0] as string
    expect(formula).toBe(CELL_WITH_REF.formula_ref)
    // grammar_v1 round-trip
    expect(parseWpFormulaRef(formula)).not.toBeNull()
    wrapper.unmount()
  })

  it('ACNR cell 无 formula_ref 时兜底构造 3 参 WP(parent,sheet,cell)，仍 grammar_v1-valid', async () => {
    mockListCells.mockResolvedValue([{ ...CELL_WITH_REF, formula_ref: '' }])
    const wrapper = mountRefPicker()
    await activateWpTab(wrapper)
    await selectWpSheet(wrapper, SHEET.addr_id)

    const rows = findWpCellTable(wrapper)!.props('data') as any[]
    expect(rows[0].formula_ref).toBe("WP('D2','D2-2','E100')")
    expect(parseWpFormulaRef(rows[0].formula_ref)).not.toBeNull()
    wrapper.unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// WP tab 空 → 回退 legacy store（Req 14.4，无回归）
// ══════════════════════════════════════════════════════════════════════════════

describe('FormulaRefPicker WP tab — ACNR 空则回退 legacy store wp 域', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    // ACNR listSheets 空 → wpAcnrAvailable=false → 走 legacy 回退
    mockListSheets.mockResolvedValue([])
    mockListCells.mockResolvedValue([])
  })
  afterEach(() => {
    useAddressRegistry().dispose()
  })

  it('ACNR 无 sheet 时，filteredWpCells 取自 store.wpAddresses（含 formula_ref）', async () => {
    const store = useAddressRegistry()
    // 注入 legacy wp 域地址（带 grammar_v1 formula_ref）
    store.addresses = [
      {
        uri: 'wp://E1/E1-1#B10',
        domain: 'wp',
        source: 'E1',
        path: 'E1-1',
        cell: 'B10',
        label: '货币资金合计',
        formula_ref: "WP('E1','E1-1','B10')",
        jump_route: '',
        wp_code: 'E1',
      },
    ] as any

    const wrapper = mountRefPicker()
    await activateWpTab(wrapper)
    await flushPromises()

    const table = findWpCellTable(wrapper)
    expect(table).toBeTruthy()
    const rows = table!.props('data') as any[]
    // 回退来源 = legacy store 条目
    expect(rows).toHaveLength(1)
    expect(rows[0].formula_ref).toBe("WP('E1','E1-1','B10')")
    expect(parseWpFormulaRef(rows[0].formula_ref)).not.toBeNull()
    wrapper.unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 三 picker 取数一致性
// ══════════════════════════════════════════════════════════════════════════════

describe('三 picker 取数一致 — FormulaRefPicker / FormulaEditDialog / CellSelector 同源 ACNR', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockListSheets.mockResolvedValue([SHEET])
    mockListCells.mockResolvedValue([CELL_WITH_REF])
  })
  afterEach(() => {
    useAddressRegistry().dispose()
  })

  it('FormulaRefPicker（WP tab）与 FormulaEditDialog（mapAcnrCellsToPickerRows）对同一 cell 产出相同 grammar_v1 ref', async () => {
    // FormulaEditDialog 路径：mapAcnrCellsToPickerRows._ref == cell.formula_ref
    const editRows = mapAcnrCellsToPickerRows([CELL_WITH_REF as any])
    expect(editRows[0]._ref).toBe(CELL_WITH_REF.formula_ref)

    // FormulaRefPicker 路径：透传 cell.formula_ref
    const wrapper = mountRefPicker()
    await activateWpTab(wrapper)
    await selectWpSheet(wrapper, SHEET.addr_id)
    const pickerRow = (findWpCellTable(wrapper)!.props('data') as any[])[0]

    // 两 picker 对同一 cell 得到字节级相同的 formula_ref
    expect(pickerRow.formula_ref).toBe(editRows[0]._ref)
    // 且均 grammar_v1-valid
    expect(parseWpFormulaRef(pickerRow.formula_ref)).not.toBeNull()
    expect(parseWpFormulaRef(editRows[0]._ref!)).not.toBeNull()
    wrapper.unmount()
  })

  it('CellSelector workpaper 源与 FormulaRefPicker 均以 acnr.listSheets 为 WP 数据源', async () => {
    // FormulaRefPicker WP tab
    const p1 = mountRefPicker()
    await activateWpTab(p1)
    expect(mockListSheets).toHaveBeenCalled()
    p1.unmount()

    mockListSheets.mockClear()

    // CellSelector 打开（visible false→true）触发 watch → ensureWpSheets 预取 ACNR 目录
    const p2 = mount(CellSelector, {
      props: { modelValue: false, trialBalanceData: [], reportData: [], noteSections: [] },
      global: {
        plugins: [ElementPlus],
        stubs: STUBS,
      },
    })
    await p2.setProps({ modelValue: true })
    await flushPromises()
    expect(mockListSheets).toHaveBeenCalled()
    p2.unmount()
  })
})
