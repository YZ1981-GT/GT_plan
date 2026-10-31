/**
 * 导出对话框按五态显示一致性检查（spec formula-hub-integrity-closure 阶段 D 缺陷 D-3，需求 16.4 / 16.5）。
 *
 * 原状：只按 passed 显示 ✅ / ❌ / ⚠，五态改造后「未执行」的阻断项 passed=false ⇒ 被当成阻断失败、禁用导出，
 * 比后端导出包服务 observe 口径（只看「失败 ∧ 阻断级」）还严。
 * 本对话框目前没有挂载点（唯一宿主 WorkflowDashboard.vue 不在任何路由 / 页面里），以挂载本组件为证。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('@/utils/http', () => ({ default: { post: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { role: 'partner' } }) }))

import ExportDialog from '@/components/ExportDialog.vue'

function mountDialog() {
  return mount(ExportDialog, { props: { projectId: 'p1', year: 2025 }, global: { plugins: [ElementPlus] } })
}

function rows(w: ReturnType<typeof mountDialog>) {
  return w.findAll('[data-testid="export-check-item"]').map(r => ({
    status: r.find('[data-testid="export-check-status"]').text(),
    text: r.text(),
    cls: r.classes(),
  }))
}

function exportButton(w: ReturnType<typeof mountDialog>) {
  return w.findAll('button').find(b => b.text().includes('开始导出'))!
}

describe('ExportDialog 一致性检查五态', () => {
  beforeEach(() => get.mockReset())

  it('请求一致性检查展示端点；五态各有标签与原因，未执行不显示成通过', async () => {
    get.mockResolvedValue({
      checks: [
        { check_name: '试算平衡', passed: true, status: 'passed', reason: '', details: '平衡', severity: 'blocking' },
        { check_name: '报表平衡', passed: false, status: 'not_executed', reason: '数据不完整，跳过检查', details: '',
          severity: 'blocking' },
        { check_name: '附注完整性', passed: false, status: 'not_applicable', reason: '底稿已裁剪', details: '',
          severity: 'warning' },
        { check_name: 'E1现金流', passed: false, status: 'error', reason: '检查异常：RuntimeError：boom', details: '',
          severity: 'blocking' },
      ],
    })
    const w = mountDialog()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/projects/p1/workflow/consistency-check', { params: { year: 2025 } })
    const r = rows(w)
    expect(r.map(x => x.status)).toEqual(['通过', '未执行（数据缺失）', '不适用', '检查异常'])
    expect(r[1].text).toContain('数据不完整，跳过检查')
    expect(r[2].text).toContain('底稿已裁剪')
    expect(r[3].text).toContain('检查异常：RuntimeError：boom')
    expect(r[1].cls).toContain('gt-export-check-item--not-run')
    expect(r[1].cls).not.toContain('gt-export-check-item--pass')
    // 没有「失败 ∧ 阻断级」：导出按钮可用（与导出包服务 observe 口径一致），强制导出选项不出现
    expect(exportButton(w).attributes('disabled')).toBeUndefined()
    expect(w.text()).not.toContain('强制导出')
    w.unmount()
  })

  it('有「失败 ∧ 阻断级」：禁用导出并给出强制导出选项', async () => {
    get.mockResolvedValue({
      checks: [{ check_name: '报表平衡', passed: false, status: 'failed', reason: '差额 10.00', details: '',
        severity: 'blocking' }],
    })
    const w = mountDialog()
    await flushPromises()
    const [row] = rows(w)
    expect(row.status).toBe('失败')
    expect(row.text).toContain('差额 10.00')
    expect(row.cls).toContain('gt-export-check-item--fail-blocking')
    expect(exportButton(w).attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('强制导出')
    w.unmount()
  })

  it('接口没给出检查状态：按「检查异常」显示，不当成通过', async () => {
    get.mockResolvedValue({ checks: [{ check_name: '试算平衡', passed: true, details: '', severity: 'blocking' }] })
    const w = mountDialog()
    await flushPromises()
    const [row] = rows(w)
    expect(row.status).toBe('检查异常')
    expect(row.text).toContain('接口未返回检查状态')
    expect(row.cls).not.toContain('gt-export-check-item--pass')
    w.unmount()
  })
})
