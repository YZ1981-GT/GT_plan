/**
 * 503 MIGRATION_PENDING（数据库结构未升级）：不重试、提示用后端说明（spec voucher-workflow-linkage-lineage-closure R2）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const notify = vi.hoisted(() => vi.fn())

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(() => ({ close: vi.fn() })), success: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn(), push: vi.fn() } }))
vi.mock('@/utils/feedback', () => ({ feedback: { notify } }))

const PENDING_TEXT = '数据库结构未升级：程序需要 V251，库里最高 V234，还有 17 个迁移未执行。请联系管理员重启后端（启动时会自动执行迁移）'

let http: typeof import('@/utils/http').default
let originalAdapter: unknown

function failure(config: any, status: number, message: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), {
    config,
    response: { status, data: { code: status, message }, headers: {}, config },
    isAxiosError: true,
  })
}

beforeEach(async () => {
  vi.resetModules()
  notify.mockReset()
  http = (await import('@/utils/http')).default
  originalAdapter = http.defaults.adapter
})

afterEach(() => {
  http.defaults.adapter = originalAdapter as any
})

describe('migrationPendingMessage', () => {
  it('只认 503 + MIGRATION_PENDING，信封 message / detail 两处都认', async () => {
    const { migrationPendingMessage } = await import('@/utils/migrationPending')
    const body = { error_code: 'MIGRATION_PENDING', message: PENDING_TEXT }
    expect(migrationPendingMessage({ response: { status: 503, data: { message: body } } })).toBe(PENDING_TEXT)
    expect(migrationPendingMessage({ response: { status: 503, data: { detail: body } } })).toBe(PENDING_TEXT)
    expect(migrationPendingMessage({ response: { status: 500, data: { message: body } } })).toBeNull()
    expect(migrationPendingMessage({ response: { status: 503, data: { message: '服务暂时不可用' } } })).toBeNull()
    // 503 带业务对象但不是迁移未执行（如维护中）：不能说成数据库结构问题
    const other = { error_code: 'SERVICE_UNAVAILABLE', message: '系统维护中' }
    expect(migrationPendingMessage({ response: { status: 503, data: { message: other } } })).toBeNull()
    expect(migrationPendingMessage(new Error('网络'))).toBeNull()
  })
})

describe('http 拦截器', () => {
  it('GET 遇 MIGRATION_PENDING 不重试，通知标题与正文用后端说明', async () => {
    let calls = 0
    http.defaults.adapter = async (config: any) => {
      calls += 1
      throw failure(config, 503, { error_code: 'MIGRATION_PENDING', message: PENDING_TEXT })
    }
    await expect(http.get('/api/projects')).rejects.toBeTruthy()
    expect(calls).toBe(1)
    expect(notify).toHaveBeenCalledTimes(1)
    const arg = notify.mock.calls[0][0]
    expect(arg.title).toBe('数据库结构未升级')
    expect(arg.message).toContain(PENDING_TEXT)
  })
})
