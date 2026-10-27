/**
 * AcnrTargetResults.spec.ts — 单元格取值结果区与拒绝提示（acnr-foundation-defect-closure T16，需求 1.6 / 1.7）
 *
 * - 四种状态渲染：ok 显示值、text 显示原文、missing / blocked 显示「—」与原因（不显示空白或 0）。
 * - 下钻：有 `source.jump_route` 直接打开它（站内路由不带 noopener，追加 cell=）；没有才按 addr_id 经 ACNR 解析。
 * - 拒绝提示：后端真实 422 / 503 / 403 形状（生产信封 `{code, message: detail}` 经 http 拦截器同一个
 *   `normaliseErrorEnvelope` 补出 `detail`）→ 逐项中文原因可见，不出现英文。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const acnrMocks = vi.hoisted(() => ({ resolveIndex: vi.fn() }))
vi.mock('@/services/acnr/useAcnr', () => ({ useAcnr: () => acnrMocks }))

import AcnrTargetResults, { type AcnrResultsBlock } from '../AcnrTargetResults.vue'
import { queryErrorText } from '../queryPayloads'
import { normaliseErrorEnvelope } from '@/utils/http'

const src = (sheet: string, cell: string, jump: string | null) => ({
  wp_code: 'E1', sheet_code: sheet, sheet_key: sheet, cell, wp_id: jump ? 'w1' : null, jump_route: jump,
})
const BLOCK: AcnrResultsBlock = {
  registry_version: '20261027161822', year: 2025,
  items: [
    { input: 'E1/E1-18/B20', addr_id: 'E1/E1-18/B20', display_label: '底稿 > E1 > 企业信用报告信息查询记录E1-18 › B20',
      formula_ref: "WP('E1','企业信用报告信息查询记录E1-18','B20')", state: 'ok', value: '11', text: '11',
      reason_code: null, reason: null, source: src('E1-18', 'B20', '/projects/p1/workpapers/w1/edit?sheet=E1-18') },
    { input: 'E1/E1-14/B30', addr_id: 'E1/E1-14/B30', display_label: '结论', formula_ref: "WP('E1','货币资金分析表E1-14','B30')",
      state: 'text', value: null, text: '结论文本', reason_code: 'non_numeric', reason: '单元格是文本', source: src('E1-14', 'B30', null) },
    { input: 'E1/E1-15/B25', addr_id: 'E1/E1-15/B25', display_label: '空格', formula_ref: "WP('E1','利息收入月度分析E1-15','B25')",
      state: 'missing', value: null, text: null, reason_code: 'cell_empty', reason: '单元格未录入', source: src('E1-15', 'B25', null) },
    { input: 'D2/D2-2/E100', addr_id: 'D2/D2-2/E100', display_label: '歧义', formula_ref: "WP('D2','明细表','E100')",
      state: 'blocked', value: null, text: null, reason_code: 'wp_ambiguous', reason: '底稿记录有歧义', source: null },
  ],
}

function mountBlock(block: AcnrResultsBlock | null = BLOCK) {
  return mount(AcnrTargetResults, {
    props: { block, projectId: 'p1' },
    global: { plugins: [ElementPlus], stubs: { GtIndexChip: { template: '<button class="chip" @click="$emit(\'click\')" />' } } },
  })
}

beforeEach(() => {
  acnrMocks.resolveIndex.mockReset()
})

describe('四种状态渲染', () => {
  it('ok 显示值、text 显示原文、missing / blocked 显示「—」与原因', async () => {
    const w = mountBlock()
    await flushPromises()
    expect(w.findAll('[data-testid="acnr-value"]').map((n) => n.text())).toEqual(['11', '结论文本', '—', '—'])
    expect(w.findAll('[data-testid="acnr-reason"]').map((n) => n.text())).toEqual(['', '单元格是文本', '单元格未录入', '底稿记录有歧义'])
    expect(w.text()).toContain('已取值')
    expect(w.text()).toContain('取不到')
    expect(w.text()).toContain('无法确定')
    expect(w.text()).toContain('底稿 > E1 > 企业信用报告信息查询记录E1-18 › B20')
  })

  it('没有取值块（不带 acnr_targets 的查询）不渲染', () => {
    expect(mountBlock(null).find('[data-testid="acnr-target-results"]').exists()).toBe(false)
  })
})

describe('下钻', () => {
  it('有 jump_route：直接打开，站内路由不带 noopener、追加 cell=，不再走解析', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const w = mountBlock()
    await flushPromises()
    await w.findAll('.chip')[0].trigger('click')
    expect(open).toHaveBeenCalledWith('/projects/p1/workpapers/w1/edit?sheet=E1-18&cell=B20', '_blank')
    expect(acnrMocks.resolveIndex).not.toHaveBeenCalled()
    open.mockRestore()
  })

  it('没有 jump_route：按 addr_id 经 ACNR 解析后打开', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    acnrMocks.resolveIndex.mockResolvedValue({ found: true, jump_route: '/projects/p1/workpapers/w2/edit?sheet=E1-14' })
    const w = mountBlock()
    await flushPromises()
    await w.findAll('.chip')[1].trigger('click')
    await flushPromises()
    expect(acnrMocks.resolveIndex).toHaveBeenCalledWith('cell:E1-14!B30')
    expect(open).toHaveBeenCalledWith('/projects/p1/workpapers/w2/edit?sheet=E1-14&cell=B30', '_blank')
    open.mockRestore()
  })
})

/** 生产错误：后端 http_exception_handler 把 detail 放进 message，拦截器同一函数补出 detail */
function wire(status: number, body: Record<string, unknown>) {
  const response = { status, data: body }
  normaliseErrorEnvelope(response)
  return { response }
}

