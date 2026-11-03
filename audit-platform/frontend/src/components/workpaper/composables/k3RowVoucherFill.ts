/**
 * K3-5 长期挂账 / K3-6 关联方往来的行级抽凭（spec voucher-identity-writeback-and-audit-phase 任务 13）
 *
 * 这两张表一行是一个往来对象、不是一张凭证：行上「📋」抽到的凭证记进本表的「抽凭明细」——一个对方科目一行，
 * 挂到发起抽凭的往来对象行；共享回填函数按分录指纹去重、按批次撤销、年审阶段预审行只读，行元数据 `_gt` 随明细落库。
 * 挂凭导入没有发起行：按辅助核算往来单位（唯一命中才有）对上同名往来对象，对不上的留在明细里、标「未对应」。
 * 原实现读引擎载荷的 `payload.voucherNo`（载荷是 `{ samples, … }`）⇒ 抽凭与挂凭导入都是空操作。
 * 明细单独存一条 checklist 项（`<表号>-row-vouchers`），不动往来对象行的结构。
 */
import { ref, toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'
import { partyNameForColumn } from './shared/samplingPartyTarget'
import {
  useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillOutcome, type FillSample, type PreparedItem,
} from './shared/voucherCheckFill'

export interface K3RowVoucher {
  rowId: string
  /** 挂到的往来对象行（空 = 挂凭导入时没对上往来对象） */
  targetRowId: string
  /** 往来对象名称（冗余：往来对象行删掉后仍看得出是谁的） */
  counterparty: string
  voucherDate: string
  voucherNo: string
  summary: string
  counterpartAccount: string
  counterpartAccountName: string
  debitAmount: number
  creditAmount: number
  /** 核对结果（用户填） */
  checkResult: string
  remark: string
}

export interface K3RowVoucherTarget {
  rowId: string
  counterparty: string
}

export function emptyK3RowVoucher(): K3RowVoucher {
  return {
    rowId: `k3rv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    targetRowId: '', counterparty: '', voucherDate: '', voucherNo: '', summary: '',
    counterpartAccount: '', counterpartAccountName: '', debitAmount: 0, creditAmount: 0, checkResult: '', remark: '',
  }
}

/** 共享回填函数的待写入项 → 抽凭明细行（金额在样本自己的借贷栏，对方科目按后端配对，配不上写「多科目」） */
export function mapPreparedToK3RowVoucher(item: PreparedItem, target: K3RowVoucherTarget | null): K3RowVoucher {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null; selectionReason?: string | null }
  const code = item.counterpartAccount
  const name = item.counterpartAccountName
  return {
    ...emptyK3RowVoucher(),
    targetRowId: target?.rowId ?? '',
    counterparty: target?.counterparty ?? (partyNameForColumn(s, 'supplier') || ''),
    voucherDate: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    summary: s.summary || '',
    counterpartAccount: code,
    counterpartAccountName: name && name !== code ? name : '',
    debitAmount: Number(item.debitAmount ?? 0) || 0,
    creditAmount: Number(item.creditAmount ?? 0) || 0,
    remark: s.selectionReason || '',
  }
}

/** 明细行上已填核对结果（替换与撤销抽凭时据此先确认；备注缺省是选样原因，不算） */
export function hasK3RowVoucherContent(r: K3RowVoucher): boolean {
  return String(r.checkResult ?? '').trim() !== ''
}

export function useK3RowVoucherFill(opts: {
  /** 表号（K3-5 / K3-6）：明细存 `<表号>-row-vouchers` */
  sheet: string
  allResponses: () => Map<string, any>
  save: (itemId: string, payload: { remark: string }) => void
  projectId: MaybeRefOrGetter<string | null | undefined>
  readonly?: MaybeRefOrGetter<boolean | undefined>
  /** 往来对象行（挂凭导入按名称对上） */
  targets: () => K3RowVoucherTarget[]
}) {
  const itemId = `${opts.sheet}-row-vouchers`
  const rows: Ref<K3RowVoucher[]> = ref([])
  /** 本次抽凭的发起行（引擎回填期间有效） */
  let pending: K3RowVoucherTarget | null = null

  function matchTarget(item: PreparedItem): K3RowVoucherTarget | null {
    const party = (partyNameForColumn(item.sample, 'supplier') || '').trim()
    if (!party) return null
    const hits = opts.targets().filter(t => String(t.counterparty ?? '').trim() === party)
    return hits.length === 1 ? hits[0] : null
  }

  function persist(): void {
    opts.save(itemId, { remark: JSON.stringify(fill.guardPersist(rows.value)) })
  }

  const fill = useVoucherCheckFill<K3RowVoucher>({
    projectId: opts.projectId,
    tables: rows,
    mapSampleToRow: (item) => mapPreparedToK3RowVoucher(item, item.meta.src.includes('attach') ? matchTarget(item) : pending),
    persist,
    hasUserContent: hasK3RowVoucherContent,
    readonly: () => Boolean(toValue(opts.readonly)),
  })

  function load(): void {
    try {
      const raw = opts.allResponses().get(itemId)?.remark
      const list = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : []
      rows.value = Array.isArray(list) ? list.map((r: any) => withRowMeta({ ...emptyK3RowVoucher(), ...r }, r)) : []
    } catch {
      rows.value = []
    } finally {
      fill.markLoaded()
    }
  }
  // 父组件重读 allResponses（切页签、他处保存）时跟着重读
  watch(() => opts.allResponses().get(itemId)?.remark, load, { immediate: true })

  /** 行上「📋」抽凭：样本挂到发起行，按分录指纹去重；填完由共享函数保存并提示填入几行 */
  async function onEngineFilled(payload: EngineFilledPayload, target: K3RowVoucherTarget | null): Promise<FillOutcome> {
    pending = target
    try {
      return await fill.onEngineFilled(payload)
    } finally {
      pending = null
    }
  }

  /** 从序时账挂入导入：幂等追加，按往来单位对上往来对象 */
  function onAttachImported(samples: FillSample[]): Promise<FillOutcome> {
    return fill.onAttachImported(samples)
  }

  function vouchersOf(targetRowId: string): K3RowVoucher[] {
    return rows.value.filter(v => v.targetRowId === targetRowId)
  }

  /** 删明细行（年审阶段的预审行不删） */
  function removeVoucher(rowId: string): void {
    if (toValue(opts.readonly)) return
    rows.value = rows.value.filter(v => v.rowId !== rowId || fill.isRowLocked(v))
    persist()
  }

  return {
    itemId,
    rows,
    load,
    persist,
    onEngineFilled,
    onAttachImported,
    onUndoRequest: fill.onUndoRequest,
    rowClass: fill.rowClass,
    isRowLocked: fill.isRowLocked,
    ready: fill.ready,
    vouchersOf,
    removeVoucher,
  }
}
