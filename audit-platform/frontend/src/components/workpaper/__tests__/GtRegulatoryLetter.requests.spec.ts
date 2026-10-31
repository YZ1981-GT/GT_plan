/**
 * A18-2 与监管层沟通函：读写 / 表头带出 / 导出请求打到后端真实接口（spec platform-performance-residual-findings-closure）。
 *
 * 原先除导出外的 5 个请求都少 /api 前缀（`/projects/{pid}/…`），且检查表读写用了不存在的
 * `/projects/{pid}/working-papers/{wp}/checklist-responses`：读拿到首页 HTML ⇒ 已填内容从不加载；保存发数组体、
 * 空适用性发空串 ⇒ 后端 422（后端要 `{project_id, items}`，A18-2 结论只收 Y / N / done / pending）；
 * 表头年度读不存在的 audit_period_end。这里按后端真实形状 mock，钉住请求路径与请求体。
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
const box = vi.hoisted(() => ({ confirm: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: box,
}))

import GtRegulatoryLetter from '../GtRegulatoryLetter.vue'

const PID = 'p-1'
const WP = 'wp-1'
const CHECKLIST = `/api/workpapers/${WP}/checklist-responses`
const SUGGESTIONS = `/api/projects/${PID}/a18/suggestions`

function serve(map: Record<string, unknown>) {
  api.get.mockImplementation(async (url: string) => {
    if (url in map) return map[url]
    throw new Error(`未登记的 GET ${url}`)
  })
}

function mountLetter() {
  return shallowMount(GtRegulatoryLetter, {
    props: { projectId: PID, wpId: WP },
    global: { directives: { loading: {} } },
  })
}

/** 挂载流程是一串 await（议题定义动态导入 → 读检查表 → 表头带出 → 建议），多冲几轮微任务 */
async function settle() {
  for (let i = 0; i < 6; i += 1) await flushPromises()
}

beforeAll(async () => {
  await import('@/data/a18_topic_definitions.json') // 先载入：组件里的动态导入随后同步命中缓存
})

beforeEach(() => {
  api.get.mockReset()
  api.put.mockReset()
  box.confirm.mockReset()
  api.put.mockResolvedValue([])
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
})
afterEach(() => {
  vi.useRealTimers()
})

describe('GtRegulatoryLetter 请求', () => {
  it('已填内容按底稿检查表接口加载；保存走同一接口，请求体 {project_id, items}，未选适用性存 null', async () => {
    serve({
      [CHECKLIST]: [
        { item_id: 'A18-2-header', conclusion: 'done',
          remark: JSON.stringify({ regulator: '某证监局', companyName: '甲公司', auditYear: '2025', partnerName: '张三' }) },
        { item_id: 'A18-2-001', conclusion: 'Y', remark: JSON.stringify({ content: '已沟通舞弊事项', wpRefs: [] }) },
        { item_id: 'A18-2-002', conclusion: '', remark: JSON.stringify({ content: '', wpRefs: [] }) },
      ],
      [SUGGESTIONS]: {},
    })
    const w = mountLetter()
    await settle()
    // 表头已有公司名 ⇒ 不再带出项目信息
    expect(api.get.mock.calls.map((c) => c[0])).toEqual([CHECKLIST, SUGGESTIONS])
    const vm = w.vm as any
    expect(vm.headerData.companyName).toBe('甲公司')
    expect(vm.topicDataMap.topic_001).toMatchObject({ applicable: 'Y', content: '已沟通舞弊事项' })

    vm.headerData.regulator = '另一证监局' // 用户改一处 ⇒ 1.5 秒后保存
    await flushPromises()
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(api.put).toHaveBeenCalledTimes(1)
    const [url, body] = api.put.mock.calls[0]
    expect(url).toBe(CHECKLIST)
    expect(body.project_id).toBe(PID)
    const byId = Object.fromEntries(body.items.map((i: any) => [i.item_id, i]))
    expect(byId['A18-2-header'].conclusion).toBe('done')
    expect(JSON.parse(byId['A18-2-header'].remark).regulator).toBe('另一证监局')
    expect(byId['A18-2-001'].conclusion).toBe('Y')
    expect(byId['A18-2-002'].conclusion).toBeNull()
  })

  it('表头为空时从项目详情 audit_year 与委派（先取签字合伙人）带出', async () => {
    serve({
      [CHECKLIST]: [],
      [`/api/projects/${PID}`]: { client_name: '乙公司', name: '乙公司_2025', audit_year: 2025 },
      [`/api/projects/${PID}/assignments`]: [
        { role: 'partner', staff_name: '李四' },
        { role: 'signing_partner', staff_name: '王五' },
      ],
      [SUGGESTIONS]: {},
    })
    const w = mountLetter()
    await settle()
    expect(api.get.mock.calls.map((c) => c[0])).toEqual([
      CHECKLIST, `/api/projects/${PID}`, `/api/projects/${PID}/assignments`, SUGGESTIONS,
    ])
    expect((w.vm as any).headerData).toMatchObject({ companyName: '乙公司', auditYear: '2025', partnerName: '王五' })
    // 带出只填显示：不落库（R9）
    vi.advanceTimersByTime(3000)
    await flushPromises()
    expect(api.put).not.toHaveBeenCalled()
  })

  it('导出：先按统一检查契约提示未填议题，再下载文件', async () => {
    serve({ [CHECKLIST]: [{ item_id: 'A18-2-header', conclusion: 'done', remark: JSON.stringify({ companyName: '甲公司' }) }], [SUGGESTIONS]: {} })
    const w = mountLetter()
    await settle()
    const base = `/api/projects/${PID}/working-papers/${WP}/export-word`
    api.get.mockImplementation(async (url: string) => {
      if (url === `${base}/check-incomplete`) {
        return { complete: false, missing_fields: ['舞弊', '重大违法行为'], wp_code: 'A18-2', reason: '2 项议题未填写' }
      }
      if (url === base) return new Blob(['docx'])
      throw new Error(`未登记的 GET ${url}`)
    })
    box.confirm.mockResolvedValue('confirm')
    const createObjectURL = vi.fn(() => 'blob:x')
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() })
    await (w.vm as any).exportWord()
    expect(box.confirm.mock.calls[0][0]).toContain('存在 2 项未完成内容（舞弊、重大违法行为）')
    expect(api.get).toHaveBeenCalledWith(base, { responseType: 'blob' })
    expect(createObjectURL).toHaveBeenCalledTimes(1)
  })
})

