<template>
  <div class="f2-val-sheet">
    <header class="sheet-header">
      <div><h3>生产成本分配</h3><span class="code">F2-44</span></div>
      <div class="stat-row">
        <span class="stat">分配合计 {{ ca.allocGrandTotal.value.toLocaleString() }}</span>
        <el-tag v-if="ca.allocationMismatch.value" type="danger" size="small">分配差异需关注</el-tag>
      </div>
    </header>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 生产成本按合理的分配基准（工时/机时/产量/定额工资等）在完工产品与在产品、各产品品种间分配，方法须前后一致（CAS 1 号存货）。</p>
        <p>2. 灰色底纹列为自动计算列（基准占比、分配合计、差异），系统据来源底稿与分配基准自动计算，不可手工编辑。</p>
        <p>3. 分配合计应与 F2-41 材料、F2-42 人工、F2-43 制造费用来源合计勾稽一致，差异>0.01 自动标红提示复核分配基准。</p>
        <p>4. 分配基准应与生产实际相关且可验证，避免人为调节完工与在产品成本、跨期结转损益。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证生产成本在完工产品与在产品间分配基准的合理性与一贯性，确认三项成本要素分配合计与来源底稿勾稽一致，防止成本分配错误影响存货计价。"
      class="objective-alert"
    />

    <div class="source-bar">
      <span>来源底稿联动：</span>
      <GtIndexChip value="wp:F2-41" />
      <GtIndexChip value="wp:F2-42" />
      <GtIndexChip value="wp:F2-43" />
      <span class="source-nums">
        材料 {{ ca.sourceTotals.value.material.toLocaleString() }}
        | 人工 {{ ca.sourceTotals.value.labor.toLocaleString() }}
        | 制造费用 {{ ca.sourceTotals.value.overhead.toLocaleString() }}
      </span>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ca.addRow()">+ 新增产品</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-44"
          :disabled="isReadonly"
          ai-section="cost-analysis"
          :existing-content="ca.auditNote.value"
          review-section="F2-44-conclusion"
          @ai-filled="(t: string) => { ca.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ ca.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="ca.enrichedRows.value" border size="small" max-height="420">
      <el-table-column label="产品" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.productName" size="small"
            @change="(v: string) => ca.updateRow(row.rowId, { productName: v })" />
          <span v-else>{{ row.productName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="分配基准" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.allocationBase" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { allocationBase: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="基准占比%" width="95" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula" title="分配基准 ÷ 基准合计 × 100%">{{ row.baseRatio.toFixed(1) }}</span></template>
      </el-table-column>
      <el-table-column label="材料分配" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.materialAlloc" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { materialAlloc: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="人工分配" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.laborAlloc" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { laborAlloc: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="费用分配" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.overheadAlloc" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ca.updateRow(row.rowId, { overheadAlloc: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="分配合计" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula" title="材料分配 + 人工分配 + 费用分配">{{ row.totalAlloc.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="差异" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula" title="分配合计 − 按基准占比应分配额" :class="Math.abs(row.variance) > 0.01 ? 'warn-text' : ''">{{ row.variance.toFixed(0) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="ca.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input v-model="ca.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="生产成本分配合理性审计说明..." />
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
import { useF2CostAllocation } from '../../composables/useF2CostAllocation'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const ca = useF2CostAllocation({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计结论（独立持久化，F2 计价组事件） ───────────────────────────────
const CONCLUSION_KEY = 'F2-44-audit-conclusion'
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
<style scoped>
.source-nums { margin-left: auto; font-weight: 500; color: #303133; }
.warn-text { color: #f56c6c; font-weight: 600; }
</style>
