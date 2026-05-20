/**
 * useNTaxCycleSheetGroups — N 税金循环 sheet 分组 composable
 *
 * spec workpaper-n-tax-cycle N-F2（Task 2.1）
 *
 * 痛点：N 循环 5 文件合并后 45 有效 sheet，模板无业务语义分组。
 *      尤其税费计算 / 递延所得税 / 附注披露 等专项 sheet 散落在通用类别中。
 *
 * 方案：
 *   按 design.md CP-2 定义 8 类分组规则（首个命中即停止，priority 升序），
 *   索引默认隐藏，附注+调整类 defaultHidden=true。
 *
 * 8 类规则设计（按 priority 升序）：
 *   1. index (1, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. procedure (2): 程序表 / N*A 结尾
 *   3. audit_table (3): 审定表
 *   4. detail (4): 明细表
 *   5. tax_calc (5): 测算表 / 计算表 / 税费计算 / 应交税费
 *   6. deferred_tax (6): 递延所得税核对 / 递延费用
 *   7. notes_adj (7, defaultHidden=true): 附注披露 / 调整分录
 *   8. other (99): fallback
 *
 * _Requirements: N-F2_
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface NSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface NSheetGroupRule extends NSheetCategory {
  id: string
  match: (sheetName: string) => boolean
}

export interface NTaxCycleSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface NTaxCycleSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: NTaxCycleSheetItem[]
}

// ===== 8 类分组规则（按 priority 升序，首个命中即停止） =====

export const N_SHEET_GROUP_RULES: NSheetGroupRule[] = [
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
  // 2. 程序表（含"程序表"关键词 或 N*A 结尾，如"应交税费审计程序表N2A"）
  {
    id: 'procedure',
    category: '程序表',
    icon: '🎯',
    color: '#1976d2',
    priority: 2,
    match: (s) => /程序表|[A-Z]\d*A\s*$/.test(s),
  },
  // 3. 审定表（含"审定表"关键词，如 N1-1/N2-1/N3-1/N4-1/N5-1）
  {
    id: 'audit_table',
    category: '审定表',
    icon: '✅',
    color: '#388e3c',
    priority: 3,
    match: (s) => /审定表/.test(s),
  },
  // 4. 明细表（含"明细表"关键词，如 N1-2/N2-2/N3-2/N4-2/N5-2）
  {
    id: 'detail',
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 4,
    match: (s) => /明细表/.test(s),
  },
  // 5. 税费计算（测算表 / 计算表 / 税费.*计算 / 应交.*税费）
  //    如：应交其他税费测算表N2-8, 当期所得税费用计算表N5-4
  {
    id: 'tax_calc',
    category: '税费计算',
    icon: '🧮',
    color: '#e65100',
    priority: 5,
    match: (s) => /测算表|计算表|税费.*计算|应交.*税费/.test(s),
  },
  // 6. 递延所得税（递延所得税.*核对 / 递延.*费用）
  //    如：递延所得税费用核对表N5-8, 递延所得税资产/负债相关
  {
    id: 'deferred_tax',
    category: '递延所得税',
    icon: '⏳',
    color: '#4a148c',
    priority: 6,
    match: (s) => /递延所得税.*核对|递延.*费用/.test(s),
  },
  // 7. 附注+调整（附注披露 / 调整分录，defaultHidden=true）
  {
    id: 'notes_adj',
    category: '附注+调整',
    icon: '📝',
    color: '#795548',
    priority: 7,
    defaultHidden: true,
    match: (s) => /附注披露|调整分录/.test(s),
  },
  // 8. 其他（fallback）
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
export const FALLBACK_GROUP: NSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 99,
}

/**
 * 按 N_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
 *
 * 规则保证：
 *   - 任意 sheet 名恰好匹配 1 类（最后一条 fallback `match: () => true`）
 *   - 优先级冲突时由 priority 升序决定（首个命中即停止）
 *
 * 特殊处理：
 *   - 索引类（底稿目录/GT_Custom）: defaultHidden=true
 *   - 附注+调整类（含"附注披露"/"调整分录"关键词）: defaultHidden=true
 *   - 附注披露子类（含"附注披露"）: defaultHidden=true + readonly=true
 */
export function classifyNSheet(name: string): NSheetCategory {
  for (const rule of N_SHEET_GROUP_RULES) {
    if (rule.match(name)) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { id: _id, match: _match, ...rest } = rule

      // 附注+调整类特殊处理：附注披露 readonly=true
      if (_id === 'notes_adj' && /附注披露/.test(name)) {
        return { ...rest, defaultHidden: true, readonly: true }
      }

      return rest
    }
  }
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * N 税金循环 sheet 分组 composable
 *
 * @param univerAPI  Univer Facade API ref
 */
export function useNTaxCycleSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<NTaxCycleSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyNSheet(name)
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
      const items: NTaxCycleSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyNSheet(name)
          const item: NTaxCycleSheetItem = {
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
          (s: NTaxCycleSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useNTaxCycleSheetGroups] refresh failed:', err)
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
      console.warn('[useNTaxCycleSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<NTaxCycleSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, NTaxCycleSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyNSheet(sheet.name)
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
    classifyNSheet,
  }
}
