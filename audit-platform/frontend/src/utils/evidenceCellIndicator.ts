/**
 * evidenceCellIndicator — 单元格📎图标渲染 + hover 预览
 *
 * Sprint 6 Task 6.5:
 * 提供工具函数，用于在 Univer 单元格右上角渲染📎图标，
 * 以及 hover 时展示该单元格关联的证据列表。
 *
 * 注意：完整的 Univer 自定义渲染需要 @univerjs/engine-render 的
 * ICellCustomRender 接口。当前提供逻辑层工具函数，
 * 视觉层集成待 Univer 插件体系稳定后实施。
 */

export interface CellEvidenceInfo {
  cellRef: string
  count: number
  types: string[]
  latestAt: string | null
}

/**
 * 从证据链接列表中提取每个单元格的证据摘要信息
 * 用于批量判断哪些单元格需要显示📎图标
 */
export function buildCellEvidenceMap(
  links: Array<{
    cell_ref: string | null
    evidence_type: string | null
    created_at: string | null
  }>
): Map<string, CellEvidenceInfo> {
  const map = new Map<string, CellEvidenceInfo>()

  for (const link of links) {
    if (!link.cell_ref) continue
    const existing = map.get(link.cell_ref)
    if (existing) {
      existing.count++
      if (link.evidence_type && !existing.types.includes(link.evidence_type)) {
        existing.types.push(link.evidence_type)
      }
      if (link.created_at && (!existing.latestAt || link.created_at > existing.latestAt)) {
        existing.latestAt = link.created_at
      }
    } else {
      map.set(link.cell_ref, {
        cellRef: link.cell_ref,
        count: 1,
        types: link.evidence_type ? [link.evidence_type] : [],
        latestAt: link.created_at,
      })
    }
  }

  return map
}

/**
 * 判断单元格是否应显示📎图标
 */
export function shouldShowIndicator(
  cellRef: string,
  evidenceMap: Map<string, CellEvidenceInfo>
): boolean {
  return evidenceMap.has(cellRef)
}

/**
 * 获取 hover 预览所需的摘要文本
 */
export function getHoverText(
  cellRef: string,
  evidenceMap: Map<string, CellEvidenceInfo>
): string {
  const info = evidenceMap.get(cellRef)
  if (!info) return ''
  const typeStr = info.types.length > 0 ? info.types.join('、') : '未分类'
  return `📎 ${info.count} 个附件（${typeStr}）`
}

/**
 * 证据类型中文标签映射
 */
export const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  voucher: '原始凭证',
  contract: '合同',
  statement: '对账单',
  confirmation: '函证',
  other: '其他',
}
