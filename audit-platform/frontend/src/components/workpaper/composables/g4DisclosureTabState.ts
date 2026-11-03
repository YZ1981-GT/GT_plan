/**
 * G4 债权投资披露 Tab 的段落表格状态、打开时回显与同步快照（底稿披露 Tab 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1）。
 *
 * 由 `G4TabDisclosureListed` / `G4TabDisclosureSOE` 原样抽出：各段默认行（原 `buildSections`）、打开时回显
 * （原 `readSaved` + `loadFromHtmlData`：读 htmlData 里的已存段落与三阶段明细 / 说明）、同步快照（原
 * `buildSyncSnapshot`）。审定事件回填合计行、文本保存与广播、AI、提示与同步发送仍在 Tab。
 *
 * 🔴 回显的数据源：Tab 读 `htmlData.checklist_responses`（键 → 回复）或 `htmlData.responses`（回复列表），
 *    render-config 实际下发的是 `responses_snapshot`（2026-10-28 实测，两个键都没有）⇒ Tab 打开时三阶段明细 /
 *    说明恒为默认值（缺陷已登记，修法见 spec note-pull-followup-closure 交付说明）。离屏同步按回显函数支持的
 *    `checklist_responses` 形态喂本底稿回复（`g4ResponsesAsHtmlData`），推的是上次保存的三阶段明细 / 说明。
 * 🔴 国企回显按国企 3 张骨架解析阶段表：原按上市 6 张骨架解析 ⇒ 表名 / 末列名被换成上市写法（「期末处于…」/
 *    「划分依据」），同步到 八、15 就成了模板里没有的孤儿表。生产中该路径因上一条读不到数据从未走到。
 */
import { reactive, ref } from 'vue'
import {
  buildDefaultSoeStageBlocks,
  buildDefaultStageBlocks,
  endingImpairmentTotal,
  parseStageBlocks,
  type G4StageBlock,
} from './g4ListedStageDisclosure'
import type { G4DisclosureVariant } from './g4NoteSectionMap'
import type { ChecklistResponse } from './useF1FormData'

/** 三阶段明细 / 三阶段说明的回复条目（Tab 保存，打开时回显） */
export const G4_DISCLOSURE_STAGE_KEYS = {
  listed: { rows: 'G4-disclosure-listed-stages', note: 'G4-disclosure-listed-stage-note' },
  soe: { rows: 'G4-disclosure-soe-stages', note: 'G4-disclosure-soe-stage-note' },
} as const satisfies Record<G4DisclosureVariant, { rows: string; note: string }>

export interface G4DisclosureRow {
  item: string
  endingBalance: number
  endingImpairment: number
  endingBookValue: number
  priorBalance: number
  priorImpairment: number
  priorBookValue: number
  isFormula?: boolean
  openingBalance?: number
  closingBalance?: number
  impairment?: number
  amortizedCost?: number
}

export interface G4DisclosureSection {
  id: string
  title: string
  rows: G4DisclosureRow[]
  hasTextArea: boolean
  textContent: string
}

