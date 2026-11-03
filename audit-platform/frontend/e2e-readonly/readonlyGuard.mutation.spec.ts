/**
 * 只读 UAT 防火墙变异测试（spec trim-generation-plan-followup-optimizations R5.6）。
 *
 * 不连任何真实服务：应用源是本机一个没人监听的端口，页面与 API 由「桩服务器」路由应答。防火墙在桩之后注册
 * （Playwright 后注册的路由先执行），只有防火墙放行的请求才到得了桩。页面里逐类发起写入：fetch POST / PUT /
 * PATCH / DELETE、keepalive、XHR、sendBeacon、表单提交、弹窗里的写入、WebSocket，以及未知 API GET、外部域名 GET：
 * - 每一类都被拦下并记入对应清单，桩一条写入都没收到；白名单 GET / HEAD 照常返回；
 * - 反向对照：不装防火墙时同样的探针确实到达桩（探针是真的，守卫不是空转）；
 * - newGuardedContext 建的 context 禁用 Service Worker（对照 context 能注册）。
 */
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test, type Browser, type BrowserContext, type Page, type Route } from '@playwright/test'
import {
  classifyRequest,
  installReadonlyGuard,
  isViteHmrSocket,
  newGuardedContext,
  summarizeLog,
  type ReadonlyGuardOptions,
} from './fixtures/readonlyUatGuard'

const ORIGIN = 'http://127.0.0.1:39999'
const WS_ORIGIN = 'ws://127.0.0.1:39999'
const OPTIONS: ReadonlyGuardOptions = { appOrigin: ORIGIN, apiReadAllowlist: [/^\/api\/allowed$/] }
const PAGE_HTML =
  '<!doctype html><meta charset="utf-8"><title>guard</title>' +
  '<form id="f" method="post" action="/api/form-post"><input name="a" value="1"></form>'

/** 桩服务器：记录真正到达「服务器」的请求（方法 + 路径）。 */
async function installStubServer(context: BrowserContext): Promise<string[]> {
  const served: string[] = []
  await context.route(`${ORIGIN}/**`, async (route: Route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    served.push(`${request.method()} ${pathname}`)
    if (pathname === '/') await route.fulfill({ status: 200, contentType: 'text/html', body: PAGE_HTML })
    else if (pathname === '/sw.js') await route.fulfill({ status: 200, contentType: 'text/javascript', body: '' })
    else await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' })
  })
  return served
}

async function guardedWithStub(browser: Browser) {
  const context = await browser.newContext({ serviceWorkers: 'block' })
  const served = await installStubServer(context) // 先挂桩
  const log = await installReadonlyGuard(context, OPTIONS) // 后装防火墙 ⇒ 防火墙先执行
  return { context, served, log }
}

async function runProbes(page: Page, wsOrigin: string): Promise<Record<string, string>> {
  return page.evaluate(async (wsBase) => {
    const results: Record<string, string> = {}
    const tryFetch = async (key: string, url: string, init?: RequestInit) => {
      try {
        const response = await fetch(url, init)
        results[key] = `status ${response.status}`
      } catch {
        results[key] = 'blocked'
      }
    }
    await tryFetch('post', '/api/write-post', { method: 'POST', body: '{}' })
    await tryFetch('put', '/api/write-put', { method: 'PUT', body: '{}' })
    await tryFetch('patch', '/api/write-patch', { method: 'PATCH', body: '{}' })
    await tryFetch('delete', '/api/write-delete', { method: 'DELETE' })
    await tryFetch('keepalive', '/api/write-keepalive', { method: 'POST', body: 'x', keepalive: true })
    await tryFetch('allowed', '/api/allowed')
    await tryFetch('head_allowed', '/api/allowed', { method: 'HEAD' })
    await tryFetch('unknown_get', '/api/unknown-read')
    await tryFetch('external', 'http://external.invalid/x')
    results.xhr = await new Promise<string>((resolve) => {
      const xhr = new XMLHttpRequest()
      xhr.open('PUT', '/api/write-xhr')
      xhr.onload = () => resolve(`status ${xhr.status}`)
      xhr.onerror = () => resolve('blocked')
      xhr.send('{}')
    })
    results.beacon = String(navigator.sendBeacon('/api/write-beacon', 'x'))
    const socketResult = (url: string) => new Promise<string>((resolve) => {
      const socket = new WebSocket(url)
      socket.onclose = (event) => resolve(`closed ${event.code}`)
      setTimeout(() => resolve('timeout'), 3000)
    })
    results.ws = await socketResult(`${wsBase}/api/ws`)
    results.hmr = await socketResult(`${wsBase}/?token=dev`)
    return results
  }, wsOrigin)
}

