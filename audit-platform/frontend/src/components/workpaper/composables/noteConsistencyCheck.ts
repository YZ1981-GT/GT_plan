/**
 * noteConsistencyCheck — 附注一致性校对纯函数（共享）
 *
 * 披露表同步到附注后，只读比对附注现存合计行 vs 本页合计，
 * 以发现"同步了但附注侧残留旧行致合计不一致"的差异。
 */
import { ElMessage } from 'element-plus'
import { getDisclosureNoteDetail } from '@/services/auditPlatformApi'

/**
 * 从附注详情的 table_data 中取第一个合计行的第一个非零数值。
 * 多表附注取 _tables 优先，单表退化取顶层 rows。
 */
export function pickNoteTotal(detail: any): number | null {
  const td = detail?.table_data
  const tables: any[] = Array.isArray(td?._tables) ? td._tables : []
  const candidates = tables.length > 0
    ? tables
    : (Array.isArray(td?.rows) ? [{ rows: td.rows }] : [])
  for (const t of candidates) {
    const rows: any[] = Array.isArray(t?.rows) ? t.rows : []
    const totalRow = rows.find((r: any) => r?.is_total || String(r?.label ?? '').trim() === '合计')
    if (!totalRow) continue
    const values: any[] = Array.isArray(totalRow.values) ? totalRow.values : []
    for (const v of values) {
      const n = Number(v)
      if (Number.isFinite(n) && n !== 0) return n
    }
  }
  return null
}

export interface NoteCheckResult {
  status: 'ok' | 'diff' | 'missing' | 'error'
  message: string
}

/**
 * 静默校对附注合计 vs 本页合计。
 * @param projectId - 项目 ID
 * @param year - 审计年度
 * @param noteSection - 附注章节号（如 五、4）
 * @param pageTotal - 本页期末合计（由各组件提供）
 * @param silent - true=仅返回结果不弹消息；false=弹 ElMessage
 */
export async function checkNoteConsistencyGeneric(
  projectId: string,
  year: number,
  noteSection: string,
  pageTotal: number,
  silent = true,
): Promise<NoteCheckResult> {
  try {
    const detail = await getDisclosureNoteDetail(projectId, year, noteSection)
    const noteTotal = pickNoteTotal(detail)
    if (noteTotal === null) {
      const r: NoteCheckResult = {
        status: 'missing',
        message: `附注「${noteSection}」暂无可比对的合计行（尚未同步或附注为空）`,
      }
      if (!silent) ElMessage.warning(r.message)
      return r
    }
    if (Math.abs(noteTotal - pageTotal) <= 0.01) {
      const r: NoteCheckResult = { status: 'ok', message: '附注现存期末合计与本页一致' }
      if (!silent) ElMessage.success(r.message)
      return r
    }
    const r: NoteCheckResult = {
      status: 'diff',
      message: `附注现存合计 ${noteTotal} 与本页期末合计 ${pageTotal} 不一致（差异 ${(noteTotal - pageTotal).toFixed(2)}）`,
    }
    if (!silent) ElMessage.warning(r.message)
    return r
  } catch {
    const r: NoteCheckResult = { status: 'error', message: '读取附注数据失败（附注可能尚未生成）' }
    if (!silent) ElMessage.warning(r.message)
    return r
  }
}
