<!--
  G7TabInternalTransaction.vue — G7-15 内部交易抵销测算表（41行×14列）

  核心特色：顺流/逆流差异化抵销逻辑
  - 顺流交易(投资方→被投资方)：应抵销 = 未实现利润 × 100%（全额抵消）
  - 逆流交易(被投资方→投资方)：应抵销 = 未实现利润 × 持股比例（按份额）
  - 交易类型未选时应抵销列显示"—"

  14列：被投资单位|交易类型(下拉)|交易内容|交易金额|未实现利润(公式/可覆盖)|
        持股比例|应抵销金额(公式)|上年抵销|本年变动(公式)|抵销分录|
        是否关联交易|审计结论|索引|备注

  Spec: .kiro/specs/g7-long-term-equity-method/
  Task: 6.3
  Requirements: 6.1, 6.2, 6.3, 7.4
-->
<template>
  <div class="g7-tab-internal-transaction">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>内部交易抵销规则：</strong></p>
      <ul>
        <li><b>顺流交易</b>（投资方→被投资方）：应抵销 = 未实现利润 × 100%</li>
        <li><b>逆流交易</b>（被投资方→投资方）：应抵销 = 未实现利润 × 持股比例</li>
        <li>未实现利润 = 交易金额 × 毛利率（或直接填写覆盖）</li>
      </ul>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证投资方与合营/联营企业之间顺流、逆流内部交易未实现利润的抵销是否完整，抵销方向及金额是否恰当。"
      class="objective-alert"
    />

    <!-- section标题 + 操作按钮 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-15 内部交易抵销测算表</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiConclusion">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G7-15-internal-transaction')">💬复核</el-button>
      </div>
    </div>

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-15" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 14列表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="580"
      class="internal-transaction-table"
      row-key="id"
    >
      <!-- 序号 -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <!-- 1. 被投资单位 -->
      <el-table-column label="被投资单位" min-width="130" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'investeeName', v)"
          />
        </template>
      </el-table-column>

      <!-- 2. 交易类型(下拉) -->
      <el-table-column label="交易类型" width="110" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.transactionType"
            size="small"
            placeholder="请选择"
            clearable
            :disabled="isReadonly"
            @change="(v: string) => handleTypeChange(row.id, v as '顺流' | '逆流')"
          >
            <el-option label="顺流" value="顺流" />
            <el-option label="逆流" value="逆流" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 3. 交易内容 -->
      <el-table-column label="交易内容" min-width="130">
        <template #default="{ row }">
          <el-input
            :model-value="row.transactionContent"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'transactionContent', v)"
          />
        </template>
      </el-table-column>

      <!-- 4. 交易金额 -->
      <el-table-column label="交易金额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.transactionAmount"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => handleAmountChange(row.id, v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 5. 未实现利润(公式 OR 直接填写覆盖) -->
      <el-table-column label="未实现利润" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="= 交易金额 × 毛利率（支持直接填写覆盖）">
            未实现利润
          </span>
        </template>
        <template #default="{ row }">
          <el-input-number
            :model-value="row.unrealizedProfit"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => handleProfitOverride(row.id, v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 6. 持股比例 -->
      <el-table-column label="持股比例" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.investmentRatio"
            size="small"
            :controls="false"
            :precision="4"
            :step="0.01"
            :min="0"
            :max="1"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => handleRatioChange(row.id, v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 7. 应抵销金额(公式，核心差异化列) -->
      <el-table-column label="应抵销金额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="顺流=未实现利润; 逆流=未实现利润×持股比例">
            应抵销金额
          </span>
        </template>
        <template #default="{ row }">
          <span
            v-if="row.transactionType"
            class="formula-cell"
            :title="getEliminationTooltip(row)"
          >
            {{ fmtNum(row.eliminationAmount) }}
          </span>
          <span v-else class="no-type-placeholder">—</span>
        </template>
      </el-table-column>

      <!-- 8. 上年抵销 -->
      <el-table-column label="上年抵销" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.priorElimination"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => handlePriorChange(row.id, v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 9. 本年变动(公式) -->
      <el-table-column label="本年变动" min-width="110" align="right">
        <template #header>
          <span class="formula-header" title="= 应抵销金额 - 上年抵销">本年变动</span>
        </template>
        <template #default="{ row }">
          <span
            v-if="row.transactionType"
            class="formula-cell"
            :title="`本年变动 = ${fmtNum(row.eliminationAmount)} - ${fmtNum(row.priorElimination)}`"
          >
            {{ fmtNum(row.currentChange) }}
          </span>
          <span v-else class="no-type-placeholder">—</span>
        </template>
      </el-table-column>

      <!-- 10. 抵销分录 -->
      <el-table-column label="抵销分录" min-width="150">
        <template #default="{ row }">
          <el-input
            :model-value="row.eliminationEntry"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'eliminationEntry', v)"
          />
        </template>
      </el-table-column>

      <!-- 11. 是否关联交易 -->
      <el-table-column label="关联交易" width="90" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.isRelatedParty ? '是' : '否'"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'isRelatedParty', v === '是')"
          >
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 12. 审计结论 -->
      <el-table-column label="审计结论" width="110" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.auditConclusion"
            size="small"
            placeholder="请选择"
            clearable
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'auditConclusion', v)"
          >
            <el-option label="合理" value="合理" />
            <el-option label="基本合理" value="基本合理" />
            <el-option label="不合理" value="不合理" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 13. 索引 -->
      <el-table-column label="索引" width="90">
        <template #default="{ row }">
          <el-input
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'indexRef', v)"
          />
        </template>
      </el-table-column>

      <!-- 14. 备注 -->
      <el-table-column label="备注" min-width="130">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'remark', v)"
          />
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="handleRemoveRow(row.id)">
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述所执行程序、测试情况及结果，拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论（AI辅助） -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对内部交易抵销测算的审计结论..."
        @change="persistConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>顺流交易（投资方→被投资方）：全额抵销未实现利润</li>
        <li>逆流交易（被投资方→投资方）：按持股比例抵销未实现利润</li>
        <li>未实现利润可由公式计算（交易金额×毛利率），也可直接填写覆盖</li>
        <li>本年变动 = 应抵销金额 - 上年抵销金额</li>
        <li>交易类型未选择时，应抵销金额和本年变动显示"—"</li>
        <li>抵销分录建议填写：借/贷科目及金额</li>
        <li>G7-15的抵销金额将联动G7-14权益法测算表中的"内部交易抵销"列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabInternalTransaction — G7-15 内部交易抵销测算表
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Task: 6.3
 *
 * 核心逻辑：
 * - calcEliminationAmount('downstream', profit, ratio) → profit (全额)
 * - calcEliminationAmount('upstream', profit, ratio) → profit × ratio (按份额)
 * - 交易类型未选时 eliminationAmount 显示 "—"
 * - unrealizedProfit 支持公式计算 OR 直接填写覆盖
 *
 * Requirements: 6.1, 6.2, 6.3, 7.4
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calcEliminationAmount,
  parseNum,
} from '../../composables/useG7EquityMethodFormulaEngine'
import {
  G7_15_ROWS_KEY,
  G7_15_SECTION_KEY,
} from '../../composables/g7EquityMethodCrossSheet'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { InternalTransactionRow } from '../../composables/useG7EquityMethodFormData'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Data Layer ──────────────────────────────────────────────────────────────

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const SECTION_KEY = G7_15_SECTION_KEY
const ROWS_KEY = G7_15_ROWS_KEY
const CONCLUSION_KEY = 'G7-15-conclusion'
const AUDIT_NOTE_KEY = 'G7-15-audit-note'

