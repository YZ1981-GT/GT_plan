<template>
  <div class="g7-soe">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按源模板 A1:Q355 编制国企披露。前半部分服务「七、合并范围的变化」多个子节，后半部分服务「八、18 长期股权投资」；表格、提示、示例与正式文本分开处理，并与 G7-1/2/4/5/11/16 及附注模块多目标联动。
    </el-alert>

    <div class="toolbar">
      <div>
        <strong>附注披露信息（国企）</strong>
        <el-tag size="small" type="info" effect="plain">源模板 355 行</el-tag>
        <el-tag size="small" type="success" effect="plain">结构化表格 {{ tableCount }} 个</el-tag>
        <el-tag size="small" type="warning" effect="plain">披露文本 {{ narrativeCount }} 个</el-tag>
        <el-tag size="small" effect="plain">附注目标 {{ syncTargetCount }} 个</el-tag>
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
        <span class="chip-wrap"><GtIndexChip value="wp:G7-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-5" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-8" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-9" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-12" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-14" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-16" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="Note:八、18" :context-project-id="projectId" /></span>
      </div>
    </div>

    <el-alert
      v-if="adjudicatedAmount != null"
      :type="reconciliationDiff === 0 ? 'success' : 'warning'"
      :closable="false"
      class="reconciliation"
    >
      1511审定数：{{ fmtAmount(adjudicatedAmount) }}；
      披露分类净额（G7-1勾稽行）：{{ fmtAmount(disclosureClosingTotal) }}；
      差异：{{ fmtAmount(reconciliationDiff) }}。
      <span v-if="reconciliationDiff !== 0">请核对子公司/合营/联营分类及减值口径。</span>
    </el-alert>

    <el-skeleton v-if="!hydrated" :rows="12" animated />

    <template v-else>
      <section
        v-for="chapter in chapters"
        :key="chapter.id"
        class="chapter"
      >
        <header class="chapter-head">
          <div>
            <h3>{{ chapter.title }}</h3>
            <p>{{ chapter.subtitle }}</p>
          </div>
          <el-tag :type="chapter.tagType" effect="plain">{{ chapter.range }}</el-tag>
        </header>

        <el-collapse v-model="activeSections" class="sections">
          <el-collapse-item
            v-for="section in chapter.sections"
            :key="section.id"
            :name="section.id"
          >
            <template #title>
              <div class="section-title">
                <span>{{ section.title }}</span>
                <el-tag size="small" effect="plain">Excel {{ section.sourceRows }}</el-tag>
                <span class="chip-wrap">
                  <GtIndexChip
                    :value="`Note:${section.noteSectionId}`"
                    :context-project-id="projectId"
                  />
                </span>
                <GtReviewTrigger :section-id="`G7-disclosure-soe-${section.id}`" />
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
                    <template v-if="table.id === 'lte-movement' || table.id === 'unrecognized-losses'">
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
                      新增行
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
                    <el-table-column label="项目/企业名称" fixed width="230">
                      <template #default="{ row }">
                        <template v-if="row.kind === 'subtotal' || row.kind === 'total' || row.kind === 'group'">
                          <strong>{{ row.label }}</strong>
                        </template>
                        <template v-else>
                          <el-input
                            v-model="row.label"
                            size="small"
                            :disabled="isReadonly"
                            placeholder="名称/项目"
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
                      min-width="120"
                      :align="column.type === 'text' ? 'left' : 'right'"
                    >
                      <template #default="{ row }">
                        <span
                          v-if="row.kind === 'subtotal' || row.kind === 'total' || row.kind === 'group'"
                          class="computed-value"
                        >
                          {{
                            row.kind === 'group'
                              ? '—'
                              : formatCell(computedCell(table, row, column.key), column.type)
                          }}
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
      </section>
    </template>

    <details class="prep-hint">
      <summary>编制逻辑与联动说明</summary>
      <ul>
        <li>A6:M199 对应附注「七、合并范围的变化」多个子节；A200:M355 对应「八、18 长期股权投资」。</li>
        <li>同步时按 noteSectionId 拆成多份载荷分别写入附注模块（底稿→附注单向，附注改动不回写底稿）。各区块标题旁 Note 芯片可跳转对应附注节。</li>
        <li>带“来源”的行对应 G7-1/2/4/5/8/9/10/11/14/16；工具栏索引芯片可跳转源表；「从源表取数」自动承接。提示与示例文字不进入附注正文。</li>
        <li>表格与文本统一保存到 checklist_responses（G7-main-disclosure-soe-v2）。</li>
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
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7MainAiGenerate } from '../../composables/useG7MainAiGenerate'
import {
  collectDisclosureTruncations,
  formatTruncationHint,
  G7_SOURCE_SAVED_EVENT,
  loadG7DisclosureSources,
  refreshSoeTablesFromSources,
} from '../../composables/g7DisclosureCrossSheet'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeSyncPayloads,
  createG7SoeDisclosureState,
  g7SoeChapterSections,
  type G7DisclosureColumnType,
  type G7DisclosureNarrative,
  type G7DisclosureRow,
  type G7DisclosureTable,
  type G7DisclosureValue,
  type G7SoeDisclosureState,
} from './g7SoeDisclosureModel'

