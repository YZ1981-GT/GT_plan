// AC 1.4 / 1.5：同步提示必须消费 runtime readiness，静态 capability 不能冒充注册成功。
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

import GtEntrySyncCapabilityNotice from '../GtEntrySyncCapabilityNotice.vue'
import { WORKPAPER_SYNC_MANIFEST } from '../workpaperSyncManifest.generated'
import type { EntrySyncReadiness } from '../workpaperSyncApi'
import {
  ENTRY_SYNC_NOTICE_LABEL,
  ENTRY_SYNC_NOTICE_SUMMARY,
  entrySyncNotice,
} from '../workpaperEntrySyncNotice'

function readiness(
  patch: Partial<EntrySyncReadiness> = {},
): EntrySyncReadiness {
  return {
    entry_id: 'xlsx/test-entry',
    effective_entry_id: 'xlsx/test-entry',
    capability: 'bidirectional',
    adjudication_state: 'terminal',
    allowed_modes: ['html', 'oo'],
    can_claim_bidirectional: true,
    runtime: {
      ready: true,
      adapter_id: 'test.adapter',
      authority_model: 'projection_contract',
      definition_bundle_id: 'bundle',
      definition_bundle_sha256: 'a'.repeat(64),
      typed_slots_complete: true,
      typed_slots: [],
      representation_id: 'representation',
      representation_generation: 1,
    },
    acceptance: {
      state: 'verified', stale: false, run_id: 'run',
      required_scenario_set_digest: 'b'.repeat(64),
    },
    reason: null,
    ...patch,
  }
}

describe('entrySyncNotice — readiness 单一真源', () => {
  it('运行时真正 ready 且 evidence verified 时不显示警告', () => {
    expect(entrySyncNotice(readiness())).toBeNull()
  })

  it('静态 bidirectional 但 runtime blocked 时必须显示原因', () => {
    const value = readiness({
      can_claim_bidirectional: false,
      runtime: { ...readiness().runtime, ready: false },
      reason: {
        code: 'CONTRACT_DRIFT',
        message: '契约与当前发布版本不一致。',
        next_action: '重新发布后重试。',
      },
    })
    const notice = entrySyncNotice(value)
    expect(notice?.level).toBe('unavailable')
    expect(notice?.label).toBe('在线编辑不可用')
    expect(notice?.reason).toContain('重新发布')
  })

  it('pending entry 显示两侧未互通，不把目标态当完成态', () => {
    const value = readiness({
      capability: null,
      adjudication_state: 'pending',
      can_claim_bidirectional: false,
      runtime: { ...readiness().runtime, ready: false, adapter_id: null },
      acceptance: { state: 'not_applicable', stale: false, run_id: null, required_scenario_set_digest: null },
      reason: {
        code: 'ENTRY_UNADJUDICATED',
        message: '该底稿尚未完成双向能力裁决。',
        next_action: '先完成 definition producer。',
      },
    })
    const notice = entrySyncNotice(value)
    expect(notice?.level).toBe('not_synchronized')
    expect(notice?.label).toBe(ENTRY_SYNC_NOTICE_LABEL)
    expect(notice?.summary).toBe(ENTRY_SYNC_NOTICE_SUMMARY)
  })

  it('加载与错误状态都 fail-closed', () => {
    expect(entrySyncNotice(null, 'loading')?.label).toBe('正在核验同步状态')
    expect(entrySyncNotice(null, 'error')?.label).toBe('同步状态读取失败')
  })

  it('提示中不出现笼统成功态', () => {
    const value = readiness({
      capability: null,
      adjudication_state: 'pending',
      reason: { code: 'ENTRY_UNADJUDICATED', message: '尚未完成。', next_action: '继续核对。' },
    })
    const text = JSON.stringify(entrySyncNotice(value))
    for (const forbidden of ['同步成功', '已同步', '可双向回写']) {
      expect(text).not.toContain(forbidden)
    }
  })
})

