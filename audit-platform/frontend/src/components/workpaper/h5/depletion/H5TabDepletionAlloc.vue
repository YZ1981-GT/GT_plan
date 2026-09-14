<template>
  <div class="h5-tab-depletion-alloc">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" title="审计目标：验证本期折耗在各成本中心的分配合理、分配合计与折耗总额一致，并联动 D5 营业成本。" class="objective-alert" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H5-13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.allocRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-13 折耗分配分析表（11公式）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H5-13')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="balance-bar">
        <span>折耗总额: <b>{{ fmtAmt(state.totalCurrentDepletion.value) }}</b></span>
        <span>已分配: <b>{{ fmtAmt(state.totalAllocAmount.value) }}</b></span>
        <el-tag :type="state.allocIsBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.allocIsBalanced.value ? '分配平衡 ✓' : '未平衡' }}
        </el-tag>
      </div>

      <el-table :data="state.allocRows.value" border stripe size="small" class="alloc-table">
        <el-table-column prop="costCenter" label="成本中心" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.costCenter" size="small" @change="state.updateAllocCell(row.rowId, 'costCenter', $event)" />
            <span v-else>{{ row.costCenter }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocRatio" label="分配比例(%)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocRatio" :controls="false" :precision="2" :min="0" :max="100" size="small"
              @change="state.updateAllocCell(row.rowId, 'allocRatio', $event ?? 0)" />
            <span v-else>{{ row.allocRatio.toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="分配金额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=折耗总额×分配比例">{{ fmtAmt(row.allocAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="state.updateAllocCell(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" size="small" :disabled="!state.allocIsBalanced.value" @click="state.publishDepletionAlloc()">
        发布折耗分配 → D5营业成本
      </el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNoteText" :autosize="{ minRows: 5 }"
        placeholder="填写折耗分配审计说明..." :disabled="isReadonly" @change="savePolishNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusionText" :autosize="{ minRows: 3 }"
        placeholder="填写折耗分配审计结论..." :disabled="isReadonly" @change="savePolishConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折耗分配将各油田折耗计入对应的营业成本科目</li>
        <li>分配比例合计应=100%，分配金额合计=折耗总额</li>
        <li>发布后联动D5营业成本底稿(EventBus depletion:allocated)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH5Depletion } from '../../composables/useH5Depletion'
import { useH5FormData } from '../../composables/useH5FormData'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

// 审计说明/结论（component-local H5-13，沿用 useH5FormData 契约，conclusion:null）
const NOTE_KEY = 'H5-13-audit-note'
const CONCLUSION_KEY = 'H5-13-audit-conclusion'
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

const state = useH5Depletion({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
  onPublishEvent: (event: string, payload: any) => {
    // Emit depletion:allocated → D5 via real EventBus
    eventBus.emit(event as any, { ...payload, timestamp: Date.now() })
  },
})

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-depletion-alloc { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.balance-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; font-size: var(--wp-font-size, 13px); }
.alloc-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.action-bar { margin: 12px 0; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
