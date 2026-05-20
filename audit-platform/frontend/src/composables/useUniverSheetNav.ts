/**
 * useUniverSheetNav — Univer sheet 列表导航 composable
 *
 * 痛点：致同底稿模板 sheet 数 23+，Univer 默认底部 sheet bar 横向滚动名称被截断
 * 方案：提供左侧分类树（按 sheet 名称模式分组）+ 当前 sheet 高亮 + 切换 API
 *
 * 用法：
 *   const sheetNav = useUniverSheetNav(univerAPI)
 *   await sheetNav.refresh()
 *   sheetNav.groups.value  // [{ category: '审定表', icon: '📋', sheets: [{ id, name, index }] }]
 *   sheetNav.activeSheetId.value
 *   sheetNav.switchTo(sheetId)
 *
 * E1 Sprint 2 Task 2.3: scenarioFilter 参数（F1.2 + F1.7）
 *   - normal 场景下隐藏 IPO/舞弊应对类 sheet（E1-26~E1-32 等）
 *   - has_foreign_currency=false 时隐藏外币相关 sheet（E1-3 双版本二选一）
 */
import { ref, computed, type Ref } from 'vue'

export interface SheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden?: boolean
  /** D 循环（task 2.7）：附注披露 sheet 应展示"只读"标识；E 循环不设置 */
  readonly?: boolean
}

export interface SheetGroup {
  category: string
  icon: string
  color: string
  sheets: SheetItem[]
  /** D 循环（task 2.7）：1-99 用于 UniverSheetNav 按 priority 升序排列；E 循环不设置时保持原顺序 */
  priority?: number
}

/** Sprint 2 Task 2.3: 场景过滤参数 */
export interface ScenarioFilter {
  /** 项目场景: normal/ipo/listed/transfer/restructure/fraud_response */
  scenario: string
  /** 是否有外币业务（驱动 E1-3 双版本 + E1-8 外币盘点显隐） */
  hasForeignCurrency: boolean
}

/** sheet 名称是否属于"非 normal 场景才显示"（IPO/上市/重组/舞弊应对相关） */
function isIpoFraudOnlySheet(name: string): boolean {
  const patterns = [
    /IPO\s*应对/i,
    /反舞弊|舞弊应对/,
    /E1-2[6-9]|E1-3[0-2]/,  // E1-26~E1-32
    /上市重组|新三板/,
  ]
  return patterns.some((p) => p.test(name))
}

/** sheet 名称是否属于"有外币才显示"（外币相关） */
function isForeignCurrencyOnlySheet(name: string): boolean {
  const patterns = [
    /外币.*盘点|外币.*现金/,
    /E1-8(?!\d)/,  // E1-8 但不是 E1-80+
    /外币及人民币|外币人民币/,
  ]
  return patterns.some((p) => p.test(name))
}

/** sheet 名称是否属于"修订前/示例/提示"类历史遗留 sheet（应隐藏） */
function isLegacyOrSampleSheet(name: string): boolean {
  const patterns = [
    /[（(]修订前[）)]/,
    /[（(]示例[）)]/,
    /[（(]提示[）)]/,
    /F1-6.*修订前/,
  ]
  return patterns.some((p) => p.test(name))
}

// 致同底稿 sheet 命名模式 → 分类（按优先级匹配）
const SHEET_PATTERNS: Array<{ pattern: RegExp; category: string; icon: string; color: string }> = [
  { pattern: /^底稿目录|^封面|目录$/, category: '目录', icon: '📑', color: '#909399' },
  { pattern: /审定表|审定数/, category: '审定表', icon: '📋', color: '#4b2d77' },
  { pattern: /程序表|实质性程序|分析程序|检查程序|控制测试/, category: '程序表', icon: '📝', color: '#5e35b1' },
  { pattern: /附注披露|附注/, category: '附注披露', icon: '📎', color: '#8e24aa' },
  { pattern: /函证|确认书|回函/, category: '函证', icon: '✉️', color: '#1976d2' },
  { pattern: /盘点|存货监盘|银行存单/, category: '盘点表', icon: '🔢', color: '#388e3c' },
  { pattern: /明细表|分类账|分户/, category: '明细表', icon: '📊', color: '#00838f' },
  { pattern: /调整分录|AJE|RJE/, category: '调整分录', icon: '✏️', color: '#f57c00' },
  { pattern: /分析|变动|趋势/, category: '分析表', icon: '📈', color: '#7b1fa2' },
  { pattern: /截止测试|跨期/, category: '截止测试', icon: '⏱️', color: '#c62828' },
  { pattern: /减值|坏账|拨备/, category: '减值测试', icon: '⚠️', color: '#d84315' },
  { pattern: /对账|余额调节/, category: '对账', icon: '⚖️', color: '#0277bd' },
  { pattern: /检查|核对|查询记录|信用报告/, category: '检查表', icon: '🔍', color: '#455a64' },
  { pattern: /承诺|声明书|管理层/, category: '声明承诺', icon: '✍️', color: '#5d4037' },
  { pattern: /custom|自定义|gt_custom/i, category: '自定义', icon: '⭐', color: '#9e9e9e' },
]

const FALLBACK_GROUP = { category: '其他', icon: '📄', color: '#bdbdbd' }

function classifySheet(name: string): { category: string; icon: string; color: string } {
  for (const p of SHEET_PATTERNS) {
    if (p.pattern.test(name)) {
      return { category: p.category, icon: p.icon, color: p.color }
    }
  }
  return FALLBACK_GROUP
}