/**
 * 只在用户改动后保存（spec platform-performance-residual-findings-closure R9）。
 * 原先 `watch([topicDataMap, headerData])` 一挂载就被「读已存内容」「表头带出」触发 ⇒ 每次打开 1.5 秒后自动 PUT
 * （只读打开提示「保存失败」，真实项目打开即写库）。
 */
describe('GtRegulatoryLetter 只在用户改动后保存', () => {
  const SAVED = [
    { item_id: 'A18-2-header', conclusion: 'done',
      remark: JSON.stringify({ regulator: '某证监局', companyName: '甲公司', auditYear: '2025', partnerName: '张三' }) },
    { item_id: 'A18-2-001', conclusion: 'Y', remark: JSON.stringify({ content: '已沟通舞弊事项', wpRefs: [] }) },
  ]

  it('打开（读已存内容）后不保存；改动后 1.5 秒保存一次，卸载不重复保存', async () => {
    serve({ [CHECKLIST]: SAVED, [SUGGESTIONS]: {} })
    const w = mountLetter()
    await settle()
    vi.advanceTimersByTime(3000)
    await flushPromises()
    expect(api.put).not.toHaveBeenCalled()

    ;(w.vm as any).topicDataMap.topic_001.content = '补充说明'
    await flushPromises()
    vi.advanceTimersByTime(1499)
    expect(api.put).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(api.put).toHaveBeenCalledTimes(1)
    const items = api.put.mock.calls[0][1].items
    expect(JSON.parse(items.find((i: any) => i.item_id === 'A18-2-001').remark).content).toBe('补充说明')
    w.unmount()
    await flushPromises()
    expect(api.put).toHaveBeenCalledTimes(1)
  })

  it('改了又改回原值：撤掉待发的保存', async () => {
    serve({ [CHECKLIST]: SAVED, [SUGGESTIONS]: {} })
    const w = mountLetter()
    await settle()
    const vm = w.vm as any
    vm.headerData.regulator = '另一证监局'
    await flushPromises()
    vm.headerData.regulator = '某证监局'
    await flushPromises()
    vi.advanceTimersByTime(3000)
    await flushPromises()
    expect(api.put).not.toHaveBeenCalled()
  })

  it('保存后基线前移：保存途中改回原值 ⇒ 按刚落库的内容再保存一次', async () => {
    serve({ [CHECKLIST]: SAVED, [SUGGESTIONS]: {} })
    let release!: () => void
    api.put.mockImplementationOnce(() => new Promise((resolve) => { release = () => resolve([]) }))
    const w = mountLetter()
    await settle()
    const vm = w.vm as any
    vm.headerData.regulator = '另一证监局'
    await flushPromises()
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(api.put).toHaveBeenCalledTimes(1)
    vm.headerData.regulator = '某证监局' // 第一次保存还没回来时改回去
    await flushPromises()
    release()
    await flushPromises()
    vi.advanceTimersByTime(1500)
    await flushPromises()
    expect(api.put).toHaveBeenCalledTimes(2)
    expect(JSON.parse(api.put.mock.calls[1][1].items[0].remark).regulator).toBe('某证监局')
  })

  it('读已存内容失败：不自动保存并提示（避免用带出值覆盖已存表头）', async () => {
    const { ElMessage } = await import('element-plus')
    api.get.mockImplementation(async (url: string) => {
      if (url === CHECKLIST) throw new Error('HTTP 500')
      if (url === `/api/projects/${PID}`) return { client_name: '乙公司', audit_year: 2025 }
      if (url === `/api/projects/${PID}/assignments`) return []
      if (url === SUGGESTIONS) return {}
      throw new Error(`未登记的 GET ${url}`)
    })
    const w = mountLetter()
    await settle()
    expect(ElMessage.error).toHaveBeenCalledWith('读取已填内容失败，本页不自动保存，请刷新重试')
    ;(w.vm as any).headerData.regulator = '某证监局'
    await flushPromises()
    vi.advanceTimersByTime(3000)
    await flushPromises()
    expect(api.put).not.toHaveBeenCalled()
  })
})
