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
  /** V166：凭证日期。null = 历史行未记日期，回拉时退化为按年度匹配（可能命中同号别张凭证）。 */
  voucher_date: string | null
  account_code: string | null
  sampling_record_id: string | null
  working_paper_id: string | null
  /** 非空 = 抽凭引擎批次登记；null = 手工挂凭。 */
  batch_id?: string | null
  /** 后端派生的来源标签：'manual' | 'sampling_engine'。 */
  source?: string | null
  note: string | null
  sampled_at: string | null
}

/** 挂凭到底稿请求 */
export interface AttachVoucherPayload {
  year: number
  voucherNo: string
  /** 凭证日期 YYYY-MM-DD。🔴 凭证号跨日重复，强烈建议传入以精确定位单张凭证。 */
  voucherDate?: string | null
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
    voucher_date: payload.voucherDate ?? null,
    account_code: payload.accountCode ?? null,
    working_paper_id: payload.workpaperId ?? null,
    source: payload.source ?? 'ledger',
    note: payload.note ?? null,
  })
  return unwrap(res)
}

/**
 * 拉取抽样清单（可按目标底稿过滤）。
 *
 * @param manualOnly 只取手工挂凭（batch_id IS NULL），排除抽凭引擎批次登记。
 *                   底稿「从序时账挂入导入」应传 true —— 否则会把引擎批次的凭证
 *                   也标成「序时账手工挂入」，来源标签失真。
 */
export async function listAttachedVouchers(
  projectId: string,
  year: number,
  workpaperId?: string,
  manualOnly = false,
): Promise<AttachedVoucherRecord[]> {
  const params: Record<string, unknown> = { year }
  if (workpaperId) params.working_paper_id = workpaperId
  if (manualOnly) params.manual_only = true
  const res = await http.get(P_ledger.sampledVouchers(projectId), { params })
  const data = unwrap<{ items?: AttachedVoucherRecord[] }>(res)
  return Array.isArray(data?.items) ? data.items : []
}

/** 取消挂凭（软删一条抽样记录） */
export async function removeAttachedVoucher(projectId: string, sampledId: string): Promise<void> {
  await http.delete(P_ledger.sampledVoucherDelete(projectId, sampledId))
}

/**
 * 单张凭证的完整分录（穿透）。
 *
 * 🔴 必须传 `voucherDate`：凭证号在真实数据中**不唯一** —— 实测 8 个项目里 7 个
 * 跨月/跨日重复，单个号最多对应 83 个不同日期。只传 year 时后端返回**全年所有同号
 * 凭证**的分录（实测某项目 0075 号返回 66 张凭证共 5918 行，借方虚增到 3.7 亿），
 * 回填到底稿就是错的样本。带上日期后 `(voucher_date, voucher_no)` 唯一定位一张凭证。
 */
