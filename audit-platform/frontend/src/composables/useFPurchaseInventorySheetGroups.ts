/**
 * useFPurchaseInventorySheetGroups — F 采购存货循环 sheet 分组 composable
 *
 * spec workpaper-f-purchase-inventory ADR-F5（任务 2.1）
 *
 * 痛点：F 循环 6 主底稿（F0/F1/F2/F3/F4/F5）合并后 sheet 数 90+（F2 单底稿
 *      11 文件 90 sheet 全系统最复杂），D 循环 14 类规则不能覆盖 F2 独有的
 *      "存货监盘/计价测试/合同履约成本/供应商访谈/会计政策" 等业务语义。
 * 方案：与 useUniverSheetNav 等同接口（SheetItem / SheetGroup / ScenarioFilter），
 *      定义 F 循环专属的 16 类规则 + 优先级 + 默认隐藏 / 只读字段。
 *
 * 设计参考：spec design.md ADR-F5 规则清单
 *   priority 1  : index            底稿目录 / GT_Custom / 修订说明（默认隐藏）
 *   priority 1  : control_panel    F[0-5]A / F2-21A / F2-55A / F2-61A 总控台
 *   priority 2  : verified         审定表
 *   priority 4  : impairment       跌价 / 减值 / 可变现净值（在 detail 之前以避免
 *                                  "坏账明细表" 被误归类）
 *   priority 3  : detail           明细表（非跌价类）
 *   priority 5  : analysis         分析 / 周转率 / 库龄 / 毛利
 *   priority 6  : stocktake        存货监盘 / 盘点 / 抽盘
 *   priority 7  : cutoff           截止测试
 *   priority 8  : check            检查表 / 核查表
 *   priority 9  : costing          计价测试 / 成本计算
 *   priority 10 : related_party    关联方 / 关联交易
 *   priority 11 : contract_cost    合同履约成本
 *   priority 12 : supplier_interview 供应商访谈
 *   priority 13 : note             附注披露（默认 readonly）
 *   priority 14 : adjustment       调整分录
 *   priority 15 : policy           会计政策
 *   priority 99 : historical       修订前 / （原） / G+数字-删除/移至 / 示例（默认隐藏）
 */
import { computed, ref, type Ref } from 'vue'
import type { SheetGroup, SheetItem, ScenarioFilter } from './useUniverSheetNav'

// ===== 类型定义 =====

export interface FSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  defaultHidden?: boolean
  readonly?: boolean
}

export interface FSheetPattern extends FSheetCategory {
  pattern: RegExp
}

