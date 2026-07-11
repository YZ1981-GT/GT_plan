<template>
  <div class="f2-obsolete">
    <h3 class="title">长库龄呆滞超保质期存货 F2-48</h3>
    <div class="summary">
      <el-tag size="small">长库龄 ≥365天: {{ obs.summary.value.longAgeCount }}</el-tag>
      <el-tag size="small" type="warning">呆滞: {{ obs.summary.value.obsoleteCount }}</el-tag>
      <el-tag size="small" type="danger">超保质期: {{ obs.summary.value.expiredCount }}</el-tag>
      <el-tag size="small" type="info">建议跌价合计: {{ obs.summary.value.impairmentTotal.toLocaleString() }}</el-tag>
    </div>
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 识别长库龄（≥365 天）、呆滞及超保质期存货，结合处置方案评估其可变现净值，判断跌价准备计提的充分性（CAS 1 号存货）。</p>
        <p>2. 灰色底纹列为自动计算列（剩余天数、建议跌价），据库龄/保质期与处置方案自动测算，不可手工编辑。</p>
        <p>3. 超保质期（剩余天数为负）自动标红、长库龄/呆滞行标橙，须逐项落实处置方案与可回收金额，评价管理层跌价计提是否恰当。</p>
        <p>4. 关注呆滞存货是否长期挂账未计提、处置方案是否具备可执行性与商业实质。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：识别长库龄、呆滞及超保质期存货，评估其可变现净值，验证跌价准备计提的充分性与完整性，防止存货高估。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="obs.addRow()">+ 新增行</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-48"
          :disabled="isReadonly"
          ai-section="impairment-evaluation"
          :existing-content="obs.auditNote.value"
          review-section="F2-48-conclusion"
          @ai-filled="(t: string) => { obs.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ obs.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>
    <el-table :data="obs.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''">
      <el-table-column label="品名" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => obs.updateRow(row.rowId, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="数量" width="80">
        <template #default="{ row }">
          <el-input-number :model-value="row.qty" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { qty: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="账面成本" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.bookCost" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { bookCost: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="库龄(天)" width="90">
        <template #default="{ row }">
          <el-input-number :model-value="row.ageDays" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { ageDays: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="保质期(天)" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.shelfDays" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => obs.updateRow(row.rowId, { shelfDays: v ?? 365 })" />
        </template>
      </el-table-column>
      <el-table-column label="剩余天数" width="80" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula" title="保质期(天) − 库龄(天)" :class="{ expired: row.expired }">{{ row.remainingDays }}</span>
        </template>
      </el-table-column>
      <el-table-column label="呆滞" width="60">
        <template #default="{ row }">
          <el-checkbox :model-value="row.isObsolete" :disabled="isReadonly"
            @change="(v: boolean) => obs.updateRow(row.rowId, { isObsolete: !!v })" />
        </template>
      </el-table-column>
      <el-table-column label="处置方案" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.disposalPlan" size="small"
            @change="(v: string) => obs.updateRow(row.rowId, { disposalPlan: v })">
            <el-option v-for="opt in DISPOSAL_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.disposalPlan }}</span>
        </template>
      </el-table-column>
      <el-table-column label="建议跌价" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula" title="据库龄/呆滞/超保质期与处置方案测算的建议跌价金额">{{ row.suggestedImpairment.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="obs.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">审计说明</span></div>
      </template>
      <el-input v-model="obs.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="长库龄/呆滞/超保质期存货审计说明..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2ObsoleteInventory, DISPOSAL_OPTIONS } from '../../composables/useF2ObsoleteInventory'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const obs = useF2ObsoleteInventory({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-obsolete { padding: 12px; font-size: 13px; }
.f2-obsolete :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-obsolete :deep(.el-table .cell) { font-size: 13px !important; }
.title { margin: 0 0 8px; }
.summary { margin-bottom: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
.expired { color: #f56c6c; font-weight: 600; }
:deep(.warn-row) { background: #fdf6ec; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; font-size: 13px; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
