/**
 * useAttachedVouchers.ts — 序时账「挂凭到底稿」↔ 底稿凭证检查联动（可复用）
 *
 * 两个方向：
 *  1. 序时账侧（LedgerPenetration）手工挑选凭证 → 挂凭弹窗走 `attachVouchersBatch`（多张凭证 × 多张底稿一次挂，
 *     逐条返回新挂 / 已挂 / 失败原因）；凭证层「抽中本凭证」走 `attachVoucher`（单张，可不指定底稿）。两者都记到
 *     sampled_vouchers 的手工侧（batch_id 为空）：凭证按当前账套定位成一张（凭证键），阶段取项目当前阶段，
 *     已挂的再挂不改阶段。`queryVoucherLinks`：凭证键 → 已挂 / 已抽于哪些底稿（序时账明细层与凭证层的标签）。
 *  2. 底稿凭证检查侧（如 E1-23 收支检查）→ `pullSamplesForWorkpaper` 拉取挂到本底稿的凭证，逐张按凭证键
 *     取回完整分录，映射为抽凭引擎同款 `SampledVoucher[]`，交给宿主的共享回填函数
 *     （`useVoucherCheckFill().onAttachImported`：与抽凭引擎回填同一口径，按分录指纹去重、多科目按配对展开）。
 *
 * 不新造抽样算法、不改抽凭引擎。端点：sample-voucher / sample-vouchers/batch / voucher-links/query /
 * sampled-vouchers / ledger/voucher/{no}。
 */
import http from '@/utils/http'
import { ledger as P_ledger } from '@/services/apiPaths'
import {
  voucherKeyAmbiguityOf, voucherLabel, type VoucherKeyAmbiguity, type VoucherKeyCandidate,
} from '@/utils/voucherIdentity'
import { counterpartLabelOf, type SamplePairing } from './shared/voucherCheckFill'
import type { SampledVoucher } from './useSamplingAlgorithms'

