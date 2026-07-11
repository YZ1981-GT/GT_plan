<template>
  <div class="l5-tab-adjudication">
    <!-- ═══ 标题 + DualMode + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L5-1 长期应付款审定表</h3>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('adjudication')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>
        <strong>审计目标：</strong>确认长期应付款及未确认融资费用余额的存在、完整、准确与列报，验证实际利率法摊销与净额计算正确，检查关联方交易公允性。
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>长期应付款为负债类贷方科目（2701）：</strong>
        期末余额 = 期初 + 贷方发生额 − 借方发生额。
        未确认融资费用为借方备抵科目：期末 = 期初 + 借方(新增) − 贷方(摊销)。
        净额 = 长期应付款 − 未确认融资费用。审定数 = 未审数 + AJE + RJE。
      </div>
    </div>

    <!-- ═══ 一、长期应付款（贷方/负债）区块 ═══ -->
    <div class="block-section">
      <h4 class="block-title">一、长期应付款（贷方/负债类）</h4>
      <el-table
        :data="computedPayableRows"
        border
        size="small"
        style="width: 100%"
        show-summary
        :summary-method="getPayableSummaries"
      >
        <el-table-column prop="itemName" label="项目" min-width="160" fixed>
          <template #default="{ row }">
            <el-tag size="small" type="info" style="margin-right: 4px">{{ row.category }}</el-tag>
            {{ row.itemName }}
          </template>
        </el-table-column>

        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updatePayableRow($index, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="贷方发生" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.increaseAmount" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updatePayableRow($index, 'increaseAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.increaseAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="借方发生" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.decreaseAmount" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updatePayableRow($index, 'decreaseAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="期初 + 贷方 − 借方（负债类贷方！）" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="未审数" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updatePayableRow($index, 'unadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.aje" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updatePayableRow($index, 'aje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.rje" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updatePayableRow($index, 'rje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="审定数" width="120" align="right">
          <template #header>
            <el-tooltip content="未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 二、未确认融资费用（借方/备抵）区块 ═══ -->
    <div class="block-section">
      <h4 class="block-title">二、未确认融资费用（借方/负债备抵类）</h4>
      <el-table
        :data="computedUnrecognizedRows"
        border
        size="small"
        style="width: 100%"
        show-summary
        :summary-method="getUnrecognizedSummaries"
      >
        <el-table-column prop="itemName" label="项目" min-width="160" fixed>
          <template #default="{ row }">
            <el-tag size="small" type="warning" style="margin-right: 4px">{{ row.category }}</el-tag>
            {{ row.itemName }}
          </template>
        </el-table-column>

        <el-table-column label="期初" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.beginning" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updateUnrecognizedRow($index, 'beginning', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="借方发生" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.increaseAmount" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updateUnrecognizedRow($index, 'increaseAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.increaseAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="贷方发生" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.decreaseAmount" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updateUnrecognizedRow($index, 'decreaseAmount', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末" width="120" align="right">
          <template #header>
            <el-tooltip content="期初 + 借方 − 贷方（备抵类借方！）" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="未审数" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.unadjusted" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updateUnrecognizedRow($index, 'unadjusted', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="AJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.aje" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updateUnrecognizedRow($index, 'aje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="RJE" width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number :model-value="row.rje" :controls="false" size="small" style="width: 100%" @change="(val: number | undefined) => updateUnrecognizedRow($index, 'rje', val ?? 0)" />
            </template>
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="审定数" width="120" align="right">
          <template #header>
            <el-tooltip content="未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 三、净额合计 ═══ -->
    <div class="net-section">
      <h4 class="block-title">三、净额合计</h4>
      <div class="net-summary-grid">
        <div class="net-item">
          <span class="net-label">长期应付款审定数</span>
          <span class="net-value">{{ fmtAmount(payableTotal.audited) }}</span>
        </div>
        <div class="net-item net-minus">
          <span class="net-label">− 未确认融资费用审定数</span>
          <span class="net-value">{{ fmtAmount(unrecognizedTotal.audited) }}</span>
        </div>
        <div class="net-item net-result">
          <span class="net-label">= 长期应付款净额</span>
          <span class="net-value net-value-highlight" :class="{ 'net-abnormal': netPayableAudited < 0 }">
            {{ fmtAmount(netPayableAudited) }}
          </span>
        </div>
      </div>
      <el-alert v-if="netPayableAudited < 0" type="warning" :closable="false" show-icon style="margin-top: 8px">
        净额异常：长期应付款净额为负，请核查未确认融资费用是否超出应付款总额
      </el-alert>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>长期应付款为负债类贷方科目：期末 = 期初 + 贷方 − 借方</li>
        <li>未确认融资费用为借方备抵科目：期末 = 期初 + 借方 − 贷方</li>
        <li>净额 = 长期应付款 − 未确认融资费用（报表列示金额）</li>
        <li>按款项类型分类：融资租赁 / 分期付款 / 其他</li>
        <li>审定数变化自动回写 TB（科目2701+未确认融资费用）并通知附注组件</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传 -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display: none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabAdjudication — L5-1 长期应付款审定表
 *
 * Requirements: 2.1-2.8
 * - 负债类双区块：一、长期应付款(贷方/负债) → 二、未确认融资费用(借方/备抵) → 三、净额合计
 * - 公式列：期末(负债类/备抵类) + 审定数(未审+AJE+RJE)
 * - DualMode el-segmented at top (结构化/OO)
 * - Import/Export dropdown
 * - Save → writebackTB(2701+未确认融资费用)
 */
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useL5FormData } from '../../composables/useL5FormData'
import { useL5DualMode } from '../../composables/useL5DualMode'
import { useL5ImportExport } from '../../composables/useL5ImportExport'
import {
  useL5Adjudication,
  type L5AdjudicationData,
  type L5AdjudicationRow,
} from '../../composables/useL5Adjudication'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useL5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── DualMode ────────────────────────────────────────────────────────────────

const dualMode = useL5DualMode({
  wpId: computed(() => props.wpId),
})

// ─── ImportExport ────────────────────────────────────────────────────────────

const importExport = useL5ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 审定表行数据（双区块） ──────────────────────────────────────────────────

const adjudicationData: L5AdjudicationData = reactive({
  payableRows: [
    { key: 'p1', category: '融资租赁', itemName: '融资租赁应付款', beginning: 0, increaseAmount: 0, decreaseAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { key: 'p2', category: '分期付款', itemName: '分期付款购买资产', beginning: 0, increaseAmount: 0, decreaseAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { key: 'p3', category: '其他', itemName: '其他长期应付款', beginning: 0, increaseAmount: 0, decreaseAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
  ] as L5AdjudicationRow[],
  unrecognizedRows: [
    { key: 'u1', category: '融资租赁', itemName: '融资租赁未确认费用', beginning: 0, increaseAmount: 0, decreaseAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { key: 'u2', category: '分期付款', itemName: '分期付款未确认费用', beginning: 0, increaseAmount: 0, decreaseAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
    { key: 'u3', category: '其他', itemName: '其他未确认融资费用', beginning: 0, increaseAmount: 0, decreaseAmount: 0, endBalance: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0 },
  ] as L5AdjudicationRow[],
})

// ─── Adjudication Composable ─────────────────────────────────────────────────

const {
  computedPayableRows,
  computedUnrecognizedRows,
  payableTotal,
  unrecognizedTotal,
  netPayableAudited,
  updatePayableRow,
  updateUnrecognizedRow,
  saveAndWriteback,
} = useL5Adjudication(formData, adjudicationData)

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 合计行方法 ──────────────────────────────────────────────────────────────

function getPayableSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const t = payableTotal.value
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '长期应付款合计'; return }
    const vals = [t.beginning, t.increase, t.decrease, t.end, t.unadjusted, t.aje, t.rje, t.audited]
    sums[index] = fmtAmount(vals[index - 1] ?? 0)
  })
  return sums
}

function getUnrecognizedSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const t = unrecognizedTotal.value
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '未确认融资费用合计'; return }
    const vals = [t.beginning, t.increase, t.decrease, t.end, t.unadjusted, t.aje, t.rje, t.audited]
    sums[index] = fmtAmount(vals[index - 1] ?? 0)
  })
  return sums
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
  } finally {
    isSaving.value = false
  }
}

function handleImportExport(command: string) {
  switch (command) {
    case 'export-template':
      importExport.exportTemplate()
      break
    case 'export-data':
      importExport.exportData()
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    importExport.importData(file)
  }
  // Reset input
  if (input) input.value = ''
}

function saveAuditNote() {
  formData.debouncedSave('L5-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(_section: string) {
  // AI辅助钩子（集成时实现）
}

function handleReview() {
  openReviewDialog?.()
}

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 加载 ─────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l5-tab-adjudication {
  padding: 12px;
  font-size: 13px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: 13px;
  color: #6b5900;
  line-height: 1.6;
}

.block-section {
  margin-bottom: 24px;
}

.block-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

:deep(.el-table) {
  font-size: 13px;
}

.net-section {
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.net-summary-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.net-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  border-radius: 4px;
}

.net-label {
  color: #606266;
  font-size: 13px;
}

.net-value {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.net-minus {
  color: #e6a23c;
}

.net-result {
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
}

.net-value-highlight {
  color: #409eff;
  font-size: 16px;
}

.net-abnormal {
  color: #f56c6c !important;
}

.audit-note-card {
  margin-top: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.l5-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l5-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.l5-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