export function buildG4ListedDisclosureSections(): G4DisclosureSection[] {
  return [
    {
      id: 'bond-overview',
      title: '债权投资',
      rows: [
        { item: '国债', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '企业债', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '其他债权投资', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '小计', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
        { item: '减：一年内到期的债权投资', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '合计', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'impairment-movement',
      title: '（1）债权投资减值准备本期变动情况',
      rows: [
        { item: '期初余额', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期增加', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期减少', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '期末余额', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'important-bonds',
      title: '（2）期末重要的债权投资',
      rows: [
        { item: '重要债权投资1', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '重要债权投资2', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '合计', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'stage-impairment',
      title: '（3）减值准备计提情况（三阶段）',
      rows: [],
      hasTextArea: false,
      textContent: '',
    },
    {
      id: 'provision-walkforward',
      title: '（4）本期计提、收回或转回的减值准备情况',
      rows: [
        { item: '上年年末余额', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期计提', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期转回', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期核销', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '期末余额', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'writeoff',
      title: '（5）本期实际核销的债权投资',
      rows: [
        { item: '实际核销的债权投资', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '合计', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
  ]
}

export function buildG4SoeDisclosureSections(): G4DisclosureSection[] {
  return [
    {
      id: 'bond-overview',
      title: '（1）债权投资情况',
      rows: [
        { item: '项目1', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '项目2', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '项目3', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '合计', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'important-bonds',
      title: '（2）期末重要的债权投资情况',
      rows: [
        { item: '重要项目1', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '重要项目2', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '合计', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'stage-impairment',
      title: '（3）减值准备计提情况',
      rows: [],
      hasTextArea: false,
      textContent: '',
    },
    {
      id: 'provision-walkforward',
      title: '本期计提、收回或转回的减值准备情况',
      rows: [
        { item: '期初余额', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期计提', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期转回', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '本期核销', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0 },
        { item: '期末余额', endingBalance: 0, endingImpairment: 0, endingBookValue: 0, priorBalance: 0, priorImpairment: 0, priorBookValue: 0, isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
  ]
}

/** 已存回复：`checklist_responses`（键 → 回复或字符串）优先，其次 `responses`（回复列表）；取 remark */
export function readG4DisclosureSaved(htmlData: Record<string, any> | null | undefined, key: string): string {
  const cr = htmlData?.checklist_responses
  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {
    const v = (cr as Record<string, any>)[key]
    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')
  }
  const resp = htmlData?.responses
  if (Array.isArray(resp)) {
    const found = resp.find((r: any) => r?.item_id === key)
    if (found?.remark) return found.remark
  }
  return ''
}

/** 离屏同步：把本底稿回复按回显函数支持的 `checklist_responses` 形态交给同一个回显（见文件头） */
export function g4ResponsesAsHtmlData(responses: ReadonlyMap<string, ChecklistResponse>): Record<string, any> {
  return { checklist_responses: Object.fromEntries(responses) }
}

/** 同步快照：主表行 = 「债权投资」段；各段文本域按 section.id；三阶段块与说明原样 */
export function g4DisclosureSyncSnapshot(
  sections: readonly G4DisclosureSection[],
  stageBlocks: G4StageBlock[],
  stageNote: string,
) {
  const main = sections.find((s) => s.id === 'bond-overview')
  const sectionTexts: Record<string, string> = {}
  for (const s of sections) {
    if (s.hasTextArea && s.textContent) sectionTexts[s.id] = s.textContent
  }
  return {
    mainRows: main?.rows ?? [],
    stageBlocks,
    stageNote,
    sectionTexts,
  }
}

/**
 * 披露 Tab 的表格状态（段落 / 三阶段块 / 三阶段说明）+ 打开时回显 + 同步快照。
 * Tab 在 onMounted 里调 `loadFromHtmlData()`（与原实现同一时机）；离屏同步在 prepare 里调。
 */
export function useG4DisclosureTabState(
  variant: G4DisclosureVariant,
  htmlData: () => Record<string, any> | null | undefined,
) {
  const keys = G4_DISCLOSURE_STAGE_KEYS[variant]
  const sections = reactive<G4DisclosureSection[]>(
    variant === 'listed' ? buildG4ListedDisclosureSections() : buildG4SoeDisclosureSections(),
  )
  const stageBlocks = ref<G4StageBlock[]>(
    variant === 'listed' ? buildDefaultStageBlocks() : buildDefaultSoeStageBlocks(),
  )
  const stageNoteText = ref('')

  function loadListed(hd: Record<string, any> | null | undefined): void {
    if (hd?.disclosureListed?.sections) {
      const saved = hd.disclosureListed.sections as G4DisclosureSection[]
      saved.forEach((s, i) => {
        if (sections[i] && sections[i].id !== 'stage-impairment') {
          if (s.textContent) sections[i].textContent = s.textContent
          if (s.rows?.length) sections[i].rows = s.rows
        }
      })
    }
    const parsed = parseStageBlocks(readG4DisclosureSaved(hd, keys.rows))
    if (parsed) stageBlocks.value = parsed
    const note = readG4DisclosureSaved(hd, keys.note)
    if (note) stageNoteText.value = note
    // 暴露勾稽值供调试/扩展
    void endingImpairmentTotal(stageBlocks.value)
  }

  function loadSoe(hd: Record<string, any> | null | undefined): void {
    if (hd?.disclosureSOE?.sections) {
      const saved = hd.disclosureSOE.sections as G4DisclosureSection[]
      saved.forEach((s, i) => {
        if (sections[i] && sections[i].id !== 'stage-impairment') {
          if (s.textContent) sections[i].textContent = s.textContent
          if (s.rows?.length && 'endingBalance' in (s.rows[0] || {})) {
            sections[i].rows = s.rows as G4DisclosureRow[]
          }
        }
      })
    }
    // 🔴 按国企骨架解析（见文件头）：表名 / 损失率列名 / 末列名始终取国企模板写法
    const parsed = parseStageBlocks(readG4DisclosureSaved(hd, keys.rows), buildDefaultSoeStageBlocks())
    if (parsed) {
      // 国企仅保留期末三阶段
      const soeIds = new Set(buildDefaultSoeStageBlocks().map(b => b.id))
      const filtered = parsed.filter(b => soeIds.has(b.id))
      stageBlocks.value = filtered.length ? filtered : buildDefaultSoeStageBlocks()
      // 补全缺省 block
      const have = new Set(stageBlocks.value.map(b => b.id))
      for (const def of buildDefaultSoeStageBlocks()) {
        if (!have.has(def.id)) stageBlocks.value.push(def)
      }
    }
    const note = readG4DisclosureSaved(hd, keys.note)
    if (note) stageNoteText.value = note
  }

  function loadFromHtmlData(): void {
    if (variant === 'listed') loadListed(htmlData())
    else loadSoe(htmlData())
  }

  function buildSyncSnapshot() {
    return g4DisclosureSyncSnapshot(sections, stageBlocks.value, stageNoteText.value)
  }

  return { sections, stageBlocks, stageNoteText, loadFromHtmlData, buildSyncSnapshot }
}