const ACCOUNT_CODE = '1511'
const RESPONSE_KEY = 'G7-main-disclosure-soe-v2'
const SHEET_NAME = '附注披露信息（国企）'
const CURRENT_STANDARD = 'soe'

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

const sections = G7_SOE_DISCLOSURE_SECTIONS
const state = reactive<G7SoeDisclosureState>(createG7SoeDisclosureState())
const hydrated = ref(false)
const isSyncing = ref(false)
const isRefreshing = ref(false)
const lastRefreshHint = ref('')
let hydrateInFlight: Promise<void> | null = null
const savePhase = ref<SavePhase>(SAVE_PHASE.IDLE)
const activeSections = ref<string[]>(
  sections[0] ? [sections[0].id] : [],
)
const adjudicatedAmount = ref<number | null>(null)
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG7MainAiGenerate(wpIdRef)
const { sum: decimalSum, sub: decimalSub } = useDecimalCalc()

let saveTimer: ReturnType<typeof setTimeout> | null = null
let sourceRefreshTimer: ReturnType<typeof setTimeout> | null = null
let hasLocalEdits = false
let loadedSavedPayload = false
const loadedVersion = ref('')

const chapters = computed(() => [
  {
    id: 'consolidation-scope',
    title: '七、企业合并及合并财务报表',
    subtitle: '同步目标：附注模块「合并范围的变化」各子节',
    range: 'Excel A6:M199',
    tagType: 'warning' as const,
    sections: g7SoeChapterSections('consolidation-scope'),
  },
  {
    id: 'long-term-equity',
    title: '八、财务报表主要项目注释 · 18 长期股权投资',
    subtitle: '同步目标：附注模块「八、18 长期股权投资」',
    range: 'Excel A200:M355',
    tagType: 'success' as const,
    sections: g7SoeChapterSections('long-term-equity'),
  },
])

const tableCount = computed(() => sections.reduce((count, section) => count + (section.tables?.length ?? 0), 0))
const narrativeCount = computed(() => sections.reduce((count, section) => count + (section.narratives?.length ?? 0), 0))
const syncTargetCount = computed(() => new Set(sections.map(section => section.noteSectionId)).size)
const saveStatus = computed(() => ({
  idle: '',
  pending: '待保存',
  saving: '保存中…',
  saved: '已保存',
  error: '保存失败',
}[savePhase.value]))

