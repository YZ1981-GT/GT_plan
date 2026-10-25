/**
 * 公式管理「公式推送」面板（spec chain-closure-phase2-formula-push-engine 任务 14 · 需求 1.4 / 3.4）
 *
 * 真挂载组件（mock 只替换 apiProxy 网络层）：规则表 / 最近推送 / 待处理差异 / 立即推送 / 试跑 /
 * 采用公式值 / 锁定 的请求形状与全中文展示。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const calls: Array<{ method: string; url: string; body?: any; params?: any }> = []
const responses: Record<string, any> = {}

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(async (url: string, cfg?: any) => {
      calls.push({ method: 'get', url, params: cfg?.params })
      return responses[`get ${url.split('/').pop()}`]
    }),
    post: vi.fn(async (url: string, body?: any) => {
      calls.push({ method: 'post', url, body })
      return responses[`post ${url.split('/').slice(-2).join('/')}`] ?? { written_count: 3, kept_count: 1 }
    }),
  },
}))

import FormulaPushPanel from '../FormulaPushPanel.vue'
import { actionable, pendingStates, runStatusTag, targetText, triggersText, valueText } from '../formulaPushView'

const RULE = {
  rule_id: 'E1.tb_amount.ending', stage: 'source', policy: 'system', triggers: ['TRIAL_BALANCE_UPDATED', 'manual'],
  description: '试算平衡表数（期末）= 试算表审定数', formula: "TB('1001','期末余额')+TB('1002','期末余额')",
  target: { domain: 'workpaper', sheet_code: 'E1-1', item_id: 'E1-adj-tb-amount-ending' },
}
const PENDING = {
  addr_id: 'E1/E1-2/E1-cash-detail-rows[fixed-rmb].opening', rule_id: 'E1.cash_rows.four_table',
  domain: 'workpaper', state: 'pending_confirm', current_value: 200, formula_value: 286.73, differs: true,
  updated_at: '2026-09-29T10:00:00+00:00',
}
const NOTE_KEPT = { ...PENDING, addr_id: 'note://五、1/货币资金/银行存款.end', domain: 'note', state: 'manual' }

beforeEach(() => {
  calls.length = 0
  responses['get rules'] = { rules: [RULE] }
  responses['get latest'] = {
    run: { run_id: 'r1', trigger: 'TRIAL_BALANCE_UPDATED', status: 'succeeded', written_count: 20, unchanged_count: 11,
      kept_count: 2, skipped_count: 4, started_at: 'x', finished_at: 'y', detail: { warnings: ['试算表含多个公司编码'] } },
    state_counts: { pending_confirm: 1 },
  }
  responses['get states'] = { states: [PENDING, NOTE_KEPT, { ...PENDING, addr_id: 'E1/a', state: 'auto', differs: false }] }
})

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(FormulaPushPanel, {
    props: { projectId: 'p1', year: 2025, wpCode: 'E1', ...props },
    global: { plugins: [ElementPlus] },
  })
}

describe('展示逻辑（纯函数）', () => {
  it('待处理差异 = 非自动且有差异；附注目标不可在面板操作', () => {
    const list = pendingStates([PENDING, NOTE_KEPT, { ...PENDING, state: 'auto' }, { ...PENDING, differs: false }])
    expect(list).toEqual([PENDING, NOTE_KEPT])
    expect(actionable(PENDING)).toBe(true)
    expect(actionable(NOTE_KEPT)).toBe(false)
  })

  it('中文标签与数值格式', () => {
    expect(triggersText(['TRIAL_BALANCE_UPDATED', 'WORKPAPER_SAVED', 'manual'])).toBe('试算表更新、底稿保存、手动')
    expect(targetText(RULE as any)).toBe('底稿 E1-1 E1-adj-tb-amount-ending')
    expect(targetText({ ...RULE, target: { domain: 'note', sections: { listed: '五、1', soe: '八、1' } } } as any))
      .toBe('附注 上市 五、1 / 国企 八、1')
    expect(valueText(286.73)).toBe('286.73')
    expect(valueText('1234567')).toBe('1,234,567.00')
    expect(valueText(null)).toBe('（空）')
    expect(valueText('')).toBe('（空）')
    expect([runStatusTag('succeeded'), runStatusTag('partial'), runStatusTag('failed'), runStatusTag(null)])
      .toEqual(['success', 'warning', 'danger', 'info'])
  })
})

describe('面板（真挂载）', () => {
  it('加载规则 / 最近推送 / 状态，全中文展示', async () => {
    const w = mountPanel()
    await flushPromises()
    const gets = calls.filter((c) => c.method === 'get').map((c) => c.url)
    expect(gets).toEqual([
      '/api/projects/p1/formula-push/rules', '/api/projects/p1/formula-push/latest', '/api/projects/p1/formula-push/states',
    ])
    expect(calls[0].params).toEqual({ wp_code: 'E1' })
    expect(calls[1].params).toEqual({ year: 2025, wp_code: 'E1' })
    expect(calls[2].params).toEqual({ year: 2025, wp_code: 'E1' })
    const text = w.text()
    for (const s of ['公式推送 · E1', '最近一次推送', '成功', '触发：试算表更新', '写入 20', '待处理差异（2）',
      '待确认', '人工修改', '在附注模块中处理', '推送规则（1）', '系统值（总是跟随公式）', '试算表含多个公司编码']) {
      expect(text, s).toContain(s)
    }
  })

  it('立即推送 / 试跑：请求体带 year 与 dry_run；试跑不刷新、只展示将写入', async () => {
    const w = mountPanel()
    await flushPromises()
    calls.length = 0
    responses['post formula-push/run'] = {
      written_count: 26, unchanged_count: 9, kept_count: 2, skipped_count: 5, dry_run: true, warnings: [],
    }
    await w.findAll('button').find((b) => b.text().includes('试跑'))!.trigger('click')
    await flushPromises()
    expect(calls).toEqual([{ method: 'post', url: '/api/projects/p1/formula-push/run', body: { year: 2025, dry_run: true, wp_codes: ['E1'] } }])
    // 四类计数与「最近一次推送」同口径（含未变化）；字段缺失按 0 显示而非 undefined
    expect(w.text()).toContain('试跑结果：将写入 26 项，未变化 9 项，保留 2 项，跳过 5 项（未写入任何数据）')
    calls.length = 0
    responses['post formula-push/run'] = { written_count: 3, kept_count: 1 }
    await w.findAll('button').find((b) => b.text().includes('立即推送'))!.trigger('click')
    await flushPromises()
    expect(calls[0]).toEqual({ method: 'post', url: '/api/projects/p1/formula-push/run', body: { year: 2025, dry_run: false, wp_codes: ['E1'] } })
    expect(calls.slice(1).every((c) => c.method === 'get')).toBe(true)
  })

  it('采用公式值（确认后）与锁定：地址与 year 正确', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const w = mountPanel()
    await flushPromises()
    calls.length = 0
    await w.findAll('button').find((b) => b.text() === '采用公式值')!.trigger('click')
    await flushPromises()
    expect(calls[0]).toEqual({
      method: 'post', url: '/api/projects/p1/formula-push/states/adopt', body: { year: 2025, addr_ids: [PENDING.addr_id] },
    })
    calls.length = 0
    await w.findAll('button').find((b) => b.text() === '保持并锁定')!.trigger('click')
    await flushPromises()
    expect(calls[0]).toEqual({
      method: 'post', url: '/api/projects/p1/formula-push/states/lock',
      body: { year: 2025, addr_ids: [PENDING.addr_id], locked: true },
    })
  })

  it('空列表：两张表的空态是中文（不依赖全局语言包，挂载未配 locale 时也不出现 No Data）', async () => {
    responses['get rules'] = { rules: [] }
    responses['get latest'] = { run: null, state_counts: {} }
    responses['get states'] = { states: [] }
    const w = mountPanel()
    await flushPromises()
    const text = w.text()
    for (const s of ['本年度尚未推送过', '待处理差异（0）', '暂无待处理差异', '推送规则（0）', '暂无推送规则']) {
      expect(text, s).toContain(s)
    }
    expect(text).not.toContain('No Data')
  })

  it('加载中显示遮罩（慢请求期间不让「推送规则（0）」看起来像真的没有规则）', async () => {
    let release!: (v: unknown) => void
    responses['get rules'] = new Promise((r) => { release = r })
    const w = mountPanel()
    await flushPromises()
    expect(w.find('.el-loading-mask').exists()).toBe(true)
    release({ rules: [RULE] })
    await flushPromises()
    expect(w.text()).toContain('推送规则（1）')
  })

  it('无编辑权：写操作按钮置灰', async () => {
    const w = mountPanel({ canEdit: false })
    await flushPromises()
    const btn = (t: string) => w.findAll('button').find((b) => b.text().includes(t))!
    expect(btn('立即推送').attributes('disabled')).toBeDefined()
    expect(btn('试跑').attributes('disabled')).toBeDefined()
  })
})

describe('公式管理弹窗接线（源码级）', () => {
  const src = readFileSync(resolve(__dirname, '../FormulaManagerDialog.vue'), 'utf-8')

  it('「公式推送」页对所有底稿显示（含未接入说明），且主公式表在该页隐藏', () => {
    expect(src).not.toContain('PUSH_WP_CODES')
    expect(src).toContain('formulaPush.bindings(props.projectId)')
    expect(src).toMatch(/<el-tab-pane v-if="projectId && year" name="formula_push">/)
    expect(src).toContain("['user_formulas', 'history', 'formula_push'].includes(activeCategory)")
    expect(src).toContain('<FormulaPushPanel')
    // 未接入底稿的说明
    expect(src).toContain('本底稿尚未接入自动推送')
  })
})


describe('按科目隔离（Task 10）', () => {
  it('latest 和 states 的请求都带 wp_code 参数', async () => {
    mountPanel()
    await flushPromises()
    const latestCall = calls.find((c) => c.url.includes('/latest'))
    const statesCall = calls.find((c) => c.url.includes('/states'))
    expect(latestCall?.params).toEqual({ year: 2025, wp_code: 'E1' })
    expect(statesCall?.params).toEqual({ year: 2025, wp_code: 'E1' })
  })

  it('立即推送请求体带 wp_codes', async () => {
    const w = mountPanel()
    await flushPromises()
    calls.length = 0
    await w.findAll('button').find((b) => b.text().includes('立即推送'))!.trigger('click')
    await flushPromises()
    const runCall = calls.find((c) => c.method === 'post' && c.url.includes('/run'))
    expect(runCall?.body).toEqual({ year: 2025, dry_run: false, wp_codes: ['E1'] })
  })

  it('全部推送按钮在多 binding 时可见', async () => {
    const w = mount(FormulaPushPanel, {
      props: { projectId: 'p1', year: 2025, wpCode: 'E1', supportedWpCodes: ['E1', 'K1'] },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    const allBtn = w.findAll('button').find((b) => b.text().includes('全部推送'))
    expect(allBtn).toBeDefined()
  })

  it('全部推送按钮在单 binding 时隐藏', async () => {
    const w = mount(FormulaPushPanel, {
      props: { projectId: 'p1', year: 2025, wpCode: 'E1', supportedWpCodes: ['E1'] },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    const allBtn = w.findAll('button').find((b) => b.text().includes('全部推送'))
    expect(allBtn).toBeUndefined()
  })

  it('全部推送请求体不带 wp_codes（= 后端全量推送语义）', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as any)
    const w = mount(FormulaPushPanel, {
      props: { projectId: 'p1', year: 2025, wpCode: 'E1', supportedWpCodes: ['E1', 'K1'] },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    calls.length = 0
    const allBtn = w.findAll('button').find((b) => b.text().includes('全部推送'))!
    await allBtn.trigger('click')
    await flushPromises()
    const runCall = calls.find((c) => c.method === 'post' && c.url.includes('/run'))
    expect(runCall?.body).toEqual({ year: 2025, dry_run: false })
  })
})
