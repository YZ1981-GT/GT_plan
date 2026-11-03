/**
 * G6 其他债权投资披露（国企）Tab 的表格状态、回显 / 回填与同步载荷（底稿披露 Tab 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1）。
 *
 * 由 `G6TabDisclosureSOE` 原样抽出：余额 / 重要投资 / 变动 / 三阶段 / 说明的状态与默认行、`readResponse`、`loadPersisted`、
 * 从 G6-1 / G6-2 / G6-3 回填（原 `refreshFromSources` 去掉末尾的保存与提示 = `applySourceRows`）、`buildSyncData`、
 * `G6_SOE_COLUMNS` 与发送体（原 `syncToDisclosureNotes` 里内联的请求体 = `buildSyncPayload`）。保存（`g6:save-items`）、
 * 回填后的保存与提示、勾稽标签、AI、审定事件与自动同步 watch 仍在 Tab。
 *
 * 口径：章节 / 准则取自 htmlData 的 `applicable_standards`（render-config 页签 html_data 实测没有这个键 ⇒ 恒
 * soe_standalone / 八、16，与附注注册表一致）。国企附注只推「其他债权投资情况」「期末重要的其他债权投资」两张表，
 * 三阶段与减值变动表留底稿（`_removed_table_keys` 清历史孤儿）。
 */
import { computed, ref } from 'vue'
import { buildDefaultSoeStageBlocks, parseStageBlocks, type G4StageBlock } from './g4ListedStageDisclosure'
import type { ColumnDef } from './disclosureColumnDefs'
import type { ChecklistResponse } from './useF1FormData'

export interface G6SoeBalanceRow {
  item: string
  endingBalance: number
  openingBalance: number
}

export interface G6SoeImportantRow {
  item: string
  faceValue: number
  amortizedCost: number
  fairValue: number
  ociCumulative: number
  impairment: number
}

export type G6SoeMovementAmountKey = 'stage1' | 'stage2' | 'stage3'

export interface G6SoeMovementRow {
  key: string
  item: string
  stage1: number
  stage2: number
  stage3: number
  editable: boolean
}

/** 结构化行 / 三阶段块 / 附注说明的回复条目 */
export const G6_SOE_DISCLOSURE_KEYS = {
  rows: 'G6-disclosure-soe-rows',
  stages: 'G6-disclosure-soe-stages',
  text: 'G6-disclosure-soe-text',
} as const

function n(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}
export { n as g6SoeNum }

export function g6SoeStageDefaults(): G4StageBlock[] {
  return buildDefaultSoeStageBlocks().map(block => ({
    ...block,
    title: block.title.replace('债权投资', '其他债权投资'),
  }))
}

function parseJson(raw: string): any {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

// 列头元数据（disclosure-table-sync-convergence）：label 取自本组件 el-table-column
export const G6_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  其他债权投资情况: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'prior_balance', label: '期初余额', format: 'amount' },
  ],
  期末重要的其他债权投资: [
    { key: 'label', label: '其他债权投资项目', is_label: true },
    { key: 'face_value', label: '面值', format: 'amount' },
    { key: 'amortized_cost', label: '摊余成本', format: 'amount' },
    { key: 'fair_value', label: '公允价值', format: 'amount' },
    { key: 'oci_cumulative', label: '累计计入 OCI 的公允价值变动', format: 'amount' },
    { key: 'impairment', label: '减值准备', format: 'amount' },
  ],
  减值准备计提情况: [
    { key: 'label', label: '类别', is_label: true },
    { key: 'book_balance', label: '账面余额', format: 'amount' },
    { key: 'impairment', label: '减值准备', format: 'amount' },
    { key: 'book_value', label: '账面价值（分析口径）', format: 'amount' },
    { key: 'reason', label: '理由' },
  ],
  减值准备变动: [
    { key: 'label', label: '减值准备', is_label: true },
    { key: 'stage1', label: '第一阶段', format: 'amount' },
    { key: 'stage2', label: '第二阶段', format: 'amount' },
    { key: 'stage3', label: '第三阶段', format: 'amount' },
    { key: 'total', label: '合计', format: 'amount' },
  ],
}

