/**
 * T31 守卫：歧义候选提示与外部命名空间中文提示（design §12.2~§12.5）
 *
 * 判据：
 * 1. AcnrCandidatesHint 显示后端给的中文原因、需补上下文、候选与下一步；
 *    点选候选把 addr_id 交回调用方。
 * 2. found=true 时不显示（不干扰正常命中）。
 * 3. GtIndexChip 对外部命名空间显示中文原因 + 下一步，界面不出现英文错误码。
 * 4. 命中停用条目时 chip 提示附停用原因（RV7-03）。
 *
 * 变异要求（tasks.md T31）：
 * - 删某命名空间 label_zh → 后端遍历用例红（见 test_external_namespace_reasons.py）。
 * - chip 改回只显示「跳转 → ns:target」→ 本文件外部命名空间用例红。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import AcnrCandidatesHint from '../AcnrCandidatesHint.vue'

// ─── 桩：chip 依赖的 SDK 与路由 ───
const resolveIndexBatched = vi.fn()
vi.mock('@/services/acnr', () => ({
  useAcnr: () => ({
    resolveIndexBatched,
    resolveInstance: vi.fn(),
  }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1' }, query: {}, path: '/x' }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/composables/useWpNavigationHistory', () => ({
  useWpNavigationHistory: () => ({ push: vi.fn() }),
}))

const stubs = {
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-tooltip': { props: ['content'], template: '<div :data-tip="content"><slot /></div>' },
  'el-dropdown': { template: '<div><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { template: '<div><slot /></div>' },
  'el-icon': { template: '<i><slot /></i>' },
}

describe('AcnrCandidatesHint', () => {
  it('显示中文原因、需补上下文与下一步', () => {
    const w = mount(AcnrCandidatesHint, {
      props: {
        result: {
          found: false,
          error: 'ambiguous',
          reason: '编码「D1-1」在多张底稿下都登记了',
          required_context: ['parent_wp_code'],
          next_step: '请补上所属底稿编码再解析，或从候选中选择一个',
          candidates: [
            { addr_id: 'D1/D1-1', display_label: 'D1 应收票据审定表' },
            { addr_id: 'D3/D1-1', display_label: 'D3 其他应收款审定表' },
          ],
        },
      },
      global: { stubs },
    })
    const text = w.text()
    expect(text).toContain('编码「D1-1」在多张底稿下都登记了')
    // 字段名要翻成中文说明，不能把 parent_wp_code 甩给用户
    expect(text).toContain('所属底稿编码')
    expect(text).not.toContain('parent_wp_code')
    expect(text).toContain('请补上所属底稿编码再解析')
    expect(text).toContain('D1 应收票据审定表')
    expect(text).toContain('D3 其他应收款审定表')
  })

  it('点选候选交回 addr_id', async () => {
    const w = mount(AcnrCandidatesHint, {
      props: {
        result: {
          found: false,
          reason: '多处匹配',
          candidates: [{ addr_id: 'D1/D1-1/C10', display_label: 'D1 应收票据审定表 › 期末余额' }],
        },
      },
      global: { stubs },
    })
    await w.find('button').trigger('click')
    const picked = w.emitted('pick')
    expect(picked).toBeTruthy()
    expect(picked![0][0]).toBe('D1/D1-1/C10')
  })

  it('命中时不显示', () => {
    const w = mount(AcnrCandidatesHint, {
      props: { result: { found: true, addr_id: 'D1/D1-1/C10', display_label: 'x' } },
      global: { stubs },
    })
    expect(w.text()).toBe('')
  })

  it('停用条目显示替代地址', () => {
    const w = mount(AcnrCandidatesHint, {
      props: {
        result: {
          found: false,
          deprecated: true,
          replaced_by: 'K10/K10-1',
          reason: '该地址已停用，建议改用 K10 应付职工薪酬审定表',
        },
      },
      global: { stubs },
    })
    expect(w.text()).toContain('该地址已停用')
    expect(w.text()).toContain('K10/K10-1')
  })

  it('未登记的上下文字段名照原样显示（便于发现漏登记）', () => {
    const w = mount(AcnrCandidatesHint, {
      props: { result: { found: false, reason: 'x', required_context: ['brand_new_field'] } },
      global: { stubs },
    })
    expect(w.text()).toContain('brand_new_field')
  })
})

describe('GtIndexChip 外部命名空间与停用提示', () => {
  beforeEach(() => {
    resolveIndexBatched.mockReset()
  })

  async function mountChip(value: string) {
    const GtIndexChip = (await import('@/components/workpaper/GtIndexChip.vue')).default
    const w = mount(GtIndexChip, { props: { value }, global: { stubs } })
    await new Promise(r => setTimeout(r, 0))
    await w.vm.$nextTick()
    return w
  }

  it('外部命名空间显示中文原因与下一步，不显示英文错误码', async () => {
    resolveIndexBatched.mockResolvedValue({
      found: false,
      error: 'external_module_not_resolved',
      reason: '「审计调整分录」类引用暂不支持定位到物理地址',
      next_step: '请在「调整分录」模块按编号查看该分录',
    })
    const w = await mountChip('Adj:AJE-001')
    const tip = w.find('[data-tip]').attributes('data-tip') || ''
    expect(tip).toContain('「审计调整分录」类引用暂不支持定位到物理地址')
    expect(tip).toContain('请在「调整分录」模块按编号查看该分录')
    expect(tip).not.toContain('external_module_not_resolved')
    expect(tip).not.toContain('底稿不存在')
  })

  it('命中停用条目时提示附停用原因', async () => {
    resolveIndexBatched.mockResolvedValue({
      found: true,
      addr_id: 'K14/K14',
      display_label: 'K14 应付职工薪酬审定表',
      deprecated: true,
      replaced_by: 'K10/K10-1',
      reason: '该地址已停用，建议改用 K10 应付职工薪酬审定表',
    })
    const w = await mountChip('wp:K14')
    const tip = w.find('[data-tip]').attributes('data-tip') || ''
    expect(tip).toContain('K14 应付职工薪酬审定表')
    expect(tip).toContain('该地址已停用')
  })

  it('后端没给原因时才退回「底稿不存在」', async () => {
    resolveIndexBatched.mockResolvedValue({ found: false })
    const w = await mountChip('wp:ZZ9')
    const tip = w.find('[data-tip]').attributes('data-tip') || ''
    expect(tip).toBe('底稿不存在')
  })
})
