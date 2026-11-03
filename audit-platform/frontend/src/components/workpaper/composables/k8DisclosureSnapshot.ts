/**
 * K8 销售费用披露表：表单状态（读已保存行 / 按 K8-1 审定表建行 / 自动取数）与同步快照
 * （底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `K8TabDisclosureListed` / `K8TabDisclosureSoe` 原先在组件里内联这几步；抽成本模块的纯函数后 Tab（onMounted / 同步按钮）
 * 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。Tab 自动取数后会保存披露行（写底稿）—— 保存与提示留在 Tab，
 * 离屏只改内存里的行。行身份由调用方经 `K8RowIdentity` 传入（Tab：值化身份工厂；载荷不含身份）。
 */
import type { K8DisclosureVariant } from './k8NoteSectionMap'

/** 披露行（`remark` 说明列只有上市版有，不进附注） */
export interface K8DisclosureFormRow {
  id: string
  project: string
  currentAmount: number
  priorAmount: number
  remark?: string
  isTotal?: boolean
}

export interface K8DisclosureFormState {
  rows: K8DisclosureFormRow[]
  narrativeText: string
  /** 行是按 K8-1 审定表项目建的（Tab 显示「已自动取数」提示） */
  hasAutoData: boolean
}

/** 行身份：默认行（上市 `row` / 国企 `soe`）与按 K8-1 建的行（`k81`）的身份前缀 */
export interface K8RowIdentity {
  newRow: (kind: 'row' | 'soe' | 'k81') => string
}

/** 离屏同步：载荷不含行身份 */
export const K8_HEADLESS_ROW_IDENTITY: K8RowIdentity = { newRow: () => '' }

/** 底稿回复（只读 `remark`，与 Tab / 离屏框架两种来源同口径） */
export type K8DisclosureResponses = ReadonlyMap<string, { remark?: string | null } | undefined>

/** K8-1 审定表按费用项目的审定数（审定表 `_persistAuditedByItem` 写） */
export type K81AuditedMap = Record<string, { audited?: number; prior?: number }>

const ITEM = {
  listed: { rows: 'K8-disclosure-listed-rows', narrative: 'K8-disclosure-listed-narrative' },
  soe: { rows: 'K8-disclosure-soe-rows', narrative: 'K8-disclosure-soe-narrative' },
} as const satisfies Record<K8DisclosureVariant, { rows: string; narrative: string }>
const AUDITED_BY_ITEM = 'K8-1-audited-by-item'

/** 默认费用性质清单（上市公司 / 国企简化版） */
const DEFAULT_PROJECTS: Record<K8DisclosureVariant, readonly string[]> = {
  listed: [
    '职工薪酬', '差旅费', '业务招待费', '广告宣传费', '运输费',
    '折旧费', '摊销费', '办公费', '通讯费', '物料消耗',
    '租赁费', '装卸费', '保险费', '修理费', '低值易耗品摊销',
    '包装费', '展览费', '会议费', '佣金及手续费', '售后服务费',
    '质量检验费', '样品费', '水电费', '差旅交通费', '仓储费',
    '劳动保护费', '代理费', '销售机构设备折旧', '其他',
  ],
  soe: [
    '职工薪酬', '差旅费', '业务招待费', '广告宣传费', '运输费',
    '折旧费', '摊销费', '办公费', '通讯费', '物料消耗',
    '租赁费', '保险费', '修理费', '包装费', '佣金及手续费',
    '售后服务费', '水电费', '仓储费', '其他',
  ],
}

/** 一行：上市带空 `remark`、国企没有（与 Tab 持久化 JSON 逐字段一致） */
function makeRow(
  variant: K8DisclosureVariant,
  id: string,
  project: string,
  currentAmount: number,
  priorAmount: number,
): K8DisclosureFormRow {
  return variant === 'listed'
    ? { id, project, currentAmount, priorAmount, remark: '' }
    : { id, project, currentAmount, priorAmount }
}

function defaultRows(variant: K8DisclosureVariant, ids: K8RowIdentity): K8DisclosureFormRow[] {
  const kind = variant === 'listed' ? 'row' : 'soe'
  return DEFAULT_PROJECTS[variant].map((name) => makeRow(variant, ids.newRow(kind), name, 0, 0))
}

/** 读 K8-1-audited-by-item（{项目名:{audited,prior}}）；没有 / 损坏 ⇒ 空 */
export function readK81AuditedMap(responses: K8DisclosureResponses): K81AuditedMap {
  const adjData = responses.get(AUDITED_BY_ITEM)
  if (!adjData?.remark) return {}
  try {
    const m = JSON.parse(adjData.remark)
    return m && typeof m === 'object' ? m : {}
  } catch { return {} }
}

/**
 * 读已保存的披露表（Tab onMounted 的 loadSavedData）：有手工保存的行用它（损坏 ⇒ 默认清单）；没有时优先按 K8-1 审定表项目
 * 动态建行（对齐源模板 B7='审定表K8-1'!A7，`hasAutoData`），否则默认清单。
 */
export function loadK8DisclosureState(
  responses: K8DisclosureResponses,
  variant: K8DisclosureVariant,
  ids: K8RowIdentity,
): K8DisclosureFormState {
  let rows: K8DisclosureFormRow[]
  let hasAutoData = false
  const saved = responses.get(ITEM[variant].rows)
  if (saved?.remark) {
    try {
      rows = JSON.parse(saved.remark)
    } catch { rows = defaultRows(variant, ids) }
  } else {
    const map = readK81AuditedMap(responses)
    const names = Object.keys(map)
    if (names.length) {
      rows = names.map((name) => makeRow(
        variant, ids.newRow('k81'), name, Number(map[name].audited ?? 0), Number(map[name].prior ?? 0),
      ))
      hasAutoData = true
    } else {
      rows = defaultRows(variant, ids)
    }
  }
  const savedNarrative = responses.get(ITEM[variant].narrative)
  return { rows, narrativeText: savedNarrative?.remark ? savedNarrative.remark : '', hasAutoData }
}

/**
 * 按 K8-1 审定表回填同名行（本期 / 上期），并追加 K8-1 有、披露表尚无的费用项目（动态项目对齐；就地改 `rows`）。
 * `data` 为空时不动。保存与提示由调用方决定（Tab 自动取数后保存，离屏不保存）。
 */
export function applyK8AutoFill(
  data: K81AuditedMap,
  rows: K8DisclosureFormRow[],
  variant: K8DisclosureVariant,
  ids: K8RowIdentity,
): void {
  const names = Object.keys(data)
  if (!names.length) return
  const existing = new Set(rows.map((r) => r.project))
  for (const row of rows) {
    const src = (data as any)[row.project]
    if (src) {
      row.currentAmount = Number(src.currentAmount ?? src.audited ?? 0)
      row.priorAmount = Number(src.priorAmount ?? src.prior ?? 0)
    }
  }
  for (const name of names) {
    if (!existing.has(name)) {
      const src = (data as any)[name]
      rows.push(makeRow(variant, ids.newRow('k81'), name, Number(src.audited ?? 0), Number(src.prior ?? 0)))
    }
  }
}

/** 披露表 → `buildK8SyncPayload` 的行：合计行由载荷层统一派生，这里只给明细行（避免双合计） */
export function k8DisclosureSyncRows(rows: readonly K8DisclosureFormRow[]): K8DisclosureFormRow[] {
  return rows.filter((r) => !r.isTotal)
}
