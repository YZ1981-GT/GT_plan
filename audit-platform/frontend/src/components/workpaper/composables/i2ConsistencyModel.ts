/**
 * i2ConsistencyModel — I2 跨表一致性仪表盘纯函数
 * 覆盖：I2-4 政策 / I2-6 资本化 / I2-15·16 减值 关键检查点
 */

function _safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (remark != null) return _safeParseArray(remark)
  }
  return []
}

function _readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export type I2ConsistencyLevel = 'ok' | 'warn' | 'error' | 'info'

export interface I2ConsistencyItem {
  id: string
  area: string
  level: I2ConsistencyLevel
  message: string
  sheetHint?: string
}

export interface I2ConsistencyDashboard {
  items: I2ConsistencyItem[]
  errorCount: number
  warnCount: number
  okCount: number
}

/** 从 allResponses Map 构建跨表一致性项 */
export function buildI2ConsistencyDashboard(map: Map<string, any> | undefined | null): I2ConsistencyDashboard {
  const items: I2ConsistencyItem[] = []
  if (!map || map.size === 0) {
    return { items: [], errorCount: 0, warnCount: 0, okCount: 0 }
  }

  // I2-4 政策
  const policyFilled = [...map.keys()].some((k) => k.startsWith('I2-4-') && _hasValue(map.get(k)))
  items.push(policyFilled
    ? { id: 'policy', area: 'I2-4 政策', level: 'ok', message: '会计政策检查已有填报', sheetHint: 'I2-4' }
    : { id: 'policy', area: 'I2-4 政策', level: 'warn', message: '会计政策检查尚未填报', sheetHint: 'I2-4' })

  // I2-6 资本化
  const i26Rows = _safeParseArray(map.get('I2-6-rows'))
  if (!i26Rows.length) {
    const legacy = map.get('I2-6-capitalization')
    if (legacy) {
      items.push({ id: 'cap-legacy', area: 'I2-6 资本化', level: 'info', message: '存在旧版资本化数据，建议迁移为项目行表', sheetHint: 'I2-6' })
    } else {
      items.push({ id: 'cap-empty', area: 'I2-6 资本化', level: 'warn', message: '尚未评价研发项目资本化五条件', sheetHint: 'I2-6' })
    }
  } else {
    let gateErr = 0
    let pending = 0
    let met = 0
    for (const r of i26Rows) {
      const conds = Array.isArray(r?.conditions) ? r.conditions : []
      const allYes = [1, 2, 3, 4, 5].every((id) => {
        const c = conds.find((x: any) => Number(x?.id) === id)
        return c?.result === 'yes'
      })
      if (allYes) met++
      else if (conds.some((c: any) => c?.result === 'yes' || c?.result === 'no')) { /* evaluated incomplete */ }
      else pending++
      const hasCapAmt = _num(r?.recognizedIaAmount) > 0.01
        || (!!_readText(r?.capStartDate) && _num(r?.developmentAmount) > 0.01)
      if (hasCapAmt && !allYes) gateErr++
    }
    if (gateErr > 0) {
      items.push({
        id: 'cap-gate',
        area: 'I2-6 资本化',
        level: 'error',
        message: `${gateErr} 项已填资本化金额/时点但五条件未齐`,
        sheetHint: 'I2-6',
      })
    } else if (pending === i26Rows.length) {
      items.push({
        id: 'cap-pending',
        area: 'I2-6 资本化',
        level: 'warn',
        message: `${i26Rows.length} 个项目待评价五条件`,
        sheetHint: 'I2-6',
      })
    } else {
      items.push({
        id: 'cap-ok',
        area: 'I2-6 资本化',
        level: 'ok',
        message: `已评价 ${i26Rows.length} 项，可资本化 ${met} 项`,
        sheetHint: 'I2-6',
      })
    }
  }

  // I2-15 / I2-16 减值
  const i15 = _safeParseArray(map.get('I2-15-rows'))
  const i16 = _safeParseArray(map.get('I2-16-dcf-params'))
  const needTest = i15.filter((r) => r?.needTest || r?.hasIndication === 'Y')
  if (!i15.length) {
    items.push({ id: 'imp-empty', area: 'I2-15/16 减值', level: 'info', message: '尚未开展减值迹象评估', sheetHint: 'I2-15' })
  } else if (needTest.length === 0) {
    items.push({ id: 'imp-noneed', area: 'I2-15/16 减值', level: 'ok', message: '无项目须测试可收回金额', sheetHint: 'I2-15' })
  } else {
    const i16Names = new Set(i16.map((r) => String(r?.name || '').trim()).filter(Boolean))
    let missing = 0
    let stale = 0
    for (const r of needTest) {
      const name = String(r?.name || '').trim()
      if (!name) continue
      const hit = i16.find((x) => String(x?.name || '').trim() === name)
      if (!hit) {
        missing++
        continue
      }
      const d15 = _num(r?.dcfValue ?? r?.recoverableAmount)
      const d16 = _num(hit?.valueInUse ?? hit?.recoverableAmount)
      if (Math.abs(d15 - d16) > 0.01 && _num(hit?.recoverableAmount) > 0) stale++
    }
    if (missing > 0) {
      items.push({
        id: 'imp-missing',
        area: 'I2-15/16 减值',
        level: 'error',
        message: `${missing} 项须测试但 I2-16 尚无测算组`,
        sheetHint: 'I2-16',
      })
    }
    if (stale > 0) {
      items.push({
        id: 'imp-stale',
        area: 'I2-15/16 减值',
        level: 'warn',
        message: `${stale} 项 I2-15 与 I2-16 金额不一致，请联动回写`,
        sheetHint: 'I2-16',
      })
    }
    if (missing === 0 && stale === 0) {
      items.push({
        id: 'imp-ok',
        area: 'I2-15/16 减值',
        level: 'ok',
        message: `须测试 ${needTest.length} 项，I2-16 测算组 ${i16Names.size} 个，金额一致`,
        sheetHint: 'I2-15',
      })
    }
  }

  // I2-12 抽查覆盖
  const i212 = _safeParseArray(map.get('I2-12-rows'))
  if (i212.length) {
    const fails = i212.filter((r) =>
      [r?.check1, r?.check2, r?.check3, r?.check4, r?.check5].some((c) => c === '×'),
    ).length
    items.push(fails
      ? { id: 't12-fail', area: 'I2-12 抽查', level: 'warn', message: `抽查 ${i212.length} 笔，核对× ${fails} 笔`, sheetHint: 'I2-12' }
      : { id: 't12-ok', area: 'I2-12 抽查', level: 'ok', message: `抽查 ${i212.length} 笔，未见核对×`, sheetHint: 'I2-12' })
  }

  const errorCount = items.filter((i) => i.level === 'error').length
  const warnCount = items.filter((i) => i.level === 'warn').length
  const okCount = items.filter((i) => i.level === 'ok').length
  return { items, errorCount, warnCount, okCount }
}

