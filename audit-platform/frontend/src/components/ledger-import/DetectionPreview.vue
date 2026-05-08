<template>
  <div class="detection-preview">
    <!-- 年度信息 -->
    <div v-if="detectionResult" class="year-info">
      <el-tag v-if="detectionResult.detected_year" type="info" size="large">
        识别年度：{{ detectionResult.detected_year }}
        <span class="confidence-text">（置信度 {{ detectionResult.year_confidence }}%）</span>
      </el-tag>
      <el-tag v-else type="warning" size="large">
        未能自动识别年度，请在提交时手动选择
      </el-tag>
    </div>

    <!-- Sheet 列表表格 -->
    <el-table
      :data="sheetRows"
      border
      stripe
      style="width: 100%; margin-top: 16px"
      max-height="400"
    >
      <el-table-column prop="file_name" label="文件" min-width="120" show-overflow-tooltip />
      <el-table-column prop="sheet_name" label="Sheet" min-width="100" show-overflow-tooltip />

      <el-table-column label="识别类型" width="140">
        <template #default="{ row }">
          <el-select
            v-model="row.table_type"
            size="small"
            placeholder="选择类型"
          >
            <el-option label="余额表" value="balance" />
            <el-option label="序时账" value="ledger" />
            <el-option label="辅助余额" value="aux_balance" />
            <el-option label="辅助明细" value="aux_ledger" />
            <el-option label="科目表" value="account_chart" />
            <el-option label="未知" value="unknown" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="置信度" width="90" align="center">
        <template #default="{ row }">
          <el-tooltip
            :content="getConfidenceTooltip(row.table_type_confidence)"
            placement="top"
          >
            <el-tag
              :type="getConfidenceTagType(row.table_type_confidence)"
              size="small"
              effect="dark"
            >
              {{ row.table_type_confidence }}%
            </el-tag>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="关键列覆盖" width="140" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.keyColumnsCovered === row.keyColumnsTotal ? 'success' : 'warning'"
            size="small"
          >
            {{ row.keyColumnsCovered }}/{{ row.keyColumnsTotal }} 关键列{{ row.keyColumnsCovered === row.keyColumnsTotal ? '已识别' : '缺失' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="行数" width="80" align="right">
        <template #default="{ row }">
          {{ row.row_count_estimate.toLocaleString() }}
        </template>
      </el-table-column>

      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" aria-label="预览数据" @click="showPreview(row)">
            预览
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 警告信息 -->
    <div v-if="warnings.length > 0" class="warnings-section">
      <el-alert
        v-for="(warn, idx) in warnings"
        :key="idx"
        :title="warn"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 8px"
      />
    </div>

    <!-- 操作按钮 -->
    <div class="step-actions">
      <el-button aria-label="返回上一步" @click="emit('back')">上一步</el-button>
      <el-button type="primary" aria-label="确认并继续" @click="onConfirm">确认并继续</el-button>
    </div>

    <!-- 预览弹窗 -->
    <el-dialog
      v-model="previewVisible"
      title="数据预览（前 20 行）"
      width="80%"
      append-to-body
    >
      <el-table
        v-if="previewSheet"
        :data="previewData"
        border
        max-height="400"
        size="small"
      >
        <el-table-column
          v-for="(header, colIdx) in previewHeaders"
          :key="colIdx"
          :label="header || `列${colIdx + 1}`"
          :prop="String(colIdx)"
          min-width="100"
          show-overflow-tooltip
        />
      </el-table>
    </el-dialog>

    <!-- 年度冲突警告弹窗 (Task 67) -->
    <el-dialog
      v-model="yearConflictVisible"
      title="⚠️ 年度冲突警告"
      width="450px"
      append-to-body
    >
      <p>文件识别年度与当前项目审计期不一致：</p>
      <el-descriptions :column="1" border size="small" style="margin: 12px 0">
        <el-descriptions-item label="文件识别年度">
          {{ detectionResult?.detected_year || '未识别' }}
        </el-descriptions-item>
        <el-descriptions-item label="置信度">
          {{ detectionResult?.year_confidence || 0 }}%
        </el-descriptions-item>
      </el-descriptions>
      <p style="color: var(--el-color-warning); font-size: 13px">
        请确认是否继续使用识别的年度，或在提交时手动修改。
      </p>
      <template #footer>
        <el-button aria-label="取消" @click="yearConflictVisible = false">取消</el-button>
        <el-button type="primary" aria-label="继续导入" @click="confirmYearConflict">继续导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { LedgerDetectionResult, SheetDetection } from './LedgerImportDialog.vue'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  detectionResult: LedgerDetectionResult | null
}>()

const emit = defineEmits<{
  confirm: [sheets: SheetDetection[]]
  back: []
}>()

// ─── State ──────────────────────────────────────────────────────────────────

const previewVisible = ref(false)
const previewSheet = ref<SheetDetection | null>(null)
const yearConflictVisible = ref(false)

// ─── Computed ───────────────────────────────────────────────────────────────

interface SheetRow extends SheetDetection {
  keyColumnsCovered: number
  keyColumnsTotal: number
}

const sheetRows = computed<SheetRow[]>(() => {
  if (!props.detectionResult) return []
  const rows: SheetRow[] = []
  for (const file of props.detectionResult.files) {
    for (const sheet of file.sheets) {
      const keyMappings = sheet.column_mappings.filter(m => m.column_tier === 'key')
      const covered = keyMappings.filter(m => m.standard_field && m.confidence >= 80).length
      rows.push({
        ...sheet,
        keyColumnsCovered: covered,
        keyColumnsTotal: Math.max(keyMappings.length, 1),
      })
    }
  }
  return rows
})

const warnings = computed<string[]>(() => {
  if (!props.detectionResult) return []
  const warns: string[] = []
  for (const file of props.detectionResult.files) {
    for (const sheet of file.sheets) {
      warns.push(...sheet.warnings)
    }
  }
  // 年度冲突
  if (props.detectionResult.detected_year && props.detectionResult.year_confidence < 60) {
    warns.push('年度识别置信度较低，请确认导入年度是否正确')
  }
  return warns
})

const previewHeaders = computed<string[]>(() => {
  if (!previewSheet.value || previewSheet.value.preview_rows.length === 0) return []
  return previewSheet.value.preview_rows[0] || []
})

const previewData = computed(() => {
  if (!previewSheet.value || previewSheet.value.preview_rows.length <= 1) return []
  return previewSheet.value.preview_rows.slice(1).map(row => {
    const obj: Record<string, string> = {}
    row.forEach((cell, idx) => { obj[String(idx)] = cell })
    return obj
  })
})

// ─── Methods ────────────────────────────────────────────────────────────────

function getConfidenceTagType(confidence: number): 'success' | 'warning' | 'danger' {
  if (confidence >= 80) return 'success'
  if (confidence >= 60) return 'warning'
  return 'danger'
}

function getConfidenceTooltip(confidence: number): string {
  if (confidence >= 80) return '高置信度：自动识别可靠'
  if (confidence >= 60) return '中置信度：建议人工确认'
  return '低置信度：需要手动指定类型'
}

function showPreview(row: SheetDetection) {
  previewSheet.value = row
  previewVisible.value = true
}

function onConfirm() {
  // Check for year conflict (Task 67)
  if (props.detectionResult?.detected_year && props.detectionResult.year_confidence < 60) {
    yearConflictVisible.value = true
    return
  }
  doConfirm()
}

function confirmYearConflict() {
  yearConflictVisible.value = false
  doConfirm()
}

function doConfirm() {
  const sheets = sheetRows.value.filter(r => r.table_type !== 'unknown')
  emit('confirm', sheets)
}
</script>

<style scoped>
.detection-preview {
  padding: 0 8px;
}

.year-info {
  margin-bottom: 8px;
}

.confidence-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.warnings-section {
  margin-top: 16px;
}

.step-actions {
  margin-top: 24px;
  display: flex;
  justify-content: space-between;
}
</style>
