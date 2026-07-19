<template>

  <div class="g4-disclosure-soe">

    <el-alert

      type="info"

      :closable="false"

      show-icon

      title="审计目标：确认债权投资在国有企业财务报表附注中完整、准确披露期初/期末账面余额、减值准备与账面价值，以及期末三阶段计提与减值准备变动情况。"

      class="objective-alert"

      style="margin-bottom: 12px"

    />



    <!-- 非三阶段 section -->

    <template v-for="(section, sIdx) in sections" :key="section.id">

      <template v-if="section.id !== 'stage-impairment'">

        <div class="section-head">

          <h4 class="section-title">{{ section.title }}</h4>

          <div class="head-actions">

            <el-button

              v-if="section.hasTextArea"

              size="small"

              type="primary"

              text

              :disabled="isReadonly || !aiAvailable"

              :loading="aiLoading"

              @click="fillAiDraft(sIdx)"

            >

              🤖AI辅助

            </el-button>

            <GtReviewTrigger :section-id="`G4-disclosure-soe-${section.id}`" />

          </div>

        </div>



        <el-table

          v-if="section.rows.length > 0"

          :data="section.rows"

          border

          stripe

          style="width: 100%; font-size: 13px; margin-bottom: 8px"

        >

          <el-table-column prop="item" label="项目" min-width="160" fixed />

          <el-table-column label="期末数" align="center">

            <el-table-column label="账面余额" width="120" align="right">

              <template #default="{ row }">

                <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.endingBalance) }}</span>

              </template>

            </el-table-column>

            <el-table-column label="减值准备" width="120" align="right">

              <template #default="{ row }">{{ fmtAmount(row.endingImpairment) }}</template>

            </el-table-column>

            <el-table-column label="账面价值" width="120" align="right">

              <template #default="{ row }">

                <span class="formula-cell">{{ fmtAmount(row.endingBookValue) }}</span>

              </template>

            </el-table-column>

          </el-table-column>

          <el-table-column label="期初数" align="center">

            <el-table-column label="账面余额" width="120" align="right">

              <template #default="{ row }">{{ fmtAmount(row.priorBalance) }}</template>

            </el-table-column>

            <el-table-column label="减值准备" width="120" align="right">

              <template #default="{ row }">{{ fmtAmount(row.priorImpairment) }}</template>

            </el-table-column>

            <el-table-column label="账面价值" width="120" align="right">

              <template #default="{ row }">

                <span class="formula-cell">{{ fmtAmount(row.priorBookValue) }}</span>

              </template>

            </el-table-column>

          </el-table-column>

        </el-table>



        <el-card v-if="section.hasTextArea" shadow="never" class="text-card">

          <el-input

            v-model="section.textContent"

            type="textarea"

            :autosize="{ minRows: 3, maxRows: 12 }"

            :disabled="isReadonly"

            :placeholder="`${section.title} 附注文本...`"

            @change="onNoteTextChange(sIdx)"

          />

        </el-card>

      </template>

    </template>



    <!-- （3）期末三阶段：动态其中行（对齐上市披露逻辑，无上年对照） -->

    <div class="section-head">

      <h4 class="section-title">（3）减值准备计提情况（期末三阶段）</h4>

      <div class="head-actions">

        <GtReviewTrigger section-id="G4-disclosure-soe-stage-impairment" />

      </div>

    </div>

    <el-alert

      type="warning"

      :closable="false"

      show-icon

      class="stage-tip"

      title="国企附注仅披露期末三阶段。「其中」可动态增删（对应 Excel 预留插行区）；父级「按单项/按组合」自动汇总。"

    />



    <el-card

      v-for="block in stageBlocks"

      :key="block.id"

      shadow="never"

      class="stage-card"

    >

      <template #header>

        <span class="stage-card-title">{{ block.title }}</span>

      </template>



      <div

        v-for="method in (['individual', 'portfolio'] as const)"

        :key="method"

        class="method-block"

      >

        <div class="method-head">

          <span class="method-label">

            {{ method === 'individual' ? '按单项计提减值准备' : '按组合计提减值准备' }}

          </span>

          <el-button

            size="small"

            type="primary"

            link

            :disabled="isReadonly"

            @click="onAddDetail(block.id, method)"

          >

            + 添加其中行

          </el-button>

        </div>

        <el-table :data="methodTableRows(block, method)" border size="small" class="stage-table">

          <el-table-column label="类别" min-width="140">

            <template #default="{ row }">

              <el-input

                v-if="row.kind === 'detail' && !isReadonly"

                :model-value="row.name"

                size="small"

                @change="(v: string) => onPatchDetail(block.id, method, row.id, { name: v })"

              />

              <span v-else :class="{ 'is-parent': row.kind === 'parent' }">{{ row.name }}</span>

            </template>

          </el-table-column>

          <el-table-column label="账面余额" width="120" align="right">

            <template #default="{ row }">

              <el-input-number

                v-if="row.kind === 'detail' && !isReadonly"

                :model-value="row.bookBalance"

                size="small"

                :controls="false"

                class="amt-input"

                @change="(v: number) => onPatchDetail(block.id, method, row.id, { bookBalance: v ?? 0 })"

              />

              <span v-else class="amount-cell">{{ fmtAmount(row.bookBalance) }}</span>

            </template>

          </el-table-column>

          <el-table-column :label="block.rateLabel" width="160" align="right">

            <template #default="{ row }">

              <span class="formula-cell">{{ fmtRate(row.ratePct) }}</span>

            </template>

          </el-table-column>

          <el-table-column label="减值准备" width="120" align="right">

            <template #default="{ row }">

              <el-input-number

                v-if="row.kind === 'detail' && !isReadonly"

                :model-value="row.impairment"

                size="small"

                :controls="false"

                class="amt-input"

                @change="(v: number) => onPatchDetail(block.id, method, row.id, { impairment: v ?? 0 })"

              />

              <span v-else class="amount-cell">{{ fmtAmount(row.impairment) }}</span>

            </template>

          </el-table-column>

          <el-table-column label="账面价值" width="120" align="right">

            <template #default="{ row }">

              <span class="formula-cell">{{ fmtAmount(row.bookValue) }}</span>

            </template>

          </el-table-column>

          <el-table-column :label="block.reasonHeader" min-width="140">

            <template #default="{ row }">

              <el-input

                v-if="row.kind === 'detail' && !isReadonly"

                :model-value="row.reason"

                size="small"

                @change="(v: string) => onPatchDetail(block.id, method, row.id, { reason: v })"

              />

              <span v-else>{{ row.reason }}</span>

            </template>

          </el-table-column>

          <el-table-column v-if="!isReadonly" label="" width="52" align="center">

            <template #default="{ row }">

              <el-button

                v-if="row.kind === 'detail'"

                size="small"

                type="danger"

                link

                @click="onRemoveDetail(block.id, method, row.id)"

              >

                删

              </el-button>

            </template>

          </el-table-column>

        </el-table>

      </div>



      <div class="stage-total">

        合计：账面余额 {{ fmtAmount(stageTotals(block).bookBalance) }}

        ／ 减值准备 {{ fmtAmount(stageTotals(block).impairment) }}

        ／ 账面价值 {{ fmtAmount(stageTotals(block).bookValue) }}

        ／ ECL率 {{ fmtRate(stageTotals(block).ratePct) }}

      </div>

    </el-card>



    <el-card shadow="never" class="text-card">

      <el-input

        v-model="stageNoteText"

        type="textarea"

        :autosize="{ minRows: 3, maxRows: 10 }"

        :disabled="isReadonly"

        placeholder="三阶段减值附注说明..."

        @change="onStageNoteChange"

      />

    </el-card>



    <details class="prep-hint">

      <summary>编制提示</summary>

      <ul>

        <li>对齐 Excel 国企附注：（1）余额表 →（2）重要债权投资 →（3）期末三阶段 → 减值准备变动</li>

        <li>相对上市表：无上年三阶段对照、无重要核销明细；「其中」同样支持动态插行</li>

        <li>账面价值 = 账面余额 − 减值准备；编辑后发布 disclosure:note-text-updated</li>

      </ul>

    </details>

  </div>

