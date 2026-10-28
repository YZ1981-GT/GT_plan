/**
 * K2 其他流动资产披露表：表单状态、读回与同步快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `K2TabDisclosureListed` / `K2TabDisclosureSoe` 原先在组件里内联「默认行 → onMounted 读已保存的表（loadSavedData）→ 同步时拼快照」；
 * 抽成本模块的纯函数后，Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。读回就地改传入的状态对象
 * （Tab 传 reactive 对象，界面照常响应）；编辑、提示、AI、事件留在 Tab。叙述段的标题 / 填报要求（`_note_texts` 的中文
 * title 真源）在 `k2NoteSectionMap`（`K2_LISTED_TEXT_SEGMENTS` / `K2_SOE_NOTE_TEXT`）。
 */
import { recalcContractCost } from './useK2DisclosureEngine'
import {
  K2_CARBON_ROWS,
  K2_DEFAULT_CONTRACT_COST_CATEGORIES,
  K2_LISTED_MAIN_ROWS,
  K2_LISTED_TEXT_SEGMENTS,
  K2_SOE_MAIN_ROWS,
  K2_SOE_NOTE_TEXT,
  type K2DisclosureSnapshot,
  type K2ListedTextKey,
} from './k2NoteSectionMap'

/** 主表行（`fixed` = 模板固定行：行名不可改、不可删） */
export interface K2DisclosureMainRow {
  label: string
  endAmount: number
  priorAmount: number
  fixed: boolean
}

export interface K2ListedDisclosureState {
  mainRows: K2DisclosureMainRow[]
  contractCost: { enabled: boolean; categories: string[]; cells: number[][] }
  carbon: { enabled: boolean; rows: Array<{ label: string; currentAmount: number; priorAmount: number }> }
  texts: Record<K2ListedTextKey, string>
}

/** 底稿回复（读 `remark`，兼容旧 `value`；与 Tab / 离屏框架两种来源同口径） */
export type K2DisclosureResponses = ReadonlyMap<string, { remark?: unknown; value?: unknown } | undefined>

function defaultMainRows(labels: readonly string[]): K2DisclosureMainRow[] {
  return labels.map(label => ({ label, endAmount: 0, priorAmount: 0, fixed: true }))
}

/** 上市表单初值（主表 13 固定行、合同取得成本示例类别、碳排放 10 行，两张条件表默认关闭） */
export function createK2ListedDisclosureState(): K2ListedDisclosureState {
  return {
    mainRows: defaultMainRows(K2_LISTED_MAIN_ROWS),
    contractCost: {
      enabled: false,
      categories: [...K2_DEFAULT_CONTRACT_COST_CATEGORIES],
      cells: recalcContractCost([], K2_DEFAULT_CONTRACT_COST_CATEGORIES.length),
    },
    carbon: {
      enabled: false,
      rows: K2_CARBON_ROWS.map(label => ({ label, currentAmount: 0, priorAmount: 0 })),
    },
    texts: { significant: '', contractCost: '', carbon: '' },
  }
}

/** 国企主表初值（8 固定行） */
export function k2SoeDefaultMainRows(): K2DisclosureMainRow[] {
  return defaultMainRows(K2_SOE_MAIN_ROWS)
}

