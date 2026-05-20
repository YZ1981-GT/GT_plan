/**
 * useDSalesCycleSheetGroups — D 销售循环 sheet 分组 composable
 *
 * spec workpaper-d-sales-cycle ADR D5（任务 2.5）
 *
 * 痛点：D 循环 D0~D7 共 8 主底稿合并后 sheet 数 40+，致同模板默认 sheet bar
 *      横向滚动名称被截断；E 循环 useUniverSheetNav 的 15 类规则面向通用底稿，
 *      不能精确反映 D 循环"总控台/审定/明细/坏账/分析/截止/检查/关联方/监盘/
 *      访谈/附注/调整/历史"等业务语义。
 * 方案：与 useUniverSheetNav 等同接口（SheetItem / SheetGroup / ScenarioFilter），
 *      但定义 D 循环专属的 14 类规则 + 优先级 + 默认隐藏 / 只读字段。
 *
 * 用法：
 *   const dNav = useDSalesCycleSheetGroups(univerAPI, scenarioFilter)
 *   await dNav.refresh()
 *   dNav.groups.value         // 按 priority 升序排列的 DSalesCycleSheetGroup[]
 *   dNav.activeSheetId.value
 *   dNav.switchTo(sheetId)
 *
 * 设计参考：design.md ADR D5 规则清单
 *   priority 1  : index            底稿目录 / GT_Custom（默认隐藏）
 *   priority 1  : control_panel    D[0-7]A 总控台 / D4-22A IPO 总控台（高亮主入口）
 *   priority 2  : verified         审定表
 *   priority 3  : detail           明细表（非坏账）
 *   priority 4  : bad_debt         坏账 / 减值 / ECL
 *   priority 5  : analysis         分析 / 毛利 / 增长率 / 集中度
 *   priority 6  : cutoff           截止测试
 *   priority 7  : check            检查表
 *   priority 8  : related_party    关联方
 *   priority 9  : monitor          监盘
 *   priority 10 : interview        访谈
 *   priority 11 : note             附注披露（默认 readonly）
 *   priority 12 : adjustment       调整分录
 *   priority 99 : historical       修订前 / （原）（默认隐藏）
 */
import { ref, computed, type Ref } from 'vue'
import type { SheetItem, SheetGroup, ScenarioFilter } from './useUniverSheetNav'

// ===== 类型定义 =====

/** D 循环 sheet 类目元数据（不含 pattern，便于运行时返回） */
export interface DSheetCategory {
  category: string
  icon: string
  color: string
  priority: number
  /** 是否默认隐藏（如历史遗留 sheet 和底稿目录） */
  defaultHidden?: boolean
  /** 是否只读（如附注披露） */
  readonly?: boolean
}

/** 名称匹配规则（仅供分类内部使用） */
export interface DSheetPattern extends DSheetCategory {
  pattern: RegExp
}

/** 扩展 useUniverSheetNav.SheetItem，附带 D 循环特有字段 */
export interface DSalesCycleSheetItem extends SheetItem {
  priority: number
  defaultHidden: boolean
  readonly: boolean
}

/** 扩展 useUniverSheetNav.SheetGroup，附带 priority 用于排序 */
export interface DSalesCycleSheetGroup extends SheetGroup {
  priority: number
}

// ===== 14 类规则（按 priority 排序） =====

