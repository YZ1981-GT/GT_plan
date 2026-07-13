/**
 * WpBulkImportExport.spec.ts — 项目级底稿批量 Tab 导入导出组件测试
 *
 * Spec: .kiro/specs/workpaper-bulk-tab-import-export/
 * Task: 6.5（组件挂载 + 报告状态渲染）
 * Requirements: 5.1, 2.5
 *
 * 覆盖：
 * - WpBulkImportReport：逐 sheet 状态标签渲染（success/partial/failed/missing/
 *   unlisted/blocked_by_status/conflict_rejected）+ 汇总标签 + 错误/告警/原因展示 +
 *   DryRun 与正式导入报告标题区分
 * - WpBulkDialog：三按钮入口挂载 + 选择操作进入配置步骤
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { ImportReport } from '@/composables/useBulkTabImportExport'

// ── 隔离 composable 依赖（http/sse），避免真实网络/鉴权 ──
const exportTemplates = vi.fn().mockResolvedValue(undefined)
const exportData = vi.fn().mockResolvedValue(undefined)
const importData = vi.fn()
vi.mock('@/composables/useBulkTabImportExport', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useBulkTabImportExport')>()
  return {
    ...actual,
    useBulkTabImportExport: () => ({
      loading: { value: false },
      error: { value: null },
      busy: { value: false },
      exportTemplates,
      exportData,
      importData,
      rollback: vi.fn(),
      subscribeProgress: vi.fn(() => () => {}),
      closeProgress: vi.fn(),
    }),
  }
})

import WpBulkImportReport from '../WpBulkImportReport.vue'
import WpBulkDialog from '../WpBulkDialog.vue'

const ELEMENT_STUBS = {
  'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><span>{{ label }}</span><slot /></div>', props: ['label'] },
  'el-checkbox-group': { template: '<div><slot /></div>' },
  'el-checkbox': { template: '<label><slot /></label>' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio': { template: '<label><slot /></label>' },
  'el-switch': true,
  'el-upload': { template: '<div><slot name="trigger" /><slot /><slot name="tip" /></div>' },
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-alert': { template: '<div class="el-alert" :data-title="title"><slot /></div>', props: ['title', 'type'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-table': {
    template: '<table><slot /></table>',
    props: ['data'],
  },
  'el-table-column': {
    // 对每一行渲染默认插槽，模拟 el-table 行作用域
    template: '<div><template v-for="(row, i) in rows" :key="i"><slot :row="row" /></template></div>',
    props: ['prop', 'label'],
    computed: {
      rows(this: any) {
        const parent = this.$parent
        const data = parent?.data ?? parent?.$props?.data ?? []
        return Array.isArray(data) ? data : []
      },
    },
  },
  'el-empty': { template: '<div class="el-empty"><slot /></div>' },
  'el-progress': true,
  Loading: true,
}

function makeReport(overrides: Partial<ImportReport> = {}): ImportReport {
  return {
    import_id: 'imp-1',
    strategy: 'overwrite',
    dry_run: false,
    snapshots: [],
    sheets: [
      { sheet_code: 'D2-2', status: 'success', rows: 42 },
      { sheet_code: 'D2-1', status: 'partial', rows: 10, warnings: ['row_limit_exceeded: 520 > 500'] },
      { sheet_code: 'D2-7', status: 'blocked_by_status', reason: 'review_passed' },
      { sheet_code: 'D2-3', status: 'missing' },
      { sheet_code: 'D2-4', status: 'failed', errors: ['解析失败: 表头不匹配'] },
      { sheet_code: 'D2-5', status: 'conflict_rejected', reason: '目标已有非空数据' },
      { sheet_code: 'D2-6', status: 'unlisted' },
    ],
    summary: {
      success: 1,
      partial: 1,
      failed: 1,
      blocked: 1,
      missing: 1,
      unlisted: 1,
      conflict_rejected: 1,
    },
    ...overrides,
  }
}

describe('WpBulkImportReport — 逐 sheet 报告渲染', () => {
  it('挂载并渲染汇总标签', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport(), dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    expect(wrapper.exists()).toBe(true)
    const text = wrapper.text()
    expect(text).toContain('成功: 1')
    expect(text).toContain('部分: 1')
    expect(text).toContain('失败: 1')
    expect(text).toContain('受阻: 1')
    expect(text).toContain('缺失: 1')
    expect(text).toContain('未登记: 1')
    expect(text).toContain('冲突拒绝: 1')
  })

  it('渲染每种 sheet 状态的中文标签', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport(), dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    const text = wrapper.text()
    // statusLabel 映射
    expect(text).toContain('成功')
    expect(text).toContain('部分成功')
    expect(text).toContain('失败')
    expect(text).toContain('状态受阻')
    expect(text).toContain('文件缺失')
    expect(text).toContain('冲突拒绝')
    expect(text).toContain('未登记')
  })

  it('展示错误信息（errors 优先于 reason/warnings）', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: {
        report: makeReport({
          sheets: [{ sheet_code: 'D2-4', status: 'failed', errors: ['解析失败: 表头不匹配'] }],
        }),
        dryRun: false,
      },
      global: { stubs: ELEMENT_STUBS },
    })
    expect(wrapper.text()).toContain('解析失败: 表头不匹配')
  })

  it('DryRun 报告标题为预检（未写库）', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport({ dry_run: true }), dryRun: true },
      global: { stubs: ELEMENT_STUBS },
    })
    const alert = wrapper.find('.el-alert')
    expect(alert.attributes('data-title')).toContain('预检')
  })

  it('正式导入报告标题为导入报告', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: makeReport(), dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    const alert = wrapper.find('.el-alert')
    expect(alert.attributes('data-title')).toContain('导入报告')
  })

  it('report 为 null 时渲染空状态', () => {
    const wrapper = mount(WpBulkImportReport, {
      props: { report: null, dryRun: false },
      global: { stubs: ELEMENT_STUBS },
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })
})

describe('WpBulkDialog — 三按钮入口', () => {
  beforeEach(() => {
    exportTemplates.mockClear()
    exportData.mockClear()
    importData.mockClear()
  })

  it('挂载并渲染三个操作按钮', () => {
    const wrapper = mount(WpBulkDialog, {
      props: { modelValue: true, projectId: 'proj-1' },
      global: { stubs: ELEMENT_STUBS },
    })
    const text = wrapper.text()
    expect(text).toContain('导出全部模板')
    expect(text).toContain('导入全部数据')
    expect(text).toContain('导出全部数据')
  })

  it('选择"导出全部模板"后进入配置步骤（循环多选）', async () => {
    const wrapper = mount(WpBulkDialog, {
      props: { modelValue: true, projectId: 'proj-1' },
      global: { stubs: ELEMENT_STUBS },
    })
    // 找到"导出全部模板"按钮并点击
    const buttons = wrapper.findAll('button')
    const target = buttons.find((b) => b.text().includes('导出全部模板'))
    expect(target).toBeTruthy()
    await target!.trigger('click')
    expect(wrapper.text()).toContain('选择审计循环')
  })
})
