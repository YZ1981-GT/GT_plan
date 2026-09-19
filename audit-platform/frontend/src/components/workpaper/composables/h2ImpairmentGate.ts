/**
 * H2-15/16 减值门禁（纯函数）
 * 需求 12.5：减值迹象 ≥ 2 项时强制完成 H2-16 可收回金额测试。
 */
export const H215_SIGNS_KEY = 'H2-15-impairment-signs'
export const H215_CALC_KEY = 'H2-15-test-rows'
export const H215_CONCLUSION_KEY = 'H2-15-audit-conclusion'
export const H216_GROUPS_KEY = 'H2-16-groups'
export const H216_CONCLUSION_KEY = 'H2-16-audit-conclusion'
export const H216_NOTE_KEY = 'H2-16-audit-note'

const SIGN_THRESHOLD = 2

function _remark(map: Map<string, any>, key: string): string {
  const r = map.get(key)?.remark
  return r == null ? '' : String(r).trim()
}

function _parseJson<T>(raw: string): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

/** CAS8 六项迹象中判定为「是」的数量 */
export function countImpairmentSignYes(responses: Map<string, any>): number {
  const arr = _parseJson<any[]>(_remark(responses, H215_SIGNS_KEY))
  if (!Array.isArray(arr)) return 0
  return arr.filter((s) => s?.exists === '是' || s?.exists === 'Y' || s?.exists === true).length
}

/** 迹象 ≥ 2 须做 H2-16 */
export function needsH216RecoverableTest(responses: Map<string, any>): boolean {
  return countImpairmentSignYes(responses) >= SIGN_THRESHOLD
}

/** H2-16 是否已实质完成（结论或工程组可收回金额已测算） */
export function isH216RecoverableComplete(responses: Map<string, any>): boolean {
  if (_remark(responses, H216_CONCLUSION_KEY)) return true

  const groups = _parseJson<any[]>(_remark(responses, H216_GROUPS_KEY))
  if (Array.isArray(groups) && groups.some((g) => {
    const fv = Number(g?.fairValueNet ?? g?.fairValue ?? 0)
    const pv = Number(g?.pvCashFlows ?? g?.presentValue ?? 0)
    const rec = Number(g?.recoverableAmount ?? 0)
    return rec > 0 || fv > 0 || pv > 0
  })) {
    return true
  }

  // 回写至 H2-15 测算行：有迹象行均已填可收回/公允/现值
  const calcs = _parseJson<any[]>(_remark(responses, H215_CALC_KEY))
  if (Array.isArray(calcs)) {
    const signed = calcs.filter((r) => r?.hasSign === '是')
    if (
      signed.length > 0
      && signed.every((r) => {
        const fv = Number(r?.fairValueNet ?? 0)
        const pv = Number(r?.pvCashFlows ?? 0)
        const rec = Number(r?.recoverableAmount ?? 0)
        return rec > 0 || fv > 0 || pv > 0
      })
    ) {
      return true
    }
  }

  return false
}

/** 门禁是否阻断（须做 H2-16 且尚未完成） */
export function isImpairmentGateBlocked(responses: Map<string, any>): boolean {
  return needsH216RecoverableTest(responses) && !isH216RecoverableComplete(responses)
}

export function impairmentGateBlockReason(responses: Map<string, any>): string | null {
  if (!isImpairmentGateBlocked(responses)) return null
  const n = countImpairmentSignYes(responses)
  return `减值迹象 ${n} 项（≥${SIGN_THRESHOLD}）：须完成 H2-16 可收回金额测试后方可出具无保留减值结论`
}

/**
 * 「清洁」结论：暗示无需进一步测试 / 未见异常。
 * 门禁阻断时禁止保存此类结论。
 */
export function isCleanImpairmentConclusion(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  if (/须完成\s*H2-16|尚未完成\s*H2-16|范围受限|无法获取充分|不可确认|待完成\s*H2-16/.test(t)) {
    return false
  }
  return /未见异常|公允反映|无需进行减值|本期无需.*减值|减值准备计提充分(?!.*关注)/.test(t)
}

/** 门禁阻断时的标准受限结论草稿 */
export function buildBlockedImpairmentConclusion(signYesCount: number): string {
  return (
    `经按 CAS8 检查，主体层面识别减值迹象 ${signYesCount} 项（≥${SIGN_THRESHOLD}）。`
    + '可收回金额测试（H2-16）尚未完成，审计范围受到限制，本期不可确认在建工程减值准备已充分计提。'
    + '请完成 H2-16 并回写 H2-15 后更新本结论。'
  )
}
