/**
 * useHSyncMode 守卫 —— H 循环统一双模式接桥的**行为级**判据。
 *
 * spec: `h-cycle-sync-foundation-and-first-canary`
 *
 * 钉住用户明确要求的切换语义（「点保存后切换要丝滑；编辑未保存则可在切换时保存」）
 * 与本 composable 收敛掉的历史 bug：
 *  ① 四分支保存协议逐条可分辨：applied ⇒ 只 reload 不保存 / 未改动 ⇒ clean close 不保存
 *     / 脏且可保存 ⇒ 真 forceSave / 脏但不放行 ⇒ 放人走且**明确告知未同步**；
 *  ② `modeOptions` 不用 `!ooHealthy` 锁死（D4 bug ③）；
 *  ③ switchMode 竞态兜底：健康未就绪的点击不被静默吞掉（D4 bug ②）；
 *  ④ 非受管 sheet 不得进 OO（后端无 adapter，切了必失败）；
 *  ⑤ `applied` 虽在 in-flight 集合里，切回 HTML 仍必须放行（D4 真栈卡死过）。
 *
 * 变异反证：把分支②的 `leaveWithoutSaving` 换成 `forceSave`、或把分支④的
 * `lastNotice` 赋值删掉（退回 F2 各宿主的静默 `persistMode`），对应用例即打红。
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
const switchToHtml = vi.fn(() => Promise.resolve())
const reloadAfterApplied = vi.fn(() => Promise.resolve())
const leaveWithoutSaving = vi.fn(() => Promise.resolve())
const persistMode = vi.fn()
const bridgeMode = ref<'html' | 'oo'>('html')
const bridgeState = ref('html_idle')
const bridgeDirty = ref(false)
const bridgeCanForcesave = ref(false)
vi.mock('../../sync/useWorkpaperSyncBridge', () => ({
  // 含 applied：与生产 WP_BRIDGE_IN_FLIGHT_STATES 同形，才能测判据⑤
  WP_BRIDGE_IN_FLIGHT_STATES: ['materializing', 'oo_loading', 'applied'],
  useWorkpaperSyncBridge: () => ({
    mode: bridgeMode,
    state: bridgeState,
    descriptor: ref(null),
    feedback: ref({ message: '' }),
    dirty: bridgeDirty,
    lastError: ref(''),
    canForcesave: bridgeCanForcesave,
    switchToOnlyOffice,
    switchToHtml,
    reloadAfterApplied,
    leaveWithoutSaving,
    persistMode,
  }),
}))
vi.mock('../../sync/workpaperSyncApi', () => ({}))
vi.mock('../../sync/workpaperSyncCapability', () => ({
  capabilityForEntry: () => 'bidirectional',
}))

import { useHSyncMode, H_ONLINE_EDIT_LABEL } from '../useHSyncMode'
import { __resetOoHealthCacheForTests } from '../../sync/onlyOfficeHealth'
import { H_MANAGED_SHEETS, H_OO_WIRED_ROWS_CODES } from '../../sync/hManagedSheets'

/** canary 的真实短码/entry —— 从受管清单取，不在测试里另写字面量。 */
const CANARY = H_MANAGED_SHEETS.find((s) => s.code === H_OO_WIRED_ROWS_CODES[0])!

const forceSave = vi.fn(() => Promise.resolve({ operationId: 'op-1' }))

function makeMode(code = CANARY.code) {
  const mode = useHSyncMode({
    entryId: CANARY.entryId,
    wpId: ref('wp'),
    projectId: ref('p'),
    currentCode: ref(code),
    isReadonly: ref(false),
    flushHtml: async () => ({
      expectedRevision: 1,
      projection: { values: {}, row_keys: {} },
      sheetKey: CANARY.sheetKey,
    } as any),
    reloadHtml: async () => {},
  })
  mode.syncHostRef.value = { forceSave }
  return mode
}

/** 把桥摆到「已在 OO 里」的姿态。 */
function enterOo(state = 'oo_editing', dirty = false, canForce = false) {
  bridgeMode.value = 'oo'
  bridgeState.value = state
  bridgeDirty.value = dirty
  bridgeCanForcesave.value = canForce
}

