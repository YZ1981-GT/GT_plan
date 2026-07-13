<template>
  <div class="m1-tab-dividend-calc">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M1-5 应付股利（利润）测算表</h3>
        <el-tag type="warning" size="small">13公式·接收M6联动</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增股东
        </el-button>
        <el-dropdown :disabled="isReadonly" @command="handleImportExport" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('general')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ M6联动状态提示 ═══ -->
    <el-alert
      v-if="!m6DataReady"
      type="warning"
      :closable="false"
      show-icon
      class="m6-pending-alert"
    >
      <template #title>
        待M6利润分配完成 — 可供分配利润数据尚未接收（订阅 'm6:profit-distributed'）
      </template>
    </el-alert>

    <el-alert
      v-if="m6DataReady"
      type="success"
      :closable="false"
      show-icon
      class="m6-ready-alert"
    >
      <template #title>
        已接收M6利润分配数据：可供分配利润 {{ fmtAmount(m6ProfitDistributed) }} 元
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>股利测算逻辑：</strong>
        应宣告股利 = 可供分配利润 × 分配比例；宣告差异 = 测算宣告 − 账面宣告。
        |宣告差异| > {{ declareThreshold.toLocaleString() }} 元时红色高亮，需填写差异说明。
        可供分配利润来源于M6未分配利润底稿（通过EventBus自动接收）。
      </div>
    </div>

    <!-- ═══ 主表 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />

      <!-- 股东名称 -->
      <el-table-column prop="shareholderName" label="股东" min-width="150" fixed>
        <template #default="{ row }">
          <span>{{ row.shareholderName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 可供分配利润（来自M6或手动） -->
      <el-table-column label="可供分配利润" width="160" align="right">
        <template #header>
          <el-tooltip content="来源: M6利润分配方案（EventBus订阅'm6:profit-distributed'）" placement="top">
            <span class="formula-col-header">可供分配利润</span>
          </el-tooltip>
        </template>
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.profit"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate($index, 'profit', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.profit) }}</span>
        </template>
      </el-table-column>

      <!-- 分配比例（用户输入） -->
      <el-table-column label="分配比例" width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.ratio"
            :controls="false"
            :precision="4"
            :min="0"
            :max="1"
            :step="0.01"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate($index, 'ratio', val ?? 0)"
          />
          <span v-else>{{ row.ratio ? (row.ratio * 100).toFixed(2) + '%' : '—' }}</span>
        </template>
      </el-table-column>

      <!-- 应宣告股利（公式计算） -->
      <el-table-column label="应宣告股利" width="150" align="right">
        <template #header>
          <el-tooltip content="公式: 可供分配利润 × 分配比例" placement="top">
            <span class="formula-col-header">应宣告股利</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.declaredDividend) }}</span>
        </template>
      </el-table-column>

      <!-- 账面宣告（用户输入） -->
      <el-table-column label="账面宣告" width="150" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.booked"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => handleUpdate($index, 'booked', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.booked) }}</span>
        </template>
      </el-table-column>

      <!-- 差异（公式计算） -->
      <el-table-column label="差异" width="150" align="right">
        <template #header>
          <el-tooltip content="公式: 应宣告股利 − 账面宣告" placement="top">
            <span class="formula-col-header">差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            class="formula-value"
            :class="{ 'declare-diff-alert': Math.abs(row.declareDiff) > declareThreshold }"
          >
            {{ fmtAmount(row.declareDiff) }}
          </span>
          <el-icon v-if="Math.abs(row.declareDiff) > declareThreshold" class="declare-warning-icon"><Warning /></el-icon>
        </template>
      </el-table-column>

      <!-- 差异说明（当差异超阈值时需填写） -->
      <el-table-column label="差异说明" min-width="180">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly && Math.abs(row.declareDiff) > declareThreshold"
            :model-value="row.diffNote"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            size="small"
            placeholder="差异超阈值，请填写说明"
            @change="(val: string) => handleUpdate($index, 'diffNote', val)"
          />
          <span v-else-if="row.diffNote">{{ row.diffNote }}</span>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除该股东？" @confirm="handleRemoveRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 汇总行 ═══ -->
    <div class="summary-bar">
      <span>应宣告合计：<strong class="formula-value--primary">{{ fmtAmount(totalDeclared) }}</strong></span>
      <span>账面宣告合计：<strong>{{ fmtAmount(totalBooked) }}</strong></span>
      <span>差异合计：<strong :class="{ 'declare-diff-alert': Math.abs(totalDeclareDiff) > declareThreshold }">{{ fmtAmount(totalDeclareDiff) }}</strong></span>
      <span>共 <strong>{{ rows.length }}</strong> 个股东</span>
    </div>

    <!-- ═══ 跨底稿联动 ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref M6联动：</span>
      <GtIndexChip value="M6" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">未分配利润（可供分配利润来源）</span>
      <GtIndexChip value="M1-2" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">明细表（股东持股比例来源）</span>
      <GtIndexChip value="M1-6" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">检查表（宣告核对结果）</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>可供分配利润通过EventBus订阅M6('m6:profit-distributed')自动填入</li>
        <li>分配比例为小数（如0.30代表30%），来自股东会决议</li>
        <li>应宣告股利 = 可供分配利润 × 分配比例（13公式前端实时计算）</li>
        <li>差异 = 应宣告股利 − 账面宣告（正值=少分配，负值=多分配）</li>
        <li>差异超阈值（{{ declareThreshold.toLocaleString() }}元）红色高亮，需填写差异说明</li>
        <li>核对结果联动M1-6检查表，审计结论依据此表差异分析</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabDividendCalc — M1-5 应付股利(利润)测算表
 *
 * Requirements: 5.1-5.6
 * - 29×14 table: 可供分配利润 | 分配比例 | 应宣告股利(calc) | 账面宣告 | 差异(calc)
 * - 13 formulas computed real-time
 * - Subscribe to EventBus 'm6:profit-distributed' for M6 data
 * - Red highlight when |宣告差异| > threshold
 * - Uses calcDeclaredDividend, calcDeclareDiff from useM1DividendEngine
 * - GtIndexChip linking to M6
 */
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { Plus, MagicStick, Check, Warning } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useM1FormData } from '../../composables/useM1FormData'
import { useM1ImportExport } from '../../composables/useM1ImportExport'
import { calcDeclaredDividend, calcDeclareDiff } from '../../composables/useM1DividendEngine'
import { eventBus } from '@/utils/eventBus'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface DividendRow {
  key: string
  shareholderName: string
  profit: number
  ratio: number
  booked: number
  diffNote: string
}

