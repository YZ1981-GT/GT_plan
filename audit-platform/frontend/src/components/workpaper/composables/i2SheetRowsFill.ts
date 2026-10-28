/**
 * I2-9 研发人员认定检查 / I2-10 研发人员工时检查接入共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 12）
 *
 * 这两张表的行是人员 / 项目月份，不是凭证：抽凭样本一个一行（`policy: 'join'`），凭证号与日期只记在备注 / 附件索引里，
 * 行是哪笔分录只看 `_gt` 里的分录指纹。旧行（没有 `_gt`）没有凭证号、日期、金额列，认不出是哪笔分录，不参与去重
 * （原实现回填根本不去重：同一凭证抽两次插两行）。行的读入 / 保存原写在组件里，收进这里：读入透传 `_gt`，
 * 保存经 `guardPersist`（年审阶段预审行按读入版本写回）。
 */
import { ref, toValue, type MaybeRefOrGetter, type Ref } from 'vue'
import {
  useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillOutcome, type FillSample, type PreparedItem, type UndoRequestPayload,
} from './shared/voucherCheckFill'
import { assetAmount, sampleOf, type AssetSample } from './assetVoucherFill'
import {
  emptyI2StaffRow, I2_STAFF_STORAGE_KEY, normalizeI2StaffRow, persistI2StaffRow, type I2StaffCheckRow,
} from './i2StaffCheckModel'
import {
  emptyI2WorkHourRow, I2_WORKHOUR_STORAGE_KEY, normalizeI2WorkHourRow, persistI2WorkHourRow, type I2WorkHourCheckRow,
} from './i2WorkHourModel'

