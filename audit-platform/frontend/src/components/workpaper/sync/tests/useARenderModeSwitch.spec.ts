/**
 * useARenderModeSwitch 守卫 —— A 循环统一在线编辑双模式接桥的**行为级**判据。
 *
 * spec: `a-cycle-online-edit-driver-closure`
 *
 * 钉住：
 *  ① 切 docx 真调 `switchToOnlyOffice`（这正是 f20789453 漏掉、守卫
 *     bridgeMaterializeDriven 抓的「空壳」根因）；
 *  ② 四分支保存协议逐条可分辨（applied 秒切 / 未改动丝滑 / 脏可保存 forceSave /
 *     脏不放行放人走且明示未同步）；
 *  ③ `modeOptions` 不因健康未就绪锁死「在线编辑」（D4 bug ③）；
 *  ④ switchMode 竞态兜底：健康未就绪的点击不被静默吞掉（D4 bug ②）；
 *  ⑤ `applied` 虽在 in-flight 集合里，切回 HTML 仍放行（D4 真栈卡死过）；
 *  ⑥ B 类 `beforeEnterOo` 返 false ⇒ 不进 OO（A177 生成 Word 失败不切）。
 *
 * 变异反证：把切 docx 的 `switchToOnlyOffice` 调用删掉（退回 f20789453 的空壳形态），
 * 「① 切 docx 真调 switchToOnlyOffice」用例即打红 —— 与守卫 bridgeMaterializeDriven
 * 的 drivingWrappers 识别规则同源（模块体无 switchToOnlyOffice 调用 ⇒ 不被认作 driver）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { effectScope, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

const getCalls: string[] = []
let healthResolver: (v: any) => void = () => {}
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn((url: string) => {
      getCalls.push(url)
      if (url.includes('onlyoffice/health')) {
        return new Promise((resolve) => { healthResolver = resolve })
      }
      return Promise.resolve({ data: { data: {} } })
    }),
  },
}))

const switchToOnlyOffice = vi.fn(() => Promise.resolve({} as any))
const reloadAfterApplied = vi.fn(() => Promise.resolve())
const leaveWithoutSaving = vi.fn(() => Promise.resolve())
const persistMode = vi.fn()
const bridgeMode = ref<'html' | 'oo'>('html')
const bridgeState = ref('html_idle')
const bridgeDirty = ref(false)
const bridgeCanForcesave = ref(false)
const bridgeDescriptor = ref<any>(null)
vi.mock('../useWorkpaperSyncBridge', () => ({
  // 含 applied：与生产 WP_BRIDGE_IN_FLIGHT_STATES 同形，才能测判据⑤
  WP_BRIDGE_IN_FLIGHT_STATES: ['materializing', 'oo_loading', 'applied'],
  useWorkpaperSyncBridge: () => ({
    mode: bridgeMode,
    state: bridgeState,
    descriptor: bridgeDescriptor,
    feedback: ref({ message: '' }),
    dirty: bridgeDirty,
    lastError: ref(''),
    canForcesave: bridgeCanForcesave,
    switchToOnlyOffice,
    reloadAfterApplied,
    leaveWithoutSaving,
    persistMode,
  }),
}))
vi.mock('../workpaperSyncCapability', () => ({
  capabilityForEntry: () => 'single_onlyoffice',
}))

import { useARenderModeSwitch, A_ONLINE_EDIT_LABEL } from '../useARenderModeSwitch'
import { __resetOoHealthCacheForTests } from '../onlyOfficeHealth'

const ENTRY = 'xlsx/gt-a91-deficiency-letter'
const forceSave = vi.fn(() => Promise.resolve({ operationId: 'op-1' }))

function makeMode(extra: Partial<Parameters<typeof useARenderModeSwitch>[0]> = {}) {
  const m = useARenderModeSwitch({
    entryId: ENTRY,
    wpId: ref('wp'),
    projectId: ref('p'),
    isReadonly: ref(false),
    flushHtml: async () => ({ expectedRevision: 1, projection: null, sheetKey: `${ENTRY}:managed` } as any),
    reloadHtml: async () => {},
    flushBeforeSwitch: () => {},
    ...extra,
  })
  m.syncHostRef.value = { forceSave }
  return m
}

/** 把桥摆到「已在 OO 里」的姿态。 */
function enterOo(state = 'oo_editing', dirty = false, canForce = false) {
  bridgeMode.value = 'oo'
  bridgeState.value = state
  bridgeDirty.value = dirty
  bridgeCanForcesave.value = canForce
}