function _hasValue(v: unknown): boolean {
  if (v == null || v === '') return false
  if (typeof v === 'object') {
    const t = _readText(v)
    return t !== '' && t !== '[]' && t !== '{}'
  }
  return true
}

/** 必填项完成度：按 sheet 关键字段是否有实质内容 */
export function computeI2SheetCompletion(
  map: Map<string, any> | undefined | null,
  fieldPrefixes: string[],
): { filled: number; total: number; progress: number; status: '未开始' | '进行中' | '已完成' } {
  if (!fieldPrefixes.length) {
    return { filled: 0, total: 0, progress: 0, status: '未开始' }
  }
  if (!map || map.size === 0) {
    return { filled: 0, total: 0, progress: 0, status: '未开始' }
  }

  // 关键 key 优先（行表/结论）
  const criticalKeys: Record<string, string[]> = {
    'I2-6-': ['I2-6-rows', 'I2-6-audit-conclusion'],
    'I2-12-': ['I2-12-rows', 'I2-12-audit-conclusion'],
    'I2-15-': ['I2-15-rows'],
    'I2-16-': ['I2-16-dcf-params', 'I2-16-audit-conclusion'],
    'I2-2-': ['I2-2-rows'],
    'I2-7-': ['I2-7-rows'],
    'I2-13-': ['I2-13-rows', 'I2-13-audit-conclusion'],
    'I2-14-': ['I2-14-rows', 'I2-14-audit-conclusion'],
  }

  let filled = 0
  let total = 0

  for (const prefix of fieldPrefixes) {
    const crit = criticalKeys[prefix]
    if (crit) {
      for (const key of crit) {
        total++
        if (_hasValue(map.get(key))) filled++
      }
      continue
    }
    for (const [key, value] of map) {
      if (!key.startsWith(prefix)) continue
      total++
      if (_hasValue(value)) filled++
    }
  }

  if (total === 0) return { filled: 0, total: 0, progress: 0, status: '未开始' }
  const progress = Math.round((filled / total) * 100)
  if (progress >= 90) return { filled, total, progress: 100, status: '已完成' }
  if (filled > 0) return { filled, total, progress, status: '进行中' }
  return { filled, total, progress: 0, status: '未开始' }
}
