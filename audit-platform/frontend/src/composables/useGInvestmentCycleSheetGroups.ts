/**
 * useGInvestmentCycleSheetGroups — G 投资循环 sheet 分组 composable
 *
 * spec workpaper-g-investment-cycle ADR-G2 / ADR-G6（Task 1.2 + Task 2.1）
 *
 * 痛点：G 循环 G0~G14 共 15 主底稿合并后 152 sheet。
 *      ① G7 长期股权投资支持三种核算方式（权益法/成本法/公允价值法），按
 *        每笔投资配置（同项目可同时存在采用不同方式的多笔投资）。
 *      ② 152 sheet 默认全部展示，致同模板无业务语义分组（索引/总控台/审定表/
 *        明细表/公允价值/减值/收益/分类/函证/调整 等），用户难以快速定位。
 *
 * 方案：
 *   ① 读取 `working_paper.parsed_data.g7_accounting_methods[]`，按当前选中投资
 *      的 method 控制 G7 sheet 显隐。
 *   ② 按 design.md ADR-G6 定义 12 类分组规则（首个命中即停止，priority 升序），
 *      索引/历史遗留默认隐藏，附注披露 readonly。
 */
import { computed, ref, type Ref } from 'vue'

// ===== 类型定义 =====

/** G7 三种核算方式枚举（与后端约定一致） */
export type G7AccountingMethod = 'equity_method' | 'cost_method' | 'fair_value_method'

/** parsed_data.g7_accounting_methods 数组项 */
export interface G7AccountingMethodEntry {
  investee_name: string
  method: G7AccountingMethod
}

/** working_paper.parsed_data 中本 composable 关心的字段子集 */
export interface GParsedData {
  /** G7 长期股权投资 per-investment 核算方式配置 */
  g7_accounting_methods?: G7AccountingMethodEntry[]
  [key: string]: unknown
}

/** sheet 类目元数据 */
export interface GSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

/** 名称匹配规则（按 priority 升序匹配，首个命中即停止） */
export interface GSheetGroupRule extends GSheetCategory {
  /** 类别 ID（与 design.md ADR-G6 对齐） */
  id: string
  /** 匹配函数：返回 true 表示该 sheet 名属于本类目 */
  match: (sheetName: string) => boolean
}

