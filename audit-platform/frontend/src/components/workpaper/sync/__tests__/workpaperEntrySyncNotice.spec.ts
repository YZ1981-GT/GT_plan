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
