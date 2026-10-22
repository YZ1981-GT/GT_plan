/**
 * Property 14: 编辑器呈现等于模型
 *
 * Feature: partner-manager-edit-permission, Property 14: 编辑器呈现等于模型
 * Validates: Requirements 10.3, 10.4, 10.5, 10.11
 *
 * fast-check numRuns: 5（用户约定）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { presentEntry, type NoteEditState, type PresentationResult } from '../noteEditPresentation'
import { WRITE_ENTRIES, type NoteWriteEntry } from '../noteEditWriteEntries'

// ── Generators ──────────────────────────────────────────────────────────────

/** 只生成需求 10.1 可能出现的组合 */
const queryStatusArb = fc.constantFrom('pending' as const, 'ok' as const, 'failed' as const)

const reasons = [
  '权限不足',
  '独立复核合伙人（EQCR）在本项目只读',
  '当前角色没有编辑附注的操作权限',
  '项目已归档，无法编辑',
]

/** 生成合法的 NoteEditState（判为 EQCR 时 canEdit 必为 false） */
const stateArb: fc.Arbitrary<NoteEditState> = fc.tuple(
  queryStatusArb,
  fc.boolean(), // canEdit
  fc.constantFrom(null, ...reasons),
  fc.boolean(), // isEqcr
  fc.boolean(), // isArchived
  fc.boolean(), // forcedReadonly
).filter(([status, canEdit, reason, isEqcr]) => {
  // 只在 ok 时有意义
  if (status !== 'ok') return true
  // 判为 EQCR 时 canEdit 必为 false
  if (isEqcr && canEdit) return false
  // 不能编辑时 reason 非空
  if (!canEdit && !reason) return false
  // 能编辑时 reason 应为 null
  if (canEdit && reason) return false
  return true
}).map(([queryStatus, canEdit, reason, isEqcr, isArchived, forcedReadonly]) => ({
  queryStatus, canEdit, reason, isEqcr, isArchived, forcedReadonly,
}))

const entryArb: fc.Arbitrary<NoteWriteEntry> = fc.constantFrom(...WRITE_ENTRIES)

// ── Reference model ─────────────────────────────────────────────────────────

function model(state: NoteEditState, entry: NoteWriteEntry): PresentationResult {
  const { queryStatus, canEdit, isEqcr, isArchived, forcedReadonly } = state
  const { lockConstrained, eqcrHidden, coverage } = entry

  const queryOk = queryStatus === 'ok'

  // 按 EQCR 隐藏的入口的 rendered
  if (eqcrHidden) {
    const rendered = queryOk && !isEqcr
    if (!rendered) return { operable: false, rendered: false, disabled: false, tooltip: '' }
    // 渲染了但不能写
    if (coverage) {
      const baseCanWrite = queryOk && canEdit && !isArchived
      const operable = baseCanWrite && (!lockConstrained || !forcedReadonly)
      if (!operable) return { operable: false, rendered: true, disabled: true, tooltip: pickTip(state) }
    }
    return { operable: true, rendered: true, disabled: false, tooltip: '' }
  }

  // 覆盖入口
  if (coverage) {
    const baseCanWrite = queryOk && canEdit && !isArchived
    const operable = baseCanWrite && (!lockConstrained || !forcedReadonly)
    if (!operable) return { operable: false, rendered: true, disabled: true, tooltip: pickTip(state) }
    return { operable: true, rendered: true, disabled: false, tooltip: '' }
  }

  // 非覆盖、非 eqcrHidden：always operable when rendered
  return { operable: true, rendered: true, disabled: false, tooltip: '' }
}

function pickTip(state: NoteEditState): string {
  if (state.queryStatus === 'pending') return '正在确认编辑权限…'
  if (state.queryStatus === 'failed') return '无法确认编辑权限'
  if (state.queryStatus === 'ok' && !state.canEdit && state.reason) return state.reason
  if (state.isArchived) return '项目已归档，无法编辑'
  if (state.forcedReadonly) return '他人正在编辑，当前为只读'
  return ''
}

// ── Property test ───────────────────────────────────────────────────────────

