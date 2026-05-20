/**
 * useJPayrollSheetGroups — J 职工薪酬循环 sheet 分组 composable
 *
 * spec workpaper-j-payroll-cycle ADR-J1 / J-F2（Task 2.1）
 *
 * 痛点：J 循环 J1~J3 共 3 文件合并后 29 有效 sheet。
 *      模板无业务语义分组（索引/程序表/审定表/明细表/分析程序/检查表/
 *      IPO专项/附注+调整 等），用户难以快速定位。
 *
 * 方案：
 *   按 design.md J-F2 定义 8 类分组规则（首个命中即停止，priority 升序），
 *   索引默认隐藏，附注披露类 defaultHidden=true。
 *
 * 8 类规则设计（按 priority 升序）：
 *   1. index: 底稿目录 / GT_Custom → defaultHidden=true
 *   2. procedure: 实质性程序表 / xxA 结尾 → 程序表
 *   3. audit_table: 审定表 / 情况表 → 审定表
 *   4. detail: 明细表 → 明细表
 *   5. analysis: 分析 / 对比 → 分析程序
 *   6. check_table: 检查表 / 计提情况 / 分配情况 → 检查表
 *   7. ipo: IPO / 首发 → IPO专项
 *   8. disclosure_adj: 附注披露 / 调整分录 → 附注+调整（附注 defaultHidden=true）
 *   9. other: fallback → 其他
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

/** sheet 类目元数据 */
export interface JSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

/** 名称匹配规则（按 priority 升序匹配，首个命中即停止） */
export interface JSheetGroupRule extends JSheetCategory {
  /** 类别 ID */
  id: string
  /** 匹配函数：返回 true 表示该 sheet 名属于本类目 */
  match: (sheetName: string) => boolean
}

/** sheet 项 */
export interface JPayrollSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

/** 分组（按 priority 升序展示） */
export interface JPayrollSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: JPayrollSheetItem[]
}

// ===== 8 类分组规则（按 priority 升序，首个命中即停止） =====

export const J_SHEET_GROUP_RULES: JSheetGroupRule[] = [
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
  // 2. 程序表（实质性程序表 / xxA 结尾 / xxA- / xxA 空格）
  {
    id: 'procedure',
    category: '程序表',
    icon: '🎯',
    color: '#1976d2',
    priority: 1,
    match: (s) =>
      /实质性程序表/.test(s) ||
      /[A-Z]\d*A$/.test(s.trim()) ||
      /[A-Z]\d*A-/.test(s) ||
      /[A-Z]\d*A /.test(s),
  },
  // 3. 审定表（审定表 / 情况表）
  {
    id: 'audit_table',
    category: '审定表',
    icon: '✅',
    color: '#388e3c',
    priority: 2,
    match: (s) => /审定表|情况表/.test(s),
  },
  // 4. 明细表
  {
    id: 'detail',
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 3,
    match: (s) => /明细表/.test(s),
  },
  // 5. 分析程序（分析 / 对比）
  {
    id: 'analysis',
    category: '分析程序',
    icon: '📊',
    color: '#00838f',
    priority: 4,
    match: (s) => /分析|对比/.test(s),
  },
  // 6. 检查表（检查表 / 计提情况 / 分配情况）
  {
    id: 'check_table',
    category: '检查表',
    icon: '🔍',
    color: '#5e35b1',
    priority: 5,
    match: (s) => /检查表|计提情况|分配情况/.test(s),
  },
  // 7. IPO专项（IPO / 首发）
  {
    id: 'ipo',
    category: 'IPO专项',
    icon: '🏢',
    color: '#d84315',
    priority: 6,
    match: (s) => /IPO|首发/.test(s),
  },
  // 8. 附注+调整（附注披露 / 调整分录）
  //    附注披露 defaultHidden=true（通过 classifyJSheet 特殊处理）
  {
    id: 'disclosure_adj',
    category: '附注+调整',
    icon: '📝',
    color: '#795548',
    priority: 7,
    defaultHidden: false,
    match: (s) => /附注披露|调整分录/.test(s),
  },
  // 9. 其他（fallback）
  {
    id: 'other',
    category: '其他',
    icon: '📄',
    color: '#bdbdbd',
    priority: 8,
    match: () => true,
  },
]

/** Fallback 分组 */
export const FALLBACK_GROUP: JSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 8,
}

/**
 * 按 J_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
 *
 * 规则保证：
 *   - 任意 sheet 名恰好匹配 1 类（最后一条 fallback `match: () => true`）
 *   - 优先级冲突时由 priority 升序决定（首个命中即停止）
 *
 * 特殊处理：
 *   - 索引类（底稿目录/GT_Custom）: defaultHidden=true
 *   - 附注披露类（含"附注披露"关键词）: defaultHidden=true
 *   - 调整分录类（含"调整分录"但不含"附注披露"）: defaultHidden=false
 */
export function classifyJSheet(name: string): JSheetCategory {
  for (const rule of J_SHEET_GROUP_RULES) {
    if (rule.match(name)) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { id: _id, match: _match, ...rest } = rule

      // 附注+调整类特殊处理：附注披露 defaultHidden=true
      if (_id === 'disclosure_adj' && /附注披露/.test(name)) {
        return { ...rest, defaultHidden: true }
      }

      return rest
    }
  }
  // 不会到达（fallback `match: () => true` 必然命中）
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * J 职工薪酬循环 sheet 分组 composable
 *
 * @param univerAPI  Univer Facade API ref
 */
export function useJPayrollSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<JPayrollSheetItem[]>([])
  const activeSheetId = ref<string>('')

  /** 是否应过滤掉该 sheet（基于类目 defaultHidden） */
  function shouldFilterOut(name: string): boolean {
    const cls = classifyJSheet(name)
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
      const items: JPayrollSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyJSheet(name)
          const item: JPayrollSheetItem = {
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
          (s: JPayrollSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useJPayrollSheetGroups] refresh failed:', err)
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
      console.warn('[useJPayrollSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<JPayrollSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, JPayrollSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyJSheet(sheet.name)
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
    classifyJSheet,
  }
}
