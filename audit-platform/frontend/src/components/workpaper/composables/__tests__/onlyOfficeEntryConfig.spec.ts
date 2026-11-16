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


// ═══════════════════════════════════════════════════════════════════════════
// task 3.1：binding 三态（migrated / pending / out_of_scope）
//
// 🔴 为什么需要这三条：`available` 一个布尔无法区分
//   * 「已 migrated 但供给暂时不就绪」→ 等供给恢复，**不能**回退旧式（会造第二个 doc key）
//   * 「binding pending 从未迁移」→ 本来就能用独立在线编辑，判成不可用会让入口打不开
// 二者都会让 `available=false`，但下一步动作完全相反。
// ═══════════════════════════════════════════════════════════════════════════

describe('task 3.1：binding 三态', () => {
  it('migrated + 供给就绪 ⇒ room 协议，syncMode=bound', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({
            entry_id: 'xlsx/gt-k11-asset-impairment-loss',
            status: 'migrated',
            room_ready: true,
            reason: null,
            sync_mode: 'bound',
          }),
        )
      }
      throw new Error(`不该调旧端点：${url}`)
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'p', wpId: 'w', sheetName: 'K11-1',
    })
    expect(probe.protocol).toBe('room')
    expect(probe.available).toBe(true)
    expect(probe.bindingStatus).toBe('migrated')
    expect(probe.syncMode).toBe('bound')
    const called = get.mock.calls.map((c) => String(c[0]))
    expect(called.some((u) => u.includes('onlyoffice-config'))).toBe(false)
  })

  it('migrated + 供给未就绪 ⇒ **不回退旧式**，给原因且 syncMode 仍为 bound', async () => {
    // 回退旧式会让新旧两个 doc key 同时存在（双写）—— 这是本 spec 要消灭的事故本身。
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({
            entry_id: 'xlsx/gt-k11-asset-impairment-loss',
            status: 'migrated',
            room_ready: false,
            reason: '该版本冻结的受管结构与当前实测不一致。',
          }),
        )
      }
      throw new Error(`migrated 竟回退旧端点：${url}`)
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'p', wpId: 'w', sheetName: 'K11-1',
    })
    expect(probe.protocol).toBe('room')
    expect(probe.available).toBe(false)
    expect(probe.reason).toContain('受管结构')
    expect(probe.syncMode).toBe('bound')
  })

  it('pending ⇒ 走旧式但标 independent（**不是**不可用）', async () => {
    // 🔴 关键：`room_ready` 故意设 **true**。pending 与「供给就绪」可以同时成立
    // （映射未审核但 room 技术可用），此时**必须**仍走独立在线编辑 —— binding 是
    // 权威判定。首版用 `room_ready: false` 写这条，pending 被误判成 bound 时也走 legacy
    // ⇒ 变异存活（实测 M1）。改 true 之后两种实现才可区分。
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({
            entry_id: null,
            status: 'pending',
            room_ready: true,
            reason: null,
          }),
        )
      }
      return Promise.resolve(
        envelope({
          config: { document: { key: 'k' } },
          sync_mode: 'independent',
          binding_status: 'pending',
        }),
      )
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'p', wpId: 'w', sheetName: 'K11-1',
    })
    expect(probe.protocol).toBe('legacy')
    expect(probe.available).toBe(true)
    expect(probe.syncMode).toBe('independent')
    // 界面据此显示「独立在线编辑（不同步）」而不是「已同步」。
    expect(probe.reason).toBeNull()
    expect(probe.entryId).toBeNull()
  })

  it('out_of_scope ⇒ 同 pending：可用但 independent', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({ entry_id: null, status: 'out_of_scope', room_ready: false, reason: null }),
        )
      }
      // 🔴 `sync_mode` / `binding_status` 在**响应顶层**（与 config 平级），不在 config 内部。
      return Promise.resolve(
        envelope({
          config: { document: {} },
          sync_mode: 'independent',
          binding_status: 'out_of_scope',
        }),
      )
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'p', wpId: 'w', sheetName: 'doc.docx',
    })
    expect(probe.available).toBe(true)
    expect(probe.syncMode).toBe('independent')
    expect(probe.bindingStatus).toBe('out_of_scope')
  })

  it('服务端给未知 status ⇒ 归 null，不静默当 pending', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({ entry_id: null, status: 'some_future_state', room_ready: false, reason: null }),
        )
      }
      return Promise.resolve(envelope({ config: { document: {} } }))
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'p', wpId: 'w', sheetName: 'x',
    })
    expect(probe.bindingStatus).toBeNull()
  })

  it('缺 status 时按 room_ready 判（灰度期兼容）', async () => {
    // `status` 是后端 2.1 新增字段；前后端版本共存时缺它必须仍按 room_ready 工作，
    // 否则灰度期所有已就绪入口都退回旧式。
    get.mockImplementation((url: string) => {
      if (url.includes('/sync/entry-identity')) {
        return Promise.resolve(
          envelope({ entry_id: 'xlsx/e', room_ready: true, reason: null }),
        )
      }
      throw new Error('不该调旧端点')
    })

    const probe = await probeOnlyOfficeEntryConfig({
      projectId: 'p', wpId: 'w', sheetName: 'x',
    })
    expect(probe.protocol).toBe('room')
    expect(probe.available).toBe(true)
  })
})