/** 后端 sampled_vouchers 行 */
export interface AttachedVoucherRecord {
  id: string
  voucher_no: string
  /** V166：凭证日期。null = 历史行未记日期，回拉时退化为按年度匹配（可能命中同号别张凭证）。 */
  voucher_date: string | null
  /** V210：凭证字（'' = 凭证字为空）。null / 缺省 = 旧行未记，同日同号多凭证字时回拉拿不到唯一一张。 */
  voucher_type?: string | null
  /** V210：主体编码 */
  company_code?: string | null
  /** 凭证键（有日期的记录才有）；回拉按它定位单张凭证 */
  voucher_key?: string | null
  /** 挂凭时的审计阶段 preliminary / final；null = 旧行未标 */
  phase?: string | null
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
  /** 凭证字（'' = 凭证字为空）；null / 缺省 = 不知道，由后端在当前账套里补全，命中多张时 409 */
  voucherType?: string | null
  companyCode?: string | null
  /** 审计阶段；缺省由后端按项目阶段取 */
  phase?: 'preliminary' | 'final'
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
 * 挂凭（单张）：把一张凭证记录到抽样清单，可关联一张目标底稿（凭证层「抽中本凭证」不指定底稿）。
 * 同一凭证（凭证键）挂同一底稿只有一条：再挂 = 更新说明与意图科目，阶段保持当初挂凭时的；挂到不同底稿各一条。
 * 挂多张底稿用 {@link attachVouchersBatch}。后端按当前账套定位凭证：命中多张 409 VOUCHER_KEY_AMBIGUOUS（带候选），
 * 找不到 404 VOUCHER_NOT_FOUND —— 原样抛出，由调用方把原因告诉用户。`_silent`：不弹全局提示。
 */
export async function attachVoucher(
  projectId: string,
  payload: AttachVoucherPayload,
): Promise<{ id: string; voucher_no: string; voucher_type?: string | null; status: string }> {
  const body: Record<string, unknown> = {
    year: payload.year,
    voucher_no: payload.voucherNo,
    voucher_date: payload.voucherDate ?? null,
    voucher_type: payload.voucherType ?? null,
    company_code: payload.companyCode ?? null,
    account_code: payload.accountCode ?? null,
    working_paper_id: payload.workpaperId ?? null,
    source: payload.source ?? 'ledger',
    note: payload.note ?? null,
  }
  if (payload.phase) body.phase = payload.phase
  const res = await http.post(P_ledger.sampleVoucher(projectId), body, { _silent: true } as any)
  return unwrap(res)
}

/** 挂凭失败的原因（给用户看的中文）：多张凭证 / 账套里没有 / 其他 */
export function attachFailureReason(err: unknown): string {
  const ambiguity = voucherKeyAmbiguityOf(err)
  if (ambiguity) {
    const names = ambiguity.candidates.slice(0, 3).map(c => `${c.voucher_date} ${voucherLabel(c.voucher_type, c.voucher_no)}`)
    return `对应多张凭证（${names.join('、')}${ambiguity.candidates.length > 3 ? ' 等' : ''}），请在凭证层选定一张再挂`
  }
  const res = (err as { response?: { status?: number; data?: { detail?: unknown } } } | null)?.response
  if (res?.status === 404) return '当前账套里没有这张凭证（可能账套已重导）'
  if (res?.status === 403) return '没有本项目的编辑权限'
  const detail = res?.data?.detail as { message?: unknown } | undefined
  if (res?.status === 422 && typeof detail?.message === 'string') return detail.message
  return '挂凭失败，请稍后重试'
}

/** 一次最多挂这么多个「凭证 × 底稿」组合；已挂查询一次最多这么多个凭证键（与后端 voucher_links 一致） */
export const ATTACH_BATCH_MAX_PAIRS = 500
export const VOUCHER_LINKS_MAX_KEYS = 500

export interface AttachBatchVoucher {
  voucherNo: string
  voucherDate?: string | null
  /** '' = 凭证字为空；null / 缺省 = 不知道（后端补全，命中多张时这一条失败并列候选） */
  voucherType?: string | null
  companyCode?: string | null
  /** 挂凭意图科目（用户所在行的科目），回拉时第 ② 级筛选用 */
  accountCode?: string | null
}

/** 批量挂凭逐条状态：新挂（含软删后复活）/ 之前已挂（原行不动）/ 没挂上 */
export const ATTACH_STATUS = { CREATED: 'created', EXISTED: 'existed', FAILED: 'failed' } as const

/** 批量挂凭的一条结果：一个「凭证 × 底稿」 */
export interface AttachBatchResult {
  voucher_no: string
  voucher_date: string | null
  voucher_type: string | null
  /** 定位成功才有 */
  voucher_key: string | null
  working_paper_id: string
  /** 底稿不在本项目时为 null（不透出别的项目底稿编码） */
  wp_code: string | null
  status: (typeof ATTACH_STATUS)[keyof typeof ATTACH_STATUS]
  id?: string
  /** 已挂（existed）的是当初挂凭时的阶段 */
  phase?: string | null
  error_code?: string
  reason?: string
  /** 凭证对应多张时的前几张候选 */
  candidates?: VoucherKeyCandidate[]
}

export interface AttachBatchResponse {
  results: AttachBatchResult[]
  created: number
  existed: number
  failed: number
  phase?: string
}

/**
 * 批量挂凭：多张凭证 × 多张底稿一次提交，逐条返回新挂（created）/ 已挂（existed，原行不动）/ 失败 + 原因
 * （凭证对应多张、账套里没有、底稿不在本项目、数据库拒绝）。阶段由后端取项目当前阶段，不传。
 * 整单失败（无编辑权限 403、组合超过 500 个 422）原样抛出，用 {@link attachFailureReason} 取原因。
 */
export async function attachVouchersBatch(
  projectId: string,
  payload: { year: number; vouchers: AttachBatchVoucher[]; workpaperIds: string[]; note?: string | null; source?: string },
): Promise<AttachBatchResponse> {
  const body = {
    year: payload.year,
    vouchers: payload.vouchers.map(v => ({
      voucher_no: v.voucherNo,
      voucher_date: v.voucherDate ?? null,
      voucher_type: v.voucherType ?? null,
      company_code: v.companyCode ?? null,
      account_code: v.accountCode ?? null,
    })),
    working_paper_ids: payload.workpaperIds,
    note: payload.note ?? null,
    source: payload.source ?? 'ledger',
  }
  const res = await http.post(P_ledger.sampleVouchersBatch(projectId), body, { _silent: true } as any)
  const data = unwrap<AttachBatchResponse>(res)
  return { ...data, results: Array.isArray(data?.results) ? data.results : [] }
}

/** 已挂 / 已抽标识的一条：凭证挂到（或被抽到）某张底稿，按来源 × 阶段合并 */
export interface VoucherLink {
  working_paper_id: string | null
  wp_code: string | null
  wp_name: string | null
  /** 记录指向的底稿已删除或不在本项目 */
  wp_missing: boolean
  /** manual = 序时账手工挂凭；sampling_engine = 抽凭引擎登记 */
  source: 'manual' | 'sampling_engine'
  phase: 'preliminary' | 'final' | null
  /** 同一底稿被几个抽凭批次抽到（手工挂凭恒为 1） */
  count: number
  /** 旧登记没记凭证字或主体：同日同号的另一张凭证也会显示它 */
  legacy: boolean
}

/**
 * 凭证键 → 已挂 / 已抽于哪些底稿（一次最多 500 个键；超过请调用方分段）。没有记录的键不在结果里。
 * 只读查询走 POST（键里有主体名称，500 个键放进查询串会超长）；`_dedupe: false`：分段查询互不取消。
 */
export async function queryVoucherLinks(
  projectId: string,
  year: number,
  keys: string[],
): Promise<Record<string, VoucherLink[]>> {
  if (keys.length === 0) return {}
  const res = await http.post(P_ledger.voucherLinksQuery(projectId), { year, keys }, { _silent: true, _dedupe: false } as any)
  const data = unwrap<{ links?: Record<string, VoucherLink[]> }>(res)
  return data?.links && typeof data.links === 'object' ? data.links : {}
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
  /** 审计年度；项目没填为 null ⇒ 不发请求、按「没有挂凭」处理（只读计数 / 角标） */
  year: number | null,
  workpaperId?: string,
  manualOnly = false,
): Promise<AttachedVoucherRecord[]> {
  if (year == null) return []
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
 * 单张凭证的完整分录（穿透），按凭证键定位：日期 + 凭证字 + 号。
 *
 * 🔴 凭证号单独不唯一（单号最多对应 83 个日期），同日同号也不唯一（四川物流 2025-01-07 的
 * FY-0003 与 ZZ-0003）。后端命中多张凭证时回 409 VOUCHER_KEY_AMBIGUOUS + 候选、不合并分录，
 * 这里原样抛出，由调用方处理（以前只传号会拿回全年同号凭证的分录，借方虚增到 3.7 亿）。
 * `_silent`：逐张凭证失败不弹全局提示，调用方把原因写进占位样本。
 */
export async function fetchVoucherLines(
  projectId: string,
  year: number,
  voucherNo: string,
  voucherDate?: string | null,
  voucherType?: string | null,
  /** 主体编码：一套账两个主体同日同号同凭证字时必带；空 = 不限 */
  companyCode?: string | null,
): Promise<any[]> {
  const params: Record<string, unknown> = { year }
  if (voucherDate) params.voucher_date = voucherDate
  if (voucherType != null) params.voucher_type = voucherType
  if (companyCode) params.company_code = companyCode
  const res = await http.get(P_ledger.voucher(projectId, voucherNo), { params, _silent: true } as any)
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
    let ambiguity: VoucherKeyAmbiguity | null = null
    try {
      // 带上挂凭时记录的日期、凭证字与主体 → 定位单张凭证（旧行缺这几列时可能命中多张，后端回 409）
      lines = await fetchVoucherLines(projectId, year, rec.voucher_no, rec.voucher_date, rec.voucher_type, rec.company_code)
    } catch (e) {
      lines = []
      ambiguity = voucherKeyAmbiguityOf(e)
      fetchFailed = !ambiguity
    }

    // ── 穿透失败（技术失败）或命中多张凭证：保留占位样本，不把多张凭证的分录并进来（R3.6）──
    if (lines.length === 0) {
      samples.push(makeSample(
        rec.voucher_no, rec.voucher_date || '', rec.account_code || '',
        null, null, null,
        ambiguity ? ambiguousVoucherNote(ambiguity) : fetchFailed ? '凭证分录穿透失败，请手工补录' : null,
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
      // 对方科目取后端配对结果（voucher_pairing，需求 3）：配上的填科目，配不上的「多科目」，不在前端按借贷分桶推断
      const cp = counterpartLabelOf(line?.pairing) ?? { code: null, name: null }
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
          cp.code,
          cp.name,
          lines.map(l => ({
            account_code: String(l?.account_code ?? '').trim(),
            account_name: String(l?.account_name ?? '').trim(),
            debit_amount: l?.debit_amount != null ? String(l.debit_amount) : null,
            credit_amount: l?.credit_amount != null ? String(l.credit_amount) : null,
            summary: String(l?.summary ?? ''),
          })),
          line?.voucher_type != null ? String(line.voucher_type) : null,
          // 后端给每行分录补的凭证键与分录指纹：宿主据此去重，账套重导后仍认得同一笔
          line?.voucher_key ?? rec.voucher_key ?? null,
          line?.line_fp ?? null,
          line?.pairing ?? null,
        ),
      )
    }
  }
  return { samples, records, misattached }
}

/** 挂凭记录对应多张凭证（旧行缺日期或凭证字）：列出是哪几张，提示重新挂凭，不猜是哪一张。 */
function ambiguousVoucherNote(a: VoucherKeyAmbiguity): string {
  const names = a.candidates.slice(0, 5).map(c => `${c.voucher_date} ${voucherLabel(c.voucher_type, c.voucher_no)}`)
  const more = a.candidates.length > 5 || a.truncated ? ' 等' : ''
  return `该凭证号对应多张凭证（${names.join('、')}${more}），挂凭时未记凭证字或日期，请在序时账重新挂凭后再导入`
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
  /** 推断的对方科目代码 */
  counterpartAccount: string | null = null,
  /** 推断的对方科目名称 */
  counterpartAccountName: string | null = null,
  /** 完整凭证分录明细 */
  voucherEntries: SampledVoucher['voucherEntries'] = [],
  /** 凭证字（分录行上带的；未知为 null） */
  voucherType: string | null = null,
  /** 凭证键 / 分录指纹（后端穿透给的；占位样本只有挂凭记录的凭证键） */
  voucherKey: string | null = null,
  lineFp: string | null = null,
  /** 后端配对结果（穿透每行带）：回填按它展开或标「多科目」 */
  pairing: SamplePairing | null = null,
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
    voucherKey,
    lineFp,
    pairing,
    voucherNo,
    voucherDate,
    summary,
    debitAmount,
    creditAmount,
    accountCode,
    accountName,
    counterpartAccount,
    counterpartAccountName,
    isMultiAccount: counterpartAccount === '多科目',
    voucherEntries,
    voucherType,
    accountingPeriod: null,
    checkResult: '',
    abnormal: false,
    remark,
    selected: true,
    phase: 'final',
    editTrail: [],
  }
}
