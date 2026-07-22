<template>
  <div class="h5-tab-stocktake-check">
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：执行油气资产双向抽盘（账面→实物测存在、实物→账面测完整），比对账面/企业盘点/审计抽盘三数量，核对账实差异并分析异常，为监盘小结提供依据。" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('navigate-sheet', 'H5-9')">← H5-9</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H5-11')">H5-11 →</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-10" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.checkRows.value.length }} 行</el-tag>
        <el-button v-if="!isReadonly" size="small" @click="onDraftConclusion">起草结论</el-button>
        <el-button size="small" type="default" link @click="handleReview('H5-10')">💬 复核</el-button>
      </div>
    </div>

    <ItemAttachment
      v-if="projectId && wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-key="H5-10"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.mp4,.mov"
    />

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <div>
            <span>（一）账面→实物（存在性）</span>
            <el-tag v-if="b2fVariance > 0" size="small" type="danger" class="ml-tag">{{ b2fVariance }} 行差异</el-tag>
            <el-tag v-else-if="b2fH1Rows.length" size="small" type="success" class="ml-tag">无差异</el-tag>
          </div>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow('bookToFloor')">+ 明细行</el-button>
          </div>
        </div>
      </template>
      <H1CheckDirectionTable
        :rows="b2fH1Rows"
        :is-readonly="isReadonly"
        empty-text="暂无「账面→实物」明细；可新增或从旧数据自动归入本方向"
        @update="onRowUpdate"
        @remove="(id) => state.removeCheckRow(id)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <div>
            <span>（二）实物→账面（完整性）</span>
            <el-tag v-if="f2bVariance > 0" size="small" type="danger" class="ml-tag">{{ f2bVariance }} 行差异</el-tag>
            <el-tag v-else-if="f2bH1Rows.length" size="small" type="success" class="ml-tag">无差异</el-tag>
          </div>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow('floorToBook')">+ 明细行</el-button>
          </div>
        </div>
      </template>
      <H1CheckDirectionTable
        :rows="f2bH1Rows"
        :is-readonly="isReadonly"
        empty-text="暂无「实物→账面」明细；完整性测试不可省略"
        @update="onRowUpdate"
        @remove="(id) => state.removeCheckRow(id)"
      />
    </el-card>

    <div class="summary-bar">
      <span>异常 {{ state.abnormalCheckItems.value.length }} 项</span>
      <span>差异合计 {{ fmtAmt(state.totalDifference.value) }}</span>
      <span>账面→实物 {{ b2fH1Rows.length }}</span>
      <span>实物→账面 {{ f2bH1Rows.length }}</span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5 }"
        placeholder="填写盘点检查审计说明..." :disabled="isReadonly" @change="savePolishNote" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3 }"
        placeholder="填写盘点检查审计结论..." :disabled="isReadonly" @change="savePolishConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>双向抽盘：账面→实物测存在性，实物→账面测完整性。</li>
        <li>三数量：账面数量、企业盘点数量、审计抽盘数量；差异自动计算。</li>
        <li>旧数据中的「账面数/实盘数」已分别映射为账面金额/抽盘数量，可继续编辑。</li>
        <li>异常项需说明差异原因；完成后汇入 H5-11 监盘小结。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import H1CheckDirectionTable from '../../h1/stocktake/H1CheckDirectionTable.vue'
import {
  useH5Stocktake,
  toH1CheckRow,
  draftH5CheckConclusion,
  type StocktakeDirection,
} from '../../composables/useH5Stocktake'
import { useH5FormData } from '../../composables/useH5FormData'
import { calcRowDiffs, type StocktakeCheckRow as H1Row } from '../../composables/h1StocktakeCheckModel'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const state = useH5Stocktake({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
})

const NOTE_KEY = 'H5-10-audit-note'
const CONCLUSION_KEY = 'H5-10-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')

function savePolishNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void formData.saveResponse(NOTE_KEY, val)
}
function savePolishConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusionText.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void formData.saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

const b2fH1Rows = computed(() => state.bookToFloorRows.value.map(toH1CheckRow))
const f2bH1Rows = computed(() => state.floorToBookRows.value.map(toH1CheckRow))
const b2fVariance = computed(() => b2fH1Rows.value.filter((r) => calcRowDiffs(r).hasVariance).length)
const f2bVariance = computed(() => f2bH1Rows.value.filter((r) => calcRowDiffs(r).hasVariance).length)

function onRowUpdate(rowId: string, patch: Partial<H1Row>): void {
  state.updateCheckFromH1(rowId, patch)
}

async function handleAddRow(direction: StocktakeDirection) {
  try {
    const { value } = await ElMessageBox.prompt('请输入盘点项目', '新增检查项', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (value) state.addCheckRow(value, direction)
  } catch { /* cancelled */ }
}

function onDraftConclusion(): void {
  if (props.isReadonly) return
  const rows = state.checkRows.value
  const matchCount = rows.filter((r) => r.result === '账实相符' || Math.abs(r.sampleQty - r.bookQty) < 0.001).length
  const varianceCount = rows.filter((r) => calcRowDiffs(r).hasVariance).length
  const text = draftH5CheckConclusion({
    total: rows.length,
    matchCount,
    varianceCount,
    bookToFloorCount: state.bookToFloorRows.value.length,
    floorToBookCount: state.floorToBookRows.value.length,
  })
  savePolishConclusion(text)
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h5-tab-stocktake-check { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.ml-tag { margin-left: 8px; }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-bottom: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
