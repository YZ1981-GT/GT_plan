/**
 * `onlyOfficeEntryConfig` —— 在线编辑取配置的唯一入口（spec 任务 2.8 第 ② 步）。
 *
 * 三条臂缺任一条，这类「按状态选协议」的层就会退化成恒走一侧：
 * 1. **room 就绪** ⇒ 判「可切」，**不**调旧端点（证明旧链路真的被绕开）
 * 2. **供给未就绪但有原因** ⇒ 透传原因、判不可切，**不**调旧端点
 * 3. **entry-identity 端点失败 / 无 projectId** ⇒ 回落旧式（fail-open 方向）
 *
 * 臂 2 / 3 是核心：只测臂 1 会让「一律走 room、失败就报不可用」的实现全绿，
 * 而那会让一批 entry 在线编辑整个打不开（Requirement 12.8）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.fn()

vi.mock('@/utils/http', () => ({
  default: { get: (...args: any[]) => get(...args) },
}))

import {
  entryIdentityUrl,
  legacyOnlyOfficeConfigUrl,
  canOpenOnlyOfficeEntry,
  onlyOfficeEntryUnavailableReason,
  probeOnlyOfficeEntryConfig,
} from '../onlyOfficeEntryConfig'

/** 包一层 ResponseWrapperMiddleware 信封（`http` 返回完整响应体）。 */
function envelope(data: any) {
  return { data: { code: 0, message: 'ok', data } }
}

beforeEach(() => {
  get.mockReset()
})

describe('端点拼接（全仓唯一一处）', () => {
  it('旧式端点形状不变（迁移前后调用方拿到的 URL 一致）', () => {
    expect(legacyOnlyOfficeConfigUrl('wp-1', 'D4-8 收入')).toBe(
      '/api/workpapers/wp-1/sheets/D4-8%20%E6%94%B6%E5%85%A5/onlyoffice-config',
    )
  })

  it('entry-identity 端点挂在 sync 下、不带 entry_id 段', () => {
    const url = entryIdentityUrl('proj-1', 'wp-1')
    expect(url).toBe('/api/projects/proj-1/workpapers/wp-1/sync/entry-identity')
    expect(url).not.toContain('/entries/')
  })
})

describe('臂 1：room 供给就绪 ⇒ 判可切且不碰旧端点', () => {
  it('room_ready=true 时走 room，且旧式端点零调用', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({
            entry_id: 'xlsx-sheet/D4-8/D4-8_收入',
            wp_code: 'D4-8',
            room_ready: true,
            reason: null,
            allowed_modes: ['html', 'onlyoffice'],
          }),
        )
      }
      throw new Error(`不该调旧端点：${url}`)
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'proj-1',
      wpId: 'wp-1',
      sheetName: 'D4-8 收入',
    })

    expect(probe.protocol).toBe('room')
    expect(probe.available).toBe(true)
    expect(probe.reason).toBeNull()
    expect(probe.entryId).toBe('xlsx-sheet/D4-8/D4-8_收入')
    const called = get.mock.calls.map((c) => String(c[0]))
    expect(called.some((u) => u.includes('onlyoffice-config'))).toBe(false)
  })
})

describe('臂 2：供给未就绪且给了原因 ⇒ 透传原因，不碰旧端点', () => {
  it('room_ready=false + reason 时直接返回该原因', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({
            entry_id: 'xlsx-sheet/D4-1/__whole__',
            room_ready: false,
            reason: '该版本冻结的受管结构与当前实测不一致。',
            allowed_modes: ['html'],
          }),
        )
      }
      throw new Error(`不该调旧端点：${url}`)
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'proj-1',
      wpId: 'wp-1',
      sheetName: 'D4-1',
    })

    expect(probe.available).toBe(false)
    expect(probe.reason).toBe('该版本冻结的受管结构与当前实测不一致。')
    const called = get.mock.calls.map((c) => String(c[0]))
    expect(called.some((u) => u.includes('onlyoffice-config'))).toBe(false)
  })
})

describe('臂 3：fail-open 到旧式（方向必须是这一侧）', () => {
  it('entry-identity 抛错时回落旧式并成功', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) return Promise.reject(new Error('boom'))
      if (url.includes('onlyoffice-config')) {
        return Promise.resolve(envelope({ config: { document: { key: 'k' } }, token: 't' }))
      }
      throw new Error(`意外 URL：${url}`)
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'proj-1',
      wpId: 'wp-1',
      sheetName: 'D4-1',
    })

    expect(probe.protocol).toBe('legacy')
    expect(probe.available).toBe(true)
    expect(probe.config).not.toBeNull()
    expect(probe.entryId).toBeNull()
  })

  it('没有 projectId 时直接走旧式（不多发一次注定失败的请求）', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('onlyoffice-config')) {
        return Promise.resolve(envelope({ config: { document: {} } }))
      }
      throw new Error(`不该调 ${url}`)
    })

    const probe = await probeOnlyOfficeEntryConfig({ wpId: 'wp-1', sheetName: 'D4-1' })

    expect(probe.protocol).toBe('legacy')
    expect(probe.available).toBe(true)
    const called = get.mock.calls.map((c) => String(c[0]))
    expect(called.some((u) => u.includes('/sync/entry-identity'))).toBe(false)
  })
})

describe('后端已停止签发旧 URL 时给引导文案（2.8 第①步的 409）', () => {
  it('409 legacy_onlyoffice_url_retired ⇒ 可操作中文文案', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(envelope({ entry_id: null, room_ready: false, reason: null }))
      }
      return Promise.reject({
        response: {
          data: {
            detail: {
              error_code: 'legacy_onlyoffice_url_retired',
              message: '该底稿已支持统一在线编辑协议，请改用协同编辑入口打开（旧式编辑器地址已停止签发）',
            },
          },
        },
      })
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'proj-1',
      wpId: 'wp-1',
      sheetName: 'D4-1',
    })

    expect(probe.available).toBe(false)
    expect(probe.reason).toContain('统一在线编辑协议')
  })
})

describe('兼容壳', () => {
  it('canOpenOnlyOfficeEntry 与 probe 结论一致', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(envelope({ entry_id: 'e', room_ready: true, reason: null }))
      }
      throw new Error('unexpected')
    })
    await expect(
      canOpenOnlyOfficeEntry({ projectId: 'p', wpId: 'w', sheetName: 's' }),
    ).resolves.toBe(true)
  })

  it('onlyOfficeEntryUnavailableReason 在可切时返回 null', async () => {
    get.mockImplementation(() =>
      Promise.resolve(envelope({ entry_id: 'e', room_ready: true, reason: null })),
    )
    await expect(
      onlyOfficeEntryUnavailableReason({ projectId: 'p', wpId: 'w', sheetName: 's' }),
    ).resolves.toBeNull()
  })
})
