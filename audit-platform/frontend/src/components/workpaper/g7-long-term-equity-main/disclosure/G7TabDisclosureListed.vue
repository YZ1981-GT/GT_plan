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
        <el-tooltip :disabled="g7ExtractionEnabled" content="四表取数未启用" placement="top">
          <el-button
            size="small"
            :disabled="isReadonly || !g7ExtractionEnabled"
            :loading="isSeedingFromFourTable"
            @click="handleSeedFromFourTable"
          >
            从四表库带入
          </el-button>
        </el-tooltip>
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
        <span class="chip-wrap"><GtIndexChip value="wp:G7-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-14" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-16" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-17" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${NOTE_SECTION_ID}`" :context-project-id="projectId" /></span>
        <el-dropdown
          split-button
          type="primary"
          size="small"
          :disabled="!projectId"
          @click="jumpToNote('listed')"
          @command="jumpToNote"
        >
          ↩ 跳转回附注（{{ NOTE_SECTION_ID }}）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="listed">上市版（五、18 长期股权投资）</el-dropdown-item>
              <el-dropdown-item command="soe">国企版（八、18 长期股权投资）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
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

    <WpDisclosureConsistencyPanel :results="consistencyChecks" :project-id="projectId" />

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
              <div class="block-head-main">
                <h4>{{ table.title }}</h4>
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
              <div v-if="table.slotConfig" class="add-row-actions">
                <el-button size="small" :disabled="isReadonly" @click="addSlotEntity(table.slotConfig)">
                  新增列
                </el-button>
                <el-tag
                  v-for="name in entitySlotNames(table.slotConfig)"
                  :key="name"
                  size="small"
                  class="slot-entity-tag"
                  closable
                  :disable-transitions="true"
                  @close="removeSlotEntity(table.slotConfig, name)"
                  @click="renameSlotEntity(table.slotConfig, name)"
                >
                  {{ name }}
                </el-tag>
              </div>
            </header>

            <p v-if="table.description" class="table-description">
              {{ table.description }}
            </p>

            <div class="table-meta">
              <span class="table-meta-label">数据来源</span>
              <el-tag size="small" type="info" effect="plain">
                Excel {{ table.sourceRows }}
              </el-tag>
              <el-tag
                v-for="src in tableMeta(table).unique"
                :key="src"
                size="small"
                effect="plain"
              >
                {{ src }}
              </el-tag>
            </div>

            <div class="table-scroll">
              <el-table
                :data="tableRows(table)"
                size="small"
                :row-class-name="tableRowClass"
                class="disclosure-table"
              >
                <el-table-column label="项目/被投资单位" fixed width="190">
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
                    </template>
                  </template>
                </el-table-column>

                <!--
                  两级表头：相邻同 `column.group` 的列合并到父表头下（对齐源模板合并单元格）。
                  分块逻辑在 `buildG7HeaderBlocks()`，与国企 Tab 同一份实现。
                  改造前此处是扁平 v-for、只读 label/width/type ⇒ `group` 是死代码，
                  源模板 11 张两级表在浏览器里全渲染成单层。
                -->
                <template v-for="(blk, bi) in headerBlocks(table)" :key="`blk-${bi}`">
                  <el-table-column v-if="blk.group" :label="blk.group" align="center">
                    <el-table-column
                      v-for="column in blk.columns"
                      :key="column.key"
                      :label="column.label"
                      :width="column.width"
                      min-width="118"
                      :align="column.type === 'text' ? 'left' : 'right'"
                    >
                      <template #default="{ row }">
                        <G7DisclosureCell
                          :row="row"
                          :column="column"
                          :mode="cellMode(row)"
                          :computed-text="cellComputedText(table, row, column)"
                          :readonly="isReadonly"
                          @change="scheduleSave"
                        />
                      </template>
                    </el-table-column>
                  </el-table-column>

                  <el-table-column
                    v-else
                    :label="blk.columns[0].label"
                    :width="blk.columns[0].width"
                    min-width="118"
                    :align="blk.columns[0].type === 'text' ? 'left' : 'right'"
                  >
                    <template #default="{ row }">
                      <G7DisclosureCell
                        :row="row"
                        :column="blk.columns[0]"
                        :mode="cellMode(row)"
                        :computed-text="cellComputedText(table, row, blk.columns[0])"
                        :readonly="isReadonly"
                        @change="scheduleSave"
                      />
                    </template>
                  </el-table-column>
                </template>

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

            <details
              v-if="tableMeta(table).showDetail"
              class="table-source-detail"
            >
              <summary>各行取数明细（{{ tableMeta(table).labeled.length }}）</summary>
              <ul class="source-detail-list">
                <li
                  v-for="item in tableMeta(table).labeled"
                  :key="`${item.label}-${item.source}`"
                >
                  <span class="source-detail-label">{{ item.label }}</span>
                  <span class="source-detail-value">{{ item.source }}</span>
                </li>
              </ul>
            </details>
          </article>

          <article
            v-for="narrative in section.narratives ?? []"
            :key="narrative.id"
            class="narrative-block"
          >
            <header class="block-head">
              <div class="block-head-main">
                <h4>{{ narrative.title }}</h4>
                <div class="table-meta table-meta--compact">
                  <span class="table-meta-label">数据来源</span>
                  <el-tag size="small" type="info" effect="plain">
                    Excel {{ narrative.sourceRows }}
                  </el-tag>
                </div>
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
        <li>带“来源”的行对应 G7-4、G7-5、G7-10、G7-14、G7-16。点击「从源表取数」可从 G7-1/2/4/5/10/14/16 自动承接；工具栏索引芯片可跳转源表或附注「{{ NOTE_SECTION_ID }}」。</li>
        <li>提示、法规要求和示例文字只作为编制辅助；只有文本框中的项目实际披露内容会同步到附注模块（底稿→附注单向，附注改动不回写底稿）。</li>
        <li>表格与文本统一保存到 checklist_responses，并通过正式 sync-from-workpaper 接口写入附注模块。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, toRef, watch, inject, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import { useDecimalCalc } from '@/composables/useDecimalCalc'
import {
  buildNoteJumpRoute,
  type DisclosureVariant,
} from '@/views/composables/noteDisclosureReverseJump'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
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
  buildG7ListedColumns,
  buildG7ListedSyncData,
  buildG7ListedSyncPayloads,
  markG7ListedSynced,
  createG7ListedDisclosureState,
  resolveG7ListedTableColumns,
  type G7DisclosureColumnType,
  type G7DisclosureNarrative,
  type G7DisclosureRow,
  type G7DisclosureTable,
  type G7DisclosureValue,
  type G7ListedDisclosureState,
} from './g7ListedDisclosureModel'
import { buildG7HeaderBlocks, type G7HeaderBlock } from './g7DisclosureHeaderBlocks'
import { describeSyncError, describeSyncTailFailure } from './g7DisclosureSyncFeedback'
import G7DisclosureCell from './G7DisclosureCell.vue'
// 🔴 列元数据收窄（数据风险闭合）：见 g7PayloadColumns.ts 顶部注释。
import { pickColumnsForPayload } from './g7PayloadColumns'
import { tableMetaSources } from './g7DisclosureTableMeta'
import { seedG7MovementFromLeafCategories, type G7LeafBucketSlot } from '../../composables/g7FourTableSeed'
// 🔴 科目码单一真源：运行态取宿主 provide 的 tb_source_codes（报表映射解析结果），
//    常量只作兜底。本文件不得出现字面量科目码（R11.1 / Property 15）。
import {
  g7AccountCode,
  isG7GrossCode,
} from '../../composables/g7AccountScope'
import type { TbSourceCodes } from '../../composables/shared/tbSourceCodes'
import WpDisclosureConsistencyPanel from '../../shared/disclosure/WpDisclosureConsistencyPanel.vue'
// 金额录入已下沉到 `G7DisclosureCell.vue`（两级表头改造），此处不再直接用 WpAmountInput；
// 样式 `.disclosure-table :deep(.el-input-number)` 仍对子组件渲染出的控件生效，故保留 CSS。
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { buildG7ConsistencyChecks, type G7ConsistencyInput } from '../../composables/g7DisclosureConsistency'

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

/** 四表取数溯源（宿主 provide）→ 科目码 */
const tbSourceCodes = inject<ComputedRef<TbSourceCodes | null>>(
  'g7TbSourceCodes',
  computed(() => null),
)
const accountCode = computed(() => g7AccountCode(tbSourceCodes.value))

const sections = G7_LISTED_DISCLOSURE_SECTIONS
const state = reactive<G7ListedDisclosureState>(createG7ListedDisclosureState())
const hydrated = ref(false)
const isRefreshing = ref(false)
const lastRefreshHint = ref('')
const isSeedingFromFourTable = ref(false)
const g7ExtractionEnabled = computed(() =>
  !!(props.htmlData as any)?.project_context?.g7_extraction_enabled,
)
let hydrateInFlight: Promise<void> | null = null
const isSyncing = ref(false)
const savePhase = ref<SavePhase>(SAVE_PHASE.IDLE)
const activeSections = ref(sections.map(section => section.id))
const adjudicatedAmount = ref<number | null>(null)
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG7MainAiGenerate(wpIdRef)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const { sum: decimalSum, sub: decimalSub } = useDecimalCalc()
const router = useRouter()

/** 反向跳转（仅导航，不改数据）：披露表 → 附注模块对应章节 */
function jumpToNote(variant: DisclosureVariant = 'listed'): void {
  const route = buildNoteJumpRoute(
    props.projectId,
    'G7',
    variant,
    resolveAuditYear(props.htmlData),
  )
  if (!route) {
    ElMessage.warning('未能解析附注章节，请确认项目上下文')
    return
  }
  void router.push(route)
}

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

const consistencyChecks = computed(() => {
  const mainRows = (state.tables['investment-movement'] ?? [])
    .filter(r => r.id !== 'investment-total' && !r.isStructure)
    .map(r => ({
      // 行名真源是 `G7DisclosureRow.label`（`state.tables` 存的是内部行模型，
      // `values` 只按**数据列 key** 存值、从不含标签键）⇒ 这里直接读 `r.label`。
      // 🔴 改造前写 `r.values?.['项目'] ?? r.label`：`'项目'` 既不是内部行模型的键、
      //    也不是（改造后的）载荷标签键 ⇒ 那是恒 undefined 的死 fallback。
      name: String(r.label ?? ''),
      openingBook: Number(r.values?.['openingBook'] ?? 0) || null,
      totalIncrease: (() => {
        const keys = ['addition', 'equityProfit', 'oci', 'otherEquity', 'other']
        const vals = keys.map(k => Number(r.values?.[k] ?? 0) || 0)
        const sum = vals.reduce((a, b) => a + b, 0)
        return sum || null
      })(),
      totalDecrease: (() => {
        const keys = ['reduction', 'dividend', 'impairment']
        const vals = keys.map(k => Number(r.values?.[k] ?? 0) || 0)
        const sum = vals.reduce((a, b) => a + b, 0)
        return sum || null
      })(),
      closingBook: Number(r.values?.['closingBook'] ?? 0) || null,
    }))

  const input: G7ConsistencyInput = {
    classificationRows: [],
    classificationSubtotal: null,
    classificationImpairment: null,
    classificationTotal: null,
    mainTableRows: mainRows,
    mainTableClosingTotal: disclosureClosingTotal.value || null,
    adjudicatedAmount: adjudicatedAmount.value,
    disclosureImpairmentEnd: null,
    g7_17ImpairmentTotal: null,
    excessLoss: null,
  }
  return buildG7ConsistencyChecks(input)
})

function tableRows(table: G7DisclosureTable): G7DisclosureRow[] {
  return state.tables[table.id] ?? []
}

/**
 * 该表的**有效**列集：无 `slotConfig` 时原样返回静态 `table.columns`；有 `slotConfig`
 * 时按 `state.entitySlots` 动态生成（Task 5.6，Property 18）。UI 渲染、`addRow` 新行取值、
 * `computedCell` 求和均须走它，不能再读 `table.columns`（会退回写死的默认实体名）。
 */
function tableColumns(table: G7DisclosureTable): G7DisclosureColumn[] {
  return resolveG7ListedTableColumns(table, state.entitySlots)
}

/**
 * 该表的表头块（两级表头渲染用）。分块实现在 `buildG7HeaderBlocks()`，
 * 与国企 Tab 共用一份，禁止在此另写一套按 group 归并的逻辑。
 */
function headerBlocks(table: G7DisclosureTable): G7HeaderBlock[] {
  return buildG7HeaderBlocks(tableColumns(table))
}

/**
 * 计算行判定 —— **保留上市 Tab 原语义**：仅 subtotal / total 不可录入
 * （国企 Tab 另含 `group` 分支，故该判定不下沉到单元格组件）。
 */
function cellMode(row: { kind?: string }): 'computed' | 'editable' {
  return row.kind === 'subtotal' || row.kind === 'total' ? 'computed' : 'editable'
}

/** 计算行显示文本（上市 Tab 无 `group` 行特例，逐字保留原表达式）。 */
function cellComputedText(
  table: G7DisclosureTable,
  row: { kind?: string },
  column: G7DisclosureColumn,
): string {
  return formatCell(computedCell(table, row as never, column.key), column.type)
}

function tableMeta(table: G7DisclosureTable) {
  return tableMetaSources(table, tableRows(table))
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

// 🔴 金额格式单一真源 = displayPrefs store 成员（不是模块级导出）
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

function fmtAmount(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return displayPrefs.fmtAmount(value)
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
  const values = Object.fromEntries(tableColumns(table).map(column => [column.key, column.type === 'text' ? '' : null]))
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

/** 该槎位当前的实体名清单（缺省回退默认清单，与 `resolveG7ListedTableColumns` 同源）。 */
function entitySlotNames(slotConfig: { slot: string }): string[] {
  return state.entitySlots?.[slotConfig.slot] ?? []
}

async function addSlotEntity(slotConfig: { slot: string }): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入新增实体名称（如公司名称）',
      '新增列',
      { confirmButtonText: '创建', cancelButtonText: '取消' },
    )
    const name = String(value ?? '').trim()
    if (!name) {
      ElMessage.warning('名称不能为空')
      return
    }
    const names = entitySlotNames(slotConfig)
    if (names.includes(name)) {
      ElMessage.warning('该名称已存在，请改用其它名称或先重命名现有列')
      return
    }
    if (!state.entitySlots) state.entitySlots = {}
    state.entitySlots[slotConfig.slot] = [...names, name]
    scheduleSave()
  } catch {
    // 用户取消
  }
}

async function renameSlotEntity(slotConfig: { slot: string }, current: string): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入新的实体名称',
      '修改列名',
      { inputValue: current, confirmButtonText: '保存', cancelButtonText: '取消' },
    )
    const name = String(value ?? '').trim()
    if (!name) {
      ElMessage.warning('名称不能为空')
      return
    }
    const names = entitySlotNames(slotConfig)
    if (name !== current && names.includes(name)) {
      ElMessage.warning('该名称已存在，请改用其它名称')
      return
    }
    if (!state.entitySlots) state.entitySlots = {}
    // 🔴 只改显示名，key 仍是 `{slot}_{seq}`（seq = 数组下标 + 1）不变，数据不因改名丢落点。
    state.entitySlots[slotConfig.slot] = names.map(n => (n === current ? name : n))
    scheduleSave()
  } catch {
    // 用户取消
  }
}

async function removeSlotEntity(slotConfig: { slot: string }, name: string): Promise<void> {
  if (props.isReadonly) return
  const names = entitySlotNames(slotConfig)
  if (names.length <= 1) {
    ElMessage.warning('至少保留一列')
    return
  }
  try {
    await ElMessageBox.confirm(`删除后「${name}」列的数据将同时清除，是否继续？`, '删除列', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  if (!state.entitySlots) return
  state.entitySlots[slotConfig.slot] = names.filter(n => n !== name)
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
    previouslySyncedTables: Object.fromEntries(
      Object.entries(state.previouslySyncedTables ?? {}).map(([k, v]) => [k, [...v]]),
    ),
    entitySlots: Object.fromEntries(
      Object.entries(state.entitySlots ?? {}).map(([k, v]) => [k, [...v]]),
    ),
  }
}

function scheduleSave(options?: { userEdit?: boolean }): void {
  if (props.isReadonly || !hydrated.value) return
  if (options?.userEdit !== false) hasLocalEdits = true
  savePhase.value = SAVE_PHASE.PENDING
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void persist(), 600)
}

async function handleSeedFromFourTable(): Promise<void> {
  if (isSeedingFromFourTable.value || props.isReadonly) return
  isSeedingFromFourTable.value = true
  try {
    const cats = (props.htmlData as any)?.tb_leaf_categories
    const buckets: Record<string, G7LeafBucketSlot> | null = cats?.buckets ?? null
    if (!buckets || !Object.keys(buckets).length) {
      ElMessage.info('四表库无长期股权投资分类数据（灰度未启用或科目无余额）')
      return
    }
    const TABLE_ID = 'investment-movement'
    const rows = state.tables[TABLE_ID]
    if (!rows?.length) {
      ElMessage.warning('主表行为空，请先初始化')
      return
    }
    const { filled, skipped } = seedG7MovementFromLeafCategories(rows, buckets)
    if (filled > 0) {
      scheduleSave({ userEdit: false })
      ElMessage.success(`已从四表库带入 ${filled} 个格子（跳过已有值 ${skipped} 个）`)
    } else {
      ElMessage.info(`四表库数据与主表无可填充交集（已有值 ${skipped} 个未覆盖）`)
    }
  } finally {
    isSeedingFromFourTable.value = false
  }
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
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
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
  if (saved.previouslySyncedTables && typeof saved.previouslySyncedTables === 'object') {
    state.previouslySyncedTables = Object.fromEntries(
      Object.entries(saved.previouslySyncedTables).map(([k, v]) => [k, Array.isArray(v) ? [...v] : []]),
    )
  }
  if (saved.entitySlots && typeof saved.entitySlots === 'object') {
    state.entitySlots = Object.fromEntries(
      Object.entries(saved.entitySlots).map(([k, v]) => [k, Array.isArray(v) ? [...v] : []]),
    )
  }
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
      accountCode: accountCode.value,
      projectId: props.projectId,
      wpId: props.wpId,
      sheetName: SHEET_NAME,
      section: 'listed',
      sectionId: NOTE_SECTION_ID,
      text: allNarrativeText(),
      tableData: buildG7ListedSyncData(serialisableState()),
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
      disclosureType: 'listed',
      accountCode: accountCode.value,
      instruction: narrative.placeholder,
    },
    `AI生成：${narrative.title}`,
  )
  if (!generated) return
  state.texts[narrative.id] = generated
  onNarrativeChange()
}

// 🔴 R8.1：改多章节 payload（对齐国企侧已有范式），不再把 15 张表全推 `五、18`
// （其中 14 张在该章节是孤儿表；子公司权益/合营联营权益/共同经营三区块归 `七、1`）。
async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId) return
  isSyncing.value = true
  try {
    // ── ① 真同步：失败 ⇒ 附注确实没落地 ────────────────────────────────
    // 🔴 与 ② 分段的理由见 `g7DisclosureSyncFeedback.ts`：原先一个 try 包住整条链 +
    //    裸 catch，国企侧实测「已同步 128 行到 14 个附注章节」与「同步附注失败」
    //    **同时出现**而库里已全部写入 ⇒ 失败提示是误报、指向根本没问题的章节映射，
    //    还诱使重复写库。两侧同款结构，一并改造。
    let data: any
    let payloads: ReturnType<typeof buildG7ListedSyncPayloads>
    try {
      await persist()
      payloads = buildG7ListedSyncPayloads(serialisableState())
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-batch-from-workpaper`,
        {
          wp_id: props.wpId,
          current_standard: 'listed',
          year: resolveAuditYear(props.htmlData as Record<string, any> | null),
          // 🔴 列元数据必须**按 payload 收窄**（不能传全量 map）：后端对
          // `_sub_table_columns` 是全量覆盖、对 `sub_table_data` 是按表名浅合并 ⇒
          // 传全量会把「本章节没推的表」的列也换成新 key，而它们的行仍是旧键 ⇒
          // 投影时行名整列变空（实测复现）。收窄后行与列恒在同一请求原子更新。
          items: payloads.map(payload => ({
            sheet_name: payload.sheetName,
            section_id: payload.noteSectionId,
            sub_table_data: payload.subTableData,
            columns: pickColumnsForPayload(
              payload.subTableData,
              buildG7ListedColumns(state.entitySlots),
            ),
          })),
        },
      )
      data = result?.data ?? result
    } catch (err: unknown) {
      // 请求被取消（防重复提交 / 组件卸载 / 竞争去重）→ 静默跳过，不误报「同步失败」
      const e = err as any
      if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError' || e?.__CANCEL__) return
      // 🔴 绝不吞异常：原始 err 进控制台，提示带真实原因（后端 detail / HTTP 状态）
      console.error('[G7 上市披露] 同步到附注失败（附注未落地）', err)
      ElMessage.error(`同步附注失败：${describeSyncError(err)}`)
      return
    }

    // ── ② 成功后的收尾：失败 ⇒ 附注**已落地**，绝不能报「同步失败」──────────
    const okText =
      `已同步 ${Number(data?.rows_synced ?? 0)} 行到 ` +
      `${Number(data?.sections_synced ?? payloads.length)} 个附注章节` +
      `（含 ${NOTE_SECTION_ID} 长期股权投资与 七、1 在其他主体中的权益）`
    try {
      state.previouslySyncedTables = markG7ListedSynced(serialisableState(), payloads)
      await persist()
      dispatchNoteUpdated()
      ElMessage.success(okText)
    } catch (err: unknown) {
      console.error('[G7 上市披露] 同步已落地，但同步基线回写失败', err)
      ElMessage.warning(describeSyncTailFailure(okText, err))
    }
  } finally {
    isSyncing.value = false
  }
}

