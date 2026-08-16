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
        <el-dropdown size="small" trigger="click" @command="onImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData" :disabled="isReadonly">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="importFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onImportFileChange" />
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
        <span class="chip-wrap"><GtIndexChip value="wp:G7-8" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-9" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-12" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-14" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G7-16" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="Note:八、18" :context-project-id="projectId" /></span>
        <el-dropdown
          split-button
          type="primary"
          size="small"
          :disabled="!projectId"
          @click="jumpToNote('soe')"
          @command="jumpToNote"
        >
          ↩ 跳转回附注（八、18）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="soe">国企版（八、18 长期股权投资）</el-dropdown-item>
              <el-dropdown-item command="listed">上市版（五、18 长期股权投资）</el-dropdown-item>
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
      披露分类净额（G7-1勾稽行）：{{ fmtAmount(disclosureClosingTotal) }}；
      差异：{{ fmtAmount(reconciliationDiff) }}。
      <span v-if="reconciliationDiff !== 0">请核对子公司/合营/联营分类及减值口径。</span>
    </el-alert>

    <WpDisclosureConsistencyPanel :results="consistencyChecks" :project-id="projectId" />

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
                  <div class="block-head-main">
                    <h4>{{ table.title }}</h4>
                  </div>
                  <div v-if="table.dynamic" class="add-row-actions">
                    <template v-if="table.slotConfig">
                      <el-button size="small" :disabled="isReadonly" @click="addSlotEntity(table.slotConfig)">
                        新增列
                      </el-button>
                      <el-tag
                        v-for="name in entitySlotNames(table.slotConfig)"
                        :key="name"
                        size="small"
                        closable
                        :disable-transitions="true"
                        @close="removeSlotEntity(table.slotConfig, name)"
                        @click="renameSlotEntity(table.slotConfig, name)"
                      >
                        {{ name }}
                      </el-tag>
                    </template>
                    <template v-else-if="table.id === 'lte-movement' || table.id === 'unrecognized-losses'">
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
                    <el-table-column label="项目/企业名称" fixed width="190">
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
                        </template>
                      </template>
                    </el-table-column>

                    <!--
                      两级表头：相邻同 `column.group` 的列合并到父表头下（对齐源模板合并
                      单元格）。分块逻辑在 `buildG7HeaderBlocks()`，与上市 Tab 同一份实现。
                      改造前此处是扁平 v-for、只读 label/width/type ⇒ `group` 是死代码，
                      源模板 13 张两级表在浏览器里全渲染成单层（5 组一样的「期末数|期初数」
                      分不清属于哪家公司）。
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
  refreshSoeTablesFromSources,
} from '../../composables/g7DisclosureCrossSheet'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeColumns,
  buildG7SoeSyncPayloads,
  markG7SoeSynced,
  createG7SoeDisclosureState,
  g7SoeChapterSections,
  resolveG7SoeTableColumns,
  type G7DisclosureColumnType,
  type G7DisclosureNarrative,
  type G7DisclosureRow,
  type G7DisclosureTable,
  type G7DisclosureValue,
  type G7SoeDisclosureState,
} from './g7SoeDisclosureModel'
import { buildG7HeaderBlocks, type G7HeaderBlock } from './g7DisclosureHeaderBlocks'
import { describeSyncError, describeSyncTailFailure } from './g7DisclosureSyncFeedback'
import G7DisclosureCell from './G7DisclosureCell.vue'
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

const RESPONSE_KEY = 'G7-main-disclosure-soe-v2'
const SHEET_NAME = '附注披露信息（国企）'
const CURRENT_STANDARD = 'soe'
// 列头元数据（disclosure-table-sync-convergence）：全部 SOE 子表键 → ColumnDef
const soeColumns = buildG7SoeColumns()

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