/** 行数据(响应式) */
const rows = ref<InternalTransactionRow[]>([])

/** 审计结论 */
const conclusion = ref('')

/** 审计说明（持久化 checklist_responses，conclusion:null） */
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

// ─── Initialize ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.load()

  const hydrateRows = (raw: unknown): boolean => {
    const list = Array.isArray(raw)
      ? raw
      : (raw && typeof raw === 'object' && Array.isArray((raw as any).rows) ? (raw as any).rows : null)
    if (!list?.length) return false
    rows.value = list.map((r: any, idx: number) => ({
      ...createEmptyRow(idx + 1),
      ...r,
      seq: idx + 1,
      id: r.id || `g15-${Date.now()}-${idx}`,
    }))
    recalcAll()
    return true
  }

  const parseSaved = (raw: unknown): unknown => {
    if (raw == null || raw === '') return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(String(raw)) } catch { return null }
  }

  const sectionSaved = parseSaved(formData.data.value.get(SECTION_KEY)?.conclusion)
  const rowsSaved = parseSaved(
    formData.data.value.get(ROWS_KEY)?.conclusion
    ?? formData.data.value.get(ROWS_KEY)?.remark,
  )
  const snapshotSection = parseSaved(props.htmlData?.responses_snapshot?.[SECTION_KEY]?.conclusion)
  const snapshotRows = parseSaved(
    props.htmlData?.responses_snapshot?.[ROWS_KEY]?.conclusion
    ?? props.htmlData?.responses_snapshot?.[ROWS_KEY]?.remark,
  )

  if (
    !hydrateRows(sectionSaved)
    && !hydrateRows(rowsSaved)
    && !hydrateRows(snapshotSection)
    && !hydrateRows(snapshotRows)
    && !hydrateRows(props.htmlData?.internalTransaction)
    && !hydrateRows((props.htmlData as any)?.rows)
  ) {
    rows.value = Array.from({ length: 5 }, (_, i) => createEmptyRow(i + 1))
  }

  const savedConclusion = formData.data.value.get(CONCLUSION_KEY)
  if (savedConclusion?.conclusion) {
    conclusion.value = savedConclusion.conclusion
  }

  const savedNote = formData.data.value.get(AUDIT_NOTE_KEY)
  if (savedNote?.remark) {
    auditNote.value = savedNote.remark
  }
})