const disclosureClosingTotal = computed(() => {
  const table = sections
    .flatMap(section => section.tables ?? [])
    .find(item => item.id === 'lte-classification')
  const total = state.tables['lte-classification']?.find(row => row.id === 'lte-total')
  if (!table || !total) return 0
  return Number(computedCell(table, total, 'closing')) || 0
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

  if (table.id === 'lte-movement') {
    const markerId = group === 'joint-venture' ? 'mv-assoc-group' : 'mv-total'
    const insertAt = rows.findIndex(row => row.id === markerId)
    if (insertAt >= 0) rows.splice(insertAt, 0, nextRow)
    else rows.push(nextRow)
    rows.find(row => row.id === 'mv-total')?.sumRows?.push(id)
    scheduleSave()
    return
  }

  if (table.id === 'unrecognized-losses') {
    const subtotalId = group === 'joint-venture' ? 'ul-jv-subtotal' : 'ul-assoc-subtotal'
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

  if (table.id === 'sponsor-income') {
    rows.find(row => row.id === 'si-total')?.sumRows?.push(id)
  }
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

function serialisableState(): G7SoeDisclosureState {
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

function applySavedState(saved: Partial<G7SoeDisclosureState>): void {
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

  const legacy = data.disclosureSOE?.sections
  if (!loadedSnapshot && Array.isArray(legacy)) {
    const targets = [
      'holding-voting-diff',
      'sale-date-method',
      'group-asset-restrictions',
      'ownership-change-description',
      'lte-holding-voting-diff',
      'fund-transfer-restrictions',
      'unconsolidated-structured-basic',
      'sponsor-determination',
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
        ? `【${section.noteSectionId} · ${item.title}】\n${state.texts[item.id].trim()}`
        : '')
      .filter(Boolean),
  ).join('\n\n')
}

function dispatchNoteUpdated(): void {
  const payloads = buildG7SoeSyncPayloads(serialisableState())
  window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
    detail: {
      accountCode: ACCOUNT_CODE,
      projectId: props.projectId,
      wpId: props.wpId,
      sheetName: SHEET_NAME,
      section: 'soe',
      sectionIds: payloads.map(p => p.noteSectionId),
      payloads,
      text: allNarrativeText(),
      timestamp: Date.now(),
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
      disclosureType: 'soe',
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
    const payloads = buildG7SoeSyncPayloads(serialisableState())
    const result: any = await api.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-batch-from-workpaper`,
      {
        wp_id: props.wpId,
        current_standard: CURRENT_STANDARD,
        year: resolveAuditYear(props.htmlData as Record<string, any> | null),
        items: payloads.map(payload => ({
          sheet_name: SHEET_NAME,
          section_id: payload.noteSectionId,
          sub_table_data: payload.subTableData,
        })),
      },
    )
    const data = result?.data ?? result
    dispatchNoteUpdated()
    ElMessage.success(
      `已同步 ${Number(data?.rows_synced ?? 0)} 行到 ${Number(data?.sections_synced ?? payloads.length)} 个附注章节（含合并范围变化与八、18）`,
    )
  } catch {
    ElMessage.warning('同步附注失败，请检查国企附注章节映射后重试')
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
    const filled = refreshSoeTablesFromSources(state.tables, bundle, force, state.texts)
    const truncHint = formatTruncationHint(collectDisclosureTruncations(bundle, 'soe'))
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
        : '未找到 G7-1/2/4/5/8/9/10/12/14/16 源数据'
      ElMessage.warning(lastRefreshHint.value)
      if (truncHint) ElMessage.warning(truncHint)
    } else if (!bundle.sourcesHit.length) {
      lastRefreshHint.value = '暂无源表数据'
    } else if (truncHint) {
      lastRefreshHint.value = truncHint
    }
  } catch {
    lastRefreshHint.value = '源表取数失败'
    if (force) ElMessage.warning('从源表取数失败，请确认相关源表已保存')
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
.g7-soe {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.objective,
.reconciliation {
  margin-bottom: 12px;
}

.toolbar,
.block-head,
.section-title,
.chapter-head {
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
  flex-wrap: wrap;
}

.chip-wrap {
  display: inline-flex;
  align-items: center;
}

.save-status {
  min-width: 48px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.chapter {
  margin-bottom: 18px;
}

.chapter-head {
  margin-bottom: 8px;
  padding: 8px 2px;
}

.chapter-head h3 {
  margin: 0 0 2px;
  font-size: 15px;
}

.chapter-head p {
  margin: 0;
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
  flex-wrap: wrap;
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

.disclosure-table :deep(.row-group td) {
  background: var(--el-fill-color);
  font-weight: 600;
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
  .block-head,
  .chapter-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
