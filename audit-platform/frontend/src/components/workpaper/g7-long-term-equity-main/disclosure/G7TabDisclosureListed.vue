<template>
  <div class="g7-listed">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按源模板 A1:M243 的披露顺序编制长期股权投资附注，区分结构化表格、编制提示、示例文字和正式披露文本，并与 G7-4、G7-5、G7-10、G7-16 及附注模块保持可追溯联动。
    </el-alert>

    <div class="toolbar">
      <div>
        <strong>附注披露信息（上市公司）</strong>
        <el-tag size="small" type="info" effect="plain">源模板 243 行 / 13 列</el-tag>
        <el-tag size="small" type="success" effect="plain">结构化区块 {{ tableCount }} 个</el-tag>
        <el-tag size="small" type="warning" effect="plain">披露文本 {{ narrativeCount }} 个</el-tag>
      </div>
      <div class="toolbar-actions">
        <span class="save-status">{{ saveStatus }}</span>
        <el-tag v-if="lastRefreshHint" size="small" type="info" effect="plain">{{ lastRefreshHint }}</el-tag>
        <el-button
          size="small"
          :disabled="isReadonly"
          :loading="isRefreshing"
          @click="refreshFromSources(true)"
        >
          从源表取数
        </el-button>
        <el-button
          type="primary"
          size="small"
          :disabled="isReadonly || !projectId"
          :loading="isSyncing"
          @click="syncToDisclosureNotes"
        >
          同步到附注模块
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="adjudicatedAmount != null"
      :type="reconciliationDiff === 0 ? 'success' : 'warning'"
      :closable="false"
      class="reconciliation"
    >
      1511审定数：{{ fmtAmount(adjudicatedAmount) }}；
      披露表期末账面价值合计：{{ fmtAmount(disclosureClosingTotal) }}；
      差异：{{ fmtAmount(reconciliationDiff) }}。
      <span v-if="reconciliationDiff !== 0">请核对合营、联营投资范围及与审定表的口径差异。</span>
    </el-alert>

    <el-skeleton v-if="!hydrated" :rows="10" animated />

    <el-collapse v-else v-model="activeSections" class="sections">
      <el-collapse-item
        v-for="section in sections"
        :key="section.id"
        :name="section.id"
      >
        <template #title>
          <div class="section-title">
            <span>{{ section.title }}</span>
            <el-tag size="small" effect="plain">Excel {{ section.sourceRows }}</el-tag>
            <GtReviewTrigger :section-id="`G7-disclosure-listed-${section.id}`" />
          </div>
        </template>

        <div class="section-body">
          <el-alert
            v-for="tip in section.guidance ?? []"
            :key="tip"
            type="info"
            :closable="false"
            class="source-tip"
          >
            {{ tip }}
          </el-alert>

          <article
            v-for="table in section.tables ?? []"
            :key="table.id"
            class="table-block"
          >
            <header class="block-head">
              <div>
                <h4>{{ table.title }}</h4>
                <span>源区域：{{ table.sourceRows }}</span>
              </div>
              <div v-if="table.dynamic" class="add-row-actions">
                <template v-if="table.id === 'investment-movement'">
                  <el-button
                    size="small"
                    :disabled="isReadonly || tableRows(table).length >= (table.maxRows ?? 100)"
                    @click="addRow(table, 'joint-venture')"
                  >
                    新增合营企业
                  </el-button>
                  <el-button
                    size="small"
                    :disabled="isReadonly || tableRows(table).length >= (table.maxRows ?? 100)"
                    @click="addRow(table, 'associate')"
                  >
                    新增联营企业
                  </el-button>
                </template>
                <template v-else-if="table.id === 'excess-losses'">
                  <el-button
                    size="small"
                    :disabled="isReadonly || tableRows(table).length >= (table.maxRows ?? 100)"
                    @click="addRow(table, 'joint-venture')"
                  >
                    新增合营行
                  </el-button>
                  <el-button
                    size="small"
                    :disabled="isReadonly || tableRows(table).length >= (table.maxRows ?? 100)"
                    @click="addRow(table, 'associate')"
                  >
                    新增联营行
                  </el-button>
                </template>
                <el-button
                  v-else
                  size="small"
                  :disabled="isReadonly || tableRows(table).length >= (table.maxRows ?? 100)"
                  @click="addRow(table)"
                >
                  新增被投资单位
                </el-button>
              </div>
            </header>

            <p v-if="table.description" class="table-description">
              {{ table.description }}
            </p>

            <div class="table-scroll">
              <el-table
                :data="tableRows(table)"
                border
                size="small"
                :row-class-name="tableRowClass"
                class="disclosure-table"
              >
                <el-table-column label="项目/被投资单位" fixed width="230">
                  <template #default="{ row }">
                    <template v-if="row.kind === 'subtotal' || row.kind === 'total' || row.kind === 'group'">
                      <strong>{{ row.label }}</strong>
                    </template>
                    <template v-else>
                      <el-input
                        v-model="row.label"
                        size="small"
                        :disabled="isReadonly"
                        placeholder="被投资单位名称"
                        @change="scheduleSave"
                      />
                      <span v-if="row.source" class="cell-source" :title="row.source">
                        来源：{{ row.source }}
                      </span>
                    </template>
                  </template>
                </el-table-column>

                <el-table-column
                  v-for="column in table.columns"
                  :key="column.key"
                  :label="column.label"
                  :width="column.width"
                  min-width="130"
                  :align="column.type === 'text' ? 'left' : 'right'"
                >
                  <template #default="{ row }">
                    <span
                      v-if="row.kind === 'subtotal' || row.kind === 'total'"
                      class="computed-value"
                    >
                      {{ formatCell(computedCell(table, row, column.key), column.type) }}
                    </span>
                    <el-input
                      v-else-if="column.type === 'text'"
                      v-model="row.values[column.key]"
                      size="small"
                      :disabled="isReadonly"
                      @change="scheduleSave"
                    />
                    <el-input-number
                      v-else
                      v-model="row.values[column.key]"
                      size="small"
                      controls-position="right"
                      :precision="column.type === 'percent' ? 4 : 2"
                      :min="column.type === 'percent' ? 0 : undefined"
                      :max="column.type === 'percent' ? 100 : undefined"
                      :disabled="isReadonly"
                      @change="scheduleSave"
                    />
                  </template>
                </el-table-column>

                <el-table-column v-if="table.dynamic" label="操作" fixed="right" width="64">
                  <template #default="{ row }">
                    <el-button
                      v-if="row.kind === 'data'"
                      link
                      type="danger"
                      size="small"
                      :disabled="isReadonly"
                      @click="removeRow(table, row.id)"
                    >
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </article>

          <article
            v-for="narrative in section.narratives ?? []"
            :key="narrative.id"
            class="narrative-block"
          >
            <header class="block-head">
              <div>
                <h4>{{ narrative.title }}</h4>
                <span>源区域：{{ narrative.sourceRows }}</span>
              </div>
              <el-button
                size="small"
                text
                type="primary"
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoading"
                @click="fillAiDraft(narrative)"
              >
                AI辅助
              </el-button>
            </header>
            <ul v-if="narrative.guidance?.length" class="guidance-list">
              <li v-for="tip in narrative.guidance" :key="tip">{{ tip }}</li>
            </ul>
            <el-input
              v-model="state.texts[narrative.id]"
              type="textarea"
              :rows="5"
              :disabled="isReadonly"
              :placeholder="narrative.placeholder"
              @change="onNarrativeChange"
            />
          </article>
        </div>
      </el-collapse-item>
    </el-collapse>

    <details class="prep-hint">
      <summary>编制逻辑与联动说明</summary>
      <ul>
        <li>保留源模板的实际层级：长期股权投资变动、子公司权益、合营/联营权益、共同经营；不再使用虚构的“五段统一13列表”。</li>
        <li>带“来源”的行对应 G7-4、G7-5、G7-10、G7-14、G7-16。点击「从源表取数」可从 G7-1/2/4/5/10/14/16 自动承接。</li>
        <li>提示、法规要求和示例文字只作为编制辅助；只有文本框中的项目实际披露内容会同步到附注模块。</li>
        <li>表格与文本统一保存到 checklist_responses，并通过正式 sync-from-workpaper 接口写入附注模块。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, toRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useDecimalCalc } from '@/composables/useDecimalCalc'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useG7MainAiGenerate } from '../../composables/useG7MainAiGenerate'
