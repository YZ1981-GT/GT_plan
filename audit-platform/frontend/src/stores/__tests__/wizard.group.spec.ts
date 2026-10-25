/**
 * stores/wizard.ts — 集团关系字段收发（spec consol-tree-three-code-autobuild 任务 4.1，需求 1.6 / 1.8）
 * 1. 创建请求对所有报表类型发三码与关系（原实现只在合并报表时发）
 * 2. 以响应为准回填（后端可能按名称补了关系、继承了另一口径项目的集团关系）
 * 3. 批量导入项目兜底回填恢复三码与关系
 * 4. 建项/保存的 notices 暴露给页面提示
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const post = vi.fn()
const get = vi.fn()
const put = vi.fn()
vi.mock('@/utils/http', () => ({ default: { post: (...a: any[]) => post(...a), get: (...a: any[]) => get(...a), put: (...a: any[]) => put(...a) } }))

import { useWizardStore, type BasicInfo } from '@/stores/wizard'

const OWN = '91110000300000000G'
const PARENT = '911100002000000005'
const GROUP = '91110000100000000R'

function basicInfo(patch: Partial<BasicInfo> = {}): BasicInfo {
  return {
    client_name: '某某有限公司临港店', short_name: '临港店', audit_year: 2025, project_type: 'annual',
    accounting_standard: 'enterprise', company_code: OWN, template_type: 'soe', company_subtype: null,
    custom_template_id: '', custom_template_name: '', custom_template_version: '',
    report_scope: 'standalone',
    parent_company_name: '某某有限公司', parent_company_code: PARENT, relation_to_parent: '',
    ultimate_company_name: '', ultimate_company_code: ' ',
    signing_partner_id: null, manager_id: null, budget_hours: null, contract_amount: null,
    ...patch,
  }
}

describe('wizard store 集团关系', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    post.mockReset(); get.mockReset(); put.mockReset()
  })

  it('单户项目也发送三码与关系，空值不发', async () => {
    post.mockResolvedValue({ data: { id: 'p1', notices: [] } })
    await useWizardStore().createProject(basicInfo({ relation_to_parent: 'branch' }))
    const payload = post.mock.calls[0][1]
    expect(payload.report_scope).toBe('standalone')
    expect(payload.parent_company_code).toBe(PARENT)
    expect(payload.parent_company_name).toBe('某某有限公司')
    expect(payload.relation_to_parent).toBe('branch')
    expect('ultimate_company_code' in payload).toBe(false)
    expect('consolidation_type' in payload).toBe(false)
  })

  it('以创建响应的集团关系为准回填，并暴露 notices', async () => {
    post.mockResolvedValue({ data: {
      id: 'p1', parent_company_code: PARENT, parent_company_name: '某某有限公司',
      relation_to_parent: 'branch', ultimate_company_code: GROUP, ultimate_company_name: '某集团',
      notices: ['与上级关系未填写，已按企业名称默认为「分公司」', '最终控制方已按上级企业补齐为 某集团'],
    } })
    const store = useWizardStore()
    await store.createProject(basicInfo())
    const saved = store.stepData.basic_info as unknown as BasicInfo
    expect(saved.relation_to_parent).toBe('branch')
    expect(saved.ultimate_company_code).toBe(GROUP)
    expect(store.lastNotices).toHaveLength(2)
  })

  it('保存基本信息时收集 notices；reset 清空', async () => {
    put.mockResolvedValue({ data: {
      project_id: 'p1', current_step: 'basic_info', completed: false,
      steps: { basic_info: { step: 'basic_info', data: { client_name: 'X' }, completed: true } },
      notices: ['已同步集团关系到同企业的合并项目「X」'],
    } })
    const store = useWizardStore()
    store.projectId = 'p1'
    await store.saveStep('basic_info', { client_name: 'X' })
    expect(store.lastNotices).toEqual(['已同步集团关系到同企业的合并项目「X」'])
    store.reset()
    expect(store.lastNotices).toEqual([])
  })

  it('无向导状态的项目（批量导入）从项目详情回填三码与关系', async () => {
    get.mockImplementation((url: string) => {
      if (url.endsWith('/wizard')) return Promise.resolve({ status: 404, data: null })
      return Promise.resolve({ data: {
        client_name: '某某有限公司临港店', company_code: OWN, audit_year: 2025, report_scope: 'standalone',
        parent_company_code: PARENT, parent_company_name: null, relation_to_parent: 'branch',
        ultimate_company_code: GROUP, ultimate_company_name: '某集团',
      } })
    })
    const store = useWizardStore()
    await store.loadWizardState('p1')
    const saved = store.stepData.basic_info as unknown as BasicInfo
    expect(saved.parent_company_code).toBe(PARENT)
    expect(saved.parent_company_name).toBe('')
    expect(saved.relation_to_parent).toBe('branch')
    expect(saved.ultimate_company_code).toBe(GROUP)
  })
})