function handleAdjudicated(event: Event): void {
  const detail = (event as CustomEvent).detail
  if (!isG7GrossCode(detail?.accountCode, tbSourceCodes.value)) return
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
    const filled = refreshListedTablesFromSources(state.tables, bundle, force, state.texts)
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
        : '未找到 G7-2/4/5/10/14/16 源数据'
      ElMessage.warning(lastRefreshHint.value)
      if (truncHint) ElMessage.warning(truncHint)
    } else if (!bundle.sourcesHit.length) {
      lastRefreshHint.value = '暂无源表数据'
    } else if (truncHint) {
      lastRefreshHint.value = truncHint
    }
  } catch {
    lastRefreshHint.value = '源表取数失败'
    if (force) ElMessage.warning('从源表取数失败，请确认 G7-2/4/5/10/14/16 已保存')
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
  autoSync.cancelPending()
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
  border-radius: 8px;
  background: var(--el-bg-color);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
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
  padding: 14px 16px;
  margin: 0 0 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}

.block-head {
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.block-head-main {
  flex: 1;
  min-width: 0;
}

.add-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
  flex-shrink: 0;
}

.block-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.table-description {
  margin: 0 0 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.table-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-extra-light);
}

.table-meta--compact {
  margin: 6px 0 0;
  padding: 6px 8px;
}

