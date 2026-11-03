/**
 * J2 长期应付职工薪酬披露 Tab 的表单状态 + 挂载读回 + 同步载荷（底稿披露 Tab 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 由 `J2TabDisclosureListed`（上市 五、49，净负债期末为负另推 五、17 设定受益计划净资产）/ `J2TabDisclosureSoe`（国企 八、54）
 * 原样抽出：
 * - 表单状态与默认行（汇总 / 设定受益计划变动 / 到期分析 / 计划资产构成 / 精算假设 / 敏感性分析 / 三段说明）；
 * - `load`：挂载、回复变化时读回已保存的各区块（按 key 合并；国企还原用户新增的「其他变动」与计划资产子类别动态行），
 *   汇总表全 0 时按 J2-1 审定表（`J2-1-main`）带出期末（上市）/ 期初（国企）；
 * - `syncRequests(wpId, year)`：「同步到附注」发出的请求体（`toJ2SyncRequest(buildJ2…SyncPayload(快照))`）。
 * Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。保存、提示、AI、动态行的增删改名、勾稽、事件留在 Tab。
 */
import { reactive, ref } from 'vue'
import {
  buildJ2ListedSyncPayload,
  buildJ2NetAssetPayload,
  buildJ2SoeSyncPayload,
  toJ2SyncRequest,
  type J2SyncRequest,
} from './j2DisclosureSyncPayload'

/** 宿主下发的 checklist 回复（item_id → { remark, conclusion }） */
export type J2Responses = ReadonlyMap<string, { remark?: string | null } | undefined> | undefined

export function j2Num(v: unknown): number {
  const x = typeof v === 'number' ? v : parseFloat(String(v ?? ''))
  return Number.isFinite(x) ? x : 0
}
const n = j2Num

function parseJson<T>(responses: J2Responses, id: string, fb: T): T {
  const raw = responses?.get(id)?.remark
  if (!raw) return fb
  try { const p = JSON.parse(raw); return (p ?? fb) as T } catch { return fb }
}
function assignRows<T extends object>(target: T[], saved: unknown) {
  if (!Array.isArray(saved)) return
  for (const s of saved as Record<string, unknown>[]) { const row = target.find(r => (r as Record<string, unknown>).key === s.key); if (row) Object.assign(row, s) }
}

// ─── 上市（五、49） ──────────────────────────────────────────────────────────

export const J2_LISTED_KEY = {
  summary: 'J2-listed-summary', dbo: 'J2-listed-dbo', asset: 'J2-listed-planasset',
  net: 'J2-listed-netliab', maturity: 'J2-listed-maturity', assets: 'J2-listed-assets',
  assume: 'J2-listed-assumptions', sens: 'J2-listed-sensitivity',
  noteTerm: 'J2-listed-note-termination', noteDbp: 'J2-listed-note-dbp', noteSens: 'J2-listed-note-sensitivity',
}

export interface J2ListedAmtRow { key: string; label: string; end: number; begin: number }
export interface J2ListedMoveRow { key: string; label: string; indent: number; group?: boolean; cur: number; prior: number }
function mvListed(key: string, label: string, indent = 0, group = false): J2ListedMoveRow { return { key, label, indent, group, cur: 0, prior: 0 } }