import {
  collectDisclosureTruncations,
  formatTruncationHint,
  G7_SOURCE_SAVED_EVENT,
  loadG7DisclosureSources,
  refreshListedTablesFromSources,
} from '../../composables/g7DisclosureCrossSheet'
import {
  G7_LISTED_DISCLOSURE_SECTIONS,
  buildG7ListedSyncData,
  createG7ListedDisclosureState,
  type G7DisclosureColumnType,
  type G7DisclosureNarrative,
  type G7DisclosureRow,
  type G7DisclosureTable,
  type G7DisclosureValue,
  type G7ListedDisclosureState,
} from './g7ListedDisclosureModel'

const ACCOUNT_CODE = '1511'
const RESPONSE_KEY = 'G7-main-disclosure-listed-v2'
const NOTE_SECTION_ID = '五、18'
const SHEET_NAME = '附注披露信息（上市公司）'

function resolveAuditYear(htmlData: Record<string, any> | null | undefined): number | undefined {
  const raw = htmlData?.project_context?.audit_year
    ?? htmlData?.project_context?.auditYear
    ?? htmlData?.audit_year
    ?? htmlData?.auditYear
  const year = Number(raw)
  return Number.isFinite(year) && year >= 2000 ? year : undefined
}
const SAVE_PHASE = {
  IDLE: 'idle',
  PENDING: 'pending',
  SAVING: 'saving',
  SAVED: 'saved',
  ERROR: 'error',
} as const
type SavePhase = typeof SAVE_PHASE[keyof typeof SAVE_PHASE]

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const sections = G7_LISTED_DISCLOSURE_SECTIONS
const state = reactive<G7ListedDisclosureState>(createG7ListedDisclosureState())
const hydrated = ref(false)
const isRefreshing = ref(false)
const lastRefreshHint = ref('')
let hydrateInFlight: Promise<void> | null = null
const isSyncing = ref(false)
const savePhase = ref<SavePhase>(SAVE_PHASE.IDLE)
const activeSections = ref(sections.map(section => section.id))
const adjudicatedAmount = ref<number | null>(null)
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG7MainAiGenerate(wpIdRef)
const { sum: decimalSum, sub: decimalSub } = useDecimalCalc()

