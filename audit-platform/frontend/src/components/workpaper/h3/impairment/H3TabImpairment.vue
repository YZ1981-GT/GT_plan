<template>
  <div class="h3-tab-impairment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产减值测算（H3-10），仅成本模式适用；公允价值模式不计提减值。</p>
        <p>2. 先判断减值迹象（CAS8），存在迹象时测算：减值 = MAX(账面价值 − 可收回金额, 0)。</p>
        <p>3. 可收回金额取公允价值减处置费用与预计未来现金流量现值（DCF）孰高，详见 H3-11。</p>
        <p>4. 减值损失一经确认不得转回；减值结果应与 H3-1 审定表、附注披露勾稽。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产（成本模式）减值迹象判断的充分性与减值测算的准确性，确认减值损失确认恰当。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-10" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ impairmentCalcRows.length }} 行</el-tag>
    </div>

    <!-- 仅成本模式提示 -->
    <el-alert title="减值测算（H3-10）— 仅成本模式适用" type="info" :closable="false" show-icon class="mode-alert" />

    <!-- 区域1：减值迹象判断 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>一、减值迹象判断</span>
          <el-button size="small" @click="generateAI('H3-10-signs')">AI</el-button>
        </div>
      </template>
      <el-table :data="impairmentSigns" border size="small" class="audit-table">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="indicator" label="减值迹象" min-width="200" />
        <el-table-column prop="exists" label="是否存在" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select v-model="row.exists" size="small" :disabled="isReadonly" @change="onSignChange($index, row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="判断依据" min-width="200">
          <template #default="{ row, $index }">
            <el-input v-model="row.evidence" size="small" :disabled="isReadonly" @change="onSignChange($index, row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域2：减值测算表 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>二、减值测算表</span>
          <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-11 可收回金额')">→ H3-11 DCF模型</el-tag>
        </div>
      </template>
      <el-table :data="impairmentCalcRows" border size="small" class="audit-table">
        <el-table-column prop="assetName" label="资产名称" min-width="120" />
        <el-table-column prop="bookValue" label="账面价值" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onCalcChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="recoverableAmount" label="可收回金额" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.recoverableAmount" size="small" :disabled="isReadonly" @change="onCalcChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="减值=MAX(账面-可收回,0)" min-width="140" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-danger': row.impairmentLoss > 0 }">
              {{ fmtNum(row.impairmentLoss) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCalcChange($index, row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-10')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-10')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：减值迹象判断依据、可收回金额确定方法、减值测算与确认情况。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、减值迹象判断充分、测算准确。B、除下列事项外未见异常。C、减值确认存在重大问题，不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabImpairment.vue — H3-10 减值测算（仅成本模式）
 * 减值迹象+测算表+GtIndexChip→H3-11
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { useH3Impairment } from '../../composables/useH3Impairment'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  impairmentSigns, impairmentCalcRows, updateSign, updateCalcRow,
} = useH3Impairment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-10-audit-note'
const CONCLUSION_KEY = 'H3-10-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onSignChange(index: number, row: any) { updateSign(index, row) }
function onCalcChange(index: number, row: any) { updateCalcRow(index, row) }

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.mode-alert { margin-bottom: 16px; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.nav-chip { cursor: pointer; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.conclusion-card { margin-top: 16px; }
.action-btns { display: flex; gap: 4px; }
</style>
