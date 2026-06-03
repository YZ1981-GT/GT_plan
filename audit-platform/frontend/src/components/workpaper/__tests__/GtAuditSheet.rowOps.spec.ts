/**
 * GtAuditSheet.rowOps.spec.ts — 审定表行操作单元测试（Task 17）
 *
 * 验证：
 * 1. +新增行：尾部追加空的可编辑自定义行（isCustom=true），id 唯一，参与保存载荷
 * 2. 多选 + 批量删除：onSelectionChange 同步选中 → batchDelete 二次确认后按 id 删除 → 清空勾选
 * 3. 合计行自动汇总：isComputed 行的 审定数/期初未审/本期未审/账项调整/重分类 = 明细行求和
 * 4. 多选可选性：分节/合计行不可选（isRowSelectable=false），仅可编辑行可选
 * 5. readonly：新增/删除按钮禁用，addRow/batchDelete 强制调用不生效
 *
 * 行操作通过 defineExpose 的方法直接调用（el-table selection-change 在 stub 下不冒泡），
 * 与既有 spec 测试 defineExpose 方法的模式一致。
 *
 * Validates: Requirements 6.1, 6.2, 6.4
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtAuditSheet, { type AuditSheetHtmlData } from '../GtAuditSheet.vue'

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
    props: ['data', 'border', 'size', 'headerCellStyle', 'rowClassName', 'rowKey'],
    methods: {
      clearSelection() {
        /* stub no-op */
      },
    },
  },
  'el-table-column': {
    template:
      '<div class="el-table-column" :data-label="label"><template v-if="$slots.default"><div class="gas-cell" v-for="(r, i) in rows" :key="i"><slot :row="r" :$index="i" /></div></template></div>',
    props: ['label', 'width', 'minWidth', 'align', 'fixed', 'type', 'selectable'],
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

/** 含分节 / 两条明细 / 合计行的 fixture（合计行汇总明细行） */
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
        isSection: false,
        isComputed: false,
        account_code: '1121',
        adj_amount: 5000,
        reclass_amount: 1000,
        reason: '确认坏账',
      },
      {
        id: 'row-3',
        item: '坏账准备',
        indent: 1,
        isSection: false,
        isComputed: false,
        account_code: '1231',
        adj_amount: -500,
        reclass_amount: null,
        reason: '计提',
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

describe('GtAuditSheet — 新增行（Task 17 / Req 6.1）', () => {
  it('点击 ➕ 新增行在尾部追加空的可编辑自定义行', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const before = vm.tableData.length
    const addBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('新增行'))
    expect(addBtn).toBeDefined()
    await addBtn!.trigger('click')
    await nextTick()
    expect(vm.tableData.length).toBe(before + 1)
    const added = vm.tableData[vm.tableData.length - 1]
    expect(added.isCustom).toBe(true)
    expect(added.isSection).toBe(false)
    expect(added.isComputed).toBe(false)
    expect(added.item).toBe('')
    // 自定义行可编辑
    expect(vm.isEditableRow(added)).toBe(true)
    // 无 TB 取数
    expect(added.account_code).toBeNull()
    expect(added.opening_unadjusted).toBeNull()
  })

  it('多次新增行 id 唯一', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    vm.addRow()
    vm.addRow()
    vm.addRow()
    const ids = vm.tableData.map((r: any) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
    // nextRowId 直接调用也不撞
    const a = vm.nextRowId()
    const b = vm.nextRowId()
    expect(a).not.toBe(b)
  })

  it('新增行参与保存载荷（持久化完整结构 + 用户编辑列）', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    vm.addRow()
    const added = vm.tableData[vm.tableData.length - 1]
    added.item = '自定义其他应收款'
    added.adj_amount = 8888
    added.reason = '补充行'
    const payload = vm.buildSavePayload() as AuditSheetHtmlData
    const saved = payload.audit_rows!.find((r) => r.id === added.id)!
    expect(saved).toBeDefined()
    expect(saved.item).toBe('自定义其他应收款')
    expect(saved.adj_amount).toBe(8888)
    expect(saved.reason).toBe('补充行')
    expect((saved as any).isCustom).toBe(true)
    // TB 实时值仍被剥离
    expect('opening_unadjusted' in saved).toBe(false)
    expect('current_unadjusted' in saved).toBe(false)
  })

  it('readonly 模式禁用新增行按钮，addRow 强制调用不生效', () => {
    const wrapper = mountSheet(buildHtmlData(), true)
    const vm = wrapper.vm as any
    const addBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('新增行'))
    expect((addBtn!.element as HTMLButtonElement).disabled).toBe(true)
    const before = vm.tableData.length
    vm.addRow()
    expect(vm.tableData.length).toBe(before)
  })
})

