/**
 * formula-manager-closure Task 2.1 — openFormulaManagerFromLocation 组件级单测.
 *
 * 覆盖 ADR-FMC-03 / 需求 3.1/3.2/3.3/3.5/9.1：
 *  - 生产入口经统一命令 createOpenFormulaManagerCommand 校验（#5）。
 *  - 提交完整 CanonicalWorkpaperLocation（projectId/wpId/wpCode/sheet），断言③。
 *  - 缺 wpId/projectId/wpCode → fail-closed（不发 node-only、不开 context-less 弹窗）。
 *  - 底稿入口 scope 恒为 workpaper，不落 report。
 *
 * 单测级变异反证（门禁级①②③交 Task 8.1）：
 *  - 「去 wp_id」样本命中③（emit 不触发、返回 incomplete_location），配反向断言
 *    （完整样本 emit 一次且 payload 带完整 location）。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

const emitted: Array<{ event: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (event: string, payload: any) => {
      emitted.push({ event, payload })
    },
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// Spy on the unified command to prove production truly routes through it (#5).
import * as commandModule from '../openFormulaManagerCommand'
import {
  openFormulaManagerFromLocation,
  openFormulaManagerScope,
  buildLocationFromContext,
  payloadFromLocation,
  type FormulaManagerOutletContext,
} from '../openFormulaManagerFromLocation'

import type { WorkpaperCapabilitySnapshot } from '../workpaperCapabilitySnapshot'

function fullCtx(overrides: Partial<FormulaManagerOutletContext> = {}): FormulaManagerOutletContext {
  return {
    projectId: 'proj-1',
    wpId: 'wp-123',
    wpCode: 'E1',
    year: 2026,
    sheetName: 'E1-1',
    sheetCodes: ['E1-1', 'E1-2'],
    host: 'html',
    ...overrides,
  }
}

function capability(allowed = true): WorkpaperCapabilitySnapshot {
  const decision = {
    allowed,
    reasonCode: allowed ? null : 'denied',
    owner: 'test',
    nextAction: null,
    zhMessage: allowed ? null : '无权限',
  }
  return {
    snapshotVersion: '1.0', subjectDigest: 'a'.repeat(64), ownerEpoch: 0,
    expiresAt: '2099-01-01T00:00:00Z',
    formulaView: decision, formulaEditUser: decision, formulaHistory: decision,
    aiReviewPage: decision, aiReviewBatch: decision, aiAssistChat: decision,
    humanReviewRead: decision, humanReviewWrite: decision, guidanceRead: decision,
  }
}

describe('openFormulaManagerFromLocation — Task 2.1 (ADR-FMC-03)', () => {
  beforeEach(() => {
    emitted.length = 0
    vi.restoreAllMocks()
  })

  it('完整上下文：经统一命令校验后提交完整 location 并 emit 一次（断言③反向）', () => {
    const spy = vi.spyOn(commandModule, 'createOpenFormulaManagerCommand')
    const realCapability = capability()
    const outcome = openFormulaManagerFromLocation(fullCtx(), realCapability)

    // #5：生产真正调用 createOpenFormulaManagerCommand，且使用调用方真实快照。
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy.mock.calls[0][0].capability).toBe(realCapability)
    const passedLocation = spy.mock.calls[0][0].location
    expect(passedLocation.projectId).toBe('proj-1')
    expect(passedLocation.wpId).toBe('wp-123')
    expect(passedLocation.wpCode).toBe('E1')

    expect(outcome.ok).toBe(true)
    // ③：提交完整 location（payload 带 projectId/wpId/wpCode/sheetName，非仅 nodeKey）。
    expect(emitted).toHaveLength(1)
    expect(emitted[0].event).toBe('open-formula-manager')
    const payload = emitted[0].payload
    expect(payload.projectId).toBe('proj-1')
    expect(payload.wpId).toBe('wp-123')
    expect(payload.wpCode).toBe('E1')
    expect(payload.sheetName).toBe('E1-1')
    expect(payload.year).toBe(2026)
    // 底稿入口 scope 恒 workpaper，不落 report。
    expect(payload.scope).toBe('workpaper')
    // 不退 node-only：无 nodeKey（除非显式 legacyNodeKey）。
    expect(payload.nodeKey).toBeUndefined()
  })

  it('变异「去 wp_id」命中③：fail-closed、不 emit、不调命令', () => {
    const spy = vi.spyOn(commandModule, 'createOpenFormulaManagerCommand')
    const outcome = openFormulaManagerFromLocation(fullCtx({ wpId: '' }), capability())

    expect(outcome.ok).toBe(false)
    if (!outcome.ok) expect(outcome.reasonCode).toBe('incomplete_location')
    // 缺 wpId ⇒ 连命令都不该调用（location 构建期即 fail-closed）。
    expect(spy).not.toHaveBeenCalled()
    // 不发 node-only、不开 context-less 弹窗。
    expect(emitted).toHaveLength(0)
  })

  it('缺 projectId / wpCode 同样 fail-closed', () => {
    expect(openFormulaManagerFromLocation(fullCtx({ projectId: '' }), capability()).ok).toBe(false)
    expect(openFormulaManagerFromLocation(fullCtx({ wpCode: '' }), capability()).ok).toBe(false)
    expect(emitted).toHaveLength(0)
  })

  it('buildLocationFromContext：完整字段 → sheet anchor；空 sheet → whole_workbook', () => {
    const withSheet = buildLocationFromContext(fullCtx())
    expect(withSheet).not.toBeNull()
    expect(withSheet!.anchor.kind).toBe('sheet')

    const workbook = buildLocationFromContext(fullCtx({ sheetName: '' }))
    expect(workbook!.anchor.kind).toBe('whole_workbook')
    expect(workbook!.display.sheetName).toBeNull()
  })

  it('buildLocationFromContext：缺任一必需身份 → null（fail-closed）', () => {
    expect(buildLocationFromContext(fullCtx({ wpId: '' }))).toBeNull()
    expect(buildLocationFromContext(fullCtx({ projectId: '  ' }))).toBeNull()
    expect(buildLocationFromContext(fullCtx({ wpCode: undefined }))).toBeNull()
  })

  it('payloadFromLocation：scope 默认 workpaper（不退 report），extras 合并保留', () => {
    const loc = buildLocationFromContext(fullCtx())!
    const payload = payloadFromLocation(loc, fullCtx({ extras: { templateType: 'listed' } }))
    expect(payload.scope).toBe('workpaper')
    expect(payload.templateType).toBe('listed')

    // workpaper helper 强制收敛为 workpaper；附注/合并必须走 openFormulaManagerScope。
    const noteLoc = buildLocationFromContext(fullCtx())!
    const notePayload = payloadFromLocation(noteLoc, fullCtx({ scope: 'note' }))
    expect(notePayload.scope).toBe('workpaper')
  })

  it('legacyNodeKey 作为迁移元数据可随 payload 透传（非位置身份）', () => {
    openFormulaManagerFromLocation(fullCtx({ legacyNodeKey: 'wp_e1_1' }), capability())
    expect(emitted).toHaveLength(1)
    expect(emitted[0].payload.nodeKey).toBe('wp_e1_1')
    // 但位置身份仍来自完整 location，而非 nodeKey。
    expect(emitted[0].payload.wpId).toBe('wp-123')
  })
})


describe('真实 capability fail-closed', () => {
  beforeEach(() => { emitted.length = 0 })

  it('缺 capability 不 emit，不能再由 helper 制造全允许快照', () => {
    const outcome = openFormulaManagerFromLocation(fullCtx(), null)
    expect(outcome.ok).toBe(false)
    if (!outcome.ok) expect(outcome.reasonCode).toBe('capability_missing')
    expect(emitted).toHaveLength(0)
  })

  it('formulaView 被拒绝时不打开', () => {
    const outcome = openFormulaManagerFromLocation(fullCtx(), capability(false))
    expect(outcome.ok).toBe(false)
    expect(emitted).toHaveLength(0)
  })
})


describe('显式 project scope context', () => {
  beforeEach(() => { emitted.length = 0 })

  it('合并 scope 不伪造 wpId，完整保留项目/年度/章节', () => {
    const outcome = openFormulaManagerScope({
      scope: 'consol_note', projectId: 'p-consol', year: 2025,
      noteSection: '五、1', templateType: 'soe',
    })
    expect(outcome.ok).toBe(true)
    expect(emitted).toHaveLength(1)
    expect(emitted[0].payload.contextKind).toBe('scope')
    expect(emitted[0].payload.wpId).toBeUndefined()
    expect(emitted[0].payload.noteSection).toBe('五、1')
  })

  it('缺项目或年度 fail-closed', () => {
    expect(openFormulaManagerScope({ scope: 'consol_report', projectId: '', year: 2025 }).ok).toBe(false)
    expect(openFormulaManagerScope({ scope: 'consol_report', projectId: 'p', year: Number.NaN }).ok).toBe(false)
    expect(emitted).toHaveLength(0)
  })
})