const sections = G7_SOE_DISCLOSURE_SECTIONS
const state = reactive<G7SoeDisclosureState>(createG7SoeDisclosureState())
const hydrated = ref(false)
const isSyncing = ref(false)
const isRefreshing = ref(false)
const lastRefreshHint = ref('')
const isSeedingFromFourTable = ref(false)
const g7ExtractionEnabled = computed(() =>
  !!(props.htmlData as any)?.project_context?.g7_extraction_enabled,
)
let hydrateInFlight: Promise<void> | null = null
const savePhase = ref<SavePhase>(SAVE_PHASE.IDLE)
const activeSections = ref<string[]>(
  sections[0] ? [sections[0].id] : [],
)
const adjudicatedAmount = ref<number | null>(null)
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG7MainAiGenerate(wpIdRef)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const { sum: decimalSum, sub: decimalSub } = useDecimalCalc()
const router = useRouter()
const importFileRef = ref<HTMLInputElement | null>(null)

/** 反向跳转（仅导航，不改数据）：披露表 → 附注模块对应章节；「七、」各子节由区块内 Note 芯片跳转 */
function jumpToNote(variant: DisclosureVariant = 'soe'): void {
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

const consistencyChecks = computed(() => {
  // 国企分类表：从 lte-classification 表提取行
  const classRows = (state.tables['lte-classification'] ?? [])
    .filter(r => !r.isStructure && r.id !== 'lte-subtotal' && r.id !== 'lte-impairment' && r.id !== 'lte-total')
  const classSubtotalRow = (state.tables['lte-classification'] ?? []).find(r => r.id === 'lte-subtotal')
  const classImpairmentRow = (state.tables['lte-classification'] ?? []).find(r => r.id === 'lte-impairment')
  const classTotalRow = (state.tables['lte-classification'] ?? []).find(r => r.id === 'lte-total')

  // 主表（明细表）：从 lte-detail 表提取行
  const mainRows = (state.tables['lte-detail'] ?? [])
    .filter(r => r.id !== 'lte-detail-total' && !r.isStructure)
    .map(r => ({
      // 行名真源是 `G7DisclosureRow.label`（同 listed 侧）；`values` 只存数据列。
      // 🔴 `r.values?.['项目']` 是恒 undefined 的死 fallback，已移除。
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

  const mainTotal = (state.tables['lte-detail'] ?? []).find(r => r.id === 'lte-detail-total')
  const mainClosingTotal = mainTotal ? (Number(mainTotal.values?.['closingBook'] ?? 0) || null) : null

  const input: G7ConsistencyInput = {
    classificationRows: classRows.map(r => ({
      label: String(r.label ?? ''),
      endAmount: Number(r.values?.['closing'] ?? 0) || null,
    })),
    classificationSubtotal: classSubtotalRow ? (Number(classSubtotalRow.values?.['closing'] ?? 0) || null) : null,
    classificationImpairment: classImpairmentRow ? (Number(classImpairmentRow.values?.['closing'] ?? 0) || null) : null,
    classificationTotal: classTotalRow ? (Number(classTotalRow.values?.['closing'] ?? 0) || null) : null,
    mainTableRows: mainRows,
    mainTableClosingTotal: mainClosingTotal,
    adjudicatedAmount: adjudicatedAmount.value,
    disclosureImpairmentEnd: classImpairmentRow ? (Number(classImpairmentRow.values?.['closing'] ?? 0) || null) : null,
    g7_17ImpairmentTotal: null,
    excessLoss: null,
  }
  return buildG7ConsistencyChecks(input)
})

function tableRows(table: G7DisclosureTable): G7DisclosureRow[] {
  return state.tables[table.id] ?? []
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
  const values = Object.fromEntries(effectiveColumns(table).map(column => [column.key, column.type === 'text' ? '' : null]))
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

// ── 动态列（按被投资单位/公司横向展开）管理 ──────────────────────────────
// Task 5.6 / Property 18：列数由数据决定，key 稳定 {slot}_{seq}，改名只改 label。

/** 该槎位当前的实体名清单（缺省回退默认清单，与 resolveG7SoeTableColumns 同源）。 */
function entitySlotNames(slotConfig: { slot: string }): string[] {
  return state.entitySlots?.[slotConfig.slot] ?? []
}

/**
 * 该表的表头块（两级表头渲染用）。分块实现在 `buildG7HeaderBlocks()`，
 * 与上市 Tab 共用一份，禁止在此另写一套按 group 归并的逻辑。
 */
function headerBlocks(table: G7DisclosureTable): G7HeaderBlock[] {
  return buildG7HeaderBlocks(effectiveColumns(table))
}

/**
 * 计算行判定 —— **保留国企 Tab 原语义**：`kind` 为 subtotal / total / group 都不可录入。
 * 单元格组件不自作判断（上市 Tab 不含 group 分支，下沉会串味）。
 */
function cellMode(row: { kind?: string }): 'computed' | 'editable' {
  return row.kind === 'subtotal' || row.kind === 'total' || row.kind === 'group'
    ? 'computed'
    : 'editable'
}

/** 计算行显示文本 —— 国企 Tab 的 `group` 行显示 `—`（原语义逐字保留）。 */
function cellComputedText(
  table: G7DisclosureTable,
  row: { kind?: string },
  column: G7DisclosureColumn,
): string {
  if (row.kind === 'group') return '—'
  return formatCell(computedCell(table, row as never, column.key), column.type)
}

/** 解析某表的有效列集（slotConfig 时动态生成）。 */
function effectiveColumns(table: G7DisclosureTable) {
  return resolveG7SoeTableColumns(table, state.entitySlots)
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
    // 🔴 只改显示名，key 仍是 `{slot}_{seq}` 不变，数据不因改名丢落点。
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
    previouslySyncedTables: state.previouslySyncedTables ? { ...state.previouslySyncedTables } : undefined,
    entitySlots: state.entitySlots
      ? Object.fromEntries(Object.entries(state.entitySlots).map(([k, v]) => [k, [...v]]))
      : undefined,
  }
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────
const DISCLOSURE_SHEET_CODE = 'disclosure-soe'

function onImportExportCommand(command: string): void {
  switch (command) {
    case 'exportTemplate':
      doExportTemplate()
      break
    case 'exportData':
      doExportData()
      break
    case 'importData':
      importFileRef.value?.click()
      break
  }
}

/** 区分 404（后端未实现）vs 其他错误，给出友好提示 */
function handleImportExportError(err: any, action: string): void {
  const status = err?.response?.status
  if (status === 404 || status === 422) {
    ElMessage.info(`${action}功能开发中，敬请期待`)
  } else {
    const msg = err?.response?.data?.detail || err?.response?.data?.message || `${action}失败`
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
}

async function doExportTemplate(): Promise<void> {
  try {
    const response = await api.post(
      `/api/workpapers/${props.wpId}/g7-main/export-template`,
      null,
      { params: { sheet: DISCLOSURE_SHEET_CODE }, responseType: 'blob' },
    )
    const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'G7_附注披露信息（国企）_模板.xlsx'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('模板已导出')
  } catch (err: any) {
    handleImportExportError(err, '导出模板')
  }
}

async function doExportData(): Promise<void> {
  try {
    const response = await api.post(
      `/api/workpapers/${props.wpId}/g7-main/export-data`,
      null,
      { params: { sheet: DISCLOSURE_SHEET_CODE }, responseType: 'blob' },
    )
    const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'G7_附注披露信息（国企）_数据.xlsx'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('数据已导出')
  } catch (err: any) {
    handleImportExportError(err, '导出数据')
  }
}

async function onImportFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    const response: any = await api.post(
      `/api/workpapers/${props.wpId}/g7-main/import-data`,
      formData,
      { params: { sheet: DISCLOSURE_SHEET_CODE }, headers: { 'Content-Type': 'multipart/form-data' } },
    )
    const data = response?.data ?? response
    const count = data?.imported_count ?? data?.rowCount ?? 0
    ElMessage.success(`导入完成，共 ${count} 行`)
    await hydrate()
  } catch (err: any) {
    handleImportExportError(err, '导入数据')
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
    const TABLE_ID = 'lte-movement'
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
  // 🔴 必须恢复 `previouslySyncedTables`（Task 13）：`serialisableState()` 一直在
  // 持久化它，但改造前**载入时不读回** ⇒ 每次打开底稿基线都退回 `{}`，
  // 差集恒空、`_removed_table_keys` 永不上报（写了也白写）。
  if (saved.previouslySyncedTables && typeof saved.previouslySyncedTables === 'object') {
    state.previouslySyncedTables = Object.fromEntries(
      Object.entries(saved.previouslySyncedTables).map(([k, v]) => [
        k,
        Array.isArray(v) ? [...v] : [],
      ]),
    )
  }
  if (saved.entitySlots && typeof saved.entitySlots === 'object') {
    if (!state.entitySlots) state.entitySlots = {}
    for (const [slot, names] of Object.entries(saved.entitySlots)) {
      if (Array.isArray(names)) state.entitySlots[slot] = [...names]
    }
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
      accountCode: accountCode.value,
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
      accountCode: accountCode.value,
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
    // ── ① 真同步：失败 ⇒ 附注确实没落地 ────────────────────────────────
    // 🔴 与 ② 分段的理由见 `g7DisclosureSyncFeedback.ts`：原先一个 try 包住整条链 +
    //    裸 catch，实测「已同步 128 行到 14 个附注章节」与「同步附注失败，请检查国企
    //    附注章节映射」**同时出现**，而库里 13 章节全部写入 ⇒ 失败提示是误报，
    //    还把排查方向指向根本没问题的章节映射，并诱使重复写库。
    let data: any
    let payloads: ReturnType<typeof buildG7SoeSyncPayloads>
    try {
      await persist()
      payloads = buildG7SoeSyncPayloads(serialisableState())
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-batch-from-workpaper`,
        {
          wp_id: props.wpId,
          current_standard: CURRENT_STANDARD,
          year: resolveAuditYear(props.htmlData as Record<string, any> | null),
        // 🔴 列元数据必须按 payload 实含表名收窄（`pickColumnsForPayload`）：
        // 原实现给每个 section 都发**全部 23 张表**的列定义，于是 A 章节的记录里也被
        // 写入 B 章节表的列头。B 类改 key 后这会让「列已是 label / 行还是 `项目`」
        // 的错配窗口从「本章节」放大到「任何被同步过的章节」，而投影器兜底是
        // **单向**的（只能 label→旧 key，不能旧 key→label）⇒ 存量行名会读成空。
          items: payloads.map(payload => ({
            sheet_name: SHEET_NAME,
            section_id: payload.noteSectionId,
            sub_table_data: payload.subTableData,
            columns: pickColumnsForPayload(payload.subTableData, soeColumns),
          })),
        },
      )
      data = result?.data ?? result
    } catch (err: unknown) {
      // 请求被取消（防重复提交 / 组件卸载 / 竞争去重）→ 静默跳过，不误报「同步失败」
      const e = err as any
      if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError' || e?.__CANCEL__) return
      // 🔴 绝不吞异常：原始 err 进控制台，提示带真实原因（后端 detail / HTTP 状态）
      console.error('[G7 国企披露] 同步到附注失败（附注未落地）', err)
      ElMessage.error(`同步附注失败：${describeSyncError(err)}`)
      return
    }

    // ── ② 成功后的收尾：失败 ⇒ 附注**已落地**，绝不能报「同步失败」──────────
    const okText =
      `已同步 ${Number(data?.rows_synced ?? 0)} 行到 ` +
      `${Number(data?.sections_synced ?? payloads.length)} 个附注章节（含合并范围变化与八、18）`
    try {
      // 🔴 同步成功后必须回写「本次各章节实际推送的表名」基线并落库（Task 13）：
      // 少了这一步，`previouslySyncedTables` 永远停在 `{}`，`buildRemovedTableKeys`
      // 的被减数恒空 ⇒ `_removed_table_keys` 永不上报 ⇒ 删表后附注永久残留过时明细。
      // 顺序必须是「同步成功 → 更新基线 → persist」：先 persist 会把旧基线写回，
      // 而在 `api.post` 失败时不更新基线才是对的（那次推送没落地）。
      state.previouslySyncedTables = markG7SoeSynced(serialisableState(), payloads)
      await persist()
      dispatchNoteUpdated()
      ElMessage.success(okText)
    } catch (err: unknown) {
      console.error('[G7 国企披露] 同步已落地，但同步基线回写失败', err)
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
  autoSync.cancelPending()
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

.disclosure-table :deep(.row-group td) {
  background: var(--el-fill-color-lighter);
  font-weight: 600;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.disclosure-table :deep(.row-subtotal td) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.disclosure-table :deep(.row-total td) {
  background: var(--el-color-primary-light-9);
  font-weight: 700;
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
  .block-head,
  .chapter-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
