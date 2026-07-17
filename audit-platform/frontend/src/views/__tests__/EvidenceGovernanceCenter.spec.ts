/**
 * EvidenceGovernanceCenter — 挂载冒烟测试（Wave 9 UI 接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * 验证治理中心视图可挂载、8 个治理域 tab 全部注册、projectId/year/role 正确注入子组件。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

// ── mock 路由 ──
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-1' } }),
}))

// ── mock stores ──
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({ year: ref(2025), clientName: ref('测试客户') }),
}))
vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => ({
    currentProjectRole: { role: 'manager' },
    effectiveRole: 'manager',
    loadProjectRole: vi.fn(),
  }),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { role: 'manager' } }),
}))
// storeToRefs 直接返回传入对象（stores 已是 ref 字段）
vi.mock('pinia', () => ({
  storeToRefs: (s: any) => s,
}))

import EvidenceGovernanceCenter from '../EvidenceGovernanceCenter.vue'

const STUBS = {
  EvidenceRefsTab: { template: '<div class="stub-refs">{{ projectId }}-{{ year }}</div>', props: ['projectId', 'year'] },
  OcrGovernanceTab: { template: '<div class="stub-ocr" />', props: ['projectId', 'year', 'role'] },
  CitationTab: { template: '<div class="stub-citation" />', props: ['projectId', 'year'] },
  AiGateTab: { template: '<div class="stub-ai" />', props: ['projectId', 'year', 'role'] },
  ReviewEvidenceTab: { template: '<div class="stub-review" />', props: ['projectId', 'year'] },
  ArchiveManifestTab: { template: '<div class="stub-archive" />', props: ['projectId', 'year'] },
  LegalHoldTab: { template: '<div class="stub-hold" />', props: ['projectId', 'year'] },
  MetricsTab: { template: '<div class="stub-metrics" />' },
}

describe('EvidenceGovernanceCenter', () => {
  it('挂载并渲染标题与 8 个治理域 tab', () => {
    const wrapper = mount(EvidenceGovernanceCenter, { global: { stubs: STUBS } })
    const html = wrapper.html()
    expect(html).toContain('证据链治理中心')
    for (const label of ['证据关系', 'OCR 治理', '引用定位', 'AI 门禁', '复核证据', '归档清单', '法定保全', '治理指标']) {
      expect(html).toContain(label)
    }
  })

  it('首个 tab（证据关系）默认渲染并注入 projectId/year', () => {
    const wrapper = mount(EvidenceGovernanceCenter, { global: { stubs: STUBS } })
    const refsTab = wrapper.find('.stub-refs')
    expect(refsTab.exists()).toBe(true)
    expect(refsTab.text()).toContain('proj-1-2025')
  })
})
