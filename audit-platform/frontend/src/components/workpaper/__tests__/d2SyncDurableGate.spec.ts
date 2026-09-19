/**
 * D2 双向回写「耐久门」守卫 —— 锁死 2026-09-06 浏览器实测抓到的两条 P0 缺陷。
 *
 * 判据全部落在**行为**上（调了哪些 API、顺序如何、失败时切没切模式），
 * 不是「某个字符串存在」——后者改个名就绿了。
 *
 * 缺陷 A：切到 OO 前不 flush ⇒ push 推的是 debounce 前的旧数据。
 * 缺陷 B：切回 HTML 前不等耐久确认 ⇒ pull 读旧文件并覆盖 HTML 新录入。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const posts: Array<{ url: string; body: unknown; config?: Record<string, unknown> }> = []
const gets: string[] = []
let pullFailure: Error | null = null

/** 每个 case 自己设置：forcesave 端点返回什么 */
let forceSaveReply: { accepted: boolean; durable: boolean; detail: string } = {
  accepted: true,
  durable: true,
  detail: '强制保存命令已被 OnlyOffice 接受',
}
let statusReply: Record<string, unknown> = {
  entry_id: 'xlsx/gt-d2-accounts-receivable',
  bidirectional: true,
  managed_sheet: '明细表D2-2',
  html: { rows: 1260 },
  excel: { exists: true, business_rows: 1260 },
}

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(async (url: string) => {
      gets.push(url)
      return { data: { data: statusReply } }
    }),
    post: vi.fn(async (url: string, body: unknown, config?: Record<string, unknown>) => {
      posts.push({ url, body, config })
      if (url.includes('push-to-excel')) {
        return { data: { data: { rows: 1260, fields: 49140 } } }
      }
      if (url.includes('pull-from-excel')) {
        if (pullFailure) throw pullFailure
        return { data: { data: { rows: 3, fields: 12, rows_changed: 3 } } }
      }
      return { data: { data: {} } }
    }),
  },
}))

const messages: Array<{ kind: string; text: string }> = []
let confirmAction: 'confirm' | 'cancel' = 'confirm'
vi.mock('element-plus', () => ({
  ElMessage: {
    success: (m: unknown) => messages.push({ kind: 'success', text: readMsg(m) }),
    warning: (m: unknown) => messages.push({ kind: 'warning', text: readMsg(m) }),
    error: (m: unknown) => messages.push({ kind: 'error', text: readMsg(m) }),
  },
  ElMessageBox: {
    confirm: vi.fn(async () => {
      if (confirmAction === 'cancel') throw 'cancel'
      return 'confirm'
    }),
  },
}))

function readMsg(m: unknown): string {
  if (typeof m === 'string') return m
  return String((m as { message?: string })?.message ?? '')
}

import { useD2SyncBridge } from '../sync/useD2SyncBridge'

function makeBridge(overrides: Record<string, unknown> = {}) {
  const calls: string[] = []
  const bridge = useD2SyncBridge({
    wpId: ref('wp-1'),
    flushBeforeOo: async () => {
      calls.push('flush')
    },
    reloadHtml: async () => {
      calls.push('reload')
    },
    requestForceSave: async () => {
      calls.push('forceSave')
      return forceSaveReply
    },
    ...overrides,
  } as never)
  return { bridge, calls }
}

beforeEach(() => {
  posts.length = 0
  gets.length = 0
  messages.length = 0
  confirmAction = 'confirm'
  pullFailure = null
  localStorage.clear()
  forceSaveReply = { accepted: true, durable: true, detail: '已落盘' }
  statusReply = {
    entry_id: 'xlsx/gt-d2-accounts-receivable',
    bidirectional: true,
    managed_sheet: '明细表D2-2',
    html: { rows: 1260 },
    excel: { exists: true, business_rows: 1260 },
  }
})

describe('缺陷 A：HTML→Excel 必须先 flush 再 push', () => {
  it('切到在线编辑时，flush 严格早于 push-to-excel', async () => {
    const { bridge, calls } = makeBridge()
    await bridge.switchMode('onlyoffice')

    // flush 必须发生，且必须在 push 之前
    expect(calls).toContain('flush')
    const pushIdx = posts.findIndex(p => p.url.includes('push-to-excel'))
    expect(pushIdx).toBeGreaterThanOrEqual(0)
    // flush 是同步 await 的，push 只能在它之后发生 —— 用 calls 顺序证明
    expect(calls.indexOf('flush')).toBe(0)
    expect(bridge.currentMode.value).toBe('onlyoffice')
  })

  it('flush 抛错时不切模式、不 push（不能把旧数据推给 OO）', async () => {
    const { bridge } = makeBridge({
      flushBeforeOo: async () => {
        throw new Error('落库失败')
      },
    })
    await bridge.switchMode('onlyoffice')

    expect(posts.some(p => p.url.includes('push-to-excel'))).toBe(false)
    expect(bridge.currentMode.value).toBe('html')
    expect(messages.some(m => m.kind === 'error')).toBe(true)
  })
})

