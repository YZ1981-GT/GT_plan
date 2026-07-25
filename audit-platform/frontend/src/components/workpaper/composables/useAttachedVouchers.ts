/**
 * useAttachedVouchers.ts — 序时账「挂凭到底稿」↔ 底稿凭证检查联动（可复用）
 *
 * 两个方向：
 *  1. 序时账侧（LedgerPenetration）手工挑选凭证 → `attachVoucher` 记录到 sampled_vouchers
 *     （带 working_paper_id + source='ledger'），作为该底稿的手工挂入样本清单。
 *  2. 底稿凭证检查侧（如 E1-23 收支检查）→ `pullSamplesForWorkpaper` 拉取挂到本底稿的
 *     凭证，逐张取回完整分录，映射为抽凭引擎同款 `SampledVoucher[]`，喂给底稿既有
 *     的 `onSampleFilled`/`fillFromSamples`（与抽凭引擎回填口径一致）。
 *
 * 不新造抽样算法/不改抽凭引擎；仅复用既有 sample-voucher / sampled-vouchers /
 * ledger/voucher/{no} 三个端点。
 */
import http from '@/utils/http'
import { ledger as P_ledger } from '@/services/apiPaths'
import type { SampledVoucher } from './useSamplingAlgorithms'

/** 后端 sampled_vouchers 行 */
export interface AttachedVoucherRecord {
  id: string
  voucher_no: string
  account_code: string | null
  sampling_record_id: string | null
  working_paper_id: string | null
  note: string | null
  sampled_at: string | null
}

/** 挂凭到底稿请求 */
export interface AttachVoucherPayload {
  year: number
  voucherNo: string
  accountCode?: string | null
  workpaperId?: string | null
  source?: string
  note?: string
}

function unwrap<T = any>(res: any): T {
  // http 拦截器已解包 { code, data } 信封 → res.data 通常即真实数据
  return (res?.data?.data ?? res?.data ?? res) as T
}

/**
 * 挂凭：把一张凭证记录到抽样清单（可关联目标底稿）。同项目+年度+凭证号去重
 * （已挂则更新 working_paper_id/note）。
 */
export async function attachVoucher(
  projectId: string,
  payload: AttachVoucherPayload,
): Promise<{ id: string; voucher_no: string; status: string }> {
  const res = await http.post(P_ledger.sampleVoucher(projectId), {
    year: payload.year,
    voucher_no: payload.voucherNo,
    account_code: payload.accountCode ?? null,
    working_paper_id: payload.workpaperId ?? null,
    source: payload.source ?? 'ledger',
    note: payload.note ?? null,
  })
  return unwrap(res)
}

/** 拉取抽样清单（可按目标底稿过滤） */
export async function listAttachedVouchers(
  projectId: string,
  year: number,
  workpaperId?: string,
): Promise<AttachedVoucherRecord[]> {
  const params: Record<string, unknown> = { year }
  if (workpaperId) params.working_paper_id = workpaperId
  const res = await http.get(P_ledger.sampledVouchers(projectId), { params })
  const data = unwrap<{ items?: AttachedVoucherRecord[] }>(res)
  return Array.isArray(data?.items) ? data.items : []
}

/** 取消挂凭（软删一条抽样记录） */
export async function removeAttachedVoucher(projectId: string, sampledId: string): Promise<void> {
  await http.delete(P_ledger.sampledVoucherDelete(projectId, sampledId))
}

/** 单张凭证的完整分录（穿透） */
async function fetchVoucherLines(
  projectId: string,
  year: number,
  voucherNo: string,
): Promise<any[]> {
  const res = await http.get(P_ledger.voucher(projectId, voucherNo), { params: { year } })
  const data = unwrap<any>(res)
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.items)) return data.items
  return []
}

/** 判断一条分录行的科目是否落在给定科目前缀集合内（用于挑「本科目」那条分录） */
function lineMatchesAccounts(line: any, accountPrefixes: string[]): boolean {
  if (!accountPrefixes.length) return true
  const code = String(line?.account_code ?? '')
  return accountPrefixes.some((p) => p && code.startsWith(p))
}

export interface PullSamplesResult {
  /** 映射为抽凭引擎同款样本，可直接喂给底稿 onSampleFilled({ samples }) */
  samples: SampledVoucher[]
  /** 对应的 sampled_vouchers 记录 id（供 UI 显示/取消挂凭） */
  records: AttachedVoucherRecord[]
}

/**
 * 拉取挂到指定底稿的凭证 → 映射为 SampledVoucher[]。
 *
 * @param accountPrefixes  只取匹配科目前缀的分录行（如货币资金 ['1001','1002','1012']）。
 *                         空数组 = 取凭证的每一条分录行。
 */
export async function pullSamplesForWorkpaper(
  projectId: string,
  year: number,
  workpaperId: string,
  accountPrefixes: string[] = [],
): Promise<PullSamplesResult> {
  const records = await listAttachedVouchers(projectId, year, workpaperId)
  const samples: SampledVoucher[] = []
  for (const rec of records) {
    let lines: any[] = []
    try {
      lines = await fetchVoucherLines(projectId, year, rec.voucher_no)
    } catch {
      lines = []
    }
    // 优先取匹配科目前缀的分录；都不匹配则回退取全部分录
    let picked = lines.filter((l) => lineMatchesAccounts(l, accountPrefixes))
    if (picked.length === 0) picked = lines
    // 没有分录明细（穿透失败）→ 至少造一条占位样本，保留凭证号供审计师补录
    if (picked.length === 0) {
      samples.push(makeSample(rec.voucher_no, '', rec.account_code || '', null, null, null, null))
      continue
    }
    for (const line of picked) {
      samples.push(
        makeSample(
          rec.voucher_no,
          String(line?.voucher_date ?? ''),
          String(line?.account_code ?? rec.account_code ?? ''),
          line?.account_name != null ? String(line.account_name) : null,
          line?.debit_amount != null ? String(line.debit_amount) : null,
          line?.credit_amount != null ? String(line.credit_amount) : null,
          line?.summary != null ? String(line.summary) : null,
        ),
      )
    }
  }
  return { samples, records }
}

function makeSample(
  voucherNo: string,
  voucherDate: string,
  accountCode: string,
  accountName: string | null,
  debitAmount: string | null,
  creditAmount: string | null,
  summary: string | null,
): SampledVoucher {
  return {
    voucherNo,
    voucherDate,
    summary,
    debitAmount,
    creditAmount,
    accountCode,
    accountName,
    counterpartAccount: null,
    voucherType: null,
    accountingPeriod: null,
    checkResult: '',
    abnormal: false,
    remark: '序时账手工挂入',
    selected: true,
    phase: 'final',
    editTrail: [],
  }
}