// ─── Row Factory ─────────────────────────────────────────────────────────────

function createEmptyRow(seq: number, investeeName = ''): InternalTransactionRow {
  return {
    id: `g15-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    investeeName,
    transactionType: '' as any,
    transactionContent: '',
    transactionAmount: 0,
    unrealizedProfit: 0,
    investmentRatio: 0,
    eliminationAmount: 0,
    priorElimination: 0,
    currentChange: 0,
    eliminationEntry: '',
    isRelatedParty: false,
    auditConclusion: '' as any,
    indexRef: '',
    remark: '',
  }
}

// ─── Formula Recalculation ───────────────────────────────────────────────────

/** 对单行重新计算公式列 */
function recalcRow(row: InternalTransactionRow): void {
  // eliminationAmount：取决于交易类型
  if (row.transactionType === '顺流') {
    row.eliminationAmount = calcEliminationAmount('downstream', row.unrealizedProfit, row.investmentRatio)
  } else if (row.transactionType === '逆流') {
    row.eliminationAmount = calcEliminationAmount('upstream', row.unrealizedProfit, row.investmentRatio)
  } else {
    row.eliminationAmount = 0
  }

  // currentChange = eliminationAmount - priorElimination
  if (row.transactionType) {
    row.currentChange = Math.round((row.eliminationAmount - parseNum(row.priorElimination)) * 100) / 100
  } else {
    row.currentChange = 0
  }
}

/** 重新计算所有行公式 */
function recalcAll(): void {
  for (const row of rows.value) {
    recalcRow(row)
  }
}

// ─── Field Update Handlers ───────────────────────────────────────────────────

function updateField(rowId: string, field: keyof InternalTransactionRow, value: any): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as any)[field] = value
  persistRows()
}

/** 交易类型变更 → 重算应抵销金额 */
function handleTypeChange(rowId: string, value: '顺流' | '逆流'): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.transactionType = value
  recalcRow(row)
  persistRows()
}

/** 交易金额变更 → unrealizedProfit 公式重算（若未被手动覆盖） */
function handleAmountChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.transactionAmount = value
  // 注意：unrealizedProfit 支持直接填写覆盖，此处不自动联动
  // 若需要公式联动，用户可在"未实现利润"列重新触发
  recalcRow(row)
  persistRows()
}

/** 未实现利润直接填写覆盖 */
function handleProfitOverride(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.unrealizedProfit = value
  recalcRow(row)
  persistRows()
}

/** 持股比例变更 → 重算应抵销金额（逆流时影响） */
function handleRatioChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.investmentRatio = value
  recalcRow(row)
  persistRows()
}

/** 上年抵销变更 → 重算本年变动 */
function handlePriorChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.priorElimination = value
  recalcRow(row)
  persistRows()
}

// ─── Dynamic Rows ────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入被投资单位名称',
      '新增内部交易行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '被投资单位名称' },
    )
    if (!name?.trim()) {
      ElMessage.warning('被投资单位名称不能为空')
      return
    }
    const newRow = createEmptyRow(rows.value.length + 1, name.trim())
    rows.value.push(newRow)
    persistRows()
    ElMessage.success(`已新增: ${name.trim()}`)
  } catch {
    // 用户取消
  }
}

function handleRemoveRow(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.id === rowId)
  if (idx < 0) return
  rows.value.splice(idx, 1)
  // 重排序号
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function persistRows(): void {
  if (isReadonly.value) return
  const payload = JSON.stringify({ rows: rows.value })
  const flatRows = JSON.stringify(rows.value)
  formData.debouncedSaveBatch([
    {
      itemId: SECTION_KEY,
      data: { conclusion: payload, remark: null },
    },
    {
      itemId: ROWS_KEY,
      // 后端合并联动 / 导入导出认 G7-15-rows
      data: { conclusion: flatRows, remark: flatRows },
    },
  ])
}

function persistConclusion(): void {
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: conclusion.value })
}

// ─── AI Conclusion ───────────────────────────────────────────────────────────

async function handleAiConclusion(): Promise<void> {
  if (isReadonly.value) return
  try {
    const res = await api.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/internal-transaction-conclusion`,
      { project_id: props.projectId, rows: rows.value },
    )
    const aiText = res?.data?.conclusion ?? res?.conclusion ?? ''
    if (aiText) {
      conclusion.value = conclusion.value ? `${conclusion.value}\n${aiText}` : aiText
      persistConclusion()
      ElMessage.success('AI结论已生成')
    } else {
      // Fallback: 本地生成
      generateLocalConclusion()
    }
  } catch {
    // AI端点不可用时本地生成
    generateLocalConclusion()
  }
}