function parseSaved(responses: K2DisclosureResponses, itemId: string): any {
  const saved = responses.get(itemId)
  const raw = saved?.remark ?? saved?.value ?? null
  if (!raw) return null
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/** 已保存的主表整表替换（就地改）；模板固定行按行名认 */
function restoreMainRows(rows: K2DisclosureMainRow[], saved: any, fixedLabels: readonly string[]): void {
  if (!Array.isArray(saved) || !saved.length) return
  rows.splice(0, rows.length, ...saved.map((r: any) => ({
    label: String(r?.label ?? ''),
    endAmount: Number(r?.endAmount) || 0,
    priorAmount: Number(r?.priorAmount) || 0,
    fixed: fixedLabels.includes(String(r?.label ?? '')),
  })))
}

/** 上市：读已保存的四个条目（Tab onMounted 的 loadSavedData），就地改 `state`；缺失 / 损坏的条目保持初值 */
export function loadK2ListedDisclosureState(responses: K2DisclosureResponses, state: K2ListedDisclosureState): void {
  restoreMainRows(state.mainRows, parseSaved(responses, 'K2-disc-listed-main'), K2_LISTED_MAIN_ROWS)

  const savedCc = parseSaved(responses, 'K2-disc-listed-contract-cost')
  if (savedCc && typeof savedCc === 'object') {
    state.contractCost.enabled = !!savedCc.enabled
    const cats = Array.isArray(savedCc.categories)
      ? savedCc.categories.map((c: any) => String(c ?? '').trim()).filter(Boolean)
      : []
    state.contractCost.categories = cats.length ? cats : [...K2_DEFAULT_CONTRACT_COST_CATEGORIES]
    state.contractCost.cells = recalcContractCost(
      Array.isArray(savedCc.cells) ? savedCc.cells : [],
      state.contractCost.categories.length,
    )
  }

  const savedCarbon = parseSaved(responses, 'K2-disc-listed-carbon')
  if (savedCarbon && typeof savedCarbon === 'object') {
    state.carbon.enabled = !!savedCarbon.enabled
    const byLabel = new Map(
      (Array.isArray(savedCarbon.rows) ? savedCarbon.rows : []).map((r: any) => [String(r?.label ?? ''), r]),
    )
    state.carbon.rows = K2_CARBON_ROWS.map(label => {
      const hit: any = byLabel.get(label)
      return {
        label,
        currentAmount: Number(hit?.currentAmount) || 0,
        priorAmount: Number(hit?.priorAmount) || 0,
      }
    })
  }

  const savedTexts = parseSaved(responses, 'K2-disc-listed-texts')
  if (savedTexts && typeof savedTexts === 'object') {
    for (const key of ['significant', 'contractCost', 'carbon'] as K2ListedTextKey[]) {
      state.texts[key] = String(savedTexts[key] ?? '')
    }
  }
}

/** 国企：读已保存的主表（就地改 `mainRows`）；返回已保存的说明（没有 / 损坏回 null，调用方保持原值） */
export function loadK2SoeDisclosureState(responses: K2DisclosureResponses, mainRows: K2DisclosureMainRow[]): string | null {
  restoreMainRows(mainRows, parseSaved(responses, 'K2-disc-soe-main'), K2_SOE_MAIN_ROWS)
  const savedText = parseSaved(responses, 'K2-disc-soe-text')
  return savedText && typeof savedText === 'object' ? String(savedText.text ?? '') : null
}

function mainSnapshot(rows: readonly K2DisclosureMainRow[]): K2DisclosureSnapshot['mainRows'] {
  return rows.map(r => ({
    label: r.label,
    endAmount: r.endAmount,
    priorAmount: r.priorAmount,
  }))
}

/** 上市同步快照 → `buildK2SyncPayload('listed', …)`（文本段只推非空的） */
export function buildK2ListedDisclosureSnapshot(state: K2ListedDisclosureState): K2DisclosureSnapshot {
  return {
    mainRows: mainSnapshot(state.mainRows),
    contractCost: {
      enabled: state.contractCost.enabled,
      categories: [...state.contractCost.categories],
      cells: state.contractCost.cells.map(r => [...r]),
    },
    carbon: {
      enabled: state.carbon.enabled,
      rows: state.carbon.rows.map(r => ({ ...r })),
    },
    texts: K2_LISTED_TEXT_SEGMENTS
      .filter(seg => state.texts[seg.key].trim())
      .map(seg => ({ section: `k2-${seg.key}`, title: seg.title, text: state.texts[seg.key] })),
  }
}

/** 国企同步快照 → `buildK2SyncPayload('soe', …)`（说明非空才推） */
export function buildK2SoeDisclosureSnapshot(mainRows: readonly K2DisclosureMainRow[], noteText: string): K2DisclosureSnapshot {
  return {
    mainRows: mainSnapshot(mainRows),
    texts: noteText.trim()
      ? [{ section: K2_SOE_NOTE_TEXT.section, title: K2_SOE_NOTE_TEXT.title, text: noteText }]
      : [],
  }
}