describe('拒绝提示：后端真实形状 → 中文', () => {
  it('422 ACNR_TARGETS_REJECTED：总述 + 逐项原因', () => {
    const e = wire(422, { code: 422, message: {
      error_code: 'ACNR_TARGETS_REJECTED', message: '所选单元格中有 2 项无法取值，未执行查询',
      issues: [
        { ref: 'E1/E1-14', error_code: 'sheet_level', message: '所选为整张表、不是单元格，请细化到具体单元格' },
        { ref: 'tb:1001', error_code: 'unsupported_domain', message: '该地址不是底稿单元格（tb / 报表 / 附注 / 辅助域），本功能暂不支持取值' },
      ] } })
    expect(queryErrorText(e)).toBe('所选单元格中有 2 项无法取值，未执行查询：E1/E1-14：所选为整张表、不是单元格，请细化到具体单元格；'
      + 'tb:1001：该地址不是底稿单元格（tb / 报表 / 附注 / 辅助域），本功能暂不支持取值')
  })

  it('422 YEAR_REQUIRED / PROJECT_REQUIRED 显示后端中文', () => {
    expect(queryErrorText(wire(422, { code: 422, message: { error_code: 'YEAR_REQUIRED', message: '项目审计年度未知，请指定年度后再取值' } })))
      .toBe('项目审计年度未知，请指定年度后再取值')
  })

  it('422 请求模型校验（未声明字段 / 单元格引用）显示中文 msg；其它英文字段错误交给兜底', () => {
    const e = { response: { status: 422, data: { code: 422, message: '请求参数校验失败', detail: [
      { type: 'unknown_field', loc: ['body'], msg: '请求包含未声明的字段「foo」，已拒绝' },
      { type: 'acnr_target_empty', loc: ['body', 'acnr_targets'], msg: '第 2 个单元格引用为空' },
    ] } } }
    normaliseErrorEnvelope(e.response)
    expect(queryErrorText(e)).toBe('请求包含未声明的字段「foo」，已拒绝；第 2 个单元格引用为空')
    expect(queryErrorText({ response: { status: 422, data: { detail: [{ type: 'missing', msg: 'Field required' }] } } })).toBeNull()
  })

  it('503 / 403 用固定中文', () => {
    expect(queryErrorText(wire(503, { code: 503, message: { error_code: 'RESOLVE_UNAVAILABLE', message: '地址解析服务暂不可用，未执行查询，请稍后重试', issues: [] } })))
      .toBe('地址解析服务暂不可用，请稍后重试')
    expect(queryErrorText(wire(403, { code: 403, message: { error_code: 'FORBIDDEN_PROJECT', message: 'forbidden' } }))).toBe('无权访问该项目')
    expect(queryErrorText(wire(500, { code: 500, message: '服务器内部错误' }))).toBeNull()
  })
})