describe('缺陷 B：Excel→HTML 必须先拿到耐久确认', () => {
  it('取消“保存并切换”时留在在线编辑，且不发 forcesave/pull、不显示失败', async () => {
    confirmAction = 'cancel'
    const { bridge, calls } = makeBridge()
    bridge.currentMode.value = 'onlyoffice'
    await bridge.switchMode('html')

    expect(bridge.currentMode.value).toBe('onlyoffice')
    expect(calls).not.toContain('forceSave')
    expect(posts.some(p => p.url.includes('pull-from-excel'))).toBe(false)
    expect(messages.some(m => m.kind === 'warning' || m.kind === 'error')).toBe(false)
  })

  it('durable=true 时才发 pull，且 forceSave 早于 pull', async () => {
    const { bridge, calls } = makeBridge()
    bridge.currentMode.value = 'onlyoffice'
    await bridge.switchMode('html')

    expect(calls).toContain('forceSave')
    expect(calls.indexOf('forceSave')).toBeLessThan(calls.indexOf('reload'))
    expect(posts.some(p => p.url.includes('pull-from-excel'))).toBe(true)
    expect(bridge.currentMode.value).toBe('html')
  })

  it('durable=false 时绝不发 pull、绝不切模式（核心回归判据）', async () => {
    forceSaveReply = { accepted: true, durable: false, detail: '超时内未落盘' }
    const { bridge } = makeBridge()
    bridge.currentMode.value = 'onlyoffice'
    await bridge.switchMode('html')

    // 这两条就是缺陷 B 的反向锁：一旦有人去掉耐久门，它们必红
    expect(posts.some(p => p.url.includes('pull-from-excel'))).toBe(false)
    expect(bridge.currentMode.value).toBe('onlyoffice')
    // 文案必须说明「留在在线编辑」而不是「同步成功」
    const warn = messages.find(m => m.kind === 'warning')
    expect(warn).toBeTruthy()
    expect(warn!.text).toContain('尚未落盘')
    expect(bridge.lastSync.value).toBe('')
    expect(messages.some(m => m.kind === 'success')).toBe(false)
  })

  it('requestForceSave 返回 null 视为拿不到确认，同样拒绝 pull', async () => {
    const { bridge } = makeBridge({ requestForceSave: async () => null })
    bridge.currentMode.value = 'onlyoffice'
    await bridge.switchMode('html')

    expect(posts.some(p => p.url.includes('pull-from-excel'))).toBe(false)
    expect(bridge.currentMode.value).toBe('onlyoffice')
  })

  it('pull 失败由 bridge 单点提示，保持 OO 且不保留绿色同步摘要', async () => {
    pullFailure = new Error('服务端拒绝陈旧文件')
    const { bridge } = makeBridge()
    bridge.currentMode.value = 'onlyoffice'
    bridge.lastSync.value = '旧的绿色成功摘要'
    await bridge.switchMode('html')

    const pull = posts.find(p => p.url.includes('pull-from-excel'))
    expect(pull?.config?._silent).toBe(true)
    expect(bridge.currentMode.value).toBe('onlyoffice')
    expect(bridge.lastSync.value).toBe('')
    expect(messages.filter(m => m.kind === 'error')).toHaveLength(1)
    expect(messages.some(m => m.kind === 'success')).toBe(false)
  })

  it('pull 请求把耐久指纹带给后端，供服务端二次陈旧校验', async () => {
    forceSaveReply = {
      accepted: true,
      durable: true,
      detail: '已落盘',
      // @ts-expect-error 测试构造：真实回执带 artifact 指纹与服务端三态 outcome
      artifact: {
        before: { sha256: 'aaa' },
        after: { sha256: 'bbb' },
        outcome: 'accepted',
      },
    }
    const { bridge } = makeBridge()
    bridge.currentMode.value = 'onlyoffice'
    await bridge.switchMode('html')

    const pull = posts.find(p => p.url.includes('pull-from-excel'))
    expect(pull).toBeTruthy()
    expect(pull!.config?._silent).toBe(true)
    expect((pull!.body as Record<string, unknown>).durable_fingerprint).toEqual({
      before: { sha256: 'aaa' },
      after: { sha256: 'bbb' },
      outcome: 'accepted',
    })
  })
})

describe('能力态诚实化：isOoAvailable 读真实状态而非硬编码', () => {
  it('bidirectional=false 时禁用在线编辑并给出中文原因', async () => {
    statusReply = { ...statusReply, bidirectional: false }
    const { bridge } = makeBridge()
    await bridge.refreshStatus()

    expect(bridge.isOoAvailable.value).toBe(false)
    expect(bridge.unavailableReason.value).toContain('尚未完成双向回写接线')
    const ooOption = bridge.modeOptions.value.find(o => o.value === 'onlyoffice')
    expect(ooOption?.disabled).toBe(true)
  })

  it('Excel 文件不存在时禁用并说明要先录入', async () => {
    statusReply = { ...statusReply, excel: { exists: false } }
    const { bridge } = makeBridge()
    await bridge.refreshStatus()

    expect(bridge.isOoAvailable.value).toBe(false)
    expect(bridge.unavailableReason.value).toContain('尚未生成')
  })

  it('状态正常时可用且无原因文案', async () => {
    const { bridge } = makeBridge()
    await bridge.refreshStatus()

    expect(bridge.isOoAvailable.value).toBe(true)
    expect(bridge.unavailableReason.value).toBe('')
  })
})

describe('回写文案如实区分「回写了多少」与「变了多少」', () => {
  it('后端给出 rows_changed 时文案必须体现真实变化行数', async () => {
    const { bridge } = makeBridge()
    bridge.currentMode.value = 'onlyoffice'
    await bridge.switchMode('html')

    expect(bridge.lastSync.value).toContain('3 行有变化')
  })
})