export function useUniverSheetNav(univerAPI: Ref<any>, scenarioFilter?: Ref<ScenarioFilter | null>) {
  const sheets = ref<SheetItem[]>([])
  const activeSheetId = ref<string>('')

  /** 是否应该过滤掉该 sheet（基于 scenarioFilter） */
  function shouldFilterOut(name: string): boolean {
    // 历史遗留 sheet 永远过滤
    if (isLegacyOrSampleSheet(name)) return true
    const filter = scenarioFilter?.value
    if (!filter) return false
    // normal 场景过滤掉 IPO/舞弊应对相关
    if (filter.scenario === 'normal' && isIpoFraudOnlySheet(name)) return true
    // 无外币过滤掉外币相关 sheet
    if (!filter.hasForeignCurrency && isForeignCurrencyOnlySheet(name)) return true
    return false
  }

  function refresh() {
    const api = univerAPI.value
    if (!api) {
      sheets.value = []
      return
    }
    try {
      const wb = api.getActiveWorkbook?.()
      if (!wb) return
      // Univer 0.21 API: getSheets() / getActiveSheet()
      const allSheets = wb.getSheets?.() || []
      const active = wb.getActiveSheet?.()
      const items: SheetItem[] = allSheets.map((s: any, idx: number) => {
        const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
        const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
        const hidden = s.isSheetHidden?.() === true
        const cls = classifySheet(name)
        return { id, name, index: idx, category: cls.category, hidden }
      }).filter((s: SheetItem) => !s.hidden && !shouldFilterOut(s.name))
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (items.length > 0) {
        activeSheetId.value = items[0].id
      }
    } catch (err) {
      console.warn('[useUniverSheetNav] refresh failed:', err)
    }
  }

  function switchTo(sheetId: string) {
    const api = univerAPI.value
    if (!api) return
    try {
      const wb = api.getActiveWorkbook?.()
      if (!wb) return
      // Try Univer Facade API to set active sheet
      const targetSheet = wb.getSheets?.()?.find((s: any) => {
        const id = s.getSheetId?.() || s.getId?.()
        return id === sheetId
      })
      if (targetSheet?.activate) {
        targetSheet.activate()
        activeSheetId.value = sheetId
      } else if (wb.setActiveSheet) {
        wb.setActiveSheet(sheetId)
        activeSheetId.value = sheetId
      } else {
        // Fallback: dispatch command
        const unitId = wb.getId?.() || wb.getUnitId?.()
        if (unitId && api.executeCommand) {
          api.executeCommand('sheet.command.set-worksheet-activate', {
            unitId,
            subUnitId: sheetId,
          }).catch(() => {})
          activeSheetId.value = sheetId
        }
      }
    } catch (err) {
      console.warn('[useUniverSheetNav] switchTo failed:', err)
    }
  }

  /** Sprint 2 Task 2.37: E1-1 双区显隐（has_foreign_currency=false 时隐藏 R7-R21 上区） */
  function setRowsVisible(sheetName: string, rowIndexes: number[], visible: boolean): boolean {
    const api = univerAPI.value
    if (!api) return false
    try {
      const wb = api.getActiveWorkbook?.()
      if (!wb) return false
      const targetSheet = wb.getSheets?.()?.find((s: any) => {
        const name = s.getSheetName?.() || s.getName?.()
        return name === sheetName
      })
      if (!targetSheet) return false
      if (targetSheet.setRowVisible) {
        targetSheet.setRowVisible(rowIndexes, visible)
        return true
      }
      // Fallback: 逐行调用
      if (targetSheet.showRow && targetSheet.hideRow) {
        rowIndexes.forEach((r) => {
          if (visible) targetSheet.showRow(r)
          else targetSheet.hideRow(r)
        })
        return true
      }
      return false
    } catch (err) {
      console.warn('[useUniverSheetNav] setRowsVisible failed:', err)
      return false
    }
  }

  /** Sprint 2 Task 2.37: E1-1 上区行索引（R7-R21，0-based 即 6-20） */
  const E1_FOREIGN_REGION_ROWS = Array.from({ length: 15 }, (_, i) => 6 + i)

  /** 应用 has_foreign_currency 显隐规则到 E1-1 sheet */
  function applyForeignCurrencyVisibility() {
    const filter = scenarioFilter?.value
    if (!filter) return
    const e1Sheet = sheets.value.find((s) => /货币资金审定表E1-1|E1-1\b/.test(s.name))
    if (!e1Sheet) return
    setRowsVisible(e1Sheet.name, E1_FOREIGN_REGION_ROWS, filter.hasForeignCurrency)
  }

  // 按 category 分组（保持模板原顺序）
  const groups = computed<SheetGroup[]>(() => {
    const groupMap = new Map<string, SheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifySheet(sheet.name)
      if (!groupMap.has(sheet.category)) {
        groupMap.set(sheet.category, { category: sheet.category, icon: cls.icon, color: cls.color, sheets: [] })
      }
      groupMap.get(sheet.category)!.sheets.push(sheet)
    }
    return Array.from(groupMap.values())
  })

  const totalCount = computed(() => sheets.value.length)

  return {
    sheets,
    groups,
    activeSheetId,
    totalCount,
    refresh,
    switchTo,
    setRowsVisible,
    applyForeignCurrencyVisibility,
    E1_FOREIGN_REGION_ROWS,
  }
}
