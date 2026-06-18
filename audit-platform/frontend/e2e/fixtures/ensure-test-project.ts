/**
 * ensure-test-project.ts — E2E Fixture: 确保测试项目存在
 *
 * 在 E2E 测试运行前调用，验证 PROJECT_ID 对应的项目存在且有必要底稿。
 * 项目 ID 优先读环境变量；本地默认 FIX-B（辽宁卫生）。
 *
 * 运行 seed:
 *   cd backend && python scripts/e2e/seed_fix_projects.py --fix
 *   → 输出 data/e2e_fix_projects.json 中的 env 块
 *
 * 用法：
 *   const fixture = await ensureTestProject(request)
 *   const fixA = await ensureFixtureProject(request, 'FIX-A')
 */
import { type APIRequestContext } from '@playwright/test'

/** FIX-B 默认：辽宁卫生 2025（completion-phase e2e-matrix） */
export const DEFAULT_FIX_B_PROJECT_ID = '37814426-a29e-4fc2-9313-a59d229bf7b0'

export type FixtureKind = 'FIX-A' | 'FIX-B' | 'FIX-INT' | 'FIX-RP'

const ENV_KEYS: Record<FixtureKind, string> = {
  'FIX-A': 'TEST_PROJECT_ID_FIX_A',
  'FIX-B': 'TEST_PROJECT_ID_FIX_B',
  'FIX-INT': 'TEST_PROJECT_ID_FIX_INT',
  'FIX-RP': 'TEST_PROJECT_ID_FIX_RP',
}

/** 通用 TEST_PROJECT_ID；未设时回退 FIX-B */
export const TEST_PROJECT_ID =
  process.env.TEST_PROJECT_ID ||
  process.env.TEST_PROJECT_ID_FIX_B ||
  DEFAULT_FIX_B_PROJECT_ID

export function resolveFixtureProjectId(kind: FixtureKind): string {
  const key = ENV_KEYS[kind]
  const fromEnv = process.env[key]
  if (fromEnv) return fromEnv
  if (kind === 'FIX-B') return TEST_PROJECT_ID
  return ''
}

export function projectBaseApi(projectId: string): string {
  return `/api/projects/${projectId}`
}

/** @deprecated 使用 projectBaseApi(TEST_PROJECT_ID) */
export const TEST_BASE_API = projectBaseApi(TEST_PROJECT_ID)

export interface TestFixture {
  ready: boolean
  token: string
  projectId: string
  fixture?: FixtureKind
  reason?: string
}

async function login(request: APIRequestContext): Promise<{ ok: boolean; token: string; reason?: string }> {
  try {
    const resp = await request.post('/api/auth/login', {
      data: { username: 'admin', password: 'admin123' },
    })
    if (resp.status() !== 200) {
      return { ok: false, token: '', reason: '后端不可达或 admin 账号不存在' }
    }
    const body = await resp.json()
    const token = body.data?.access_token ?? body.access_token ?? ''
    if (!token) {
      return { ok: false, token: '', reason: '登录成功但未返回 token' }
    }
    return { ok: true, token }
  } catch (e) {
    return { ok: false, token: '', reason: `登录失败: ${e}` }
  }
}

/**
 * 获取 auth token + 验证项目存在
 */
export async function ensureTestProject(
  request: APIRequestContext,
  projectId: string = TEST_PROJECT_ID,
): Promise<TestFixture> {
  const loginResult = await login(request)
  if (!loginResult.ok) {
    return {
      ready: false,
      token: '',
      projectId,
      reason: loginResult.reason,
    }
  }

  const token = loginResult.token

  try {
    const projResp = await request.get(`/api/projects/${projectId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (projResp.status() === 404) {
      return {
        ready: false,
        token,
        projectId,
        reason:
          `测试项目 ${projectId} 不存在。请先运行 backend/scripts/e2e/seed_fix_projects.py --fix`,
      }
    }
  } catch {
    return { ready: false, token, projectId, reason: '项目查询失败' }
  }

  return { ready: true, token, projectId }
}

/**
 * 按 e2e-matrix 夹具类型解析项目 ID 并校验存在
 */
export async function ensureFixtureProject(
  request: APIRequestContext,
  kind: FixtureKind,
): Promise<TestFixture> {
  const projectId = resolveFixtureProjectId(kind)
  if (!projectId) {
    return {
      ready: false,
      token: '',
      projectId: '',
      fixture: kind,
      reason: `未设置 ${ENV_KEYS[kind]}。请运行 seed_fix_projects.py --fix 并 export 对应 env`,
    }
  }
  const base = await ensureTestProject(request, projectId)
  return { ...base, fixture: kind }
}

/**
 * 验证特定 wp_code 的底稿存在
 */
export async function findWorkpaper(
  request: APIRequestContext,
  token: string,
  wpCode: string,
  projectId: string = TEST_PROJECT_ID,
): Promise<{ exists: boolean; wpId?: string }> {
  try {
    const resp = await request.get(`${projectBaseApi(projectId)}/working-papers`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const body = await resp.json()
    const list = body?.data?.items || body?.items || body?.data || (Array.isArray(body) ? body : [])
    const wp = list.find((w: any) => w.wp_code === wpCode)
    return wp ? { exists: true, wpId: wp.id } : { exists: false }
  } catch {
    return { exists: false }
  }
}