describe('GtEntrySyncCapabilityNotice — DOM', () => {
  const pendingEntry = WORKPAPER_SYNC_MANIFEST.find(
    (entry) => entry.independentEntry && entry.capability === null,
  )

  it('无运行时 scope 时按静态 pending 事实常显摘要与原因入口', () => {
    expect(pendingEntry).toBeDefined()
    const wrapper = mount(GtEntrySyncCapabilityNotice, {
      props: { entryId: pendingEntry!.entryId },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    expect(wrapper.text()).toContain(ENTRY_SYNC_NOTICE_LABEL)
    expect(wrapper.text()).toContain(ENTRY_SYNC_NOTICE_SUMMARY)
    expect(wrapper.text()).toContain('查看原因')
    const tagged = wrapper.get('[data-entry-sync-notice]')
    expect(tagged.attributes('data-entry-sync-notice')).toBe(pendingEntry!.entryId)
    expect(tagged.attributes('data-entry-sync-state')).toBe('ready')
    wrapper.unmount()
  })

  it('空 entry id 不渲染无主提示', () => {
    const wrapper = mount(GtEntrySyncCapabilityNotice, {
      props: { entryId: '' },
      global: { plugins: [ElementPlus] },
    })
    expect(wrapper.find('[data-entry-sync-notice]').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('能力披露的可达性（键盘 / 窄屏 / 中文可读性，tasks 3.4）', () => {
  const pendingEntry = WORKPAPER_SYNC_MANIFEST.find(
    (entry) => entry.independentEntry && entry.capability === null,
  )

  function mountNotice() {
    expect(pendingEntry, 'manifest 里没有 pending entry ⇒ 判据会在空集上恒真').toBeDefined()
    return mount(GtEntrySyncCapabilityNotice, {
      props: { entryId: pendingEntry!.entryId },
      global: { plugins: [ElementPlus] },
    })
  }

  it('原因入口是真按钮语义，不是带 tabindex 的 span', () => {
    const wrapper = mountNotice()
    const trigger = wrapper.get('.entry-sync-notice__detail')
    expect(trigger.element.tagName).toBe('BUTTON')
    expect(trigger.attributes('type')).toBe('button')
    // 原实现用 `tabindex="0"` 伪造可聚焦：读屏不知道这是可操作元素
    expect(trigger.attributes('tabindex')).toBeUndefined()
    wrapper.unmount()
  })

  it('点击可展开/收起，aria-expanded 与 aria-controls 同步且指向真实节点', async () => {
    const wrapper = mountNotice()
    const trigger = wrapper.get('.entry-sync-notice__detail')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.entry-sync-notice__reason').exists()).toBe(false)

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    const reason = wrapper.get('.entry-sync-notice__reason')
    expect(reason.attributes('id')).toBe(trigger.attributes('aria-controls'))
    expect(reason.attributes('role')).toBe('note')
    expect(trigger.text()).toContain('收起')

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.entry-sync-notice__reason').exists()).toBe(false)
    wrapper.unmount()
  })

  it('展开后的原因是中文、不含占位 code，且与摘要不是同一句', async () => {
    const wrapper = mountNotice()
    await wrapper.get('.entry-sync-notice__detail').trigger('click')
    const reason = wrapper.get('.entry-sync-notice__reason').text().trim()
    const summary = wrapper.get('.entry-sync-notice__summary').text().trim()

    expect(reason.length).toBeGreaterThan(8)
    expect(/[\u4e00-\u9fa5]/.test(reason), `原因无中文：${reason}`).toBe(true)
    // 不得把 reason code / 英文枚举直接甩给用户
    expect(reason).not.toMatch(/[A-Z]{3,}_[A-Z_]{3,}/)
    expect(reason).not.toBe(summary)
    wrapper.unmount()
  })

  it('摘要常显并带 title 兜底（窄屏截断时仍能看到全文）', () => {
    const wrapper = mountNotice()
    const summary = wrapper.get('.entry-sync-notice__summary')
    expect(summary.text().trim().length).toBeGreaterThan(0)
    expect(summary.attributes('title')).toBe(summary.text().trim())
    wrapper.unmount()
  })

  it('原因节点 id 不依赖安全上下文 API（内网 http 下 randomUUID 不可用）', () => {
    const wrapper = mountNotice()
    const id = wrapper.get('.entry-sync-notice__detail').attributes('aria-controls')
    expect(id).toBeTruthy()
    expect(id).toMatch(/^entry-sync-reason-[\w-]+$/)
    // 同一 entry 重复挂载必须得到同一个 id（随机 id 会让 aria 关联在重渲染后失效）
    const again = mountNotice()
    expect(again.get('.entry-sync-notice__detail').attributes('aria-controls')).toBe(id)
    wrapper.unmount()
    again.unmount()
  })
})
