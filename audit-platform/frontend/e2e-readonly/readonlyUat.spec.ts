/**
 * 真实项目只读走查（spec trim-generation-plan-followup-optimizations R5.5）。
 *
 * 只认显式环境变量，缺一即跳过；本用例不建账号、不 apply、不写任何数据：
 *   GT_READONLY_UAT_USERNAME / GT_READONLY_UAT_PASSWORD / GT_READONLY_UAT_PROJECT_ID
 * 可选：
 *   GT_READONLY_UAT_BASE_URL  默认 http://127.0.0.1:3030（经 Vite 代理到后端）
 *   GT_READONLY_UAT_PAGES     逗号分隔的页面路径，`{pid}` 占位；默认程序裁剪页 + 底稿列表
 *   GT_READONLY_UAT_ALLOW     追加允许的 API 读路径正则（逗号分隔，匹配 pathname）；未列入的 API GET 一律拦下并报告
 *   GT_READONLY_UAT_PYTHON    服务端核对用的 Python（默认仓库 .venv）
 *
 * 账号须先由 backend/scripts/e2e/provision_readonly_uat_user.py 显式 apply（用户放行后）。登录是唯一控制面例外，
 * 用独立的 APIRequestContext 完成后把令牌注入浏览器；账号不是 readonly 直接失败、不开浏览器。
 * 双证：浏览器防火墙 attemptedWrites 为空 + 服务端 logs 在走查期间零写入（backend/scripts/check/check_readonly_uat_writes.py）。
 */
import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, request as playwrightRequest, test } from '@playwright/test'
import { newGuardedContext, summarizeLog } from './fixtures/readonlyUatGuard'

const env = {
  username: process.env.GT_READONLY_UAT_USERNAME ?? '',
  password: process.env.GT_READONLY_UAT_PASSWORD ?? '',
  projectId: process.env.GT_READONLY_UAT_PROJECT_ID ?? '',
  baseURL: process.env.GT_READONLY_UAT_BASE_URL || 'http://127.0.0.1:3030',
}
const ready = Boolean(env.username && env.password && /^[0-9a-f-]{36}$/i.test(env.projectId))
const HERE = dirname(fileURLToPath(import.meta.url))
const BACKEND_DIR = resolve(HERE, '..', '..', '..', 'backend')
const PYTHON = process.env.GT_READONLY_UAT_PYTHON || resolve(HERE, '..', '..', '..', '.venv', 'Scripts', 'python.exe')
/** 服务端时钟（数据库容器）可能慢于本机：核对窗口往前放宽，账号是专用只读号，放宽只会更严。 */
const SINCE_MARGIN_MS = 10 * 60_000

function escapeRe(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function apiReadAllowlist(projectId: string): RegExp[] {
  const pid = escapeRe(projectId)
  const base = [
    '^/api/users/me$',
    `^/api/projects/${pid}$`,
    `^/api/projects/${pid}/permission-matrix$`,
    `^/api/projects/${pid}/procedure-scope/data-availability$`,
  ]
  const extra = (process.env.GT_READONLY_UAT_ALLOW ?? '').split(',').map((s) => s.trim()).filter(Boolean)
  return [...base, ...extra].map((source) => new RegExp(source))
}

function pages(projectId: string): string[] {
  const raw = process.env.GT_READONLY_UAT_PAGES || '/projects/{pid}/procedures,/projects/{pid}/workpapers'
  return raw.split(',').map((p) => p.trim()).filter(Boolean).map((p) => p.replace(/\{pid\}/g, projectId))
}

function unwrap<T = any>(body: any): T {
  return (body && typeof body === 'object' && 'data' in body && 'code' in body ? body.data : body) as T
}

test.describe('真实项目只读走查（R5.5）', () => {
  test.skip(!ready, '未设置 GT_READONLY_UAT_USERNAME / PASSWORD / PROJECT_ID，跳过（不会自建账号）')

  test('只读账号登录、页面读、零写入双证', async ({ browser }) => {
    const since = new Date(Date.now() - SINCE_MARGIN_MS).toISOString()
    const api = await playwrightRequest.newContext({ baseURL: env.baseURL })
    let tokens!: { access_token: string; refresh_token: string; user: { role: string; username: string } }
    try {
      const login = await api.post('/api/auth/login', { data: { username: env.username, password: env.password } })
      expect(login.status(), '登录失败').toBe(200)
      tokens = unwrap(await login.json())
      expect(tokens.user?.role, '只接受只读专用账号（role=readonly），其他账号直接终止').toBe('readonly')

      const auth = { Authorization: `Bearer ${tokens.access_token}` }
      const project = await api.get(`/api/projects/${env.projectId}`, { headers: auth })
      expect(project.status(), '只读成员读项目详情').toBe(200)
      const matrix = unwrap(await (await api.get(`/api/projects/${env.projectId}/permission-matrix`, { headers: auth })).json())
      expect(matrix.system_role).toBe('readonly')
      expect(matrix.operations, '只读账号不应有任何操作码').toEqual([])
    } finally {
      await api.dispose()
    }

    const { context, log } = await newGuardedContext(browser, {
      appOrigin: env.baseURL,
      apiReadAllowlist: apiReadAllowlist(env.projectId),
    })
    try {
      await context.addInitScript(({ origin, token, refresh, user }) => {
        if (location.origin !== origin) return
        sessionStorage.setItem('token', token)
        sessionStorage.setItem('refreshToken', refresh)
        sessionStorage.setItem('user', JSON.stringify(user))
      }, { origin: new URL(env.baseURL).origin, token: tokens.access_token, refresh: tokens.refresh_token, user: tokens.user })
      const page = await context.newPage()
      for (const path of pages(env.projectId)) {
        await page.goto(`${env.baseURL}${path}`, { waitUntil: 'domcontentloaded' })
        await page.waitForTimeout(3_000)
        expect(new URL(page.url()).pathname, `${path} 被重定向（登录态 / 权限问题）`).toBe(path)
        expect(await page.locator('#app').innerHTML(), `${path} 没有渲染`).not.toBe('')
      }
      await page.waitForTimeout(1_000)
      const summary = summarizeLog(log)
      await test.info().attach('readonly-guard-log.json', {
        body: JSON.stringify(summary, null, 2),
        contentType: 'application/json',
      })
      expect(summary.attemptedWrites, '浏览器发起了写入（已拦下，但只读走查不允许任何写入尝试）').toEqual([])
    } finally {
      await context.close()
    }

    let stdout = ''
    try {
      stdout = execFileSync(PYTHON, ['scripts/check/check_readonly_uat_writes.py', '--username', env.username, '--since', since], {
        cwd: BACKEND_DIR, encoding: 'utf-8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      })
    } catch (error) {
      stdout = String((error as { stdout?: string }).stdout ?? '')
    }
    const serverSide = JSON.parse(stdout.trim().split('\n').pop() || '{}')
    await test.info().attach('server-side-writes.json', { body: JSON.stringify(serverSide, null, 2), contentType: 'application/json' })
    expect(serverSide.error, '服务端核对失败').toBeUndefined()
    expect(serverSide.logs, '服务端在走查期间记到了该账号的成功写入').toBe(0)
  })
})
