<template>

  <div class="g4-disclosure-listed">

    <el-alert

      type="info"

      :closable="false"

      show-icon

      title="审计目标：确认债权投资在上市公司财务报表附注中按模板完整披露期末/上年年末账面余额、减值准备与账面价值，以及减值变动、重要债权投资、三阶段计提等情况。"

      class="objective-alert"

      style="margin-bottom: 12px"

    />



    <!-- 非三阶段 section：沿用原表格 -->

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

            <GtReviewTrigger :section-id="`G4-disclosure-listed-${section.id}`" />

          </div>

        </div>



        <el-table

          v-if="section.rows.length > 0"

          :data="section.rows"

          border

          stripe

          :max-height="section.rows.length > 50 ? 520 : undefined"

          style="width: 100%; font-size: 13px; margin-bottom: 8px"

        >

          <el-table-column prop="item" label="项目" min-width="160" fixed />

          <el-table-column label="期末余额" align="center">

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

                <span class="formula-cell" title="账面价值 = 账面余额 − 减值准备">{{ fmtAmount(row.endingBookValue) }}</span>

              </template>

            </el-table-column>

          </el-table-column>

          <el-table-column label="上年年末余额" align="center">

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

            :autosize="{ minRows: 4, maxRows: 20 }"

            :disabled="isReadonly"

            :placeholder="`${section.title} 附注文本...`"

            @change="onNoteTextChange(sIdx)"

          />

        </el-card>

      </template>

    </template>



    <!-- （3）三阶段减值：动态「其中」行 -->

    <div class="section-head">

      <h4 class="section-title">（3）减值准备计提情况（三阶段）</h4>

      <div class="head-actions">

        <GtReviewTrigger section-id="G4-disclosure-listed-stage-impairment" />

      </div>

    </div>

    <el-alert

      type="warning"

      :closable="false"

      show-icon

      class="stage-tip"

      title="「其中」明细可动态增删（对应 Excel 预留插行区），勿写死固定行数。父级「按单项/按组合」自动汇总，ECL率与账面价值为公式列。"

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



      <!-- 按单项 -->

      <div class="method-head">

        <span class="method-label">按单项计提减值准备</span>

        <el-button

          size="small"

          type="primary"

          link

          :disabled="isReadonly"

          @click="onAddDetail(block.id, 'individual')"

        >

          + 添加其中行

        </el-button>

      </div>

      <el-table :data="methodTableRows(block, 'individual')" border size="small" class="stage-table">

        <el-table-column label="类别" min-width="140">

          <template #default="{ row }">

            <el-input

              v-if="row.kind === 'detail' && !isReadonly"

              :model-value="row.name"

              size="small"

              @change="(v: string) => onPatchDetail(block.id, 'individual', row.id, { name: v })"

            />

            <span v-else :class="{ 'is-total': row.kind !== 'detail', 'is-parent': row.kind === 'parent' }">

              {{ row.name }}

            </span>

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

              @change="(v: number) => onPatchDetail(block.id, 'individual', row.id, { bookBalance: v ?? 0 })"

            />

            <span v-else class="amount-cell">{{ fmtAmount(row.bookBalance) }}</span>

          </template>

        </el-table-column>

        <el-table-column :label="block.rateLabel" width="150" align="right">

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

              @change="(v: number) => onPatchDetail(block.id, 'individual', row.id, { impairment: v ?? 0 })"

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

              @change="(v: string) => onPatchDetail(block.id, 'individual', row.id, { reason: v })"

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

              @click="onRemoveDetail(block.id, 'individual', row.id)"

            >

              删

            </el-button>

          </template>

        </el-table-column>

      </el-table>



      <!-- 按组合 -->

      <div class="method-head" style="margin-top: 10px">

        <span class="method-label">按组合计提减值准备</span>

        <el-button

          size="small"

          type="primary"

          link

          :disabled="isReadonly"

          @click="onAddDetail(block.id, 'portfolio')"

        >

          + 添加其中行

        </el-button>

      </div>

      <el-table :data="methodTableRows(block, 'portfolio')" border size="small" class="stage-table">

        <el-table-column label="类别" min-width="140">

          <template #default="{ row }">

            <el-input

              v-if="row.kind === 'detail' && !isReadonly"

              :model-value="row.name"

              size="small"

              @change="(v: string) => onPatchDetail(block.id, 'portfolio', row.id, { name: v })"

            />

            <span v-else :class="{ 'is-total': row.kind !== 'detail', 'is-parent': row.kind === 'parent' }">

              {{ row.name }}

            </span>

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

              @change="(v: number) => onPatchDetail(block.id, 'portfolio', row.id, { bookBalance: v ?? 0 })"

            />

            <span v-else class="amount-cell">{{ fmtAmount(row.bookBalance) }}</span>

          </template>

        </el-table-column>

        <el-table-column :label="block.rateLabel" width="150" align="right">

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

              @change="(v: number) => onPatchDetail(block.id, 'portfolio', row.id, { impairment: v ?? 0 })"

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

              @change="(v: string) => onPatchDetail(block.id, 'portfolio', row.id, { reason: v })"

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

              @click="onRemoveDetail(block.id, 'portfolio', row.id)"

            >

              删

            </el-button>

          </template>

        </el-table-column>

      </el-table>



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

        :autosize="{ minRows: 3, maxRows: 12 }"

        :disabled="isReadonly"

        placeholder="三阶段减值附注文本（显著变动说明、划分依据汇总等）..."

        @change="onStageNoteChange"

      />

    </el-card>



    <details class="prep-hint">

      <summary>编制提示</summary>

      <ul>

        <li>对齐 Excel：主表 7 列；三阶段「其中」对应预留插行区，平台用「+ 添加其中行」动态扩展</li>

        <li>账面价值 = 账面余额 − 减值准备；ECL率 = 减值准备 / 账面余额</li>

        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>

      </ul>

    </details>

  </div>

