<template>
<div class="d5-fair-value">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 应收款项融资以公允价值计量（FVOCI），本表对出售模式的应收票据/账款按贴现法测算期末公允价值。</p>
        <p>2. 贴现公式：贴现利息 = 票面金额 × 市场贴现利率 × 剩余天数 ÷ 360；公允价值 = 票面金额 − 贴现利息。灰底列为自动计算列，不可手工编辑。</p>
        <p>3. 可设置全表默认贴现利率，并逐行覆盖；市场贴现利率的选取依据应在审计说明中评价其合理性。</p>
        <p>4. 公允价值层次（第二/第三层次）判定依据需披露，测算合计与 D5-1 审定表 OCI 变动核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：评价应收款项融资公允价值测算所采用市场贴现利率的合理性与公允价值层次判定的恰当性，确认公允价值及其变动（OCI）计量准确。"
      class="objective-alert"
    />

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
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加测算行</el-button>
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
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx"
                  :auto-upload="false"
                  :disabled="isReadonly || importing"
                  @change="(f: any) => onImportFile(f.raw || f)"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:D5-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
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
      <el-table-column label="剩余天数" width="90" align="right" class-name="auto-calc-col">
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
      <el-table-column label="贴现利息" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.discountInterest) }}</span>
        </template>
      </el-table-column>

      <!-- J: 贴现金额 (自动) -->
      <el-table-column label="贴现金额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.discountAmount) }}</span>
        </template>
      </el-table-column>

      <!-- K: 公允价值 (自动) -->
      <el-table-column label="公允价值" width="110" align="right" class-name="auto-calc-col">
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
              <el-tag v-if="row.fvHierarchy" size="small" type="info" effect="plain">附注</el-tag>
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

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D5-1" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明（评价贴现利率合理性 + 层次判定依据）</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoading"
                :disabled="isReadonly || !aiAvailable" @click="genFairValueNote">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReviewDialog('D5-4-note')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.explanation"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 8 }"
          :disabled="isReadonly"
          placeholder="评价市场贴现利率选取依据的合理性，说明公允价值层次判定依据..."
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" @click="openReviewDialog('D5-4-conclusion')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNotes.conclusion"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 7 }"
          :disabled="isReadonly"
          placeholder="对公允价值测算结果的总结性结论..."
        />
      </div>
    </el-card>
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
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  periodEnd: string
  defaultDiscountRate: number
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

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
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  periodEnd: computed(() => props.periodEnd) as unknown as Ref<string>,
  defaultDiscountRate: computed(() => props.defaultDiscountRate) as unknown as Ref<number>,
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD5AiGenerate(toRef(props, 'wpId'))

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

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
  padding: 12px;
}
.d5-fair-value :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d5-fair-value :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.default-rate-config {
  display: flex;
  align-items: center;
  gap: 6px;
}
.rate-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.rate-pct {
  font-size: 12px;
  color: #909399;
}

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
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
  background: #f5f7fa;
  border-radius: 4px;
  margin: 12px 0;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}
.fv-total {
  color: #409eff;
}

/* 审计意见卡片 */
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