async function fetchVoucherLines(
  projectId: string,
  year: number,
  voucherNo: string,
  voucherDate?: string | null,
): Promise<any[]> {
  const params: Record<string, unknown> = { year }
  if (voucherDate) params.voucher_date = voucherDate
  const res = await http.get(P_ledger.voucher(projectId, voucherNo), { params })
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

/** 挂错底稿的凭证（三级筛选全空 ⇒ 不产样本，汇总提示用） */
export interface MisattachedVoucher {
  voucherNo: string
  /** 挂凭时记录的日期（无则空串） */
  voucherDate: string
  /** 该凭证实际包含的科目（去重，便于用户判断该挂到哪张底稿） */
  actualAccounts: string[]
  /** 该 sampled_vouchers 记录 id（供 UI 取消挂凭） */
  recordId: string
}

export interface PullSamplesResult {
  /** 映射为抽凭引擎同款样本，可直接喂给底稿 onSampleFilled({ samples }) */
  samples: SampledVoucher[]
  /** 对应的 sampled_vouchers 记录 id（供 UI 显示/取消挂凭） */
  records: AttachedVoucherRecord[]
  /**
   * 挂错底稿的凭证清单（**业务错挂**，非技术失败）。
   *
   * 🔴 调用方应把它呈现给用户（凭证号 + 实际科目），建议重新挂到正确底稿。
   * 与「穿透失败」区分：后者仍会产出占位样本（见 `samples`），前者一行不产。
   */
  misattached: MisattachedVoucher[]
}

/**
 * 拉取挂到指定底稿的凭证 → 映射为 SampledVoucher[]。
 *
 * ## 三级筛选优先级（spec R3.1）
 *
 * ```
 * ① 命中底稿科目前缀（accountPrefixes）        → 正常路径，回填该科目分录
 * ② 命中挂凭意图（rec.account_code）           → 回填并在 remark 标注待核对
 * ③ 两者皆空但凭证有分录                        → 判「挂错底稿」，不产样本、进 misattached
 * ─ 凭证无分录（穿透失败/网络错误）              → 占位样本，保留凭证号供手工补录
 * ```
 *
 * 🔴 改造前这里是 `if (picked.length === 0) picked = lines` —— 筛不到本底稿科目就
 * **回退取全部分录**。后果：用户挂错底稿时，整张凭证所有科目的分录（可能十几条、
 * 跨多个循环）被静默灌进底稿，审计师看不出这些行不属于本表。
 *
 * 🔴 第 ② 级是新增的：`rec.account_code` 是用户挂凭时**所在行的科目**，表达
 * 「我关注这张凭证的哪个科目」。改造前它只用于兜底显示、不参与筛选，
 * 于是用户在「1002 银行存款」那行挂的凭证，回拉时若底稿前缀不匹配就整张灌回。
 *
 * @param accountPrefixes 底稿科目前缀，应来自对应 `*AccountScope.ts`（spec R4.1，
 *                        禁组件内字面量）。空数组 = 不按科目筛（取全部分录）。
 */
export async function pullSamplesForWorkpaper(
  projectId: string,
  year: number,
  workpaperId: string,
  accountPrefixes: string[] = [],
): Promise<PullSamplesResult> {
  // manualOnly=true：只拉手工挂入的，不把抽凭引擎批次的凭证冒充成「序时账手工挂入」
  const records = await listAttachedVouchers(projectId, year, workpaperId, true)
  const samples: SampledVoucher[] = []
  const misattached: MisattachedVoucher[] = []

  for (const rec of records) {
    let lines: any[] = []
    let fetchFailed = false
    try {
      // 带上挂凭时记录的日期 → 精确定位单张凭证（无日期的历史行退化为按年匹配）
      lines = await fetchVoucherLines(projectId, year, rec.voucher_no, rec.voucher_date)
    } catch {
      lines = []
      fetchFailed = true
    }

    // ── 穿透失败（技术失败）：保留占位样本供手工补录，与业务错挂区分（R3.6）──
    if (lines.length === 0) {
      samples.push(makeSample(
        rec.voucher_no, rec.voucher_date || '', rec.account_code || '',
        null, null, null,
        fetchFailed ? '凭证分录穿透失败，请手工补录' : null,
        rec.voucher_date == null,
      ))
      continue
    }

    // ── ① 底稿科目前缀 ──
    let picked = lines.filter((l) => lineMatchesAccounts(l, accountPrefixes))
    let byIntent = false

    // ── ② 挂凭意图（用户挂凭时所在行的科目）──
    if (picked.length === 0 && rec.account_code) {
      picked = lines.filter((l) => lineMatchesAccounts(l, [rec.account_code as string]))
      byIntent = picked.length > 0
    }

    // ── ③ 挂错底稿：不产样本，进 misattached（R3.4 —— 绝不回退取全部分录）──
    if (picked.length === 0) {
      const actual: string[] = []
      for (const l of lines) {
        const code = String(l?.account_code ?? '').trim()
        if (code && !actual.includes(code)) actual.push(code)
      }
      misattached.push({
        voucherNo: rec.voucher_no,
        voucherDate: rec.voucher_date || '',
        actualAccounts: actual,
        recordId: rec.id,
      })
      continue
    }

    for (const line of picked) {
      samples.push(
        makeSample(
          rec.voucher_no,
          String(line?.voucher_date ?? rec.voucher_date ?? ''),
          String(line?.account_code ?? rec.account_code ?? ''),
          line?.account_name != null ? String(line.account_name) : null,
          line?.debit_amount != null ? String(line.debit_amount) : null,
          line?.credit_amount != null ? String(line.credit_amount) : null,
          line?.summary != null ? String(line.summary) : null,
          // 挂凭记录没存日期 ⇒ 本次是按年度匹配拉回的，可能混入同号别张凭证
          rec.voucher_date == null,
          // ② 级命中 ⇒ 未落在本底稿科目范围内，标注待核对（R3.3）
          byIntent ? (rec.account_code as string) : null,
        ),
      )
    }
  }
  return { samples, records, misattached }
}

function makeSample(
  voucherNo: string,
  voucherDate: string,
  accountCode: string,
  accountName: string | null,
  debitAmount: string | null,
  creditAmount: string | null,
  summary: string | null,
  /** true = 挂凭记录无日期，本条按年度匹配拉回，可能混入同号别张凭证 */
  dateAmbiguous = false,
  /**
   * 非 null = 本条是按**挂凭意图科目**（② 级）取到的，未落在本底稿科目范围内。
   * 值为挂凭时用户所在行的科目码，写进 remark 供审计师核对（spec R3.3）。
   */
  intentAccountCode: string | null = null,
): SampledVoucher {
  /**
   * 🔴 两类歧义都要如实标注，且可叠加 —— 静默会让审计师以为这些行是正常取到的。
   * - 日期歧义：凭证号跨日重复（实测单号最多对应 83 个日期），无日期只能按年匹配
   * - 科目歧义：未命中本底稿科目，是按挂凭意图取的，可能挂错了底稿
   */
  const notes: string[] = []
  if (dateAmbiguous) notes.push('挂凭时未记凭证日期，同号凭证可能跨日重复')
  if (intentAccountCode) {
    notes.push(`按挂凭时选定科目 ${intentAccountCode} 取分录，未命中本底稿科目范围`)
  }
  const remark = notes.length
    ? `序时账手工挂入（${notes.join('；')}，请核对）`
    : '序时账手工挂入'

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
    remark,
    selected: true,
    phase: 'final',
    editTrail: [],
  }
}
