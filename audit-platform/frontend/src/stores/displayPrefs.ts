/**
 * 全局显示偏好 Store
 *
 * 管理金额单位、字体字号、表格密度、固定列等用户级显示偏好。
 * 持久化到 localStorage，切换后所有表格实时响应。
 *
 * 用法：
 * ```ts
 * const prefs = useDisplayPrefsStore()
 * // 模板中
 * {{ prefs.fmt(row.amount) }}
 * // 表头
 * <span>单位：{{ prefs.unitSuffix }}</span>
 * // 密度
 * <el-table :size="prefs.tableDensity" />
 * ```
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fmtAmountUnit, unitLabel,
  type AmountUnit, type FontSize,
  AMOUNT_UNITS, FONT_SIZES,
} from '@/utils/formatters'
import { fmtDateTime as _fmtDateTime } from '@/utils/formatters'

const STORAGE_KEY = 'gt_display_prefs'
// 偏好版本：v2 起平台金额单位默认「元」（此前误默认为「万元」）。
// 版本升级时对旧持久化做一次性迁移，将遗留的默认「万元」归一到「元」。
const PREFS_VERSION = 2

/** 表格密度 */
export type TableDensity = 'compact' | 'default' | 'comfortable'

/** 密度配置 */
export const TABLE_DENSITIES: Record<TableDensity, { label: string; rowHeight: string; padding: string; elSize: 'small' | 'default' | 'large' }> = {
  compact:     { label: '紧凑', rowHeight: '32px', padding: '4px 8px', elSize: 'small' },
  default:     { label: '标准', rowHeight: '40px', padding: '8px 12px', elSize: 'default' },
  comfortable: { label: '宽松', rowHeight: '48px', padding: '12px 16px', elSize: 'large' },
}

/** 固定列配置（按页面） */
export interface FixedColumnsConfig {
  [pageKey: string]: string[]  // pageKey → 固定的列 key 数组
}

interface DisplayPrefsData {
  amountUnit: AmountUnit
  fontSize: FontSize
  showZero: boolean
  decimals: number
  negativeRed: boolean
  highlightThreshold: number  // 变动超过此比例高亮（0.2 = 20%），0 表示关闭
  density: TableDensity
  fixedColumns: FixedColumnsConfig
}

const DEFAULTS: DisplayPrefsData = {
  amountUnit: 'yuan',   // 平台铁律：所有数值默认「元」（不是万元）
  fontSize: 'sm',
  showZero: false,
  decimals: 2,
  negativeRed: true,
  highlightThreshold: 0.2,
  density: 'default',
  fixedColumns: {},
}

function loadFromStorage(): DisplayPrefsData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<DisplayPrefsData> & { _v?: number }
      const merged = { ...DEFAULTS, ...parsed }
      // 一次性迁移：v2 起平台默认「元」；将旧版本遗留的默认「万元」归一到「元」
      if ((parsed._v ?? 1) < PREFS_VERSION) {
        if (parsed.amountUnit === 'wan') merged.amountUnit = 'yuan'
        saveToStorage(merged)
      }
      return merged
    }
  } catch { /* ignore */ }
  return { ...DEFAULTS }
}

function saveToStorage(data: DisplayPrefsData) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...data, _v: PREFS_VERSION }))
}

