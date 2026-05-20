/**
 * useHFixedAssetSheetGroups — H 固定资产循环 sheet 分组 composable
 *
 * spec workpaper-h-fixed-assets-cycle ADR-H3b（Task 1.3b / 2.3）
 *
 * H 循环 11 主底稿（H0~H10）合并后 159 sheet，按 14 类规则分组。
 * 集成 MEASUREMENT_MODEL_FILTER 控制 H3/H7 双计量模式 sheet 显隐。
 *
 * 14 类分组规则（按 priority 匹配顺序，首个命中即停止）：
 *   1. 索引（defaultHidden=true）
 *   2. 历史遗留（defaultHidden=true）— H 实测 0 命中，保留做回归保护
 *   3. 总控台（程序表 xxA）
 *   4. 审定表
 *   5. 附注披露（readonly=true）
 *   6. 明细表
 *   7. 折旧/折耗测算
 *   8. 减值测试
 *   9. 增减检查
 *  10. 实物盘点
 *  11. 权属/产权检查
 *  12. 关联交易
 *  13. 租赁专项（H8/H9 特有）
 *  14. 调整分录
 *  15. 其他程序（fallback 兜底）
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface HSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface HSheetPattern extends HSheetCategory {
  pattern: RegExp
}

export interface HFixedAssetSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface HFixedAssetSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: HFixedAssetSheetItem[]
}

// ===== MEASUREMENT_MODEL_FILTER（与后端 Python 字典对齐） =====

export const MEASUREMENT_MODEL_FILTER: Record<string, { hide_patterns: string[] }> = {
  cost: {
    hide_patterns: ['（公允价值模式）', '(公允价值模式)'],
  },
  fair_value: {
    hide_patterns: ['（成本模式）', '(成本模式)'],
  },
}

// ===== 14 类规则（按 priority 匹配顺序） =====

export const H_SHEET_PATTERNS: HSheetPattern[] = [
  // 1. 索引类（defaultHidden=true）
  {
    pattern: /^底稿目录$|^GT_Custom$|^修订说明$/,
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 0,
    defaultHidden: true,
  },
  // 2. 历史遗留类（defaultHidden=true）— H 循环实测 0 命中，保留规则做回归保护
  {
    pattern: /修订前|[（(]原[）)]|G\d+.*[删除移至]|（示例）|\(示例\)|示例[）)]?$/,
    category: '历史遗留',
    icon: '🗄️',
    color: '#9e9e9e',
    priority: 1,
    defaultHidden: true,
  },
  // 3. 总控台（程序表 xxA）
  {
    pattern: /[A-Z]\d*A$|实质性程序表/,
    category: '总控台',
    icon: '🎯',
    color: '#1976d2',
    priority: 2,
  },
  // 4. 审定表
  {
    pattern: /审定表/,
    category: '审定表',
    icon: '✅',
    color: '#388e3c',
    priority: 3,
  },
  // 5. 附注披露（readonly=true）
  {
    pattern: /附注披露/,
    category: '附注披露',
    icon: '📝',
    color: '#795548',
    priority: 4,
    readonly: true,
  },
  // 6. 明细表
  {
    pattern: /明细表/,
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 5,
  },
  // 7. 折旧/折耗测算
  {
    pattern: /折旧|折耗|折旧分配/,
    category: '折旧测算',
    icon: '📉',
    color: '#7b1fa2',
    priority: 6,
  },
  // 8. 减值测试
  {
    pattern: /减值|可收回金额/,
    category: '减值测试',
    icon: '⚠️',
    color: '#d84315',
    priority: 7,
  },
  // 9. 增减检查
  {
    pattern: /增加检查|减少检查|增减检查/,
    category: '增减检查',
    icon: '🔄',
    color: '#00838f',
    priority: 8,
  },
  // 10. 实物盘点
  {
    pattern: /监盘|盘点|监盘小结/,
    category: '实物盘点',
    icon: '📦',
    color: '#2e7d32',
    priority: 9,
  },
  // 11. 权属/产权检查
  {
    pattern: /权属|产权|产权核对/,
    category: '权属检查',
    icon: '🏠',
    color: '#5d4037',
    priority: 10,
  },
  // 12. 关联交易
  {
    pattern: /关联/,
    category: '关联交易',
    icon: '🔗',
    color: '#5e35b1',
    priority: 11,
  },
  // 13. 租赁专项（H8/H9 特有）
  {
    pattern: /租赁|使用权资产|融资费用|租赁变更|简化处理/,
    category: '租赁专项',
    icon: '🏢',
    color: '#1565c0',
    priority: 12,
  },
  // 14. 调整分录
  {
    pattern: /调整分录/,
    category: '调整分录',
    icon: '✏️',
    color: '#3949ab',
    priority: 13,
  },
]

export const FALLBACK_GROUP: HSheetCategory = {
  category: '其他程序',
  icon: '📄',
  color: '#bdbdbd',
  priority: 14,
}

/** 按 H_SHEET_PATTERNS 顺序匹配 sheet 名，返回 H 循环类目元数据 */
export function classifyHSheet(name: string): HSheetCategory {
  for (const p of H_SHEET_PATTERNS) {
    if (p.pattern.test(name)) {
      const { pattern: _pattern, ...rest } = p
      return rest
    }
  }
  return FALLBACK_GROUP
}

