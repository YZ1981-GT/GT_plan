/**
 * useKAdminCycleSheetGroups — K 管理循环 sheet 分组 composable
 *
 * spec workpaper-k-admin-cycle K-F2（Task 2.1）
 *
 * 痛点：K 循环 14 文件合并后 109 有效 sheet，模板无业务语义分组。
 *      尤其 K8/K9 费用明细 / K1/K3 往来款检查 等专项 sheet 散落在通用类别中。
 *
 * 方案：
 *   按 design.md K-F2 定义 11 类分组规则（首个命中即停止，priority 升序），
 *   索引默认隐藏，附注披露类 defaultHidden=true。
 *
 * 10 类规则设计（按 priority 升序）：
 *   1. index (0, defaultHidden=true): 底稿目录 / GT_Custom
 *   2. procedure (1): 实质性程序表 / 函证程序表 / xxA 结尾
 *   3. audit_table (2): 审定表 / 情况表 / 函证结果汇总
 *   4. expense_detail (3): 明细表K8-2 / 明细表K9-2 / K10-2~K13-2 (费用类月度明细，特殊匹配前置)
 *   5. detail (4): 其他 明细表
 *   6. analysis (5): 分析 / 对比 / 情况分析
 *   7. receivable_payable_check (6): K1-/K3- 含 检查/账龄/挂账/关联方/三阶段/未收回/大额
 *   8. check_table (7): 检查表 / 计提 / 分配 / 截止性测试 / 测算 / 测试表 / 政策检查
 *   9. confirmation_aux (7.5): K0-x 函证辅助（函证/替代程序/回函/核实/舞弊风险/差异调节/过程控制/会计提示）
 *  10. disclosure_adj (8): 附注披露 (defaultHidden=true) / 调整分录
 *  11. other (9): fallback
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

export interface KSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface KSheetGroupRule extends KSheetCategory {
  id: string
  match: (sheetName: string) => boolean
}

export interface KAdminCycleSheetItem {
  id: string
  name: string
  index: number
  category: string
  hidden: boolean
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface KAdminCycleSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: KAdminCycleSheetItem[]
}

// ===== 11 类分组规则（按 priority 升序，首个命中即停止） =====

export const K_SHEET_GROUP_RULES: KSheetGroupRule[] = [
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
  // 2. 程序表（实质性程序表 / 函证程序表 / xxA 结尾）
  {
    id: 'procedure',
    category: '程序表',
    icon: '🎯',
    color: '#1976d2',
    priority: 1,
    match: (s) =>
      /实质性程序表/.test(s) ||
      /函证程序表/.test(s) ||
      /[A-Z]\d*A$/.test(s.trim()) ||
      /[A-Z]\d*A-/.test(s) ||
      /[A-Z]\d*A /.test(s),
  },
  // 3. 审定表（审定表 / 情况表 / 函证结果汇总）
  {
    id: 'audit_table',
    category: '审定表',
    icon: '✅',
    color: '#388e3c',
    priority: 2,
    match: (s) => /审定表|情况表|函证结果汇总/.test(s),
  },
  // 4. 费用明细（K8-2/K9-2/K10-2/K11-2/K12-2/K13-2 费用类月度明细 — 优先于通用明细表）
  {
    id: 'expense_detail',
    category: '费用明细',
    icon: '💰',
    color: '#e91e63',
    priority: 3,
    match: (s) => /^明细表K(8|9|1[0-3])-/.test(s.trim()),
  },
  // 5. 明细表（其他 明细表）
  {
    id: 'detail',
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 4,
    match: (s) => /明细表/.test(s),
  },
  // 6. 分析程序（分析 / 对比 / 情况分析）
  {
    id: 'analysis',
    category: '分析程序',
    icon: '📊',
    color: '#00838f',
    priority: 5,
    match: (s) => /分析|对比|情况分析/.test(s),
  },
  // 7. 往来款检查（K1-/K3- 含 检查/账龄/挂账/关联方/三阶段/未收回/大额）
  {
    id: 'receivable_payable_check',
    category: '往来款检查',
    icon: '🔄',
    color: '#7b1fa2',
    priority: 6,
    match: (s) =>
      /K[13]-/.test(s) &&
      /(检查|账龄|挂账|关联方|三阶段|未收回|大额|坏账|核销|转回|替代程序|信用减值)/.test(s),
  },
  // 8. 检查表（检查表 / 计提 / 分配 / 截止性测试 / 测算 / 测试表 / 政策检查 / 核对表）
  //    "计提"必须不被 "会"前缀（避免误命中"会计提示"）
  {
    id: 'check_table',
    category: '检查表',
    icon: '🔍',
    color: '#5e35b1',
    priority: 7,
    match: (s) =>
      /检查表|分配|截止性测试|测算|测试表|政策检查|核对表/.test(s) ||
      /(?<!会)计提/.test(s),
  },
  // 9. 函证辅助（K0-2~K0-8 函证相关 sheet）
  {
    id: 'confirmation_aux',
    category: '函证辅助',
    icon: '📮',
    color: '#00695c',
    priority: 7.5,
    match: (s) => /K0[-]?\d/.test(s) && /函证|替代程序|回函|核实|舞弊风险|差异调节|过程控制|会计提示/.test(s),
  },
  // 10. 附注+调整（附注披露 / 调整分录）
  //     附注披露 defaultHidden=true（通过 classifyKSheet 特殊处理）
  {
    id: 'disclosure_adj',
    category: '附注+调整',
    icon: '📝',
    color: '#795548',
    priority: 8,
    defaultHidden: false,
    match: (s) => /附注披露|调整分录|调整分录汇总/.test(s),
  },
  // 11. 其他（fallback）
  {
    id: 'other',
    category: '其他',
    icon: '📄',
    color: '#bdbdbd',
    priority: 9,
    match: () => true,
  },
]

/** Fallback 分组 */
export const FALLBACK_GROUP: KSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 9,
}

/**
 * 按 K_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
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
export function classifyKSheet(name: string): KSheetCategory {
  for (const rule of K_SHEET_GROUP_RULES) {
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
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * K 管理循环 sheet 分组 composable
 *
 * @param univerAPI  Univer Facade API ref
 */
export function useKAdminCycleSheetGroups(univerAPI: Ref<any>) {
  const sheets = ref<KAdminCycleSheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyKSheet(name)
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
      const items: KAdminCycleSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyKSheet(name)
          const item: KAdminCycleSheetItem = {
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
          (s: KAdminCycleSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useKAdminCycleSheetGroups] refresh failed:', err)
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
      console.warn('[useKAdminCycleSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<KAdminCycleSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, KAdminCycleSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyKSheet(sheet.name)
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
    classifyKSheet,
  }
}
