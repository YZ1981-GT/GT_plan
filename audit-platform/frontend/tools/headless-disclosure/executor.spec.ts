// @vitest-environment node
/**
 * 离屏披露 Node 执行器契约（spec note-disclosure-pull-regression-and-headless-backend 任务 13，design §5.4）。
 *
 * 与构建同一换法：`@/utils/http` 换成 `nodeHttp`（vite.config.ts 的别名），后端换成按路径应答的假 fetch。provider 用真实的
 * `defineHeadlessProvider` 框架声明（同一套取数 / 章节判定 / 发送代码），编排走真实的 `refreshNotes` →
 * `runHeadlessDisclosure`。钉住：顺序（prepare → 离屏同步 → push → 重算）、每个请求都带服务端令牌、写请求名单、
 * 首次同步保护（从未由底稿同步、已有人工填写的章节不写）。
 */
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createHash } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/http', async () => await import('./nodeHttp'))
vi.mock('@/components/workpaper/headless/registry', async () => {
  const fw = await import('@/components/workpaper/headless/headlessFramework')
  const http = (await import('@/utils/http')).default  // 与真实 provider 同一写法：别名换成 nodeHttp
  const zz = fw.defineHeadlessProvider({
    prefix: 'ZZ-',
    setup: ({ responses }) => ({ rows: [...responses.keys()] }),
    build: (inst) => ['五、1', '五、2'].map((section_id) => ({
      section_id, sheet_name: '附注披露信息(上市公司)', current_standard: 'listed_standalone', wp_id: 'wp-zz',
      sub_table_data: { 表一: inst.rows.map((label) => ({ label, end_amount: 1 })) },
    })),
  })
  const yy = fw.defineHeadlessProvider({  // 越界 provider：想改底稿 ⇒ 名单拦下、不发出
    prefix: 'YY-',
    setup: () => ({}),
    build: () => ({ section_id: '五、3' }),
    post: async () => {
      await http.post('/api/workpapers/wp-yy/checklist-responses', { item_id: 'YY-a', remark: '改底稿' })
      return { section: '五、3', rows: 1 }
    },
  })
  return { HEADLESS_PROVIDERS: { ZZ: async () => zz, YY: async () => yy } }
})

const { configureNodeHttp, PASS, HEADLESS_USER_AGENT } = await import('./nodeHttp')
const nodeHttp = (await import('./nodeHttp')).default
const { refreshNotes, headlessWriteAllowlist } = await import('./entry')
const { checkBuild } = await import('./buildCheck.mjs')
const { runCommand } = await import('./run.mjs')

const P = '11111111-2222-4333-8444-555555555555'
const BASE = 'http://127.0.0.1:9987'
const TOKEN = 'tkn-短期令牌'

interface Seen { method: string; path: string; query: Record<string, string>; headers: Record<string, string>; body: any }
let seen: Seen[] = []

function section(sectionId: string, code: string, state: { synced_before: boolean; manual_values: number }) {
  return {
    section: sectionId, wp_codes: [code], wp_ids: { [code]: `wp-${code.toLowerCase()}` }, push_wp_codes: [],
    unsupported_wp_codes: [], written: 0, unchanged: 0, kept: 0, skipped: 0, reasons: [], exists: true, ...state,
  }
}

const PREPARE = {
  phase: 'prepare', synced: 1, skipped: 0, skipped_never_synced: 1, variant: 'listed', applicable_standards: [],
  push: { ran: false, error: null, wp_codes: [], written: 0, kept: 0, skipped: 0, run_id: null, warnings: [] },
  sections: [
    section('五、1', 'ZZ', { synced_before: true, manual_values: 0 }),
    section('五、2', 'ZZ', { synced_before: false, manual_values: 3 }),
    section('五、3', 'YY', { synced_before: true, manual_values: 0 }),
  ],
}