.table-meta-label {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.table-source-detail {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-blank);
  border: 1px dashed var(--el-border-color-lighter);
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.table-source-detail summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.source-detail-list {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.source-detail-list li {
  display: flex;
  gap: 8px;
  padding: 3px 0;
  line-height: 1.5;
}

.source-detail-label {
  flex-shrink: 0;
  min-width: 88px;
  color: var(--el-text-color-regular);
}

.source-detail-value {
  color: var(--el-text-color-secondary);
}

.table-scroll {
  overflow-x: auto;
  border-radius: 6px;
}

.disclosure-table {
  min-width: 100%;
}

/* 去掉默认 border 的厚重感，改用轻量分隔 */
.disclosure-table :deep(.el-table__inner-wrapper) {
  border-radius: 6px;
}

.disclosure-table :deep(th.el-table__cell) {
  background: var(--el-fill-color-lighter) !important;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  padding: 8px 6px;
}

.disclosure-table :deep(td.el-table__cell) {
  padding: 6px 6px;
}

.disclosure-table :deep(.el-input-number) {
  width: 100%;
}

.disclosure-table :deep(.el-input-number .el-input__inner) {
  font-size: 12px;
}

.disclosure-table :deep(.el-input .el-input__inner) {
  font-size: 12px;
}

.disclosure-table :deep(.row-subtotal td) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.disclosure-table :deep(.row-total td) {
  background: var(--el-color-primary-light-9);
  font-weight: 700;
}

.disclosure-table :deep(.row-group td) {
  background: var(--el-fill-color-lighter);
  font-weight: 600;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.computed-value {
  border-bottom: 1px dashed var(--el-color-success);
  cursor: help;
}

.guidance-list,
.prep-hint ul {
  margin: 0 0 8px;
  padding-left: 20px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.8;
}

.prep-hint {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}

@media (max-width: 900px) {
  .toolbar,
  .block-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
