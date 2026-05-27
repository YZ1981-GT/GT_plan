/**
 * useLazySheetLoader — D-1 大底稿懒加载（proposal-remaining-18 task 0.4）
 *
 * 配合后端 `GET /xlsx-to-json?sheets=active` 与 `GET /sheet/{sheet_name}` 端点：
 * - 首屏加载：仅 active sheet 完整 cellData，其余 sheet 仅元数据（cellData={}, custom._lazy=true）
 * - 切换 sheet：本 composable 检测 lazy sheet → fetch /sheet/{name} → 注入 Univer
 * - 已加载 sheet 缓存：避免重复 fetch
 *
 * 使用方式：
 *   const lazyLoader = useLazySheetLoader({ projectId, wpId })
 *   lazyLoader.markAllInitialLoaded(workbookData)  // 标记初次加载到的 sheet
 *   await lazyLoader.ensureSheetLoaded(sheetName, univerAPI)  // 切换时调用
 */
import { ref } from 'vue'
import httpApi from '@/utils/http'

export interface LazyLoaderOptions {
  projectId: () => string
  wpId: () => string
}

export interface LazyLoaderReturn {
  /** 已加载（含初始化 + 已 fetch）sheet 名集合，前端可用于显示 loading 状态 */
  loadedSheets: Set<string>
  /** 累计 fetch 次数（指标） */
  fetchCount: ReturnType<typeof ref<number>>
  /**
   * 标记初次加载结果中所有非 _lazy 的 sheet 为已加载。
   * @param workbookData /xlsx-to-json 返回的 IWorkbookData
   */
  markAllInitialLoaded(workbookData: any): void
  /** 单独标记某个 sheet 已加载（场景：保存后服务端返回新 snapshot） */
  markLoaded(sheetName: string): void
  /** 是否已加载 */
  isLoaded(sheetName: string): boolean
  /**
   * 确保某个 sheet 数据已加载。如果 sheet 仍处 _lazy 状态：
   *   1. 调 GET /sheet/{name} 获取完整数据
   *   2. 通过 univerAPI 注入到现有 sheet（cellData / mergeData / freeze）
   *   3. 标记为已加载
   * 已加载或正在 loading 时直接返回，避免重复 fetch。
   */
  ensureSheetLoaded(sheetName: string, univerAPI: any): Promise<boolean>
}

export function useLazySheetLoader(opts: LazyLoaderOptions): LazyLoaderReturn {
  const loadedSheets = new Set<string>()
  const inflight = new Map<string, Promise<boolean>>()
  const fetchCount = ref(0)

  function markLoaded(sheetName: string) {
    if (sheetName) loadedSheets.add(sheetName)
  }

  function markAllInitialLoaded(workbookData: any): void {
    const sheets = workbookData?.sheets
    if (!sheets) return
    for (const sheet of Object.values(sheets) as any[]) {
      if (!sheet?.name) continue
      // 显式 _lazy=true 表示需要按需加载，跳过标记
      if (sheet?.custom?._lazy === true) continue
      loadedSheets.add(sheet.name)
    }
  }

  function isLoaded(sheetName: string): boolean {
    return loadedSheets.has(sheetName)
  }

  async function ensureSheetLoaded(sheetName: string, univerAPI: any): Promise<boolean> {
    if (!sheetName) return false
    if (loadedSheets.has(sheetName)) return false  // 已加载，跳过
    const existing = inflight.get(sheetName)
    if (existing) return existing  // 并发去重

    const task = (async (): Promise<boolean> => {
      try {
        const sheetData = await httpApi.get(
          `/api/projects/${opts.projectId()}/workpapers/${opts.wpId()}/template-file/sheet/${encodeURIComponent(sheetName)}`,
        )
        fetchCount.value = (fetchCount.value ?? 0) + 1
        if (!sheetData) {
          loadedSheets.add(sheetName)  // 即使失败也避免反复重试
          return false
        }
        _applyToUniver(univerAPI, sheetName, sheetData)
        loadedSheets.add(sheetName)
        return true
      } catch (e: any) {
        console.warn(`[LazySheetLoader] fetch ${sheetName} failed:`, e?.message || e)
        // 不标记 loaded 也不重试（避免无限循环）；UI 可保留空白态
        return false
      } finally {
        inflight.delete(sheetName)
      }
    })()
    inflight.set(sheetName, task)
    return task
  }

  return {
    loadedSheets,
    fetchCount,
    markAllInitialLoaded,
    markLoaded,
    isLoaded,
    ensureSheetLoaded,
  }
}

/**
 * 将后端返回的单 sheet 数据注入到 Univer 现有 sheet。
 *
 * Univer Facade API 0.21+：通过 sheet.getRange().setValues() 批量写入 cellData，
 * mergeData/freeze 通过对应 API 设置（best-effort，不支持时静默跳过）。
 */
function _applyToUniver(univerAPI: any, sheetName: string, sheetData: any): void {
  if (!univerAPI || !sheetData?.cellData) return
  const wb = univerAPI?.getActiveWorkbook?.()
  if (!wb) return
  const sheet = wb.getSheetByName?.(sheetName)
  if (!sheet) {
    console.warn(`[LazySheetLoader] sheet not found in Univer: ${sheetName}`)
    return
  }

  const cellData = sheetData.cellData as Record<string, Record<string, any>>
  const rowKeys = Object.keys(cellData)
  if (!rowKeys.length) return

  // 计算 cellData 范围
  let maxR = 0
  let maxC = 0
  for (const rs of rowKeys) {
    const r = Number(rs)
    if (r > maxR) maxR = r
    const colsObj = cellData[rs] || {}
    for (const cs of Object.keys(colsObj)) {
      const c = Number(cs)
      if (c > maxC) maxC = c
    }
  }

  // 构造 Univer setValues 矩阵：[[ICellData, ...], ...]
  const matrix: any[][] = []
  for (let r = 0; r <= maxR; r++) {
    const row: any[] = []
    const rowData = cellData[String(r)] || {}
    for (let c = 0; c <= maxC; c++) {
      const cell = rowData[String(c)]
      if (!cell) {
        row.push(null)
        continue
      }
      // 仅传递 v/f/s 字段（其余忽略，Univer 会保留原 sheet 元数据）
      row.push({
        v: cell.v,
        f: cell.f,
        s: cell.s,
        custom: cell.custom,
      })
    }
    matrix.push(row)
  }

  try {
    const range = sheet.getRange?.(0, 0, maxR + 1, maxC + 1)
    range?.setValues?.(matrix)
  } catch (e: any) {
    console.warn(`[LazySheetLoader] setValues failed for ${sheetName}:`, e?.message || e)
  }

  // best-effort 应用 mergeData
  if (Array.isArray(sheetData.mergeData) && sheetData.mergeData.length) {
    try {
      for (const m of sheetData.mergeData) {
        const r = sheet.getRange?.(m.startRow, m.startColumn, m.endRow - m.startRow + 1, m.endColumn - m.startColumn + 1)
        r?.merge?.()
      }
    } catch { /* ignore */ }
  }

  // freeze (best-effort)
  if (sheetData.freeze) {
    try {
      sheet.setFreeze?.({
        startRow: sheetData.freeze.startRow,
        startColumn: sheetData.freeze.startColumn,
        xSplit: sheetData.freeze.xSplit ?? sheetData.freeze.startColumn ?? 0,
        ySplit: sheetData.freeze.ySplit ?? sheetData.freeze.startRow ?? 0,
      })
    } catch { /* ignore */ }
  }
}
