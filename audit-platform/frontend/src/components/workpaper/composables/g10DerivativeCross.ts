/**
 * G10-8 衍生工具核查 ↔ G10-2 衍生负债明细 / G10-3 调整联动
 */
import { matchG10LiabilityKey, inferG10AdjudicationRowKey } from './g10AccountMatch'
import {
  aggregateG10AdjustmentAjeRjeByRow,
} from './g10AdjStorage'
import { G10_DETAIL_ROWS_KEY, commitG10AdjustmentWritebackFromRows, parseG10DetailRows } from './g10CrossHelpers'
import { G10_ACCOUNT_CODE } from './g10Constants'
import { G10_ADJ_KEY } from './g10FvCrossHelpers'
import type { G10DetailRow } from './useG10Detail'
import type { ChecklistResponse } from './useF1FormData'
import type { G10DerivativeRow } from './useG10DerivativeCheck'

export const G10_DERIVATIVE_DETAIL_LINKS_KEY = 'G10-derivative-detail-links'

export interface G10DerivativeDetailLink {
  detailRowId: string
  liabilityName: string
}

/**
 * 判定一条 G10-2 明细行是否为衍生负债。
 *
 * 🔴 **C-7 根治读错源**（spec `g-cycle-single-region-detail-lanes`）：
 * 改造前读 `row.isDerivative` 与 `row.liabilityType`，而这两列的权威来源是
 * **衍生金融工具核查表G10-8**；`明细表G10-2` 按权威模板重构后（19 列 A..S）
 * 根本没有这两列，留着就是两个真源。
 *
 * 现只按 **B 列项目名称**做形态判定（模板里唯一能表达衍生属性的受管列）。
 * 更权威的判定走 G10-8 的链接清单 `G10_DERIVATIVE_DETAIL_LINKS_KEY`
 * —— 本函数是「候选筛选」，链接清单是「已核查确认」，两者分工不同。
 */
export function isG10DerivativeDetailRow(row: Pick<G10DetailRow, 'liabilityName'>): boolean {
  return /衍生|期权|互换|期货|远期/.test(String(row.liabilityName ?? ''))
}

export function filterG10DerivativeDetailRows(rows: G10DetailRow[]): G10DetailRow[] {
  return rows.filter(isG10DerivativeDetailRow)
}