</template>



<script setup lang="ts">

/**

 * G4TabDisclosureSOE.vue — 附注披露信息（国企）

 * 对齐 Excel 结构；三阶段「其中」动态增删（与上市披露同源逻辑）。

 */

import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'

import GtReviewTrigger from '../../GtReviewTrigger.vue'

import http from '@/utils/http'

import { useG4MainAiGenerate } from '../../composables/useG4MainAiGenerate'

import {

  addStageDetail,

  bookValue,

  buildDefaultSoeStageBlocks,

  eclRatePct,

  methodTotals,

  parseStageBlocks,

  patchStageDetail,

  removeStageDetail,

  serializeStageBlocks,

  stageTotals,

  type G4StageBlock,

  type G4StageDetailRow,

  type G4StageMethod,

} from '../../composables/g4ListedStageDisclosure'



const G4_ACCOUNT_CODE = '1501'

const STAGE_ROWS_KEY = 'G4-disclosure-soe-stages'

const STAGE_NOTE_KEY = 'G4-disclosure-soe-stage-note'



const props = defineProps<{

  htmlData: Record<string, any> | null

  wpId: string

  projectId: string

  isReadonly: boolean

}>()



function fmtAmount(v: number | null | undefined): string {

  if (v == null || v === 0) return '-'

  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

}



