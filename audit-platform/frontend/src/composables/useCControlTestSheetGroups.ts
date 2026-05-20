/**
 * useCControlTestSheetGroups — C 类底稿（控制测试）sheet 分组 composable
 *
 * C 循环 36 个模板文件，分为 4 组 + 1 fallback：
 *
 * 4 类规则设计（按 priority 升序）：
 *   1. 索引 (priority=1, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. 企业层面控制测试 (priority=2): C1/C21~C26
 *   3. 业务循环控制测试 (priority=3): C2~C15 各循环控制测试
 *   4. 偏差评价 (priority=4): 各循环评价控制偏差（C*-2 系列）
 *   5. 其他 (priority=99): fallback
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface CSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface CSheetGroupRule extends CSheetCategory {
  id: string
  match: (sheetName: string) => boolean
}

export interface CControlTestSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface CControlTestSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: CControlTestSheetItem[]
}

// ===== 5 类分组规则（按 priority 升序，首个命中即停止） =====

export const C_SHEET_GROUP_RULES: CSheetGroupRule[] = [
  // 1. 索引（底稿目录 / GT_Custom，默认隐藏）
  {
    id: 'index',
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 1,
    defaultHidden: true,
    match: (s) => /^(底稿目录|GT_Custom)$/.test(s.trim()),
  },
  // 2. 企业层面控制测试（企业层面|C1$|C1\b|IT.*控制|会计分录|内审|信息处理）
  {
    id: 'entity_level_test',
    category: '企业层面控制测试',
    icon: '🏢',
    color: '#6a1b9a',
    priority: 2,
    match: (s) => /企业层面|C1\b|C1$|IT.*控制|会计分录|内审|信息处理/.test(s),
  },
  // 3. 业务循环控制测试（循环.*控制测试|C[2-9]\b|C1[0-5]）
  //    注意：排除 C*-2 偏差评价模式（由下一条规则匹配）
  {
    id: 'process_cycle_test',
    category: '业务循环控制测试',
    icon: '🔄',
    color: '#1565c0',
    priority: 3,
    match: (s) => {
      // 先排除偏差评价模式（C\d+-2）
      if (/偏差|C\d+-2/.test(s)) return false
      return /循环.*控制测试|C[2-9]\b|C1[0-5]/.test(s)
    },
  },
  // 4. 偏差评价（偏差|C\d+-2）
  {
    id: 'deviation_evaluation',
    category: '偏差评价',
    icon: '📊',
    color: '#e65100',
    priority: 4,
    match: (s) => /偏差|C\d+-2/.test(s),
  },
  // 5. 其他（fallback）
  {
    id: 'other',
    category: '其他',
    icon: '📄',
    color: '#bdbdbd',
    priority: 99,
    match: () => true,
  },
]

/** Fallback 分组 */
export const FALLBACK_GROUP: CSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 99,
}

/**
 * 按 C_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
 *
 * 规则保证：
 *   - 任意 sheet 名恰好匹配 1 类（最后一条 fallback `match: () => true`）
 *   - 优先级冲突时由 priority 升序决定（首个命中即停止）
 *
 * 特殊处理：
 *   - 索引类（底稿目录/GT_Custom）: defaultHidden=true
 */
export function classifyCSheet(name: string): CSheetCategory {
  for (const rule of C_SHEET_GROUP_RULES) {
    if (rule.match(name)) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { id: _id, match: _match, ...rest } = rule
      return rest
    }
  }
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * C 类底稿（控制测试）sheet 分组 composable
 *
 * @param univerAPI  Univer Facade API ref
 */
export function useCControlTestSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<CControlTestSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyCSheet(name)
    return cls.defaultHidden === true
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
      const items: CControlTestSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyCSheet(name)
          const item: CControlTestSheetItem = {
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
        .filter(
          (s: CControlTestSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useCControlTestSheetGroups] refresh failed:', err)
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
      console.warn('[useCControlTestSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<CControlTestSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, CControlTestSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyCSheet(sheet.name)
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
    classifyCSheet,
  }
}