describe('Property 14: 编辑器呈现等于模型', () => {
  it('presentEntry result matches reference model for all inputs', () => {
    fc.assert(
      fc.property(stateArb, entryArb, (state, entry) => {
        const actual = presentEntry(state, entry)
        const expected = model(state, entry)
        expect(actual.operable).toBe(expected.operable)
        expect(actual.rendered).toBe(expected.rendered)
        expect(actual.disabled).toBe(expected.disabled)
        expect(actual.tooltip).toBe(expected.tooltip)
      }),
      { numRuns: 5 },
    )
  })

  // ── Fixed samples (design §8.3) ─────────────────────────────────────

  // P / Q 项目样例：EQCR 项目显示标识，非 EQCR 项目不显示
  it('EQCR project (P): write entry hidden or disabled, badge shown', () => {
    const eqcrState: NoteEditState = {
      queryStatus: 'ok', canEdit: false, reason: '独立复核合伙人（EQCR）在本项目只读',
      isEqcr: true, isArchived: false, forcedReadonly: false,
    }
    const saveEntry = WRITE_ENTRIES.find(e => e.id === 'save')!
    const result = presentEntry(eqcrState, saveEntry)
    expect(result.operable).toBe(false)
    expect(result.disabled).toBe(true)
  })

  it('non-EQCR project (Q): write entry enabled, no badge', () => {
    const editableState: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const saveEntry = WRITE_ENTRIES.find(e => e.id === 'save')!
    const result = presentEntry(editableState, saveEntry)
    expect(result.operable).toBe(true)
    expect(result.disabled).toBe(false)
  })

  // 五种身份
  it('edit member (identity ①): entry operable', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'save')!
    expect(presentEntry(state, entry).operable).toBe(true)
  })

  it('review non-EQCR member (identity ②): entry operable', () => {
    // Review + non-EQCR → canEdit = true from backend
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'validate')!
    expect(presentEntry(state, entry).operable).toBe(true)
  })

  it('readonly member (identity ③): entry disabled', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: false, reason: '权限不足',
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'save')!
    const r = presentEntry(state, entry)
    expect(r.operable).toBe(false)
    expect(r.disabled).toBe(true)
    expect(r.tooltip).toBe('权限不足')
  })

  it('non-member (identity ④): entry disabled', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: false, reason: '权限不足',
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'offline-import')!
    const r = presentEntry(state, entry)
    expect(r.operable).toBe(false)
    expect(r.disabled).toBe(true)
  })

  it('EQCR member (identity ⑤): entry disabled', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: false, reason: '独立复核合伙人（EQCR）在本项目只读',
      isEqcr: true, isArchived: false, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'save')!
    const r = presentEntry(state, entry)
    expect(r.operable).toBe(false)
    expect(r.disabled).toBe(true)
  })

  // pending / failed
  it('pending: entry disabled with pending message', () => {
    const state: NoteEditState = {
      queryStatus: 'pending', canEdit: false, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'save')!
    const r = presentEntry(state, entry)
    expect(r.operable).toBe(false)
    expect(r.tooltip).toBe('正在确认编辑权限…')
  })

  it('failed: entry disabled with failure message', () => {
    const state: NoteEditState = {
      queryStatus: 'failed', canEdit: false, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'save')!
    const r = presentEntry(state, entry)
    expect(r.operable).toBe(false)
    expect(r.tooltip).toBe('无法确认编辑权限')
  })

  // archived
  it('archived project: entry disabled even if canEdit', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null,
      isEqcr: false, isArchived: true, forcedReadonly: false,
    }
    const entry = WRITE_ENTRIES.find(e => e.id === 'save')!
    const r = presentEntry(state, entry)
    expect(r.operable).toBe(false)
    expect(r.tooltip).toBe('项目已归档，无法编辑')
  })

  // multi-window lock
  it('forcedReadonly: lock-constrained entry disabled', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: true,
    }
    const lockEntry = WRITE_ENTRIES.find(e => e.id === 'save')!
    expect(lockEntry.lockConstrained).toBe(true)
    const r = presentEntry(state, lockEntry)
    expect(r.operable).toBe(false)
    expect(r.tooltip).toBe('他人正在编辑，当前为只读')
  })

  it('forcedReadonly: non-lock-constrained entry still operable', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: true,
    }
    const nonLockEntry = WRITE_ENTRIES.find(e => e.id === 'validate')!
    expect(nonLockEntry.lockConstrained).toBe(false)
    const r = presentEntry(state, nonLockEntry)
    expect(r.operable).toBe(true)
  })

  // EQCR-hidden entries
  it('EQCR-hidden entry: not rendered when EQCR', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: false, reason: 'EQCR',
      isEqcr: true, isArchived: false, forcedReadonly: false,
    }
    const hiddenEntry = WRITE_ENTRIES.find(e => e.eqcrHidden)!
    const r = presentEntry(state, hiddenEntry)
    expect(r.rendered).toBe(false)
  })

  it('EQCR-hidden entry: not rendered when pending (treated as EQCR)', () => {
    const state: NoteEditState = {
      queryStatus: 'pending', canEdit: false, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const hiddenEntry = WRITE_ENTRIES.find(e => e.eqcrHidden)!
    const r = presentEntry(state, hiddenEntry)
    expect(r.rendered).toBe(false)
  })

  it('EQCR-hidden entry: rendered and operable for non-EQCR editable user', () => {
    const state: NoteEditState = {
      queryStatus: 'ok', canEdit: true, reason: null,
      isEqcr: false, isArchived: false, forcedReadonly: false,
    }
    const hiddenEntry = WRITE_ENTRIES.find(e => e.eqcrHidden && e.coverage)!
    const r = presentEntry(state, hiddenEntry)
    expect(r.rendered).toBe(true)
    expect(r.operable).toBe(true)
  })
})
