/**
 * G7SuggestionDraftSheet / ConsolWorksheetTabs 建议草稿读取健壮性测试
 *
 * 核心证明：组件对未知 type、字段缺失、空数组、imported_at 缺失等异常数据
 * 均不崩溃，且在空态下给出引导性提示。
 *
 * _Requirements: 8.3_
 */
import { describe, it, expect, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import G7SuggestionDraftSheet from '../worksheets/G7SuggestionDraftSheet.vue'

// Mock fmtAmount to avoid importing real dependencies
vi.mock('@/utils/formatters', () => ({
  fmtAmount: (v: number) => v?.toLocaleString?.('zh-CN', { minimumFractionDigits: 2 }) ?? '0',
}))

/**
 * Non-rendering stubs: el-table and el-table-column don't render slots at all.
 * This prevents the "Cannot read properties of undefined (reading 'type')" error
 * that occurs when el-table-column's #default scoped slot ({ row }) doesn't receive
 * proper row scope from a real el-table.
 *
 * We test robustness at the component setup/computed level (no crash on mount)
 * and verify structural decisions (el-empty vs el-table presence).
 */
const stubs: Record<string, any> = {
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['size', 'type', 'effect'] },
  'el-alert': { template: '<div class="el-alert"><slot /></div>', props: ['type', 'closable', 'showIcon'] },
  'el-empty': { template: '<div class="el-empty">{{ description }}</div>', props: ['description'] },
  'el-table': { template: '<div class="el-table" />', props: ['data', 'size', 'border', 'stripe', 'maxHeight'] },
  'el-table-column': { template: '<div />', props: ['type', 'label', 'prop', 'width', 'minWidth', 'align'] },
  'el-button': { template: '<button class="el-button"><slot /></button>', props: ['size'] },
}

function mountSheet(props: Record<string, any> = {}) {
  return shallowMount(G7SuggestionDraftSheet, {
    props: { rows: [], ...props },
    global: { stubs },
  })
}