describe('useARenderModeSwitch', () => {
  beforeEach(() => {
    getCalls.length = 0
    __resetOoHealthCacheForTests()
    vi.clearAllMocks()
    bridgeMode.value = 'html'
    bridgeState.value = 'html_idle'
    bridgeDirty.value = false
    bridgeCanForcesave.value = false
    bridgeDescriptor.value = null
  })

  it('① 切 docx 真调 switchToOnlyOffice（空壳根因的正面判据）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    const p = m.switchMode('docx')
    healthResolver({ data: { data: { healthy: true } } })
    await p
    expect(switchToOnlyOffice).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('② modeOptions 不因健康未就绪锁死「在线编辑」', () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    expect(m.ooHealthy.value).toBe(false)
    const online = m.modeOptions.value.find((o) => o.label === A_ONLINE_EDIT_LABEL)!
    expect(online.disabled).toBe(false)
    scope.stop()
  })

  it('③ 健康未就绪时的点击不被静默吞掉（竞态兜底）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    const p = m.switchMode('docx')
    healthResolver({ data: { data: { healthy: true } } })
    await p
    expect(switchToOnlyOffice).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('③b OO 不健康时切在线编辑 ⇒ 明确告知，不静默', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    const p = m.switchMode('docx')
    healthResolver({ data: { data: { healthy: false } } })
    await p
    expect(switchToOnlyOffice).not.toHaveBeenCalled()
    expect(m.lastNotice.value?.type).toBe('warning')
    scope.stop()
  })

  it('健康端点唯一正确（禁用旧 404 端点）', async () => {
    const scope = effectScope()
    scope.run(() => makeMode())
    healthResolver({ data: { data: { healthy: true } } })
    await flushPromises()
    expect(getCalls.some((u) => u === '/api/workpapers/onlyoffice/health')).toBe(true)
    expect(getCalls.some((u) => u.includes('/api/onlyoffice/health'))).toBe(false)
    scope.stop()
  })

  it('分支① applied ⇒ 只 reload，不再发任何保存（秒切）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    enterOo('applied')
    await m.switchMode('html')
    expect(reloadAfterApplied).toHaveBeenCalledTimes(1)
    expect(forceSave).not.toHaveBeenCalled()
    expect(leaveWithoutSaving).not.toHaveBeenCalled()
    expect(m.lastNotice.value).toBeNull()
    scope.stop()
  })

  it('分支② 未改动 ⇒ clean close，不发强制保存（丝滑）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    enterOo('oo_editing', false, true)
    await m.switchMode('html')
    expect(leaveWithoutSaving).toHaveBeenCalledTimes(1)
    expect(forceSave).not.toHaveBeenCalled()
    expect(reloadAfterApplied).not.toHaveBeenCalled()
    scope.stop()
  })

  it('分支③ 有改动且可保存 ⇒ 真 forceSave（允许慢）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    enterOo('oo_editing', true, true)
    await m.switchMode('html')
    expect(forceSave).toHaveBeenCalledTimes(1)
    expect(leaveWithoutSaving).not.toHaveBeenCalled()
    expect(m.lastNotice.value).toBeNull()
    scope.stop()
  })

  it('分支④ 有改动但桥不放行 ⇒ 放人走且**明确告知未同步**（不静默）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    enterOo('oo_editing', true, false)
    await m.switchMode('html')
    expect(forceSave).not.toHaveBeenCalled()
    expect(leaveWithoutSaving).not.toHaveBeenCalled()
    expect(persistMode).toHaveBeenCalledWith('html')
    expect(m.lastNotice.value).not.toBeNull()
    expect(m.lastNotice.value!.type).toBe('danger')
    expect(m.syncStateTag.value.type).toBe('danger')
    scope.stop()
  })

  it('⑤ applied 在 in-flight 集合里，但切回 HTML 仍放行', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    enterOo('applied')
    expect(m.busy.value).toBe(true)
    const html = m.modeOptions.value.find((o) => o.value === 'html')!
    expect(html.disabled).toBe(false)
    await m.switchMode('html')
    expect(reloadAfterApplied).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('⑥ B 类 beforeEnterOo 返 false ⇒ 不进 OO（生成 Word 失败不切）', async () => {
    const scope = effectScope()
    const beforeEnterOo = vi.fn(async () => false)
    const m = scope.run(() => makeMode({ beforeEnterOo }))!
    const p = m.switchMode('docx')
    healthResolver({ data: { data: { healthy: true } } })
    await p
    expect(beforeEnterOo).toHaveBeenCalledTimes(1)
    expect(switchToOnlyOffice).not.toHaveBeenCalled()
    scope.stop()
  })

  it('⑥b B 类 beforeEnterOo 返 true ⇒ 先预处理再进 OO', async () => {
    const scope = effectScope()
    const order: string[] = []
    const beforeEnterOo = vi.fn(async () => { order.push('before'); return true })
    switchToOnlyOffice.mockImplementationOnce(() => { order.push('switch'); return Promise.resolve({} as any) })
    const m = scope.run(() => makeMode({ beforeEnterOo }))!
    const p = m.switchMode('docx')
    healthResolver({ data: { data: { healthy: true } } })
    await p
    expect(order).toEqual(['before', 'switch'])
    scope.stop()
  })

  it('⑦ afterLeaveOo 在切回 html 后被调用', async () => {
    const scope = effectScope()
    const afterLeaveOo = vi.fn()
    const m = scope.run(() => makeMode({ afterLeaveOo }))!
    enterOo('oo_editing', false, true)
    await m.switchMode('html')
    expect(afterLeaveOo).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('⑧ switchToOnlyOffice 抛错 ⇒ 状态标签变 danger，不静默、不 unhandled', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    switchToOnlyOffice.mockRejectedValueOnce(new Error('boom'))
    const p = m.switchMode('docx')
    healthResolver({ data: { data: { healthy: true } } })
    await p
    expect(m.lastNotice.value?.type).toBe('danger')
    scope.stop()
  })

  it('⑨ renderMode 以桥为真源（bridge.mode=oo ⇒ docx）', () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    expect(m.renderMode.value).toBe('html')
    bridgeMode.value = 'oo'
    expect(m.renderMode.value).toBe('docx')
    scope.stop()
  })
})