/**
 * 判断 sheet 是否应被 measurement_model 隐藏
 */
export function isHiddenByMeasurementModel(
  sheetName: string,
  measurementModel: string,
): boolean {
  const filter = MEASUREMENT_MODEL_FILTER[measurementModel]
  if (!filter) return false
  return filter.hide_patterns.some((p) => sheetName.includes(p))
}

// ===== composable =====

/**
 * H 固定资产循环 sheet 分组 composable
 *
 * 接口与 useFPurchaseInventorySheetGroups 等同。
 * 集成 MEASUREMENT_MODEL_FILTER 控制 H3/H7 双计量模式 sheet 显隐。
 */
export function useHFixedAssetSheetGroups(
  univerAPI: Ref<any>,
  measurementModel?: Ref<string>,
) {
  const sheets = ref<HFixedAssetSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyHSheet(name)
    if (cls.defaultHidden) return true
    // measurement_model 显隐控制
    const model = measurementModel?.value || 'cost'
    if (isHiddenByMeasurementModel(name, model)) return true
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
      const allSheets = wb.getSheets?.() || []
      const active = wb.getActiveSheet?.()
      const items: HFixedAssetSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyHSheet(name)
          const item: HFixedAssetSheetItem = {
            id,
            name,
            index: idx,
            category: cls.category,
            hidden,
            priority: cls.priority,
            defaultHidden: cls.defaultHidden ?? false,
            readonly: cls.readonly ?? false,
          }
          return item
        })
        .filter((s: HFixedAssetSheetItem) => !s.hidden && !shouldFilterOut(s.name))
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (items.length > 0) {
        activeSheetId.value = items[0].id
      }
    } catch (err) {
      console.warn('[useHFixedAssetSheetGroups] refresh failed:', err)
    }
  }

  function switchTo(sheetId: string) {
    const api = univerAPI.value
    if (!api) return
    try {
      const wb = api.getActiveWorkbook?.()
      if (!wb) return
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
        const unitId = wb.getId?.() || wb.getUnitId?.()
        if (unitId && api.executeCommand) {
          api
            .executeCommand('sheet.command.set-worksheet-activate', {
              unitId,
              subUnitId: sheetId,
            })
            .catch(() => {})
          activeSheetId.value = sheetId
        }
      }
    } catch (err) {
      console.warn('[useHFixedAssetSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<HFixedAssetSheetGroup[]>(() => {
    const groupMap = new Map<string, HFixedAssetSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyHSheet(sheet.name)
      if (!groupMap.has(sheet.category)) {
        groupMap.set(sheet.category, {
          category: sheet.category,
          icon: cls.icon,
          color: cls.color,
          priority: cls.priority,
          sheets: [],
        })
      }
      groupMap.get(sheet.category)!.sheets.push(sheet)
    }
    return Array.from(groupMap.values()).sort((a, b) => a.priority - b.priority)
  })

  const totalCount = computed(() => sheets.value.length)

  return {
    sheets,
    groups,
    activeSheetId,
    totalCount,
    refresh,
    switchTo,
    classifyHSheet,
  }
}
