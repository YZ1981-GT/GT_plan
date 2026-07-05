<template>
<div class="d5-fair-value">
    <!-- OCI差异提示 -->
    <el-alert
      v-if="ociDiffMessage"
      type="warning"
      :title="ociDiffMessage"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    />

    <!-- 工具栏 -->
    <div class="fv-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
        添加测算行
      </el-button>
      <el-button size="small" :disabled="isReadonly" @click="exportTemplate">导出模板</el-button>
      <el-button size="small" :disabled="isReadonly" @click="exportData">导出数据</el-button>
      <el-upload
        :show-file-list="false"
        accept=".xlsx"
        :auto-upload="false"
        :disabled="isReadonly || importing"
        @change="(f: any) => onImportFile(f.raw || f)"
      >
        <el-button size="small" :disabled="isReadonly || importing">导入数据</el-button>
      </el-upload>
      <div class="default-rate-config">
        <span class="rate-label">全表默认贴现利率：</span>
        <el-input-number
          :model-value="defaultDiscountRate"
          :min="0"
          :max="1"
          :step="0.001"
          :precision="4"
          :controls="false"
          size="small"
          style="width: 100px"
          :disabled="isReadonly"
          @change="(val: number) => setDefaultRate(val ?? 0)"
        />
        <span class="rate-pct">{{ ((defaultDiscountRate ?? 0) * 100).toFixed(2) }}%</span>
      </div>
    </div>

    <!-- 公允价值测算表 -->
    <el-table
      :data="rows"
      size="small"
      border
      stripe
      style="width: 100%"
      @cell-contextmenu="onCellContextMenu"
    >
      <!-- A: 类别 -->
      <el-table-column label="类别" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="类别"
            @change="(val: string) => updateCell(row.rowId, 'category', val)"
          >
            <el-option label="应收票据" value="应收票据" />
            <el-option label="应收账款" value="应收账款" />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <!-- B: 明细项目 -->
      <el-table-column label="明细项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.itemName"
            size="small"
            @change="(val: string) => updateCell(row.rowId, 'itemName', val)"
          />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>

      <!-- C: 票据号 -->
      <el-table-column label="票据号" width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.billNo"
            size="small"
            @change="(val: string) => updateCell(row.rowId, 'billNo', val)"
          />
          <span v-else>{{ row.billNo }}</span>
        </template>
      </el-table-column>

      <!-- D: 票面金额 -->
      <el-table-column label="票面金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.faceValue"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'faceValue', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.faceValue) }}</span>
        </template>
      </el-table-column>

      <!-- E: 计量日 -->
      <el-table-column label="计量日" width="130">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.measurementDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            style="width:100%"
            @update:model-value="(val: string) => updateCell(row.rowId, 'measurementDate', val || '')"
          />
          <span v-else>{{ row.measurementDate }}</span>
        </template>
      </el-table-column>

      <!-- F: 到期日 -->
      <el-table-column label="到期日" width="130">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.maturityDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            style="width:100%"
            @update:model-value="(val: string) => updateCell(row.rowId, 'maturityDate', val || '')"
          />
          <span v-else>{{ row.maturityDate }}</span>
        </template>
      </el-table-column>

      <!-- G: 剩余天数 (自动) -->
      <el-table-column label="剩余天数" width="90" align="right">
        <template #default="{ row }">
          <span :class="{ 'warning-cell': row.remainingDays <= 0 && row.maturityDate }">
            {{ row.remainingDays }}
          </span>
        </template>
      </el-table-column>

      <!-- H: 市场贴现利率 -->
      <el-table-column label="贴现利率" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.discountRate"
            :min="0"
            :max="1"
            :step="0.001"
            :precision="4"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(val: number) => updateCell(row.rowId, 'discountRate', val ?? 0)"
          />
          <span v-else>{{ (row.discountRate * 100).toFixed(2) }}%</span>
        </template>
      </el-table-column>

      <!-- I: 贴现利息 (自动) -->
      <el-table-column label="贴现利息" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.discountInterest) }}</span>
        </template>
      </el-table-column>

      <!-- J: 贴现金额 (自动) -->
      <el-table-column label="贴现金额" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.discountAmount) }}</span>
        </template>
      </el-table-column>

      <!-- K: 公允价值 (自动) -->
      <el-table-column label="公允价值" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.fairValue) }}</span>
        </template>
      </el-table-column>

      <!-- L: 公允价值层次 -->
      <el-table-column label="层次" width="110">
        <template #default="{ row }">
          <el-tooltip :content="FV_HIERARCHY_TOOLTIP" placement="top">
            <el-select
              v-if="!isReadonly"
              :model-value="row.fvHierarchy"
              size="small"
              placeholder="层次"
              @change="(val: string) => updateCell(row.rowId, 'fvHierarchy', val)"
            >
              <el-option label="第二层次" value="第二层次" />
              <el-option label="第三层次" value="第三层次" />
            </el-select>
            <span v-else>
              {{ row.fvHierarchy }}
              <GtIndexChip v-if="row.fvHierarchy" wp-code="附注披露" label="附注" />
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- M: 备注 -->
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(val: string) => updateCell(row.rowId, 'remark', val)"
          />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly"
            type="danger"
            text
            size="small"
            @click="removeRow(row.rowId)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-row">
      <span>票面合计：{{ fmtAmount(totalRow.faceValue) }}</span>
      <span>贴现利息合计：{{ fmtAmount(totalRow.discountInterest) }}</span>
      <span class="fv-total">公允价值合计：{{ fmtAmount(totalRow.fairValue) }}</span>
    </div>

    <!-- 审计说明区域 -->
    <div class="audit-notes-section">
      <h4>审计说明（评价贴现利率合理性 + 层次判定依据）</h4>
      <el-input
        v-model="auditNotes.explanation"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="评价市场贴现利率选取依据的合理性，说明公允价值层次判定依据..."
      />
      <div class="note-actions">
        <el-button
          size="small"
          :disabled="isReadonly || !aiAvailable || aiLoading"
          :loading="aiLoading"
          @click="genFairValueNote"
        >🤖AI</el-button>
      </div>
    </div>

    <!-- 审计结论区域 -->
    <div class="audit-conclusion-section">
      <h4>审计结论</h4>
      <el-input
        v-model="auditNotes.conclusion"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="对公允价值测算结果的总结性结论..."
      />
    </div>
