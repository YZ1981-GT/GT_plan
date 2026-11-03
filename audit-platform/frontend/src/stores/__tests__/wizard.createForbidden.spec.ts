/**
 * stores/wizard.ts createProject 的 403 钩子（spec batch-project-authorization-and-lock-hardening 6.2 实测）：
 * 调用方给了 onForbidden ⇒ 作为请求级 `_forbiddenHandler` 交给 http 拦截器（403 时替代通用「权限不足」）；
 * 没给 ⇒ 请求与原来一致（不带第三个参数）。失败照常抛给调用方，不写 projectId。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const post = vi.fn()
vi.mock('@/utils/http', () => ({ default: { post: (...a: any[]) => post(...a), get: vi.fn(), put: vi.fn() } }))
vi.mock('@/services/projectListQuery', () => ({ invalidateProjectListQuery: vi.fn() }))

import { useWizardStore, type BasicInfo } from '@/stores/wizard'

function basicInfo(): BasicInfo {
  return {
    client_name: '【测试】甲', short_name: '甲', audit_year: 2097, project_type: 'annual',
    accounting_standard: 'enterprise', company_code: '91110000BPAH62011M', template_type: 'soe', company_subtype: null,
    business_category: null, scenario: 'normal',
    custom_template_id: '', custom_template_name: '', custom_template_version: '',
    report_scope: 'standalone',
    parent_company_name: '', parent_company_code: '', relation_to_parent: '',
    ultimate_company_name: '', ultimate_company_code: '',
    signing_partner_id: null, manager_id: null, budget_hours: null, contract_amount: null,
  }
}

describe('wizard store createProject 的 403 钩子', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    post.mockReset()
  })

  it('给了 onForbidden：作为 _forbiddenHandler 交给请求', async () => {
    post.mockResolvedValue({ data: { id: 'p1', notices: [] } })
    const onForbidden = vi.fn()
    await useWizardStore().createProject(basicInfo(), { onForbidden })
    expect(post).toHaveBeenCalledTimes(1)
    const [url, , config] = post.mock.calls[0]
    expect(url).toBe('/api/projects')
    expect(config._forbiddenHandler).toBe(onForbidden)
  })

  it('没给：请求不带第三个参数（与原来一致）', async () => {
    post.mockResolvedValue({ data: { id: 'p1', notices: [] } })
    await useWizardStore().createProject(basicInfo())
    expect(post.mock.calls[0]).toHaveLength(2)
  })

  it('被拒照常抛给调用方，不写 projectId、loading 复位', async () => {
    const denied = { isAxiosError: true, response: { status: 403, data: { detail: { message: '暂无建项授权' } } } }
    post.mockRejectedValue(denied)
    const store = useWizardStore()
    await expect(store.createProject(basicInfo(), { onForbidden: vi.fn() })).rejects.toBe(denied)
    expect(store.projectId).toBeNull()
    expect(store.loading).toBe(false)
  })
})
