/**
 * useBAuditPlanSheetGroups — B 类底稿（控制了解/审计计划）sheet 分组 composable
 *
 * B 循环 49 个模板文件，分为 6 组 + 1 fallback：
 *
 * 6 类规则设计（按 priority 升序）：
 *   1. 索引 (priority=1, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. 风险评估 (priority=2): 风险评估表/业务承接/独立性/项目组讨论/汇总风险
 *   3. 了解环境 (priority=3): 了解被审计单位/访谈/分析程序/重要性
 *   4. 企业层面控制 (priority=4): B22系列
 *   5. 业务层面控制 (priority=5): B23系列（了解业务层面控制）
 *   6. 集团审计+项目管理 (priority=6): 集团审计/工时预算
 *   7. 其他 (priority=99): fallback
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface BSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface BSheetGroupRule extends BSheetCategory {
  id: string
  match: (sheetName: string) => boolean
}

export interface BAuditPlanSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface BAuditPlanSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: BAuditPlanSheetItem[]
}

// ===== 7 类分组规则（按 priority 升序，首个命中即停止） =====

export const B_SHEET_GROUP_RULES: BSheetGroupRule[] = [
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
  // 2. 风险评估（风险评估|B1-|B1A|B1B|B2\b|B3\b|B40|B50|B51|B52）
  //    注意：B2/B3 用 \b 避免误命中 B22/B23/B30
  {
    id: 'risk_assessment',
    category: '风险评估',
    icon: '⚠️',
    color: '#d32f2f',
    priority: 2,
    match: (s) => /风险评估|B1-|B1A|B1B|B2\b|B3\b|B40|B50|B51|B52/.test(s),
  },
  // 3. 了解环境（了解.*环境|B10|B11|B12|B13|B15|B18|B19|初步分析|重要性）
  {
    id: 'understand_environment',
    category: '了解环境',
    icon: '🔎',
    color: '#1565c0',
    priority: 3,
    match: (s) => /了解.*环境|B10|B11|B12|B13|B15|B18|B19|初步分析|重要性/.test(s),
  },
  // 4. 企业层面控制（企业层面|B22|控制环境|管理层凌驾|信息与沟通|监督|控制矩阵|设计有效性|IT概要|信息系统|IT一般控制）
  {
    id: 'entity_level_control',
    category: '企业层面控制',
    icon: '🏢',
    color: '#6a1b9a',
    priority: 4,
    match: (s) =>
      /企业层面|B22|控制环境|管理层凌驾|信息与沟通|监督|控制矩阵|设计有效性|IT概要|信息系统|IT一般控制/.test(s),
  },
  // 5. 业务层面控制（B23|信息处理控制|职责分离）
  {
    id: 'process_level_control',
    category: '业务层面控制',
    icon: '⚙️',
    color: '#00838f',
    priority: 5,
    match: (s) => /B23|信息处理控制|职责分离/.test(s),
  },
  // 6. 集团审计+项目管理（集团|B30|工时|B60）
  {
    id: 'group_audit',
    category: '集团审计+项目管理',
    icon: '🌐',
    color: '#2e7d32',
    priority: 6,
    match: (s) => /集团|B30|工时|B60/.test(s),
  },
  // 7. 其他（fallback）
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
export const FALLBACK_GROUP: BSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 99,
}

/**
 * 按 B_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
 *
 * 规则保证：
 *   - 任意 sheet 名恰好匹配 1 类（最后一条 fallback `match: () => true`）
 *   - 优先级冲突时由 priority 升序决定（首个命中即停止）
 *
 * 特殊处理：
 *   - 索引类（底稿目录/GT_Custom）: defaultHidden=true
 */
export function classifyBSheet(name: string): BSheetCategory {
  for (const rule of B_SHEET_GROUP_RULES) {
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
 * B 类底稿（控制了解/审计计划）sheet 分组 composable
 *
 * @param univerAPI  Univer Facade API ref
 */
export function useBAuditPlanSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<BAuditPlanSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyBSheet(name)
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
      const items: BAuditPlanSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyBSheet(name)
          const item: BAuditPlanSheetItem = {
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
          (s: BAuditPlanSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useBAuditPlanSheetGroups] refresh failed:', err)
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
      console.warn('[useBAuditPlanSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<BAuditPlanSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, BAuditPlanSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyBSheet(sheet.name)
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
    classifyBSheet,
  }
}
