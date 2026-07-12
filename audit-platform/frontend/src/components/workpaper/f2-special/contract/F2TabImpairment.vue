<template>
  <div class="f2-spe-impairment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 合同履约成本减值 = 账面价值 − 可收回金额（预计剩余合同收入 − 至完工估计成本 − 减值前账面价值）。</p>
        <p>2. 灰底列为自动测算列（完工进度、可收回金额、减值金额、差异），不可手动编辑。</p>
        <p>3. 复核管理层计提是否充分，测算差异标红行须在审计说明中解释并考虑调整。</p>
        <p>4. 减值合计应与合同资产减值损失及审定表勾稽一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：复核合同履约成本减值准备计提的充分性与准确性，确认管理层估计合理、期末余额恰当。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="imp.addRow()">+ 新增项目</el-button>
        <el-tag size="small" type="info">减值合计: {{ imp.impairmentTotal.value.toLocaleString() }}</el-tag>
        <el-tag v-if="imp.diffCount.value > 0" size="small" type="danger">差异 {{ imp.diffCount.value }} 笔</el-tag>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-57"
          :disabled="isReadonly"
          ai-section="impairment-analysis"
          :existing-content="imp.auditNote.value"
          review-section="F2-57-impairment"
          @ai-filled="(t: string) => { imp.auditNote.value = t }"
        />
        <GtIndexChip value="wp:F2-57" />
        <el-tag size="small" type="info">共 {{ imp.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="imp.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.hasDifference ? 'error-row' : ''">
      <el-table-column label="项目" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
            @change="(v: string) => imp.updateRow(row.id, { projectName: v })" />
          <span v-else>{{ row.projectName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预计总收入" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.estimatedTotalRevenue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { estimatedTotalRevenue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="已确认收入" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.recognizedRevenue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { recognizedRevenue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="完工进度" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="完工进度 = 已确认收入 / 预计总收入" placement="top">
            <span class="formula" v-if="typeof row.completionRate === 'number'">{{ (row.completionRate * 100).toFixed(1) }}%</span>
            <span v-else>N/A</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="账面价值" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.bookValue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { bookValue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="可收回金额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="可收回金额 = 预计总收入 − 已确认收入（剩余可回收）" placement="top">
            <span class="formula">{{ row.recoverableAmount.toLocaleString() }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="减值金额" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="减值金额 = 账面价值 − 可收回金额（＞0 时计提）" placement="top">
            <span class="formula">{{ row.impairmentAmount.toLocaleString() }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="管理层计提" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.managementProvision" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { managementProvision: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="差异 = 测算减值金额 − 管理层计提" placement="top">
            <span class="formula">{{ row.difference.toLocaleString() }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="imp.removeRow(row.id)">删</el-button>
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
      <el-input v-model="imp.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请说明减值测算方法、管理层计提充分性判断及差异处理……" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2Impairment } from '../../composables/useF2Impairment'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const imp = useF2Impairment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-spe-impairment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-spe-impairment :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-spe-impairment :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
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
:deep(.error-row) { background: #fef0f0; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
