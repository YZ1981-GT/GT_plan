<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>制造费用明细表</h3><span class="code">F2-43</span></div>
      <div class="stat-row">
        <span class="stat sub">预算 {{ oh.totals.value.budget.toLocaleString() }}</span>
        <span class="stat sub">实际 {{ oh.totals.value.actual.toLocaleString() }}</span>
        <span class="stat">分配 {{ oh.totals.value.allocated.toLocaleString() }}</span>
        <el-tag v-if="oh.mismatchCount.value" type="danger" size="small">{{ oh.mismatchCount.value }} 行分配不符</el-tag>
      </div>
    </header>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 制造费用按费用项目归集预算、实际与分配额，验证费用归集完整性与分配方法的合理性、一贯性（CAS 1 号存货加工成本）。</p>
        <p>2. 灰色底纹列为自动计算列（变动率），据实际与预算自动测算，不可手工编辑。</p>
        <p>3. 分配额与预算/实际不符的行自动标红，须核查分配基准是否恰当、是否存在费用跨期或错误归集。</p>
        <p>4. 关注将期间费用错误计入制造费用、或制造费用未按受益对象合理分配导致存货成本失真的情形。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证制造费用归集的完整性与分配方法的合理性、一贯性，通过预算与实际对比识别异常波动，确认制造费用计入存货成本的准确性。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="oh.addRow()">+ 新增费用项</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-43"
          :disabled="isReadonly"
          ai-section="cost-analysis"
          :existing-content="oh.auditNote.value"
          review-section="F2-43-conclusion"
          @ai-filled="(t: string) => { oh.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ oh.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="oh.enrichedRows.value" border size="small" max-height="460"
      :row-class-name="({ row }) => row.allocMismatch ? 'error-row' : ''"
    >
      <el-table-column label="费用项目" width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.costItem" size="small"
            @change="(v: string) => oh.updateRow(row.rowId, { costItem: v })" />
          <span v-else>{{ row.costItem }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预算" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.budgetAmt" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => oh.updateRow(row.rowId, { budgetAmt: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="实际" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.actualAmt" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => oh.updateRow(row.rowId, { actualAmt: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="分配额" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.allocatedAmt" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => oh.updateRow(row.rowId, { allocatedAmt: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="85" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.varianceRate !== '' && row.varianceRate !== 'N/A'" class="formula" title="(实际 − 预算) ÷ 预算 × 100%">
            {{ (Number(row.varianceRate) * 100).toFixed(1) }}%
          </span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="oh.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input v-model="oh.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="制造费用明细审计说明..." />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, toRef } from 'vue'
import { useF2OverheadDetail } from '../../composables/useF2OverheadDetail'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const oh = useF2OverheadDetail({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计结论（独立持久化，F2 计价组事件） ───────────────────────────────
const CONCLUSION_KEY = 'F2-43-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