let saveTimer: ReturnType<typeof setTimeout> | null = null
let sourceRefreshTimer: ReturnType<typeof setTimeout> | null = null
let hasLocalEdits = false
let loadedSavedPayload = false
const loadedVersion = ref('')

const tableCount = computed(() => sections.reduce((count, section) => count + (section.tables?.length ?? 0), 0))
const narrativeCount = computed(() => sections.reduce((count, section) => count + (section.narratives?.length ?? 0), 0))
const saveStatus = computed(() => ({
  idle: '',
  pending: '待保存',
  saving: '保存中…',
  saved: '已保存',
  error: '保存失败',
}[savePhase.value]))

const disclosureClosingTotal = computed(() => {
  const table = sections[0]?.tables?.find(item => item.id === 'investment-movement')
  const total = state.tables['investment-movement']?.find(row => row.id === 'investment-total')
  if (!table || !total) return 0
  return Number(computedCell(table, total, 'closingBook')) || 0
})

const reconciliationDiff = computed(() => {
  if (adjudicatedAmount.value == null) return 0
  return Number(decimalSub(disclosureClosingTotal.value, adjudicatedAmount.value))
})

function tableRows(table: G7DisclosureTable): G7DisclosureRow[] {
  return state.tables[table.id] ?? []
}

function tableRowClass({ row }: { row: G7DisclosureRow }): string {
  return `row-${row.kind ?? 'data'}`
}

function rowById(table: G7DisclosureTable, rowId: string): G7DisclosureRow | undefined {
  return tableRows(table).find(row => row.id === rowId)
}

