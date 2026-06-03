/**
 * GtAuditSheet.importExport.spec.ts — 审定表导入导出单元测试（Task 16）
 *
 * 验证：
 * 1. 导出模板：调用 useExcelIO.exportTemplate，传入正确的列定义（行项目名 + 列标题）、
 *    sheetName=审定表、当前 tableData 作为现有数据行、文件名含 sheetName。
 * 2. 导入 Excel：按项目名匹配 → 可编辑行计入 matched，分节/合计/未知行计入 skipped，
 *    弹出预览弹窗（matched/skipped 统计 + 前 N 行预览）。
 * 3. 确认导入：仅写回可编辑列（adj_amount/reclass_amount/reason），逐行 emit field-change，
 *    不触碰 TB 只读列与 computed 行；导入后清空预览状态。
 * 4. parseNum：千分位/空/非法值归一。
 * 5. readonly：导入入口禁用，confirmImport/onFileSelected 不生效。
 *
 * useExcelIO 被 mock（隔离 xlsx 动态 import），onFileSelected 直接以可设值的解析结果回调。
 *
 * Validates: Requirements 5.1, 5.2, 5.3
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtAuditSheet, { type AuditSheetHtmlData } from '../GtAuditSheet.vue'

// ─── mock useExcelIO（隔离 xlsx 动态 import） ───
const { mockExportTemplate, mockOnFileSelected, parseResultRef } = vi.hoisted(() => {
  return {
    mockExportTemplate: vi.fn(async () => {}),
    // onFileSelected(event, callback, options) → 用可设值的解析结果调用回调
    parseResultRef: { value: { rows: [] as any[], headers: [] as string[] } },
    mockOnFileSelected: vi.fn(async (_e: Event, cb: (r: any) => void) => {
      cb(parseResultRef.value)
    }),
  }
})

vi.mock('@/composables/useExcelIO', () => ({
  useExcelIO: () => ({
    exportTemplate: mockExportTemplate,
    exportData: vi.fn(async () => {}),
    parseFile: vi.fn(),
    onFileSelected: mockOnFileSelected,
  }),
}))

const globalStubs = {
  'el-empty': { template: '<div class="el-empty"><slot /></div>', props: ['description', 'imageSize'] },
  'el-alert': { template: '<div class="el-alert"><slot name="title" /></div>', props: ['type', 'closable'] },
  'el-dialog': {
    template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'appendToBody'],
  },
  'el-button': {
    template:
      '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled'],
    emits: ['click'],
  },
  'el-table': {
    template: '<div class="el-table"><slot /></div>',
    props: ['data', 'border', 'size', 'headerCellStyle', 'rowClassName', 'maxHeight'],
  },
  'el-table-column': {
    template:
      '<div class="el-table-column" :data-label="label"><template v-if="$slots.default"><div class="gas-cell" v-for="(r, i) in rows" :key="i"><slot :row="r" :$index="i" /></div></template></div>',
    props: ['label', 'width', 'minWidth', 'align', 'fixed', 'prop'],
    computed: {
      rows(): Record<string, any>[] {
        const self = this as any
        const data = self.$parent?.$attrs?.data || self.$parent?.data || []
        return Array.isArray(data) ? data : []
      },
    },
  },
  'el-input-number': {
    template:
      '<input class="el-input-number" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', Number($event.target.value)); $emit(\'change\', Number($event.target.value))" />',
    props: ['modelValue', 'precision', 'controls', 'disabled', 'placeholder', 'size'],
    emits: ['update:modelValue', 'change'],
  },
  'el-input': {
    template:
      '<input class="el-input" :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)" />',
    props: ['modelValue', 'disabled', 'placeholder', 'size'],
    emits: ['update:modelValue', 'change'],
  },
}

function buildHtmlData(): AuditSheetHtmlData {
  return {
    audit_rows: [
      {
        id: 'row-1',
        item: '一、应收票据',
        indent: 0,
        bold: true,
        isSection: true,
        isComputed: false,
        account_code: null,
        adj_amount: null,
        reclass_amount: null,
        reason: '',
      },
      {
        id: 'row-2',
        item: '原值',
        indent: 1,
        bold: false,
        isSection: false,
        isComputed: false,
        account_code: '1121',
        adj_amount: null,
        reclass_amount: null,
        reason: '',
      },
      {
        id: 'row-3',
        item: '坏账准备',
        indent: 1,
        bold: false,
        isSection: false,
        isComputed: false,
        account_code: '1231',
        adj_amount: null,
        reclass_amount: null,
        reason: '',
      },
      {
        id: 'row-4',
        item: '合计',
        indent: 0,
        bold: true,
        isSection: false,
        isComputed: true,
        account_code: null,
        adj_amount: null,
        reclass_amount: null,
        reason: '',
      },
    ],
    tb_values: {
      'row-2': { opening_unadjusted: 100000, current_unadjusted: 120000, sys_aje: 0, sys_rje: 0 },
      'row-3': { opening_unadjusted: -2000, current_unadjusted: -3000, sys_aje: 0, sys_rje: 0 },
    },
  }
}

function mountSheet(htmlData: AuditSheetHtmlData, readonly = false) {
  return mount(GtAuditSheet, {
    props: { wpId: 'wp-001', sheetName: '审定表D1-1', schema: {}, htmlData, readonly },
    global: { stubs: globalStubs },
  })
}

beforeEach(() => {
  mockExportTemplate.mockClear()
  mockOnFileSelected.mockClear()
  parseResultRef.value = { rows: [], headers: [] }
})

describe('GtAuditSheet — 导出模板（Task 16）', () => {
  it('点击导出模板按钮调用 useExcelIO.exportTemplate', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const exportBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('导出模板'))
    expect(exportBtn).toBeDefined()
    await exportBtn!.trigger('click')
    expect(mockExportTemplate).toHaveBeenCalledTimes(1)
  })

  it('导出选项含行项目名 + 列标题、sheetName=审定表、文件名含 sheetName', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    await vm.onExportTemplate()
    const opts = mockExportTemplate.mock.calls[0][0]
    // sheetName 与导入解析一致
    expect(opts.sheetName).toBe('审定表')
    // 文件名含当前 sheetName
    expect(opts.fileName).toContain('审定表D1-1')
    // 列定义含项目列 + 三个可编辑列标题
    const headers = opts.columns.map((c: any) => c.header)
    expect(headers).toContain('项目')
    expect(headers).toContain('账项调整')
    expect(headers).toContain('重分类调整')
    expect(headers).toContain('原因分析')
    // 现有数据行数 = tableData 行数（行项目名随数据导出）
    expect(opts.existingData.length).toBe(vm.tableData.length)
    // 第 2 列为项目名（导入按此匹配）
    expect(opts.existingData[1][1]).toBe('原值')
  })

  it('readonly 模式下导出模板仍可用（只读操作）', () => {
    const wrapper = mountSheet(buildHtmlData(), true)
    const exportBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('导出模板'))
    expect((exportBtn!.element as HTMLButtonElement).disabled).toBe(false)
  })
})

describe('GtAuditSheet — 导入 Excel 匹配/跳过（Task 16）', () => {
  const HEADERS = ['序号', '项目', '期初未审数', '期初审定数', '本期未审数', '账项调整', '重分类调整', '审定数', '原因分析']

  it('按行名匹配：可编辑行计入 matched，分节/合计/未知行计入 skipped', async () => {
    parseResultRef.value = {
      headers: HEADERS,
      rows: [
        { 序号: '1', 项目: '一、应收票据', 账项调整: 999, 重分类调整: null, 原因分析: '分节不应导入' }, // 分节 → skip
        { 序号: '2', 项目: '原值', 账项调整: 5000, 重分类调整: 1000, 原因分析: '确认坏账' }, // 可编辑 → match
        { 序号: '3', 项目: '坏账准备', 账项调整: -500, 重分类调整: null, 原因分析: '计提' }, // 可编辑 → match
        { 序号: '4', 项目: '合计', 账项调整: 100, 重分类调整: null, 原因分析: '合计不应导入' }, // 合计 → skip
        { 序号: '5', 项目: '不存在的科目', 账项调整: 1, 重分类调整: 1, 原因分析: 'x' }, // 未知 → skip
        { 序号: '', 项目: '', 账项调整: '', 重分类调整: '', 原因分析: '' }, // 空行 → skip
      ],
    }
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    await vm.onFileSelected({ target: { files: [{}] } } as any)
    await nextTick()
    expect(vm.importStats.matched).toBe(2)
    expect(vm.importStats.skipped).toBe(4)
    expect(vm.importVisible).toBe(true)
    // 预览行含匹配的两行
    expect(vm.importPreviewRows.length).toBe(2)
    const items = vm.importPreviewRows.map((r: any) => r.item)
    expect(items).toContain('原值')
    expect(items).toContain('坏账准备')
  })

  it('点击导入按钮触发文件选择器（onFileSelected 经由 input change）', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const importBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('导入'))
    expect(importBtn).toBeDefined()
    // 触发 input change 直接调用组件 onFileSelected
    const input = wrapper.find('input[type="file"]')
    expect(input.exists()).toBe(true)
    await input.trigger('change')
    expect(mockOnFileSelected).toHaveBeenCalled()
  })

  it('readonly 模式禁用导入按钮，triggerImport / onFileSelected 不生效', async () => {
    const wrapper = mountSheet(buildHtmlData(), true)
    const vm = wrapper.vm as any
    const importBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('导入'))
    expect((importBtn!.element as HTMLButtonElement).disabled).toBe(true)
    vm.triggerImport()
    await vm.onFileSelected({ target: { files: [{}] } } as any)
    expect(mockOnFileSelected).not.toHaveBeenCalled()
    expect(vm.importVisible).toBe(false)
  })
})

describe('GtAuditSheet — 确认导入写回（Task 16）', () => {
  const HEADERS = ['序号', '项目', '期初未审数', '期初审定数', '本期未审数', '账项调整', '重分类调整', '审定数', '原因分析']

  async function importThenSetup() {
    parseResultRef.value = {
      headers: HEADERS,
      rows: [
        { 项目: '原值', 账项调整: 5000, 重分类调整: 1000, 原因分析: '确认坏账' },
        { 项目: '坏账准备', 账项调整: -500, 重分类调整: '', 原因分析: '计提' },
      ],
    }
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    await vm.onFileSelected({ target: { files: [{}] } } as any)
    await nextTick()
    return { wrapper, vm }
  }

  it('确认导入仅写回可编辑列（adj/reclass/reason），并清空预览状态', async () => {
    const { wrapper, vm } = await importThenSetup()
    vm.confirmImport()
    await nextTick()
    const row2 = vm.tableData.find((r: any) => r.id === 'row-2')
    expect(row2.adj_amount).toBe(5000)
    expect(row2.reclass_amount).toBe(1000)
    expect(row2.reason).toBe('确认坏账')
    const row3 = vm.tableData.find((r: any) => r.id === 'row-3')
    expect(row3.adj_amount).toBe(-500)
    expect(row3.reclass_amount).toBeNull() // 空字符串 → null
    expect(row3.reason).toBe('计提')
    // 预览状态清空
    expect(vm.importVisible).toBe(false)
    expect(vm.importStats).toBeNull()
    expect(vm.importPreviewRows.length).toBe(0)
    // emit field-change（每行 3 次）
    expect(wrapper.emitted('field-change')!.length).toBe(6)
  })

  it('确认导入不触碰 TB 只读列与 computed 行', async () => {
    const { vm } = await importThenSetup()
    vm.confirmImport()
    await nextTick()
    const row2 = vm.tableData.find((r: any) => r.id === 'row-2')
    // TB 只读列保持原值
    expect(row2.current_unadjusted).toBe(120000)
    expect(row2.opening_unadjusted).toBe(100000)
    // 合计行（isComputed）不被导入写入
    const total = vm.tableData.find((r: any) => r.id === 'row-4')
    expect(total.adj_amount).toBeNull()
    expect(total.reason).toBe('')
  })

  it('确认导入后审定数随写回值重算', async () => {
    const { vm } = await importThenSetup()
    vm.confirmImport()
    await nextTick()
    const row2 = vm.tableData.find((r: any) => r.id === 'row-2')
    // 120000 + 5000 + 1000
    expect(vm.auditedAmount(row2)).toBe(126000)
  })

  it('readonly 模式 confirmImport 不写回', async () => {
    parseResultRef.value = {
      headers: HEADERS,
      rows: [{ 项目: '原值', 账项调整: 5000, 重分类调整: 1000, 原因分析: '确认坏账' }],
    }
    const wrapper = mountSheet(buildHtmlData(), true)
    const vm = wrapper.vm as any
    // 直接填充解析 map 模拟已解析（readonly 下 onFileSelected 本就不生效）
    vm.importParsedMap.set('原值', { adj_amount: 5000, reclass_amount: 1000, reason: '确认坏账' })
    vm.confirmImport()
    await nextTick()
    const row2 = vm.tableData.find((r: any) => r.id === 'row-2')
    expect(row2.adj_amount).toBeNull()
  })
})

describe('GtAuditSheet — parseNum（Task 16）', () => {
  it('千分位/空/非法值归一', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.parseNum('1,234.56')).toBeCloseTo(1234.56, 2)
    expect(vm.parseNum(5000)).toBe(5000)
    expect(vm.parseNum('')).toBeNull()
    expect(vm.parseNum(null)).toBeNull()
    expect(vm.parseNum('abc')).toBeNull()
    expect(vm.parseNum(0)).toBe(0)
  })
})
