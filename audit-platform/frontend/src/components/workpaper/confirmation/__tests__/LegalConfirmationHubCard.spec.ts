/**
 * A12-1 律师询证函 ↔ 函证中心（spec attachment-confirmation-evidence-loop 需求 5.2）
 *
 * 一张 A12-1 底稿对应函证中心里 `wp_id = 本底稿` 且类型为律师的那一笔；别的底稿 / 别的类型不算。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ElementPlus from 'element-plus'

const apiGet = vi.fn()
const apiPost = vi.fn()
const apiPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...a: any[]) => apiGet(...a), post: (...a: any[]) => apiPost(...a), put: (...a: any[]) => apiPut(...a) },
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {} }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('../ConfirmationAttachmentDrawer.vue', () => ({
  default: defineComponent({
    name: 'DrawerStub',
    props: ['visible', 'confirmationId', 'readonly', 'counterpartyName'],
    setup: (p: any) => () => h('i', { class: 'drawer-stub', 'data-cid': p.confirmationId, 'data-ro': String(!!p.readonly), 'data-open': String(!!p.visible) }),
  }),
}))

import LegalConfirmationHubCard from '../LegalConfirmationHubCard.vue'

const OTHER = [
  { id: 'X1', confirm_type: 'legal', counterparty: '别的所', status: 'sent', wp_id: 'W-other' },
  { id: 'X2', confirm_type: 'receivable', counterparty: '甲律所', status: 'sent', wp_id: 'W1' },
]
const mine = { id: 'C1', confirm_type: 'legal', counterparty: '甲律所', status: 'returned', wp_id: 'W1', outbound_count: 1, inbound_count: 2 }

function mountCard(props: Record<string, unknown> = {}) {
  return mount(LegalConfirmationHubCard, {
    props: { wpId: 'W1', projectId: 'P1', firmName: '甲律所', ...props },
    global: { plugins: [ElementPlus] },
  })
}

describe('A12-1 函证中心卡片', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    apiPut.mockReset()
  })

  it('未登记：只认本底稿的律师函证；登记 = 建律师类型、对象为收件人律师事务所', async () => {
    apiGet.mockResolvedValue({ items: OTHER })
    apiPost.mockResolvedValue({ id: 'C1' })
    const w = mountCard()
    await flushPromises()
    expect(w.text()).toContain('未登记')
    apiGet.mockResolvedValue({ items: [...OTHER, mine] })
    await w.find('[data-testid="legal-hub-register"]').trigger('click')
    await flushPromises()
    expect(apiPost).toHaveBeenCalledWith('/api/projects/P1/confirmations',
      { confirm_type: 'legal', counterparty: '甲律所', wp_id: 'W1' }, { _silent: true })
    expect(w.find('[data-testid="legal-hub-status"]').text()).toBe('已回函')
    expect(w.find('[data-testid="legal-hub-attachments"]').text()).toContain('发函件 1 份 · 回函件 2 份')
  })

  it('没填律师事务所不能登记', async () => {
    apiGet.mockResolvedValue({ items: [] })
    const w = mountCard({ firmName: '  ' })
    await flushPromises()
    expect(w.find('[data-testid="legal-hub-register"]').attributes('disabled')).toBeDefined()
  })

  it('事务所名称改了可一键更新；点件数打开同一个附件抽屉', async () => {
    apiGet.mockResolvedValue({ items: [mine] })
    apiPut.mockResolvedValue({ id: 'C1' })
    const w = mountCard({ firmName: '乙律所' })
    await flushPromises()
    await w.find('[data-testid="legal-hub-rename"]').trigger('click')
    await flushPromises()
    expect(apiPut).toHaveBeenCalledWith('/api/projects/P1/confirmations/C1', { counterparty: '乙律所' }, { _silent: true })
    await w.find('[data-testid="legal-hub-attachments"]').trigger('click')
    expect(w.find('.drawer-stub').attributes()).toMatchObject({ 'data-cid': 'C1', 'data-open': 'true', 'data-ro': 'false' })
  })

  it('只读：不能登记 / 更新，抽屉只读', async () => {
    apiGet.mockResolvedValue({ items: [mine] })
    const w = mountCard({ firmName: '乙律所', readonly: true })
    await flushPromises()
    expect(w.find('[data-testid="legal-hub-rename"]').exists()).toBe(false)
    expect(w.find('.drawer-stub').attributes('data-ro')).toBe('true')
    apiGet.mockResolvedValue({ items: [] })
    const fresh = mountCard({ readonly: true })
    await flushPromises()
    expect(fresh.find('[data-testid="legal-hub-register"]').exists()).toBe(false)
  })
})
