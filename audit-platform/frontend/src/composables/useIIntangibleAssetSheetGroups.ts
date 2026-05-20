/**
 * useIIntangibleAssetSheetGroups — I 无形资产循环 sheet 分组 composable
 *
 * spec workpaper-i-intangible-assets-cycle ADR-I5b（Task 2.3）
 *
 * I 循环 6 主底稿（I1~I6）合并后 67 sheet，按 10 类规则分组（+ fallback 其他程序）。
 * 与 H 循环差异：
 *   - I 没有 折旧测算（用 摊销测算 替代）
 *   - I 没有 增减检查/实物盘点/权属检查/关联交易/租赁专项（H 特有）
 *   - I 有 针对性检查（资本化时点判断/研发项目/加计扣除/项目成立条件）
 *   - I 没有 measurement_model（不存在双计量模式）
 *
 * 10 类分组规则（按 priority 匹配顺序，首个命中即停止）：
 *   1. 索引（defaultHidden=true）
 *   2. 历史遗留（defaultHidden=true）
 *   3. 总控台（程序表 xxA）
 *   4. 审定表
 *   5. 附注披露（readonly=true）
 *   6. 明细表
 *   7. 摊销测算
 *   8. 减值测试
 *   9. 针对性检查
 *  10. 调整分录
 *  11. 其他程序（fallback 兜底）
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface ISheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface ISheetPattern extends ISheetCategory {
  pattern: RegExp
}

export interface IIntangibleAssetSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface IIntangibleAssetSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: IIntangibleAssetSheetItem[]
}

// ===== 10 类规则（按 priority 匹配顺序） =====

export const I_SHEET_PATTERNS: ISheetPattern[] = [
  // 1. 索引类（defaultHidden=true）
  {
    pattern: /^底稿目录$|^GT_Custom$|^修订说明$/,
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 0,
    defaultHidden: true,
  },
  // 2. 历史遗留类（defaultHidden=true）— 覆盖 I3 "参考－商誉减值测试示例" 等
  {
    pattern: /参考.*示例|示例[）)]?$|修订前/,
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
  // 7. 摊销测算
  {
    pattern: /摊销测算|摊销分配/,
    category: '摊销测算',
    icon: '📉',
    color: '#7b1fa2',
    priority: 6,
  },
  // 8. 减值测试
  {
    pattern: /减值测试|可收回金额|商誉减值/,
    category: '减值测试',
    icon: '⚠️',
    color: '#d84315',
    priority: 7,
  },
  // 9. 针对性检查（含资本化时点/研发项目/加计扣除/项目成立条件）
  {
    pattern: /资本化时点|研发项目|加计扣除|项目成立条件/,
    category: '针对性检查',
    icon: '🔍',
    color: '#00838f',
    priority: 8,
  },
  // 10. 调整分录
  {
    pattern: /调整分录/,
    category: '调整分录',
    icon: '✏️',
    color: '#3949ab',
    priority: 9,
  },
]

export const FALLBACK_GROUP: ISheetCategory = {
  category: '其他程序',
  icon: '📄',
  color: '#bdbdbd',
  priority: 10,
}

/** 按 I_SHEET_PATTERNS 顺序匹配 sheet 名，返回 I 循环类目元数据 */
export function classifyISheet(name: string): ISheetCategory {
  for (const p of I_SHEET_PATTERNS) {
    if (p.pattern.test(name)) {
      const { pattern: _pattern, ...rest } = p
      return rest
    }
  }
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * I 无形资产循环 sheet 分组 composable
 *
 * 接口与 useHFixedAssetSheetGroups 等同，但不需要 measurementModel 参数
 * （I 循环不存在双计量模式）。
 */
export function useIIntangibleAssetSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<IIntangibleAssetSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyISheet(name)
    if (cls.defaultHidden) return true
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
      const items: IIntangibleAssetSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyISheet(name)
          const item: IIntangibleAssetSheetItem = {
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
        .filter((s: IIntangibleAssetSheetItem) => !s.hidden && !shouldFilterOut(s.name))
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (items.length > 0) {
        activeSheetId.value = items[0].id
      }
    } catch (err) {
      console.warn('[useIIntangibleAssetSheetGroups] refresh failed:', err)
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
      console.warn('[useIIntangibleAssetSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<IIntangibleAssetSheetGroup[]>(() => {
    const groupMap = new Map<string, IIntangibleAssetSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyISheet(sheet.name)
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
    classifyISheet,
  }
}
