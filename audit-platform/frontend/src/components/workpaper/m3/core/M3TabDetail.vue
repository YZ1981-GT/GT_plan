<template>
  <div class="m3-tab-detail">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M3-2 库存股明细表</h3>
        <el-tag type="warning" size="small">19列·区段Tab·动态行</el-tag>
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
        <el-button size="small" @click="handleAI('detail')">
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
        <strong>库存股明细表（按回购批次列示）：</strong>
        库存股是<strong>权益备抵类借方科目</strong>。期末库存股数 = 期初 + 回购股数 − 注销股数；
        期末金额 = 期初金额 + 回购金额 − 注销金额。
        19列宽表拆3区段Tab管理（回购信息 / 注销情况 / 期末余额），行同步。
      </div>
    </div>

    <!-- ═══ 跨sheet验证警告 ═══ -->
    <el-alert
      v-if="detail.totalEndAmount.value !== 0 && crossSheetDiff !== 0"
      type="error"
      :closable="false"
      show-icon
      class="cross-sheet-alert"
    >
      <template #title>
        明细合计与审定表M3-1不一致（差额：{{ fmtAmount(crossSheetDiff) }}）
      </template>
    </el-alert>

    <!-- ═══ 3 区段Tab (el-segmented) ═══ -->
    <el-segmented
      v-model="activeSegment"
      :options="segmentOptions"
      size="default"
      class="segment-switcher"
    />

    <!-- ═══ 回购信息 区段 ═══ -->
    <el-table
      v-if="activeSegment === 'repurchase'"
      :data="detail.computedRows.value"
      border
      size="small"
      style="width: 100%"
    >
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="回购批次" min-width="140">
        <template #default="{ row }">
          <span class="batch-name">{{ row.batchName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回购日期" min-width="120">
        <template #default="{ row, $index }">
          <el-date-picker
            v-if="!isReadonly"
            :model-value="row.repurchaseDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width:100%"
            placeholder="选择日期"
            @change="(val: string) => detail.updateRow($index, 'repurchaseDate', val || '')"
          />
          <span v-else>{{ row.repurchaseDate || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回购股数" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.repurchaseShares"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => detail.updateRow($index, 'repurchaseShares', val ?? 0)"
          />
          <span v-else>{{ fmtNumber(row.repurchaseShares) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回购单价" min-width="100" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.price"
            :controls="false"
            :min="0"
            :precision="4"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => detail.updateRow($index, 'price', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.price) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回购金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.repurchaseAmount"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => detail.updateRow($index, 'repurchaseAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.repurchaseAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="回购目的" min-width="120">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.purpose"
            size="small"
            placeholder="回购目的"
            @change="(val: string) => detail.updateRow($index, 'purpose', val)"
          />
          <span v-else>{{ row.purpose || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="股份来源" min-width="100">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.source"
            size="small"
            placeholder="来源"
            @change="(val: string) => detail.updateRow($index, 'source', val)"
          />
          <span v-else>{{ row.source || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="决议文号" min-width="130">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.resolutionNo"
            size="small"
            placeholder="决议文号"
            @change="(val: string) => detail.updateRow($index, 'resolutionNo', val)"
          />
          <span v-else>{{ row.resolutionNo || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="币种" width="80">
        <template #default="{ row, $index }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.currency"
            size="small"
            @change="(val: string) => detail.updateRow($index, 'currency', val)"
          >
            <el-option label="CNY" value="CNY" />
            <el-option label="USD" value="USD" />
            <el-option label="HKD" value="HKD" />
            <el-option label="EUR" value="EUR" />
          </el-select>
          <span v-else>{{ row.currency }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="detail.removeRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 注销情况 区段 ═══ -->
    <el-table
      v-if="activeSegment === 'cancel'"
      :data="detail.computedRows.value"
      border
      size="small"
      style="width: 100%"
    >
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="回购批次" min-width="140">
        <template #default="{ row }">
          <span class="batch-name">{{ row.batchName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="注销股数" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.cancelShares"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => detail.updateRow($index, 'cancelShares', val ?? 0)"
          />
          <span v-else>{{ fmtNumber(row.cancelShares) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="注销金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.cancelAmount"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => detail.updateRow($index, 'cancelAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.cancelAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="detail.removeRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 期末余额 区段 ═══ -->
    <el-table
      v-if="activeSegment === 'endBalance'"
      :data="detail.computedRows.value"
      border
      size="small"
      style="width: 100%"
    >
      <el-table-column type="index" label="#" width="50" align="center" />
      <el-table-column label="回购批次" min-width="140">
        <template #default="{ row }">
          <span class="batch-name">{{ row.batchName || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初股数" min-width="110" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.beginShares"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => detail.updateRow($index, 'beginShares', val ?? 0)"
          />
          <span v-else>{{ fmtNumber(row.beginShares) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初金额" min-width="120" align="right">
        <template #default="{ row, $index }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.beginAmount"
            :controls="false"
            :min="0"
            size="small"
            style="width:100%"
            @change="(val: number | undefined) => detail.updateRow($index, 'beginAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.beginAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末库存股数" min-width="130" align="right">
        <template #header>
          <el-tooltip content="公式: 期初股数 + 回购股数 − 注销股数（备抵借方增加）" placement="top">
            <span class="formula-col-header">期末股数</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtNumber(row.endShares) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末金额" min-width="130" align="right">
        <template #header>
          <el-tooltip content="公式: 期初金额 + 回购金额 − 注销金额（备抵借方增加）" placement="top">
            <span class="formula-col-header">期末金额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmount(row.endAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="140">
        <template #default="{ row, $index }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => detail.updateRow($index, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计区 ═══ -->
    <div class="total-bar">
      <span>期末金额合计：<strong class="formula-value">{{ fmtAmount(detail.totalEndAmount.value) }}</strong></span>
      <span>期末股数合计：<strong class="formula-value">{{ fmtNumber(detail.totalEndShares.value) }}</strong></span>
      <span>回购金额合计：<strong>{{ fmtAmount(detail.totalRepurchaseAmount.value) }}</strong></span>
      <span>注销金额合计：<strong>{{ fmtAmount(detail.totalCancelAmount.value) }}</strong></span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>权益备抵借方铁律</strong>：期末 = 期初 + 回购(借方增加) − 注销(贷方减少)</li>
        <li>19列宽表拆3区段Tab：回购信息(9列) / 注销情况(2列) / 期末余额(5列)</li>
        <li>新增行需先输入回购批次名称（弹窗确认）</li>
        <li>明细合计应与M3-1审定表库存股期末余额一致</li>
        <li>外币回购请同步填写M3-4外币投资汇率测算表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M3TabDetail — M3-2 库存股明细表（19列区段Tab+动态行）
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 4.3
 * Requirements: 3.1-3.5
 *
 * 功能：
 * - 19列宽表拆3区段Tab (el-segmented): 回购信息 / 注销情况 / 期末余额（行同步）
 * - 动态行新增（先弹ElMessageBox.prompt输入批次名）
 * - 导入导出 (useM3ImportExport)
 * - 期末公式自动计算（权益备抵借方：期末=期初+回购-注销）
 * - 与M3-1审定表交叉验证
 *
 * 科目：4002 库存股（**借方/权益备抵类！**）
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useM3FormData } from '../../composables/useM3FormData'
import { useM3Detail, type M3DetailRow, type M3DetailSegment } from '../../composables/useM3Detail'
import { useM3ImportExport, type M3ImportableSheet } from '../../composables/useM3ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useM3FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<M3DetailRow[]>([])

const detail = useM3Detail(formData, detailRows)

const { exportTemplate, exportData, importData } = useM3ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 区段Tab state ───────────────────────────────────────────────────────────

const activeSegment = computed({
  get: () => detail.activeSegment.value,
  set: (val: string) => detail.switchSegment(val as M3DetailSegment),
})

const segmentOptions = [
  { label: '回购信息', value: 'repurchase' },
  { label: '注销情况', value: 'cancel' },
  { label: '期末余额', value: 'endBalance' },
]

// ─── 跨sheet验证 ─────────────────────────────────────────────────────────────

const adjudicationEndAudited = ref(0)

const crossSheetDiff = computed(() => {
  if (adjudicationEndAudited.value === 0) return 0
  return detail.totalEndAmount.value - adjudicationEndAudited.value
})

watch(() => formData.allResponses.value, (responses) => {
  const auditedResp = responses.get('M3-M3-1-total-audited')
  if (auditedResp?.remark) {
    const val = parseFloat(auditedResp.remark)
    if (!isNaN(val)) adjudicationEndAudited.value = val
  }
}, { immediate: true })

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddRow() {
  await detail.addRow()
}

function handleImportExport(command: string) {
  const sheet: M3ImportableSheet = 'M3-2'
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

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('M3-2-detail', '库存股明细表') }

// ─── Format helpers ──────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtNumber(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN')
}

// ─── Restore from responses ──────────────────────────────────────────────────

function _restoreRows() {
  const fullData = formData.allResponses.value.get('M3-M3-2-full-data')
  if (fullData?.remark) {
    try {
      const parsed = JSON.parse(fullData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed
      }
    } catch { /* keep empty */ }
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
})
</script>

<style scoped>
.m3-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }
.batch-name { font-weight: 500; color: #303133; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.total-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; border-radius: 6px; background: #f0f9eb; font-size: var(--wp-font-size, 13px); align-items: center; flex-wrap: wrap; }
.m3-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
