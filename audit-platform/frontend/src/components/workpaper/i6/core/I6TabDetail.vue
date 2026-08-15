<template>
  <div class="i6-tab-detail">
    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title><span class="obj-title">一、审计目标</span></template>
      <ol class="obj-list">
        <li>确认所有应当记录的研发费用均已记录，所有已记录的研发费用均已包括在财务报表中（发生与完整性）。</li>
        <li>确认与研发费用有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性、计价和分摊、分类和可理解性）。</li>
      </ol>
    </el-alert>

    <!-- 编制逻辑说明 -->
    <div class="methodology-context">
      <p>
        <strong>I6-2 编制逻辑（对齐致同 Excel）：</strong>
        <strong>项目类别(A列)</strong>标识明细行，供 I6-1 审定表引用；
        <strong>费用性质(X列)</strong>用于附注披露 SUMIF（人工费/材料费等）。
        逐月归集未审发生额 → AJE/RJE → 本期审定数。
      </p>
    </div>

    <!-- TB 勾稽警告 -->
    <el-alert
      v-if="tbCrossCheck.hasData && !tbCrossCheck.isBalanced"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`明细未审合计 ${fmtAmount(tbCrossCheck.detailUnadj)} 与 TB 6602 发生额 ${fmtAmount(tbCrossCheck.tbNet)} 不一致，差额 ${fmtAmount(tbCrossCheck.diff)}`"
    />

    <!-- I6-1 勾稽警告 -->
    <el-alert
      v-if="adjudicationCrossCheck.hasData && !adjudicationCrossCheck.isBalanced"
      type="error"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`明细审定合计 ${fmtAmount(adjudicationCrossCheck.detailAudited)} 与 I6-1 审定合计 ${fmtAmount(adjudicationCrossCheck.adjudicationTotal)} 不一致，差额 ${fmtAmount(adjudicationCrossCheck.diff)}`"
    />

    <!-- I6-3 勾稽警告 -->
    <el-alert
      v-if="i63CrossCheck.hasData && !i63CrossCheck.isBalanced"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="`明细 AJE/RJE（${fmtAmount(i63CrossCheck.detailAje)}/${fmtAmount(i63CrossCheck.detailRje)}）与 I6-3 净额（${fmtAmount(i63CrossCheck.i63Aje)}/${fmtAmount(i63CrossCheck.i63Rje)}）不一致`"
    />

    <!-- 月度趋势图 -->
    <details class="chart-details" open>
      <summary>月度趋势图（合计行）</summary>
      <div ref="chartRef" class="trend-chart" />
    </details>

    <!-- 工具栏 -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>二、审计过程 — 研发费用明细表</h3>
        <GtIndexChip value="wp:I6-2" :context-project-id="projectId" />
        <GtIndexChip value="I6-1" @click="emit('navigate-sheet', 'I6-1')" />
        <GtIndexChip value="I6-3" @click="emit('navigate-sheet', 'I6-3')" />
      </div>
      <div class="header-actions">
        <el-button
          v-if="!isReadonly"
          size="small"
          plain
          @click="handleApplyTb"
        >
          TB写入未审
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          plain
          @click="handleSyncFromI63"
        >
          从 I6-3 同步调整
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          @click="handlePushToI63"
        >
          推送至 I6-3
        </el-button>
        <el-dropdown v-if="!isReadonly" size="small" trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :loading="pullingI1"
          :disabled="isReadonly"
          data-testid="i6-pull-i1-amort"
          @click="handlePullI1Amort"
        >
          从 I1-9 取摊销
        </el-button>
      </div>
    </div>

    <!-- 区段 Tab -->
    <div class="tab-bar">
      <el-segmented v-model="activeTab" :options="tabOptions" size="small" />
      <div class="tab-right">
        <el-button v-if="!isReadonly" size="small" type="success" plain @click="handleAddRow">
          + 新增明细行
        </el-button>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 主表 -->
    <el-table
      :data="rows"
      border
      size="small"
      class="detail-table"
      max-height="520"
      scrollbar-always-on
      :row-class-name="getRowClassName"
    >
      <el-table-column type="index" label="#" width="45" align="center" fixed="left" />

      <!-- 项目类别 A列 -->
      <el-table-column prop="category" label="项目类别(A)" min-width="120" fixed="left">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            placeholder="如：XX研发项目"
            @change="(v: string) => onCellChange(row.id, 'category', v)"
          />
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <!-- 费用性质 X列 -->
      <el-table-column prop="expenseNature" label="费用性质(X)" min-width="120" fixed="left">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.expenseNature"
            size="small"
            filterable
            allow-create
            default-first-option
            placeholder="人工费/材料费…"
            class="nature-select"
            @change="(v: string) => onCellChange(row.id, 'expenseNature', v)"
          >
            <el-option v-for="opt in expenseNatureOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.expenseNature || row.category }}</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            type="danger"
            text
            class="row-del"
            @click="handleRemoveRow(row.id)"
          >✕</el-button>
        </template>
      </el-table-column>

      <!-- 月度明细区段 -->
      <template v-if="activeTab === 'monthly'">
        <el-table-column
          v-for="(label, idx) in monthLabels"
          :key="`m-${idx}`"
          :label="label"
          min-width="95"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.months[idx]"
              size="small"
              :controls="false"
              :precision="2"
              class="amt-input"
              @change="(v: number | null) => onCellChange(row.id, `month_${idx}`, v ?? 0)"
            />
            <span v-else :class="{ 'anomaly-cell': isAnomalyMonth(row, idx) }">
              {{ fmtAmount(row.months[idx]) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="本期未审合计" min-width="120" align="right">
          <template #header>
            <el-tooltip content="= SUM(1月~12月)" placement="top">
              <span class="formula-col-header">本期未审合计</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.unadjTotal) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 调整审定区段 -->
      <template v-if="activeTab === 'audit'">
        <el-table-column label="本期未审合计" min-width="120" align="right">
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.unadjTotal) }}</span></template>
        </el-table-column>
        <el-table-column label="账项调整AJE" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.aje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number | null) => onCellChange(row.id, 'aje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类RJE" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.rje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number | null) => onCellChange(row.id, 'rje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期审定数" min-width="120" align="right">
          <template #header>
            <el-tooltip content="= 未审合计 + AJE + RJE" placement="top">
              <span class="formula-col-header">本期审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.auditedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比(%)" min-width="80" align="right">
          <template #default="{ row }">
            <span>{{ fmtPercent(row.ratio) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorUnadj"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number | null) => onCellChange(row.id, 'priorUnadj', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorUnadj) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorAje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number | null) => onCellChange(row.id, 'priorAje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorRje"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number | null) => onCellChange(row.id, 'priorRje', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorRje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期审定" min-width="110" align="right">
          <template #header>
            <el-tooltip content="= 上期未审 + 上期AJE + 上期RJE" placement="top">
              <span class="formula-col-header">上期审定</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.priorAudited) }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 分析勾稽区段 -->
      <template v-if="activeTab === 'linkage'">
        <el-table-column label="本期审定数" min-width="120" align="right">
          <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.auditedAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="与相关科目勾稽" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.reconciliation"
              size="small"
              placeholder="如：研发支出-结转"
              @change="(v: string) => onCellChange(row.id, 'reconciliation', v)"
            />
            <span v-else>{{ row.reconciliation || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="个别重分类" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.individualReclass"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number | null) => onCellChange(row.id, 'individualReclass', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.individualReclass) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合并重分类" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.consolidatedReclass"
              size="small"
              :controls="false"
              :precision="2"
              @change="(v: number | null) => onCellChange(row.id, 'consolidatedReclass', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.consolidatedReclass) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              @change="(v: string) => onCellChange(row.id, 'remark', v)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="55" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleRemoveRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <!-- 表尾：合计行 + 各月比例行 -->
    <div class="subtotals-bar">
      <div class="subtotal-row">
        <span class="subtotal-label">合计</span>
        <span class="subtotal-item">未审 {{ fmtAmount(totalRow.unadjTotal) }}</span>
        <span class="subtotal-item">AJE {{ fmtAmount(totalRow.aje) }}</span>
        <span class="subtotal-item">RJE {{ fmtAmount(totalRow.rje) }}</span>
        <span class="subtotal-item emphasize">审定 {{ fmtAmount(totalRow.auditedAmount) }}</span>
        <span class="subtotal-item">上期审定 {{ fmtAmount(totalRow.priorAudited) }}</span>
      </div>
      <div class="subtotal-row ratio-row">
        <span class="subtotal-label">各月比例</span>
        <span
          v-for="(ratio, idx) in monthlyRatios"
          :key="idx"
          class="subtotal-item"
          :class="{ 'anomaly-cell': anomalyMonths.includes(idx) }"
        >
          {{ monthLabels[idx] }}: {{ fmtPercent(ratio) }}
        </span>
      </div>
    </div>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <div class="cross-ref-bar">
            <span class="cross-ref-label">关联底稿：</span>
            <GtIndexChip value="I3-4" @click="emit('navigate-sheet', 'I3-4')" />
            <GtIndexChip value="I2-5" @click="emit('navigate-sheet', 'I2-5')" />
            <GtIndexChip value="I2-7" @click="emit('navigate-sheet', 'I2-7')" />
            <GtIndexChip value="I2-8" @click="emit('navigate-sheet', 'I2-8')" />
            <GtIndexChip value="I2-9" @click="emit('navigate-sheet', 'I2-9')" />
            <GtIndexChip value="I2-11" @click="emit('navigate-sheet', 'I2-11')" />
          </div>
        </div>
      </template>
      <ul class="procedure-list">
        <li v-for="(p, i) in auditProcedures" :key="i">{{ p }}</li>
      </ul>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="补充说明：各费用类别月度归集情况、异常月份分析、与 I6-1 审定表勾稽结果等…"
        @blur="onAuditNoteBlur"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="研发费用明细归集完整、准确，与审定表 I6-1 一致，列报恰当…"
        @blur="onAuditConclusionBlur"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>行维度：<strong>项目类别(A)</strong>供 I6-1 引用；<strong>费用性质(X)</strong>供附注 SUMIF</li>
        <li>同一费用性质可对应多行项目类别，附注披露按 X 列汇总</li>
        <li>本期未审合计 = SUM(1月~12月)；本期审定 = 未审 + AJE + RJE</li>
        <li>底部合计行应与 I6-1 审定表一致；各月比例 = 各月合计 / 全年审定 × 100%</li>
        <li>月度环比变动超 ±30% 红色标记，需在审计说明中解释</li>
        <li>无形资产摊销可点「从 I1-9 取摊销」自动回填</li>
        <li>AJE/RJE 可与 I6-3 双向联动：「从 I6-3 同步」或「推送至 I6-3」</li>
        <li>构成数据可推送至 I2-5「从 I6-2 带入构成」</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I6TabDetail.vue — I6-2 研发费用明细表（对齐致同 Excel 65列宽表）
 *
 * 行维度：费用性质（人工费/材料费/…）× 12月横向矩阵
 * 列分组：月度明细 | 调整审定 | 分析勾稽（el-segmented 切换）
 * 表尾：合计行 + 各月比例行
 *
 * Spec: .kiro/specs/i6-research-development-expense/ Task 4.3
 */
import { ref, computed, watch, onMounted, inject, nextTick, toRef, type Ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import {
  useI6Detail,
  DETAIL_TABS,
  NOTE_KEY,
  CONCLUSION_KEY,
  I6_DETAIL_AUDIT_PROCEDURES,
  I6_DETAIL_DEFAULT_CATEGORIES,
  type I6DetailRow,
  type I6DetailTabKey,
} from '../../composables/useI6Detail'
import { useI6ImportExport } from '../../composables/useI6ImportExport'
import { pullI1AmortIntoExpenseDetail } from '../../composables/expenseWpI1AmortPull'
import http from '@/utils/http'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// 🔴 金额展示走 displayPrefs 单一真源（千分符 / 2 位小数 / 单位「元」/ showZero 偏好）。
//    必须 setup **顶层** inject —— 写进函数体会静默失效（平台铁律）。
//    DisplayPrefs_Key 只能从 composables/displayPrefsKey 引入，
//    从 @/stores/displayPrefs 连带引会让整页崩（该 store 没有这个导出）。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData?: { unadjusted6602: number; audited6602?: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>
const isReadonlyRef = toRef(props, 'isReadonly') as Ref<boolean>
const tbDataRef = computed(() => props.tbData ?? { unadjusted6602: 0, audited6602: 0 })

const activeTab = ref<I6DetailTabKey>('monthly')
const tabOptions = DETAIL_TABS.map((t) => ({ label: t.label, value: t.key }))
const auditProcedures = I6_DETAIL_AUDIT_PROCEDURES
const expenseNatureOptions = [...I6_DETAIL_DEFAULT_CATEGORIES]

const auditNote = ref('')
const auditConclusion = ref('')
const chartRef = ref<HTMLElement>()
const pullingI1 = ref(false)

function _str(id: string): string {
  const it = props.allResponses.get(id)
  return (it?.remark ?? (typeof it === 'string' ? it : '')) as string
}

watch(() => props.allResponses, () => {
  auditNote.value = _str(NOTE_KEY)
  auditConclusion.value = _str(CONCLUSION_KEY)
}, { immediate: true })

const {
  rows,
  totalRow,
  monthlyTotals,
  monthlyRatios,
  anomalyMonths,
  adjudicationCrossCheck,
  tbCrossCheck,
  i63CrossCheck,
  monthLabels,
  updateCell,
  addRow,
  removeRow,
  replaceRows,
  applyI1AmortAmount,
  applyTbData,
  syncAjeFromI63,
  pushAjeToI63,
} = useI6Detail({
  allResponses: allResponsesRef,
  isReadonly: isReadonlyRef,
  tbData: tbDataRef,
  onSave: (itemId, value) => emit('save', itemId, value),
})

const { exportTemplate, exportData, importData } = useI6ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  onImported: async () => { /* rows reload via allResponses watch */ },
})

function onCellChange(id: string, key: string, value: number | string): void {
  updateCell(id, key, value)
}

function isAnomalyMonth(row: I6DetailRow, monthIdx: number): boolean {
  if (monthIdx < 1) return false
  const prior = row.months[monthIdx - 1] || 0
  const current = row.months[monthIdx] || 0
  if (prior === 0) return false
  return Math.abs((current - prior) / Math.abs(prior)) > 0.3
}

function getRowClassName({ row }: { row: I6DetailRow }): string {
  return row.anomalyHighlight ? 'row-anomaly' : ''
}

async function handleAddRow(): Promise<void> {
  try {
    const { value: category } = await ElMessageBox.prompt('请输入项目类别（A列）', '新增明细行', {
      confirmButtonText: '下一步',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
      inputPlaceholder: '如：芯片研发项目A',
    })
    const { value: nature } = await ElMessageBox.prompt('请选择/输入费用性质（X列）', '费用性质', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: category?.trim() || '',
      inputPlaceholder: '如：人工费、材料费',
    })
    if (category?.trim()) addRow(category.trim(), (nature || category).trim())
  } catch { /* cancelled */ }
}

function handleRemoveRow(id: string): void { removeRow(id) }

function handleImportExport(command: string): void {
  switch (command) {
    case 'export-template': exportTemplate('I6-2'); break
    case 'export-data': exportData('I6-2'); break
    case 'import-data': triggerImport(); break
  }
}

function triggerImport(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls,.csv'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/i6/import-data`,
        formData,
        { params: { sheet: 'I6-2' }, headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const data = res.data?.data ?? res.data
      if (Array.isArray(data?.rows)) {
        replaceRows(data.rows)
        ElMessage.success('导入成功')
      } else {
        await importData(file, 'I6-2')
      }
    } catch {
      ElMessage.error('导入失败')
    }
  }
  input.click()
}