describe('GtAuditSheet — 多选 + 批量删除（Task 17 / Req 6.2）', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('isRowSelectable：分节/合计行不可选，可编辑行可选', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.isRowSelectable(vm.tableData[0])).toBe(false) // 分节
    expect(vm.isRowSelectable(vm.tableData[1])).toBe(true) // 明细
    expect(vm.isRowSelectable(vm.tableData[2])).toBe(true) // 明细
    expect(vm.isRowSelectable(vm.tableData[3])).toBe(false) // 合计
  })

  it('onSelectionChange 同步选中行；批量删除按钮随选中数启用并显示计数', async () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const delBtn = () => wrapper.findAll('.el-button').find((b) => b.text().includes('批量删除'))
    // 无选中：禁用
    expect((delBtn()!.element as HTMLButtonElement).disabled).toBe(true)
    vm.onSelectionChange([vm.tableData[1], vm.tableData[2]])
    await nextTick()
    expect(vm.selectedRows.length).toBe(2)
    expect((delBtn()!.element as HTMLButtonElement).disabled).toBe(false)
    expect(delBtn()!.text()).toContain('2')
  })

  it('batchDelete 二次确认后按 id 删除选中行并清空勾选', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValueOnce({ action: 'confirm' } as any)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => ({}) as any)
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    vm.onSelectionChange([vm.tableData[1]]) // 删 row-2
    await nextTick()
    await vm.batchDelete()
    await nextTick()
    const ids = vm.tableData.map((r: any) => r.id)
    expect(ids).not.toContain('row-2')
    expect(ids).toContain('row-3')
    expect(vm.selectedRows.length).toBe(0)
  })

  it('batchDelete 用户取消时不删除', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValueOnce('cancel')
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const before = vm.tableData.length
    vm.onSelectionChange([vm.tableData[1]])
    await nextTick()
    await vm.batchDelete()
    await nextTick()
    expect(vm.tableData.length).toBe(before)
  })

  it('无选中时 batchDelete 不弹确认、不删除', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm')
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const before = vm.tableData.length
    await vm.batchDelete()
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(vm.tableData.length).toBe(before)
  })

  it('readonly 模式禁用批量删除按钮，batchDelete 强制调用不生效', async () => {
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm')
    const wrapper = mountSheet(buildHtmlData(), true)
    const vm = wrapper.vm as any
    vm.selectedRows = [vm.tableData[1]]
    await nextTick()
    const delBtn = wrapper.findAll('.el-button').find((b) => b.text().includes('批量删除'))
    expect((delBtn!.element as HTMLButtonElement).disabled).toBe(true)
    const before = vm.tableData.length
    await vm.batchDelete()
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(vm.tableData.length).toBe(before)
  })

  it('删除后保存载荷不含被删行', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValueOnce({ action: 'confirm' } as any)
    vi.spyOn(ElMessage, 'success').mockImplementation(() => ({}) as any)
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    vm.onSelectionChange([vm.tableData[1]])
    await nextTick()
    await vm.batchDelete()
    await nextTick()
    const payload = vm.buildSavePayload() as AuditSheetHtmlData
    expect(payload.audit_rows!.find((r) => r.id === 'row-2')).toBeUndefined()
  })
})

describe('GtAuditSheet — 合计行自动汇总（Task 17 / Req 6.4）', () => {
  it('合计行审定数 = 明细行审定数之和', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const total = vm.tableData[3]
    expect(total.isComputed).toBe(true)
    // row-2: 120000 + 5000 + 1000 = 126000；row-3: -3000 + (-500) + 0 = -3500
    expect(vm.auditedAmount(vm.tableData[1])).toBe(126000)
    expect(vm.auditedAmount(vm.tableData[2])).toBe(-3500)
    // 合计 = 126000 + (-3500) = 122500
    expect(vm.auditedAmount(total)).toBe(122500)
  })

  it('合计行各列展示值 = 明细行对应列之和', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const total = vm.tableData[3]
    // 期初未审：100000 + (-2000) = 98000
    expect(vm.displayOpeningUnadjusted(total)).toBe(98000)
    // 本期未审：120000 + (-3000) = 117000
    expect(vm.displayCurrentUnadjusted(total)).toBe(117000)
    // 账项调整：5000 + (-500) = 4500
    expect(vm.displayAdj(total)).toBe(4500)
    // 重分类：1000 + 0 = 1000
    expect(vm.displayReclass(total)).toBe(1000)
    // 期初审定（= 期初未审汇总）：98000
    expect(vm.openingAudited(total)).toBe(98000)
    // 变动额 = 审定数 - 期初审定 = 122500 - 98000 = 24500
    expect(vm.changeAmount(total)).toBe(24500)
  })

  it('明细行展示值取本行原值（非汇总）', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    expect(vm.displayAdj(vm.tableData[1])).toBe(5000)
    expect(vm.displayCurrentUnadjusted(vm.tableData[1])).toBe(120000)
  })

  it('合计行汇总随明细编辑联动重算', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const total = vm.tableData[3]
    expect(vm.auditedAmount(total)).toBe(122500)
    // 编辑明细行 row-2 的调整
    vm.tableData[1].adj_amount = 10000 // 原 5000 → +5000
    expect(vm.auditedAmount(vm.tableData[1])).toBe(131000)
    // 合计随之 +5000 → 127500
    expect(vm.auditedAmount(total)).toBe(127500)
    expect(vm.displayAdj(total)).toBe(9500) // 10000 + (-500)
  })

  it('新增行计入合计汇总', () => {
    const wrapper = mountSheet(buildHtmlData())
    const vm = wrapper.vm as any
    const total = vm.tableData.find((r: any) => r.isComputed)
    const before = vm.auditedAmount(total)
    vm.addRow()
    const added = vm.tableData[vm.tableData.length - 1]
    // 注意：新增行追加在合计行之后，但 detailRows 按 isComputed/isSection 过滤，与位置无关
    added.current_unadjusted = 50000
    added.adj_amount = 2000
    expect(vm.auditedAmount(total)).toBe(before + 52000)
  })
})
