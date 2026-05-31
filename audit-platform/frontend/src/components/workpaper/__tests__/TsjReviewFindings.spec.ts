/**
 * TsjReviewFindings.spec.ts — TSJ 复核发现列表 vitest
 *
 * spec wp-ai-review-ux-fix task 6
 *
 * 验证：
 * 1. C1: wpCode prop 存在时渲染底稿编号 el-tag
 * 2. 确认/驳回按钮基本渲染
 * 3. locate-cell emit 包含 componentType
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TsjReviewFindings from '../TsjReviewFindings.vue'

const mockPost = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

const globalStubs = {
  stubs: {
    'el-tag': {
      template: '<span class="stub-tag" :data-type="type" :data-effect="effect"><slot /></span>',
      props: ['type', 'size', 'effect', 'round'],
    },
    'el-button': {
      template: '<button class="stub-btn" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
      props: ['type', 'size', 'loading', 'disabled'],
      emits: ['click'],
    },
    'el-button-group': {
      template: '<div class="stub-btn-group"><slot /></div>',
    },
    'el-card': {
      template: '<div class="stub-card"><div class="stub-card-header"><slot name="header" /></div><slot /></div>',
      props: ['shadow'],
    },
    'el-link': {
      template: '<a class="stub-link" @click="$emit(\'click\')"><slot /></a>',
      props: ['type', 'underline'],
      emits: ['click'],
    },
  },
}

function makeFinding(overrides = {}): any {
  return {
    id: 'f-001',
    content_type: 'finding',
    content_text: '测试发现内容',
    confidence_level: 'high',
    confirmation_status: 'pending',
    issue_type: '数值错误',
    severity: 'high',
    sheet: 'Sheet1',
    cell_range: 'B5',
    description: '金额计算有误',
    remediation: '请核实公式',
    ...overrides,
  }
}

describe('TsjReviewFindings — C1 底稿编号 tag', () => {
  beforeEach(() => {
    mockPost.mockReset()
  })

  it('wpCode 存在时渲染底稿编号 el-tag（type=primary, effect=plain）', () => {
    const wrapper = mount(TsjReviewFindings, {
      props: {
        findings: [makeFinding()],
        wpId: 'wp-123',
        wpCode: 'D2-1',
      },
      global: globalStubs,
    })

    const tags = wrapper.findAll('.stub-tag')
    const wpTag = tags.find((t) => t.text().includes('D2-1'))
    expect(wpTag).toBeTruthy()
    expect(wpTag!.attributes('data-type')).toBe('primary')
    expect(wpTag!.attributes('data-effect')).toBe('plain')
    expect(wpTag!.text()).toContain('📋')
  })

  it('wpCode 为空时不渲染底稿编号 tag', () => {
    const wrapper = mount(TsjReviewFindings, {
      props: {
        findings: [makeFinding()],
        wpId: 'wp-123',
      },
      global: globalStubs,
    })

    const tags = wrapper.findAll('.stub-tag')
    const wpTag = tags.find((t) => t.text().includes('📋'))
    expect(wpTag).toBeUndefined()
  })

  it('多条发现每条都显示底稿编号', () => {
    const wrapper = mount(TsjReviewFindings, {
      props: {
        findings: [makeFinding({ id: 'f-001' }), makeFinding({ id: 'f-002' })],
        wpId: 'wp-123',
        wpCode: 'E1',
      },
      global: globalStubs,
    })

    const wpTags = wrapper.findAll('.stub-tag').filter((t) => t.text().includes('📋'))
    expect(wpTags).toHaveLength(2)
    wpTags.forEach((tag) => {
      expect(tag.text()).toContain('E1')
    })
  })
})

describe('TsjReviewFindings — 确认/驳回', () => {
  beforeEach(() => {
    mockPost.mockReset()
  })

  it('每条发现有确认和驳回按钮', () => {
    const wrapper = mount(TsjReviewFindings, {
      props: {
        findings: [makeFinding()],
        wpId: 'wp-123',
        wpCode: 'D2-1',
      },
      global: globalStubs,
    })

    const buttons = wrapper.findAll('.stub-btn')
    const confirmBtn = buttons.find((b) => b.text().includes('确认'))
    const rejectBtn = buttons.find((b) => b.text().includes('驳回'))
    expect(confirmBtn).toBeTruthy()
    expect(rejectBtn).toBeTruthy()
  })

  it('确认成功后 emit finding-confirmed', async () => {
    mockPost.mockResolvedValueOnce({})
    const finding = makeFinding()

    const wrapper = mount(TsjReviewFindings, {
      props: {
        findings: [finding],
        wpId: 'wp-123',
        wpCode: 'D2-1',
      },
      global: globalStubs,
    })

    const confirmBtn = wrapper.findAll('.stub-btn').find((b) => b.text().includes('确认'))
    await confirmBtn!.trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledWith('/api/ai-content/f-001/confirm')
    const emitted = wrapper.emitted('finding-confirmed')
    expect(emitted).toHaveLength(1)
  })
})

describe('TsjReviewFindings — locate-cell emit 含 componentType', () => {
  it('点定位 emit 包含 componentType', async () => {
    const wrapper = mount(TsjReviewFindings, {
      props: {
        findings: [makeFinding()],
        wpId: 'wp-123',
        wpCode: 'D2-1',
        componentType: 'c-note-table',
      },
      global: globalStubs,
    })

    const locateLink = wrapper.findAll('.stub-link').find((l) => l.text().includes('定位'))
    expect(locateLink).toBeTruthy()
    await locateLink!.trigger('click')

    const emitted = wrapper.emitted('locate-cell')
    expect(emitted).toHaveLength(1)
    expect(emitted![0][0]).toEqual({
      wpCode: 'D2-1',
      sheet: 'Sheet1',
      cellRange: 'B5',
      componentType: 'c-note-table',
    })
  })
})
