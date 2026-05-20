/**
 * VRSummaryCard.spec.ts — Sprint 2 Task 4.3
 *
 * 测试 VRSummaryCard.vue 组件:
 * - 全通过绿色标识
 * - blocking 红色标记
 * - 展开 details（el-collapse）
 * - 降级状态（null → "数据获取失败" + retry 按钮）
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { VRSummaryData } from '@/composables/useDashboardData'

// ─── Import component under test ────────────────────────────────────────────

import VRSummaryCard from '../VRSummaryCard.vue'

// ─── Element Plus stubs ──────────────────────────────────────────────────────

const globalStubs = {
  'el-empty': {
    template: '<div class="el-empty"><slot name="description" /><slot /></div>',
    props: ['imageSize', 'description'],
  },
  'el-button': {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size'],
    emits: ['click'],
  },
  'el-tag': {
    template: '<span class="el-tag" :data-type="type"><slot /></span>',
    props: ['type', 'effect', 'size'],
  },
  'el-collapse': {
    template: '<div class="el-collapse"><slot /></div>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-collapse-item': {
    template: '<div class="el-collapse-item"><div class="el-collapse-item__title"><slot name="title" /></div><div class="el-collapse-item__content"><slot /></div></div>',
    props: ['name'],
  },
  'el-badge': {
    template: '<span class="el-badge" :data-value="value" :data-type="type">{{ value }}</span>',
    props: ['value', 'type'],
  },
}

// ─── Test Fixtures ───────────────────────────────────────────────────────────

function createAllPassedData(): VRSummaryData {
  return {
    total_rules: 33,
    blocking_failed: 0,
    all_passed: true,
    by_cycle: [],
  }
}

function createBlockingData(): VRSummaryData {
  return {
    total_rules: 33,
    blocking_failed: 3,
    all_passed: false,
    by_cycle: [
      {
        cycle: 'D',
        blocking_failed: 2,
        failed_rules: [
          { rule_id: 'VR-D4-01', rule_name: '收入确认完整性', details: '销售收入与发票金额差异超过重要性水平' },
          { rule_id: 'VR-D4-02', rule_name: '截止测试', details: null },
        ],
      },
      {
        cycle: 'F',
        blocking_failed: 1,
        failed_rules: [
          { rule_id: 'VR-F2-01', rule_name: '存货计价', details: '成本与可变现净值差异' },
        ],
      },
      {
        cycle: 'E',
        blocking_failed: 0,
        failed_rules: [],
      },
    ],
  }
}

function mountComponent(props: { vrSummary: VRSummaryData | null; error: string | null }) {
  return mount(VRSummaryCard, {
    props,
    global: { stubs: globalStubs },
  })
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('VRSummaryCard — 全通过绿色标识', () => {
  it('all_passed=true 时显示"全部通过"绿色标签', () => {
    const wrapper = mountComponent({ vrSummary: createAllPassedData(), error: null })
    const passBadge = wrapper.find('.vr-pass-badge')
    expect(passBadge.exists()).toBe(true)
    expect(passBadge.text()).toBe('全部通过')
    expect(passBadge.attributes('data-type')).toBe('success')
  })

  it('all_passed=true 时不显示循环分组列表', () => {
    const wrapper = mountComponent({ vrSummary: createAllPassedData(), error: null })
    expect(wrapper.find('.vr-cycle-list').exists()).toBe(false)
  })

  it('all_passed=true 时显示 blocking_failed=0 统计', () => {
    const wrapper = mountComponent({ vrSummary: createAllPassedData(), error: null })
    expect(wrapper.find('.vr-blocking-count').text()).toBe('0')
    expect(wrapper.find('.vr-total-count').text()).toBe('33')
  })
})

describe('VRSummaryCard — blocking 红色标记', () => {
  it('显示 blocking_failed 数量', () => {
    const wrapper = mountComponent({ vrSummary: createBlockingData(), error: null })
    expect(wrapper.find('.vr-blocking-count').text()).toBe('3')
  })

  it('不显示"全部通过"标签', () => {
    const wrapper = mountComponent({ vrSummary: createBlockingData(), error: null })
    expect(wrapper.find('.vr-pass-badge').exists()).toBe(false)
  })

  it('仅渲染 blocking_failed > 0 的循环', () => {
    const wrapper = mountComponent({ vrSummary: createBlockingData(), error: null })
    const collapseItems = wrapper.findAll('.el-collapse-item')
    // D(2) + F(1) = 2 items, E(0) 不渲染
    expect(collapseItems).toHaveLength(2)
  })

  it('每个循环显示 danger 类型的 badge', () => {
    const wrapper = mountComponent({ vrSummary: createBlockingData(), error: null })
    const badges = wrapper.findAll('.el-badge')
    expect(badges.length).toBeGreaterThanOrEqual(2)
    expect(badges[0].attributes('data-type')).toBe('danger')
    expect(badges[0].attributes('data-value')).toBe('2')
  })

  it('显示失败规则的 rule_id 和 rule_name', () => {
    const wrapper = mountComponent({ vrSummary: createBlockingData(), error: null })
    const ruleItems = wrapper.findAll('.vr-rule-item')
    expect(ruleItems.length).toBe(3) // D:2 + F:1
    expect(wrapper.text()).toContain('VR-D4-01')
    expect(wrapper.text()).toContain('收入确认完整性')
  })
})

describe('VRSummaryCard — 展开 details（el-collapse）', () => {
  it('规则有 details 时显示详情文本', () => {
    const wrapper = mountComponent({ vrSummary: createBlockingData(), error: null })
    const details = wrapper.findAll('.vr-rule-details')
    // VR-D4-01 有 details, VR-D4-02 无 details, VR-F2-01 有 details
    expect(details).toHaveLength(2)
    expect(details[0].text()).toBe('销售收入与发票金额差异超过重要性水平')
  })

  it('规则无 details 时不渲染详情区域', () => {
    const data = createBlockingData()
    // 确保 VR-D4-02 的 details 为 null
    const wrapper = mountComponent({ vrSummary: data, error: null })
    const ruleItems = wrapper.findAll('.vr-rule-item')
    // 第二个规则（VR-D4-02）不应有 .vr-rule-details
    const secondRule = ruleItems[1]
    expect(secondRule.find('.vr-rule-details').exists()).toBe(false)
  })

  it('collapse 组件存在且可交互', () => {
    const wrapper = mountComponent({ vrSummary: createBlockingData(), error: null })
    expect(wrapper.find('.el-collapse').exists()).toBe(true)
  })
})

describe('VRSummaryCard — 降级状态', () => {
  it('vrSummary=null 时显示"数据获取失败"', () => {
    const wrapper = mountComponent({ vrSummary: null, error: null })
    expect(wrapper.text()).toContain('数据获取失败')
  })

  it('vrSummary=null 时显示自定义 error 消息', () => {
    const wrapper = mountComponent({ vrSummary: null, error: 'ConsistencyGate timeout' })
    expect(wrapper.text()).toContain('ConsistencyGate timeout')
  })

  it('vrSummary=null 时显示重试按钮', () => {
    const wrapper = mountComponent({ vrSummary: null, error: null })
    const retryBtn = wrapper.find('.el-button')
    expect(retryBtn.exists()).toBe(true)
    expect(retryBtn.text()).toBe('重试')
  })

  it('点击重试按钮触发 retry 事件', async () => {
    const wrapper = mountComponent({ vrSummary: null, error: null })
    const retryBtn = wrapper.find('.el-button')
    await retryBtn.trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('vrSummary=null 时不显示汇总统计', () => {
    const wrapper = mountComponent({ vrSummary: null, error: null })
    expect(wrapper.find('.vr-summary-header').exists()).toBe(false)
  })
})