/** allResponses 里一张表的行（JSON 字符串、带 remark 的条目或数组） */
function parseStoredRows(raw: unknown): unknown[] {
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string'
      ? JSON.parse(raw)
      : ((raw as { remark?: string }).remark ? JSON.parse(String((raw as { remark?: string }).remark)) : raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export interface I2SheetRowsFill<R> {
  rows: Ref<R[]>
  /** 读入一张表（allResponses 里的条目原样传入） */
  load: (raw: unknown) => void
  /** 保存这张表（「保存」按钮与回填 / 撤销同一写法） */
  save: () => Promise<void>
  /** 删一行（年审阶段预审行不删） */
  removeAt: (index: number) => void
  onEngineFilled: (payload: EngineFilledPayload) => Promise<FillOutcome>
  onAttachImported: (samples: FillSample[]) => Promise<FillOutcome>
  onUndoRequest: (payload: UndoRequestPayload) => Promise<boolean>
  rowClass: (arg: { row: R }) => string
  isRowLocked: (row: R) => boolean
  ready: () => Promise<unknown>
}

export function useI2SheetRowsFill<R extends { rowId: string }>(opts: {
  sheetCode: string
  storageKey: string
  projectId: MaybeRefOrGetter<string | null | undefined>
  readonly: MaybeRefOrGetter<boolean | undefined>
  saveResponse: (sheetCode: string, data: Record<string, unknown>) => Promise<void>
  normalize: (raw: any) => R
  /** 行 → 落库形状（宿主原有的 persist 函数） */
  toStored: (row: R) => object
  mapSampleToRow: (item: PreparedItem) => R
  hasUserContent: (row: R) => boolean
}): I2SheetRowsFill<R> {
  const rows = ref([]) as Ref<R[]>

  async function save(): Promise<void> {
    const stored = fill.guardPersist(rows.value).map(r => withRowMeta(opts.toStored(r), r))
    await opts.saveResponse(opts.sheetCode, { [opts.storageKey]: JSON.stringify(stored) })
  }

  const fill = useVoucherCheckFill<R>({
    projectId: opts.projectId,
    tables: rows,
    policy: 'join',
    mapSampleToRow: item => opts.mapSampleToRow(item),
    persist: () => save(),
    hasUserContent: opts.hasUserContent,
    legacy: () => null,
    readonly: () => toValue(opts.readonly) === true,
  })

  function load(raw: unknown): void {
    rows.value = parseStoredRows(raw).map(r => withRowMeta(opts.normalize(r), r))
    fill.markLoaded()
  }

  function removeAt(index: number): void {
    const row = rows.value[index]
    if (!row || fill.isRowLocked(row)) return
    rows.value.splice(index, 1)
  }

  return {
    rows,
    load,
    save,
    removeAt,
    onEngineFilled: payload => fill.onEngineFilled(payload),
    onAttachImported: samples => fill.onAttachImported(samples),
    onUndoRequest: payload => fill.onUndoRequest(payload),
    rowClass: fill.rowClass,
    isRowLocked: fill.isRowLocked,
    ready: fill.ready,
  }
}

/** 凭证号 / 日期（「凭证 0012 / 2025-03-04」）：同号凭证可能跨日重复，只记凭证号认不出是哪一张 */
function voucherRef(s: AssetSample): string {
  return [s.voucherNo ? `凭证 ${s.voucherNo}` : '', s.voucherDate || ''].filter(Boolean).join(' / ')
}

/** 凭证号 / 日期 / 摘要拼成的说明（「凭证 0012 / 2025-03-04 / 摘要」，原实现的写法） */
function voucherNote(s: AssetSample): string {
  return [voucherRef(s), String(s.summary ?? '')].filter(Boolean).join(' / ')
}

/** 抽凭样本 → I2-9 人员行：姓名先取摘要（待人工改成人员姓名），凭证号、日期、摘要记在备注 */
export function staffRowFromPrepared(item: PreparedItem): I2StaffCheckRow {
  const s = sampleOf(item)
  return emptyI2StaffRow({
    staffName: String(s.summary || s.voucherNo || ''),
    remark: voucherNote(s),
  })
}

/**
 * 抽凭样本 → I2-10 工时行：人员先取摘要、项目取样本科目名，薪酬计提取样本自己那一栏的金额（红字带符号），附件索引记
 * 凭证号与日期（原实现只记凭证号）
 */
export function workHourRowFromPrepared(item: PreparedItem): I2WorkHourCheckRow {
  const s = sampleOf(item) as AssetSample & { accountName?: string | null }
  return emptyI2WorkHourRow({
    staffName: String(s.summary || s.voucherNo || ''),
    projectName: String(s.accountName ?? ''),
    salaryAccrual: assetAmount(item, 'debit'),
    attachmentIndex: voucherRef(s),
  })
}

/** I2-9 行上已填核对内容（替换与撤销抽凭时据此先确认）：人员资料各栏、附件、改过的认定结论 */
export function hasI2StaffContent(r: I2StaffCheckRow): boolean {
  return [r.gender, r.education, r.graduateSchool, r.major, r.title, r.position, r.department, r.personnelCategory,
    r.hireDate, r.employmentForm, r.fullTimeRd, r.projects, r.attachmentIndex].some(v => String(v ?? '').trim() !== '')
    || r.age != null || r.rdHourRatio != null
    || (!!r.conclusion && r.conclusion !== r.suggestedConclusion)
}

/** I2-10 行上已填核对内容：项目号与期间、月份、工时、分配依据、检查要素、股份支付、备注、改过的结论 */
export function hasI2WorkHourContent(r: I2WorkHourCheckRow): boolean {
  return [r.projectCode, r.projectPeriod, r.month, r.allocationBasis, r.customCheck, r.hasShareBasedPay, r.remark]
    .some(v => String(v ?? '').trim() !== '')
    || Number(r.hours) !== 0 || Number(r.totalHours) !== 0
    || (!!r.conclusion && r.conclusion !== r.suggestedConclusion)
}

/** 宿主组件给的上下文 */
export interface I2SheetRowsContext {
  projectId: MaybeRefOrGetter<string | null | undefined>
  readonly: MaybeRefOrGetter<boolean | undefined>
  saveResponse: (sheetCode: string, data: Record<string, unknown>) => Promise<void>
}

/** I2-9 研发人员认定检查的行读写与回填 */
export function useI2StaffRowsFill(ctx: I2SheetRowsContext): I2SheetRowsFill<I2StaffCheckRow> {
  return useI2SheetRowsFill<I2StaffCheckRow>({
    ...ctx,
    sheetCode: 'I2-9',
    storageKey: I2_STAFF_STORAGE_KEY,
    normalize: normalizeI2StaffRow,
    toStored: persistI2StaffRow,
    mapSampleToRow: staffRowFromPrepared,
    hasUserContent: hasI2StaffContent,
  })
}

/** I2-10 研发人员工时检查的行读写与回填 */
export function useI2WorkHourRowsFill(ctx: I2SheetRowsContext): I2SheetRowsFill<I2WorkHourCheckRow> {
  return useI2SheetRowsFill<I2WorkHourCheckRow>({
    ...ctx,
    sheetCode: 'I2-10',
    storageKey: I2_WORKHOUR_STORAGE_KEY,
    normalize: normalizeI2WorkHourRow,
    toStored: persistI2WorkHourRow,
    mapSampleToRow: workHourRowFromPrepared,
    hasUserContent: hasI2WorkHourContent,
  })
}
