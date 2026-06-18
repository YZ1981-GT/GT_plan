/**
 * KAM (Key Audit Matters / 关键审计事项) JSON schema types.
 *
 * 存储于 `checklist_responses.remark` 字段（JSON 字符串化）。
 * item_id 模式：`A17-2-1-KAM-001` ~ `A17-2-1-KAM-NNN`
 */

/** KAM 措辞审核状态 */
export type KamWordingReviewStatus = 'pending' | 'done' | 'na'

/** KAM remark JSON schema（前后端双校验） */
export interface KamRemarkSchema {
  /** 情况描述 */
  situation: string
  /** 确定为 KAM 的原因 */
  reason: string
  /** 审计应对 */
  response: string
  /** 引用底稿 */
  refs: string
  /** 措辞审核状态 */
  wording_review: KamWordingReviewStatus
  /** 治理层确认 */
  governance_confirmed: boolean
}

/** 单条 KAM 数据（对应 checklist_responses 一行） */
export interface KamEntry {
  /** item_id: A17-2-1-KAM-001 ~ NNN */
  item_id: string
  /** KAM 标题/风险领域 (conclusion 字段) */
  title: string
  /** 引用底稿索引 (wp_ref 字段) */
  wp_ref: string
  /** 结构化 remark 数据 */
  remark: KamRemarkSchema
}

/** KAM remark 默认值工厂 */
export function createDefaultKamRemark(): KamRemarkSchema {
  return {
    situation: '',
    reason: '',
    response: '',
    refs: '',
    wording_review: 'pending',
    governance_confirmed: false,
  }
}

/** 校验 remark JSON 是否符合 schema */
export function validateKamRemark(data: unknown): data is KamRemarkSchema {
  if (!data || typeof data !== 'object') return false
  const obj = data as Record<string, unknown>
  return (
    typeof obj.situation === 'string' &&
    typeof obj.reason === 'string' &&
    typeof obj.response === 'string' &&
    typeof obj.refs === 'string' &&
    ['pending', 'done', 'na'].includes(obj.wording_review as string) &&
    typeof obj.governance_confirmed === 'boolean'
  )
}
