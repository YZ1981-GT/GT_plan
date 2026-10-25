import type { BrowserContext, Route } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { noteHeaderRows } from '../../src/components/consolidation/composables/consolNoteHeaders'

export const syntheticProjectId = 'cp04-offline-project'
const origin = 'http://localhost:3030'
const templateData = Object.fromEntries(['soe', 'listed'].map((standard) => [standard,
  JSON.parse(readFileSync(resolve(process.cwd(), `../../backend/data/consol_note_sections_${standard}.json`), 'utf8')),
])) as Record<string, any[]>

export async function installSyntheticNoteRoutes(context: BrowserContext) {
  const requests: Array<{ method: string; path: string; body: any }> = []
  const blocked: string[] = []
  let activeStandard = 'soe'
  const holds: Array<{ fragment: string; method: string; reached: boolean; promise: Promise<void>; release: () => void }> = []
  const stored = new Map<string, any>()
  const delayNext = (fragment: string, method = 'GET') => {
    let release!: () => void
    const hold = { fragment, method, reached: false, promise: new Promise<void>((r) => { release = r }), release: () => release() }
    holds.push(hold)
    return hold
  }
  const fulfill = async (route: Route, payload: any, status = 200) => {
    const path = decodeURIComponent(new URL(route.request().url()).pathname)
    const hold = holds.find((h) => !h.reached && h.method === route.request().method() && path.includes(h.fragment))
    if (hold) { hold.reached = true; await hold.promise }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ code: status, message: '', data: payload }) }).catch((error) => {
      if (!context.pages().length || String(error).includes('closed') || String(error).includes('intercepted')) return
      throw error
    })
  }
  const makeSection = (standard: string, sectionId: string) => {
    const source = templateData[standard].find((s) => s.section_id === sectionId)
    if (!source) return null
    const result = structuredClone(source)
    result.header_rows = noteHeaderRows(result)
    result._header_row_indexes ||= []
    result.template_type = standard
    const bodyIndex = result._header_row_indexes.length
    result.rows[bodyIndex] = [standard === 'listed' ? '合成上市业务' : '合成国企业务', ...result.headers.slice(1).map((_: unknown, i: number) => String((i + 1) * 101))]
    return result
  }

  await context.addInitScript(() => { (window as any).__CP04_SYNTHETIC_ROUTES__ = true })
  await context.routeWebSocket('**/*', (socket) => { socket.close() })
  // No fetch/fallback: only local static GETs may reach Vite, every API is fulfilled or aborted here.
  await context.route('**/*', async (route) => {
    const request = route.request(), url = new URL(request.url())
    const path = decodeURIComponent(url.pathname), method = request.method()
    if (url.origin !== origin || !['GET', 'HEAD'].includes(method) && !path.startsWith('/api/')) {
      blocked.push(`${method} ${url.href}`); await route.abort('blockedbyclient'); return
    }
    if (!path.startsWith('/api/')) {
      const staticPath = /^\/(e2e\/fixtures\/|src\/|node_modules\/|@vite\/|@id\/|@fs\/|@vite-env(?:$|\/)|favicon\.ico$)/.test(path)
      if (staticPath && ['GET', 'HEAD'].includes(method)) { await route.continue(); return }
      blocked.push(`${method} ${path}`); await route.abort('blockedbyclient'); return
    }
    let body: any = null
    if (method !== 'GET' && request.postData()) body = request.postDataJSON()
    requests.push({ method, path, body })
    const detail = path.match(/^\/api\/consol-note-sections\/(soe|listed)\/(五-5-[23])$/)
    if (method === 'GET' && detail) {
      activeStandard = detail[1]
      await fulfill(route, makeSection(detail[1], detail[2])); return
    }
    const list = path.match(/^\/api\/consol-note-sections\/(soe|listed)$/)
    if (method === 'GET' && list) {
      await fulfill(route, [{ section: '合成章节', children: ['五-5-2', '五-5-3'].map((id) => ({ section_id: id, title: makeSection(list[1], id)?.title })) }]); return
    }
    const data = path.match(/^\/api\/consol-note-sections\/data\/cp04-offline-project\/2025\/(五-5-[23])$/)
    if (data && url.searchParams.get('node_key') === 'G:consol') {
      const scope = { project_id: syntheticProjectId, year: 2025, node_key: 'G:consol', section_id: data[1] }
      if (method === 'GET') {
        await fulfill(route, { ...scope, content: stored.get(`${activeStandard}:${data[1]}`) || {} }); return
      }
      if (method === 'PUT' && ['soe', 'listed'].includes(body?.data?.template_variant)) {
        stored.set(`${body.data.template_variant}:${data[1]}`, structuredClone(body.data))
        await fulfill(route, { ...scope, ok: true }); return
      }
    }
    if (method === 'GET' && /^\/api\/cell-comments\/cp04-offline-project\/2025\/consol_note\/五-5-[23]$/.test(path)) {
      await fulfill(route, []); return
    }
    if (method === 'GET' && /^\/api\/consol-note-sections\/breakdown\/cp04-offline-project\/2025\/五-5-[23]$/.test(path)
      && url.searchParams.get('node_key') === 'G:consol') {
      await fulfill(route, { project_id: syntheticProjectId, year: 2025, section_id: path.split('/').at(-1), node_key: 'G:consol', cells: [] }); return
    }
    if (method === 'GET' && path === '/api/consol-note-formulas' && ['soe', 'listed'].includes(url.searchParams.get('template_type') || '')) {
      await fulfill(route, []); return
    }
    blocked.push(`${method} ${path}`)
    await route.abort('blockedbyclient')
  })
  return { requests, blocked, delayNext, releaseAll: () => holds.forEach((hold) => hold.release()) }
}