function onAuditNoteBlur(): void {
  if (props.isReadonly) return
  emit('save', NOTE_KEY, auditNote.value)
}

function onAuditConclusionBlur(): void {
  if (props.isReadonly) return
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

function handleReview(): void { openReviewDialog('I6-2 明细表') }

function handleSyncFromI63(): void {
  const result = syncAjeFromI63()
  if (result.ok) ElMessage.success(result.message)
  else ElMessage.info(result.message)
}

function handleApplyTb(): void {
  const result = applyTbData()
  if (result.ok) ElMessage.success(result.message)
  else ElMessage.warning(result.message)
}

function handlePushToI63(): void {
  const result = pushAjeToI63()
  if (result.ok) {
    ElMessage.success(result.message)
    emit('navigate-sheet', 'I6-3')
  } else {
    ElMessage.info(result.message)
  }
}

async function handlePullI1Amort(): Promise<void> {
  if (props.isReadonly) return
  pullingI1.value = true
  try {
    const result = await pullI1AmortIntoExpenseDetail(props.projectId, 'I6')
    if (!result.amount) {
      ElMessage.warning(result.message || 'I1-9 摊销合计为 0')
      return
    }
    const applied = applyI1AmortAmount(result.amount)
    if (applied.ok) ElMessage.success(applied.message)
    else ElMessage.warning(applied.message)
  } catch (e: any) {
    ElMessage.error(e?.message || '拉取 I1-9 失败')
  } finally {
    pullingI1.value = false
  }
}

onMounted(async () => {
  await nextTick()
  if (!chartRef.value) return
  try {
    const echarts = await import('echarts')
    const chart = echarts.init(chartRef.value)
    watch(monthlyTotals, (totals) => {
      chart.setOption({
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: [...monthLabels] },
        yAxis: { type: 'value', name: '金额(元)' },
        series: [{
          type: 'line',
          name: '合计',
          data: totals,
          smooth: true,
          areaStyle: { opacity: 0.15 },
          markPoint: anomalyMonths.value.length
            ? { data: anomalyMonths.value.map((idx) => ({ xAxis: idx, yAxis: totals[idx], symbolSize: 10 })) }
            : undefined,
        }],
        grid: { left: 60, right: 20, top: 30, bottom: 30 },
      })
    }, { immediate: true })
  } catch { /* echarts unavailable */ }
})

