/**
 * migrateDformToConfirmation — d-form-table → confirmation-v1 软升级
 *
 * 检测：无 _format，且含 rows（d-form 形态）
 * 策略：快照 _legacy_dform，尽力映射常见列名；无法识别则建空行骨架
 */
import type { ConfirmationPayload, ConfirmationRow } from '../confirmationTypes'

const INDEX_KEYS = ['函证索引号', '索引号', '编号', 'confirm_index', '索引']
const NAME_KEYS = ['被询证单位', '被函证单位', '单位名称', '客户名称', '对方单位', '银行名称', 'entity_name', 'counterparty']
const AMOUNT_KEYS = ['函证金额', '账面金额', '发函金额', 'amount', 'book_amount', '余额']
const REPLY_KEYS = ['回函金额', '确认金额', 'reply_amount', 'confirmed_amount']
const TYPE_KEYS = ['科目', '科目大类', 'account_type', '类型']
const STATUS_KEYS = ['相符情况', '回函状态', 'match_status', '状态']
const METHOD_KEYS = ['函证方式', 'confirmation_method']

function pick(raw: Record<string, any>, keys: string[]): any {
  for (const k of keys) {
    if (raw[k] != null && String(raw[k]).trim() !== '') return raw[k]
  }
  // 模糊：键名包含关键字
  for (const [rk, rv] of Object.entries(raw)) {
    if (rv == null || String(rv).trim() === '') continue
    for (const k of keys) {
      if (rk.includes(k) || k.includes(rk)) return rv
    }
  }
  return undefined
}

export function isLegacyDformPayload(data: any): boolean {
  if (!data || typeof data !== 'object') return false
  if (data._format === 'confirmation-v1') return false
  if (data._format) return false // 其他现代格式
  return Array.isArray(data.rows) && data.rows.length >= 0
}

export function mapDformRowToConfirmation(raw: any, seq: number): ConfirmationRow {
  const src = raw && typeof raw === 'object' ? raw : {}
  const matchRaw = pick(src, STATUS_KEYS)
  let match_status: string | undefined
  if (matchRaw != null) {
    const s = String(matchRaw)
    if (/相符|一致|matching/i.test(s)) match_status = '相符'
    else if (/不符|差异|discrep/i.test(s)) match_status = '不符'
    else if (/未回|noreply|pending/i.test(s)) match_status = '未回函'
    else match_status = s
  }
  const amount = Number(pick(src, AMOUNT_KEYS))
  const reply = Number(pick(src, REPLY_KEYS))
  return {
    seq,
    confirm_index: pick(src, INDEX_KEYS) != null ? String(pick(src, INDEX_KEYS)).trim() : undefined,
    entity_name: pick(src, NAME_KEYS) != null ? String(pick(src, NAME_KEYS)).trim() : undefined,
    account_type: pick(src, TYPE_KEYS) != null ? String(pick(src, TYPE_KEYS)).trim() : '银行存款',
    amount: Number.isFinite(amount) ? amount : undefined,
    reply_amount: Number.isFinite(reply) ? reply : undefined,
    match_status,
    confirmation_method: pick(src, METHOD_KEYS) != null ? String(pick(src, METHOD_KEYS)) : undefined,
    is_replied: match_status === '相符' || match_status === '不符' ? true : undefined,
    _source: 'migrated',
  }
}

/**
 * 将 d-form payload 转为 confirmation-v1，并保留 _legacy_dform 快照
 */
export function migrateDformToConfirmationV1(data: any): ConfirmationPayload {
  const legacyRows: any[] = Array.isArray(data?.rows) ? data.rows : []
  const rows = legacyRows
    .map((r, i) => mapDformRowToConfirmation(r, i + 1))
    .filter((r) => r.entity_name || r.confirm_index || (r.amount != null && r.amount !== 0))

  return {
    _format: 'confirmation-v1',
    rows,
    sampling: {},
    notes: {
      note_general: '由旧版 d-form-table 软升级生成，请核对索引号/金额/回函状态。',
    },
    conclusion: {},
    _legacy_dform: data,
  } as ConfirmationPayload & { _legacy_dform?: any }
}