export const useDisplayPrefsStore = defineStore('displayPrefs', () => {
  const saved = loadFromStorage()

  const amountUnit = ref<AmountUnit>(saved.amountUnit)
  const fontSize = ref<FontSize>(saved.fontSize)
  const showZero = ref(saved.showZero)
  const decimals = ref(saved.decimals)
  const negativeRed = ref(saved.negativeRed)
  const highlightThreshold = ref(saved.highlightThreshold)
  const density = ref<TableDensity>(saved.density)
  const fixedColumns = ref<FixedColumnsConfig>(saved.fixedColumns)

  // 持久化
  function persist() {
    saveToStorage({
      amountUnit: amountUnit.value,
      fontSize: fontSize.value,
      showZero: showZero.value,
      decimals: decimals.value,
      negativeRed: negativeRed.value,
      highlightThreshold: highlightThreshold.value,
      density: density.value,
      fixedColumns: fixedColumns.value,
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
  // null/非数字 → '—'；opts.rawUnit=true → 不做单位换算（原始元值直接格式化）
  function fmt(v: any, opts?: { rawUnit?: boolean }): string {
    if (v == null) return '—'
    const n = typeof v === 'number' ? v : Number(v)
    if (isNaN(n)) return '—'
    if (opts?.rawUnit) {
      // 不做单位换算，仅按 decimals 格式化原始值
      if (!showZero.value && n === 0) return '—'
      return n.toLocaleString('zh-CN', {
        minimumFractionDigits: decimals.value,
        maximumFractionDigits: decimals.value,
      })
    }
    return fmtAmountUnit(v, amountUnit.value, decimals.value, showZero.value)
  }

  /** fmt 的语义别名（便于 import 命名一致） */
  const fmtAmount = fmt

  /** 格式化百分比 */
  function fmtPercent(v: any, d = 1): string {
    if (v == null) return '—'
    const n = typeof v === 'number' ? v : Number(v)
    if (isNaN(n)) return '—'
    return `${n.toFixed(d)}%`
  }

  /** 格式化日期时间（转发 utils/formatters 唯一实现） */
  function fmtDateTime(v: string | Date | null | undefined): string {
    return _fmtDateTime(v)
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
        if (!isNaN(prior)) {
          if (prior === 0 && n !== 0) {
            // 新增科目：上期为 0，本期有值，直接高亮
            classes.push('gt-amount--highlight')
          } else if (prior !== 0) {
            const changeRate = Math.abs((n - prior) / prior)
            if (changeRate >= highlightThreshold.value) classes.push('gt-amount--highlight')
          }
        }
      }
    }
    return classes.join(' ')
  }

  // 切换负数红色
  function setNegativeRed(v: boolean) { negativeRed.value = v; persist() }

  // 设置变动高亮阈值
  function setHighlightThreshold(v: number) { highlightThreshold.value = v; persist() }

  // 切换密度
  function setDensity(d: TableDensity) { density.value = d; persist() }

  // 设置某页面的固定列
  function setFixedColumns(pageKey: string, columns: string[]) {
    fixedColumns.value = { ...fixedColumns.value, [pageKey]: columns }
    persist()
  }

  // 获取某页面的固定列
  function getFixedColumns(pageKey: string): string[] {
    return fixedColumns.value[pageKey] || []
  }

  // 单位后缀文本
  const unitSuffix = computed(() => unitLabel(amountUnit.value))

  // 单位除数（用于导出时还原原值）
  const unitDivisor = computed(() => AMOUNT_UNITS[amountUnit.value].divisor)

  // 字号配置
  const fontConfig = computed(() => FONT_SIZES[fontSize.value])

  // 密度配置
  const densityConfig = computed(() => TABLE_DENSITIES[density.value])

  // el-table 的 size prop 值
  const tableDensity = computed(() => TABLE_DENSITIES[density.value].elSize)

  // 可选项（供 UI 下拉使用）
  const unitOptions = Object.entries(AMOUNT_UNITS).map(([k, v]) => ({ value: k, label: v.label }))
  const fontOptions = Object.entries(FONT_SIZES).map(([k, v]) => ({ value: k, label: v.label }))
  const densityOptions = Object.entries(TABLE_DENSITIES).map(([k, v]) => ({ value: k, label: v.label }))

  return {
    amountUnit,
    fontSize,
    showZero,
    decimals,
    negativeRed,
    highlightThreshold,
    density,
    fixedColumns,
    setUnit,
    setFontSize,
    setShowZero,
    setDecimals,
    setNegativeRed,
    setHighlightThreshold,
    setDensity,
    setFixedColumns,
    getFixedColumns,
    fmt,
    fmtAmount,
    fmtPercent,
    fmtDateTime,
    amountClass,
    unitSuffix,
    unitDivisor,
    fontConfig,
    densityConfig,
    tableDensity,
    unitOptions,
    fontOptions,
    densityOptions,
  }
})