function computedCell(
  table: G7DisclosureTable,
  row: G7DisclosureRow,
  columnKey: string,
  visited = new Set<string>(),
): G7DisclosureValue {
  if (row.diffRows?.length === 2) {
    if (visited.has(row.id)) return null
    visited.add(row.id)
    const [minuendId, subtrahendId] = row.diffRows
    const minuend = rowById(table, minuendId)
    const subtrahend = rowById(table, subtrahendId)
    const left = minuend ? Number(computedCell(table, minuend, columnKey, visited)) || 0 : 0
    const right = subtrahend ? Number(computedCell(table, subtrahend, columnKey, visited)) || 0 : 0
    return Number(decimalSub(left, right))
  }
  if (!row.sumRows?.length) return row.values[columnKey] ?? null
  if (visited.has(row.id)) return null
  visited.add(row.id)
  const values = row.sumRows.map(rowId => {
    const child = rowById(table, rowId)
    if (!child) return 0
    return Number(computedCell(table, child, columnKey, visited)) || 0
  })
  return Number(decimalSum(...values))
}

function fmtAmount(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatCell(value: G7DisclosureValue, type?: G7DisclosureColumnType): string {
  if (value == null || value === '') return '—'
  if (type === 'percent') {
    return `${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}%`
  }
  if (type === 'number') return fmtAmount(Number(value))
  return String(value)
}

function addRow(table: G7DisclosureTable, group: 'joint-venture' | 'associate' = 'associate'): void {
  if (props.isReadonly) return
  const rows = tableRows(table)
  if (rows.length >= (table.maxRows ?? 100)) return
  const dataRows = rows.filter(row => row.kind === 'data')
  const id = `${table.id}-manual-${Date.now()}-${dataRows.length + 1}`
  const values = Object.fromEntries(table.columns.map(column => [column.key, column.type === 'text' ? '' : null]))
  const nextRow: G7DisclosureRow = { id, label: '', values, kind: 'data' }

  if (table.id === 'investment-movement') {
    const subtotalId = group === 'joint-venture' ? 'joint-venture-subtotal' : 'associate-subtotal'
    const insertAt = rows.findIndex(row => row.id === subtotalId)
    if (insertAt >= 0) rows.splice(insertAt, 0, nextRow)
    else rows.push(nextRow)
    rows.find(row => row.id === subtotalId)?.sumRows?.push(id)
    scheduleSave()
    return
  }

  if (table.id === 'excess-losses') {
    const subtotalId = group === 'joint-venture' ? 'el-jv-subtotal' : 'el-assoc-subtotal'
    const insertAt = rows.findIndex(row => row.id === subtotalId)
    if (insertAt >= 0) rows.splice(insertAt, 0, nextRow)
    else rows.push(nextRow)
    rows.find(row => row.id === subtotalId)?.sumRows?.push(id)
    scheduleSave()
    return
  }

  const insertAt = rows.findIndex(row => row.kind === 'subtotal' || row.kind === 'total')
  if (insertAt >= 0) rows.splice(insertAt, 0, nextRow)
  else rows.push(nextRow)
  scheduleSave()
}

function removeRow(table: G7DisclosureTable, rowId: string): void {
  if (props.isReadonly) return
  const rows = tableRows(table)
  const index = rows.findIndex(row => row.id === rowId)
  if (index < 0) return
  rows.splice(index, 1)
  for (const totalRow of rows) {
    if (totalRow.sumRows) totalRow.sumRows = totalRow.sumRows.filter(id => id !== rowId)
  }
  scheduleSave()
}

function serialisableState(): G7ListedDisclosureState {
  return {
    version: 2,
    tables: Object.fromEntries(
      Object.entries(state.tables).map(([key, rows]) => [
        key,
        rows.map(row => ({
          ...row,
          values: { ...row.values },
          sumRows: row.sumRows ? [...row.sumRows] : undefined,
          diffRows: row.diffRows ? [...row.diffRows] as [string, string] : undefined,
        })),
      ]),
    ),
    texts: { ...state.texts },
    updatedAt: new Date().toISOString(),
  }
}

function scheduleSave(options?: { userEdit?: boolean }): void {
  if (props.isReadonly || !hydrated.value) return
  if (options?.userEdit !== false) hasLocalEdits = true
  savePhase.value = SAVE_PHASE.PENDING
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void persist(), 600)
}

