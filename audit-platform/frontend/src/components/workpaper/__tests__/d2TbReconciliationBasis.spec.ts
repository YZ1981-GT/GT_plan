/**
 * D2 对账口径 —— spec writeback-followup-issue-closure R11.2（重药安徽 D2 对账差异）。
 *
 * 锚点 `D2-adj-tb-amount` 自 2026-08-01 起是**净额**（TB('1122') − TB('1231-02')），读者没跟着改：
 * 1. D2-1「试算平衡表差异」拿**原值**合计去比净额锚点 ⇒ 差异恰好等于坏账准备；
 * 2. D2-2↔TB 横幅拿 D2-2（原值）去比净额锚点、却标「TB科目1122审定额」（重药安徽差 26,901,719.77）；
 * 3. `loadAll` 的回退种子无条件用试算表原值覆盖内存里的净额锚点（在线编辑回写后重载即触发）；
 * 4. 「从余额表导入」超上限静默截断（重药安徽 1260 户只导入 500 户），回执报成成功。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, effectScope, h, nextTick, provide, ref, type Ref } from 'vue'

const { apiGet, httpPost, message } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  httpPost: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: apiGet, post: vi.fn(), put: vi.fn(async () => ({})), patch: vi.fn(), delete: vi.fn() },
}))
vi.mock('@/utils/http', () => ({ default: { post: httpPost, get: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: message,
  ElMessageBox: { confirm: vi.fn(async () => 'confirm') },
}))
vi.mock('@/composables/useAgingConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useAgingConfig')>()
  return { ...actual, useAgingConfig: () => ({ segments: ref([]), bands: ref([]) }) }
})

const { useD2Adjudication } = await import('../composables/useD2Adjudication')
const { useD2CrossSheet } = await import('../composables/useD2CrossSheet')
const { useD2FormData, d2NetTbSeed, pickTbAudited } = await import('../composables/useD2FormData')
const { useD2Detail } = await import('../composables/useD2Detail')
const { D2_SAVE_ITEMS_KEY } = await import('../composables/d2InjectionKeys')
const { parseAuxImportResponse, auxImportPrompt } = await import('../composables/fourTableAuxImportFeedback')

type Resp = { item_id: string; conclusion: string | null; remark: string | null }

function responses(entries: Record<string, string>): Ref<Map<string, Resp>> {
  const map = new Map<string, Resp>()
  for (const [itemId, remark] of Object.entries(entries)) map.set(itemId, { item_id: itemId, conclusion: null, remark })
  return ref(map)
}

const PROVISION_100 = JSON.stringify([{ rowId: 'bd-fixed', isFixed: true, priorAudited: 0, currentAudited: 100 }])

beforeEach(() => {
  apiGet.mockReset()
  httpPost.mockReset()
  for (const fn of Object.values(message)) fn.mockReset()
})

// ═══════════════════════════════════════════════════════════════════════════
describe('D2-1 试算平衡表差异：净值对净额锚点', () => {
  function run(map: Ref<Map<string, Resp>>) {
    const scope = effectScope()
    const api = scope.run(() =>
      useD2Adjudication({ wpId: ref('wp-1'), projectId: ref('proj-1'), allResponses: map as never, isReadonly: ref(false) }),
    )!
    return { api, stop: () => scope.stop() }
  }

  it('原值 1000 − 坏账准备 100 = 净值 900，与净额锚点 900 相符', () => {
    const { api, stop } = run(responses({
      'D2-adj-individual-current-unadjusted': '1000',
      'D2-bd-individual-rows': PROVISION_100,
      'D2-adj-tb-amount': '900',
    }))
    try {
      expect(api.totalRow.value.currentAudited).toBe(1000)
      expect(api.provisionTotalAudited.value).toBe(100)
      expect(api.netTotalAudited.value).toBe(900)
      expect(api.trialBalanceDiff.value).toEqual({ amount: 0, isZero: true })
    } finally {
      stop()
    }
  })

  it('真不符时仍报差异（不是把差异抹掉）', () => {
    const { api, stop } = run(responses({
      'D2-adj-individual-current-unadjusted': '1000',
      'D2-bd-individual-rows': PROVISION_100,
      'D2-adj-tb-amount': '950',
    }))
    try {
      expect(api.trialBalanceDiff.value.amount).toBe(-50)
      expect(api.trialBalanceDiff.value.isZero).toBe(false)
    } finally {
      stop()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('D2-2↔TB 横幅：原值对 1122 原值审定额', () => {
  const DETAIL = JSON.stringify([
    { rowId: 'r1', customerName: '甲', currentAudited: 600 },
    { rowId: 'r2', customerName: '乙', currentAudited: 400 },
  ])

  function run(tbGross: number | null) {
    const scope = effectScope()
    const api = scope.run(() =>
      useD2CrossSheet({
        allResponses: responses({ 'D2-detail-rows': DETAIL, 'D2-adj-tb-amount': '900' }) as never,
        tbGrossAmount: ref(tbGross),
      }),
    )!
    return { api, stop: () => scope.stop() }
  }

  it('明细 1000 与 1122 原值 1000 相符 —— 净额锚点 900 不参与', () => {
    const { api, stop } = run(1000)
    try {
      expect(api.detailVsTbDiff.value).toEqual({ diff: 0, isBalanced: true, detailTotal: 1000, tbAmount: 1000 })
    } finally {
      stop()
    }
  })

  it('原值审定额没取到 ⇒ 不出横幅（不拿净额锚点冒充）', () => {
    const { api, stop } = run(null)
    try {
      expect(api.detailVsTbDiff.value).toBeNull()
    } finally {
      stop()
    }
  })

  it('真差异照报', () => {
    const { api, stop } = run(1100)
    try {
      expect(api.detailVsTbDiff.value).toMatchObject({ diff: -100, isBalanced: false, tbAmount: 1100 })
    } finally {
      stop()
    }
  })

  it('宿主把 1122 原值审定额接进 useD2CrossSheet', () => {
    const host = readFileSync(resolve(__dirname, '../GtD2AccountsReceivable.vue'), 'utf-8')
    expect(host).toMatch(/tbGrossAmount:\s*computed\(\(\)\s*=>\s*formData\.tbReference\.value\.grossAudited\)/)
    expect(host).toMatch(/void formData\.loadTbReference\(\)/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('D2-1↔D2-2 横幅：点名不进入 D2-1 任何分类的行', () => {
  it('空的、不属于三类的都算；三类不算（与 SUMIF 同一判据）', () => {
    const scope = effectScope()
    const api = scope.run(() =>
      useD2CrossSheet({
        allResponses: responses({
          // D2-1 按类汇总的是未审 + AJE + RJE；这里只有未审，审定 = 未审
          'D2-detail-rows': JSON.stringify([
            ['a', '单项计提', 100],
            ['b', '', 200],
            ['c', '其他组合', 300],
            ['d', '账龄组合', 400],
            ['e', '客户类型组合', 500],
          ].map(([rowId, cls, amt]) => ({
            rowId, creditRiskClassification: cls, currentUnadjusted: amt, currentAudited: amt,
          }))),
        }) as never,
      }),
    )!
    try {
      expect(api.unclassifiedDetail.value).toEqual({ count: 2, totalAudited: 500 })
      // 与 D2-1 的差额恰是这两行
      expect(api.reconciliationDiff.value.diff).toBe(500)
    } finally {
      scope.stop()
    }
  })

  it('宿主在横幅里点名行数与金额', () => {
    const host = readFileSync(resolve(__dirname, '../GtD2AccountsReceivable.vue'), 'utf-8')
    expect(host).toMatch(/v-if="crossSheet\.unclassifiedDetail\.value\.count > 0"/)
    expect(host).toContain('{{ crossSheet.unclassifiedDetail.value.count }} 行未填「信用风险组合方式」')
    expect(host).toContain('fmtAmt(crossSheet.unclassifiedDetail.value.totalAudited)')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('锚点回退种子：不覆盖已有值、补的是净额', () => {
  const TB_ROWS = [
    { standard_account_code: '1122', audited_amount: 1000, unadjusted_amount: 1000 },
    { standard_account_code: '1231-02', audited_amount: 100, unadjusted_amount: 100 },
  ]

  function routeGets(persisted: Resp[]) {
    apiGet.mockImplementation(async (url: string) => {
      if (url.endsWith('/checklist-responses')) return persisted
      if (url.endsWith('/trial-balance')) return TB_ROWS
      if (url.startsWith('/api/projects/')) return { audit_year: 2025 }
      throw new Error(`unexpected GET ${url}`)
    })
  }

  it('纯函数：取审定额 / 净额 = 原值 − 坏账准备 / render 下发的净额优先', () => {
    expect(pickTbAudited(TB_ROWS, '1122')).toBe(1000)
    expect(pickTbAudited(TB_ROWS, '9999')).toBeNull()
    expect(d2NetTbSeed(undefined, { grossAudited: 1000, provisionAudited: 100 })).toBe(900)
    expect(d2NetTbSeed({ project_context: { tb_amount: 880 } }, { grossAudited: 1000, provisionAudited: 100 })).toBe(880)
    expect(d2NetTbSeed(undefined, { grossAudited: null, provisionAudited: 100 })).toBeNull()
  })

  it('库里已有锚点（手工 / 公式推送写入）⇒ 重载后原样保留，不被试算表回退值覆盖', async () => {
    // 已有值 880 与试算表算出的净额 900 不同 —— 相同就测不出「覆盖」
    routeGets([{ item_id: 'D2-adj-tb-amount', conclusion: null, remark: '880' }])
    const form = useD2FormData(ref('wp-1'), ref('proj-1'))
    await form.loadAll()
    expect(form.allResponses.value.get('D2-adj-tb-amount')?.remark).toBe('880')
    expect(form.tbReference.value).toEqual({ grossAudited: 1000, provisionAudited: 100 })
  })

  it('库里没有锚点 ⇒ 补净额 900，不是原值 1000', async () => {
    routeGets([])
    const form = useD2FormData(ref('wp-1'), ref('proj-1'))
    await form.loadAll()
    expect(form.allResponses.value.get('D2-adj-tb-amount')?.remark).toBe('900')
  })

  it('试算表与底稿数据并行取：底稿还没回来时试算表请求已经发出', async () => {
    let releaseChecklist!: (value: unknown) => void
    apiGet.mockImplementation((url: string) => {
      if (url.endsWith('/checklist-responses')) return new Promise((done) => { releaseChecklist = done })
      if (url.endsWith('/trial-balance')) return Promise.resolve(TB_ROWS)
      if (url.startsWith('/api/projects/')) return Promise.resolve({ audit_year: 2025 })
      return Promise.reject(new Error(`unexpected GET ${url}`))
    })
    const form = useD2FormData(ref('wp-1'), ref('proj-1'))
    const done = form.loadAll()
    await vi.waitFor(() => {
      expect(apiGet.mock.calls.some(([u]) => String(u).endsWith('/trial-balance'))).toBe(true)
    })
    releaseChecklist([])
    await done
    // loadAll 结束时参考数已经到位（D2-2↔TB 横幅不会晚一拍）
    expect(form.tbReference.value).toEqual({ grossAudited: 1000, provisionAudited: 100 })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('从余额表导入超上限：回执是警告，不是成功', () => {
  it('共享提示：截断 ⇒ warning（哪怕本次新增了行）', () => {
    const outcome = parseAuxImportResponse({
      data: { imported_count: 500, truncated: true, total_units: 1260, dropped_units: 760, warning: 'W', message: 'M+W' },
    })
    expect(outcome).toMatchObject({ truncated: true, totalUnits: 1260, droppedUnits: 760, warning: 'W' })
    expect(auxImportPrompt(outcome)).toEqual({ level: 'warning', text: 'M+W' })
    expect(auxImportPrompt(parseAuxImportResponse({ data: { imported_count: 3, message: 'ok' } })).level).toBe('success')
  })

  function mountDetail() {
    let api!: ReturnType<typeof useD2Detail>
    const Child = defineComponent({
      setup() {
        api = useD2Detail({
          wpId: ref('wp-1'),
          projectId: ref('proj-1'),
          allResponses: responses({ 'D2-detail-rows': '[]' }) as never,
          isReadonly: ref(false),
          relatedParties: ref([]),
        })
        return () => null
      },
    })
    const Parent = defineComponent({
      setup() {
        provide(D2_SAVE_ITEMS_KEY, (async () => undefined) as never)
        return () => h(Child)
      },
    })
    const wrapper = mount(Parent)
    return { wrapper, api: () => api }
  }

  it('D2-2：后端回 truncated ⇒ 常驻警告、返回 truncated，不弹成功', async () => {
    httpPost.mockResolvedValue({
      truncated: true,
      message: '归集 3001 个客户……其余 1 个未导入',
      rows: [{ customerName: '乙公司', priorUnadjusted: 5, debitOccurrence: 0, creditOccurrence: 0 }],
    })
    const { wrapper, api } = mountDetail()
    try {
      const result = await api().importFromAuxBalance('proj-1')
      await nextTick()
      expect(result).toMatchObject({ added: 1, truncated: true })
      expect(message.warning).toHaveBeenCalledTimes(1)
      expect(String(message.warning.mock.calls[0][0].message)).toContain('未导入')
      expect(message.success).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('D2-2 页面：截断时不再叠一条「导入完成」', () => {
    const tab = readFileSync(resolve(__dirname, '../d2/D2TabDetail.vue'), 'utf-8')
    expect(tab).toMatch(/if \(!result\.truncated\) ElMessage\.success\(`导入完成/)
  })
})
