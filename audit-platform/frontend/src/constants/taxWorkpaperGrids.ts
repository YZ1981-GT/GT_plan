/**
 * 税审底稿样表（Univer 工作表数据）—— 类型 + 按需加载。
 *
 * 数据在同名目录 `taxWorkpaperGrids/<编号>.json`，每张底稿一个文件，
 * 🔴 生成文件，勿手改：`python backend/scripts/gen/gen_tax_workpaper_grids.py`
 *    （来源工作簿与转写口径见脚本文件头：跨表公式置空、本表公式保留）。
 * 全部样表合计约 2 MB，按编号懒加载，打开哪张取哪张，不进主包。
 * 消费方：`components/workpaper/TaxWorkpaperGrid.vue`。
 */
export interface TaxWorkpaperGridSheet {
  /** 页签名 */
  name: string
  rowCount: number
  columnCount: number
  defaultRowHeight: number
  cellData: Record<number, Record<number, { v?: string | number; f?: string; s?: string }>>
  mergeData: { startRow: number; endRow: number; startColumn: number; endColumn: number }[]
  rowData: Record<number, { h?: number; hd?: number }>
  columnData: Record<number, { w?: number; hd?: number }>
}

export interface TaxWorkpaperGridData {
  /** 样式表（Univer IStyleData，按 id 被单元格的 `s` 引用） */
  styles: Record<string, Record<string, unknown>>
  sheets: TaxWorkpaperGridSheet[]
}

const LOADERS = import.meta.glob<TaxWorkpaperGridData>('./taxWorkpaperGrids/*.json', { import: 'default' })

/** 编号 → 加载函数（键是文件名去掉扩展名，即索引编号） */
const BY_CODE: Record<string, () => Promise<TaxWorkpaperGridData>> = Object.fromEntries(
  Object.entries(LOADERS).map(([path, load]) => [path.slice(path.lastIndexOf('/') + 1, -'.json'.length), load]),
)

/** 该编号是否有样表 */
export function hasTaxWorkpaperGrid(code: string): boolean {
  return code in BY_CODE
}

/**
 * 纳税申报表样表（全部申报表一个工作簿，约 360 KB，同一生成脚本产出）。
 * 用 glob 而不是 `import()` JSON：后者让 TS 把整份 JSON 推成字面量类型，既慢又与上面的类型不兼容。
 */
const RETURN_LOADER = import.meta.glob<TaxWorkpaperGridData>('./taxReturnGrid.json', { import: 'default' })

export async function loadTaxReturnGrid(): Promise<TaxWorkpaperGridData | null> {
  const load = Object.values(RETURN_LOADER)[0]
  return load ? load() : null
}

/** 加载样表；没有样表返回 null */
export async function loadTaxWorkpaperGrid(code: string): Promise<TaxWorkpaperGridData | null> {
  const load = BY_CODE[code]
  return load ? load() : null
}