export interface FPurchaseInventorySheetItem extends SheetItem {
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

export interface FPurchaseInventorySheetGroup extends SheetGroup {
  priority: number
}

// ===== 16 类规则（按 priority 排序） =====

export const F_SHEET_PATTERNS: FSheetPattern[] = [
  // priority 1: 索引/底稿目录/修订说明（默认隐藏）
  {
    pattern: /^底稿目录|GT[_\s]?Custom|^修订说明/i,
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 1,
    defaultHidden: true,
  },
  // priority 99: 历史遗留（修订前 / G+数字-删除/移至 / 示例 / （原））
  // 必须在 control_panel/审定表/明细表 之前，避免"修订前G1A"等被误归类
  {
    pattern: /修订前|[（(]原[）)]|G\d+.*[删除移至]|（示例）|\(示例\)|示例[）)]?$/,
    category: '历史遗留',
    icon: '🗄️',
    color: '#9e9e9e',
    priority: 99,
    defaultHidden: true,
  },
  // priority 1: 总控台（高亮显示，主入口）
  // F0A/F1A/F2A/F3A/F4A/F5A + F2-21A 监盘子总控台 + F2-55A 合同履约成本 + F2-61A IPO 应对
  {
    pattern: /F[0-5]A\b|F2-21A\b|F2-55A\b|F2-61A\b|实质性程序表F\d|函证程序表F0A/,
    category: '总控台',
    icon: '🎯',
    color: '#1976d2',
    priority: 1,
  },
  // priority 2: 审定表
  {
    pattern: /审定表|审定数/,
    category: '审定表',
    icon: '✅',
    color: '#388e3c',
    priority: 2,
  },
  // priority 4: 跌价准备 / 减值（在 detail 之前以避免"减值明细表"被误归类）
  {
    pattern: /跌价|减值|可变现净值|长库龄|呆滞|超.*保质期/,
    category: '跌价准备',
    icon: '⚠️',
    color: '#d84315',
    priority: 4,
  },
  // priority 4.5: 关联方（在 分析 之前以避免"关联采购分析表"被误归类）
  {
    pattern: /关联[方采交]|定价公允|关联交易/,
    category: '关联方',
    icon: '🔗',
    color: '#5e35b1',
    priority: 10,
  },
  // priority 6: 存货监盘（在 detail 之前以避免"盘点明细"被误归类）
  {
    pattern: /监盘|盘点|抽盘|倒轧|盘点计划|监盘小结/,
    category: '存货监盘',
    icon: '📦',
    color: '#00838f',
    priority: 6,
  },
  // priority 7: 截止测试（在 check 之前）
  {
    pattern: /截止测试|截止性|入库.*凭证.*原始|出库.*凭证.*原始/,
    category: '截止测试',
    icon: '⏱️',
    color: '#c62828',
    priority: 7,
  },
  // priority 8: 检查表 / 核查表（在 detail 之前以避免"核查表"含"...物资"被误归类为明细表）
  {
    pattern: /检查表|核查表|领用检查|采购入库检查|未入账检查|供应商融资检查|长期挂[款账]|核实.*信息|跟函|过程控制|可靠性验证|风险评价/,
    category: '检查表',
    icon: '🔍',
    color: '#455a64',
    priority: 8,
  },
  // priority 9: 计价测试（在 detail 之前以避免"成本明细"被误归类）
  {
    pattern: /计价|加权平均|先进先出|标准成本.*差异|生产成本.*[明细分配]|制造费用|直接人工|利息测算|利息计算/,
    category: '计价测试',
    icon: '💰',
    color: '#7b1fa2',
    priority: 9,
  },
  // priority 11: 合同履约成本（在 detail 之前以避免"履约成本明细"被误归类）
  {
    pattern: /合同履约成本|亏损合同/,
    category: '合同履约',
    icon: '📜',
    color: '#5d4037',
    priority: 11,
  },
  // priority 12: 供应商访谈（在 check 之前）
  {
    pattern: /供应商.*访谈|访谈记录|访谈汇总/,
    category: '供应商访谈',
    icon: '🗣️',
    color: '#6d4c41',
    priority: 12,
  },
  // priority 3: 明细表（非跌价/监盘/计价/合同/检查类）
  {
    pattern: /明细[表汇]|原材料.*[明细]|在产品|库存商品|委托加工|发出商品|低值易耗|周转材料|消耗性生物/,
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 3,
  },
  // priority 5: 分析（含周转率、库龄、毛利率、增长率、函证差异调节）
  {
    pattern: /分析|周转|产销量|成本比较|毛利率|增长率|库龄|差异调节/,
    category: '分析',
    icon: '📈',
    color: '#388e3c',
    priority: 5,
  },
  // priority 7.5: 函证 / 跟函 / 替代程序（F0 函证管理框架特有）
  {
    pattern: /函证.*结果|函证.*汇总|跟函|替代程序|函证程序|函证差异/,
    category: '函证管理',
    icon: '✉️',
    color: '#1565c0',
    priority: 7,
  },
  // priority 13: 附注披露（readonly）
  {
    pattern: /附注披露|披露信息/,
    category: '附注披露',
    icon: '📝',
    color: '#795548',
    priority: 13,
    readonly: true,
  },
  // priority 14: 调整分录
  {
    pattern: /调整分录|审计调整|重分类调整|AJE|RJE/,
    category: '调整分录',
    icon: '✏️',
    color: '#3949ab',
    priority: 14,
  },
  // priority 15: 会计政策
  {
    pattern: /会计政策|政策检查/,
    category: '会计政策',
    icon: '📚',
    color: '#00796b',
    priority: 15,
  },
]

export const FALLBACK_GROUP: FSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 50,
}

/** 按 F_SHEET_PATTERNS 顺序匹配 sheet 名，返回 F 循环类目元数据 */
export function classifyFSheet(name: string): FSheetCategory {
  for (const p of F_SHEET_PATTERNS) {
    if (p.pattern.test(name)) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { pattern: _pattern, ...rest } = p
      return rest
    }
  }
  return FALLBACK_GROUP
}

// ===== composable =====

/**
 * F 采购存货循环 sheet 分组 composable
 *
 * 接口与 useUniverSheetNav / useDSalesCycleSheetGroups 等同。
 * 规则面向 F 循环 F0~F5 6 主底稿合并后场景特化。
 */
export function useFPurchaseInventorySheetGroups(
  univerAPI: Ref<any>,
  scenarioFilter?: Ref<ScenarioFilter | null>,
) {
  const sheets = ref<FPurchaseInventorySheetItem[]>([])
  const activeSheetId = ref<string>('')

  function shouldFilterOut(name: string): boolean {
    const cls = classifyFSheet(name)
    if (cls.defaultHidden) return true
    void scenarioFilter
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
      const items: FPurchaseInventorySheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyFSheet(name)
          const item: FPurchaseInventorySheetItem = {
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
          (s: FPurchaseInventorySheetItem) => !s.hidden && !shouldFilterOut(s.name),
        )
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (items.length > 0) {
        activeSheetId.value = items[0].id
      }
    } catch (err) {
      console.warn('[useFPurchaseInventorySheetGroups] refresh failed:', err)
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
      console.warn('[useFPurchaseInventorySheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组 */
  const groups = computed<FPurchaseInventorySheetGroup[]>(() => {
    const groupMap = new Map<string, FPurchaseInventorySheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyFSheet(sheet.name)
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
    classifyFSheet,
  }
}