describe('useHSyncMode', () => {
  beforeEach(() => {
    getCalls.length = 0
    __resetOoHealthCacheForTests()
    vi.clearAllMocks()
    bridgeMode.value = 'html'
    bridgeState.value = 'html_idle'
    bridgeDirty.value = false
    bridgeCanForcesave.value = false
  })

  it('① 健康端点唯一正确（禁用旧 404 端点）', async () => {
    const scope = effectScope()
    scope.run(() => makeMode())
    healthResolver({ data: { data: { healthy: true } } })
    await flushPromises()
    expect(getCalls.some((u) => u === '/api/workpapers/onlyoffice/health')).toBe(true)
    expect(getCalls.some((u) => u.includes('/api/onlyoffice/health'))).toBe(false)
    scope.stop()
  })

  it('② modeOptions 不因健康未就绪锁死「在线编辑」', () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    // 健康仍未 resolve ⇒ ooHealthy=false
    expect(m.ooHealthy.value).toBe(false)
    const online = m.modeOptions.value.find((o) => o.label === H_ONLINE_EDIT_LABEL)!
    expect(online.disabled).toBe(false)
    scope.stop()
  })

  it('③ 健康未就绪时的点击不被静默吞掉（竞态兜底）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    const p = m.switchMode('onlyoffice')
    healthResolver({ data: { data: { healthy: true } } })
    await p
    expect(switchToOnlyOffice).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('④ 非受管 sheet 不建桥（后端无 adapter，建桥必失败）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode('H9-9-不存在的受管表'))!
    expect(m.isManagedSheet.value).toBe(false)
    healthResolver({ data: { data: { healthy: true } } })
    await m.switchMode('onlyoffice')
    expect(switchToOnlyOffice).not.toHaveBeenCalled()
    scope.stop()
  })

  /**
   * 🔴 回归守卫：接桥**不得顺手拿掉**非受管 sheet 的 legacy OO 视图。
   *
   * 一册 8~9 个 sheet 里当前只有 1 张进受管面，其余（审定表 / 程序表 / 调整分录汇总 /
   * 附注）用户原本就能切到 `GtOnlyOfficeSheet` 看 Excel 原貌。首版 `modeOptions` 写了
   * `disabled: !isManagedSheet` ⇒ 那些 sheet 的 OO 视图被接桥改动静默移除，是行为回归。
   * 受管面只决定「走桥还是走 legacy」，不决定「能不能看 Excel」。
   */
  it('④b 非受管 sheet 仍可切 legacy OO 只读视图（不因接桥被拿掉）', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode('H9-1'))!
    expect(m.isManagedSheet.value).toBe(false)
    const online = m.modeOptions.value.find((o) => o.label === H_ONLINE_EDIT_LABEL)!
    expect(online.disabled, '非受管 sheet 的「在线编辑」不得被禁用').toBe(false)
    healthResolver({ data: { data: { healthy: true } } })
    await m.switchMode('onlyoffice')
    // 本地切到 legacy 视图（宿主据此渲染 GtOnlyOfficeSheet），但**不建桥**
    expect(m.renderMode.value).toBe('onlyoffice')
    expect(switchToOnlyOffice).not.toHaveBeenCalled()
    // 切回也不走桥的四分支
    await m.switchMode('html')
    expect(m.renderMode.value).toBe('html')
    expect(leaveWithoutSaving).not.toHaveBeenCalled()
    expect(persistMode).not.toHaveBeenCalled()
    scope.stop()
  })

  it('④c OO 不健康时切在线编辑 ⇒ 明确告知，不静默', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    const p = m.switchMode('onlyoffice')
    healthResolver({ data: { data: { healthy: false } } })
    await p
    expect(switchToOnlyOffice).not.toHaveBeenCalled()
    expect(m.lastNotice.value?.type).toBe('warning')
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
    // 🔴 核心判据：必须留下用户能看见的提示，不能假装已保存
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
    // busy 为真，但 html 项不得被 disabled（否则用户永远点不回表单）
    const html = m.modeOptions.value.find((o) => o.value === 'html')!
    expect(html.disabled).toBe(false)
    await m.switchMode('html')
    expect(reloadAfterApplied).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('⑥ forceSave 抛错 ⇒ 状态标签变 danger，不静默', async () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    forceSave.mockRejectedValueOnce(new Error('boom'))
    enterOo('oo_editing', true, true)
    await m.switchMode('html')
    expect(m.lastNotice.value?.type).toBe('danger')
    expect(m.syncStateTag.value.type).toBe('danger')
    scope.stop()
  })

  it('⑦ sheetKey 从受管清单派生，不是宿主内联字面量', () => {
    const scope = effectScope()
    const m = scope.run(() => makeMode())!
    expect(m.sheetKey.value).toBe(CANARY.sheetKey)
    scope.stop()
  })
})