</template>



<script setup lang="ts">

/**

 * G4TabDisclosureListed.vue — 附注披露信息（上市公司）

 * 三阶段「其中」支持动态增删，对齐 Excel 预留插行区。

 */

import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'

import GtReviewTrigger from '../../GtReviewTrigger.vue'

import http from '@/utils/http'

import { useG4MainAiGenerate } from '../../composables/useG4MainAiGenerate'

import {

  addStageDetail,

  buildDefaultStageBlocks,

  bookValue,

  eclRatePct,

  endingImpairmentTotal,

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

const STAGE_ROWS_KEY = 'G4-disclosure-listed-stages'

const STAGE_NOTE_KEY = 'G4-disclosure-listed-stage-note'



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

  openingBalance?: number

  closingBalance?: number

  impairment?: number

  amortizedCost?: number

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



const sections = reactive<DisclosureSection[]>(buildSections())

const stageBlocks = ref<G4StageBlock[]>(buildDefaultStageBlocks())

const stageNoteText = ref('')



type DisplayKind = 'parent' | 'detail' | 'total'

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



let adjudicatedAmount = 0



function handleAdjudicated(e: Event): void {

  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail

  if (d?.accountCode === G4_ACCOUNT_CODE && d.adjudicatedAmount != null) {

    adjudicatedAmount = d.adjudicatedAmount

    const overview = sections.find(s => s.id === 'bond-overview')

    if (overview && overview.rows.length > 0) {

      const total = overview.rows.find(r => r.item === '合计') || overview.rows[overview.rows.length - 1]

      total.endingBookValue = adjudicatedAmount

      total.endingBalance = adjudicatedAmount

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

    parts.push(`【（3）减值准备计提情况（三阶段）】\n${stageNoteText.value}`)

  }

  const allText = parts.join('\n\n')

  void saveAudit('G4-disclosure-listed-text', allText)

  try {

    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {

      detail: { accountCode: G4_ACCOUNT_CODE, section: 'listed', text: allText },

    }))

  } catch { /* silent */ }

}



async function fillAiDraft(sectionIdx: number): Promise<void> {

  if (props.isReadonly) return

  const section = sections[sectionIdx]

  if (!section) return

  const text = await generateAndConfirm(

    'disclosure-listed-note',

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

  if (props.htmlData?.disclosureListed?.sections) {

    const saved = props.htmlData.disclosureListed.sections as DisclosureSection[]

    saved.forEach((s, i) => {

      if (sections[i] && sections[i].id !== 'stage-impairment') {

        if (s.textContent) sections[i].textContent = s.textContent

        if (s.rows?.length) sections[i].rows = s.rows

      }

    })

  }

  const parsed = parseStageBlocks(readSaved(STAGE_ROWS_KEY))

  if (parsed) stageBlocks.value = parsed

  const note = readSaved(STAGE_NOTE_KEY)

  if (note) stageNoteText.value = note

  // 暴露勾稽值供调试/扩展

  void endingImpairmentTotal(stageBlocks.value)

}

</script>



<style scoped>

.g4-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }

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

.method-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }

.method-label { color: #c00; font-weight: 600; font-size: 13px; }

.stage-table { width: 100%; margin-bottom: 4px; }

.amt-input { width: 110px; }

.amount-cell { font-variant-numeric: tabular-nums; }

.is-parent { color: #c00; font-weight: 600; }

.is-total { font-weight: 600; }

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


