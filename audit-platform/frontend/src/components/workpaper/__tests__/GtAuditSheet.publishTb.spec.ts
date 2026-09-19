/**
 * GtAuditSheet.publishTb.spec.ts — 审定表"发布到试算表"按钮（P0-项3）
 *
 * spec: .kiro/specs/d4-dual-mode-formula-governance/
 *
 * 验证：
 * 1. 工具栏存在"发布到试算表"按钮（与"保存"分离）。
 * 2. 点击 → 二次确认 → 调 POST /api/workpapers/{wpId}/audit-determination/publish-to-tb，
 *    body 含 sheet_name + html_data（区别于普通保存，普通保存不回写 TB）。
 * 3. 用户取消二次确认 → 不发请求。
 * 4. readonly → 按钮禁用，不发请求。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtAuditSheet, { type AuditSheetHtmlData } from '../GtAuditSheet.vue'

// ─── mock apiProxy（隔离网络） ───
const { mockPost, confirmRef } = vi.hoisted(() => ({
  mockPost: vi.fn(async () => ({ message: '已发布 2 个科目的审定数到试算表', published: true })),
  confirmRef: { resolve: true },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { post: mockPost, get: vi.fn() },
}))

// ─── mock confirmDangerous（二次确认）───
vi.mock('@/utils/confirm', () => ({
  confirmDangerous: vi.fn(async () => {
    if (!confirmRef.resolve) throw new Error('cancelled')
  }),
}))

// 隔离 useExcelIO 的 xlsx 动态 import
vi.mock('@/composables/useExcelIO', () => ({
  useExcelIO: () => ({
    exportTemplate: vi.fn(),
    exportData: vi.fn(),
    parseFile: vi.fn(),
    onFileSelected: vi.fn(),
  }),
}))

const globalStubs = {
  'el-empty': { template: '<div><slot /></div>', props: ['description', 'imageSize'] },
  'el-alert': { template: '<div><slot name="title" /></div>', props: ['type', 'closable'] },
  'el-dialog': {
    template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'appendToBody'],
  },
  'el-button': {
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading'],
    emits: ['click'],
  },
  'el-table': { template: '<div><slot /></div>', props: ['data'] },
  'el-table-column': { template: '<div />', props: ['label'] },
  'el-input-number': { template: '<input />', props: ['modelValue'] },
  'el-input': { template: '<input />', props: ['modelValue'] },
}

function buildHtmlData(): AuditSheetHtmlData {
  return {
    audit_rows: [
      { id: 'r2', item: '原值', account_code: '1121', current_unadjusted: 120000, adj_amount: null, reclass_amount: null, reason: '' },
    ],
    tb_values: { r2: { current_unadjusted: 120000, sys_aje: 0, sys_rje: 0 } },
  } as any
}

function mountSheet(readonly = false) {
  return mount(GtAuditSheet, {
    props: { wpId: 'wp-001', sheetName: '审定表D1-1', schema: {}, htmlData: buildHtmlData(), readonly },
    global: { stubs: globalStubs },
  })
}

beforeEach(() => {
  mockPost.mockClear()
  confirmRef.resolve = true
})

describe('GtAuditSheet — 发布到试算表（P0-项3）', () => {
  it('工具栏存在"发布到试算表"按钮', () => {
    const wrapper = mountSheet()
    const btn = wrapper.findAll('.el-button').find((b) => b.text().includes('发布到试算表'))
    expect(btn).toBeDefined()
  })

  it('确认后调用 publish-to-tb 端点，body 含 sheet_name + html_data', async () => {
    const wrapper = mountSheet()
    await (wrapper.vm as any).onPublishToTb()
    await nextTick()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toContain('/api/workpapers/wp-001/audit-determination/publish-to-tb')
    expect(body.sheet_name).toBe('审定表D1-1')
    expect(body.html_data).toBeTruthy()
    expect(body.html_data.audit_rows.length).toBe(1)
  })

  it('用户取消二次确认 → 不发请求', async () => {
    confirmRef.resolve = false
    const wrapper = mountSheet()
    await (wrapper.vm as any).onPublishToTb()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('readonly → 不发请求（按钮禁用 + 处理函数早退）', async () => {
    const wrapper = mountSheet(true)
    await (wrapper.vm as any).onPublishToTb()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