export function useG6SoeDisclosureState(opts: {
  allResponses: () => Map<string, ChecklistResponse> | undefined
  htmlData: () => Record<string, any> | null | undefined
}) {
  const { rows: STRUCTURED_KEY, stages: STAGES_KEY, text: TEXT_KEY } = G6_SOE_DISCLOSURE_KEYS
  const sourceFvEnd = ref(0)
  const sourceFvOpening = ref(0)
  const sourceProvisionEnd = ref(0)

  const balanceRows = ref<G6SoeBalanceRow[]>(
    Array.from({ length: 4 }, (_, i) => ({
      item: `项目${i + 1}（可改名）`,
      endingBalance: 0,
      openingBalance: 0,
    })),
  )
  const importantRows = ref<G6SoeImportantRow[]>(
    Array.from({ length: 4 }, (_, i) => ({
      item: `重要项目${i + 1}`,
      faceValue: 0,
      amortizedCost: 0,
      fairValue: 0,
      ociCumulative: 0,
      impairment: 0,
    })),
  )

  const movementRows = ref<G6SoeMovementRow[]>([
    { key: 'opening', item: '期初余额', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'transfer-2', item: '—转入第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'transfer-3', item: '—转入第三阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'return-2', item: '—转回第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'return-1', item: '—转回第一阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'provision', item: '本期计提', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'reversal', item: '本期转回', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'transfer-out', item: '本期转销', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'write-off', item: '本期核销', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'other', item: '其他变动', stage1: 0, stage2: 0, stage3: 0, editable: true },
  ])

  const stageBlocks = ref<G4StageBlock[]>(g6SoeStageDefaults())
  const noteText = ref('')

  const standards = computed<string[]>(() => {
    const raw =
      opts.htmlData()?.applicable_standards
      ?? opts.htmlData()?.render_config?.applicable_standards
      ?? []
    return Array.isArray(raw) ? raw.map(String) : []
  })
  const currentStandard = computed(() =>
    standards.value.find(s => s === 'soe_standalone' || s === 'soe_consolidated')
    ?? 'soe_standalone',
  )
  const noteSection = computed(() =>
    currentStandard.value === 'soe_consolidated' ? '五、17' : '八、16',
  )

  function readResponse(key: string): string {
    const direct = opts.allResponses()?.get(key)
    if (direct?.remark || direct?.conclusion) return direct.remark || direct.conclusion || ''
    const map = opts.htmlData()?.checklist_responses
    if (map?.[key]) {
      const item = map[key]
      return typeof item === 'object' ? item.remark || item.conclusion || '' : String(item)
    }
    const list = opts.htmlData()?.responses
    if (Array.isArray(list)) {
      const item = list.find((entry: any) => entry?.item_id === key)
      return item?.remark || item?.conclusion || ''
    }
    return ''
  }

  function loadPersisted(): boolean {
    let found = false
    const structured = readResponse(STRUCTURED_KEY)
    if (structured) {
      try {
        const parsed = JSON.parse(structured)
        if (Array.isArray(parsed.balanceRows)) balanceRows.value = parsed.balanceRows
        if (Array.isArray(parsed.importantRows)) importantRows.value = parsed.importantRows
        if (Array.isArray(parsed.movementRows)) movementRows.value = parsed.movementRows
        found = true
      } catch { /* invalid legacy payload */ }
    }
    const parsedStages = parseStageBlocks(readResponse(STAGES_KEY))
    if (parsedStages) {
      const ids = new Set(g6SoeStageDefaults().map(block => block.id))
      stageBlocks.value = parsedStages
        .filter(block => ids.has(block.id))
        .map(block => ({ ...block, title: block.title.replace('债权投资', '其他债权投资') }))
      found = true
    }
    noteText.value = readResponse(TEXT_KEY)
    return found
  }

  /** 从 G6-1 / G6-2 / G6-3 回填（只改内存；`force` = 覆盖已有金额）。Tab 回填后保存并提示 */
  function applySourceRows(force = false): void {
    const adjudication = parseJson(readResponse('G6-1-rows')) || {}
    let fvEnd = 0
    let fvOpening = 0
    balanceRows.value = balanceRows.value.map((row, index) => {
      const source = adjudication[`fv-item-${index + 1}`] || {}
      const endingBalance = n(source.closingUnadjusted) + n(source.closingAdjustment)
      const openingBalance = n(source.openingUnadjusted) + n(source.openingAdjustment)
      fvEnd += endingBalance
      fvOpening += openingBalance
      return {
        item: String(source.itemLabel || row.item),
        endingBalance: force || !row.endingBalance ? endingBalance : row.endingBalance,
        openingBalance: force || !row.openingBalance ? openingBalance : row.openingBalance,
      }
    })
    sourceFvEnd.value = fvEnd
    sourceFvOpening.value = fvOpening

    const detail = parseJson(readResponse('G6-2-rows'))
    if (Array.isArray(detail)) {
      const rows = detail.filter((row: any) => row?.investProject || n(row?.closingAudited)).slice(0, 4)
      importantRows.value = importantRows.value.map((current, index) => {
        const row = rows[index]
        if (!row) return current
        return {
          item: String(row.investProject || current.item),
          faceValue: n(row.faceValue),
          amortizedCost: n(row.closingSubtotal),
          fairValue: n(row.closingAudited || row.closingFairValue),
          ociCumulative: n(row.closingCumulativeFvChange),
          impairment: current.impairment,
        }
      })
    }

    const badDebt = parseJson(readResponse('G6-3-rows'))
    if (Array.isArray(badDebt)) {
      sourceProvisionEnd.value = badDebt.reduce((sum: number, row: any) => {
        const closingUnadjusted =
          n(row.openingUnadjusted)
          + n(row.provisionIncrease)
          + n(row.otherIncrease)
          - n(row.reversal)
          - n(row.writeOff)
          - n(row.otherDecrease)
        return sum + closingUnadjusted + n(row.closingAdjustment)
      }, 0)
    }
  }

  const balanceTotals = computed(() => ({
    ending: balanceRows.value.reduce((sum, row) => sum + n(row.endingBalance), 0),
    opening: balanceRows.value.reduce((sum, row) => sum + n(row.openingBalance), 0),
  }))

  function buildSyncData(): Record<string, Record<string, unknown>[] | string[]> {
    return {
      其他债权投资情况: [
        ...balanceRows.value.map(row => ({
          label: row.item,
          end_balance: n(row.endingBalance),
          prior_balance: n(row.openingBalance),
          row_type: 'data',
        })),
        {
          label: '合计',
          end_balance: balanceTotals.value.ending,
          prior_balance: balanceTotals.value.opening,
          row_type: 'subtotal',
          is_total: true,
        },
      ],
      期末重要的其他债权投资: importantRows.value.map(row => ({
        label: row.item,
        face_value: n(row.faceValue),
        amortized_cost: n(row.amortizedCost),
        fair_value: n(row.fairValue),
        oci_cumulative: n(row.ociCumulative),
        impairment: n(row.impairment),
        row_type: 'data',
      })),
      // 🔴 国企减值准备计提情况交叉引用 G5 §八、15（附注模板 text_section 明确写
      // 「参照附注八、15 债权投资（3）减值准备计提情况进行披露」），不推三阶段表。
      // 底稿仍录入（审计证据），但不进附注。历史孤儿通过 _removed_table_keys 清理。
      _removed_table_keys: ['减值准备计提情况', '减值准备变动'],
      _note_texts: [{ section: 'soe-audit-note', title: '其他债权投资审计说明', text: noteText.value }],
    }
  }

  /** `sync-from-workpaper` 请求体（原 `syncToDisclosureNotes` 里内联，字段与顺序不变） */
  function buildSyncPayload(wpId: string) {
    return {
      wp_id: wpId,
      sheet_name: '附注披露信息（国企）',
      section_id: noteSection.value,
      current_standard: currentStandard.value,
      sub_table_data: buildSyncData(),
      columns: G6_SOE_COLUMNS,
    }
  }

  return {
    sourceFvEnd,
    sourceFvOpening,
    sourceProvisionEnd,
    balanceRows,
    importantRows,
    movementRows,
    stageBlocks,
    noteText,
    currentStandard,
    noteSection,
    balanceTotals,
    readResponse,
    loadPersisted,
    applySourceRows,
    buildSyncData,
    buildSyncPayload,
  }
}