/** sheet 项（含 G 循环特有字段，与 D/F/H/I 接口对齐） */
export interface GInvestmentCycleSheetItem {
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
export interface GInvestmentCycleSheetGroup {
  category: string
  icon: string
  color: string
  priority: number
  sheets: GInvestmentCycleSheetItem[]
}

// ===== G7 核算方式 sheet 名匹配规则（Task 1.2 既有逻辑，保留） =====
//
// - 三种方式各对应一组关键词（基于 requirements.md G-F3.2/3/4）
// - 减值测试在 equity_method 与 cost_method 共享
// - "method-specific sheet" = 至少匹配一个方式的关键词 → 受方式过滤约束
// - "method-agnostic G7 sheet" = G7 通用 sheet（如 G7A 总控台 / 审定表G7-1）
//   → 不受方式过滤影响（始终显示）

export const G7_METHOD_SHEET_PATTERNS: Record<G7AccountingMethod, RegExp> = {
  // 权益法：投资收益确认 / 权益变动 / 减值测试 / 对账
  equity_method: /权益法|投资收益确认|权益变动|减值测试|对账/,
  // 成本法：分红确认 / 减值测试
  cost_method: /成本法|分红确认|股利确认|减值测试/,
  // 公允价值法：公允价值测试 / 变动损益
  fair_value_method: /公允价值法|公允价值测试|变动损益|公允价值变动/,
}

/** G7 sheet 识别（兼容裸 wp_code 后缀 / 含 G7 名称片段） */
export function isG7Sheet(name: string): boolean {
  return /G7\b|G7-\d|G7A\b/.test(name)
}

/**
 * 是否 method-specific G7 sheet（命中至少一个方式的 pattern）
 *
 * - 命中 → 受方式过滤约束（按当前 method 决定显隐）
 * - 未命中 → 通用 G7 sheet，始终显示
 */
export function isG7MethodSpecificSheet(name: string): boolean {
  return Object.values(G7_METHOD_SHEET_PATTERNS).some((p) => p.test(name))
}

/**
 * 解析当前 G7 核算方式
 *
 * 以下情况返回 null（→ 触发 fallback 全显）：
 *   - parsedData 为 null/undefined
 *   - g7_accounting_methods 字段缺失或为空数组
 *   - currentInvesteeName 为空
 *   - 在 g7_accounting_methods 中找不到对应 investee_name
 */
export function resolveG7AccountingMethod(
  parsedData: GParsedData | null | undefined,
  currentInvesteeName?: string | null,
): G7AccountingMethod | null {
  if (!parsedData) return null
  const list = parsedData.g7_accounting_methods
  if (!Array.isArray(list) || list.length === 0) return null
  if (!currentInvesteeName) return null
  const entry = list.find((e) => e?.investee_name === currentInvesteeName)
  return entry?.method ?? null
}

/**
 * 按 G7 核算方式过滤 sheet 列表
 *
 * - 非 G7 sheet：始终保留
 * - G7 通用 sheet（不含方式关键词）：始终保留
 * - G7 method-specific sheet：仅当匹配 `method` 对应 pattern 时保留
 * - **Fallback（G-F3.5）**：method 为 null/undefined → 不做任何过滤，全量返回
 */
export function filterByG7AccountingMethod<T extends { name: string }>(
  sheets: T[],
  method: G7AccountingMethod | null | undefined,
): T[] {
  if (!method) return sheets
  return sheets.filter((s) => {
    if (!isG7Sheet(s.name)) return true
    if (!isG7MethodSpecificSheet(s.name)) return true
    return G7_METHOD_SHEET_PATTERNS[method].test(s.name)
  })
}

// ===== ADR-G6 12 类分组规则（按 priority 升序，首个命中即停止） =====
//
// 历史遗留正则采用 F 循环已验证模式：
//   - "修订前" / "（原）" / "(原)" / "G+数字+删除/移至" / "（示例）"
// G11/G12/G13/G14 4 个"修订前"sheet 通过此规则被识别并默认隐藏。

const HISTORICAL_PATTERN =
  /修订前|[（(]原[）)]|G\d+.*[删除移至]|（示例）|\(示例\)|示例[）)]?$/

