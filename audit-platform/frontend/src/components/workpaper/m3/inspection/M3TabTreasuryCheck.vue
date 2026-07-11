<template>
  <div class="m3-tab-treasury-check">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M3-5 库存股检查表</h3>
        <el-tag type="danger" size="small">回购/注销核对</el-tag>
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
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>库存股回购/注销核对要点：</strong>
        ①回购核对：回购金额 = 回购股数 × 回购单价，需与决议/银行流水/公告一致。
        ②注销核对：注销冲减差额 = 注销金额 − 冲减实收资本(M2) − 冲减资本公积(M4)。
        差额≠0需进一步冲减盈余公积/未分配利润（CAS会计准则要求）。
      </div>
    </div>

    <!-- ═══ Section 1: 回购核对区 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>回购核对</span>
          <div class="card-header-right">
            <el-button size="small" :disabled="isReadonly" type="primary" @click="handleAddRepurchaseRow">
              <el-icon><Plus /></el-icon> 新增
            </el-button>
            <el-button size="small" @click="handleAI('repurchase-check')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="check.computedRepurchaseRows.value" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="45" align="center" />
        <el-table-column label="回购批次" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.batchName"
              size="small"
              placeholder="批次名"
              @change="(val: string) => check.updateRepurchaseRow($index, 'batchName', val)"
            />
            <span v-else>{{ row.batchName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回购决议" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.resolution"
              size="small"
              placeholder="决议文号"
              @change="(val: string) => check.updateRepurchaseRow($index, 'resolution', val)"
            />
            <span v-else>{{ row.resolution || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回购股数" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.shares"
              :controls="false"
              :min="0"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => check.updateRepurchaseRow($index, 'shares', val ?? 0)"
            />
            <span v-else>{{ fmtNumber(row.shares) }}</span>
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
              @change="(val: number | undefined) => check.updateRepurchaseRow($index, 'price', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.price) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回购总额" min-width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 回购股数 × 回购单价" placement="top">
              <span class="formula-col-header">回购总额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.totalAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对结果" width="90" align="center">
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.checkResult"
              size="small"
              placeholder="—"
              @change="(val: string) => check.updateRepurchaseRow($index, 'checkResult', val)"
            >
              <el-option label="√ 一致" value="√" />
              <el-option label="× 有差异" value="×" />
            </el-select>
            <el-tag v-else :type="row.checkResult === '√' ? 'success' : row.checkResult === '×' ? 'danger' : 'info'" size="small">
              {{ row.checkResult || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(val: string) => check.updateRepurchaseRow($index, 'remark', val)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ $index }">
            <el-button type="danger" text size="small" @click="check.removeRepurchaseRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="subtotal-bar">
        回购金额合计：<strong class="formula-value">{{ fmtAmount(check.repurchaseTotal.value) }}</strong>
      </div>
    </el-card>

    <!-- ═══ Section 2: 注销核对区 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>注销核对（冲减M2/M4）</span>
          <div class="card-header-right">
            <GtIndexChip value="M2" label="→M2实收资本" />
            <GtIndexChip value="M4" label="→M4资本公积" />
            <el-button size="small" :disabled="isReadonly" type="primary" @click="handleAddCancelRow">
              <el-icon><Plus /></el-icon> 新增
            </el-button>
            <el-button size="small" type="warning" :disabled="isReadonly" @click="handlePublishCancellation">
              联动M2/M4
            </el-button>
            <el-button size="small" @click="handleAI('cancel-check')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>

      <!-- 注销差额警告 -->
      <el-alert
        v-if="check.hasUnresolvedDiff.value"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        存在注销冲减差额≠0的行，需进一步冲减盈余公积(M5)/未分配利润(M6)
      </el-alert>

      <el-table :data="check.computedCancelRows.value" border size="small" style="width: 100%">
        <el-table-column type="index" label="#" width="45" align="center" />
        <el-table-column label="回购批次" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.batchName"
              size="small"
              placeholder="批次名"
              @change="(val: string) => check.updateCancelRow($index, 'batchName', val)"
            />
            <span v-else>{{ row.batchName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="注销股数" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.cancelShares"
              :controls="false"
              :min="0"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => check.updateCancelRow($index, 'cancelShares', val ?? 0)"
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
              @change="(val: number | undefined) => check.updateCancelRow($index, 'cancelAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.cancelAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="冲减实收资本(M2)" min-width="140" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.deductCapital"
              :controls="false"
              :min="0"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => check.updateCancelRow($index, 'deductCapital', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.deductCapital) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="冲减资本公积(M4)" min-width="140" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.deductReserve"
              :controls="false"
              :min="0"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => check.updateCancelRow($index, 'deductReserve', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.deductReserve) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="冲减差额" min-width="120" align="right">
          <template #header>
            <el-tooltip content="公式: 注销金额 − 冲减实收资本 − 冲减资本公积" placement="top">
              <span class="formula-col-header">冲减差额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', Math.abs(row.diff) > 0.01 ? 'diff-warning' : '']">
              {{ fmtAmount(row.diff) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差额处理" min-width="130">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.diffHandling"
              size="small"
              placeholder="冲减M5/M6等"
              @change="(val: string) => check.updateCancelRow($index, 'diffHandling', val)"
            />
            <span v-else>{{ row.diffHandling || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ $index }">
            <el-button type="danger" text size="small" @click="check.removeCancelRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="subtotal-bar">
        注销金额合计：<strong class="formula-value">{{ fmtAmount(check.cancelTotal.value) }}</strong>
      </div>
    </el-card>

    <!-- ═══ Section 3: 核对清单 + 审计结论 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>核对清单与审计结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <!-- 清单 -->
      <div class="checklist-section">
        <div v-for="(item, idx) in check.checklist.value" :key="idx" class="checklist-item">
          <span class="checklist-index">{{ item.index }}.</span>
          <span class="checklist-text">{{ item.item }}</span>
          <el-radio-group
            v-if="!isReadonly"
            :model-value="item.passed"
            size="small"
            @change="(val: boolean | null) => check.updateChecklistItem(idx, 'passed', val)"
          >
            <el-radio-button :value="true">通过</el-radio-button>
            <el-radio-button :value="false">不通过</el-radio-button>
          </el-radio-group>
          <el-tag v-else :type="item.passed === true ? 'success' : item.passed === false ? 'danger' : 'info'" size="small">
            {{ item.passed === true ? '通过' : item.passed === false ? '不通过' : '待核' }}
          </el-tag>
        </div>
      </div>

      <!-- 审计结论 -->
      <div class="conclusion-section">
        <div class="conclusion-label">审计结论：</div>
        <el-input
          :model-value="check.conclusion.value"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          :readonly="isReadonly"
          placeholder="根据回购/注销核对结果，填写审计结论..."
          @change="(val: string) => check.setConclusion(val)"
        />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>回购核对</strong>：回购金额 = 回购股数 × 回购单价，核对银行流水/决议/公告</li>
        <li><strong>注销核对</strong>：注销冲减差额 = 注销金额 − 冲减实收资本(M2) − 冲减资本公积(M4)</li>
        <li>差额≠0时需继续冲减盈余公积(M5)/未分配利润(M6)（CAS准则要求）</li>
        <li>注销冲减联动M2实收资本和M4资本公积</li>
        <li>库存股是权益备抵（借方），注销减少库存股在贷方</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M3TabTreasuryCheck — M3-5 库存股检查表（回购/注销核对）
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 4.5
 * Requirements: 5.1-5.5
 *
 * 功能：
 * - 两 section: 回购核对区 + 注销核对区（el-card wrapped）
 * - Uses useM3TreasuryCheck composable
 * - Checklist items + conclusion textarea
 * - AI button per section
 * - 注销冲减核对(M2/M4)
 * - calcRepurchaseAmount / calcCancelDiff formulas
 *
 * 科目：4002 库存股（**借方/权益备抵类！**）
 */
import { computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useM3FormData } from '../../composables/useM3FormData'
import { useM3TreasuryCheck } from '../../composables/useM3TreasuryCheck'
import { useM3ImportExport, type M3ImportableSheet } from '../../composables/useM3ImportExport'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

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

const check = useM3TreasuryCheck(formData)

const { exportTemplate, exportData, importData } = useM3ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Init checklist items ────────────────────────────────────────────────────

function _initChecklist() {
  if (check.checklist.value.length === 0) {
    check.checklist.value = [
      { index: 1, item: '回购决议/公告是否经董事会/股东大会审议通过', passed: null, note: '' },
      { index: 2, item: '回购价格是否在决议授权范围内', passed: null, note: '' },
      { index: 3, item: '回购股数是否与银行流水/券商记录一致', passed: null, note: '' },
      { index: 4, item: '回购记账方向是否正确（借记库存股，贷记银行存款）', passed: null, note: '' },
      { index: 5, item: '注销是否经合法程序（减资决议/工商变更）', passed: null, note: '' },
      { index: 6, item: '注销冲减实收资本是否按面值计算', passed: null, note: '' },
      { index: 7, item: '注销差额冲减资本公积→盈余公积→未分配利润是否按顺序', passed: null, note: '' },
      { index: 8, item: '库存股期末余额是否与工商登记/证券登记一致', passed: null, note: '' },
    ]
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAddRepurchaseRow() {
  check.addRepurchaseRow()
}

function handleAddCancelRow() {
  check.addCancelRow()
}

/** 发布注销冲减事件到M2/M4（联动） */
function handlePublishCancellation() {
  check.publishCancellationDeduction()
  ElMessage.success('已发布注销冲减联动通知至M2/M4')
}

function handleImportExport(command: string) {
  const sheet: M3ImportableSheet = 'M3-5'
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
            _restoreData()
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
function handleReview() { openReviewDialog?.('M3-5-treasury-check', '库存股检查表') }

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

function _restoreData() {
  const repData = formData.allResponses.value.get('M3-M3-5-repurchase-all')
  if (repData?.remark) {
    try {
      const parsed = JSON.parse(repData.remark)
      if (Array.isArray(parsed)) check.repurchaseRows.value = parsed
    } catch { /* ignore */ }
  }

  const cancelData = formData.allResponses.value.get('M3-M3-5-cancel-all')
  if (cancelData?.remark) {
    try {
      const parsed = JSON.parse(cancelData.remark)
      if (Array.isArray(parsed)) check.cancelRows.value = parsed
    } catch { /* ignore */ }
  }

  const checklistData = formData.allResponses.value.get('M3-M3-5-checklist-all')
  if (checklistData?.remark) {
    try {
      const parsed = JSON.parse(checklistData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) check.checklist.value = parsed
    } catch { /* ignore */ }
  }

  const conclusionData = formData.allResponses.value.get('M3-M3-5-conclusion')
  if (conclusionData?.remark) check.conclusion.value = conclusionData.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
  _initChecklist()
})
</script>

<style scoped>
.m3-tab-treasury-check { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.check-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-header-right { display: flex; align-items: center; gap: 8px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.diff-warning { color: #f56c6c !important; font-weight: 600; }
:deep(.el-table) { font-size: 13px; }
.subtotal-bar { margin-top: 8px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; font-size: 13px; }
.checklist-section { margin-bottom: 16px; }
.checklist-item { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #f2f6fc; }
.checklist-index { font-weight: 600; color: #303133; min-width: 20px; }
.checklist-text { flex: 1; color: #606266; }
.conclusion-section { margin-top: 12px; }
.conclusion-label { font-weight: 500; color: #303133; margin-bottom: 8px; }
.m3-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.m3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