/** 上市披露 Tab 的状态与计算 */
export function useJ2ListedDisclosureState() {
  const summaryRows = reactive<J2ListedAmtRow[]>([
    { key: 'dbp_net', label: '设定受益计划净负债', end: 0, begin: 0 },
    { key: 'termination', label: '辞退福利', end: 0, begin: 0 },
    { key: 'other_lt_net', label: '符合设定受益计划条件的其他长期职工福利的净负债', end: 0, begin: 0 },
    { key: 'other_lt', label: '其他长期福利', end: 0, begin: 0 },
    { key: 'less_within1y', label: '减：一年内到期的长期应付职工薪酬', end: 0, begin: 0 },
  ])
  const dboRows = reactive<J2ListedMoveRow[]>([
    mvListed('begin', '一、期初余额', 0),
    mvListed('pl', '二、计入当期损益的设定受益成本', 0, true),
    mvListed('pl_service', '1．当期服务成本', 1),
    mvListed('pl_past', '2．过去服务成本', 1),
    mvListed('pl_settle', '3．结算利得（损失以"-"表示）', 1),
    mvListed('pl_interest', '4．利息净额', 1),
    mvListed('oci', '三、计入其他综合收益的设定受益成本', 0, true),
    mvListed('oci_actuarial', '1．精算利得（损失以"-"表示）', 1),
    mvListed('oci_return', '2．计划资产的回报（计入利息净额的除外）', 1),
    mvListed('oci_ceiling', '3．资产上限影响的变动（计入利息净额的除外）', 1),
    mvListed('other', '四、其他变动', 0, true),
    mvListed('other_settle', '1．结算时消除的负债', 1),
    mvListed('other_paid', '2．已支付的福利', 1),
    mvListed('end', '五、期末余额', 0),
  ])
  const assetRows = reactive<J2ListedMoveRow[]>([
    mvListed('begin', '一、期初余额', 0),
    mvListed('pl', '二、计入当期损益的设定受益成本', 0, true),
    mvListed('pl_interest', '1．利息净额', 1),
    mvListed('oci', '三、计入其他综合收益的设定受益成本', 0, true),
    mvListed('oci_return', '1．计划资产的回报（计入利息净额的除外）', 1),
    mvListed('oci_ceiling', '2．资产上限影响的变动（计入利息净额的除外）', 1),
    mvListed('other', '四、其他变动', 0, true),
    mvListed('end', '五、期末余额', 0),
  ])
  const netRows = reactive<J2ListedMoveRow[]>([
    mvListed('begin', '一、期初余额', 0),
    mvListed('pl', '二、计入当期损益的设定受益成本', 0),
    mvListed('oci', '三、计入其他综合收益的设定受益成本', 0),
    mvListed('other', '四、其他变动', 0),
    mvListed('end', '五、期末余额', 0),
  ])
  const maturityRows = reactive([
    { key: 'y1', label: '一年以内', amount: 0 },
    { key: 'y1_2', label: '一到两年', amount: 0 },
    { key: 'y2_5', label: '二到五年', amount: 0 },
    { key: 'y5', label: '五年以上', amount: 0 },
  ])
  const assetCompRows = reactive<J2ListedAmtRow[]>([
    { key: 'cash', label: '现金和现金等价物', end: 0, begin: 0 },
    { key: 'equity', label: '权益工具投资', end: 0, begin: 0 },
    { key: 'debt', label: '债务工具投资', end: 0, begin: 0 },
    { key: 'other', label: '其他', end: 0, begin: 0 },
  ])
  const assumeRows = reactive([
    { key: 'discount', label: '折现率', end: 0, begin: 0 },
    { key: 'mortality', label: '死亡率', end: 0, begin: 0 },
    { key: 'life', label: '预计平均寿命', end: 0, begin: 0 },
    { key: 'turnover', label: '职工的离职率', end: 0, begin: 0 },
    { key: 'salary', label: '薪酬的预期增长率', end: 0, begin: 0 },
  ])
  const sensRows = reactive([
    { key: 'discount', label: '折现率', delta: 0, up: 0, down: 0 },
    { key: 'mortality', label: '死亡率', delta: 0, up: 0, down: 0 },
    { key: 'life', label: '预计平均寿命', delta: 0, up: 0, down: 0 },
    { key: 'turnover', label: '职工的离职率', delta: 0, up: 0, down: 0 },
    { key: 'salary', label: '薪酬的预期增长率', delta: 0, up: 0, down: 0 },
  ])
  const noteTerm = ref('')
  const noteDbp = ref('')
  const noteSens = ref('')

  function load(responses: J2Responses): void {
    const KEY = J2_LISTED_KEY
    assignRows(summaryRows, parseJson(responses, KEY.summary, null))
    assignRows(dboRows, parseJson(responses, KEY.dbo, null))
    assignRows(assetRows, parseJson(responses, KEY.asset, null))
    assignRows(netRows, parseJson(responses, KEY.net, null))
    assignRows(maturityRows, parseJson(responses, KEY.maturity, null))
    assignRows(assetCompRows, parseJson(responses, KEY.assets, null))
    assignRows(assumeRows, parseJson(responses, KEY.assume, null))
    assignRows(sensRows, parseJson(responses, KEY.sens, null))
    const t = responses?.get(KEY.noteTerm)?.remark; if (t) noteTerm.value = t
    const d = responses?.get(KEY.noteDbp)?.remark; if (d) noteDbp.value = d
    const s = responses?.get(KEY.noteSens)?.remark; if (s) noteSens.value = s
    // 从审定表(J2-1-main)自动 seed 汇总表期末数（仅在汇总表全 0 时）
    const anySum = summaryRows.some(r => n(r.end) !== 0 || n(r.begin) !== 0)
    if (!anySum) {
      const mainRaw = responses?.get('J2-1-main')?.remark
      if (mainRaw) {
        try {
          const main = JSON.parse(mainRaw) as Array<Record<string, unknown>>
          const audited = (k: string) => { const r = main.find(x => x.key === k); return r ? n(r.endUnadj) + n(r.endAje) : 0 }
          const beginAud = (k: string) => { const r = main.find(x => x.key === k); return r ? n(r.beginUnadj) + n(r.beginAje) : 0 }
          summaryRows.find(r => r.key === 'dbp_net')!.end = audited('dbp')
          summaryRows.find(r => r.key === 'dbp_net')!.begin = beginAud('dbp')
          summaryRows.find(r => r.key === 'termination')!.end = audited('termination')
          summaryRows.find(r => r.key === 'termination')!.begin = beginAud('termination')
          summaryRows.find(r => r.key === 'less_within1y')!.end = audited('less_within1y')
          summaryRows.find(r => r.key === 'less_within1y')!.begin = beginAud('less_within1y')
        } catch { /* ignore */ }
      }
    }
  }

  /** 「同步到附注」的请求体：五、49 一条；净负债表期末为负（= 净资产）另推 五、17 一条 */
  function syncRequests(wpId: string, year: number | null | undefined): J2SyncRequest[] {
    const payload = buildJ2ListedSyncPayload({
      summaryRows: [...summaryRows],
      dboRows: [...dboRows],
      assetRows: [...assetRows],
      netRows: [...netRows],
      maturityRows: [...maturityRows],
      assetCompRows: [...assetCompRows],
      assumeRows: [...assumeRows],
      sensRows: [...sensRows],
      noteTerm: noteTerm.value,
      noteDbp: noteDbp.value,
      noteSens: noteSens.value,
    })
    const out: J2SyncRequest[] = [toJ2SyncRequest(payload, { wpId, currentStandard: 'listed_standalone', year })]
    const netEndRow = netRows.find(r => r.key === 'end')
    if (netEndRow && n(netEndRow.cur) < 0) {
      const netAssetPayload = buildJ2NetAssetPayload({
        dbpNetRow: {
          begin: n(netRows.find(r => r.key === 'begin')?.cur ?? 0),
          increase: n(netRows.find(r => r.key === 'pl')?.cur ?? 0) + n(netRows.find(r => r.key === 'oci')?.cur ?? 0),
          decrease: Math.abs(n(netRows.find(r => r.key === 'other')?.cur ?? 0)),
          end: n(netEndRow.cur),
        },
      })
      out.push(toJ2SyncRequest(netAssetPayload, { wpId, currentStandard: 'listed_standalone', year }))
    }
    return out
  }

  return {
    summaryRows, dboRows, assetRows, netRows, maturityRows, assetCompRows, assumeRows, sensRows,
    noteTerm, noteDbp, noteSens, load, syncRequests,
  }
}