async function refreshLoadedVersion(): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.get(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { _silent: true } as any,
    )
    const items = Array.isArray(res) ? res : (res as any)?.data ?? []
    const hit = items.find((item: any) => item.item_id === RESPONSE_KEY)
    loadedVersion.value = String(hit?.version || hit?.updated_at || '')
  } catch {
    // keep previous
  }
}

function captureVersionFromItem(item: any): void {
  if (!item) return
  const next = item.version || item.updated_at
  if (next) loadedVersion.value = String(next)
}

async function persist(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  savePhase.value = SAVE_PHASE.SAVING
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: RESPONSE_KEY,
        conclusion: null,
        remark: JSON.stringify(serialisableState()),
        ...(loadedVersion.value ? { if_match: loadedVersion.value } : {}),
      }],
    }, { _silent: true } as any)
    hasLocalEdits = false
    savePhase.value = SAVE_PHASE.SAVED
    await refreshLoadedVersion()
  } catch (err: any) {
    const status = err?.response?.status
    const detail = err?.response?.data?.detail
    if (status === 409 || detail?.code === 'version_conflict') {
      savePhase.value = SAVE_PHASE.ERROR
      ElMessage.error('披露数据已被他人修改，请刷新页面后重试')
      return
    }
    savePhase.value = SAVE_PHASE.ERROR
  }
}

function applySavedState(saved: Partial<G7ListedDisclosureState>): void {
  if (saved.version !== 2) return
  if (saved.tables && typeof saved.tables === 'object') {
    for (const [tableId, rows] of Object.entries(saved.tables)) {
      if (Array.isArray(rows) && tableId in state.tables) {
        state.tables[tableId] = rows.map(row => ({
          ...row,
          values: { ...(row.values ?? {}) },
          sumRows: row.sumRows ? [...row.sumRows] : undefined,
          diffRows: row.diffRows ? [...row.diffRows] as [string, string] : undefined,
        }))
      }
    }
  }
  if (saved.texts && typeof saved.texts === 'object') Object.assign(state.texts, saved.texts)
}

function parseSavedRemark(remark: unknown): boolean {
  if (typeof remark !== 'string' || !remark.trim()) return false
  try {
    const parsed = JSON.parse(remark)
    if (parsed?.version !== 2) return false
    applySavedState(parsed)
    return true
  } catch {
    return false
  }
}

function hydrateFromHtmlData(data: Record<string, any> | null): boolean {
  if (!data) return false
  const snapshot = data.responses_snapshot?.[RESPONSE_KEY]
  const loadedSnapshot = parseSavedRemark(snapshot?.remark)
  if (loadedSnapshot) {
    loadedSavedPayload = true
    captureVersionFromItem(snapshot)
  }

  const legacy = data.disclosureListed?.sections
  if (!loadedSnapshot && Array.isArray(legacy)) {
    const targets = [
      'impairment-method',
      'subsidiary-control-judgement',
      'jv-associate-judgement',
      'fund-transfer-restrictions',
      'joint-operation-basis',
    ]
    legacy.forEach((section: any, index: number) => {
      if (section?.textContent && targets[index]) state.texts[targets[index]] = String(section.textContent)
    })
  }
  applyAdjudicated(data.adjudicated_amount)
  return loadedSnapshot || Array.isArray(legacy)
}

async function hydrate(): Promise<void> {
  if (hydrated.value || hasLocalEdits) return
  if (hydrateInFlight) return hydrateInFlight
  hydrateInFlight = (async () => {
    try {
      const fromSeed = hydrateFromHtmlData(props.htmlData)
      if (!fromSeed && props.wpId) {
        try {
          const res = await api.get(
            `/api/workpapers/${props.wpId}/checklist-responses`,
            { _silent: true } as any,
          )
          const items = Array.isArray(res) ? res : (res as any)?.data ?? []
          const saved = items.find((item: any) => item.item_id === RESPONSE_KEY)
          if (parseSavedRemark(saved?.remark)) {
            loadedSavedPayload = true
            captureVersionFromItem(saved)
          }
        } catch {
          // 使用源模板初始结构，不阻塞编制。
        }
      } else if (fromSeed && !loadedVersion.value && props.wpId) {
        await refreshLoadedVersion()
      }
      hydrated.value = true
    } finally {
      hydrateInFlight = null
    }
  })()
  return hydrateInFlight
}

