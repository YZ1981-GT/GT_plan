/**
 * f1FourTableSource — F1 四表库取数溯源（纯函数）
 *
 * 后端 `_f1_prepayment.render` 下发 `project_context.tb_source_codes`
 * （`four_table.ReportLineAccounts.as_dict()`），本模块把它归一为界面可展示的结构。
 *
 * 🔴 为什么要兼容 `string[]`：改造前该字段是 `list[str]`（且前端 **0 消费** = dead output）。
 * 老项目的 render 缓存 / 并发会话回退都可能返回旧形态，归一后统一按 dict 消费。
 *
 * 科目映射链路（后端 docstring 有完整实证，此处只列结论）：
 *   报表行 `BS-008` → `report_config.formula` → 标准码 → `account_mapping` 反解 → 原始码
 *   备抵侧 `BS-008` 公式**不含**坏账 → 兜底标准码 `1231-04`；而实证项目均无该映射
 *   → 反解退化为宽前缀 `1231` → **必须**叠「预付」名称过滤（否则混入应收账款坏账）。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R1.7, R4.3
 */

export type F1ResolvedFrom = 'report_config' | 'fallback'

export interface F1TbSource {
  rowCode: string
  formula: string | null
  grossStandard: string[]
  gross: string[]
  provisionStandard: string[]
  provision: string[]
  resolvedFrom: F1ResolvedFrom
  provisionResolvedFrom: F1ResolvedFrom
  provisionExact: boolean
  useProvisionNameFilter: boolean
}

export interface F1CrossCycleSource {
  rowCode: string
  codes: string[]
}

export interface F1CrossCycleSources {
  inventory: F1CrossCycleSource
  payable: F1CrossCycleSource
}

const EMPTY_SOURCE: F1TbSource = {
  rowCode: 'BS-008',
  formula: null,
  grossStandard: [],
  gross: [],
  provisionStandard: [],
  provision: [],
  resolvedFrom: 'fallback',
  provisionResolvedFrom: 'fallback',
  provisionExact: false,
  useProvisionNameFilter: true,
}

function toStrList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map((x) => String(x ?? '').trim()).filter(Boolean)
}

function toResolvedFrom(v: unknown): F1ResolvedFrom {
  return String(v ?? '') === 'report_config' ? 'report_config' : 'fallback'
}

/**
 * 归一 `tb_source_codes`（兼容旧 `string[]` 与新 dict；缺字段给安全默认）。
 */
export function normalizeF1TbSource(raw: unknown): F1TbSource {
  if (Array.isArray(raw)) {
    const codes = toStrList(raw)
    return {
      ...EMPTY_SOURCE,
      grossStandard: codes,
      gross: codes,
      // 旧形态没有备抵信息 → 保守标为兜底 + 需名称过滤
      provisionStandard: [],
      provision: [],
    }
  }
  if (!raw || typeof raw !== 'object') return { ...EMPTY_SOURCE }
  const o = raw as Record<string, unknown>
  const provisionExact = o.provision_exact === true
  return {
    rowCode: String(o.row_code ?? EMPTY_SOURCE.rowCode),
    formula: o.formula == null ? null : String(o.formula),
    grossStandard: toStrList(o.gross_standard),
    gross: toStrList(o.gross),
    provisionStandard: toStrList(o.provision_standard),
    provision: toStrList(o.provision),
    resolvedFrom: toResolvedFrom(o.resolved_from),
    provisionResolvedFrom: toResolvedFrom(o.provision_resolved_from),
    provisionExact,
    useProvisionNameFilter:
      o.use_provision_name_filter === undefined
        ? !provisionExact
        : o.use_provision_name_filter === true,
  }
}

/** 归一 F1-4 跨循环锚点科目来源（存货 BS-010 区间 / 应付账款 BS-045）。 */
export function normalizeF1CrossCycleSources(raw: unknown): F1CrossCycleSources {
  const o = (raw && typeof raw === 'object' ? raw : {}) as Record<string, any>
  const pick = (key: string, fallbackRow: string, fallbackCodes: string[]): F1CrossCycleSource => {
    const node = (o[key] && typeof o[key] === 'object' ? o[key] : {}) as Record<string, unknown>
    const codes = toStrList(node.codes)
    return {
      rowCode: String(node.row_code ?? fallbackRow),
      codes: codes.length ? codes : fallbackCodes,
    }
  }
  return {
    inventory: pick('inventory', 'BS-010', ['1401~1499']),
    payable: pick('payable', 'BS-045', ['2202']),
  }
}

/** 解析来源中文化（UI 全中文化铁律；`fallback` 用橙色警示）。 */
export function describeResolvedFrom(v: F1ResolvedFrom): {
  text: string
  type: 'success' | 'warning'
} {
  return v === 'report_config'
    ? { text: '报表映射', type: 'success' }
    : { text: '兜底科目', type: 'warning' }
}

/**
 * 两个 TB 口径是否存在差异（trial_balance 重算产物 vs 科目余额表叶子合计）。
 *
 * 实证项目 `2aa00f57`：trial_balance 2,603,836.86 = 叶子合计 1,301,918.43 的 **2 倍**
 * （recalc 把 `dataset_id IS NULL` 的历史行一并计入）→ 必须让审计师看见，不能只显示一个数。
 */
export function tbAmountDivergence(
  trialBalanceAmount: number | null | undefined,
  leafAmount: number | null | undefined,
): { hasDivergence: boolean; diff: number } {
  const a = Number(trialBalanceAmount ?? 0) || 0
  const b = Number(leafAmount ?? 0) || 0
  const diff = Number((a - b).toFixed(2))
  // 任一口径为 0（未取到数）时不报差异，避免「未取数」被误读为「勾稽异常」
  if (a === 0 || b === 0) return { hasDivergence: false, diff }
  return { hasDivergence: Math.abs(diff) > 0.01, diff }
}
