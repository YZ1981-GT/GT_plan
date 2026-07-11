<template>
  <div class="m1-tab-detail">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M1-2 应付股利明细表（按股东列示）</h3>
        <el-tag type="warning" size="small">27列·3区段Tab</el-tag>
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
        <el-button size="small" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>27列按3区段Tab管理（行同步）：</strong>
        股东信息区（名称+持股比例+币种+类型）→ 宣告金额区（期初/宣告/决议/分配比例/应宣告/差异）→ 支付情况区（支付/方式/代扣/净额/期末余额/审定/变动）。
        <em>负债类公式：期末应付 = 期初 + 本期宣告 − 本期支付</em>
      </div>
    </div>

    <!-- ═══ 跨sheet交叉验证警告 ═══ -->
    <el-alert
      v-if="showCrossSheetWarning"
      type="error"
      :closable="false"
      show-icon
      class="cross-sheet-alert"
    >
      <template #title>
        明细合计与审定表M1-1不一致（差额需核查）
      </template>
    </el-alert>

    <!-- ═══ 区段Tab切换器 ═══ -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" class="segment-switcher" />

    <!-- ═══ 明细表主体 ═══ -->
    <el-table :data="computedRows" border size="small" style="width: 100%" highlight-current-row>
      <el-table-column type="index" label="#" width="50" align="center" fixed />
      <el-table-column prop="shareholderName" label="股东名称" min-width="160" fixed>
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" :model-value="row.shareholderName" size="small" @change="(val: string) => handleUpdate($index, 'shareholderName', val)" />
          <span v-else>{{ row.shareholderName || '—' }}</span>
        </template>
      </el-table-column>

      <!-- ═══ 区段1: 股东信息 ═══ -->
      <template v-if="activeSegment === 'shareholder'">
        <el-table-column label="持股比例(%)" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.shareholdingRatio" :controls="false" :precision="2" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'shareholdingRatio', val ?? 0)" />
            <span v-else>{{ row.shareholdingRatio ? row.shareholdingRatio.toFixed(2) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="币种" width="90" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.currency" size="small" style="width:100%" @change="(val: string) => handleUpdate($index, 'currency', val)">
              <el-option value="CNY" label="CNY" />
              <el-option value="USD" label="USD" />
              <el-option value="EUR" label="EUR" />
              <el-option value="HKD" label="HKD" />
              <el-option value="JPY" label="JPY" />
            </el-select>
            <span v-else>{{ row.currency || 'CNY' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="股东类型" width="110" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.shareholderType" size="small" style="width:100%" placeholder="选择" @change="(val: string) => handleUpdate($index, 'shareholderType', val)">
              <el-option v-for="opt in SHAREHOLDER_TYPE_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
            </el-select>
            <span v-else>{{ shareholderTypeLabel(row.shareholderType) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(val: string) => handleUpdate($index, 'remark', val)" />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2: 宣告金额（贷方增加） ═══ -->
      <template v-if="activeSegment === 'declared'">
        <el-table-column label="期初应付" width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'beginBalance', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期宣告" width="130" align="right">
          <template #header>
            <el-tooltip content="贷方增加：宣告分配股利时贷记应付股利" placement="top">
              <span class="formula-col-header">本期宣告</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.declaredAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'declaredAmount', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.declaredAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="宣告日期" width="130" align="center">
          <template #default="{ row, $index }">
            <el-date-picker v-if="!isReadonly" :model-value="row.declaredDate" type="date" size="small" style="width:100%" value-format="YYYY-MM-DD" @update:model-value="(val: string) => handleUpdate($index, 'declaredDate', val || '')" />
            <span v-else>{{ row.declaredDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="决议文号" width="140">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.resolutionRef" size="small" placeholder="如：董〔2025〕01号" @change="(val: string) => handleUpdate($index, 'resolutionRef', val)" />
            <span v-else>{{ row.resolutionRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分配比例(%)" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.distributionRatio" :controls="false" :precision="2" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'distributionRatio', val ?? 0)" />
            <span v-else>{{ row.distributionRatio ? row.distributionRatio.toFixed(2) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分配基数" width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.distributionBase" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'distributionBase', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.distributionBase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应宣告" width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 分配基数 × 分配比例" placement="top">
              <span class="formula-col-header">应宣告</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.expectedDeclared) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="宣告差异" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 本期宣告 − 应宣告" placement="top">
              <span class="formula-col-header">宣告差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'abnormal-value': Math.abs(row.declareDiff) > 0.01 }]">{{ fmtAmount(row.declareDiff) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段3: 支付情况（借方减少） ═══ -->
      <template v-if="activeSegment === 'payment'">
        <el-table-column label="本期支付" width="130" align="right">
          <template #header>
            <el-tooltip content="借方减少：实际支付时借记应付股利" placement="top">
              <span class="formula-col-header">本期支付</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.paidAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'paidAmount', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.paidAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支付日期" width="130" align="center">
          <template #default="{ row, $index }">
            <el-date-picker v-if="!isReadonly" :model-value="row.paidDate" type="date" size="small" style="width:100%" value-format="YYYY-MM-DD" @update:model-value="(val: string) => handleUpdate($index, 'paidDate', val || '')" />
            <span v-else>{{ row.paidDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支付方式" width="110" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" :model-value="row.paymentMethod" size="small" style="width:100%" placeholder="选择" @change="(val: string) => handleUpdate($index, 'paymentMethod', val)">
              <el-option v-for="opt in PAYMENT_METHOD_OPTIONS" :key="opt.value" :value="opt.value" :label="opt.label" />
            </el-select>
            <span v-else>{{ paymentMethodLabel(row.paymentMethod) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="代扣税金" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.withholdingTax" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => handleUpdate($index, 'withholdingTax', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.withholdingTax) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实付净额" width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 本期支付 − 代扣税金" placement="top">
              <span class="formula-col-header">实付净额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.netPaidAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应付" width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 期初 + 本期宣告 − 本期支付（负债类）" placement="top">
              <span class="formula-col-header">期末应付</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value--primary">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="130" align="right">
          <template #header>
            <el-tooltip content="审定期末余额（=期末应付，供M1-1交叉验证）" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期变动" width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 本期宣告 − 本期支付" placement="top">
              <span class="formula-col-header">本期变动</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.periodChange) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-popconfirm title="确认删除该股东明细？" @confirm="handleRemoveRow($index)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计汇总栏 ═══ -->
    <div class="summary-bar">
      <span>期初合计：<strong>{{ fmtAmount(totalBeginBalance) }}</strong></span>
      <span>本期宣告合计：<strong>{{ fmtAmount(totalDeclared) }}</strong></span>
      <span>本期支付合计：<strong>{{ fmtAmount(totalPaid) }}</strong></span>
      <span>期末合计：<strong class="formula-value--primary">{{ fmtAmount(totalEndBalance) }}</strong></span>
      <span>共 <strong>{{ computedRows.length }}</strong> 个股东</span>
    </div>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip） ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 关联底稿：</span>
      <GtIndexChip value="M1-1" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">审定表（合计验证）</span>
      <GtIndexChip value="M1-4" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">外币汇率测算</span>
      <GtIndexChip value="M6" :context-project-id="props.projectId" />
      <span class="cross-wp-desc">利润分配（分配股利来源）</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>27列按3区段Tab拆分管理，行跨区段同步（切换不丢数据）</li>
        <li><strong>负债类公式</strong>：期末应付 = 期初 + 本期宣告（贷方增加）− 本期支付（借方减少）</li>
        <li>应宣告 = 分配基数 × 分配比例；宣告差异 = 本期宣告 − 应宣告</li>
        <li>实付净额 = 本期支付 − 代扣税金</li>
        <li>期末合计应与M1-1审定表应付股利期末余额一致</li>
        <li>境外股东外币应付股利请同步填写M1-4外币汇率测算表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabDetail — M1-2 应付股利明细表（27列·3区段Tab·按股东列示）
 *
 * Requirements: 3.1-3.5
 * - 27列宽表拆3段：股东信息/宣告金额/支付情况（行同步）
 * - 动态行新增（ElMessageBox.prompt输入股东名称）
 * - 导入导出三级 using useM1ImportExport
 * - 公式：期末应付=期初+本期宣告-本期支付（负债类贷方）
 * - 与M1-1审定表交叉验证（合计行）
 *
 * 科目：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, inject, onMounted, ref } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useM1FormData } from '../../composables/useM1FormData'
import {
  useM1Detail,
  M1_DETAIL_SEGMENTS,
  SHAREHOLDER_TYPE_OPTIONS,
  PAYMENT_METHOD_OPTIONS,
  type M1DetailRow,
  type M1DetailSegment,
} from '../../composables/useM1Detail'
import { useM1ImportExport } from '../../composables/useM1ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<M1DetailRow[]>([])

const {
  activeSegment,
  computedRows,
  totalBeginBalance,
  totalDeclared,
  totalPaid,
  totalEndBalance,
  addRow,
  removeRow,
  updateRow,
} = useM1Detail(formData, detailRows)

const { exportTemplate, exportData, importData } = useM1ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Segment options ─────────────────────────────────────────────────────────

const segmentOptions = M1_DETAIL_SEGMENTS.map(s => ({ label: s.label, value: s.key }))

// ─── Cross-sheet ─────────────────────────────────────────────────────────────

const showCrossSheetWarning = ref(false) // populated by CrossSheet composable integration

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRow() { addRow() }
function handleRemoveRow(index: number) { removeRow(index) }
function handleUpdate(index: number, field: keyof M1DetailRow, value: any) { updateRow(index, field, value) }

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('M1-2')
      break
    case 'exportData':
      exportData('M1-2')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, 'M1-2')
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

function handleAI(_section: string) { /* AI辅助待集成 */ }
function handleReview() { openReviewDialog?.('M1-2-detail', '明细表') }

// ─── Label helpers ───────────────────────────────────────────────────────────

function shareholderTypeLabel(val: string): string {
  return SHAREHOLDER_TYPE_OPTIONS.find(o => o.value === val)?.label || val || '—'
}

function paymentMethodLabel(val: string): string {
  return PAYMENT_METHOD_OPTIONS.find(o => o.value === val)?.label || val || '—'
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
})

function _restoreRows() {
  const fullData = formData.allResponses.value.get('M1-M1-2-full-data')
  if (fullData?.remark) {
    try {
      const parsed = JSON.parse(fullData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed
      }
    } catch { /* keep empty */ }
  }
}
</script>

<style scoped>
.m1-tab-detail { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
.abnormal-value { color: #f56c6c; font-weight: 700; }
:deep(.el-table) { font-size: 13px; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; flex-wrap: wrap; }
.cross-wp-links { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #d9ecff; border-radius: 6px; flex-wrap: wrap; }
.cross-wp-label { font-size: 12px; color: #409eff; font-weight: 500; }
.cross-wp-desc { font-size: 12px; color: #909399; }
.m1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.m1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