function allNarrativeText(): string {
  return sections.flatMap(section =>
    (section.narratives ?? [])
      .map(item => state.texts[item.id]?.trim()
        ? `【${item.title}】\n${state.texts[item.id].trim()}`
        : '')
      .filter(Boolean),
  ).join('\n\n')
}

function dispatchNoteUpdated(): void {
  window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
    detail: {
      accountCode: ACCOUNT_CODE,
      wpId: props.wpId,
      sheetName: SHEET_NAME,
      section: 'listed',
      sectionId: NOTE_SECTION_ID,
      text: allNarrativeText(),
      tableData: buildG7ListedSyncData(serialisableState()),
    },
  }))
}

function onNarrativeChange(): void {
  scheduleSave()
  dispatchNoteUpdated()
}

async function fillAiDraft(narrative: G7DisclosureNarrative): Promise<void> {
  if (props.isReadonly) return
  const generated = await generateAndConfirm(
    'disclosure-text',
    state.texts[narrative.id] || '',
    {
      sectionId: narrative.id,
      sectionTitle: narrative.title,
      sourceRows: narrative.sourceRows,
      disclosureType: 'listed',
      accountCode: ACCOUNT_CODE,
      instruction: narrative.placeholder,
    },
    `AI生成：${narrative.title}`,
  )
  if (!generated) return
  state.texts[narrative.id] = generated
  onNarrativeChange()
}

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId) return
  isSyncing.value = true
  try {
    await persist()
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      {
        wp_id: props.wpId,
        sheet_name: SHEET_NAME,
        section_id: NOTE_SECTION_ID,
        current_standard: 'listed',
        year: resolveAuditYear(props.htmlData as Record<string, any> | null),
        sub_table_data: buildG7ListedSyncData(serialisableState()),
      },
    )
    const data = result?.data ?? result
    dispatchNoteUpdated()
    ElMessage.success(`已同步 ${Number(data?.rows_synced ?? 0)} 行到附注模块「${NOTE_SECTION_ID} 长期股权投资」`)
  } catch {
    ElMessage.warning('同步附注失败，请检查附注章节映射后重试')
  } finally {
    isSyncing.value = false
  }
}

function handleAdjudicated(event: Event): void {
  const detail = (event as CustomEvent).detail
  if (detail?.accountCode !== ACCOUNT_CODE) return
  applyAdjudicated(detail.adjudicatedAmount)
}

function applyAdjudicated(raw: unknown): void {
  if (raw == null || raw === '') return
  const amount = Number(raw)
  if (Number.isFinite(amount)) adjudicatedAmount.value = amount
}

async function refreshFromSources(force = false): Promise<void> {
  if (isRefreshing.value || props.isReadonly || !props.wpId) return
  isRefreshing.value = true
  try {
    const bundle = await loadG7DisclosureSources({
      wpId: props.wpId,
      htmlData: props.htmlData as Record<string, unknown> | null,
    })
    const filled = refreshListedTablesFromSources(state.tables, bundle, force)
    const truncHint = formatTruncationHint(collectDisclosureTruncations(bundle, 'listed'))
    if (filled.length) {
      scheduleSave({ userEdit: false })
      lastRefreshHint.value = `已取数：${bundle.sourcesHit.join('/') || '无'} → ${filled.length} 表`
        + (truncHint ? `；${truncHint}` : '')
      if (force) {
        ElMessage.success(`已从 ${bundle.sourcesHit.join('、') || '源表'} 更新 ${filled.length} 张表`)
        if (truncHint) ElMessage.warning(truncHint)
      }
    } else if (force) {
      lastRefreshHint.value = bundle.sourcesHit.length
        ? `源表已读（${bundle.sourcesHit.join('/')}），无可更新空位`
        : '未找到 G7-1/2/4/5/10/14/16 源数据'
      ElMessage.warning(lastRefreshHint.value)
      if (truncHint) ElMessage.warning(truncHint)
    } else if (!bundle.sourcesHit.length) {
      lastRefreshHint.value = '暂无源表数据'
    } else if (truncHint) {
      lastRefreshHint.value = truncHint
    }
  } catch {
    lastRefreshHint.value = '源表取数失败'
    if (force) ElMessage.warning('从源表取数失败，请确认 G7-1/2/4/5/10/14/16 已保存')
  } finally {
    isRefreshing.value = false
  }
}