function fmtRate(v: number | null | undefined): string {

  if (v == null || Number.isNaN(v)) return '—'

  return `${v.toFixed(2)}%`

}



const isReadonly = computed(() => props.isReadonly)

const wpIdRef = computed(() => props.wpId)

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4MainAiGenerate(wpIdRef)



function readSaved(key: string): string {

  const cr = props.htmlData?.checklist_responses

  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {

    const v = (cr as Record<string, any>)[key]

    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')

  }

  const resp = props.htmlData?.responses

  if (Array.isArray(resp)) {

    const found = resp.find((r: any) => r?.item_id === key)

    if (found?.remark) return found.remark

  }

  return ''

}



async function saveAudit(key: string, val: string): Promise<void> {

  if (props.isReadonly) return

  try {

    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {

      project_id: props.projectId || undefined,

      items: [{ item_id: key, conclusion: null, remark: val }],

    })

  } catch { /* silent */ }

}



interface DisclosureRow {

  item: string

  endingBalance: number

  endingImpairment: number

  endingBookValue: number

  priorBalance: number

  priorImpairment: number

  priorBookValue: number

  isFormula?: boolean

}



interface DisclosureSection {

  id: string

  title: string

  rows: DisclosureRow[]

  hasTextArea: boolean

  textContent: string

}



function buildSections(): DisclosureSection[] {

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



const sections = reactive<DisclosureSection[]>(buildSections())

const stageBlocks = ref<G4StageBlock[]>(buildDefaultSoeStageBlocks())

const stageNoteText = ref('')



type DisplayKind = 'parent' | 'detail'

interface MethodDisplayRow {

  id: string

  kind: DisplayKind

  name: string

  bookBalance: number

  impairment: number

  bookValue: number

  ratePct: number | null

  reason: string

}



function methodTableRows(block: G4StageBlock, method: G4StageMethod): MethodDisplayRow[] {

  const mb = method === 'individual' ? block.individual : block.portfolio

  const tot = methodTotals(mb)

  const parentName = method === 'individual' ? '按单项计提减值准备' : '按组合计提减值准备'

  const rows: MethodDisplayRow[] = [

    {

      id: `${block.id}-${method}-parent`,

      kind: 'parent',

      name: parentName,

      bookBalance: tot.bookBalance,

      impairment: tot.impairment,

      bookValue: tot.bookValue,

      ratePct: tot.ratePct,

      reason: '',

    },

  ]

  for (const d of mb.details) {

    rows.push({

      id: d.id,

      kind: 'detail',

      name: d.name,

      bookBalance: d.bookBalance,

      impairment: d.impairment,

      bookValue: bookValue(d.bookBalance, d.impairment),

      ratePct: eclRatePct(d.impairment, d.bookBalance),

      reason: d.reason,

    })

  }

  return rows

}



function persistStages(): void {

  void saveAudit(STAGE_ROWS_KEY, serializeStageBlocks(stageBlocks.value))

}



function onAddDetail(blockId: string, method: G4StageMethod): void {

  if (props.isReadonly) return

  stageBlocks.value = addStageDetail(stageBlocks.value, blockId, method)

  persistStages()

}



function onRemoveDetail(blockId: string, method: G4StageMethod, detailId: string): void {

  if (props.isReadonly) return

  stageBlocks.value = removeStageDetail(stageBlocks.value, blockId, method, detailId)

  persistStages()

}



function onPatchDetail(

  blockId: string,

  method: G4StageMethod,

  detailId: string,

  patch: Partial<Pick<G4StageDetailRow, 'name' | 'bookBalance' | 'impairment' | 'reason'>>,

): void {

  if (props.isReadonly) return

  stageBlocks.value = patchStageDetail(stageBlocks.value, blockId, method, detailId, patch)

  persistStages()

}



function onStageNoteChange(): void {

  void saveAudit(STAGE_NOTE_KEY, stageNoteText.value)

  onNoteTextChange(-1)

}



function handleAdjudicated(e: Event): void {

  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail

  if (d?.accountCode === G4_ACCOUNT_CODE && d.adjudicatedAmount != null) {

    const overview = sections.find(s => s.id === 'bond-overview')

    if (overview?.rows.length) {

      const total = overview.rows.find(r => r.item === '合计') || overview.rows[overview.rows.length - 1]

      total.endingBookValue = d.adjudicatedAmount

      total.endingBalance = d.adjudicatedAmount

      total.endingImpairment = 0

    }

  }

}



onMounted(() => {

  window.addEventListener('substantive:adjudicated', handleAdjudicated)

  loadFromHtmlData()

})

onBeforeUnmount(() => {

  window.removeEventListener('substantive:adjudicated', handleAdjudicated)

})



function onNoteTextChange(_sectionIdx: number): void {

  const parts = sections

    .filter(s => s.hasTextArea && s.textContent)

    .map(s => `【${s.title}】\n${s.textContent}`)

  if (stageNoteText.value) {

    parts.push(`【（3）减值准备计提情况】\n${stageNoteText.value}`)

  }

  const allText = parts.join('\n\n')

  void saveAudit('G4-disclosure-soe-text', allText)

  try {

    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {

      detail: { accountCode: G4_ACCOUNT_CODE, section: 'soe', text: allText },

    }))

  } catch { /* silent */ }

}



