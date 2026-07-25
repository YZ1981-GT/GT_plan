<template>
  <div class="m3-tab-fx-invest">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M3-4 外币投资汇率测算表</h3>
        <el-tag type="info" size="small">外币回购折算</el-tag>
      </div>
      <div class="section-header-right">
        <el-dropdown :disabled="isReadonly" trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :disabled="isReadonly" type="primary" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增批次
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handlePullFromDetail">
          从M3-2带入
        </el-button>
        <el-button size="small" :loading="aiLoading === 'fx-invest'" :disabled="isReadonly" @click="handleAI('fx-invest')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>外币回购折算（M3-4）：</strong>
        境外回购以外币计价，按回购日即期汇率折算为本位币（人民币）。
        折算本位币 = 原币回购额 × 回购日汇率；折算差异 = 折算本位币 − 账面本位币。
        当 |折算差异| > {{ FX_DIFF_THRESHOLD }} 时红色高亮，提示审计人员关注汇率选用问题。
      </div>
    </div>

    <!-- ═══ 外币折算表格 ═══ -->
    <el-table :data="computedFxRows" border size="small" style="width: 100%">
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="回购批次" min-width="140">
        <template #default="{ row }">
          <span class="batch-name">{{ row.batchName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回购日期" width="130">
        <template #default="{ row, $index }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.repurchaseDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="回购日"
            style="width:100%"
            @change="(val: string) => updateFxRow($index, 'repurchaseDate', val || '')"
          />
          <span v-else>{{ row.repurchaseDate || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="原币回购额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.foreignAmount"
            :controls="false"
            :min="0"
            :precision="2"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => updateFxRow($index, 'foreignAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.foreignAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="币种" width="90">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.currency"
            size="small"
            @change="(val: string) => updateFxRow($index, 'currency', val)"
          >
            <el-option label="USD" value="USD" />
            <el-option label="HKD" value="HKD" />
            <el-option label="EUR" value="EUR" />
            <el-option label="GBP" value="GBP" />
            <el-option label="JPY" value="JPY" />
          </el-select>
          <span v-else>{{ row.currency }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回购日汇率" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.exchangeRate"
            :controls="false"
            :min="0"
            :precision="6"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => updateFxRow($index, 'exchangeRate', val ?? 0)"
          />
          <span v-else>{{ row.exchangeRate ? row.exchangeRate.toFixed(6) : '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="折算本位币" min-width="130" align="right">
        <template #header>
          <el-tooltip content="公式: 原币回购额 × 回购日汇率" placement="top">
            <span class="formula-col-header">折算本位币</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.convertedAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面本位币" min-width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.bookedAmount"
            :controls="false"
            :min="0"
            :precision="2"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => updateFxRow($index, 'bookedAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.bookedAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="折算差异" min-width="130" align="right">
        <template #header>
          <el-tooltip content="公式: 折算本位币 − 账面本位币" placement="top">
            <span class="formula-col-header">折算差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', isOverThreshold(row.diff, row.diffRate) ? 'diff-warning' : '']">
            {{ fmtAmount(row.diff) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="差异率" width="90" align="right">
        <template #header>
          <el-tooltip content="|折算差异| ÷ 账面本位币 × 100%" placement="top">
            <span class="formula-col-header">差异率</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span :class="['formula-value', row.diffRate > FX_DIFF_RATE_THRESHOLD ? 'diff-warning' : '']">
            {{ row.bookedAmount ? (row.diffRate * 100).toFixed(2) + '%' : '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => updateFxRow($index, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="removeFxRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计 + 阈值提示 ═══ -->
    <div class="total-bar">
      <span>折算本位币合计：<strong class="formula-value">{{ fmtAmount(totalConverted) }}</strong></span>
      <span>差异合计：<strong :class="isOverThreshold(totalDiff) ? 'diff-warning' : ''">{{ fmtAmount(totalDiff) }}</strong></span>
      <span class="threshold-hint">高亮阈值：|差异| > {{ FX_DIFF_THRESHOLD }}元 或 差异率 > 1%</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>折算本位币 = 原币回购额 × 回购日即期汇率（1外币=X人民币）</li>
        <li>折算差异 = 折算本位币 − 账面本位币（被审计单位已入账金额）</li>
        <li>差异率 = |折算差异| ÷ 账面本位币 × 100%</li>
        <li>差异超阈值（|差异| > {{ FX_DIFF_THRESHOLD }}元 或 差异率 > 1%）红色高亮提醒</li>
        <li>可从M3-2明细表一键带入外币回购批次（筛选币种≠CNY）</li>
        <li>所有公式前端实时计算，无需后端参与</li>
        <li>汇率来源：中国人民银行官网/中国外汇交易中心公布的即期汇率</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M3TabFxInvest — M3-4 外币投资汇率测算表（外币回购折算）
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 4.4
 * Requirements: 4.1-4.5
 *
 * 功能：
 * - 列: 回购批次|原币回购额|币种|回购日汇率|折算本位币|账面本位币|折算差异
 * - Uses calcFxConverted / calcFxDiff from useM3FxEngine
 * - Red highlight when |差异| > threshold
 * - All formulas real-time frontend
 * - 导入导出 (useM3ImportExport)
 *
 * 科目：4002 库存股（**借方/权益备抵类！**）
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { calcFxConverted, calcFxDiff } from '../../composables/useM3FxEngine'
import { useM3FormData } from '../../composables/useM3FormData'
import { useM3ImportExport, type M3ImportableSheet } from '../../composables/useM3ImportExport'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── Constants ───────────────────────────────────────────────────────────────

const FX_DIFF_THRESHOLD = 100 // 折算差异高亮阈值（元）
/** 差异率高亮阈值（1%以上红色） */
const FX_DIFF_RATE_THRESHOLD = 0.01

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useM3FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const { exportTemplate, exportData, importData } = useM3ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Types + State ───────────────────────────────────────────────────────────

interface FxRow {
  key: string
  batchName: string
  /** 回购日期 */
  repurchaseDate: string
  foreignAmount: number
  currency: string
  exchangeRate: number
  bookedAmount: number
  remark: string
}

interface ComputedFxRow extends FxRow {
  convertedAmount: number
  diff: number
  /** 差异率=|差异|/账面（账面为0时为0） */
  diffRate: number
}

const fxRows = ref<FxRow[]>([])

// ─── Computed: 实时公式计算 ──────────────────────────────────────────────────

const computedFxRows = computed<ComputedFxRow[]>(() => {
  return fxRows.value.map(row => {
    const convertedAmount = calcFxConverted(row.foreignAmount, row.exchangeRate)
    const diff = calcFxDiff(convertedAmount, row.bookedAmount)
    const diffRate = row.bookedAmount !== 0 ? Math.abs(diff) / Math.abs(row.bookedAmount) : 0
    return { ...row, convertedAmount, diff, diffRate }
  })
})

const totalConverted = computed(() => {
  return computedFxRows.value.reduce((sum, r) => sum + r.convertedAmount, 0)
})

const totalDiff = computed(() => {
  return computedFxRows.value.reduce((sum, r) => sum + r.diff, 0)
})

// ─── Row operations ──────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value: batchName } = await ElMessageBox.prompt(
      '请输入外币回购批次名称',
      '新增外币折算行',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：2024年第一次境外回购',
        inputValidator: (val) => {
          if (!val || !val.trim()) return '批次名称不能为空'
          return true
        },
      },
    )

    const key = `m3-fx-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    fxRows.value.push({
      key,
      batchName: batchName?.trim() || '',
      repurchaseDate: '',
      foreignAmount: 0,
      currency: 'USD',
      exchangeRate: 0,
      bookedAmount: 0,
      remark: '',
    })
    _saveFxRows()
  } catch { /* 用户取消 */ }
}

function removeFxRow(index: number) {
  if (index < 0 || index >= fxRows.value.length) return
  fxRows.value.splice(index, 1)
  _saveFxRows()
}

function updateFxRow(index: number, field: keyof FxRow, value: string | number) {
  if (index < 0 || index >= fxRows.value.length) return
  const row = fxRows.value[index] as any
  row[field] = value
  _saveFxRows()
}

function isOverThreshold(diff: number, diffRate?: number): boolean {
  // 绝对值>阈值 OR 差异率>1%
  return Math.abs(diff) > FX_DIFF_THRESHOLD || (diffRate !== undefined && diffRate > FX_DIFF_RATE_THRESHOLD)
}

/**
 * 从M3-2明细表带入外币回购批次。
 * 读取allResponses中M3-2行数据,筛选currency!='CNY'的行,填入M3-4。
 */
async function handlePullFromDetail() {
  await formData.loadData()
  const newRows: FxRow[] = []
  for (const [key, resp] of formData.allResponses.value) {
    if (key.startsWith('M3-M3-2-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const row = JSON.parse(resp.remark)
        // 仅带入非人民币（外币）回购批次
        if (row.currency && row.currency !== 'CNY') {
          newRows.push({
            key: `m3-fx-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            batchName: row.batchName || '',
            repurchaseDate: row.repurchaseDate || '',
            foreignAmount: Number(row.repurchaseAmount) || 0,
            currency: row.currency || 'USD',
            exchangeRate: 0,
            bookedAmount: 0,
            remark: '',
          })
        }
      } catch { /* skip */ }
    }
  }
  if (newRows.length === 0) {
    ElMessage.info('M3-2明细表中无外币（非CNY）回购批次')
    return
  }
  // 有既有行时确认
  if (fxRows.value.length > 0) {
    try {
      await ElMessageBox.confirm(
        `将从M3-2带入${newRows.length}个外币批次（替换现有${fxRows.value.length}行），是否继续？`,
        '从明细表带入',
        { confirmButtonText: '确认替换', cancelButtonText: '取消', type: 'warning' },
      )
    } catch { return }
  }
  fxRows.value = newRows
  _saveFxRows()
  ElMessage.success(`已从M3-2带入${newRows.length}个外币回购批次`)
}

// ─── Import/Export ───────────────────────────────────────────────────────────

function handleImportExport(command: string) {
  const sheet: M3ImportableSheet = 'M3-4'
  switch (command) {
    case 'exportTemplate':
      exportTemplate(sheet)
      break
    case 'exportData':
      exportData(sheet)
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, sheet)
          if (result?.success) {
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

// ─── AI / Review ─────────────────────────────────────────────────────────────

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4002 库存股（权益备抵类·借方，外币投资汇率测算 M3-4）',
      折算本位币合计: fmtAmount(totalConverted.value),
      折算差异合计: fmtAmount(totalDiff.value),
      外币批次数: String(computedFxRows.value.length),
      高亮阈值: `|差异| > ${FX_DIFF_THRESHOLD}元 或 差异率 > 1%`,
    }
    const text = await generateAiText({ section: `m3-fx-invest-${section}`, context, existingContent: '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = ''
  }
}
function handleReview() { openReviewDialog?.('M3-4-fx-invest', '外币投资汇率测算') }

// ─── Save / Restore ──────────────────────────────────────────────────────────

function _saveFxRows() {
  formData.debouncedSave('M3-M3-4-fx-rows', {
    remark: JSON.stringify(fxRows.value),
  })
}

function _restoreRows() {
  const data = formData.allResponses.value.get('M3-M3-4-fx-rows')
  if (data?.remark) {
    try {
      const parsed = JSON.parse(data.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        fxRows.value = parsed
      }
    } catch { /* keep empty */ }
  }
}

// ─── Format helpers ──────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
})
</script>

<style scoped>
.m3-tab-fx-invest { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.batch-name { font-weight: 500; color: #303133; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.diff-warning { color: #f56c6c !important; font-weight: 600; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.total-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; border-radius: 6px; background: #f0f9eb; font-size: var(--wp-font-size, 13px); align-items: center; flex-wrap: wrap; }
.threshold-hint { font-size: 12px; color: #909399; }
.m3-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
