<template>
  <div class="n1-loss-matrix">
    <div class="matrix-hint">
      复核视角：一屏查看各亏损年度的确认判断。色块=判断结论（绿=通过／黄=需关注／红=不可确认／灰=未填）{{ readonly ? '，点击行可定位结构化视图。' : '，点击色块可直接切换判断（是否充足/来源三选）。' }}
    </div>

    <el-table
      :data="computedRows"
      size="small"
      border
      :row-class-name="rowClass"
      @row-click="handleRowClick"
    >
      <el-table-column label="到期年度" prop="expiryYear" width="96" align="center">
        <template #default="{ row }">
          <span :class="{ 'text-expired': row.isExpired }">{{ row.expiryYear }}</span>
          <el-tag v-if="row.isExpired" type="danger" size="small" style="margin-left:4px">届满</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="审定金额" width="130" align="right">
        <template #default="{ row }">{{ fmt(row.auditedAmount) }}</template>
      </el-table-column>

      <el-table-column label="确认金额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-muted': row.isExpired }">{{ row.isExpired ? '—' : fmt(row.recognizedAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="不确认金额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'text-danger-bold': row.unrecognizedAmount > 0 }">{{ fmt(row.unrecognizedAmount) }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 判断矩阵列（源模板语义） ═══ -->

      <!-- 1. 弥补期限是否届满（只读派生，不可点选） -->
      <el-table-column label="弥补期限" width="100" align="center">
        <template #default="{ row }">
          <span :class="['cell-flag', row.isExpired ? 'flag-bad' : 'flag-ok']">
            {{ row.isExpired ? '已届满' : '未届满' }}
          </span>
        </template>
      </el-table-column>

      <!-- 2. 到期前是否有足够应纳税所得额（可点选 toggle） -->
      <el-table-column label="是否充足" width="100" align="center">
        <template #header>
          <el-tooltip content="到期前是否有足够的应纳税所得额" placement="top">
            <span>是否充足</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            :class="['cell-flag', sufficiencyFlagClass(row), !readonly && !row.isExpired ? 'clickable' : '']"
            @click.stop="handleToggleSufficient(row)"
          >
            {{ sufficiencyLabel(row) }}
          </span>
        </template>
      </el-table-column>

      <!-- 3. 来源：生产经营所得（可点选 toggle） -->
      <el-table-column label="经营所得" width="95" align="center">
        <template #header>
          <el-tooltip content="预计应纳税所得额来源于生产经营所得" placement="top">
            <span>经营所得</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            :class="['cell-flag', row.sourceOperating ? 'flag-ok' : 'flag-empty', !readonly && !row.isExpired ? 'clickable' : '']"
            @click.stop="handleToggleSource(row, 'sourceOperating')"
          >
            {{ row.sourceOperating ? '√' : '—' }}
          </span>
        </template>
      </el-table-column>

      <!-- 4. 来源：应纳税暂时性差异（可点选 toggle） -->
      <el-table-column label="暂时性差异" width="100" align="center">
        <template #header>
          <el-tooltip content="预计应纳税所得额来源于以前期间产生的应纳税暂时性差异" placement="top">
            <span>暂时性差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            :class="['cell-flag', row.sourceTemporaryDiff ? 'flag-ok' : 'flag-empty', !readonly && !row.isExpired ? 'clickable' : '']"
            @click.stop="handleToggleSource(row, 'sourceTemporaryDiff')"
          >
            {{ row.sourceTemporaryDiff ? '√' : '—' }}
          </span>
        </template>
      </el-table-column>

      <!-- 5. 来源：其他（可点选 toggle） -->
      <el-table-column label="其他来源" width="90" align="center">
        <template #header>
          <el-tooltip content="预计应纳税所得额来源于其他原因" placement="top">
            <span>其他来源</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            :class="['cell-flag', row.sourceOther ? 'flag-ok' : 'flag-empty', !readonly && !row.isExpired ? 'clickable' : '']"
            @click.stop="handleToggleSource(row, 'sourceOther')"
          >
            {{ row.sourceOther ? '√' : '—' }}
          </span>
        </template>
      </el-table-column>

      <!-- 6. 依据是否已填（只读派生） -->
      <el-table-column label="依据已填" width="90" align="center">
        <template #default="{ row }">
          <span :class="['cell-flag', row.basis ? 'flag-ok' : 'flag-empty']">
            {{ row.basis ? '已填' : '未填' }}
          </span>
        </template>
      </el-table-column>

      <!-- 7. 检查底稿索引是否已填（只读派生） -->
      <el-table-column label="索引已填" width="90" align="center">
        <template #default="{ row }">
          <span :class="['cell-flag', row.indexRef ? 'flag-ok' : 'flag-empty']">
            {{ row.indexRef ? '已填' : '未填' }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <div class="matrix-summary">
      <span>共 {{ computedRows.length }} 个到期年度</span>
      <span class="sep">·</span>
      <span class="s-bad">已届满 {{ expiredCount }}</span>
      <span class="sep">·</span>
      <span class="s-warn">所得额不足 {{ insufficientCount }}</span>
      <span class="sep">·</span>
      <span class="s-empty">依据未填 {{ missingBasisCount }}</span>
      <span class="sep">·</span>
      <span class="s-empty">索引未填 {{ missingIndexCount }}</span>
      <span class="sep">·</span>
      <span class="s-ok">可确认 {{ recognizableCount }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * N1LossJudgmentMatrix — N1-5 可弥补亏损「判断矩阵」视图
 *
 * Task: 3.2
 * Requirements: 1.6, 8.1
 *
 * 判断项列按源模板语义：
 *   弥补期限是否届满（只读派生 isExpired → red/green indicator）
 *   到期前是否有足够应纳税所得额（sufficient → yes/no toggle）
 *   来源：生产经营所得（sourceOperating → boolean toggle）
 *   来源：应纳税暂时性差异（sourceTemporaryDiff → boolean toggle）
 *   来源：其他（sourceOther → boolean toggle）
 *   依据是否已填（basis non-empty → green/red indicator, read-only derived）
 *   检查底稿索引是否已填（indexRef non-empty → green/red indicator, read-only derived）
 *
 * - `readonly` 时保持只读色块行为（零回归，Req 8.1）
 * - In editable mode, clicking a cell toggles the corresponding boolean/enum value
 */
import { computed } from 'vue'

export interface N1LossMatrixRow {
  expiryYear: number
  auditedAmount: number
  recognizedAmount: number
  unrecognizedAmount: number
  isExpired: boolean
  sufficient: string // 'yes' | 'no' | ''
  sourceOperating: boolean
  sourceTemporaryDiff: boolean
  sourceOther: boolean
  basis: string
  indexRef: string
  recognizableAsset: number
}

const props = defineProps<{
  rows: N1LossMatrixRow[]
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'locate', index: number): void
  (e: 'toggle', payload: { index: number; field: 'sufficient' | 'sourceOperating' | 'sourceTemporaryDiff' | 'sourceOther' }): void
}>()

// ─── Computed ─────────────────────────────────────────────────────────────────

const computedRows = computed(() => props.rows ?? [])

const expiredCount = computed(() => computedRows.value.filter(r => r.isExpired).length)
const insufficientCount = computed(() => computedRows.value.filter(r => r.sufficient === 'no').length)
const missingBasisCount = computed(() => computedRows.value.filter(r => !r.basis && r.unrecognizedAmount > 0).length)
const missingIndexCount = computed(() => computedRows.value.filter(r => !r.indexRef).length)
const recognizableCount = computed(() => computedRows.value.filter(r => r.recognizableAsset > 0).length)

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function sufficiencyFlagClass(row: N1LossMatrixRow): string {
  if (row.isExpired) return 'flag-muted'
  if (row.sufficient === 'yes') return 'flag-ok'
  if (row.sufficient === 'no') return 'flag-bad'
  return 'flag-empty'
}

function sufficiencyLabel(row: N1LossMatrixRow): string {
  if (row.isExpired) return '不适用'
  if (row.sufficient === 'yes') return '充足'
  if (row.sufficient === 'no') return '不足'
  return '未判'
}

function rowClass({ row }: { row: N1LossMatrixRow }): string {
  if (row.isExpired) return 'matrix-row-expired'
  if (row.sufficient === 'no') return 'matrix-row-insufficient'
  return ''
}

// ─── Interaction ──────────────────────────────────────────────────────────────

function handleRowClick(row: N1LossMatrixRow) {
  const idx = computedRows.value.indexOf(row)
  if (idx >= 0) {
    emit('locate', idx)
  }
}

function handleToggleSufficient(row: N1LossMatrixRow) {
  if (props.readonly || row.isExpired) return
  const idx = computedRows.value.indexOf(row)
  if (idx >= 0) {
    emit('toggle', { index: idx, field: 'sufficient' })
  }
}

function handleToggleSource(row: N1LossMatrixRow, field: 'sourceOperating' | 'sourceTemporaryDiff' | 'sourceOther') {
  if (props.readonly || row.isExpired) return
  const idx = computedRows.value.indexOf(row)
  if (idx >= 0) {
    emit('toggle', { index: idx, field })
  }
}
</script>

<style scoped>
.n1-loss-matrix {
  font-size: var(--wp-font-size, 13px);
}

.matrix-hint {
  padding: 8px 12px;
  margin-bottom: 10px;
  background: #f4f4f5;
  border-left: 4px solid #909399;
  border-radius: 4px;
  color: #606266;
  line-height: 1.6;
}

.n1-loss-matrix :deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

.n1-loss-matrix :deep(.el-table__row) {
  cursor: pointer;
}

.n1-loss-matrix :deep(.matrix-row-expired) {
  background: #fef0f0;
}

.n1-loss-matrix :deep(.matrix-row-insufficient) {
  background: #fdf6ec;
}

.cell-flag {
  display: inline-block;
  min-width: 56px;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.7;
  text-align: center;
  user-select: none;
}

.cell-flag.clickable {
  cursor: pointer;
  transition: transform 0.1s ease, box-shadow 0.1s ease;
}

.cell-flag.clickable:hover {
  transform: scale(1.08);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

.cell-flag.clickable:active {
  transform: scale(0.95);
}

.flag-ok {
  background: #f0f9eb;
  color: #529b2e;
}

.flag-warn {
  background: #fdf6ec;
  color: #b88230;
}

.flag-bad {
  background: #fef0f0;
  color: #c45656;
}

.flag-empty {
  background: #f4f4f5;
  color: #909399;
}

.flag-muted {
  background: transparent;
  color: #a8abb2;
}

/* ─── Text helpers ─── */
.text-expired {
  color: #dc2626;
  font-weight: 600;
}

.text-muted {
  color: #909399;
}

.text-danger-bold {
  color: #dc2626;
  font-weight: 600;
}

/* ─── Summary ─── */
.matrix-summary {
  margin-top: 10px;
  color: #606266;
}

.matrix-summary .sep {
  margin: 0 8px;
  color: #c0c4cc;
}

.matrix-summary .s-ok {
  color: #529b2e;
}

.matrix-summary .s-warn {
  color: #b88230;
}

.matrix-summary .s-bad {
  color: #c45656;
}

.matrix-summary .s-empty {
  color: #909399;
}
</style>