function answer(method: string, path: string, query: Record<string, string>, body: any): unknown {
  if (path === `/api/disclosure-notes/${P}/2025/pull-from-workpapers`) {
    return query.phase === 'prepare' ? PREPARE : { ...PREPARE, phase: 'push', push: { ...PREPARE.push, ran: true } }
  }
  if (method === 'GET' && /^\/api\/workpapers\/wp-(zz|yy)\/checklist-responses$/.test(path)) {
    const code = path.includes('wp-zz') ? 'ZZ' : 'YY'
    return [{ item_id: `${code}-a`, remark: '1' }, { item_id: 'OTHER-x', remark: '别的底稿' }]
  }
  if (path === `/api/projects/${P}/disclosure-notes/sync-from-workpaper`) {
    return { section_id: body.section_id, rows_synced: body.sub_table_data.表一.length, push_kept: [{}] }
  }
  if (path.endsWith('/refresh-from-workpapers') || path.endsWith('/refresh-from-workpaper')) return { refreshed: 2 }
  return null
}

async function fakeFetch(input: string, init: { method: string; headers: Record<string, string>; body?: string }) {
  const url = new URL(input)
  const body = init.body ? JSON.parse(init.body) : null
  const query = Object.fromEntries(url.searchParams.entries())
  seen.push({ method: init.method, path: url.pathname, query, headers: init.headers, body })
  const data = answer(init.method, decodeURIComponent(url.pathname), query, body)
  const status = data === null ? 404 : 200
  const payload = data === null ? { detail: `没有这个端点：${url.pathname}` } : { code: 200, message: 'ok', data }
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } })
}

function configure(scope: { projectId: string; year: number; section?: string | null }) {
  configureNodeHttp({
    baseUrl: BASE, token: TOKEN, clientInstance: 'headless-node-test',
    allowWrite: headlessWriteAllowlist([scope]),
  })
}

