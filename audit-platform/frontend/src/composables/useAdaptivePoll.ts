/**
 * 自适应轮询（spec procedure-chain-hardening-and-java-contracts R17）。
 *
 * 顶栏导入指示器（ThreeColumnLayout）与项目概览面板（DetailProjectPanel）原先固定每 5 秒查一次 active-job：
 * 没有导入任务时，每个打开的项目页也一直每 5 秒发一条。现在用 setTimeout 链：
 * - 每轮 `tick()` 返回「是否有进行中的任务」：有 ⇒ `activeMs`（5 秒）后再查，没有 ⇒ `idleMs`（30 秒）；
 * - 页面隐藏时停，重新可见时立即查一次并恢复；
 * - `poke()`：外部知道状态变了（如刚提交导入）时立即查一次，不必等到下一轮。
 * 同一时刻只有一条链：start / poke / 可见恢复都会先作废旧链（序号），晚到的旧回调不再续链。
 */
import { getCurrentScope, onScopeDispose } from 'vue'

export const POLL_ACTIVE_MS = 5_000
export const POLL_IDLE_MS = 30_000

export interface AdaptivePoll {
  /** 开始（或重新开始）：立即查一次，然后按结果续链 */
  start: () => void
  /** 停止，不再续链 */
  stop: () => void
  /** 已开始时立即查一次（作废当前等待中的那一轮） */
  poke: () => void
  /** 停止并移除可见性监听（组件卸载时；在 effect scope 里创建时自动调用） */
  dispose: () => void
}

export function useAdaptivePoll(
  tick: () => Promise<boolean>,
  opts: { activeMs?: number; idleMs?: number } = {},
): AdaptivePoll {
  const activeMs = opts.activeMs ?? POLL_ACTIVE_MS
  const idleMs = opts.idleMs ?? POLL_IDLE_MS
  let timer: ReturnType<typeof setTimeout> | null = null
  let running = false
  let seq = 0

  function clearTimer() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  async function run(mine: number) {
    let busy = false
    try {
      busy = await tick()
    } catch {
      busy = false
    }
    if (mine !== seq || !running || document.hidden) return
    timer = setTimeout(() => { void run(mine) }, busy ? activeMs : idleMs)
  }

  function restart() {
    clearTimer()
    const mine = ++seq
    if (!document.hidden) void run(mine)
  }

  function start() {
    running = true
    restart()
  }

  function stop() {
    running = false
    seq++
    clearTimer()
  }

  function poke() {
    if (running) restart()
  }

  function onVisibility() {
    if (!running) return
    if (document.hidden) {
      seq++
      clearTimer()
    } else {
      restart()
    }
  }

  document.addEventListener('visibilitychange', onVisibility)

  function dispose() {
    stop()
    document.removeEventListener('visibilitychange', onVisibility)
  }

  if (getCurrentScope()) onScopeDispose(dispose)

  return { start, stop, poke, dispose }
}
