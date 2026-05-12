/**
 * useFocusTracker - 纯 localStorage 焦点时间追踪
 *
 * 需求 10：前端静默追踪"页面聚焦时间"，只写入 localStorage
 * 键格式：focus_tracker_<weekStart>（按周归档，每周清零）
 * 数据结构：{ [date]: { [wp_id]: { minutes: number, wp_name: string } } }
 *
 * 跨轮约束 8：不发送到后端任何端点
 */
import { onUnmounted, ref } from 'vue'

export interface FocusEntry {
  minutes: number
  wp_name: string
}

export interface WeekFocusData {
  [date: string]: {
    [wp_id: string]: FocusEntry
  }
}

/** 获取本周一的日期字符串 YYYY-MM-DD */
export function getWeekStartDate(now?: Date): string {
  const d = now ? new Date(now) : new Date()
  const day = d.getDay()
  // 周日=0 → 偏移6，周一=1 → 偏移0，周二=2 → 偏移1 ...
  const diff = day === 0 ? 6 : day - 1
  d.setDate(d.getDate() - diff)
  return d.toISOString().slice(0, 10)
}

/** 获取今天的日期字符串 YYYY-MM-DD */
function getTodayDate(): string {
  return new Date().toISOString().slice(0, 10)
}

/** 获取 localStorage key */
export function getFocusStorageKey(weekStart?: string): string {
  const ws = weekStart || getWeekStartDate()
  return `focus_tracker_${ws}`
}

/** 从 localStorage 读取本周焦点数据 */
export function readWeekFocusData(weekStart?: string): WeekFocusData {
  const key = getFocusStorageKey(weekStart)
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return {}
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

/** 写入本周焦点数据到 localStorage */
function writeWeekFocusData(data: WeekFocusData, weekStart?: string): void {
  const key = getFocusStorageKey(weekStart)
  try {
    localStorage.setItem(key, JSON.stringify(data))
  } catch {
    // localStorage 满或不可用，静默忽略
  }
}

/** 4 小时超时阈值（分钟） */
const TIMEOUT_THRESHOLD_MINUTES = 240

/**
 * useFocusTracker composable
 *
 * 在 WorkpaperEditor onMounted 时调用，开始追踪焦点时间。
 * 每分钟更新 localStorage，组件卸载时停止追踪。
 *
 * @param wpId - 底稿 ID
 * @param wpName - 底稿名称（用于时间线展示）
 */
export function useFocusTracker(wpId: string, wpName: string) {
  let intervalId: ReturnType<typeof setInterval> | null = null
  let startTime: number = Date.now()
  let accumulatedMinutes = 0
  let isPageVisible = true
  const timeoutDismissed = ref(false)
  const showTimeoutWarning = ref(false)

  /** 页面可见性变化处理 */
  function onVisibilityChange() {
    if (document.hidden) {
      // 页面不可见，暂停计时
      isPageVisible = false
    } else {
      // 页面重新可见，重置起始时间
      isPageVisible = true
      startTime = Date.now()
    }
  }

  /** 每分钟更新 localStorage */
  function tick() {
    if (!isPageVisible) return

    const now = Date.now()
    const elapsed = Math.floor((now - startTime) / 60000) // 分钟
    if (elapsed < 1) return

    // 累加分钟数
    accumulatedMinutes += elapsed
    startTime = now

    // 写入 localStorage
    const weekStart = getWeekStartDate()
    const today = getTodayDate()
    const data = readWeekFocusData(weekStart)

    if (!data[today]) {
      data[today] = {}
    }
    if (!data[today][wpId]) {
      data[today][wpId] = { minutes: 0, wp_name: wpName }
    }
    data[today][wpId].minutes += elapsed
    data[today][wpId].wp_name = wpName // 确保名称最新

    writeWeekFocusData(data, weekStart)

    // 检查 4 小时超时
    if (data[today][wpId].minutes >= TIMEOUT_THRESHOLD_MINUTES && !timeoutDismissed.value) {
      showTimeoutWarning.value = true
    }
  }

  /** 开始追踪 */
  function start() {
    startTime = Date.now()
    accumulatedMinutes = 0
    isPageVisible = !document.hidden

    // 每 60 秒更新一次
    intervalId = setInterval(tick, 60000)

    // 监听页面可见性
    document.addEventListener('visibilitychange', onVisibilityChange)
  }

  /** 停止追踪 */
  function stop() {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
    document.removeEventListener('visibilitychange', onVisibilityChange)

    // 最后一次 tick，保存剩余时间
    if (isPageVisible) {
      const now = Date.now()
      const elapsed = Math.floor((now - startTime) / 60000)
      if (elapsed >= 1) {
        const weekStart = getWeekStartDate()
        const today = getTodayDate()
        const data = readWeekFocusData(weekStart)
        if (!data[today]) data[today] = {}
        if (!data[today][wpId]) data[today][wpId] = { minutes: 0, wp_name: wpName }
        data[today][wpId].minutes += elapsed
        writeWeekFocusData(data, weekStart)
      }
    }
  }

  /** 关闭超时提示 */
  function dismissTimeout() {
    timeoutDismissed.value = true
    showTimeoutWarning.value = false
  }

  // 自动开始
  start()

  // 组件卸载时自动停止
  onUnmounted(stop)

  return {
    showTimeoutWarning,
    dismissTimeout,
    stop,
  }
}
