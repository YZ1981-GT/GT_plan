/**
 * 归档向导：启动 / 重试先二次确认并带令牌、任务 id 读 `id`、中文类别与失败步骤、带鉴权下载
 * （spec attachment-archive-and-a-class-evidence 需求 4.3、4.4、5.3、1.4）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockReplace = vi.fn()
const routeParams: Record<string, string> = { projectId: 'p1' }
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: routeParams }),
  useRouter: () => ({ push: vi.fn(), replace: mockReplace }),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/utils/passwordConfirm', async (orig) => ({
  ...(await orig<typeof import('@/utils/passwordConfirm')>()),
  requestConfirmationToken: vi.fn(),
}))
vi.mock('@/utils/http', async (orig) => ({
  ...(await orig<typeof import('@/utils/http')>()),
  downloadFile: vi.fn(() => Promise.resolve()),
}))

import ArchiveWizard from '@/views/ArchiveWizard.vue'
import { api } from '@/services/apiProxy'
import { requestConfirmationToken } from '@/utils/passwordConfirm'
import { downloadFile } from '@/utils/http'
import { ARCHIVE_CATEGORY_LABELS } from '@/constants/archiveLabels'

const STUBS = {
  'el-steps': true, 'el-step': true, 'el-table': true, 'el-table-column': true, 'el-icon': true,
  'el-alert': true, 'el-tag': { template: '<span><slot /></span>' }, GtPageHeader: true, GateReadinessPanel: true,
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-result': { template: '<div><slot name="sub-title" /><slot name="extra" /></div>' },
  'el-progress': true, 'el-descriptions': true, 'el-descriptions-item': true, 'el-form': true,
}
const JOB = (over: Record<string, any> = {}) => ({
  id: 'job-1', project_id: 'p1', scope: 'final', status: 'running', last_succeeded_section: null,
  failed_section: null, failed_reason: null, output_url: null, manifest_hash: null, started_at: null,
  finished_at: null, section_progress: {}, ...over,
})

function mountWizard() {
  return mount(ArchiveWizard, { global: { stubs: STUBS, directives: { permission: {}, loading: {} } } })
}

describe('ArchiveWizard 二次确认与作业', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    delete routeParams.jobId
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.includes('archive-completeness-report')) {
        return Promise.resolve({ categories: [], can_proceed: true, generated_at: '2026-10-27T00:00:00Z' })
      }
      if (url.includes('archive-readiness')) return Promise.resolve({ ready: true, groups: [] })
      return Promise.resolve(JOB())
    })
  })

  it('启动：取消确认不发请求', async () => {
    vi.mocked(requestConfirmationToken).mockResolvedValue(null)
    const vm = mountWizard().vm as any
    await flushPromises()
    await vm.handleStartArchive()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('启动：带令牌与长超时，按 id 跳转与轮询', async () => {
    vi.mocked(requestConfirmationToken).mockResolvedValue('tok-1')
    vi.mocked(api.post).mockResolvedValue(JOB())
    const vm = mountWizard().vm as any
    await flushPromises()
    await vm.handleStartArchive()
    await flushPromises()
    const [url, body, cfg] = vi.mocked(api.post).mock.calls[0] as any[]
    expect(url).toBe('/api/projects/p1/archive/orchestrate')
    expect(body).toMatchObject({ scope: 'final', push_to_cloud: true, purge_local: false })
    expect(cfg.headers).toEqual({ 'X-Confirmation-Token': 'tok-1' })
    expect(cfg.timeout).toBeGreaterThanOrEqual(10 * 60 * 1000)
    expect(mockReplace).toHaveBeenCalledWith({ path: '/projects/p1/archive/jobs/job-1' })
    expect(vi.mocked(api.get).mock.calls.some(([u]) => u === '/api/projects/p1/archive/jobs/job-1')).toBe(true)
    vm.stopPolling()
  })

  it('重试：先确认并带令牌', async () => {
    vi.mocked(requestConfirmationToken).mockResolvedValue('tok-2')
    vi.mocked(api.post).mockResolvedValue(JOB({ status: 'succeeded' }))
    const vm = mountWizard().vm as any
    await flushPromises()
    vm.jobData = JOB({ status: 'failed', failed_section: 'package' })
    await vm.handleRetry()
    const [url, body, cfg] = vi.mocked(api.post).mock.calls[0] as any[]
    expect(url).toBe('/api/projects/p1/archive/jobs/job-1/retry')
    expect(body).toBeUndefined()
    expect(cfg.headers).toEqual({ 'X-Confirmation-Token': 'tok-2' })
    vm.stopPolling()
  })

  it('失败步骤与问题清单显示中文；下载走带鉴权的 downloadFile', async () => {
    routeParams.jobId = 'job-1'
    vi.mocked(api.get).mockResolvedValue(JOB({
      status: 'failed', failed_section: 'package', last_succeeded_section: 'gate',
      failed_reason: '归档包有 1 项读不到，未生成归档包',
      section_progress: { gate: { status: 'succeeded' }, package: { status: 'failed', problems: ['附件｜回函.pdf｜附件文件不存在'] } },
    }))
    const wrapper = mountWizard()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('失败步骤：生成归档包')
    expect(text).toContain('最后成功步骤：门禁检查')
    expect(text).toContain('附件｜回函.pdf｜附件文件不存在')
    const vm = wrapper.vm as any
    vm.stopPolling()
    vm.jobData = JOB({ status: 'succeeded', output_url: '/api/projects/p1/archive/jobs/job-1/package' })
    await vm.handleDownload()
    expect(downloadFile).toHaveBeenCalledWith('/api/projects/p1/archive/jobs/job-1/package', { fileName: '归档包.zip' })
  })

  it('10 个完整性类别都有中文名', () => {
    for (const key of ['missing', 'unsigned', 'unresolved_reviews', 'stale', 'sampling_records', 'missing_files',
      'evidence_gaps', 'unreplied_confirmations', 'unconfirmed_ocr', 'orphan_files']) {
      expect(ARCHIVE_CATEGORY_LABELS[key], key).toMatch(/[\u4e00-\u9fa5]/)
    }
  })
})
