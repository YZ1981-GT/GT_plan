import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const entries = ref<any[]>([])
const loading = ref(false)
const error = ref(false)
const retry = vi.fn()
vi.mock('@/composables/useContractEvidenceIndex', () => ({
  useContractEvidenceIndex: () => ({ entries, loading, error, retry }),
}))
vi.mock('@/components/attachment/AttachmentEyeButton.vue', () => ({
  default: { props: ['attachmentId'], template: '<button class="eye">查看 {{ attachmentId }}</button>' },
}))

import D4ContractCard from '../D4ContractCard.vue'

const item = () => ({
  id: 'c-1', indexNo: 'D4-12-1', label: '销售合同', contractNo: 'HT-001', counterparty: '甲方',
  signDate: '', serviceContent: '', contractAmount: 0, deliveryTime: '', deliveryMethod: '',
  settlementMethod: '', settlementTime: '', warrantyClause: '', returnClause: '', breachClause: '',
  specialTerms: '', isSigned: '', isSealed: '', recognitionMethod: '', acceptanceClause: '',
  recognitionTime: '', controlTransferDoc: '', specialTransaction: '', conclusion: '', ocrStatus: 'none',
})

const buttonStub = { template: '<button v-bind="$attrs"><slot /></button>' }
const mountCard = (readonly = false) => mount(D4ContractCard, {
  props: { item: item() as any, isReadonly: readonly, ocrLoading: false, projectId: 'p1', wpId: 'w1' },
  global: { stubs: {
    'el-button': buttonStub, 'el-icon': { template: '<span><slot /></span>' },
    'el-tag': { template: '<span><slot /></span>' }, 'el-upload': { template: '<div><slot /></div>' },
    'el-progress': true, 'el-input': true, 'el-date-picker': true, 'el-input-number': true,
    'el-radio-group': { template: '<div><slot /></div>' }, 'el-radio-button': { template: '<span><slot /></span>' },
  } },
})

describe('D4ContractCard 合同证据', () => {
  beforeEach(() => {
    entries.value = []
    loading.value = false
    error.value = false
    retry.mockReset()
  })

  it('加载失败明确区别于无证据并可重试', async () => {
    error.value = true
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('加载失败，不能据此判断为无证据')
    await wrapper.get('[data-testid="contract-evidence-retry"]').trigger('click')
    expect(retry).toHaveBeenCalledTimes(1)
  })

  it('显示他稿原件、可预览并发出引用动作', async () => {
    const attachment = { id: 'a1', file_name: '合同原件.pdf', file_type: 'pdf', ocr_status: 'completed' }
    const entry = { working_paper_id: 'w2', wp_code: 'D4-11', wp_name: '合同检查', attachments: [attachment] }
    entries.value = [entry]
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('其他底稿已有 1 份')
    expect(wrapper.find('.eye').exists()).toBe(true)
    await wrapper.get('[data-testid="contract-evidence-reuse"]').trigger('click')
    expect(wrapper.emitted('reuse-evidence')?.[0]).toEqual([{ attachment, entry }])
  })

  it('只读仍可查看原件但不能引用', () => {
    entries.value = [{
      working_paper_id: 'w2', wp_code: 'D4-11', wp_name: '合同检查',
      attachments: [{ id: 'a1', file_name: '合同原件.pdf', file_type: 'pdf', ocr_status: 'completed' }],
    }]
    const wrapper = mountCard(true)
    expect(wrapper.find('.eye').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('引用到本底稿')
  })
})
