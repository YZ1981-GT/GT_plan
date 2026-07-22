<template>
  <div class="h2-disc-soe">
    <el-alert type="info" :closable="false" show-icon class="objective">
      审计目标：按国企附注格式编制在建工程披露——汇总（账面余额/减值/账面价值）、（1）情况、（2）重要项目本期变动宽表、（3）减值计提原因，与 H2-1/H2-2 勾稽，并同步至附注「{{ noteSectionId }}」。
    </el-alert>

    <div class="toolbar">
      <div class="toolbar-left">
        <strong>附注披露信息（国有企业）</strong>
        <el-tag size="small" type="success" effect="plain">23、在建工程</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="pullFromSources">从审定/明细取数</el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="h2-disclosure-soe-sync"
          @click="syncToNotes"
        >同步到附注</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:H2-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
        <GtReviewTrigger section-id="H2-disclosure-soe" />
      </div>
    </div>

    <!-- ══════ 23、汇总 ══════ -->
    <section class="block">
      <h3 class="block-title">23、在建工程</h3>
      <el-table :data="summaryDisplay" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="120" fixed>
          <template #default="{ row }">
            <span :class="{ 'is-total': row.key === '__total__' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.key !== '__total__' && !isReadonly" :model-value="row.endBook" :controls="false" size="small" style="width:100%" @update:model-value="(v: number) => updateSummary(row.key, 'endBook', v ?? 0)" />
              <span v-else class="formula-cell">{{ fmt(row.endBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.key !== '__total__' && !isReadonly" :model-value="row.endImpairment" :controls="false" size="small" style="width:100%" @update:model-value="(v: number) => updateSummary(row.key, 'endImpairment', v ?? 0)" />
              <span v-else class="formula-cell">{{ fmt(row.endImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.key === '__total__' ? row.endCarrying : soeCarrying(row.endBook, row.endImpairment)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.key !== '__total__' && !isReadonly" :model-value="row.beginBook" :controls="false" size="small" style="width:100%" @update:model-value="(v: number) => updateSummary(row.key, 'beginBook', v ?? 0)" />
              <span v-else class="formula-cell">{{ fmt(row.beginBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.key !== '__total__' && !isReadonly" :model-value="row.beginImpairment" :controls="false" size="small" style="width:100%" @update:model-value="(v: number) => updateSummary(row.key, 'beginImpairment', v ?? 0)" />
              <span v-else class="formula-cell">{{ fmt(row.beginImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.key === '__total__' ? row.beginCarrying : soeCarrying(row.beginBook, row.beginImpairment)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ （1）在建工程情况 ══════ -->
    <section class="block">
      <h4 class="sub-title">（1）在建工程情况</h4>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addDetailRow">+ 新增项目行</el-button>
      </div>
      <el-table :data="detailDisplay" border size="small" class="wp-table">
        <el-table-column label="项  目" min-width="140" fixed>
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.endBook" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.endBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.endImpairment" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.endImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.endCarrying : soeCarrying(row.endBook, row.endImpairment)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初余额" align="center">
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.beginBook" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.beginBook) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减值准备" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.beginImpairment" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.beginImpairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.beginCarrying : soeCarrying(row.beginBook, row.beginImpairment)) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeDetail(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ══════ （2）重要项目宽表 ══════ -->
    <section class="block">
      <h4 class="sub-title">（2）重要在建工程项目本期变动情况</h4>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addProjectRow">+ 新增工程行</el-button>
        <span class="hint inline">期末余额 = 期初 + 本期增加 − 转入固定资产 − 其他减少</span>
      </div>
      <div class="scroll-x">
        <el-table :data="projectDisplay" border size="small" class="wp-table">
          <el-table-column label="项目名称" min-width="130" fixed>
            <template #default="{ row }">
              <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
              <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预算数" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.budget" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.budget) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.beginBalance" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.beginBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.increase" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.increase) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期转入固定资产金额" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.transferToFA" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.transferToFA) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期其他减少金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.otherDecrease" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.otherDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.rowId === '__total__' ? row.endBalance : soeProjectEnd(row)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="工程累计投入占预算比例(%)" width="150" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.cumInputPct" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.cumInputPct) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="工程进度" min-width="100">
            <template #default="{ row }">
              <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.progress" size="small" @change="scheduleSave" />
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="利息资本化累计金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.interestCapAccum" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.interestCapAccum) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其中：本期利息资本化金额" width="140" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.interestCapCurrent" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else class="formula-cell">{{ fmt(row.interestCapCurrent) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期利息资本化率(%)" width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.interestCapRate" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
              <span v-else>{{ row.rowId === '__total__' ? '—' : fmt(row.interestCapRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="资金来源" min-width="120">
            <template #default="{ row }">
              <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.fundSource" size="small" @change="scheduleSave" />
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="48" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeProject(row.rowId)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- ══════ （3）减值 ══════ -->
    <section class="block">
      <h4 class="sub-title">（3）本期计提在建工程减值准备情况</h4>
      <div class="row-actions" v-if="!isReadonly">
        <el-button size="small" @click="addImpairmentRow">+ 新增行</el-button>
      </div>
      <el-table :data="impairmentDisplay" border size="small" class="wp-table" style="max-width: 640px">
        <el-table-column label="项  目" min-width="160">
          <template #default="{ row }">
            <span v-if="row.rowId === '__total__'" class="is-total">合  计</span>
            <el-input v-else-if="!isReadonly" v-model="row.name" size="small" @change="scheduleSave" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.provisionAmount" :controls="false" size="small" style="width:100%" @change="scheduleSave" />
            <span v-else class="formula-cell">{{ fmt(row.provisionAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提原因" min-width="200">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== '__total__' && !isReadonly" v-model="row.reason" size="small" @change="scheduleSave" />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48">
          <template #default="{ row }">
            <el-button v-if="row.rowId !== '__total__'" link type="danger" size="small" @click="removeImpairment(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-field">
        <label>减值补充说明</label>
        <el-input
          v-model="noteImpairment"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="可补充减值测试方法、关键参数等（按需）"
          @change="scheduleSave"
        />
      </div>
    </section>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>列结构严格对齐源 xlsx「附注披露信息（国有企业）」；重要项目为宽表一次披露（含资金来源）。</li>
        <li>（1）（2）（3）按实际工程动态插行；账面价值、期末余额为公式列。</li>
        <li>「同步到附注」推送至「{{ noteSectionId }}」；空名称行不推送。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabDisclosureSoe — 附注披露信息（国有企业）
 * 对齐源 xlsx 列结构；动态插行；同步附注八、23
 */
import { ref, reactive, computed, inject, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { H2_NOTE_SECTION } from '../../composables/h2NoteSectionMap'
import { buildH2SoeSyncPayloads, type H2SoeSyncSnapshot } from '../../composables/h2DisclosureSyncPayload'
import {
  H2_SOE_ITEM,
  createDefaultSoeSummary,
  createEmptySoeProject,
  mapDetailToSoeDetail,
  mapDetailToSoeProjects,
  newRowId,
  num,
  soeCarrying,
  soeDetailSubtotal,
  soeImpairmentSubtotal,
  soeProjectEnd,
  soeProjectSubtotal,
  soeSummaryTotal,
  type SoeDetailRow,
  type SoeImpairmentRow,
  type SoeProjectRow,
  type SoeSummaryRow,
} from '../../composables/h2SoeDisclosureModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const isReadonly = computed(() => props.isReadonly)
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const noteSectionId = H2_NOTE_SECTION.soe
const isSyncing = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

const summary = reactive<SoeSummaryRow[]>(createDefaultSoeSummary())
const detailRows = ref<SoeDetailRow[]>([])
const projectRows = ref<SoeProjectRow[]>([])
const impairmentRows = ref<SoeImpairmentRow[]>([])
const noteImpairment = ref('')

const summaryDisplay = computed(() => {
  const tot = soeSummaryTotal(summary)
  return [
    ...summary,
    {
      key: '__total__' as any,
      label: '合  计',
      endBook: tot.endBook,
      endImpairment: tot.endImpairment,
      endCarrying: tot.endCarrying,
      beginBook: tot.beginBook,
      beginImpairment: tot.beginImpairment,
      beginCarrying: tot.beginCarrying,
    },
  ]
})

const detailDisplay = computed(() => {
  const tot = soeDetailSubtotal(detailRows.value)
  return [
    ...detailRows.value,
    {
      rowId: '__total__',
      name: '合计',
      endBook: tot.endBook,
      endImpairment: tot.endImpairment,
      endCarrying: tot.endCarrying,
      beginBook: tot.beginBook,
      beginImpairment: tot.beginImpairment,
      beginCarrying: tot.beginCarrying,
    } as any,
  ]
})

const projectDisplay = computed(() => {
  const tot = soeProjectSubtotal(projectRows.value)
  return [
    ...projectRows.value,
    {
      rowId: '__total__',
      name: '合计',
      budget: tot.budget,
      beginBalance: tot.beginBalance,
      increase: tot.increase,
      transferToFA: tot.transferToFA,
      otherDecrease: tot.otherDecrease,
      endBalance: tot.endBalance,
      cumInputPct: tot.cumInputPct,
      interestCapAccum: tot.interestCapAccum,
      interestCapCurrent: tot.interestCapCurrent,
      interestCapRate: 0,
      progress: '',
      fundSource: '',
    } as any,
  ]
})

const impairmentDisplay = computed(() => [
  ...impairmentRows.value,
  {
    rowId: '__total__',
    name: '合计',
    provisionAmount: soeImpairmentSubtotal(impairmentRows.value),
    reason: '',
  } as any,
])

function fmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function parseJson(itemId: string): any {
  const raw = props.allResponses.get(itemId)?.remark
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function load() {
  const s = parseJson(H2_SOE_ITEM.summary)
  if (Array.isArray(s) && s.length) {
    for (const row of s) {
      const t = summary.find((x) => x.key === row.key)
      if (t) {
        t.endBook = num(row.endBook)
        t.endImpairment = num(row.endImpairment)
        t.beginBook = num(row.beginBook)
        t.beginImpairment = num(row.beginImpairment)
      }
    }
  }
  const d = parseJson(H2_SOE_ITEM.detail)
  detailRows.value = Array.isArray(d) ? d.map((r: any) => ({
    rowId: r.rowId || newRowId('soe-det'),
    name: r.name || '',
    endBook: num(r.endBook),
    endImpairment: num(r.endImpairment),
    beginBook: num(r.beginBook),
    beginImpairment: num(r.beginImpairment),
  })) : []
  const p = parseJson(H2_SOE_ITEM.projects)
  projectRows.value = Array.isArray(p) ? p.map((r: any) => ({
    ...createEmptySoeProject(),
    ...r,
    rowId: r.rowId || newRowId('soe-proj'),
    beginBalance: num(r.beginBalance),
    increase: num(r.increase),
    transferToFA: num(r.transferToFA),
    otherDecrease: num(r.otherDecrease),
    interestCapAccum: num(r.interestCapAccum),
    interestCapCurrent: num(r.interestCapCurrent),
    interestCapRate: num(r.interestCapRate),
    budget: num(r.budget),
    cumInputPct: num(r.cumInputPct),
    accumulatedInput: num(r.accumulatedInput),
  })) : []
  const i = parseJson(H2_SOE_ITEM.impairment)
  impairmentRows.value = Array.isArray(i) ? i.map((r: any) => ({
    rowId: r.rowId || newRowId('soe-imp'),
    name: r.name || '',
    provisionAmount: num(r.provisionAmount),
    reason: r.reason || '',
  })) : []
  noteImpairment.value = String(props.allResponses.get(H2_SOE_ITEM.noteImpairment)?.remark ?? '')

  const hasData = detailRows.value.length || projectRows.value.length
    || summary.some((r) => r.endBook || r.beginBook)
  if (!hasData) pullFromSources(false)
}

function scheduleSave() {
  if (isReadonly.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => persistAll(), 300)
}

function persistAll() {
  saveResponse(H2_SOE_ITEM.summary, summary.map((r) => ({ ...r })))
  saveResponse(H2_SOE_ITEM.detail, detailRows.value)
  saveResponse(H2_SOE_ITEM.projects, projectRows.value)
  saveResponse(H2_SOE_ITEM.impairment, impairmentRows.value)
  saveResponse(H2_SOE_ITEM.noteImpairment, noteImpairment.value)
  eventBus.emit('disclosure:note-text-updated' as any, {
    wp_code: 'H2',
    variant: 'soe',
    section: noteSectionId,
    text: noteImpairment.value || '',
  })
}

function updateSummary(
  key: string,
  field: 'endBook' | 'endImpairment' | 'beginBook' | 'beginImpairment',
  v: number,
) {
  const row = summary.find((r) => r.key === key)
  if (!row) return
  row[field] = num(v)
  scheduleSave()
}

function addDetailRow() {
  detailRows.value.push({
    rowId: newRowId('soe-det'),
    name: '',
    endBook: 0,
    endImpairment: 0,
    beginBook: 0,
    beginImpairment: 0,
  })
  scheduleSave()
}
function removeDetail(rowId: string) {
  detailRows.value = detailRows.value.filter((r) => r.rowId !== rowId)
  scheduleSave()
}
function addProjectRow() {
  projectRows.value.push(createEmptySoeProject())
  scheduleSave()
}
function removeProject(rowId: string) {
  projectRows.value = projectRows.value.filter((r) => r.rowId !== rowId)
  scheduleSave()
}
function addImpairmentRow() {
  impairmentRows.value.push({
    rowId: newRowId('soe-imp'),
    name: '',
    provisionAmount: 0,
    reason: '',
  })
  scheduleSave()
}
function removeImpairment(rowId: string) {
  impairmentRows.value = impairmentRows.value.filter((r) => r.rowId !== rowId)
  scheduleSave()
}

function pullFromSources(showMsg = true) {
  const adjRaw = props.allResponses.get('H2-1-rows')?.remark
  const detRaw = props.allResponses.get('H2-2-rows')?.remark
  let adj: any[] = []
  let det: any[] = []
  try { if (adjRaw) adj = JSON.parse(adjRaw) } catch { /* ignore */ }
  try { if (detRaw) det = JSON.parse(detRaw) } catch { /* ignore */ }

  if (Array.isArray(det) && det.length) {
    detailRows.value = mapDetailToSoeDetail(det)
    projectRows.value = mapDetailToSoeProjects(det)
  }

  if (Array.isArray(adj) && adj.length) {
    const cipBegin = adj.reduce((s, r) => s + num(r.cipBegin), 0)
    const cipEnd = adj.reduce((s, r) => s + num(r.cipEnd ?? r.audited), 0)
    const impair = adj.reduce((s, r) => s + num(r.impairment), 0)
    const cip = summary.find((r) => r.key === 'cip')
    if (cip) {
      cip.endBook = cipEnd
      cip.endImpairment = impair
      cip.beginBook = cipBegin
      cip.beginImpairment = 0
    }
  } else if (detailRows.value.length) {
    const tot = soeDetailSubtotal(detailRows.value)
    const cip = summary.find((r) => r.key === 'cip')
    if (cip) {
      cip.endBook = tot.endBook
      cip.endImpairment = tot.endImpairment
      cip.beginBook = tot.beginBook
      cip.beginImpairment = tot.beginImpairment
    }
  }

  scheduleSave()
  if (showMsg) ElMessage.success('已从 H2-1/H2-2 取数填充披露表')
}

function getSnapshot(): H2SoeSyncSnapshot {
  return {
    summary: summary.map((r) => ({ ...r })),
    detail: detailRows.value,
    projects: projectRows.value,
    impairment: impairmentRows.value,
    noteImpairment: noteImpairment.value,
  }
}

async function syncToNotes() {
  if (isSyncing.value || isReadonly.value || !props.projectId || !props.wpId) return
  persistAll()
  const payloads = buildH2SoeSyncPayloads(props.wpId, [], getSnapshot())
  if (!payloads.length) {
    ElMessage.warning('当前不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionId}」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<style scoped>
.h2-disc-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective { margin-bottom: 12px; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
  margin-bottom: 14px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.block { margin-bottom: 20px; }
.block-title { margin: 0 0 8px; font-size: 15px; }
.sub-title { margin: 0 0 8px; font-size: 14px; color: #303133; }
.hint { font-size: 12px; color: #909399; margin: 6px 0 0; }
.hint.inline { margin: 0; }
.row-actions { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.scroll-x { overflow-x: auto; }
.formula-cell {
  border-bottom: 1px dashed #909399; font-variant-numeric: tabular-nums;
}
.is-total { font-weight: 600; }
.note-field { margin-top: 10px; }
.note-field label {
  display: block; font-size: 12px; color: #606266; margin-bottom: 4px;
}
.compile-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