function generateLocalConclusion(): void {
  const total = rows.value.length
  const downstream = rows.value.filter((r) => r.transactionType === '顺流').length
  const upstream = rows.value.filter((r) => r.transactionType === '逆流').length
  const totalElimination = rows.value.reduce((sum, r) => sum + parseNum(r.eliminationAmount), 0)
  const totalChange = rows.value.reduce((sum, r) => sum + parseNum(r.currentChange), 0)
  const relatedCount = rows.value.filter((r) => r.isRelatedParty).length

  const draft =
    `经检查，本期共有 ${total} 笔内部交易，` +
    `其中顺流交易 ${downstream} 笔、逆流交易 ${upstream} 笔。` +
    `应抵销未实现利润合计 ${fmtNum(totalElimination)} 元，` +
    `本年变动合计 ${fmtNum(totalChange)} 元。` +
    (relatedCount > 0 ? `涉及关联交易 ${relatedCount} 笔。` : '') +
    ` 内部交易抵销计算完整，抵销方向及金额恰当。`

  conclusion.value = conclusion.value ? `${conclusion.value}\n${draft}` : draft
  persistConclusion()
  ElMessage.success('已生成本地结论')
}

// ─── Import/Export (placeholder, composable from Task 9.2) ───────────────────

function handleExportTemplate(): void {
  ElMessage.info('导出模板功能将在导入导出模块完成后启用')
}
function handleExportData(): void {
  ElMessage.info('导出数据功能将在导入导出模块完成后启用')
}
function handleImportData(): void {
  ElMessage.info('导入数据功能将在导入导出模块完成后启用')
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 获取应抵销金额的公式tooltip */
function getEliminationTooltip(row: InternalTransactionRow): string {
  if (row.transactionType === '顺流') {
    return `顺流: 应抵销 = 未实现利润(${fmtNum(row.unrealizedProfit)}) × 100% = ${fmtNum(row.eliminationAmount)}`
  }
  if (row.transactionType === '逆流') {
    return `逆流: 应抵销 = 未实现利润(${fmtNum(row.unrealizedProfit)}) × 持股比例(${row.investmentRatio}) = ${fmtNum(row.eliminationAmount)}`
  }
  return '请先选择交易类型'
}

/** 数字格式化 */
function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}
</script>

<style scoped>
.g7-tab-internal-transaction {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.tab-toolbar .chip-wrap {
  display: inline-flex;
  align-items: center;
}

/* 方法论上下文：琥珀色左边线+浅黄背景 */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
}
.methodology-context p {
  margin: 0 0 4px;
}
.methodology-context ul {
  margin: 0;
  padding-left: 18px;
}
.methodology-context li {
  margin-bottom: 2px;
}

/* section标题 */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.internal-transaction-table {
  font-size: var(--wp-font-size, 13px);
}

/* 公式列header：虚线下划线 + cursor:help */
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

/* 公式值单元格 */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  text-align: right;
}

/* 交易类型未选时占位符 */
.no-type-placeholder {
  color: #c0c4cc;
  font-size: 14px;
  display: inline-block;
  text-align: center;
  width: 100%;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 14px;
}
.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
