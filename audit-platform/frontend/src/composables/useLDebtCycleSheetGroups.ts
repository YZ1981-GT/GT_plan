/**
 * useLDebtCycleSheetGroups — L 筹资循环 sheet 分组 composable
 *
 * spec workpaper-l-debt-cycle L-F2（Task 2.1）
 *
 * 痛点：L 循环 9 文件合并后 79 有效 sheet，模板无业务语义分组。
 *      尤其利息测算 / 逾期贷款检查 / 摊余成本 等专项 sheet 散落在通用类别中。
 *
 * 方案：
 *   按 design.md ADR-L3b 定义 10 类分组规则（首个命中即停止，priority 升序），
 *   索引/历史遗留/附注+调整 默认隐藏，附注披露类 readonly=true。
 *
 * 10 类规则设计（按 priority 升序）：
 *   1. index (0, defaultHidden=true): 底稿目录 / GT_Custom / 修订说明
 *   2. historical (1, defaultHidden=true): （示例）模式
 *   3. procedure (2): 实质性程序表 / xxA 结尾
 *   4. audit_table (3): 审定表
 *   5. detail (4): 明细表
 *   6. analysis (5): 分析程序
 *   7. interest_calc (6): 利息测算 / 利息计算 / 利率测算
 *   8. check_table (7): 逾期 / 检查表 / 核查表 / 摊余成本
 *   9. disclosure_adj (8, defaultHidden=true): 附注披露 / 调整分录
 *  10. other (9): fallback
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface LSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface LSheetGroupRule extends LSheetCategory {
  id: string
  match: (sheetName: string) => boolean
}

export interface LDebtCycleSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface LDebtCycleSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: LDebtCycleSheetItem[]
}


// ===== 10 类分组规则（按 priority 升序，首个命中即停止） =====

export const L_SHEET_GROUP_RULES: LSheetGroupRule[] = [
  // 1. 索引类（底稿目录 / GT_Custom / 修订说明，默认隐藏）
  {
    id: 'index',
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 0,
    defaultHidden: true,
    match: (s) => /^底稿目录$|^GT_Custom$|^修订说明$/.test(s.trim()),
  },
  // 2. 历史遗留类（含"（示例）"或"(示例)"或以"示例"结尾，默认隐藏）
  {
    id: 'historical',
    category: '历史遗留',
    icon: '🗄️',
    color: '#757575',
    priority: 1,
    defaultHidden: true,
    match: (s) => /（示例）|\(示例\)|示例$/.test(s),
  },
  // 3. 总控台（程序表 xxA 结尾 / 实质性程序表）
  {
    id: 'procedure',
    category: '总控台',
    icon: '🎯',
    color: '#1976d2',
    priority: 2,
    match: (s) => /[A-Z]\d*A\s*$/.test(s) || /实质性程序表/.test(s),
  },
  // 4. 审定表
  {
    id: 'audit_table',
    category: '审定表',
    icon: '✅',
    color: '#388e3c',
    priority: 3,
    match: (s) => /审定表/.test(s),
  },
  // 5. 明细表
  {
    id: 'detail',
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 4,
    match: (s) => /明细表/.test(s),
  },
  // 6. 分析程序
  {
    id: 'analysis',
    category: '分析程序',
    icon: '📊',
    color: '#00838f',
    priority: 5,
    match: (s) => /分析程序/.test(s),
  },
  // 7. 利息测算（利息测算 / 利息计算 / 利率测算）
  {
    id: 'interest_calc',
    category: '利息测算',
    icon: '💹',
    color: '#c62828',
    priority: 6,
    match: (s) => /利息测算|利息计算|利率测算/.test(s),
  },
  // 8. 逾期/检查表/摊余成本
  {
    id: 'check_table',
    category: '检查表',
    icon: '🔍',
    color: '#5e35b1',
    priority: 7,
    match: (s) => /逾期|检查表|核查表|摊余成本/.test(s),
  },
  // 9. 附注披露 + 调整分录（defaultHidden=true，附注披露 readonly=true）
  {
    id: 'disclosure_adj',
    category: '附注+调整',
    icon: '📝',
    color: '#795548',
    priority: 8,
    defaultHidden: true,
    match: (s) => /附注披露|调整分录/.test(s),
  },
  // 10. 其他程序（fallback）
  {
    id: 'other',
    category: '其他程序',
    icon: '📄',
    color: '#bdbdbd',
    priority: 9,
    match: () => true,
  },
]

/** Fallback 分组 */
export const FALLBACK_GROUP: LSheetCategory = {
  category: '其他程序',
  icon: '📄',
  color: '#bdbdbd',
  priority: 9,
}

/**
 * 按 L_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
 *
 * 规则保证：
 *   - 任意 sheet 名恰好匹配 1 类（最后一条 fallback `match: () => true`）
 *   - 优先级冲突时由 priority 升序决定（首个命中即停止）
 *
 * 特殊处理：
 *   - 索引类（底稿目录/GT_Custom/修订说明）: defaultHidden=true
 *   - 历史遗留类（含"示例"）: defaultHidden=true
 *   - 附注披露类（含"附注披露"关键词）: defaultHidden=true + readonly=true
 *   - 调整分录类（含"调整分录"但不含"附注披露"）: defaultHidden=true, readonly=false
 */
export function classifyLSheet(name: string): LSheetCategory {
  for (const rule of L_SHEET_GROUP_RULES) {
    if (rule.match(name)) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { id: _id, match: _match, ...rest } = rule

      // 附注+调整类特殊处理：附注披露 readonly=true
      if (_id === 'disclosure_adj' && /附注披露/.test(name)) {
        return { ...rest, defaultHidden: true, readonly: true }
      }

      return rest
    }
  }
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * L 筹资循环 sheet 分组 composable
 *
 * @param univerAPI  Univer Facade API ref
 */
export function useLDebtCycleSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<LDebtCycleSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyLSheet(name)
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
      const items: LDebtCycleSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyLSheet(name)
          const item: LDebtCycleSheetItem = {
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
          (s: LDebtCycleSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useLDebtCycleSheetGroups] refresh failed:', err)
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
      console.warn('[useLDebtCycleSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<LDebtCycleSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, LDebtCycleSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyLSheet(sheet.name)
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
    classifyLSheet,
  }
}
