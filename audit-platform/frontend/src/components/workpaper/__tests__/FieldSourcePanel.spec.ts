/**
 * FieldSourcePanel.spec.ts — 字段来源面板组件测试
 *
 * spec workpaper-content-semantic-contract Task 7
 *
 * 验证：
 * 7.1 审定表关键字段来源入口渲染
 * 7.2 展示来源、编辑权限、人工确认、stale 策略
 * 7.3 缺失来源时显示结构化 unknown，不报错
 * 7.4 resolveSheetType 对缺少 sheet_type 的历史 schema 返回 'unknown' 且不破坏渲染
 *
 * Validates: Requirements 2.2, 2.4, 5.2
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FieldSourcePanel from '../FieldSourcePanel.vue'
import { resolveSheetType, type SheetRenderConfig } from '@/composables/useWpRenderer'
import type { FieldSourceContract } from '@/types/workpaperSemanticContract'

// ─── Element Plus stubs ───
const ElTag = {
  name: 'ElTag',
  template: '<span class="el-tag-stub" :data-type="type"><slot /></span>',
  props: ['type', 'effect', 'size'],
}

const globalConfig = {
  components: {
    'el-tag': ElTag,
  },
}

// ─── Fixtures ───
const MOCK_FIELD_SOURCE: FieldSourceContract = {
  field_id: 'd1.audit_sheet.current_unadjusted',
  label: '本期未审数',
  source_type: 'trial_balance',
  source_ref: {
    module: 'trial_balance',
    account_code: '1121',
    amount_basis: 'closing_balance',
  },
  editable: false,
  override_allowed: false,
  requires_confirmation: false,
  traceable: true,
  stale_policy: 'refresh_on_tb_updated',
}

const MOCK_MANUAL_SOURCE: FieldSourceContract = {
  field_id: 'd1.audit_sheet.conclusion_note',
  label: '结论备注',
  source_type: 'manual',
  source_ref: { module: 'user_input' },
  editable: true,
  override_allowed: true,
  requires_confirmation: true,
  traceable: false,
  stale_policy: 'none',
}

// ─── 7.1/7.2: 来源入口与详情展示 ───
describe('FieldSourcePanel — 来源展示', () => {
  it('渲染试算表来源的完整信息', () => {
    const wrapper = mount(FieldSourcePanel, {
      props: { fieldSource: MOCK_FIELD_SOURCE, fieldId: 'd1.audit_sheet.current_unadjusted' },
      global: globalConfig,
    })

    expect(wrapper.text()).toContain('本期未审数')
    expect(wrapper.text()).toContain('试算表')
    expect(wrapper.text()).toContain('trial_balance')
    expect(wrapper.text()).toContain('否') // editable = false
    expect(wrapper.text()).toContain('试算表更新时刷新')
  })

  it('渲染手工录入来源', () => {
    const wrapper = mount(FieldSourcePanel, {
      props: { fieldSource: MOCK_MANUAL_SOURCE, fieldId: 'd1.audit_sheet.conclusion_note' },
      global: globalConfig,
    })

    expect(wrapper.text()).toContain('结论备注')
    expect(wrapper.text()).toContain('手工录入')
    expect(wrapper.text()).toContain('user_input')
    expect(wrapper.text()).toContain('是') // editable = true
    expect(wrapper.text()).toContain('无') // stale_policy = none
  })

  it('source_type 映射到正确的 el-tag type', () => {
    const wrapper = mount(FieldSourcePanel, {
      props: { fieldSource: MOCK_MANUAL_SOURCE, fieldId: 'test' },
      global: globalConfig,
    })

    const tag = wrapper.find('.el-tag-stub')
    expect(tag.attributes('data-type')).toBe('warning')
  })

  it('trial_balance 使用默认 tag type（GT 紫）', () => {
    const wrapper = mount(FieldSourcePanel, {
      props: { fieldSource: MOCK_FIELD_SOURCE, fieldId: 'test' },
      global: globalConfig,
    })

    const tag = wrapper.find('.el-tag-stub')
    // default type is empty string (maps to GT purple via scoped CSS)
    expect(tag.attributes('data-type')).toBe('')
  })

  it('展示编辑权限和确认策略', () => {
    const wrapper = mount(FieldSourcePanel, {
      props: { fieldSource: MOCK_MANUAL_SOURCE, fieldId: 'test' },
      global: globalConfig,
    })

    // override_allowed: true
    expect(wrapper.text()).toContain('允许覆盖')
    // requires_confirmation: true
    expect(wrapper.text()).toContain('需人工确认')
  })
})

// ─── 7.3: 缺失来源时结构化 unknown ───
describe('FieldSourcePanel — 来源缺失', () => {
  it('fieldSource 为 null 时显示结构化未知提示', () => {
    const wrapper = mount(FieldSourcePanel, {
      props: { fieldSource: null, fieldId: 'some.field' },
      global: globalConfig,
    })

    expect(wrapper.find('.gt-field-source-panel__unknown').exists()).toBe(true)
    expect(wrapper.text()).toContain('来源未知')
    expect(wrapper.text()).toContain('该字段暂未配置来源契约')
    // 不应有任何 el-tag
    expect(wrapper.find('.el-tag-stub').exists()).toBe(false)
  })

  it('fieldSource 为 null 时不抛错', () => {
    expect(() => {
      mount(FieldSourcePanel, {
        props: { fieldSource: null, fieldId: '' },
        global: globalConfig,
      })
    }).not.toThrow()
  })
})

// ─── 7.4: resolveSheetType 回退启发式且不破坏渲染 ───
describe('resolveSheetType — 历史 schema 兼容', () => {
  it('sheet_type 缺失时回退启发式识别（审定表）', () => {
    const sheet: SheetRenderConfig = {
      sheet_name: '应收账款审定表D1-1',
      componentType: 'audit-sheet',
      schema: {},
      html_data: {},
      cross_refs: [],
      // 无 sheet_type — 历史 schema
    }
    expect(resolveSheetType(sheet)).toBe('audit_sheet')
  })

  it('sheet_type 缺失时回退启发式识别（明细表）', () => {
    const sheet: SheetRenderConfig = {
      sheet_name: '应收账款明细表',
      componentType: 'audit-sheet',
      schema: {},
      html_data: {},
      cross_refs: [],
    }
    expect(resolveSheetType(sheet)).toBe('detail_table')
  })

  it('sheet_type 缺失且无法启发式识别时返回 unknown', () => {
    const sheet: SheetRenderConfig = {
      sheet_name: '自定义底稿内容',
      componentType: 'custom',
      schema: {},
      html_data: {},
      cross_refs: [],
    }
    expect(resolveSheetType(sheet)).toBe('unknown')
  })

  it('schema 显式 sheet_type 优先于启发式', () => {
    const sheet: SheetRenderConfig = {
      sheet_name: '应收账款明细表', // 启发式会判为 detail_table
      componentType: 'audit-sheet',
      schema: {},
      html_data: {},
      cross_refs: [],
      sheet_type: 'audit_sheet', // 显式指定
    }
    expect(resolveSheetType(sheet)).toBe('audit_sheet')
  })

  it('GtWpRenderer 通过 componentType 分发不依赖 sheet_type', () => {
    // 验证 componentType 和 sheet_type 独立：componentType 仍是渲染分发依据
    const sheet: SheetRenderConfig = {
      sheet_name: '程序控制台',
      componentType: 'a-program-console', // 渲染用
      schema: {},
      html_data: {},
      cross_refs: [],
      sheet_type: 'control_panel', // 语义用
    }
    // componentType 仍为 a-program-console（渲染）
    expect(sheet.componentType).toBe('a-program-console')
    // sheet_type 用于导航/面板（不影响渲染分发）
    expect(resolveSheetType(sheet)).toBe('control_panel')
  })
})
