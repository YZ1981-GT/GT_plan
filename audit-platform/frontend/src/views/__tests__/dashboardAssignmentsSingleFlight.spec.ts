// Dashboard 首屏 assignments 单飞 + 待办并发（spec runtime-performance-and-reload-hardening-followup R6.1）。
//
// 🔴 原实现「今日日程」和「我的待办底稿」各 await 一次 getMyAssignments()，浏览器实测首屏对
// /api/my/assignments 发两条完全相同的请求；待办还对前 5 个项目串行 await 底稿列表（5 个往返排队）。
//
// 判据：assignments 只发 1 次；5 个项目的底稿请求并发发出（在第一个 resolve 之前就都已发出）；
// 单个项目失败只丢它自己那一段，顺序与截取语义不变。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const getMyAssignments = vi.fn()
const listProjectsWithProgress = vi.fn()
const httpGet = vi.fn()

vi.mock('@/services/commonApi', () => ({
  getMyAssignments: () => getMyAssignments(),
  listProjectsWithProgress: () => listProjectsWithProgress(),
}))
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: unknown[]) => httpGet(...args) },
}))

async function sourceOf(): Promise<string> {
  const fs = await import('node:fs')
  const path = await import('node:path')
  return fs.readFileSync(path.resolve(__dirname, '../Dashboard.vue'), 'utf-8')
}

/** 把 onMounted 里的取数流程按源码语义复刻一遍：判据盯的是请求形态，不是渲染。 */
async function runLoad(): Promise<{ schedule: unknown[]; workpapers: any[] }> {
  const assignmentsPromise = getMyAssignments()
  let schedule: unknown[] = []
  try {
    schedule = (await assignmentsPromise).slice(0, 6)
  } catch { /* ignore */ }
  const workpapers: any[] = []
  try {
    const assignments = await assignmentsPromise
    const projects = assignments.slice(0, 5)
    const settled = await Promise.allSettled(
      projects.map((proj: any) => httpGet(`/api/projects/${proj.project_id}/working-papers`, {
        params: { assigned_to_me: true, status: 'draft,rejected' },
      })),
    )
    settled.forEach((result: any, index: number) => {
      if (result.status !== 'fulfilled') return
      const data = result.value
      const items = Array.isArray(data) ? data : data?.items || []
      for (const wp of items.slice(0, 3)) workpapers.push({ ...wp, project_id: projects[index].project_id })
    })
  } catch { /* ignore */ }
  // 与生产一致：每项目最多 3 条、总共前 6 条
  return { schedule, workpapers: workpapers.slice(0, 6) }
}

const PROJECTS = Array.from({ length: 6 }, (_, i) => ({ project_id: `p${i + 1}` }))

beforeEach(() => {
  getMyAssignments.mockReset()
  httpGet.mockReset()
  getMyAssignments.mockResolvedValue(PROJECTS)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Dashboard 首屏取数', () => {
  it('assignments 只取一次（两处共用同一个 promise）', async () => {
    httpGet.mockResolvedValue({ items: [] })
    await runLoad()
    expect(getMyAssignments).toHaveBeenCalledTimes(1)
  })

  it('5 个项目的底稿请求并发发出，不是串行排队', async () => {
    const resolvers: Array<(v: unknown) => void> = []
    httpGet.mockImplementation(() => new Promise((resolve) => { resolvers.push(resolve) }))
    const pending = runLoad()
    // 挂起响应：若仍是串行，这里只会看到 1 条请求
    await Promise.resolve()
    await Promise.resolve()
    expect(httpGet).toHaveBeenCalledTimes(5)
    resolvers.forEach((resolve) => resolve({ items: [] }))
    await pending
  })

  it('单个项目失败只丢它自己那一段，顺序与截取不变', async () => {
    httpGet.mockImplementation((url: string) => {
      if (url.includes('p2')) return Promise.reject(new Error('boom'))
      const code = url.match(/projects\/(p\d)/)?.[1] ?? '?'
      return Promise.resolve({ items: [{ wp_code: `${code}-a` }, { wp_code: `${code}-b` }] })
    })
    const { workpapers } = await runLoad()
    expect(workpapers.map((w) => w.wp_code)).toEqual(['p1-a', 'p1-b', 'p3-a', 'p3-b', 'p4-a', 'p4-b'])
    expect(workpapers.every((w) => w.project_id)).toBe(true)
  })

  it('源码判据：onMounted 里只有一处 getMyAssignments() 调用，且用 allSettled 并保持截取', async () => {
    const source = await sourceOf()
    const mounted = source.slice(source.indexOf('onMounted(async () => {'))
    // 🔴 必须先剔注释：首版直接在全文上匹配，被我自己注释里写的 getMyAssignments() 咬成 2 次
    //（与 memory 铁律 ㉖「注释正反两向都会骗过文本匹配」同一个坑）。
    const code = mounted
      .split('\n')
      .filter((line) => !line.trim().startsWith('//') && !line.trim().startsWith('*'))
      .join('\n')
    expect(code.match(/getMyAssignments\(\)/g) ?? []).toHaveLength(1)
    expect(code).toContain('Promise.allSettled')
    expect(code).toContain('wpList.slice(0, 6)')
    expect(code).toContain('items.slice(0, 3)')
    // 反向：不得再出现「await getMyAssignments()」的第二次直接取数
    expect(code.match(/await getMyAssignments\(\)/g) ?? []).toHaveLength(0)
  })
})
