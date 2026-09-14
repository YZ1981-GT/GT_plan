/**
 * cutoffSampleAdapter — 截止测试双侧证据统一模型 CutoffSample + 三底稿双向适配器
 *
 * Spec: .kiro/specs/cutoff-test-architecture-convergence/ Wave 3 Task 6
 *
 * 收敛目标（Req2）：useCycleCutoff / useK8Cutoff / useK9Cutoff 三套 CutoffRow 字段命名各异
 * （recordDate/bookDate、amount、documentDate/sourceDate、documentAmount/sourceAmount…），
 * 统一到单一 CutoffSample（显式区分记账侧 book* / 原始单据侧 doc*）。
 *
 * 铁律：
 * - documentAmount 缺失恒 0，禁止自动复制 bookAmount（P0 证据门禁，Req2.3）
 * - 适配器双向映射，往返保真（Req2.5，P7）；K9 无 documentAmount → 恒 0，往返丢弃该字段
 * - 纯函数，无 Vue 依赖，便于 PBT
 */

// ─── canonical 双侧证据模型 ───────────────────────────────────────────────────

export interface CutoffSample {
  /** 记账侧：记账凭证日期 YYYY-MM-DD */
  bookDate: string
  /** 记账侧：账面金额 */
  bookAmount: number
  /** 记账侧：记账凭证号 */
  voucherNo: string
  /** 原始单据侧：原始单据/支出凭单日期（缺失=空串） */
  documentDate: string
  /** 原始单据侧：原始单据金额（缺失=0，禁止自动复制 bookAmount） */
  documentAmount: number
  /** 原始单据侧：原始单据号 */
  documentNo: string
  /** 摘要/业务内容 */
  summary: string
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function str(v: unknown): string {
  return v == null ? '' : String(v)
}

// ─── useCycleCutoff（I2/I6）CutoffRow ⇄ CutoffSample ──────────────────────────
// CutoffRow: recordDate/amount/voucherNo/documentDate/documentAmount/documentNo/description

export function fromCycleRow(row: Record<string, any>): CutoffSample {
  return {
    bookDate: str(row?.recordDate),
    bookAmount: num(row?.amount),
    voucherNo: str(row?.voucherNo),
    documentDate: str(row?.documentDate),
    // 禁止回退 amount：缺失恒 0
    documentAmount: num(row?.documentAmount),
    documentNo: str(row?.documentNo),
    summary: str(row?.description),
  }
}

/** 回写 CycleRow 的证据字段（调用方 merge 到既有行，保留 recordPeriod/belongPeriod 等其它字段） */
export function toCycleRow(s: CutoffSample): Record<string, any> {
  return {
    recordDate: s.bookDate,
    amount: s.bookAmount,
    voucherNo: s.voucherNo,
    documentDate: s.documentDate,
    documentAmount: s.documentAmount,
    documentNo: s.documentNo,
    description: s.summary,
  }
}

// ─── useK8Cutoff（K8-6/7）K8CutoffRow ⇄ CutoffSample ─────────────────────────
// K8CutoffRow: bookDate/amount/voucherNo/sourceDate/sourceAmount/sourceVoucherNo/summary

export function fromK8Row(row: Record<string, any>): CutoffSample {
  return {
    bookDate: str(row?.bookDate),
    bookAmount: num(row?.amount),
    voucherNo: str(row?.voucherNo),
    documentDate: str(row?.sourceDate),
    documentAmount: num(row?.sourceAmount),
    documentNo: str(row?.sourceVoucherNo),
    summary: str(row?.summary ?? row?.businessContent),
  }
}

export function toK8Row(s: CutoffSample): Record<string, any> {
  return {
    bookDate: s.bookDate,
    amount: s.bookAmount,
    voucherNo: s.voucherNo,
    sourceDate: s.documentDate,
    sourceAmount: s.documentAmount,
    sourceVoucherNo: s.documentNo,
    summary: s.summary,
  }
}

// ─── useK9Cutoff（K9-6/7）K9CutoffRow ⇄ CutoffSample ─────────────────────────
// K9CutoffRow: bookDate/amount/voucherNo/sourceDate/sourceVoucherNo/summary（无 sourceAmount）

export function fromK9Row(row: Record<string, any>): CutoffSample {
  return {
    bookDate: str(row?.bookDate),
    bookAmount: num(row?.amount),
    voucherNo: str(row?.voucherNo),
    documentDate: str(row?.sourceDate),
    // K9 无原始单据金额字段 → 恒 0（不回退 amount）
    documentAmount: 0,
    documentNo: str(row?.sourceVoucherNo),
    summary: str(row?.summary),
  }
}

export function toK9Row(s: CutoffSample): Record<string, any> {
  return {
    bookDate: s.bookDate,
    amount: s.bookAmount,
    voucherNo: s.voucherNo,
    sourceDate: s.documentDate,
    sourceVoucherNo: s.documentNo,
    summary: s.summary,
    // K9 无 sourceAmount，不回写
  }
}