async function fillAiDraft(sectionIdx: number): Promise<void> {

  if (props.isReadonly) return

  const section = sections[sectionIdx]

  if (!section) return

  const text = await generateAndConfirm(

    'disclosure-soe-note',

    section.textContent || '',

    { sectionTitle: section.title },

    'AI 附注披露',

  )

  if (text) {

    section.textContent = text

    onNoteTextChange(sectionIdx)

  }

}



function loadFromHtmlData(): void {

  if (props.htmlData?.disclosureSOE?.sections) {

    const saved = props.htmlData.disclosureSOE.sections as DisclosureSection[]

    saved.forEach((s, i) => {

      if (sections[i] && sections[i].id !== 'stage-impairment') {

        if (s.textContent) sections[i].textContent = s.textContent

        if (s.rows?.length && 'endingBalance' in (s.rows[0] || {})) {

          sections[i].rows = s.rows as DisclosureRow[]

        }

      }

    })

  }

  const parsed = parseStageBlocks(readSaved(STAGE_ROWS_KEY))

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

  const note = readSaved(STAGE_NOTE_KEY)

  if (note) stageNoteText.value = note

}

</script>



<style scoped>

.g4-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-head { display: flex; justify-content: space-between; align-items: center; margin: 16px 0 8px; }

.section-head:first-child { margin-top: 0; }

.section-title { margin: 0; font-size: 14px; font-weight: 600; }

.head-actions { display: flex; gap: 8px; align-items: center; }

.text-card { margin: 12px 0; }

.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }

.objective-alert { margin-bottom: 12px; }

.stage-tip { margin-bottom: 10px; }

.stage-card { margin-bottom: 12px; }

.stage-card-title { font-weight: 600; font-size: 13px; }

.method-block { margin-bottom: 8px; }

.method-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }

.method-label { color: #c00; font-weight: 600; font-size: 13px; }

.stage-table { width: 100%; }

.amt-input { width: 110px; }

.amount-cell { font-variant-numeric: tabular-nums; }

.is-parent { color: #c00; font-weight: 600; }

.stage-total {

  margin-top: 8px;

  padding: 6px 8px;

  background: #f5f7fa;

  font-size: 12px;

  color: #606266;

}

.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }

.prep-hint summary { cursor: pointer; }

.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }

</style>