function handleSourceRowsSaved(event: Event): void {
  const detail = (event as CustomEvent).detail || {}
  if (props.projectId && detail.projectId && detail.projectId !== props.projectId) return
  if (!hydrated.value || props.isReadonly || hasLocalEdits) return
  if (sourceRefreshTimer) clearTimeout(sourceRefreshTimer)
  sourceRefreshTimer = setTimeout(() => {
    sourceRefreshTimer = null
    void refreshFromSources(false)
  }, 800)
}

watch(
  () => props.htmlData,
  data => {
    if (!hydrated.value && data) {
      void hydrate()
      return
    }
    // 允许迟到的 responses_snapshot 覆盖模板态（用户未编辑时）
    if (
      hydrated.value
      && !hasLocalEdits
      && !loadedSavedPayload
      && data?.responses_snapshot?.[RESPONSE_KEY]?.remark
    ) {
      if (parseSavedRemark(data.responses_snapshot[RESPONSE_KEY].remark)) {
        loadedSavedPayload = true
        captureVersionFromItem(data.responses_snapshot[RESPONSE_KEY])
      }
    }
    applyAdjudicated(data?.adjudicated_amount)
  },
  { immediate: true },
)

onMounted(() => {
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  window.addEventListener(G7_SOURCE_SAVED_EVENT, handleSourceRowsSaved)
  void hydrate().then(() => {
    if (!hasLocalEdits) void refreshFromSources(false)
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  window.removeEventListener(G7_SOURCE_SAVED_EVENT, handleSourceRowsSaved)
  if (saveTimer) clearTimeout(saveTimer)
  if (sourceRefreshTimer) clearTimeout(sourceRefreshTimer)
  if (savePhase.value === SAVE_PHASE.PENDING) void persist()
})
</script>

<style scoped>
.g7-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.objective,
.reconciliation {
  margin-bottom: 12px;
}

.toolbar,
.block-head,
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.toolbar {
  position: sticky;
  top: 0;
  z-index: 12;
  padding: 10px 12px;
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-bg-color);
}

.toolbar > div,
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.save-status {
  min-width: 48px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.sections :deep(.el-collapse-item__header) {
  min-height: 48px;
  height: auto;
}

.section-title {
  width: 100%;
  padding-right: 12px;
  font-size: 14px;
  font-weight: 600;
}

.section-body {
  padding: 4px 2px 14px;
}

.source-tip {
  margin-bottom: 8px;
}

.table-block,
.narrative-block {
  padding: 12px;
  margin: 0 0 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-bg-color);
}

.block-head {
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.add-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.block-head h4 {
  margin: 0 0 2px;
  font-size: 13px;
}

.block-head span,
.table-description,
.cell-source {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.table-description {
  margin: 0 0 8px;
}

.table-scroll {
  overflow-x: auto;
}

.disclosure-table {
  min-width: 100%;
}

.disclosure-table :deep(.el-input-number) {
  width: 100%;
}

.disclosure-table :deep(.row-subtotal td) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.disclosure-table :deep(.row-total td) {
  background: var(--el-color-primary-light-9);
  font-weight: 700;
}

.cell-source {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.computed-value {
  border-bottom: 1px dashed var(--el-color-success);
}

.guidance-list,
.prep-hint ul {
  margin: 0 0 8px;
  padding-left: 20px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.prep-hint {
  margin-top: 14px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.prep-hint summary {
  cursor: pointer;
}

@media (max-width: 900px) {
  .toolbar,
  .block-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