export const G_SHEET_GROUP_RULES: GSheetGroupRule[] = [
  // 1. 索引（^底稿目录$ / ^GT_Custom$，默认隐藏）
  {
    id: 'index',
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 0,
    defaultHidden: true,
    match: (s) => /^底稿目录$|^GT_Custom$/.test(s),
  },
  // 2. 历史遗留（修订前/原/删除-移至/示例，默认隐藏）
  {
    id: 'historical',
    category: '历史遗留',
    icon: '🗄️',
    color: '#9e9e9e',
    priority: 1,
    defaultHidden: true,
    match: (s) => HISTORICAL_PATTERN.test(s),
  },
  // 3. 总控台（程序表 xxA 结尾 或 含"实质性程序"）
  {
    id: 'procedure',
    category: '总控台',
    icon: '🎯',
    color: '#1976d2',
    priority: 2,
    match: (s) => /[A-Z]\d*A$/.test(s) || /实质性程序/.test(s),
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
  // 5. 附注披露（readonly）
  {
    id: 'disclosure',
    category: '附注披露',
    icon: '📝',
    color: '#795548',
    priority: 4,
    readonly: true,
    match: (s) => /附注披露/.test(s),
  },
  // 6. 明细表 / 结存表
  {
    id: 'detail',
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 5,
    match: (s) => /明细表|结存表/.test(s),
  },
  // 7. 公允价值测试（公允价值测试 / 公允价值计量 / 第三层次）
  {
    id: 'fair_value',
    category: '公允价值测试',
    icon: '💎',
    color: '#7b1fa2',
    priority: 6,
    match: (s) => /公允价值测试|公允价值计量|第三层次/.test(s),
  },
  // 8. 减值测试（含 ECL / 信用损失）
  {
    id: 'impairment',
    category: '减值测试',
    icon: '⚠️',
    color: '#d84315',
    priority: 7,
    match: (s) => /减值|信用损失|ECL/.test(s),
  },
  // 9. 收益测算（收益测算 / 利息收入 / 投资收益）
  {
    id: 'income_calc',
    category: '收益测算',
    icon: '💰',
    color: '#00838f',
    priority: 8,
    match: (s) => /收益测算|利息收入|投资收益/.test(s),
  },
  // 10. 分类检查（业务模式 / 合同现金流 / 分类适当性 / SPPI）
  {
    id: 'classification',
    category: '分类检查',
    icon: '🔖',
    color: '#5e35b1',
    priority: 9,
    match: (s) => /业务模式|合同现金流|分类.*适当性|SPPI/.test(s),
  },
  // 11. 函证（函证 / 跟函 / 替代程序 / 差异核对 / 邮件传真 / 舞弊风险评价）
  {
    id: 'confirmation',
    category: '函证',
    icon: '✉️',
    color: '#1565c0',
    priority: 10,
    match: (s) =>
      /函证|核实被函证|跟函|差异核对|替代程序|邮件传真|舞弊风险评价/.test(s),
  },
  // 12. 调整分录
  {
    id: 'adjustment',
    category: '调整分录',
    icon: '✏️',
    color: '#3949ab',
    priority: 11,
    match: (s) => /调整分录/.test(s),
  },
  // 13. 其他程序（fallback，含监盘 / 有价证券 / 衍生工具核查 / 检查表 等）
  {
    id: 'other',
    category: '其他程序',
    icon: '📄',
    color: '#bdbdbd',
    priority: 12,
    match: () => true,
  },
]

/** Fallback 分组（与 G_SHEET_GROUP_RULES 末项一致），保留导出便于历史代码引用 */
export const FALLBACK_GROUP: GSheetCategory = {
  category: '其他程序',
  icon: '📄',
  color: '#bdbdbd',
  priority: 12,
}

/**
 * 按 G_SHEET_GROUP_RULES 顺序匹配 sheet 名，返回类目元数据。
 *
 * 规则保证：
 *   - 任意 sheet 名恰好匹配 1 类（最后一条 fallback `match: () => true`）
 *   - 优先级冲突时由 priority 升序决定（如"函证程序表G0A" → 总控台 而非 函证）
 */
export function classifyGSheet(name: string): GSheetCategory {
  for (const rule of G_SHEET_GROUP_RULES) {
    if (rule.match(name)) {
      // 剔除 id 与 match，仅返回展示元数据
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { id: _id, match: _match, ...rest } = rule
      return rest
    }
  }
  // 不会到达（fallback `match: () => true` 必然命中）
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * G 投资循环 sheet 分组 composable
 *
 * @param univerAPI       Univer Facade API ref
 * @param parsedData      workpaper.parsed_data ref（用于读取 g7_accounting_methods）
 * @param currentInvesteeName  当前选中的被投资方名称 ref
 *                              （由 G7 底稿内"当前投资"选择器驱动）
 */
export function useGInvestmentCycleSheetGroups(
  univerAPI: Ref<any>,
  parsedData?: Ref<GParsedData | null | undefined>,
  currentInvesteeName?: Ref<string | null | undefined>,
) {
  const sheets = ref<GInvestmentCycleSheetItem[]>([])
  const activeSheetId = ref<string>('')

  /** 当前生效的 G7 核算方式（响应式）；null 触发 fallback 全显 */
  const currentMethod = computed<G7AccountingMethod | null>(() =>
    resolveG7AccountingMethod(parsedData?.value, currentInvesteeName?.value),
  )

  /** 是否应过滤掉该 sheet（基于类目 defaultHidden） */
  function shouldFilterOut(name: string): boolean {
    const cls = classifyGSheet(name)
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
      const items: GInvestmentCycleSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyGSheet(name)
          const item: GInvestmentCycleSheetItem = {
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
          (s: GInvestmentCycleSheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      // 应用 G7 核算方式过滤（fallback 时为 no-op）
      sheets.value = filterByG7AccountingMethod(items, currentMethod.value)
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (sheets.value.length > 0) {
        activeSheetId.value = sheets.value[0].id
      }
    } catch (err) {
      console.warn('[useGInvestmentCycleSheetGroups] refresh failed:', err)
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
      console.warn('[useGInvestmentCycleSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<GInvestmentCycleSheetGroup[]>(() => {
    if (sheets.value.length === 0) return []
    const groupMap = new Map<string, GInvestmentCycleSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyGSheet(sheet.name)
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
    currentMethod,
    refresh,
    switchTo,
    classifyGSheet,
    filterByG7AccountingMethod,
    resolveG7AccountingMethod,
  }
}
