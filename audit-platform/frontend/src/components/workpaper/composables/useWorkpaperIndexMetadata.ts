/**
 * useWorkpaperIndexMetadata — 通用目录元数据层（Req 6.3, 6.5）
 *
 * 从 render-config sheets + ACNR canonical names 生成基础目录 SheetMeta[]，
 * 保持 render-config 原始 sheet 顺序不变。
 *
 * 业务特有勾稽（如 N2 税费多测算表联动、K1 凭证检查比例等）通过 IndexExtension
 * 扩展接口注入，不侵入通用层。
 *
 * 用法：
 *   const { sheetMetas, progressSummary } = useWorkpaperIndexMetadata(sheets, options)
 *   // sheetMetas: computed SheetMeta[]（保持原始 sheet 顺序）
 *   // 传给 GtBArchitectureTree 的 htmlData.navigation_rows 或其他 UI
 *
 * Design §8.3 / Correctness Property P10:
 *   对任意 render-config sheet 序列，生成的 SheetMeta[] 保留全部有效 sheet 的原始顺序。
 */
import { computed, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** render-config 返回的单个 sheet 条目（后端结构） */
export interface RenderConfigSheet {
  sheet_name?: string
  component_type?: string
  componentType?: string
  html_data?: Record<string, unknown>
  wp_code?: string
  /** ACNR addr_id（如已关联） */
  addr_id?: string
}

/** 通用目录元数据条目 */
export interface SheetMeta {
  /** 序号（1-based，按原始 render-config 顺序） */
  seq: number
  /** 完整 sheet 名称（如 "审定表J1-1"） */
  sheetName: string
  /** 编码/索引引用（如 "J1-1"），用于 GtIndexChip */
  indexRef: string
  /** 前端渲染 componentType */
  componentType: string
  /** ACNR canonical 名称（若可用） */
  canonicalName?: string
  /** ACNR addr_id（若可用） */
  addrId?: string
  /** 业务状态（由 extension 计算或默认 pending） */
  status?: 'completed' | 'in_progress' | 'pending' | 'not_applicable' | ''
  /** 是否隐藏（由 extension 决定） */
  hidden?: boolean
}

/**
 * 目录扩展接口 —— 业务特有勾稽通过此接口注入
 *
 * 例如 N2 税费多测算表的 linkage，K1 凭证检查表的 progress 等。
 * 扩展函数不影响 sheet 顺序（P10 保证），只提供状态/可见性/勾稽信息。
 */
export interface IndexExtension {
  /** 计算 sheet 的编制进度 (0~100) */
  progress?(sheet: SheetMeta, responses: Map<string, unknown>): number
  /** 业务特有勾稽状态 */
  linkage?(sheet: SheetMeta): 'matched' | 'diff' | 'none'
  /** 是否隐藏该 sheet（如不适用时） */
  hidden?(sheet: SheetMeta): boolean
}

export interface UseWorkpaperIndexMetadataOptions {
  /** ACNR catalog 索引（sheet_code → { sheet_name, addr_id, order }）*/
  catalogIndex?: Ref<Map<string, { sheet_name: string; addr_id: string; order: number }>>
  /** 业务扩展 */
  extension?: IndexExtension
  /** checklist responses Map（用于 progress 计算） */
  responses?: Ref<Map<string, unknown>>
  /** 排除的 componentType（默认排除 b-index / skip） */
  excludeTypes?: string[]
}

// ─── 常量 ─────────────────────────────────────────────────────────────────────

/** 默认排除的 componentType（目录本身 + skip） */
const DEFAULT_EXCLUDE_TYPES = ['b-index', 'skip']

/** 从 sheet_name 提取编码的正则（尾部匹配，如 "审定表J1-1" → "J1-1"） */
const RE_INDEX_REF = /([A-Z]\d+[A-Z]?(?:-\d+)*)\s*$/

// ─── 核心纯函数（可单独测试/PBT） ─────────────────────────────────────────────

/**
 * 从 sheet_name 提取索引编码。
 * 优先尾部匹配（如 "审定表J1-1" → "J1-1"），
 * 回退头部匹配（如 "J1A 程序表" → "J1A"）。
 */
export function extractIndexRef(sheetName: string): string {
  if (!sheetName) return ''
  const tailMatch = sheetName.match(RE_INDEX_REF)
  if (tailMatch) return tailMatch[1]
  const headMatch = sheetName.match(/^([A-Z]\d+[A-Z]?(?:-\d+)?)/)
  if (headMatch) return headMatch[1]
  return ''
}

/**
 * 判断 sheet 是否为有效目录条目（非排除类型、非空名称）
 */
export function isValidIndexSheet(
  sheet: RenderConfigSheet,
  excludeTypes: string[],
): boolean {
  const ct = sheet.component_type ?? sheet.componentType ?? ''
  if (excludeTypes.includes(ct)) return false
  const name = sheet.sheet_name ?? ''
  if (!name.trim()) return false
  return true
}

/**
 * 纯函数：从 render-config sheets 生成 SheetMeta[]。
 *
 * **核心不变量 (P10)**：输出的 SheetMeta[] 保持输入 sheets 中全部有效条目的原始顺序。
 * 即：对任意 i < j，若 sheets[i] 和 sheets[j] 都是有效条目，
 * 则在输出中 meta(i) 出现在 meta(j) 之前。
 */
export function buildSheetMetas(
  sheets: RenderConfigSheet[],
  options: {
    catalogIndex?: Map<string, { sheet_name: string; addr_id: string; order: number }>
    excludeTypes?: string[]
  } = {},
): SheetMeta[] {
  const excludeTypes = options.excludeTypes ?? DEFAULT_EXCLUDE_TYPES
  const catalog = options.catalogIndex

  let seq = 0
  const result: SheetMeta[] = []

  for (const sheet of sheets) {
    if (!isValidIndexSheet(sheet, excludeTypes)) continue
    seq++
    const sheetName = sheet.sheet_name ?? ''
    const indexRef = extractIndexRef(sheetName)
    const componentType = sheet.component_type ?? sheet.componentType ?? ''

    // 从 ACNR catalog 取 canonical 名称和 addr_id
    let canonicalName: string | undefined
    let addrId: string | undefined
    if (catalog && indexRef) {
      const entry = catalog.get(indexRef)
      if (entry) {
        canonicalName = entry.sheet_name
        addrId = entry.addr_id
      }
    }
    // 也接受 sheet 自身的 addr_id
    if (!addrId && sheet.addr_id) {
      addrId = sheet.addr_id
    }

    result.push({
      seq,
      sheetName,
      indexRef,
      componentType,
      canonicalName,
      addrId,
      status: '',
      hidden: false,
    })
  }

  return result
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * 通用目录元数据 composable。
 *
 * @param sheets - render-config 返回的 sheets 数组（响应式）
 * @param options - ACNR catalog / extension / responses
 */
export function useWorkpaperIndexMetadata(
  sheets: Ref<RenderConfigSheet[]>,
  options: UseWorkpaperIndexMetadataOptions = {},
) {
  const { catalogIndex, extension, responses, excludeTypes } = options
  const excludes = excludeTypes ?? DEFAULT_EXCLUDE_TYPES

  /** 基础 SheetMeta[]（保持原始顺序） */
  const sheetMetas = computed<SheetMeta[]>(() => {
    const baseMetas = buildSheetMetas(sheets.value, {
      catalogIndex: catalogIndex?.value,
      excludeTypes: excludes,
    })

    // 应用 extension
    if (!extension) return baseMetas

    return baseMetas.map((meta) => {
      const hidden = extension.hidden?.(meta) ?? false
      return { ...meta, hidden }
    })
  })

  /** 可见的 SheetMeta（排除 hidden） */
  const visibleMetas = computed(() => sheetMetas.value.filter((m) => !m.hidden))

  /** 编制进度汇总 */
  const progressSummary = computed(() => {
    const visible = visibleMetas.value
    if (!extension?.progress || !responses?.value) {
      return { completed: 0, total: visible.length, percent: 0 }
    }
    const respMap = responses.value
    let completed = 0
    for (const meta of visible) {
      const pct = extension.progress(meta, respMap)
      if (pct >= 100) completed++
    }
    const total = visible.length
    const percent = total === 0 ? 0 : Math.round((completed / total) * 100)
    return { completed, total, percent }
  })

  /**
   * 生成 GtBArchitectureTree 兼容的 htmlData.navigation_rows。
   * 保留 sheet 原始顺序，映射字段对齐 GtBArchitectureTree 的 allNodes 解析。
   */
  const architectureHtmlData = computed(() => ({
    navigation_rows: visibleMetas.value.map((meta) => ({
      seq: meta.seq,
      content: meta.sheetName,
      sheet_name: meta.sheetName,
      index_ref: meta.indexRef,
      component_type: meta.componentType,
      status: meta.status || '',
    })),
  }))

  return {
    /** 全部 SheetMeta（含 hidden） */
    sheetMetas,
    /** 可见 SheetMeta */
    visibleMetas,
    /** 进度汇总 { completed, total, percent } */
    progressSummary,
    /** 兼容 GtBArchitectureTree 的 htmlData */
    architectureHtmlData,
  }
}
