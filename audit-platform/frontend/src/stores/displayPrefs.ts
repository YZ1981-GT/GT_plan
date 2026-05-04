/**
 * 全局显示偏好 Store
 *
 * 管理金额单位、字体字号等用户级显示偏好。
 * 持久化到 localStorage，切换后所有表格实时响应。
 *
 * 用法：
 * ```ts
 * const prefs = useDisplayPrefsStore()
 * // 模板中
 * {{ prefs.fmt(row.amount) }}
 * // 表头
 * <span>单位：{{ prefs.unitSuffix }}</span>
 * ```
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fmtAmountUnit, unitLabel,
  type AmountUnit, type FontSize,
  AMOUNT_UNITS, FONT_SIZES,
} from '@/utils/formatters'

const STORAGE_KEY = 'gt_display_prefs'

interface DisplayPrefsData {
  amountUnit: AmountUnit
  fontSize: FontSize
  showZero: boolean
  decimals: number
  negativeRed: boolean
  highlightThreshold: number  // 变动超过此比例高亮（0.2 = 20%），0 表示关闭
}

const DEFAULTS: DisplayPrefsData = {
  amountUnit: 'wan',
  fontSize: 'sm',
  showZero: false,
  decimals: 2,
  negativeRed: true,
  highlightThreshold: 0.2,
}

function loadFromStorage(): DisplayPrefsData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return { ...DEFAULTS }
}

function saveToStorage(data: DisplayPrefsData) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
}

export const useDisplayPrefsStore = defineStore('displayPrefs', () => {
  const saved = loadFromStorage()

  const amountUnit = ref<AmountUnit>(saved.amountUnit)
  const fontSize = ref<FontSize>(saved.fontSize)
  const showZero = ref(saved.showZero)
  const decimals = ref(saved.decimals)
  const negativeRed = ref(saved.negativeRed)
  const highlightThreshold = ref(saved.highlightThreshold)

  // 持久化
  function persist() {
    saveToStorage({
      amountUnit: amountUnit.value,
      fontSize: fontSize.value,
      showZero: showZero.value,
      decimals: decimals.value,
      negativeRed: negativeRed.value,
      highlightThreshold: highlightThreshold.value,
    })
  }

  // 切换单位
  function setUnit(unit: AmountUnit) {
    amountUnit.value = unit
    persist()
  }

  // 切换字号
  function setFontSize(size: FontSize) {
    fontSize.value = size
    persist()
  }

  // 切换零值显示
  function setShowZero(show: boolean) {
    showZero.value = show
    persist()
  }

  // 设置小数位数
  function setDecimals(d: number) {
    decimals.value = d
    persist()
  }

  // 格式化金额（带单位换算）— 模板中直接调用
  function fmt(v: any): string {
    return fmtAmountUnit(v, amountUnit.value, decimals.value, showZero.value)
  }

  /**
   * 获取金额的 CSS 类名（条件格式）
   * - 负数 → 'gt-amount--negative'
   * - 变动超阈值 → 'gt-amount--highlight'
   */
  function amountClass(v: any, priorValue?: any): string {
    const classes: string[] = []
    const n = typeof v === 'number' ? v : Number(v)
    if (!isNaN(n)) {
      if (negativeRed.value && n < 0) classes.push('gt-amount--negative')
      if (highlightThreshold.value > 0 && priorValue != null) {
        const prior = Number(priorValue)
        if (!isNaN(prior) && prior !== 0) {
          const changeRate = Math.abs((n - prior) / prior)
          if (changeRate >= highlightThreshold.value) classes.push('gt-amount--highlight')
        }
      }
    }
    return classes.join(' ')
  }

  // 切换负数红色
  function setNegativeRed(v: boolean) { negativeRed.value = v; persist() }

  // 设置变动高亮阈值
  function setHighlightThreshold(v: number) { highlightThreshold.value = v; persist() }

  // 单位后缀文本
  const unitSuffix = computed(() => unitLabel(amountUnit.value))

  // 单位除数（用于导出时还原原值）
  const unitDivisor = computed(() => AMOUNT_UNITS[amountUnit.value].divisor)

  // 字号配置
  const fontConfig = computed(() => FONT_SIZES[fontSize.value])

  // 可选项（供 UI 下拉使用）
  const unitOptions = Object.entries(AMOUNT_UNITS).map(([k, v]) => ({ value: k, label: v.label }))
  const fontOptions = Object.entries(FONT_SIZES).map(([k, v]) => ({ value: k, label: v.label }))

  return {
    amountUnit,
    fontSize,
    showZero,
    decimals,
    negativeRed,
    highlightThreshold,
    setUnit,
    setFontSize,
    setShowZero,
    setDecimals,
    setNegativeRed,
    setHighlightThreshold,
    fmt,
    amountClass,
    unitSuffix,
    unitDivisor,
    fontConfig,
    unitOptions,
    fontOptions,
  }
})
