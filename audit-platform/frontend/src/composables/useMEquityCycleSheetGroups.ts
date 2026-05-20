/**
 * useMEquityCycleSheetGroups — M 权益循环 sheet 分组 composable
 *
 * spec workpaper-m-equity-cycle M-F2（Task 2.1）
 *
 * 痛点：M 循环 10 文件合并后 65 有效 sheet，模板无业务语义分组。
 *      尤其变动分析 / 检查表 / 附注披露 等专项 sheet 散落在通用类别中。
 *
 * 方案：
 *   按 design.md CP-2 定义 8 类分组规则（首个命中即停止，priority 升序），
 *   索引默认隐藏，附注+调整类 defaultHidden=true。
 *
 * 8 类规则设计（按 priority 升序）：
 *   1. index (0, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. procedure (1): 实质性程序表 / M*A 结尾
 *   3. audit_table (2): 审定表M*-1 pattern
 *   4. detail (3): 明细表 pattern（M2-2, M4-2, M5-2, M6-2, M9-2, M10-2）
 *   5. movement_analysis (4): 变动 / 增减 / 权益变动
 *   6. check_table (5): 检查 / 核查 / 测试（含针对性测试）
 *   7. disclosure_adj (6, defaultHidden=true): 附注 / 披露 / 调整
 *   8. other (7): fallback
 *
 * _Requirements: M-F2_
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface MSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface MSheetGroupRule extends MSheetCategory {
  id: string
  match: (sheetName: string) => boolean
}

export interface MEquityCycleSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface MEquityCycleSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: MEquityCycleSheetItem[]
}

// ===== 8 类分组规则（按 priority 升序，首个命中即停止） =====

export const M_SHEET_GROUP_RULES: MSheetGroupRule[] = [
  // 1. 索引（底稿目录 / GT_Custom，默认隐藏）
  {
    id: 'index',
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 0,
    defaultHidden: true,
    match: (s) => /^底稿目录$|^GT_Custom$/.test(s.trim()),
  },
  // 2. 程序表（实质性程序表 / M*A 结尾，如"实收资本实质性程序表M2A"）
  {
    id: 'procedure',
    category: '程序表',
    icon: '🎯',
    color: '#1976d2',
    priority: 1,
    match: (s) =>
      /实质性程序表/.test(s) ||
      /[A-Z]\d*A\s*$/.test(s.trim()) ||
      /M\d+A\s*$/.test(s.trim()),
  },
  // 3. 审定表（审定表M*-1 pattern）
  {
    id: 'audit_table',
    category: '审定表',
    icon: '✅',
    color: '#388e3c',
    priority: 2,
    match: (s) => /审定表/.test(s),
  },
  // 4. 明细表（明细表 pattern，含上市/非上市变体）
  {
    id: 'detail',
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 3,
    match: (s) => /明细表/.test(s),
  },
  // 5. 变动分析（变动 / 增减 / 权益变动）
  {
    id: 'movement_analysis',
    category: '变动分析',
    icon: '📊',
    color: '#00838f',
    priority: 4,
    match: (s) => /变动|增减|权益变动/.test(s),
  },
  // 6. 检查表（检查 / 核查 / 测试 / 针对性测试）
  //    注意：避免误命中"测试M8-5-删除"等历史遗留（已被 _should_skip_historical_sheet 过滤）
  {
    id: 'check_table',
    category: '检查表',
    icon: '🔍',
    color: '#5e35b1',
    priority: 5,
    match: (s) => /检查|核查|测试/.test(s),
  },
  // 7. 附注+调整（附注 / 披露 / 调整，defaultHidden=true）
  {
    id: 'disclosure_adj',
    category: '附注+调整',
    icon: '📝',
    color: '#795548',
    priority: 6,
    defaultHidden: true,
    match: (s) => /附注|披露|调整/.test(s),
  },
  // 8. 其他（fallback）
  {
    id: 'other',
    category: '其他',
    icon: '📄',
    color: '#bdbdbd',
    priority: 7,
    match: () => true,
  },
]

/** Fallback 分组 */
export const FALLBACK_GROUP: MSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 7,
}

/**
 * 按 M_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
 *
 * 规则保证：
 *   - 任意 sheet 名恰好匹配 1 类（最后一条 fallback `match: () => true`）
 *   - 优先级冲突时由 priority 升序决定（首个命中即停止）
 *
 * 特殊处理：
 *   - 索引类（底稿目录/GT_Custom）: defaultHidden=true
 *   - 附注+调整类（含"附注"/"披露"/"调整"关键词）: defaultHidden=true
 *   - 附注披露子类（含"附注披露"）: defaultHidden=true + readonly=true
 */
export function classifyMSheet(name: string): MSheetCategory {
  for (const rule of M_SHEET_GROUP_RULES) {
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
 * M 权益循环 sheet 分组 composable
 *
 * @param univerAPI  Univer Facade API ref
 */
export function useMEquityCycleSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<MEquityCycleSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyMSheet(name)
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
      const items: MEquityCycleSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyMSheet(name)
          const item: MEquityCycleSheetItem = {
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
          (s: MEquityCycleSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useMEquityCycleSheetGroups] refresh failed:', err)
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
      console.warn('[useMEquityCycleSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<MEquityCycleSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, MEquityCycleSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyMSheet(sheet.name)
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
    classifyMSheet,
  }
}
