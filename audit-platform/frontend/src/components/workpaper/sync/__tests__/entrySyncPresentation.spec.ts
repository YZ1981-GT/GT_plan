import { describe, expect, it } from 'vitest'
import type { EntrySyncReadiness } from '../workpaperSyncApi'
import { deriveEntrySyncPresentation, isFirstPublicationPending } from '../entrySyncPresentation'

function value(patch: Partial<EntrySyncReadiness> = {}): EntrySyncReadiness {
  return {
    entry_id: 'xlsx/test', effective_entry_id: 'xlsx/test',
    capability: 'bidirectional', adjudication_state: 'terminal',
    allowed_modes: ['html', 'oo'], can_claim_bidirectional: true,
    runtime: {
      ready: true, adapter_id: 'a', authority_model: 'projection_contract',
      definition_bundle_id: 'b', definition_bundle_sha256: 'a'.repeat(64),
      typed_slots_complete: true, typed_slots: [], representation_id: 'r',
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

describe('deriveEntrySyncPresentation', () => {
  it('single 模式不显示不可兑现的切换按钮', () => {
    const html = deriveEntrySyncPresentation(value({ capability: 'single_html', allowed_modes: ['html'] }), 'ready')
    expect(html).toMatchObject({ showHtml: true, showOnlyOffice: false, showModeSwitch: false })
    const oo = deriveEntrySyncPresentation(value({ capability: 'single_onlyoffice', allowed_modes: ['oo'] }), 'ready')
    expect(oo).toMatchObject({ showHtml: false, showOnlyOffice: true, showModeSwitch: false })
  })

  it('pending 不把目标态当完成态', () => {
    const got = deriveEntrySyncPresentation(value({ capability: null, adjudication_state: 'pending' }), 'ready')
    expect(got.showModeSwitch).toBe(false)
    expect(got.canClaimBidirectional).toBe(false)
    expect(got.noticeLabel).toBe('两侧数据未互通')
  })

  it('runtime blocked 时只保留回到 HTML 的出口', () => {
    const got = deriveEntrySyncPresentation(value({
      can_claim_bidirectional: false,
      runtime: { ...value().runtime, ready: false },
    }), 'ready')
    expect(got).toMatchObject({ showHtml: true, showOnlyOffice: false, canSwitchToOnlyOffice: false })
  })

  it('首版 representation 缺失时保留在线编辑入口以触发首次发布', () => {
    const got = deriveEntrySyncPresentation(value({
      allowed_modes: ['html'],
      can_claim_bidirectional: false,
      runtime: { ...value().runtime, ready: false, representation_id: null, representation_generation: null },
      acceptance: { state: 'missing', stale: false, run_id: null, required_scenario_set_digest: null },
      reason: {
        code: 'REPRESENTATION_MISSING',
        message: '当前底稿尚未发布可用于在线编辑的版本。',
        next_action: '先完成该底稿的首版 representation 发布，再重新检查。',
      },
    }), 'ready')
    expect(got).toMatchObject({
      showHtml: true,
      showOnlyOffice: true,
      showModeSwitch: true,
      canSwitchToOnlyOffice: true,
      canClaimBidirectional: false,
      noticeKind: 'warning',
      noticeLabel: '首次在线编辑将发布版本',
    })
  })

  it('runtime ready 才显示双向切换；evidence 缺失只告警不禁用', () => {
    const verified = deriveEntrySyncPresentation(value(), 'ready')
    expect(verified).toMatchObject({ showModeSwitch: true, canSwitchToOnlyOffice: true, noticeKind: 'none' })
    const missing = deriveEntrySyncPresentation(value({
      acceptance: { state: 'missing', stale: false, run_id: null, required_scenario_set_digest: null },
    }), 'ready')
    expect(missing.showModeSwitch).toBe(true)
    expect(missing.canSwitchToOnlyOffice).toBe(true)
    expect(missing.noticeLabel).toBe('验收证据待更新')
  })

  it('loading/error 都 fail-closed', () => {
    expect(deriveEntrySyncPresentation(null, 'loading')).toMatchObject({
      canSwitchToOnlyOffice: false, noticeLabel: '正在核验同步状态',
    })
    expect(deriveEntrySyncPresentation(null, 'error')).toMatchObject({
      canSwitchToOnlyOffice: false, noticeLabel: '同步状态读取失败',
    })
  })

  it('unreachable 不挂任何视图', () => {
    const got = deriveEntrySyncPresentation(value({
      capability: 'unreachable', allowed_modes: [], can_claim_bidirectional: false,
    }), 'ready')
    expect(got).toMatchObject({ showHtml: false, showOnlyOffice: false, showModeSwitch: false })
  })
})

describe('revalidating：已有裁决可展示、运行时仍在核验', () => {
  it('按静态裁决给可见性，不产生开关闪跳', () => {
    const got = deriveEntrySyncPresentation(value({
      can_claim_bidirectional: false,
      // 静态兜底里的 runtime.ready 是占位值（非实测）
      runtime: { ...value().runtime, ready: false, adapter_id: null },
      acceptance: { state: 'missing', stale: false, run_id: null, required_scenario_set_digest: null },
    }), 'revalidating')
    expect(got.showModeSwitch).toBe(true)
    expect(got.canSwitchToOnlyOffice).toBe(true)
    expect(got.noticeLabel).toBe('正在核验同步状态')
  })

  it('核验期不宣称已验收双向', () => {
    expect(deriveEntrySyncPresentation(value(), 'revalidating').canClaimBidirectional).toBe(false)
  })

  it('非 bidirectional 裁决在核验期也不得长出开关', () => {
    for (const capability of ['single_html', 'single_onlyoffice', null] as const) {
      const got = deriveEntrySyncPresentation(
        value({ capability, allowed_modes: capability === 'single_html' ? ['html'] : ['oo'] }),
        'revalidating',
      )
      expect(got.showModeSwitch, String(capability)).toBe(false)
      expect(got.canSwitchToOnlyOffice, String(capability)).toBe(false)
    }
  })

  it('unreachable 在核验期仍不挂任何视图', () => {
    const got = deriveEntrySyncPresentation(value({
      capability: 'unreachable', allowed_modes: [], can_claim_bidirectional: false,
    }), 'revalidating')
    expect(got).toMatchObject({ showHtml: false, showOnlyOffice: false, showModeSwitch: false })
  })
})

describe('尚无首版：入口开放，首次进入在线编辑时自动发布首版', () => {
  const noFirstVersion = (patch: Partial<EntrySyncReadiness> = {}) => value({
    can_claim_bidirectional: false,
    runtime: { ...value().runtime, ready: false },
    acceptance: { state: 'missing', stale: false, run_id: null, required_scenario_set_digest: null },
    reason: {
      code: 'REPRESENTATION_MISSING',
      message: '当前底稿尚未发布在线编辑版本。',
      next_action: '首次进入在线编辑时会自动发布首版。',
    },
    ...patch,
  })

  it('显示切换、可进入在线编辑，但不宣称已验收双向', () => {
    const got = deriveEntrySyncPresentation(noFirstVersion(), 'ready')
    expect(got).toMatchObject({
      showOnlyOffice: true, showModeSwitch: true, canSwitchToOnlyOffice: true,
      canClaimBidirectional: false, noticeKind: 'warning',
    })
    expect(got.noticeLabel).not.toBe('在线编辑不可用')
  })

  it('判据只认这一个原因码：其余未就绪原因照旧不可用', () => {
    const other = noFirstVersion({
      reason: { code: 'ADAPTER_NOT_READY', message: 'adapter 未就绪', next_action: '' },
    })
    expect(isFirstPublicationPending(other)).toBe(false)
    expect(deriveEntrySyncPresentation(other, 'ready')).toMatchObject({
      showOnlyOffice: false, canSwitchToOnlyOffice: false, noticeLabel: '在线编辑不可用',
    })
  })

  it('后端没放行 oo 时不开放（判据不越过后端的 allowed_modes）', () => {
    expect(isFirstPublicationPending(noFirstVersion({ allowed_modes: ['html'] }))).toBe(false)
  })

  it('非 bidirectional 不适用', () => {
    expect(isFirstPublicationPending(noFirstVersion({ capability: 'single_html' }))).toBe(false)
  })
})