beforeEach(() => {
  seen = []
  vi.stubGlobal('fetch', vi.fn(fakeFetch))
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('refreshNotes（Node 执行器编排）', () => {
  it('prepare → 离屏同步 → push → 重算，首次同步保护与写请求名单都生效', async () => {
    configure({ projectId: P, year: 2025 })
    const run: any = await refreshNotes({ projectId: P, year: 2025, section: null })

    const writes = seen.filter((s) => s.method !== 'GET').map((s) => `${s.path}${s.query.phase ? `?${s.query.phase}` : ''}`)
    expect(writes).toEqual([
      `/api/disclosure-notes/${P}/2025/pull-from-workpapers?prepare`,
      `/api/projects/${P}/disclosure-notes/sync-from-workpaper`,
      `/api/disclosure-notes/${P}/2025/pull-from-workpapers?push`,
      `/api/disclosure-notes/${P}/2025/refresh-from-workpapers`,
    ])
    const synced = seen.filter((s) => s.path.endsWith('/sync-from-workpaper')).map((s) => s.body.section_id)
    expect(synced).toEqual(['五、1'])  // 五、2：从未由底稿同步且有 3 格人工填写 ⇒ 不写
    expect(seen.some((s) => s.method !== 'GET' && s.path.includes('/checklist-responses'))).toBe(false)

    const byKey = Object.fromEntries(run.outcomes.map((o: any) => [`${o.wpCode} ${o.section}`, o]))
    expect(byKey['ZZ 五、1']).toMatchObject({ status: 'synced', rows: 1, kept: 1 })
    expect(byKey['ZZ 五、2'].status).toBe('skipped')
    expect(byKey['ZZ 五、2'].message).toContain('已有 3 格人工填写')
    expect(byKey['YY 五、3'].status).toBe('failed')
    expect(byKey['YY 五、3'].message).toContain('离屏执行器不发这类写请求')
    expect(run).toMatchObject({ ok: true, stage: 'done', refresh: { refreshed: 2 } })

    for (const s of seen) {
      expect(s.headers.Authorization).toBe(`Bearer ${TOKEN}`)
      expect(s.headers['User-Agent']).toBe(HEADLESS_USER_AGENT)
      expect(Boolean(s.headers['X-Client-Instance'])).toBe(s.method !== 'GET')
    }
  })

  it('单章节刷新：prepare 带章节、最后调本章节的重算端点', async () => {
    configure({ projectId: P, year: 2025, section: '五、1' })
    const run: any = await refreshNotes({ projectId: P, year: 2025, section: '五、1' })
    expect(seen[0].query).toMatchObject({ phase: 'prepare', note_section: '五、1' })
    const last = seen[seen.length - 1]
    expect(decodeURIComponent(last.path)).toBe(`/api/disclosure-notes/${P}/2025/五、1/refresh-from-workpaper`)
    expect(run.ok).toBe(true)
  })

  it('写请求名单只认本次运行的项目 / 年度 / 章节', () => {
    const allow = headlessWriteAllowlist([{ projectId: P, year: 2025, section: '五、1' }])
    const ok = (method: string, url: string) => allow({ method, url, body: null })
    expect(ok('POST', `/api/projects/${P}/disclosure-notes/sync-batch-from-workpaper`)).toBe(true)
    expect(ok('POST', `/api/disclosure-notes/${P}/2025/pull-from-workpapers?phase=push`)).toBe(true)
    expect(ok('POST', `/api/projects/other/disclosure-notes/sync-from-workpaper`)).toBe(false)
    expect(ok('POST', `/api/disclosure-notes/${P}/2024/refresh-from-workpapers`)).toBe(false)
    expect(ok('POST', `/api/disclosure-notes/${P}/2025/${encodeURIComponent('五、2')}/refresh-from-workpaper`)).toBe(false)
    expect(ok('PUT', `/api/projects/${P}/disclosure-notes/sync-from-workpaper`)).toBe(false)
    expect(ok('POST', `/api/workpapers/wp-zz/checklist-responses`)).toBe(false)
  })
})

describe('run.mjs runCommand（后端拉起的命令行，入口换成源码版）', () => {
  const env = { GT_HEADLESS_TOKEN: TOKEN, GT_HEADLESS_API_BASE: BASE }
  const fresh = () => ({ ok: true as const, files: 1 })
  const loadEntry = () => import('./entry')

  it('refresh：写请求名单由命令行接上，结果写 --out', async () => {
    const out = join(mkdtempSync(join(tmpdir(), 'gt-headless-run-')), 'result.json')
    const code = await runCommand(['refresh', '--project', P, '--year', '2025', '--out', out],
      { env, verifyBuild: fresh, loadEntry, stdout: () => {}, stderr: () => {} })
    expect(code).toBe(0)
    const result = JSON.parse(readFileSync(out, 'utf8'))
    expect(result).toMatchObject({ ok: true, stage: 'done' })
    expect(result.outcomes.find((o: any) => o.wpCode === 'YY').message).toContain('离屏执行器不发这类写请求')
    expect(seen.some((s) => s.method !== 'GET' && s.path.includes('/checklist-responses'))).toBe(false)
    expect(JSON.stringify(result)).not.toContain(TOKEN)
  })

  it('capture：只放行 prepare，同步载荷记下不发出', async () => {
    const printed: string[] = []
    const code = await runCommand(['capture', '--project', P, '--year', '2025'],
      { env, verifyBuild: fresh, loadEntry, stdout: (t) => printed.push(t), stderr: () => {} })
    expect(code).toBe(0)
    const result = JSON.parse(printed.join(''))
    expect(result.stage).toBe('headless')
    expect(result.captured.map((c: any) => c.body.section_id)).toEqual(['五、1'])
    expect(seen.filter((s) => s.method !== 'GET').map((s) => s.query.phase)).toEqual(['prepare'])
  })

  it('构建过期 / 参数错误 / 非环回地址：分别退出 3 / 2 / 1，过期时不加载入口', async () => {
    const errors: string[] = []
    const entry = vi.fn(loadEntry)
    const stale = () => ({ ok: false as const, reason: '离屏执行器构建产物已过期：构建后有 1 个源文件改动', changed: ['src/a.ts'] })
    expect(await runCommand(['refresh', '--project', P, '--year', '2025'],
      { env, verifyBuild: stale, loadEntry: entry, stderr: (t) => errors.push(t) })).toBe(3)
    expect(entry).not.toHaveBeenCalled()
    expect(errors.join('')).toContain('src/a.ts')
    expect(errors.join('')).toContain('vite.config.ts')
    expect(await runCommand(['refresh', '--project', P], { env, verifyBuild: fresh, loadEntry, stderr: () => {} })).toBe(2)
    expect(await runCommand(['refresh', '--project', P, '--year', '2025'],
      { env: { ...env, GT_HEADLESS_API_BASE: 'http://10.1.2.3:9980' }, verifyBuild: fresh, loadEntry, stderr: () => {} })).toBe(1)
    expect(seen).toHaveLength(0)
  })
})

describe('nodeHttp', () => {
  it('只连环回地址、必须带令牌与写请求名单', () => {
    const base = { token: TOKEN, clientInstance: 'c', allowWrite: () => true }
    expect(() => configureNodeHttp({ ...base, baseUrl: 'http://10.0.0.8:9980' })).toThrow('环回')
    expect(() => configureNodeHttp({ ...base, baseUrl: 'https://127.0.0.1:9980' })).toThrow('环回')
    expect(() => configureNodeHttp({ ...base, baseUrl: BASE, token: '' })).toThrow('令牌')
    expect(() => configureNodeHttp({ baseUrl: BASE, token: TOKEN, clientInstance: 'c' } as any)).toThrow('allowWrite')
  })

  it('只发相对路径；调用方改不了令牌头；信封解包；错误带 detail', async () => {
    configure({ projectId: P, year: 2025 })
    await expect(nodeHttp.get('http://evil.example/x')).rejects.toThrow('相对路径')
    const res: any = await nodeHttp.get('/api/workpapers/wp-zz/checklist-responses', {
      headers: { Authorization: 'Bearer 别人的' },
    })
    expect(res.data[0].item_id).toBe('ZZ-a')
    expect(seen[0].headers.Authorization).toBe(`Bearer ${TOKEN}`)
    const err: any = await nodeHttp.get('/api/nope').catch((e) => e)
    expect(err.response.status).toBe(404)
    expect(err.message).toBe('没有这个端点：/api/nope')
  })

  it('intercept：PASS 照常发出，其余不发、以返回值作响应', async () => {
    configureNodeHttp({
      baseUrl: BASE, token: TOKEN, clientInstance: 'c', allowWrite: () => true,
      intercept: (req) => (String(req.url).includes('pull-from-workpapers') ? PASS : { captured: true }),
    })
    const captured: any = await nodeHttp.post(`/api/projects/${P}/disclosure-notes/sync-from-workpaper`, { section_id: 'x' })
    expect(captured.data).toEqual({ captured: true })
    expect(seen).toHaveLength(0)
    await nodeHttp.post(`/api/disclosure-notes/${P}/2025/pull-from-workpapers`, null, { params: { phase: 'prepare' } })
    expect(seen).toHaveLength(1)
  })
})

describe('checkBuild（构建产物新鲜度）', () => {
  function fixture(content: string) {
    const root = mkdtempSync(join(tmpdir(), 'gt-headless-'))
    mkdirSync(join(root, 'src'), { recursive: true })
    mkdirSync(join(root, 'dist'), { recursive: true })
    writeFileSync(join(root, 'src', 'a.ts'), content)
    writeFileSync(join(root, 'dist', 'entry.mjs'), '')
    const sha256 = createHash('sha256').update('export const a = 1\n').digest('hex')
    writeFileSync(join(root, 'dist', 'source-manifest.json'), JSON.stringify({
      schema: 'headless-disclosure-source-manifest/v1', files: [{ path: 'src/a.ts', sha256 }],
    }))
    return root
  }

  it('源码与构建一致才放行，改过即判过期并点名', () => {
    const fresh = fixture('export const a = 1\n')
    expect(checkBuild(join(fresh, 'dist'), fresh)).toEqual({ ok: true, files: 1 })
    const stale = fixture('export const a = 2\n')
    const verdict: any = checkBuild(join(stale, 'dist'), stale)
    expect(verdict.ok).toBe(false)
    expect(verdict.reason).toContain('已过期')
    expect(verdict.changed).toEqual(['src/a.ts'])
  })

  it('没有构建清单 = 未构建', () => {
    const root = mkdtempSync(join(tmpdir(), 'gt-headless-'))
    mkdirSync(join(root, 'dist'))
    writeFileSync(join(root, 'dist', 'entry.mjs'), '')
    const verdict: any = checkBuild(join(root, 'dist'), root)
    expect(verdict.ok).toBe(false)
    expect(verdict.reason).toContain('尚未构建')
  })
})
