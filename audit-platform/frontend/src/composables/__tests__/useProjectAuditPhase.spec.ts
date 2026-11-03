/**
 * 项目当前审计阶段（spec voucher-identity-writeback-and-audit-phase 任务 8，需求 6.1 / 6.2）
 *
 * - 读：按项目缓存一份，同一项目并发读只发一次请求，静默请求（调用方自己提示）；
 * - 改：PUT 体为 current_audit_phase / interim_cutoff_date，成功后就地更新缓存 —— 另一个消费方同时看到新阶段；
 * - 失败原因：403 只有经理 / 合伙人可改、423 归档只读、422 带业务说明的原样给、其他兜底；
 * - 「年审（预审截止 2025-09-30）」显示文本；
 * - 设置区块：载入后显示当前阶段，不能改时整块禁用，保存发 PUT。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', async (orig) => {
  const mod = await orig<typeof import('element-plus')>()
  return { ...mod, ElMessage: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }
})

import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import {
  __resetProjectAuditPhaseCache,
  auditPhaseSaveFailureReason,
  auditPhaseText,
  fetchProjectAuditPhase,
  useProjectAuditPhase,
} from '../useProjectAuditPhase'
import ProjectAuditPhaseSection from '@/components/project/ProjectAuditPhaseSection.vue'

const get = http.get as unknown as ReturnType<typeof vi.fn>
const put = http.put as unknown as ReturnType<typeof vi.fn>
const wire = (over: Record<string, unknown> = {}) => ({
  data: {
    current_audit_phase: 'final', interim_cutoff_date: null,
    audit_period_start: '2025-01-01', audit_period_end: '2025-12-31', can_edit: true, ...over,
  },
})

beforeEach(() => {
  get.mockReset()
  put.mockReset()
  ;(ElMessage.success as any).mockReset?.()
  ;(ElMessage.error as any).mockReset?.()
  __resetProjectAuditPhaseCache()
})

describe('读取与缓存', () => {
  it('同一项目并发读只发一次，静默请求，结果映射成前端字段', async () => {
    get.mockResolvedValue(wire({ current_audit_phase: 'preliminary', interim_cutoff_date: '2025-09-30' }))
    const [a, b] = await Promise.all([fetchProjectAuditPhase('p-1'), fetchProjectAuditPhase('p-1')])
    expect(get).toHaveBeenCalledTimes(1)
    expect(get.mock.calls[0][0]).toBe('/api/projects/p-1/audit-phase')
    expect(get.mock.calls[0][1]).toMatchObject({ _silent: true })
    expect(a).toEqual({ phase: 'preliminary', interimCutoffDate: '2025-09-30', auditPeriodStart: '2025-01-01',
      auditPeriodEnd: '2025-12-31', canEdit: true })
    expect(b).toBe(a)
    await fetchProjectAuditPhase('p-1')
    expect(get).toHaveBeenCalledTimes(1)
    await fetchProjectAuditPhase('p-1', true)
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('未知阶段值按年审', async () => {
    get.mockResolvedValue(wire({ current_audit_phase: 'weird' }))
    expect((await fetchProjectAuditPhase('p-2')).phase).toBe('final')
  })
})

describe('保存', () => {
  it('PUT 体与静默；成功后另一个消费方立即看到新阶段', async () => {
    get.mockResolvedValue(wire())
    const a = useProjectAuditPhase('p-1')
    const b = useProjectAuditPhase(() => 'p-1')
    await a.load()
    expect(b.phase.value).toBe('final')
    put.mockResolvedValueOnce(wire({ current_audit_phase: 'preliminary', interim_cutoff_date: '2025-09-30', changed: true }))
    const changed = await a.save({ phase: 'preliminary', interimCutoffDate: '2025-09-30' })
    expect(changed).toBe(true)
    expect(put.mock.calls[0][0]).toBe('/api/projects/p-1/audit-phase')
    expect(put.mock.calls[0][1]).toEqual({ current_audit_phase: 'preliminary', interim_cutoff_date: '2025-09-30' })
    expect(put.mock.calls[0][2]).toMatchObject({ _silent: true })
    expect(b.phase.value).toBe('preliminary')
    expect(b.text.value).toBe('预审（预审截止 2025-09-30）')
  })

  it('空截止日发 null；失败时缓存不变并抛出', async () => {
    get.mockResolvedValue(wire())
    const a = useProjectAuditPhase('p-3')
    await a.load()
    put.mockRejectedValueOnce({ response: { status: 403 } })
    await expect(a.save({ phase: 'preliminary', interimCutoffDate: '' })).rejects.toBeTruthy()
    expect(put.mock.calls[0][1]).toEqual({ current_audit_phase: 'preliminary', interim_cutoff_date: null })
    expect(a.phase.value).toBe('final')
  })
})

describe('失败原因与显示文本', () => {
  it('按状态码给中文原因', () => {
    expect(auditPhaseSaveFailureReason({ response: { status: 403 } })).toContain('项目经理、合伙人')
    expect(auditPhaseSaveFailureReason({ response: { status: 423 } })).toContain('归档')
    expect(auditPhaseSaveFailureReason({ response: { status: 422, data: { detail: {
      error_code: 'INTERIM_CUTOFF_OUT_OF_PERIOD', message: '预审截止日须早于审计期间结束日 2025-12-31' } } } }))
      .toBe('预审截止日须早于审计期间结束日 2025-12-31')
    expect(auditPhaseSaveFailureReason({ response: { status: 422, data: { detail: [{ msg: 'x' }] } } }))
      .toBe('审计阶段只能是预审或年审')
    expect(auditPhaseSaveFailureReason(new Error('x'))).toBe('保存失败，请稍后重试')
  })

  it('显示文本', () => {
    expect(auditPhaseText(null)).toBe('年审')
    expect(auditPhaseText({ phase: 'final', interimCutoffDate: '2025-09-30' })).toBe('年审（预审截止 2025-09-30）')
    expect(auditPhaseText({ phase: 'preliminary', interimCutoffDate: null })).toBe('预审')
  })
})

describe('设置区块', () => {
  const mountSection = (props: Record<string, unknown> = {}) =>
    mount(ProjectAuditPhaseSection, { props: { projectId: 'p-9', ...props }, global: { plugins: [ElementPlus] } })

  it('载入当前阶段；能改时保存发 PUT', async () => {
    get.mockResolvedValue(wire({ current_audit_phase: 'final', interim_cutoff_date: '2025-06-30' }))
    const w = mountSection()
    await flushPromises()
    const radios = w.findAll('input[type="radio"]')
    expect((radios.find((r) => (r.element as HTMLInputElement).value === 'final')!.element as HTMLInputElement)
      .checked).toBe(true)
    const save = w.findAll('button').find((b) => b.text().includes('保存审计阶段'))!
    expect(save.attributes('disabled')).toBeDefined()  // 没改动不能保存
    await radios.find((r) => (r.element as HTMLInputElement).value === 'preliminary')!.setValue(true)
    put.mockResolvedValueOnce(wire({ current_audit_phase: 'preliminary', interim_cutoff_date: '2025-06-30', changed: true }))
    await save.trigger('click')
    await flushPromises()
    expect(put).toHaveBeenCalledTimes(1)
    expect(put.mock.calls[0][1]).toEqual({ current_audit_phase: 'preliminary', interim_cutoff_date: '2025-06-30' })
    expect(ElMessage.success).toHaveBeenCalledWith('审计阶段已保存')
  })

  it('不能改时整块禁用并说明谁能改', async () => {
    get.mockResolvedValue(wire({ can_edit: false }))
    const w = mountSection()
    await flushPromises()
    expect(w.findAll('input[type="radio"]').every((r) => (r.element as HTMLInputElement).disabled)).toBe(true)
    expect(w.text()).toContain('只有项目经理、合伙人（含签字合伙人）可以修改审计阶段')
  })

  it('项目只读（签发 / 归档）时即使有权限也禁用', async () => {
    get.mockResolvedValue(wire({ can_edit: true }))
    const w = mountSection({ readonly: true })
    await flushPromises()
    expect(w.findAll('input[type="radio"]').every((r) => (r.element as HTMLInputElement).disabled)).toBe(true)
  })
})
