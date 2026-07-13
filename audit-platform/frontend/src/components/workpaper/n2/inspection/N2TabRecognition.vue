<template>
  <div class="n2-tab-recognition">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>应交税金认定表 N2-5</span>
        <el-tag type="info" size="small">54×15 矩阵</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>认定测试矩阵：</strong>
        行=各税种，列=认定项目（存在/完整性/准确性/截止/分类/列报）×期间。
        通过与各测算表（N2-6/N2-8/N2-9/N2-10）交叉验证，判断各税种各认定是否满足。
        ✓ 已验证 / ⚠ 待验证 / ✗ 不满足。
      </div>
    </div>

    <!-- ═══ 交叉验证状态汇总 ═══ -->
    <div class="validation-summary">
      <div class="val-stat val-stat--ok">
        <span class="val-stat-count">{{ validationStats.verified }}</span>
        <span class="val-stat-label">✓ 已验证</span>
      </div>
      <div class="val-stat val-stat--pending">
        <span class="val-stat-count">{{ validationStats.pending }}</span>
        <span class="val-stat-label">⚠ 待验证</span>
      </div>
      <div class="val-stat val-stat--fail">
        <span class="val-stat-count">{{ validationStats.failed }}</span>
        <span class="val-stat-label">✗ 不满足</span>
      </div>
    </div>

    <!-- ═══ 认定矩阵表格 ═══ -->
    <div class="matrix-wrapper">
      <el-table
        :data="matrixRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getMatrixRowClassName"
        max-height="600"
      >
        <!-- 税种列（固定） -->
        <el-table-column prop="taxType" label="税种" width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'tax-header-cell': row._isHeader }">{{ row.taxType }}</span>
          </template>
        </el-table-column>

        <!-- 期间列 -->
        <el-table-column prop="period" label="期间" width="90" align="center" />

        <!-- 6 个认定列 -->
        <el-table-column
          v-for="assertion in ASSERTIONS"
          :key="assertion.key"
          :label="assertion.label"
          width="85"
          align="center"
        >
          <template #header>
            <el-tooltip :content="assertion.tooltip" placement="top">
              <span class="assertion-header">{{ assertion.label }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <template v-if="row._isHeader">—</template>
            <template v-else>
              <el-select
                v-if="!isReadonly"
                :model-value="getCellValue(row.id, assertion.key)"
                size="small"
                style="width: 65px"
                @change="(val: string) => handleCellChange(row.id, assertion.key, val)"
              >
                <el-option value="✓" label="✓" />
                <el-option value="⚠" label="⚠" />
                <el-option value="✗" label="✗" />
                <el-option value="" label="—" />
              </el-select>
              <span v-else :class="getCellClass(row.id, assertion.key)">
                {{ getCellValue(row.id, assertion.key) || '—' }}
              </span>
            </template>
          </template>
        </el-table-column>

        <!-- 交叉验证来源 -->
        <el-table-column label="验证来源" min-width="130">
          <template #default="{ row }">
            <span v-if="row.crossRef" class="cross-ref-badge">{{ row.crossRef }}</span>
            <span v-else class="no-ref">—</span>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <template v-if="!row._isHeader && !isReadonly">
              <el-input
                :model-value="row.remark"
                size="small"
                placeholder="备注"
                @input="(val: string) => handleRemarkChange(row.id, val)"
              />
            </template>
            <span v-else>{{ row.remark || '' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>矩阵行=各税种×期间，列=6个认定维度</li>
        <li>6个认定：存在(E)/完整性(C)/准确性(A)/截止(CO)/分类(CL)/列报(P)</li>
        <li>✓ 已验证：通过测算表/检查表交叉验证满足</li>
        <li>⚠ 待验证：尚未完成对应测算/检查</li>
        <li>✗ 不满足：测算/检查发现问题</li>
        <li>验证来源：N2-6增值税/N2-8城建税/N2-9房产税/N2-10土增税/N2-11检查表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabRecognition — N2-5 应交税金认定表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.7
 * Requirements: 9.1-9.2
 *
 * 核心职责：
 * - 54×15 矩阵：行=税种×期间，列=6认定维度
 * - 各税种×期间矩阵认定
 * - 与各测算表（N2-6/N2-8/N2-9/N2-10）交叉验证指示器
 * - ✓已验证/⚠待验证/✗不满足 三级判定
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>(
  'openReviewDialog', undefined,
)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Constants ───────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)

/** 6 个认定维度 */
const ASSERTIONS = [
  { key: 'existence', label: '存在', tooltip: '存在(E)：应交税费在资产负债表日确实存在' },
  { key: 'completeness', label: '完整性', tooltip: '完整性(C)：所有应交税费已完整记录' },
  { key: 'accuracy', label: '准确性', tooltip: '准确性(A)：应交税费金额计算准确' },
  { key: 'cutoff', label: '截止', tooltip: '截止(CO)：交易记录在正确期间' },
  { key: 'classification', label: '分类', tooltip: '分类(CL)：各税种分类列报正确' },
  { key: 'presentation', label: '列报', tooltip: '列报(P)：在财务报表中恰当列报和披露' },
]

/** 税种列表 */
const TAX_TYPES = [
  '增值税',
  '城市维护建设税',
  '教育费附加',
  '地方教育附加',
  '企业所得税',
  '房产税',
  '土地使用税',
  '土地增值税',
  '印花税',
]

/** 期间列表 */
const PERIODS = ['年度', 'Q1', 'Q2', 'Q3', 'Q4', '期末']

/** 交叉验证来源映射 */
const CROSS_REF_MAP: Record<string, string> = {
  '增值税': 'N2-6 增值税测算',
  '城市维护建设税': 'N2-8 其他税费测算',
  '教育费附加': 'N2-8 其他税费测算',
  '地方教育附加': 'N2-8 其他税费测算',
  '房产税': 'N2-9 房产税测算',
  '土地增值税': 'N2-10 土增税测算',
  '企业所得税': 'N2-11 检查表',
  '土地使用税': 'N2-11 检查表',
  '印花税': 'N2-11 检查表',
}

// ─── Types ───────────────────────────────────────────────────────────────────

interface MatrixRow {
  id: string
  taxType: string
  period: string
  crossRef: string
  remark: string
  _isHeader?: boolean
}

// ─── Cell data store ─────────────────────────────────────────────────────────

/** Map<rowId::assertionKey, value> */
const cellValues = ref<Map<string, string>>(new Map())

function getCellValue(rowId: string, assertionKey: string): string {
  return cellValues.value.get(`${rowId}::${assertionKey}`) || ''
}

function getCellClass(rowId: string, assertionKey: string): string {
  const val = getCellValue(rowId, assertionKey)
  if (val === '✓') return 'cell-ok'
  if (val === '⚠') return 'cell-pending'
  if (val === '✗') return 'cell-fail'
  return ''
}

function handleCellChange(rowId: string, assertionKey: string, val: string) {
  const key = `${rowId}::${assertionKey}`
  cellValues.value.set(key, val)
  persistMatrix()
}

// ─── Remark ──────────────────────────────────────────────────────────────────

const remarkMap = ref<Map<string, string>>(new Map())

function handleRemarkChange(rowId: string, val: string) {
  remarkMap.value.set(rowId, val)
  persistMatrix()
}

// ─── Matrix rows ─────────────────────────────────────────────────────────────

const matrixRows = computed<MatrixRow[]>(() => {
  const rows: MatrixRow[] = []
  for (const tax of TAX_TYPES) {
    for (const period of PERIODS) {
      const id = `${tax}-${period}`
      rows.push({
        id,
        taxType: tax,
        period,
        crossRef: CROSS_REF_MAP[tax] || '',
        remark: remarkMap.value.get(id) || '',
      })
    }
  }
  return rows
})

// ─── Validation stats ────────────────────────────────────────────────────────

const validationStats = computed(() => {
  let verified = 0
  let pending = 0
  let failed = 0
  for (const val of cellValues.value.values()) {
    if (val === '✓') verified++
    else if (val === '⚠') pending++
    else if (val === '✗') failed++
  }
  return { verified, pending, failed }
})

// ─── Row class ───────────────────────────────────────────────────────────────

function getMatrixRowClassName({ row }: { row: MatrixRow }): string {
  if (row._isHeader) return 'header-row'
  // 如果该行有 ✗ 不满足，高亮
  for (const assertion of ASSERTIONS) {
    if (getCellValue(row.id, assertion.key) === '✗') {
      return 'fail-row'
    }
  }
  return ''
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function persistMatrix() {
  const data: Record<string, string> = {}
  for (const [k, v] of cellValues.value.entries()) {
    if (v) data[k] = v
  }
  const remarks: Record<string, string> = {}
  for (const [k, v] of remarkMap.value.entries()) {
    if (v) remarks[k] = v
  }
  formData.debouncedSave('N2-5-matrix', {
    conclusion: JSON.stringify({ cells: data, remarks }),
  })
}

// ─── AI / Review ─────────────────────────────────────────────────────────────

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-recognition',
      prompt: '请基于应交税费底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('N2-5-认定表')
}

// ─── Restore ─────────────────────────────────────────────────────────────────

function restoreData(): void {
  const resp = formData.allResponses.value.get('N2-5-matrix')
  if (resp?.conclusion) {
    try {
      const saved = JSON.parse(resp.conclusion)
      if (saved.cells) {
        for (const [k, v] of Object.entries(saved.cells)) {
          cellValues.value.set(k, v as string)
        }
      }
      if (saved.remarks) {
        for (const [k, v] of Object.entries(saved.remarks)) {
          remarkMap.value.set(k, v as string)
        }
      }
    } catch { /* ignore */ }
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-recognition {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 验证状态汇总 ─── */
.validation-summary {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.val-stat {
  display: flex;
  align-items: center;
  gap: 6px;
}

.val-stat-count {
  font-size: 18px;
  font-weight: 700;
}

.val-stat-label {
  font-size: 12px;
  color: #606266;
}

.val-stat--ok .val-stat-count { color: #67c23a; }
.val-stat--pending .val-stat-count { color: #e6a23c; }
.val-stat--fail .val-stat-count { color: #f56c6c; }

/* ─── Matrix wrapper ─── */
.matrix-wrapper {
  margin-bottom: 16px;
}

/* ─── 认定列头 ─── */
.assertion-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-size: 12px;
}

/* ─── Cell colors ─── */
.cell-ok { color: #67c23a; font-weight: 700; font-size: 14px; }
.cell-pending { color: #e6a23c; font-weight: 700; font-size: 14px; }
.cell-fail { color: #f56c6c; font-weight: 700; font-size: 14px; }

/* ─── Cross ref badge ─── */
.cross-ref-badge {
  display: inline-block;
  padding: 2px 8px;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: 4px;
  font-size: 11px;
  color: #409eff;
}

.no-ref { color: #c0c4cc; }

/* ─── Tax header cell ─── */
.tax-header-cell { font-weight: 700; color: #303133; }

/* ─── Row styles ─── */
:deep(.header-row) { background: #f5f7fa !important; font-weight: 600; }
:deep(.fail-row) { background: #fef0f0 !important; }
:deep(.fail-row:hover > td) { background: #fde2e2 !important; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table th .cell) { font-size: 12px; font-weight: 600; }

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