</div>
</template>

<script setup lang="ts">
/**
 * D5TabFairValue.vue — D5-4 公允价值测算
 *
 * el-table 13列，自动计算列灰底（G/I/J/K）
 * 贴现公式：票面 × 利率 × 天数 / 360
 * 全表默认利率 + 逐行可覆盖
 * OCI差异提示（黄色el-alert）
 *
 * Task: 15.1
 * Requirements: 6.1-6.10, 10.7
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { useD5FairValue, FV_HIERARCHY_TOOLTIP } from '../composables/useD5FairValue'
import type { ChecklistResponse } from '../composables/useD5FormData'
import { useD5ImportExport } from '../composables/useD5ImportExport'
import { useD5AiGenerate } from '../composables/useD5AiGenerate'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  periodEnd: string
  defaultDiscountRate: number
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD5ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D5-4',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
}

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  totalRow,
  ociDiffMessage,
  addRow,
  removeRow,
  updateCell,
  setDefaultRate,
  auditNotes,
} = useD5FairValue({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  periodEnd: computed(() => props.periodEnd) as unknown as Ref<string>,
  defaultDiscountRate: computed(() => props.defaultDiscountRate) as unknown as Ref<number>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD5AiGenerate(toRef(props, 'wpId'))

async function genFairValueNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('fair-value-note', auditNotes.value.explanation, {
    task: '公允价值测算审计说明（贴现利率合理性+层次判定）',
    rowCount: rows.value.length,
    ociDiffMessage: ociDiffMessage.value || '',
  }, 'AI · 公允价值说明')
  if (text) auditNotes.value.explanation = text
}

// ─── Formatting Helpers ──────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCellContextMenu(row: any, _col: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  // 贴现利率列右键复核入口
  openReviewDialog('D5-4-discount-rate')
}
</script>

<style scoped>
.d5-fair-value {
  padding: 16px;
}

.mode-toolbar {
  margin-bottom: 12px;
}

.fv-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.default-rate-config {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.rate-label {
  font-size: 13px;
  color: #606266;
}

.rate-pct {
  font-size: 12px;
  color: #909399;
}

.auto-calc {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  color: #909399;
}

.warning-cell {
  color: #f56c6c;
  font-weight: 600;
}

.total-row {
  display: flex;
  gap: 24px;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 4px;
  margin: 12px 0;
  font-size: 13px;
  font-weight: 600;
}

.fv-total {
  color: #409eff;
}

.audit-notes-section,
.audit-conclusion-section {
  margin-top: 20px;
}

.audit-notes-section h4,
.audit-conclusion-section h4 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

</style>
