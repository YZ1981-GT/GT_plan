/**
 * 模板变体矩阵工具 composable
 *
 * 提供按 semantic_section_id 查找四版本变体映射，以及生成差异摘要的能力。
 * 对应 Requirements 8.1, 8.2, 8.3, 8.4
 */

export interface VariantInfo {
  section_id: string
  number: string
  title: string
  scope: string
  consol_sub_sections?: string[]
}

export type VariantKey = 'soe_standalone' | 'soe_consolidated' | 'listed_standalone' | 'listed_consolidated'

export interface VariantMatrixEntry {
  semantic_section_id: string
  title: string
  variants: Record<VariantKey, VariantInfo>
}

export interface VariantMatrix {
  version: string
  description: string
  matrix: VariantMatrixEntry[]
}

const VARIANT_LABELS: Record<VariantKey, string> = {
  soe_standalone: '国企单体',
  soe_consolidated: '国企合并',
  listed_standalone: '上市单体',
  listed_consolidated: '上市合并',
}

/**
 * 根据 semantic_section_id 查找四版本变体映射
 */
export function findVariants(
  semanticSectionId: string,
  matrix: VariantMatrixEntry[],
): Record<VariantKey, VariantInfo> | null {
  const entry = matrix.find((item) => item.semantic_section_id === semanticSectionId)
  return entry ? entry.variants : null
}

/**
 * 生成四版本间的差异摘要列表
 * 比较标题、编号、scope 等维度差异
 */
export function getDifferenceSummary(variants: Record<VariantKey, VariantInfo>): string[] {
  const diffs: string[] = []
  const keys = Object.keys(variants) as VariantKey[]

  // 比较标题差异
  const titles = new Set(keys.map((k) => variants[k].title))
  if (titles.size > 1) {
    const titleDetails = keys.map((k) => `${VARIANT_LABELS[k]}：${variants[k].title}`)
    diffs.push(`标题差异：${titleDetails.join('、')}`)
  }

  // 比较编号差异
  const numbers = new Set(keys.map((k) => variants[k].number))
  if (numbers.size > 1) {
    const numberDetails = keys.map((k) => `${VARIANT_LABELS[k]}=${variants[k].number}`)
    diffs.push(`编号差异：${numberDetails.join('、')}`)
  }

  // 比较 section_id 差异（国企 vs 上市）
  const soeId = variants.soe_standalone.section_id
  const listedId = variants.listed_standalone.section_id
  if (soeId !== listedId) {
    diffs.push(`国企/上市使用不同 section_id`)
  }

  // 检查合并版本是否有额外子表
  const consolKeys = keys.filter((k) => variants[k].consol_sub_sections?.length)
  if (consolKeys.length > 0) {
    const details = consolKeys.map(
      (k) => `${VARIANT_LABELS[k]} 含 ${variants[k].consol_sub_sections!.length} 个合并子表`,
    )
    diffs.push(details.join('、'))
  }

  // 比较 scope 差异
  const scopes = new Map<string, VariantKey[]>()
  for (const k of keys) {
    const scope = variants[k].scope
    if (!scopes.has(scope)) scopes.set(scope, [])
    scopes.get(scope)!.push(k)
  }
  if (scopes.size > 1) {
    const scopeDetails = [...scopes.entries()].map(
      ([scope, variantKeys]) => `${variantKeys.map((k) => VARIANT_LABELS[k]).join('/')}=${scope}`,
    )
    diffs.push(`适用范围差异：${scopeDetails.join('、')}`)
  }

  if (diffs.length === 0) {
    diffs.push('四版本结构一致，无显著差异')
  }

  return diffs
}

/**
 * 获取变体标签（中文名）
 */
export function getVariantLabel(key: VariantKey): string {
  return VARIANT_LABELS[key]
}

/**
 * Composable: 模板变体矩阵
 * 用于前端模板切换时展示对应章节和差异摘要
 */
export function useNoteTemplateVariants(matrixData: VariantMatrix) {
  const matrix = matrixData.matrix

  function lookup(semanticSectionId: string) {
    return findVariants(semanticSectionId, matrix)
  }

  function summarize(semanticSectionId: string): string[] {
    const variants = lookup(semanticSectionId)
    if (!variants) return [`未找到 ${semanticSectionId} 的变体映射`]
    return getDifferenceSummary(variants)
  }

  function allSectionIds(): string[] {
    return matrix.map((entry) => entry.semantic_section_id)
  }

  return {
    lookup,
    summarize,
    allSectionIds,
    matrix,
  }
}
