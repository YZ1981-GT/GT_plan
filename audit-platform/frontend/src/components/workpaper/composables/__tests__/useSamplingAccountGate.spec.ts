/**
 * `useSamplingAccountGate` 单测 —— spec `voucher-sampling-account-scope-and-attach-closure`
 * Requirement 2（宁缺勿造的降级），任务 4.1 / 4.2 / 4.3。
 *
 * 判据要点：
 * - 空科目 ⇒ 禁用 + 提示可操作下一步 + **不得发请求**
 * - 三态（absent / loading / readonly）必须可区分，不能都笼统显示"不可用"
 * - 有解析值时即使真源兜底为空串也应可用（空兜底只表达「无标准码」，非「本项目无数据」）
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, computed } from 'vue'

import { useSamplingAccountGate } from '../useSamplingAccountGate'

describe('useSamplingAccountGate — 科目码规范化', () => {
  it('数组去空去重保序', () => {
    const g = useSamplingAccountGate({
      codes: ['1001', '', '1002', '1001', '  1012  '],
      accountLabel: '货币资金',
    })
    expect(g.resolvedCodes.value).toEqual(['1001', '1002', '1012'])
    expect(g.accountCode.value).toBe('1001,1002,1012')
  })

  it('逗号字符串等价于数组（引擎侧会 split(\',\')）', () => {
    const g = useSamplingAccountGate({ codes: '1001,1002', accountLabel: 'X' })
    expect(g.resolvedCodes.value).toEqual(['1001', '1002'])
  })

  it('null / undefined / 空串 / 全空数组 一律判为无科目', () => {
    for (const codes of [null, undefined, '', [], ['', '  ']] as const) {
      const g = useSamplingAccountGate({ codes: codes as never, accountLabel: 'X' })
      expect(g.isAccountAbsent.value, `codes=${JSON.stringify(codes)}`).toBe(true)
      expect(g.accountCode.value).toBe('')
    }
  })
})

describe('useSamplingAccountGate — 三态可区分（R2.4）', () => {
  it('ready：有科目、非只读、非加载', () => {
    const g = useSamplingAccountGate({
      codes: ['2801'], accountLabel: '预计负债',
      isReadonly: false, isLoading: false,
    })
    expect(g.state.value).toBe('ready')
    expect(g.disabled.value).toBe(false)
    expect(g.canSample.value).toBe(true)
    expect(g.disabledReason.value).toBe('')
  })

  it('absent：无科目 ⇒ 禁用且提示含底稿名与可操作下一步', () => {
    const g = useSamplingAccountGate({ codes: [], accountLabel: '其他非流动资产' })
    expect(g.state.value).toBe('absent')
    expect(g.disabled.value).toBe(true)
    expect(g.isAccountAbsent.value).toBe(true)
    expect(g.disabledReason.value).toContain('其他非流动资产')
    // 可操作的下一步（不能只说"不可用"）
    expect(g.disabledReason.value).toMatch(/手工录入/)
    expect(g.disabledReason.value).toMatch(/报表配置/)
  })

  it('loading：加载中 ⇒ 禁用但**不**判为无科目', () => {
    const g = useSamplingAccountGate({ codes: [], accountLabel: 'X', isLoading: true })
    expect(g.state.value).toBe('loading')
    expect(g.disabled.value).toBe(true)
    expect(g.disabledReason.value).toMatch(/加载中/)
  })

  it('readonly 优先级最高（只读时不暴露"无科目"）', () => {
    const g = useSamplingAccountGate({
      codes: [], accountLabel: 'X', isReadonly: true, isLoading: true,
    })
    expect(g.state.value).toBe('readonly')
    expect(g.disabledReason.value).toMatch(/只读/)
  })

  it('🔴 三态的 disabledReason 互不相同（否则用户无法区分）', () => {
    const reasons = new Set(
      [
        useSamplingAccountGate({ codes: [], accountLabel: 'X' }),
        useSamplingAccountGate({ codes: [], accountLabel: 'X', isLoading: true }),
        useSamplingAccountGate({ codes: [], accountLabel: 'X', isReadonly: true }),
      ].map((g) => g.disabledReason.value),
    )
    expect(reasons.size).toBe(3)
  })
})

describe('useSamplingAccountGate — R2.3 有解析值时可用（空兜底不等于无数据）', () => {
  it('真源兜底为空串，但 render 解析出码 ⇒ 仍可抽凭', () => {
    // 模拟 i5/k4：FALLBACK_STANDARD = ''，但 tbSourceCodes 解析出了项目自定义码
    const I5_FALLBACK = ''
    const tbSourceCodes = ref<{ gross_standard?: string[] } | null>({ gross_standard: ['1901.05'] })
    const g = useSamplingAccountGate({
      codes: computed(() => tbSourceCodes.value?.gross_standard ?? [I5_FALLBACK]),
      accountLabel: '其他非流动资产',
    })
    expect(g.state.value).toBe('ready')
    expect(g.canSample.value).toBe(true)
    expect(g.accountCode.value).toBe('1901.05')
  })

  it('真源兜底为空串且 render 未下发 ⇒ 降级 absent', () => {
    const I5_FALLBACK = ''
    const tbSourceCodes = ref<{ gross_standard?: string[] } | null>(null)
    const g = useSamplingAccountGate({
      codes: computed(() => tbSourceCodes.value?.gross_standard ?? [I5_FALLBACK]),
      accountLabel: '其他非流动资产',
    })
    expect(g.state.value).toBe('absent')
    expect(g.canSample.value).toBe(false)
  })

  it('响应式：解析结果到达后自动从 absent 转 ready', () => {
    const codes = ref<string[]>([])
    const g = useSamplingAccountGate({ codes, accountLabel: 'X' })
    expect(g.state.value).toBe('absent')
    codes.value = ['1704']
    expect(g.state.value).toBe('ready')
    expect(g.accountCode.value).toBe('1704')
  })
})

describe('useSamplingAccountGate — R2.2 空科目不得发起请求', () => {
  /** 模拟宿主的"打开抽凭"动作：必须先查 canSample 再发请求 */
  function openSampling(gate: ReturnType<typeof useSamplingAccountGate>, http: { post: ReturnType<typeof vi.fn> }) {
    if (!gate.canSample.value) return { requested: false, reason: gate.disabledReason.value }
    http.post('/voucher-extract', { account_codes: gate.resolvedCodes.value })
    return { requested: true, reason: '' }
  }

  it('无科目 ⇒ 零请求，且返回可读原因', () => {
    const http = { post: vi.fn() }
    const g = useSamplingAccountGate({ codes: [], accountLabel: '其他流动负债' })
    const r = openSampling(g, http)
    expect(http.post).not.toHaveBeenCalled()
    expect(r.requested).toBe(false)
    expect(r.reason).toContain('其他流动负债')
  })

  it('有科目 ⇒ 发请求且 account_codes 为规范化后的码集', () => {
    const http = { post: vi.fn() }
    const g = useSamplingAccountGate({ codes: ['1704', ''], accountLabel: '开发支出' })
    const r = openSampling(g, http)
    expect(r.requested).toBe(true)
    expect(http.post).toHaveBeenCalledWith('/voucher-extract', { account_codes: ['1704'] })
  })

  it('🔴 只读/加载中同样不得发请求（绕过 UI 的程序化调用也要挡住）', () => {
    for (const opts of [
      { codes: ['1704'], accountLabel: 'X', isReadonly: true },
      { codes: ['1704'], accountLabel: 'X', isLoading: true },
    ]) {
      const http = { post: vi.fn() }
      const g = useSamplingAccountGate(opts as never)
      openSampling(g, http)
      expect(http.post, JSON.stringify(opts)).not.toHaveBeenCalled()
    }
  })
})
