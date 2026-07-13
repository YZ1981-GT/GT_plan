<template>
  <div class="f2-loss-contract">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 合同预计总成本超过预计总收入时构成亏损合同，应按 CAS13 号计提预计负债。</p>
        <p>2. 灰底列为自动测算列（是否亏损、完工进度、应确认损失、本期应计提、差异），不可手动编辑。</p>
        <p>3. 应确认损失 = 预计总成本 − 预计总收入；本期应计提为扣除已计提部分后的增量。</p>
        <p>4. 与管理层计提比较，差异标红行须在审计说明中说明并考虑调整分录。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：识别亏损合同并复核预计损失计提的完整性与准确性，确认预计负债恰当反映。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="loss.addRow()">+ 新增项目</el-button>
        <el-tag size="small" type="warning">亏损合同: {{ loss.lossCount.value }}</el-tag>
        <el-tag v-if="loss.adjustCount.value > 0" size="small" type="danger">需调整 {{ loss.adjustCount.value }} 笔</el-tag>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-58"
          :disabled="isReadonly"
          ai-section="loss-analysis"
          :existing-content="loss.auditNote.value"
          review-section="F2-58-loss"
          @ai-filled="(t: string) => { loss.auditNote.value = t }"
        />
        <GtIndexChip value="wp:F2-58" />
        <el-tag size="small" type="info">共 {{ loss.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="loss.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.isLoss ? 'warn-row' : row.needsAdjust ? 'error-row' : ''">
      <el-table-column label="项目" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
            @change="(v: string) => loss.updateRow(row.id, { projectName: v })" />
          <span v-else>{{ row.projectName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预计总收入" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.estimatedTotalRevenue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => loss.updateRow(row.id, { estimatedTotalRevenue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="预计总成本" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.estimatedTotalCost" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => loss.updateRow(row.id, { estimatedTotalCost: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="是否亏损" width="80" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tag :type="row.isLoss ? 'danger' : 'success'" size="small">{{ row.isLoss ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="完工进度" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="完工进度 = 已发生成本 / 预计总成本" placement="top">
            <span class="formula" v-if="typeof row.completionRate === 'number'">{{ (row.rateNum * 100).toFixed(1) }}%</span>
            <span v-else>N/A</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="应确认损失" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="应确认损失 = 预计总成本 − 预计总收入（＞0 时为亏损）" placement="top">
            <span class="formula">{{ row.expectedLoss.toLocaleString() }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本期应计提" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="本期应计提 = 应确认损失 − 已计提部分" placement="top">
            <span class="formula">{{ row.currentProvision.toLocaleString() }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="管理层计提" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.managementProvision" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => loss.updateRow(row.id, { managementProvision: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="差异 = 本期应计提 − 管理层计提" placement="top">
            <span class="formula">{{ row.difference.toLocaleString() }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="loss.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
        </div>
      </template>
      <el-input v-model="loss.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请说明亏损合同的识别、预计损失测算及管理层计提充分性判断……" :disabled="isReadonly" />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, toRef } from 'vue'
import { useF2LossContract } from '../../composables/useF2LossContract'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const loss = useF2LossContract({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// 审计结论（本表独立持久化，item_id 沿用 F2 特殊组 sheet-code 前缀，经 f2-spe:save-items 落库）
const CONCLUSION_KEY = 'F2-58-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<style scoped>
.f2-loss-contract { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-loss-contract :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-loss-contract :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fdf6ec; }
:deep(.error-row) { background: #fef0f0; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
