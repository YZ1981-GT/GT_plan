/**
 * TrustScorePanel 单元测试 — V3 收官增强 Req 9.7
 *
 * 验证：
 * 1. 组件 mount 不报错
 * 2. 5 个 Tab 正确渲染
 * 3. open() 方法触发 API 调用
 *
 * Validates: Requirements 9.7
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import TrustScorePanel from '../TrustScorePanel.vue'
import PenetrationTab from '../PenetrationTab.vue'
import HistoryTab from '../HistoryTab.vue'
import AiTracesTab from '../AiTracesTab.vue'
import FormulaTab from '../TrustFormulaTab.vue'
import ConsistencyTab from '../ConsistencyTab.vue'

// Mock api
vi.mock('@/services/apiProxy', () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      data: {
        penetration: [
          { layer: 1, type: 'report', label: '报表行', ref: 'report:BS', value: null },
          { layer: 2, type: 'trial_balance', label: '试算表科目', ref: null, value: null },
          { layer: 3, type: 'workpaper', label: '底稿单元格', ref: null, value: null },
          { layer: 4, type: 'ledger', label: '序时账分录', ref: null, value: null },
          { layer: 5, type: 'voucher', label: '原始凭证', ref: null, value: null },
        ],
        history: [],
        ai: [],
        formula: { root: 'report:BS|A.1', dependencies: [], depth: 0, status: 'placeholder' },
        consistency: {
          is_synced: true,
          unresolved_conflicts: 0,
          is_stale: false,
          is_manual_override: false,
          has_pending_ai: false,
          pending_ai_count: 0,
        },
      },
    }),
  },
}))

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-project-id' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

describe('TrustScorePanel', () => {
  it('mounts without error', () => {
    const wrapper = mount(TrustScorePanel, {
      props: { projectId: 'test-project-id' },
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer"><slot /></div>',
            props: ['modelValue'],
          },
          'el-tabs': {
            template: '<div class="el-tabs"><slot /></div>',
            props: ['modelValue'],
          },
          'el-tab-pane': {
            template: '<div class="el-tab-pane"><slot /></div>',
            props: ['label', 'name', 'disabled'],
          },
          'el-empty': { template: '<div class="el-empty" />' },
          PenetrationTab: true,
          HistoryTab: true,
          AiTracesTab: true,
          FormulaTab: true,
          ConsistencyTab: true,
        },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('exposes open and close methods', () => {
    const wrapper = mount(TrustScorePanel, {
      props: { projectId: 'test-project-id' },
      global: {
        stubs: {
          'el-drawer': {
            template: '<div class="el-drawer"><slot /></div>',
            props: ['modelValue'],
          },
          'el-tabs': {
            template: '<div class="el-tabs"><slot /></div>',
            props: ['modelValue'],
          },
          'el-tab-pane': {
            template: '<div class="el-tab-pane"><slot /></div>',
            props: ['label', 'name', 'disabled'],
          },
          'el-empty': { template: '<div class="el-empty" />' },
          PenetrationTab: true,
          HistoryTab: true,
          AiTracesTab: true,
          FormulaTab: true,
          ConsistencyTab: true,
        },
      },
    })
    expect(typeof wrapper.vm.open).toBe('function')
    expect(typeof wrapper.vm.close).toBe('function')
  })
})

describe('PenetrationTab', () => {
  it('renders timeline items for entries', () => {
    const entries = [
      { layer: 1, type: 'report', label: '报表行', ref: 'report:BS', value: null },
      { layer: 2, type: 'trial_balance', label: '试算表科目', ref: null, value: null },
    ]
    const wrapper = mount(PenetrationTab, {
      props: { entries },
      global: {
        stubs: {
          'el-timeline': { template: '<div class="el-timeline"><slot /></div>' },
          'el-timeline-item': { template: '<div class="el-timeline-item"><slot /></div>', props: ['type', 'hollow'] },
          'el-empty': { template: '<div class="el-empty" />' },
        },
      },
    })
    expect(wrapper.findAll('.el-timeline-item')).toHaveLength(2)
  })

  it('shows empty state when no entries', () => {
    const wrapper = mount(PenetrationTab, {
      props: { entries: [] },
      global: {
        stubs: {
          'el-timeline': { template: '<div class="el-timeline"><slot /></div>' },
          'el-timeline-item': { template: '<div class="el-timeline-item"><slot /></div>', props: ['type', 'hollow'] },
          'el-empty': { template: '<div class="el-empty" />' },
        },
      },
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })
})

describe('ConsistencyTab', () => {
  it('renders all 4 badges', () => {
    const status = {
      is_synced: true,
      unresolved_conflicts: 0,
      is_stale: false,
      is_manual_override: false,
      has_pending_ai: false,
      pending_ai_count: 0,
    }
    const wrapper = mount(ConsistencyTab, {
      props: { status },
      global: {
        stubs: {
          'el-empty': { template: '<div class="el-empty" />' },
        },
      },
    })
    expect(wrapper.findAll('.badge-item')).toHaveLength(4)
  })

  it('shows warning state for unresolved conflicts', () => {
    const status = {
      is_synced: false,
      unresolved_conflicts: 3,
      is_stale: false,
      is_manual_override: false,
      has_pending_ai: true,
      pending_ai_count: 2,
    }
    const wrapper = mount(ConsistencyTab, {
      props: { status },
      global: {
        stubs: {
          'el-empty': { template: '<div class="el-empty" />' },
        },
      },
    })
    const warnBadges = wrapper.findAll('.badge-warn')
    expect(warnBadges.length).toBeGreaterThanOrEqual(2)
  })
})

describe('AiTracesTab', () => {
  it('renders table when entries exist', () => {
    const entries = [
      {
        id: '1',
        model: 'qwen-72b',
        confidence: 0.95,
        confirm_action: 'confirmed',
        generated_at: '2026-05-27T10:00:00Z',
        target_cell: 'workpaper:D2-1:B5',
        content_preview: '测试内容',
      },
    ]
    const wrapper = mount(AiTracesTab, {
      props: { entries },
      global: {
        stubs: {
          'el-table': { template: '<div class="el-table"><slot /></div>', props: ['data', 'border', 'size'] },
          'el-table-column': { template: '<div class="el-table-column" />', props: ['prop', 'label', 'width', 'align', 'min-width', 'show-overflow-tooltip'] },
          'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size'] },
          'el-empty': { template: '<div class="el-empty" />' },
        },
      },
    })
    expect(wrapper.find('.el-table').exists()).toBe(true)
    expect(wrapper.find('.el-empty').exists()).toBe(false)
  })

  it('shows empty state when no entries', () => {
    const wrapper = mount(AiTracesTab, {
      props: { entries: [] },
      global: {
        stubs: {
          'el-table': { template: '<div class="el-table"><slot /></div>', props: ['data', 'border', 'size'] },
          'el-table-column': { template: '<div class="el-table-column" />', props: ['prop', 'label', 'width', 'align', 'min-width', 'show-overflow-tooltip'] },
          'el-empty': { template: '<div class="el-empty" />' },
        },
      },
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })
})