export const D_SHEET_PATTERNS: DSheetPattern[] = [
  // priority 1: 索引/底稿目录（默认隐藏，用户可手动 toggle）
  {
    pattern: /^底稿目录|GT[_\s]?Custom/i,
    category: '索引',
    icon: '📋',
    color: '#9e9e9e',
    priority: 1,
    defaultHidden: true,
  },
  // priority 99: 历史遗留（修订前 / （原），默认隐藏）
  // 注意：迭代顺序需在 control_panel 之前，否则"修订前D4A"会被误判为总控台
  // pattern 同时兼容裸"修订前"前缀（如"修订前D4A"）与括号形式"（修订前）"
  {
    pattern: /修订前|[（(]原[）)]/,
    category: '历史遗留',
    icon: '🗄️',
    color: '#9e9e9e',
    priority: 99,
    defaultHidden: true,
  },
  // priority 1: 总控台（高亮显示，主入口）
  {
    pattern: /D[0-7]A\b|D4-22A\b|审计程序表D[0-7]A|IPO\s*应对总控台/,
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
  // priority 4: 坏账 / 减值 / ECL
  // 注意：迭代顺序需在"明细表"之前，否则"坏账明细表D2-3"会被先匹配为明细表
  // （因 detail 的负向预查仅检查 "明细表" 之后的部分，无法识别 "坏账明细表" 这种前缀形式）
  {
    pattern: /坏账|减值|损失|拨备|ECL|预期信用损失/,
    category: '坏账与减值',
    icon: '⚠️',
    color: '#d84315',
    priority: 4,
  },
  // priority 3: 明细表（非坏账类）
  {
    pattern: /明细表(?!.*(坏账|减值|损失|准备))|按客户|按产品|按区域/,
    category: '明细表',
    icon: '📑',
    color: '#f57c00',
    priority: 3,
  },
  // priority 5: 分析（含毛利率、增长率、集中度）
  {
    pattern: /分析|毛利率|增长率|集中度|趋势|比率/,
    category: '分析',
    icon: '📈',
    color: '#7b1fa2',
    priority: 5,
  },
  // priority 6: 截止测试
  {
    pattern: /截止|跨期|cutoff/i,
    category: '截止测试',
    icon: '⏱️',
    color: '#c62828',
    priority: 6,
  },
  // priority 7: 检查表
  {
    pattern: /检查表|核对表|检查记录/,
    category: '检查表',
    icon: '🔍',
    color: '#455a64',
    priority: 7,
  },
  // priority 8: 关联方
  {
    pattern: /关联方|关联交易/,
    category: '关联方',
    icon: '🔗',
    color: '#5e35b1',
    priority: 8,
  },
  // priority 9: 监盘
  {
    pattern: /监盘|盘点(?!.*现金)/,
    category: '监盘',
    icon: '👁️',
    color: '#00838f',
    priority: 9,
  },
  // priority 10: 访谈
  {
    pattern: /访谈|管理层询问|客户询问/,
    category: '访谈',
    icon: '🗣️',
    color: '#6d4c41',
    priority: 10,
  },
  // priority 11: 附注披露（只读）
  {
    pattern: /附注披露|披露信息|附注/,
    category: '附注披露',
    icon: '📝',
    color: '#795548',
    priority: 11,
    readonly: true,
  },
  // priority 12: 调整分录
  {
    pattern: /调整分录|审计调整|重分类调整|AJE|RJE/,
    category: '调整分录',
    icon: '✏️',
    color: '#3949ab',
    priority: 12,
  },
]

export const FALLBACK_GROUP: DSheetCategory = {
  category: '其他',
  icon: '📄',
  color: '#bdbdbd',
  priority: 50,
}

/** 按 D_SHEET_PATTERNS 顺序匹配 sheet 名，返回 D 循环类目元数据 */
export function classifyDSheet(name: string): DSheetCategory {
  for (const p of D_SHEET_PATTERNS) {
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
 * D 销售循环 sheet 分组 composable
 *
 * 接口与 useUniverSheetNav 等同（SheetItem / SheetGroup / ScenarioFilter 复用），
 * 规则面向 D 循环 D0~D7 8 主底稿合并后场景特化。
 *
 * @param univerAPI Univer Facade API ref
 * @param scenarioFilter 场景过滤（与 E1 spec 一致；当前 D 循环 scenario 过滤主要在
 *                       chain_orchestrator 文件级裁剪，此处仅传入便于未来扩展）
 */
export function useDSalesCycleSheetGroups(
  univerAPI: Ref<any>,
  scenarioFilter?: Ref<ScenarioFilter | null>,
) {
  const sheets = ref<DSalesCycleSheetItem[]>([])
  const activeSheetId = ref<string>('')

  /** 是否应该过滤掉该 sheet（基于类目 defaultHidden） */
  function shouldFilterOut(name: string): boolean {
    const cls = classifyDSheet(name)
    if (cls.defaultHidden) return true
    // 预留 scenarioFilter 钩子（future hook，目前主要在后端裁剪）
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
      const items: DSalesCycleSheetItem[] = allSheets
        .map((s: any, idx: number) => {
          const id = s.getSheetId?.() || s.getId?.() || `sheet${idx}`
          const name = s.getSheetName?.() || s.getName?.() || `Sheet${idx + 1}`
          const hidden = s.isSheetHidden?.() === true
          const cls = classifyDSheet(name)
          const item: DSalesCycleSheetItem = {
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
        .filter((s: DSalesCycleSheetItem) => !s.hidden && !shouldFilterOut(s.name))
      sheets.value = items
      if (active) {
        activeSheetId.value = active.getSheetId?.() || active.getId?.() || ''
      } else if (items.length > 0) {
        activeSheetId.value = items[0].id
      }
    } catch (err) {
      console.warn('[useDSalesCycleSheetGroups] refresh failed:', err)
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
      console.warn('[useDSalesCycleSheetGroups] switchTo failed:', err)
    }
  }

  /** 按 priority 升序排列的分组（1 = 索引/总控台最先；99 = 历史遗留最后） */
  const groups = computed<DSalesCycleSheetGroup[]>(() => {
    const groupMap = new Map<string, DSalesCycleSheetGroup>()
    for (const sheet of sheets.value) {
      const cls = classifyDSheet(sheet.name)
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
    classifyDSheet,
  }
}
