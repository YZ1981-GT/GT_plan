import fs from 'node:fs'
import path from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get, post: vi.fn() } }))

import ConsolScopeConfigDialog from '../ConsolScopeConfigDialog.vue'

const STUBS = {
  'el-dialog': { name: 'el-dialog', template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>', props: ['modelValue'] },
  'el-table': { template: '<div data-testid="scope-table"><slot /></div>', props: ['data'] },
  'el-table-column': { template: '<div />' },
  'el-alert': { template: '<div data-testid="scope-alert">{{ title }}<slot /></div>', props: ['title'] },
  'el-empty': { template: '<div data-testid="scope-empty" :data-description="description" />', props: ['description'] },
  'el-button': { template: '<button><slot /></button>' },
  'el-tag': { template: '<span><slot /></span>' },
}

describe('ConsolScopeConfigDialog 自动识别范围', () => {
  beforeEach(() => get.mockReset())

  it('识别子公司/分公司并展示关系、年度、合并/单户口径，不调用 attach', async () => {
    get.mockResolvedValueOnce({ company_code: 'G', audit_year: 2025 })
      .mockResolvedValueOnce({ trees: [{ key: 'G@2025', year: 2025, children: [{
        companyCode: 'G', consolidatedProjectId: 'g', children: [{
          companyCode: 'B', companyName: '分公司B', relation: 'branch', year: 2025,
          consolidatedProjectId: null, standaloneProjectId: 'b-s', children: [],
        }],
      }] }] })
    const wrapper = mount(ConsolScopeConfigDialog, {
      props: { modelValue: true, projectId: 'g' }, global: { stubs: STUBS },
    })
    wrapper.findComponent({ name: 'el-dialog' }).vm.$emit('open')
    await flushPromises()
    expect(get).toHaveBeenNthCalledWith(2, '/api/projects/tree', { params: { year: 2025, scope: 'all' } })
    expect((wrapper.vm as any).members).toHaveLength(1)
    expect((wrapper.vm as any).members[0]).toMatchObject({ companyName: '分公司B', relation: 'branch', standaloneProjectId: 'b-s' })
  })

  it('没有下级时显示精确填写指引，且不出现勾选/纳入按钮', async () => {
    get.mockResolvedValueOnce({ company_code: 'G', audit_year: 2025 })
      .mockResolvedValueOnce({ trees: [{ key: 'G@2025', year: 2025, children: [{ companyCode: 'G', consolidatedProjectId: 'g', children: [] }] }] })
    const wrapper = mount(ConsolScopeConfigDialog, {
      props: { modelValue: true, projectId: 'g' }, global: { stubs: STUBS },
    })
    wrapper.findComponent({ name: 'el-dialog' }).vm.$emit('open')
    await flushPromises()
    expect(wrapper.text()).toContain('请在各子公司/分公司项目的基本信息中把上级代码填为 G')
    expect(wrapper.text()).not.toContain('纳入选中')
    expect(wrapper.text()).not.toContain('选择要纳入')
  })
})

describe('P12 生产接线守卫', () => {
  it('自动识别弹窗不再调用旧候选/attach 流程', () => {
    const src = fs.readFileSync(path.resolve(__dirname, '../ConsolScopeConfigDialog.vue'), 'utf-8')
    expect(src).toContain("'/api/projects/tree'")
    expect(src).not.toContain('availableSubsidiaries')
    expect(src).not.toContain('attachSubsidiaries')
    expect(src).not.toContain('child_project_ids')
    expect(src).not.toContain('type="selection"')
    expect(src).toContain('请在各子公司/分公司项目的基本信息中把上级代码填为')
  })

  it('批量预览类型含 warnings 与关系/口径字段', () => {
    const src = fs.readFileSync(path.resolve(__dirname, '../BatchImportDialog.vue'), 'utf-8')
    expect(src).toContain('warnings?: BatchWarning[]')
    expect(src).toContain('data.relation')
    expect(src).toContain('data.consolidatedProjectId')
    expect(src).toContain('data.standaloneProjectId')
    expect(src).toContain('v-if="validateResult.warnings?.length"')
    expect(src).toContain('validateResult.warnings')
  })
})