// ─── 国企（八、54） ──────────────────────────────────────────────────────────

export const J2_SOE_KEY = {
  summary: 'J2-soe-summary', change: 'J2-soe-change', maturity: 'J2-soe-maturity',
  assets: 'J2-soe-assets', assume: 'J2-soe-assumptions', sens: 'J2-soe-sensitivity',
  noteTerm: 'J2-soe-note-termination', noteDbp: 'J2-soe-note-dbp', noteSens: 'J2-soe-note-sensitivity',
}

export interface J2SoeSumRow { key: string; label: string; begin: number; increase: number; decrease: number }
export type J2SoeMoveCol = 'dboCur' | 'dboPrior' | 'assetCur' | 'assetPrior' | 'netCur' | 'netPrior'
export interface J2SoeMoveRow {
  key: string; label: string; indent: number
  kind: 'leaf' | 'sum' | 'grand'; children?: string[]; assetNa?: boolean
  dboCur: number; dboPrior: number; assetCur: number; assetPrior: number; netCur: number; netPrior: number
}
export interface J2SoeAssetRow { key: string; label: string; indent: number; group?: boolean; end: number; begin: number }

/** 国企变动表行（Tab 的动态「其他变动」行同用） */
export function j2SoeMoveRow(key: string, label: string, indent: number, kind: J2SoeMoveRow['kind'], opts: Partial<J2SoeMoveRow> = {}): J2SoeMoveRow {
  return { key, label, indent, kind, dboCur: 0, dboPrior: 0, assetCur: 0, assetPrior: 0, netCur: 0, netPrior: 0, ...opts }
}
/** 「四、其他变动」的固定行（其余 other_* 叶子行是用户新增的动态行） */
export const J2_SOE_FIXED_OTHER_KEYS = new Set(['other_settle', 'other_paid'])
/** 判断是否为四、其他变动区块的动态行（可删除） */
export function isJ2SoeOtherDynamic(row: J2SoeMoveRow): boolean {
  return row.kind === 'leaf' && row.key.startsWith('other_') && !J2_SOE_FIXED_OTHER_KEYS.has(row.key)
}
export function j2SoeSumEnd(r: J2SoeSumRow): number { return n(r.begin) + n(r.increase) - n(r.decrease) }