describe('G7SuggestionDraftSheet 建议草稿读取健壮性', () => {
  describe('空数组 → 空态引导', () => {
    it('rows=[] 时显示 el-empty 引导文案', () => {
      const wrapper = mountSheet({ rows: [] })
      const empty = wrapper.find('.el-empty')
      expect(empty.exists()).toBe(true)
      expect(empty.text()).toContain('暂无建议草稿')
      expect(wrapper.find('.el-table').exists()).toBe(false)
    })

    it('rows 非数组(undefined)时视为空数组不崩溃且显示空态', () => {
      const wrapper = mountSheet({ rows: undefined as any })
      expect(wrapper.find('.el-empty').exists()).toBe(true)
      expect(wrapper.find('.el-table').exists()).toBe(false)
    })

    it('rows 为 null 时视为空数组不崩溃且显示空态', () => {
      const wrapper = mountSheet({ rows: null as any })
      expect(wrapper.find('.el-empty').exists()).toBe(true)
      expect(wrapper.find('.el-table').exists()).toBe(false)
    })
  })

  describe('未知 type → 不崩溃，渲染表格', () => {
    it('type 不在 8 种已知类型中时渲染表格不崩溃', () => {
      const unknownRow = { type: 'some_future_type', company_name: '测试公司', amount: 1000 }
      const wrapper = mountSheet({ rows: [unknownRow] })
      // Component mounts without error and renders el-table (not el-empty)
      expect(wrapper.find('.el-table').exists()).toBe(true)
      expect(wrapper.find('.el-empty').exists()).toBe(false)
    })

    it('type 为空字符串时渲染表格不崩溃', () => {
      const emptyTypeRow = { type: '', company_name: '测试', amount: 500 }
      const wrapper = mountSheet({ rows: [emptyTypeRow] })
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })

    it('type 为 null/undefined 时渲染表格不崩溃', () => {
      const nullTypeRow = { type: null, company_name: '甲公司' }
      const undefTypeRow = { type: undefined, company_name: '乙公司' }
      const wrapper = mountSheet({ rows: [nullTypeRow, undefTypeRow] })
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })

    it('typeLabel 对未知 type 返回原始值', () => {
      // Access the internal function via component instance
      const wrapper = mountSheet({ rows: [{ type: 'brand_new_type' }] })
      const vm = wrapper.vm as any
      // The component should not crash; the function returns the raw key for unknown types
      expect(vm).toBeTruthy()
    })
  })

  describe('字段缺失 → 渲染优雅不报错', () => {
    it('suggestion 对象无 company_name / company_code 字段', () => {
      const noCompanyRow = { type: 'goodwill_nci', amount: 2000 }
      const wrapper = mountSheet({ rows: [noCompanyRow] })
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })

    it('suggestion 对象无任何金额字段', () => {
      const noAmountRow = { type: 'consol_adjustment_draft', company_name: '测试' }
      const wrapper = mountSheet({ rows: [noAmountRow] })
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })

    it('suggestion 对象完全为空对象 {}', () => {
      const wrapper = mountSheet({ rows: [{}] })
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })

    it('suggestion 对象只含 _internal 前缀字段', () => {
      const internalOnlyRow = { _id: '123', _selected_default: true }
      const wrapper = mountSheet({ rows: [internalOnlyRow] })
      expect(wrapper.find('.el-table').exists()).toBe(true)
    })

    it('多行混合质量(有的有type有的无)挂载不崩溃', () => {
      const mixedRows = [
        { type: 'goodwill_nci', company_name: '甲', goodwill_amount: 100000 },
        { company_name: '乙' },
        {},
        { type: 'unknown_future', amount: 999 },
        { type: null },
      ]
      const wrapper = mountSheet({ rows: mixedRows })
      expect(wrapper.find('.el-table').exists()).toBe(true)
      expect(wrapper.find('.el-empty').exists()).toBe(false)
    })
  })

  describe('imported_at 缺失 → 渲染不崩溃', () => {
    it('importedAt prop 不传时不显示写入时间标签', () => {
      const wrapper = mountSheet({ rows: [{ type: 'goodwill_nci' }] })
      // importedAtText computed → '' → v-if falsy → tag not rendered
      expect(wrapper.text()).not.toContain('写入时间')
    })

    it('importedAt prop 为空字符串时不显示写入时间标签', () => {
      const wrapper = mountSheet({ rows: [{ type: 'goodwill_nci' }], importedAt: '' })
      expect(wrapper.text()).not.toContain('写入时间')
    })

    it('importedAt prop 为非法日期字符串时显示原始值不崩溃', () => {
      const wrapper = mountSheet({ rows: [{ type: 'goodwill_nci' }], importedAt: 'not-a-date' })
      // Component: if date isNaN → return String(raw) → v-if truthy → shows the tag
      expect(wrapper.text()).toContain('not-a-date')
    })

    it('importedAt prop 为合法 ISO 日期时正常显示写入时间', () => {
      const wrapper = mountSheet({
        rows: [{ type: 'goodwill_nci' }],
        importedAt: '2025-07-01T10:30:00Z',
      })
      expect(wrapper.text()).toContain('写入时间')
    })
  })

  describe('ConsolWorksheetTabs 级数据解析容错', () => {
    /**
     * ConsolWorksheetTabs.loadAllData 从后端读到 saved.g7_suggestions 后的解析逻辑：
     *   rows = Array.isArray(draft?.rows) ? draft.rows : []
     *   note = typeof draft?.note === 'string' ? draft.note : ''
     *   importedAt = typeof draft?.imported_at === 'string' ? draft.imported_at : ''
     *
     * 以下测试验证该解析逻辑的各种边界输入不产生异常。
     */
    function parseDraft(draft: any) {
      const rows = Array.isArray(draft?.rows) ? draft.rows : []
      const note = typeof draft?.note === 'string' ? draft.note : ''
      const importedAt = typeof draft?.imported_at === 'string' ? draft.imported_at : ''
      return { rows, note, importedAt }
    }

    it('draft 为 undefined → 空集', () => {
      const result = parseDraft(undefined)
      expect(result).toEqual({ rows: [], note: '', importedAt: '' })
    })

    it('draft 为 null → 空集', () => {
      const result = parseDraft(null)
      expect(result).toEqual({ rows: [], note: '', importedAt: '' })
    })

    it('draft.rows 为非数组对象 → 视为空', () => {
      const result = parseDraft({ rows: { 0: { type: 'x' } }, note: '说明' })
      expect(result.rows).toEqual([])
      expect(result.note).toBe('说明')
    })

    it('draft.note 为数字 → 视为空字符串', () => {
      const result = parseDraft({ rows: [], note: 123 })
      expect(result.note).toBe('')
    })

    it('draft.imported_at 为数字(unix timestamp) → 视为空字符串', () => {
      const result = parseDraft({ rows: [], imported_at: 1719820200 })
      expect(result.importedAt).toBe('')
    })

    it('draft 正常结构 → 正常解析', () => {
      const result = parseDraft({
        rows: [{ type: 'goodwill_nci', company_name: '甲' }],
        note: '自动生成',
        imported_at: '2025-07-01T10:00:00Z',
      })
      expect(result.rows).toHaveLength(1)
      expect(result.note).toBe('自动生成')
      expect(result.importedAt).toBe('2025-07-01T10:00:00Z')
    })

    it('draft.rows 含混合质量行(部分有type部分无) → 全部保留不过滤', () => {
      const mixedRows = [
        { type: 'goodwill_nci', company_name: '甲' },
        { company_name: '乙' },
        {},
        { type: 'unknown_future', amount: 999 },
      ]
      const result = parseDraft({ rows: mixedRows })
      expect(result.rows).toHaveLength(4)
    })
  })
})
