/**
 * usePrefillMarkers — 预填充视觉标记 composable
 *
 * 从 IWorkbookData 的 cellData 中提取含 custom.prefill_source 的 cell，
 * 提供 tooltip / formula bar / color 映射等辅助函数。
 *
 * Foundation Sprint 1 Task 1.5
 */

import { ref, computed, type Ref } from 'vue'

// ── 颜色映射（与 gt-tokens.css 对齐） ──
export const SOURCE_COLOR_MAP: Record<string, string> = {
  TB: '#E3F2FD',
  TB_SUM: '#E3F2FD',
  TB_AUX: '#E3F2FD',
  AJE: '#E8F5E9',
  ADJ: '#E8F5E9',
  PREV: '#F3E5F5',
  WP: '#E0F7FA',
  ERROR: '#FF5149',
}

// 来源类型中文标签
const SOURCE_LABELS: Record<string, string> = {
  TB: '试算平衡表',
  TB_SUM: '试算平衡表（汇总）',
  TB_AUX: '辅助余额表',
  AJE: '审计调整分录',
  ADJ: '审计调整分录',
  PREV: '上年数据',
  WP: '跨底稿引用',
  ERROR: '取数失败',
}

export interface PrefillInfo {
  source: string
  formula: string
  error?: string
  bgColor: string
}

export interface PrefillMapping {
  cell_ref: string
  formula: string
  formula_type: string
  bg_color: string
}

/**
 * 从 workbook JSON 数据中提取预填充标记信息
 */
export function usePrefillMarkers(workbookData?: Ref<any>) {
  // 存储从 sheet.custom.prefill_mappings 提取的映射
  const prefillMap = ref<Map<string, PrefillInfo>>(new Map())

  /**
   * 从 workbook sheets 数据中加载 prefill 映射
   */
  function loadFromWorkbook(sheets: Record<string, any>) {
    const map = new Map<string, PrefillInfo>()
    for (const [sheetId, sheetObj] of Object.entries(sheets)) {
      const sheetName = (sheetObj as any)?.name || sheetId
      const mappings: PrefillMapping[] = (sheetObj as any)?.custom?.prefill_mappings || []
      for (const m of mappings) {
        const key = `${sheetName}!${m.cell_ref}`
        map.set(key, {
          source: m.formula_type,
          formula: m.formula,
          bgColor: m.bg_color || SOURCE_COLOR_MAP[m.formula_type] || '#E3F2FD',
        })
      }

      // Also extract from cellData[row][col].custom.prefill_source
      const cellData = (sheetObj as any)?.cellData
      if (cellData) {
        for (const [rowStr, cols] of Object.entries(cellData)) {
          for (const [colStr, cellObj] of Object.entries(cols as Record<string, any>)) {
            const custom = (cellObj as any)?.custom
            if (custom?.prefill_source) {
              const cellRef = _colToLetter(parseInt(colStr)) + (parseInt(rowStr) + 1)
              const key = `${sheetName}!${cellRef}`
              if (!map.has(key)) {
                map.set(key, {
                  source: custom.prefill_source,
                  formula: custom.prefill_formula || '',
                  error: custom.prefill_error,
                  bgColor: SOURCE_COLOR_MAP[custom.prefill_source] || '#E3F2FD',
                })
              }
            }
          }
        }
      }
    }
    prefillMap.value = map
  }

  /**
   * 获取指定 cell 的预填充信息
   */
  function getPrefillInfo(sheetName: string, cellRef: string): PrefillInfo | null {
    return prefillMap.value.get(`${sheetName}!${cellRef}`) || null
  }

  /**
   * 获取 hover tooltip 文本
   */
  function getTooltipText(sheetName: string, cellRef: string): string {
    const info = getPrefillInfo(sheetName, cellRef)
    if (!info) return ''
    if (info.source === 'ERROR') {
      return `❌ 取数失败: ${info.error || '未知错误'}`
    }
    const label = SOURCE_LABELS[info.source] || info.source
    return `📊 来源: ${label}\n公式: ${info.formula}`
  }

  /**
   * 获取公式栏显示文本
   */
  function getFormulaBarText(sheetName: string, cellRef: string): string {
    const info = getPrefillInfo(sheetName, cellRef)
    if (!info) return ''
    return info.formula || `[${SOURCE_LABELS[info.source] || info.source}]`
  }

  /**
   * 判断 cell 是否有预填充标记
   */
  function hasPrefill(sheetName: string, cellRef: string): boolean {
    return prefillMap.value.has(`${sheetName}!${cellRef}`)
  }

  const totalPrefillCells = computed(() => prefillMap.value.size)

  return {
    prefillMap,
    loadFromWorkbook,
    getPrefillInfo,
    getTooltipText,
    getFormulaBarText,
    hasPrefill,
    totalPrefillCells,
    SOURCE_COLOR_MAP,
  }
}

// ── 辅助函数 ──

function _colToLetter(col: number): string {
  let result = ''
  let c = col
  while (c >= 0) {
    result = String.fromCharCode(65 + (c % 26)) + result
    c = Math.floor(c / 26) - 1
  }
  return result
}
