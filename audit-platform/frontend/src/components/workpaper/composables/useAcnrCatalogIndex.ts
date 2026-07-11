/**
 * useAcnrCatalogIndex — Bundle 目录 Tab 的 ACNR catalog 名称索引（Req 18.1 / 18.7）
 *
 * bundle 的目录 Tab（`D2TabIndex`/`D4TabIndex` 及各循环 `*TabIndex`）原本把
 * `sheet_code → sheet_name`（索引坐标名）硬编码为字面量数组，存在与 ACNR catalog
 * 漂移的风险。本 helper 从 ACNR catalog（`useAcnr().listSheets(cycle)`）派生名称/
 * 顺序真源，供 TabIndex 合并本地 routing/applicable/完成检测（后者仍为本地逻辑）。
 *
 * 降级（Req 18.7）：catalog 空/失败 → 返回空 Map，调用方回退现有硬编码 rows，
 * 保证目录不空白、无回归。
 *
 * 用法：
 *   const { loading, catalogIndex, loadCatalogIndex } = useAcnrCatalogIndex()
 *   const idx = await loadCatalogIndex('D')   // Map<sheet_code, CatalogIndexEntry>
 *   const name = idx.get('D2-2')?.sheet_name  // 空则调用方用本地名兜底
 *
 * Requirements: 18.1, 18.7
 */
import { ref, shallowRef } from 'vue'
import { useAcnr } from '@/services/acnr/useAcnr'

/** catalog 索引条目：目录 Tab 需要的名称/坐标/顺序真源 */
export interface CatalogIndexEntry {
  sheet_name: string
  addr_id: string
  order: number
}

export function useAcnrCatalogIndex() {
  const { listSheets } = useAcnr()

  const loading = ref(false)
  /** 最近一次加载的索引（shallowRef：Map 引用整体替换即可触发更新） */
  const catalogIndex = shallowRef<Map<string, CatalogIndexEntry>>(new Map())

  /**
   * 加载某循环的 catalog 索引 → `Map<sheet_code, CatalogIndexEntry>`。
   *
   * - `order` 优先取 `import_export.import_order`，缺失则用条目在列表中的位置索引。
   * - catalog 空/失败 → 返回空 Map（调用方回退硬编码 rows，Req 18.7）。
   *
   * @param cycle - 循环码（如 'D'）；不传则加载所有循环
   */
  async function loadCatalogIndex(
    cycle?: string,
  ): Promise<Map<string, CatalogIndexEntry>> {
    loading.value = true
    const map = new Map<string, CatalogIndexEntry>()
    try {
      const entries = await listSheets(cycle)
      entries.forEach((entry, position) => {
        if (!entry?.sheet_code) return
        const order =
          typeof entry.import_export?.import_order === 'number'
            ? entry.import_export.import_order
            : position
        map.set(entry.sheet_code, {
          sheet_name: entry.sheet_name || entry.sheet_code,
          addr_id: entry.addr_id,
          order,
        })
      })
    } catch (e) {
      // 降级：catalog 不可用 → 返回空 Map，调用方回退硬编码（Req 18.7）
      console.warn('[useAcnrCatalogIndex] loadCatalogIndex 失败，回退硬编码', e)
      map.clear()
    } finally {
      loading.value = false
    }
    catalogIndex.value = map
    return map
  }

  return {
    loading,
    catalogIndex,
    loadCatalogIndex,
  }
}
