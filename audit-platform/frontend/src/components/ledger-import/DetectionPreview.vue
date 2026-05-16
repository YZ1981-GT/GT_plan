<template>
  <div class="detection-preview">
    <!-- 年度信息 + 预计耗时 -->
    <div v-if="detectionResult" class="year-info">
      <el-tag v-if="detectionResult.detected_year" type="info" size="large">
        识别年度：{{ detectionResult.detected_year }}
        <span class="confidence-text">（置信度 {{ detectionResult.year_confidence }}%）</span>
      </el-tag>
      <el-tag v-else type="warning" size="large">
        未能自动识别年度，请在提交时手动选择
      </el-tag>
      <!-- 4.14: 预计耗时展示 -->
      <el-tag v-if="estimatedMinutes" type="info" size="large" style="margin-left: 8px">
        预计耗时 约 {{ estimatedMinutes }} 分钟
      </el-tag>
      <!-- 4.14: 规模档位 badge -->
      <el-tag
        v-if="detectionResult.size_bucket"
        :type="sizeBucketType"
        size="small"
        effect="dark"
        style="margin-left: 8px"
      >
        {{ detectionResult.size_bucket }}
      </el-tag>
    </div>

    <!-- 10.45: 规模警告横幅 -->
    <el-alert
      v-if="scaleWarnings.length > 0"
      :title="scaleWarnings[0].message"
      type="warning"
      :closable="false"
      show-icon
      style="margin-top: 12px"
    >
      <template #default>
        <p style="margin: 4px 0 0; font-size: var(--gt-font-size-xs); color: var(--el-text-color-secondary)">
          检测到数据规模异常，请确认后继续
        </p>
      </template>
    </el-alert>

    <!-- Sheet 列表表格 -->
    <el-table
      :data="sheetRows"
      border
      stripe
      style="width: 100%; margin-top: 16px"
      max-height="400"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="file_name" label="文件" min-width="120" show-overflow-tooltip />
      <el-table-column prop="sheet_name" label="Sheet" min-width="100" show-overflow-tooltip />

      <el-table-column label="识别类型" width="140">
        <template #default="{ row }">
          <el-select
            v-model="row.table_type"
            size="small"
            placeholder="选择类型"
            :disabled="row.table_type === 'unknown'"
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

      <!-- 10.27: skip_reason badge for unknown sheets -->
      <el-table-column label="状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.table_type === 'unknown' && getSkipReason(row)"
            type="info"
            size="small"
            effect="plain"
          >
            {{ getSkipReason(row) }}
          </el-tag>
          <span v-else-if="row.table_type !== 'unknown'" style="color: var(--el-color-success); font-size: var(--gt-font-size-xs)">
            ✓ 已识别
          </span>
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
      <div style="display: flex; gap: 8px">
        <!-- 10.45: 强制继续按钮（有 scale_warnings 时显示） -->
        <el-button
          v-if="scaleWarnings.length > 0"
          type="warning"
          aria-label="强制继续"
          @click="onForceConfirm"
        >
          强制继续
        </el-button>
        <el-button type="primary" aria-label="确认并继续" @click="onConfirm">确认并继续</el-button>
      </div>
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
      <p style="color: var(--el-color-warning); font-size: var(--gt-font-size-sm)">
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
  confirm: [sheets: SheetDetection[], forceSubmit?: boolean]
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

/** 4.14: 预计耗时（分钟，向上取整） */
const estimatedMinutes = computed<number | null>(() => {
  const seconds = props.detectionResult?.estimated_duration_seconds
  if (typeof seconds !== 'number' || seconds <= 0) return null
  return Math.ceil(seconds / 60)
})

/** 4.14: 规模档位 tag type */
const sizeBucketType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  const bucket = props.detectionResult?.size_bucket
  if (bucket === 'S') return 'success'
  if (bucket === 'M') return 'info'
  if (bucket === 'L') return 'warning'
  if (bucket === 'XL') return 'danger'
  return 'info'
})

/** 10.45: scale_warnings from detect response */
const scaleWarnings = computed<Array<{ code: string; message: string }>>(() => {
  return (props.detectionResult as any)?.scale_warnings || []
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

/** 10.27: 获取 skip_reason 文本 */
function getSkipReason(row: SheetRow): string {
  // detection_evidence.skip_reason.message_cn 或 warnings 中的 SKIPPED_UNKNOWN tag
  const evidence = (row as any).detection_evidence
  if (evidence?.skip_reason?.message_cn) return evidence.skip_reason.message_cn
  if (evidence?.skip_reason?.code) {
    const codeMap: Record<string, string> = {
      ROWS_TOO_FEW: '行数太少',
      HEADER_UNRECOGNIZABLE: '表头无法识别',
      CONTENT_MISMATCH: '列内容不符合',
    }
    return codeMap[evidence.skip_reason.code] || evidence.skip_reason.code
  }
  // Fallback: check warnings for SKIPPED_UNKNOWN tag
  const skipWarn = row.warnings?.find((w: string) => w.startsWith('SKIPPED_UNKNOWN:'))
  if (skipWarn) return skipWarn.replace('SKIPPED_UNKNOWN:', '')
  return row.table_type === 'unknown' ? '未识别' : ''
}

/** 10.27: grey row class for unknown sheets */
function getRowClassName({ row }: { row: SheetRow }): string {
  return row.table_type === 'unknown' ? 'unknown-sheet-row' : ''
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
  doConfirm(false)
}

/** 10.45: 强制继续（忽略 scale_warnings） */
function onForceConfirm() {
  doConfirm(true)
}

function confirmYearConflict() {
  yearConflictVisible.value = false
  doConfirm(false)
}

function doConfirm(forceSubmit: boolean) {
  const sheets = sheetRows.value.filter(r => r.table_type !== 'unknown')
  emit('confirm', sheets, forceSubmit)
}
</script>

<style scoped>
.detection-preview {
  padding: 0 8px;
}

.year-info {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.confidence-text {
  font-size: var(--gt-font-size-xs);
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

/* 10.27: grey card style for unknown sheets */
:deep(.unknown-sheet-row) {
  background-color: var(--el-fill-color-lighter) !important;
  color: var(--el-text-color-placeholder);
  opacity: 0.7;
}
</style>