function fmtAmount(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v)
}

function fmtPercent(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v.toFixed(2)}%`
}
</script>

<style scoped>
.i6-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.methodology-context { border-left: 4px solid #d97706; background: #fffbeb; padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.8; }
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }
.cross-alert { margin-bottom: 12px; }
.chart-details { margin-bottom: 16px; }
.chart-details summary { cursor: pointer; font-weight: 500; font-size: var(--wp-font-size, 13px); }
.trend-chart { width: 100%; height: 220px; margin-top: 8px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.tab-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.tab-right { display: flex; gap: 8px; align-items: center; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; padding-bottom: 2px; }
.formula-value { border-bottom: 1px dashed #c0c4cc; cursor: help; padding-bottom: 1px; color: #303133; font-weight: 500; }
.row-del { margin-left: 4px; font-size: 11px; padding: 2px 4px; }
.nature-select { width: 100%; min-width: 100px; }
.anomaly-cell { color: #dc2626; font-weight: 600; background: #fef2f2; padding: 1px 4px; border-radius: 2px; }
.detail-table :deep(.row-anomaly td) { background: #fef2f2 !important; }
.subtotals-bar { margin-top: 12px; padding: 10px 12px; background: #f0f9ff; border-radius: 6px; font-size: 12px; }
.subtotal-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.subtotal-row:last-child { margin-bottom: 0; }
.ratio-row { padding-top: 6px; border-top: 1px dashed #bfdbfe; }
.subtotal-label { font-weight: 600; color: #303133; min-width: 64px; }
.subtotal-item { color: #606266; }
.subtotal-item.emphasize { font-weight: 600; color: var(--el-color-primary); }
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.cross-ref-bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cross-ref-label { font-size: 12px; color: #909399; }
.procedure-list { margin: 0 0 12px; padding-left: 20px; font-size: 12px; color: #606266; line-height: 1.7; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
.amt-input { width: 100%; }
</style>