/** 国企披露 Tab 的状态与计算 */
export function useJ2SoeDisclosureState() {
  const mv = j2SoeMoveRow
  const summaryRows = reactive<J2SoeSumRow[]>([
    { key: 'dbp_net', label: '设定受益计划净负债', begin: 0, increase: 0, decrease: 0 },
    { key: 'other_lt_net', label: '符合设定受益计划条件的其他长期职工福利的净负债', begin: 0, increase: 0, decrease: 0 },
    { key: 'termination', label: '一年后支付的辞退福利', begin: 0, increase: 0, decrease: 0 },
  ])
  const changeRows = reactive<J2SoeMoveRow[]>([
    mv('begin', '一、期初余额', 0, 'leaf'),
    mv('pl', '二、计入当期损益的设定受益成本', 0, 'sum', { children: ['pl_service', 'pl_past', 'pl_settle', 'pl_interest'] }),
    mv('pl_service', '1．当期服务成本', 1, 'leaf', { assetNa: true }),
    mv('pl_past', '2．过去服务成本', 1, 'leaf', { assetNa: true }),
    mv('pl_settle', '3．结算利得（损失以"-"表示）', 1, 'leaf', { assetNa: true }),
    mv('pl_interest', '4．利息净额', 1, 'leaf'),
    mv('oci', '三、计入其他综合收益的设定受益成本', 0, 'sum', { children: ['oci_remeasure'] }),
    mv('oci_remeasure', '设定受益计划净负债（净资产）的重新计量', 1, 'sum', { children: ['oci_actuarial', 'oci_return', 'oci_ceiling'] }),
    mv('oci_actuarial', '1．精算利得（损失以"-"表示）', 2, 'leaf', { assetNa: true }),
    mv('oci_return', '2．计划资产的回报（计入利息净额的除外）', 2, 'leaf'),
    mv('oci_ceiling', '3．资产上限影响的变动（计入利息净额的除外）', 2, 'leaf'),
    mv('other', '四、其他变动', 0, 'sum', { children: ['other_settle', 'other_paid', 'other_etc'] }),
    mv('other_settle', '1．结算时消除的负债', 1, 'leaf'),
    mv('other_paid', '2．已支付的福利', 1, 'leaf'),
    mv('other_etc', '……', 1, 'leaf'),
    mv('end', '五、期末余额', 0, 'grand'),
  ])
  const maturityRows = reactive([
    { key: 'y1', label: '一年以内', amount: 0 },
    { key: 'y1_2', label: '一到两年', amount: 0 },
    { key: 'y2_5', label: '二到五年', amount: 0 },
    { key: 'y5', label: '五年以上', amount: 0 },
  ])
  const assetCompRows = reactive<J2SoeAssetRow[]>([
    { key: 'cash', label: '现金和现金等价物', indent: 0, end: 0, begin: 0 },
    { key: 'equity', label: '权益工具投资', indent: 0, group: true, end: 0, begin: 0 },
    { key: 'equity_1', label: '1、……', indent: 1, end: 0, begin: 0 },
    { key: 'equity_2', label: '2、……', indent: 1, end: 0, begin: 0 },
    { key: 'debt', label: '债务工具投资', indent: 0, group: true, end: 0, begin: 0 },
    { key: 'debt_1', label: '1、……', indent: 1, end: 0, begin: 0 },
    { key: 'debt_2', label: '2、……', indent: 1, end: 0, begin: 0 },
    { key: 'other', label: '其他', indent: 0, end: 0, begin: 0 },
  ])
  const assumeRows = reactive([
    { key: 'discount', label: '折现率', end: 0, begin: 0 },
    { key: 'mortality', label: '死亡率', end: 0, begin: 0 },
    { key: 'life', label: '预计平均寿命', end: 0, begin: 0 },
    { key: 'turnover', label: '职工的离职率', end: 0, begin: 0 },
    { key: 'salary', label: '薪酬的预期增长率', end: 0, begin: 0 },
  ])
  const sensRows = reactive([
    { key: 'discount', label: '折现率', delta: 0, up: 0, down: 0 },
    { key: 'mortality', label: '死亡率', delta: 0, up: 0, down: 0 },
    { key: 'life', label: '预计平均寿命', delta: 0, up: 0, down: 0 },
    { key: 'turnover', label: '职工的离职率', delta: 0, up: 0, down: 0 },
    { key: 'salary', label: '薪酬的预期增长率', delta: 0, up: 0, down: 0 },
  ])
  const noteTerm = ref('')
  const noteDbp = ref('')
  const noteSens = ref('')

  function load(responses: J2Responses): void {
    const KEY = J2_SOE_KEY
    assignRows(summaryRows, parseJson(responses, KEY.summary, null))

    // Restore changeRows — including dynamically added other_* rows
    const savedChange = parseJson<J2SoeMoveRow[] | null>(responses, KEY.change, null)
    if (Array.isArray(savedChange)) {
      // Restore existing fixed rows
      assignRows(changeRows, savedChange)
      // Restore dynamic other_* rows that were added by user
      const endIdx = changeRows.findIndex(r => r.key === 'end')
      const otherParent = changeRows.find(r => r.key === 'other')
      for (const s of savedChange) {
        if (s.key.startsWith('other_') && !J2_SOE_FIXED_OTHER_KEYS.has(s.key) && s.key !== 'other_etc' && !changeRows.some(r => r.key === s.key)) {
          const newRow = mv(s.key, s.label, 1, 'leaf')
          Object.assign(newRow, s)
          newRow.indent = 1
          newRow.kind = 'leaf'
          const insertAt = endIdx >= 0 ? changeRows.findIndex(r => r.key === 'end') : changeRows.length
          changeRows.splice(insertAt, 0, newRow)
          if (otherParent?.children && !otherParent.children.includes(s.key)) {
            otherParent.children.push(s.key)
          }
        }
      }
      // Remove the placeholder other_etc row if dynamic rows exist
      const hasDynOther = changeRows.some(r => isJ2SoeOtherDynamic(r))
      if (hasDynOther) {
        const etcIdx = changeRows.findIndex(r => r.key === 'other_etc')
        if (etcIdx >= 0) changeRows.splice(etcIdx, 1)
        if (otherParent?.children) {
          const ci = otherParent.children.indexOf('other_etc')
          if (ci >= 0) otherParent.children.splice(ci, 1)
        }
      }
    }

    assignRows(maturityRows, parseJson(responses, KEY.maturity, null))

    // Restore assetCompRows — including dynamically added equity_*/debt_* rows
    const savedAssets = parseJson<J2SoeAssetRow[] | null>(responses, KEY.assets, null)
    if (Array.isArray(savedAssets)) {
      assignRows(assetCompRows, savedAssets)
      // Restore dynamic sub-rows for equity/debt
      for (const s of savedAssets) {
        const isEquitySub = s.key.startsWith('equity_') && s.key !== 'equity_1' && s.key !== 'equity_2'
        const isDebtSub = s.key.startsWith('debt_') && s.key !== 'debt_1' && s.key !== 'debt_2'
        if ((isEquitySub || isDebtSub) && !assetCompRows.some(r => r.key === s.key)) {
          const group = s.key.split('_')[0]
          const groupParentIdx = assetCompRows.findIndex(r => r.key === group)
          let insertIdx = groupParentIdx + 1
          while (insertIdx < assetCompRows.length && assetCompRows[insertIdx].key.startsWith(`${group}_`)) {
            insertIdx++
          }
          const newRow: J2SoeAssetRow = { key: s.key, label: s.label || '', indent: 1, end: n(s.end), begin: n(s.begin) }
          assetCompRows.splice(insertIdx, 0, newRow)
        }
      }
    }

    assignRows(assumeRows, parseJson(responses, KEY.assume, null))
    assignRows(sensRows, parseJson(responses, KEY.sens, null))
    const t = responses?.get(KEY.noteTerm)?.remark; if (t) noteTerm.value = t
    const d = responses?.get(KEY.noteDbp)?.remark; if (d) noteDbp.value = d
    const s = responses?.get(KEY.noteSens)?.remark; if (s) noteSens.value = s
    // 从审定表(J2-1-main)自动 seed 汇总表期初数（仅在汇总表全 0 时）
    const anySum = summaryRows.some(r => n(r.begin) !== 0 || n(r.increase) !== 0 || n(r.decrease) !== 0)
    if (!anySum) {
      const mainRaw = responses?.get('J2-1-main')?.remark
      if (mainRaw) {
        try {
          const main = JSON.parse(mainRaw) as Array<Record<string, unknown>>
          const beginAud = (k: string) => { const r = main.find(x => x.key === k); return r ? n(r.beginUnadj) + n(r.beginAje) : 0 }
          summaryRows.find(r => r.key === 'dbp_net')!.begin = beginAud('dbp')
          summaryRows.find(r => r.key === 'termination')!.begin = beginAud('termination')
        } catch { /* ignore */ }
      }
    }
  }

  /** 「同步到附注」的请求体（八、54 一条） */
  function syncRequests(wpId: string, year: number | null | undefined): J2SyncRequest[] {
    const payload = buildJ2SoeSyncPayload({
      summaryRows: [...summaryRows],
      changeRows: changeRows.filter(r => r.kind === 'leaf').map(r => ({
        key: r.key,
        label: r.label,
        dboCur: r.dboCur,
        dboPrior: r.dboPrior,
        assetCur: r.assetCur,
        assetPrior: r.assetPrior,
        netCur: r.netCur,
        netPrior: r.netPrior,
      })),
      maturityRows: [...maturityRows],
      assetCompRows: [...assetCompRows],
      assumeRows: [...assumeRows],
      sensRows: [...sensRows],
      noteTerm: noteTerm.value,
      noteDbp: noteDbp.value,
      noteSens: noteSens.value,
      summaryEndFn: (r) => n(r.begin) + n(r.increase) - n(r.decrease),
    })
    return [toJ2SyncRequest(payload, { wpId, currentStandard: 'soe_standalone', year })]
  }

  return {
    summaryRows, changeRows, maturityRows, assetCompRows, assumeRows, sensRows,
    noteTerm, noteDbp, noteSens, load, syncRequests,
  }
}