interface ComputedDividendRow extends DividendRow {
  declaredDividend: number
  declareDiff: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DECLARE_THRESHOLD_DEFAULT = 10000 // |宣告差异| > 10000 元红色高亮

// ─── State ───────────────────────────────────────────────────────────────────

const declareThreshold = ref(DECLARE_THRESHOLD_DEFAULT)
const rows = ref<DividendRow[]>([])
const m6DataReady = ref(false)
const m6ProfitDistributed = ref(0)

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const { exportTemplate, exportData, importData } = useM1ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Computed（13 formulas real-time） ────────────────────────────────────────

const computedRows = computed<ComputedDividendRow[]>(() => {
  return rows.value.map(row => {
    const declaredDividend = calcDeclaredDividend(row.profit, row.ratio)
    const declareDiff = calcDeclareDiff(declaredDividend, row.booked)
    return { ...row, declaredDividend, declareDiff }
  })
})

const totalDeclared = computed(() => computedRows.value.reduce((sum, r) => sum + r.declaredDividend, 0))
const totalBooked = computed(() => computedRows.value.reduce((sum, r) => sum + r.booked, 0))
const totalDeclareDiff = computed(() => computedRows.value.reduce((sum, r) => sum + r.declareDiff, 0))

// ─── EventBus: Subscribe 'm6:profit-distributed' ─────────────────────────────

function handleM6ProfitDistributed(payload: any): void {
  const amount = payload?.profitDistributed ?? payload?.amount ?? 0
  if (amount > 0) {
    m6DataReady.value = true
    m6ProfitDistributed.value = amount
    // 自动填入所有行的 profit 字段（股东各自按比例分，基数统一）
    for (const row of rows.value) {
      row.profit = amount
    }
    _persistRows()
    ElMessage.success(`已接收M6利润分配数据：${amount.toLocaleString()} 元`)
  }
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function _persistRows(): void {
  formData.debouncedSave('M1-M1-5-dividend-rows', {
    remark: JSON.stringify(rows.value),
  })
}

function _restoreRows(): void {
  const saved = formData.allResponses.value.get('M1-M1-5-dividend-rows')
  if (saved?.remark) {
    try {
      const parsed = JSON.parse(saved.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed
        // 检查是否已有 M6 数据
        if (parsed.some((r: DividendRow) => r.profit > 0)) {
          m6DataReady.value = true
          m6ProfitDistributed.value = parsed[0]?.profit ?? 0
        }
        return
      }
    } catch { /* use empty */ }
  }
  rows.value = []
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入股东名称',
      '新增股东',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '如：王XX / 北京XX有限公司' },
    )
    if (!name?.trim()) return
    rows.value.push({
      key: `div-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      shareholderName: name.trim(),
      profit: m6ProfitDistributed.value || 0,
      ratio: 0,
      booked: 0,
      diffNote: '',
    })
    _persistRows()
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(index: number): void {
  rows.value.splice(index, 1)
  _persistRows()
}

function handleUpdate(index: number, field: keyof DividendRow, value: any): void {
  if (index < 0 || index >= rows.value.length) return
  ;(rows.value[index] as any)[field] = value
  _persistRows()
}

function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('M1-5')
      break
    case 'exportData':
      exportData('M1-5')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'M1-5')
          if (result) {
            await formData.loadData()
            _restoreRows()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

function handleAI(section: string = 'general'): void {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `m1-dividend-calc-${section}`,
      prompt: `请基于应付股利底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview(): void { openReviewDialog?.('M1-5-dividend-calc', '股利测算表') }

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
  // Subscribe to M6 profit distributed event
  eventBus.on('m6:profit-distributed', handleM6ProfitDistributed)
})

onUnmounted(() => {
  eventBus.off('m6:profit-distributed', handleM6ProfitDistributed)
})

// Watch rows change for auto-persist
watch(rows, _persistRows, { deep: true })
</script>

<style scoped>
.m1-tab-dividend-calc { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.m6-pending-alert { margin-bottom: 12px; }
.m6-ready-alert { margin-bottom: 12px; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
.declare-diff-alert { color: #f56c6c !important; font-weight: 700; }
.declare-warning-icon { color: #f56c6c; margin-left: 4px; vertical-align: middle; }
.text-muted { color: #c0c4cc; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; flex-wrap: wrap; }
.cross-wp-links { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #d9ecff; border-radius: 6px; flex-wrap: wrap; }
.cross-wp-label { font-size: 12px; color: #409eff; font-weight: 500; }
.cross-wp-desc { font-size: 12px; color: #909399; }
.m1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