async function popupWrite(context: BrowserContext, page: Page): Promise<void> {
  const popupPromise = context.waitForEvent('page')
  await page.evaluate(() => { window.open('/', '_blank') })
  const popup = await popupPromise
  await popup.waitForLoadState('domcontentloaded')
  await popup.evaluate(async () => {
    await fetch('/api/popup-post', { method: 'POST' }).catch(() => undefined)
    await fetch('/api/popup-unknown').catch(() => undefined)
  })
  await popup.close()
}

async function formSubmit(page: Page): Promise<void> {
  await page.evaluate(() => (document.getElementById('f') as HTMLFormElement).submit())
  await page.waitForTimeout(500)
}

test.describe('只读 UAT 防火墙（R5.6）', () => {
  test('classifyRequest：只放行同源静态资源与白名单 API 读', () => {
    expect(classifyRequest('GET', `${ORIGIN}/src/main.ts`, OPTIONS)).toBe('allow')
    expect(classifyRequest('HEAD', `${ORIGIN}/api/allowed`, OPTIONS)).toBe('allow')
    expect(classifyRequest('get', `${ORIGIN}/api/allowed?x=1`, OPTIONS)).toBe('allow')
    expect(classifyRequest('GET', `${ORIGIN}/api/allowed/more`, OPTIONS)).toBe('blocked_read')
    expect(classifyRequest('GET', `${ORIGIN}/api`, OPTIONS)).toBe('blocked_read')
    expect(classifyRequest('GET', 'http://127.0.0.1:40000/x', OPTIONS)).toBe('external')
    expect(classifyRequest('GET', 'https://127.0.0.1:39999/x', OPTIONS)).toBe('external')
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'PROPFIND']) {
      expect(classifyRequest(method, `${ORIGIN}/src/main.ts`, OPTIONS), method).toBe('write')
      expect(classifyRequest(method, 'http://external.invalid/x', OPTIONS), method).toBe('write')
    }
    expect(isViteHmrSocket(`${WS_ORIGIN}/?token=abc`, ORIGIN)).toBe(true)
    expect(isViteHmrSocket(`${WS_ORIGIN}/api/ws?token=abc`, ORIGIN)).toBe(false)
    expect(isViteHmrSocket('ws://other.invalid/?token=abc', ORIGIN)).toBe(false)
  })

  test('每一类写入都被拦下并记录，桩服务器收不到任何写入', async ({ browser }) => {
    const { context, served, log } = await guardedWithStub(browser)
    try {
      const page = await context.newPage()
      await page.goto(`${ORIGIN}/`)
      const results = await runProbes(page, WS_ORIGIN)
      await popupWrite(context, page)
      await formSubmit(page)
      const expectedWrites = new Set([
        `POST ${ORIGIN}/api/write-post`, `PUT ${ORIGIN}/api/write-put`, `PATCH ${ORIGIN}/api/write-patch`,
        `DELETE ${ORIGIN}/api/write-delete`, `POST ${ORIGIN}/api/write-keepalive`, `PUT ${ORIGIN}/api/write-xhr`,
        `POST ${ORIGIN}/api/write-beacon`, `WEBSOCKET ${WS_ORIGIN}/api/ws`, `POST ${ORIGIN}/api/popup-post`,
        `POST ${ORIGIN}/api/form-post`,
      ])
      await expect.poll(() => new Set(summarizeLog(log).attemptedWrites).size, { timeout: 5000 }).toBe(expectedWrites.size)
      const summary = summarizeLog(log)
      expect(new Set(summary.attemptedWrites)).toEqual(expectedWrites)
      expect(new Set(summary.blockedReads)).toEqual(new Set([
        `GET ${ORIGIN}/api/unknown-read`, `GET ${ORIGIN}/api/popup-unknown`]))
      expect(summary.blockedExternal).toEqual(['GET http://external.invalid/x'])
      expect(summary.blockedInfra).toEqual([`WEBSOCKET ${WS_ORIGIN}/`])
      expect(results).toMatchObject({
        post: 'blocked', put: 'blocked', patch: 'blocked', delete: 'blocked', keepalive: 'blocked', xhr: 'blocked',
        allowed: 'status 200', head_allowed: 'status 200', unknown_get: 'blocked', external: 'blocked',
      })
      expect(results.ws).toMatch(/^closed /)
      expect(served.filter((line) => !/^(GET|HEAD) /.test(line)), '桩服务器不得收到任何写入').toEqual([])
      expect(new Set(served)).toEqual(new Set(['GET /', 'GET /api/allowed', 'HEAD /api/allowed']))
    } finally {
      await context.close()
    }
  })

  test('反向对照：不装防火墙时同样的探针确实到达服务器（守卫不是空转）', async ({ browser }) => {
    const context = await browser.newContext({ serviceWorkers: 'block' })
    const served = await installStubServer(context)
    try {
      const page = await context.newPage()
      await page.goto(`${ORIGIN}/`)
      const results = await runProbes(page, WS_ORIGIN)
      await popupWrite(context, page)
      await formSubmit(page)
      const expected = [
        'POST /api/write-post', 'PUT /api/write-put', 'PATCH /api/write-patch', 'DELETE /api/write-delete',
        'POST /api/write-keepalive', 'PUT /api/write-xhr', 'POST /api/write-beacon', 'GET /api/unknown-read',
        'POST /api/popup-post', 'GET /api/popup-unknown', 'POST /api/form-post',
      ]
      await expect.poll(() => expected.filter((line) => !served.includes(line)), { timeout: 5000 }).toEqual([])
      expect(results.post).toBe('status 200')
    } finally {
      await context.close()
    }
  })

  test('newGuardedContext 禁用 Service Worker，对照 context 可以注册', async ({ browser }) => {
    // Service Worker 脚本由浏览器自己取、不走页面路由 ⇒ 用测试进程内的临时 HTTP 服务（只给 / 与 /sw.js，用完即关）
    const server = createServer((request, response) => {
      const isWorker = request.url === '/sw.js'
      response.writeHead(200, { 'content-type': isWorker ? 'text/javascript' : 'text/html; charset=utf-8' })
      response.end(isWorker ? '' : PAGE_HTML)
    })
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
    const origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
    const register = async (context: BrowserContext) => {
      const page = await context.newPage()
      await page.goto(`${origin}/`)
      // Playwright 的 block 把 register 换成空实现（照样 resolve、但不返回注册对象），所以看注册结果与已注册列表
      return page.evaluate(async () => {
        if (!('serviceWorker' in navigator)) return 'unsupported'
        try {
          const registration = await navigator.serviceWorker.register('/sw.js')
          const registrations = await navigator.serviceWorker.getRegistrations()
          return `${registration ? 'registered' : 'blocked'}:${registrations.length}`
        } catch (error) {
          return `rejected: ${(error as Error).name}`
        }
      })
    }
    const { context: guarded, log } = await newGuardedContext(browser, { ...OPTIONS, appOrigin: origin })
    const control = await browser.newContext({ serviceWorkers: 'allow' })
    try {
      const allowed = await register(control)
      const blocked = await register(guarded)
      expect(allowed, '对照 context 能注册，说明探针有效').toBe('registered:1')
      expect(blocked).toBe('blocked:0')
      expect(log.attemptedWrites).toEqual([])
    } finally {
      await guarded.close()
      await control.close()
      await new Promise<void>((resolve) => server.close(() => resolve()))
    }
  })
})