export function parseG10DerivativeDetailLinks(json: string | null | undefined): G10DerivativeDetailLink[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 由 G10-2 衍生行拼披露用的合同摘要。
 *
 * 🔴 C-7：原实现读 `hostContractDesc` / `embeddedDerivativeJudgment` 两列，
 * 它们的权威源是 G10-8（见 `isG10DerivativeDetailRow` 注释）。现只用 G10-2 的受管列
 * （B 项目名称 + P 到期日 + O 期末审定数），主合同与嵌入衍生的描述由 G10-8 自己披露。
 */
export function buildG10DerivativeContractNoteFromDetails(rows: G10DetailRow[]): string {
  if (!rows.length) return ''
  return rows.map((r) => {
    const parts = [`【${r.liabilityName}】`]
    if (r.maturityDate?.trim()) parts.push(`到期日：${r.maturityDate.trim()}`)
    if (Math.abs(r.closingAdjusted) > 0.005) {
      parts.push(`期末审定 ${r.closingAdjusted.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`)
    }
    return parts.join('；')
  }).join('\n')
}

/** 从 G10-2 读取衍生行并写入链接清单 */
export function pullG10DerivativeLinksFromDetail(
  responses: Map<string, ChecklistResponse>,
): G10DerivativeDetailLink[] {
  const details = filterG10DerivativeDetailRows(
    parseG10DetailRows(responses.get(G10_DETAIL_ROWS_KEY)?.remark),
  )
  return details.map((d) => ({ detailRowId: d.rowId, liabilityName: d.liabilityName }))
}

/**
 * 🔴 **已停用**（spec `g-cycle-single-region-detail-lanes` C-7）。
 *
 * 原实现把 G10-8 的核查结论回写进 G10-2 的 `isDerivative` / `liabilityType` /
 * `embeddedDerivativeJudgment` / `remark` 四列 —— 方向错：**衍生属性的权威来源就是
 * G10-8**，而 `明细表G10-2` 按权威模板重构后（19 列 A..S）没有这四列，
 * 回写只会造出第二个真源。与 G9 的 `pushG9FvToDetail`（G9-4→G9-2）同族错误。
 *
 * 关联关系走 G10-8 自己维护的链接清单 `G10_DERIVATIVE_DETAIL_LINKS_KEY`
 * （`pullG10DerivativeLinksFromDetail` 建候选、G10-8 侧确认），**不落 G10-2 的行**。
 *
 * 保留导出与签名以免打断调用方，**恒返 0 且不写任何 store**。
 */
export function pushG10DerivativeCheckToDetail(
  _responses: Map<string, ChecklistResponse>,
  _debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  _input: {
    links: G10DerivativeDetailLink[]
    wizardConclusion?: string
    overallConclusion?: string
    indexRef?: string
  },
): number {
  return 0
}

export interface G10DerivativeIssue {
  rowId: string
  sectionNo: string
  sectionTitle: string
  checkItem: string
  riskLevel: string
  auditConclusion: string
}

/** 识别 G10-8 推送至 G10-3 的调整行 */
export function isFromG108(row: {
  summary?: string
  remark?: string
  indexRef?: string
}): boolean {
  const indexRef = String(row.indexRef || '')
  if (indexRef === 'G10-8' || indexRef.includes('G10-8')) return true
  const summary = String(row.summary || '')
  if (/^G10-8\s*衍生不合规/.test(summary)) return true
  if (/来自 G10-8/.test(String(row.remark || ''))) return true
  return false
}

/** 不合规问卷行（排除 N/A） */
export function collectG10DerivativeNonCompliantIssues(rows: G10DerivativeRow[]): G10DerivativeIssue[] {
  return rows
    .filter((r) => r.compliance === 'non_compliant')
    .map((r) => ({
      rowId: r.rowId,
      sectionNo: r.sectionNo,
      sectionTitle: r.sectionTitle,
      checkItem: r.checkItem,
      riskLevel: r.riskLevel || '',
      auditConclusion: r.auditConclusion || '',
    }))
}

function buildDerivativeIssueSummary(issue: G10DerivativeIssue): string {
  const label = issue.checkItem?.trim() || issue.sectionTitle || '未命名检查项'
  return `G10-8 衍生不合规：${issue.sectionNo} ${label}`.trim()
}

/** 不合规项 → G10-3 备忘 AJE（金额 0，待追查补录） */
export function pushG10DerivativeIssuesToAdjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  issues: G10DerivativeIssue[],
): { pushed: number; skipped: number } {
  if (!issues.length) return { pushed: 0, skipped: 0 }

  let existing: Record<string, unknown>[] = []
  const raw = responses.get(G10_ADJ_KEY)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch { /* ignore */ }
  }

  const summaries = new Set(
    existing.map((r) => String(r.summary || '').trim()).filter(Boolean),
  )
  const toPush = issues.filter((it) => !summaries.has(buildDerivativeIssueSummary(it)))
  const skipped = issues.length - toPush.length
  if (!toPush.length) return { pushed: 0, skipped }

  const added: Record<string, unknown>[] = []
  let seqBase = existing.length
  toPush.forEach((issue, i) => {
    const summary = buildDerivativeIssueSummary(issue)
    const rowKey = inferG10AdjudicationRowKey({
      liabilityType: '衍生金融负债',
      summary,
    })
    const base = {
      date: new Date().toISOString().slice(0, 10),
      entryType: 'AJE',
      preparedBy: '',
      indexRef: 'G10-8',
      liabilityType: '衍生金融负债',
      adjudicationRowKey: rowKey,
      remark: [
        '来自 G10-8 衍生工具核查；金额待追查补录',
        issue.riskLevel ? `风险：${issue.riskLevel}` : '',
        issue.auditConclusion ? `结论：${issue.auditConclusion}` : '',
      ].filter(Boolean).join('；'),
    }
    const idSuffix = `${Date.now().toString(36)}-${i}`
    added.push({
      ...base,
      rowId: `g10dr-adj-${idSuffix}a`,
      seq: seqBase + added.length + 1,
      summary,
      accountCode: G10_ACCOUNT_CODE,
      accountName: '交易性金融负债',
      debitAmount: 0,
      creditAmount: 0,
    })
    added.push({
      ...base,
      rowId: `g10dr-adj-${idSuffix}b`,
      seq: seqBase + added.length + 1,
      summary: `${summary}（对方科目待复核）`,
      accountCode: '2501',
      accountName: '其他流动负债',
      debitAmount: 0,
      creditAmount: 0,
    })
    seqBase = existing.length + added.length
  })

  const merged = [...existing, ...added]
  debouncedSave(G10_ADJ_KEY, { remark: JSON.stringify(merged) })

  commitG10AdjustmentWritebackFromRows(responses, debouncedSave, merged as Parameters<typeof aggregateG10AdjustmentAjeRjeByRow>[0], {
    source: 'G10-8',
    offerDisclosurePull: toPush.length > 0,
  })

  return { pushed: toPush.length, skipped }
}
