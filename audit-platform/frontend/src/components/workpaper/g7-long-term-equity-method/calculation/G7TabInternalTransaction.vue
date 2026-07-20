<!--
  G7TabInternalTransaction.vue — G7-15 内部交易抵销测算表

  核心特色：顺流/逆流差异化抵销逻辑
  - 顺流交易(投资方→被投资方)：应抵销 = 未实现利润 × 100%（全额抵消）
  - 逆流交易(被投资方→投资方)：应抵销 = 未实现利润 × 持股比例（按份额）
  - 交易类型未选时应抵销列显示"—"
  - 未实现利润 = 交易金额 × 毛利率（可手填覆盖）

  列：被投资单位(G7-4下拉)|交易类型|交易内容|交易金额|毛利率|未实现利润|
      持股比例|应抵销金额|上年抵销|本年变动|抵销分录|是否关联交易|审计结论|索引|备注

  Spec: .kiro/specs/g7-long-term-equity-method/
  Task: 6.3 / 9.2
  Requirements: 6.1, 6.2, 6.3, 7.3, 7.4
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
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || syncingToG714"
          :loading="syncingToG714"
          @click="syncToG714"
        >
          同步至 G7-14
        </el-button>
        <el-dropdown
          trigger="click"
          size="small"
          :disabled="importExport.importing.value"
          @command="handleDropdownCommand"
        >
          <el-button size="small" :loading="importExport.importing.value">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
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

    <!-- 主表 -->
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

      <!-- 1. 被投资单位（G7-4 下拉，带 investeeId） -->
      <el-table-column label="被投资单位" min-width="150" fixed>
        <template #default="{ row }">
          <el-select
            :model-value="row.investeeId || row.investeeName"
            size="small"
            filterable
            allow-create
            default-first-option
            clearable
            placeholder="选择或输入"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: string) => handleInvesteeChange(row.id, v)"
          >
            <el-option
              v-for="opt in investeeOptions"
              :key="opt.investeeId || opt.name"
              :label="opt.name"
              :value="opt.investeeId || opt.name"
            />
          </el-select>
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

      <!-- 5. 毛利率 -->
      <el-table-column label="毛利率" width="100" align="right">
        <template #header>
          <span class="formula-header" title="小数 0~1，如 0.2 表示 20%">毛利率</span>
        </template>
        <template #default="{ row }">
          <el-input-number
            :model-value="row.grossMargin"
            size="small"
            :controls="false"
            :precision="4"
            :step="0.01"
            :min="0"
            :max="1"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => handleMarginChange(row.id, v ?? 0)"
          />
        </template>
      </el-table-column>

      <!-- 6. 未实现利润(公式 OR 直接填写覆盖) -->
      <el-table-column label="未实现利润" min-width="140" align="right">
        <template #header>
          <span class="formula-header" title="= 交易金额 × 毛利率（支持直接填写覆盖）">
            未实现利润
          </span>
        </template>
        <template #default="{ row }">
          <div class="profit-cell">
            <el-input-number
              :model-value="row.unrealizedProfit"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @change="(v: number | undefined) => handleProfitOverride(row.id, v ?? 0)"
            />
            <el-button
              v-if="row.unrealizedProfitManual && !isReadonly"
              size="small"
              link
              type="primary"
              title="清除手工覆盖，按金额×毛利率重算"
              @click="handleClearProfitManual(row.id)"
            >
              按公式
            </el-button>
          </div>
        </template>
      </el-table-column>

      <!-- 7. 持股比例 -->
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

      <!-- 8. 应抵销金额(公式，核心差异化列) -->
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

      <!-- 9. 上年抵销 -->
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

      <!-- 10. 本年变动(公式) -->
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

      <!-- 11. 抵销分录 -->
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

      <!-- 12. 是否关联交易 -->
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

      <!-- 13. 审计结论 -->
      <el-table-column label="审计结论" width="110" align="center">
        <template #default="{ row }">
          <el-select
            :model-value="row.auditConclusion"
            size="small"
            clearable
            placeholder="—"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'auditConclusion', v)"
          >
            <el-option label="合理" value="合理" />
            <el-option label="基本合理" value="基本合理" />
            <el-option label="不合理" value="不合理" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 14. 索引 -->
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

      <!-- 15. 备注 -->
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => updateField(row.id, 'remark', v)"
          />
        </template>
      </el-table-column>

      <!-- 删除 -->
      <el-table-column label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon
            v-if="!isReadonly"
            class="delete-icon"
            @click="handleRemoveRow(row.id)"
          >
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
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="auditNote"
        :disabled="isReadonly"
        placeholder="记录内部交易识别、毛利率来源、抵销分录索引等说明…"
        @input="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="内部交易抵销审计结论…"
        @input="(v: string) => { conclusion = v; persistConclusion() }"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>被投资单位优先从 G7-4 合营/联营下拉选择，自动带入持股比例与 investeeId</li>
        <li>未实现利润可由公式计算（交易金额×毛利率），也可直接填写覆盖</li>
        <li>顺流全额抵销、逆流按持股比例抵销；未选交易类型时「应抵销/本年变动」显示 —</li>
        <li>G7-15 的本年变动将联动 G7-14 权益法测算表中的「内部交易抵销」列（可用「同步至 G7-14」）</li>
      </ul>
    </details>

    <input ref="fileInput" class="hidden-file-input" type="file" accept=".xlsx" @change="onFileSelected">
  </div>
</template>

<script setup lang="ts">
import { extractG7AiText } from '../../composables/g7AiText'
/**
 * G7TabInternalTransaction — G7-15 内部交易抵销测算表
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/
 * Task: 6.3 / 9.2
 *
 * Requirements: 6.1, 6.2, 6.3, 7.3, 7.4
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum } from '../../composables/useG7EquityMethodFormulaEngine'
import {
  G7_4_ROWS_KEY,
  G7_15_ROWS_KEY,
  G7_15_SECTION_KEY,
  applyInternalElimToG714Payload,
  buildG714DualWriteItems,
  loadEquityInvestees,
  makeG714ConclusionGetter,
  parseChecklistJson,
  resolveG714PayloadFromChecklist,
  stampLastCrossSheetSync,
  type G7EquityInvesteeOption,
} from '../../composables/g7EquityMethodCrossSheet'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { InternalTransactionRow } from '../../composables/useG7EquityMethodFormData'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import {
  createEmptyInternalTransactionRow,
  clearUnrealizedProfitManual,
  hydrateInternalTransactionRows,
  recalcInternalTransactionRow,
} from './g7InternalTransactionModel'
import { emitG7SourceRowsSaved } from '../../composables/g7DisclosureCrossSheet'
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

const formData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const importExport = useG7EquityMethodImportExport({
  wpId: computed(() => props.wpId),
})

const SECTION_KEY = G7_15_SECTION_KEY
const ROWS_KEY = G7_15_ROWS_KEY
const CONCLUSION_KEY = 'G7-15-conclusion'
const AUDIT_NOTE_KEY = 'G7-15-audit-note'

const rows = ref<InternalTransactionRow[]>([])
const conclusion = ref('')
const auditNote = ref('')
const investeeOptions = ref<G7EquityInvesteeOption[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const syncingToG714 = ref(false)

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  formData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

function refreshInvesteeOptions(): void {
  const raw =
    formData.data.value.get(G7_4_ROWS_KEY)?.conclusion
    ?? props.htmlData?.responses_snapshot?.[G7_4_ROWS_KEY]?.conclusion
  investeeOptions.value = loadEquityInvestees(raw)
}

function hydrateRows(raw: unknown): boolean {
  const hydrated = hydrateInternalTransactionRows(raw)
  if (!hydrated.length) return false
  rows.value = hydrated
  return true
}

function parseSaved(raw: unknown): unknown {
  if (raw == null || raw === '') return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(String(raw)) } catch { return null }
}

function loadRowsFromChecklist(): boolean {
  const sectionSaved = parseSaved(formData.data.value.get(SECTION_KEY)?.conclusion)
  const rowsSaved = parseSaved(
    formData.data.value.get(ROWS_KEY)?.conclusion
    ?? formData.data.value.get(ROWS_KEY)?.remark,
  )
  return hydrateRows(sectionSaved) || hydrateRows(rowsSaved)
}

onMounted(async () => {
  await formData.load()
  refreshInvesteeOptions()

  const snapshotSection = parseSaved(props.htmlData?.responses_snapshot?.[SECTION_KEY]?.conclusion)
  const snapshotRows = parseSaved(
    props.htmlData?.responses_snapshot?.[ROWS_KEY]?.conclusion
    ?? props.htmlData?.responses_snapshot?.[ROWS_KEY]?.remark,
  )

  if (
    !loadRowsFromChecklist()
    && !hydrateRows(snapshotSection)
    && !hydrateRows(snapshotRows)
    && !hydrateRows(props.htmlData?.internalTransaction)
    && !hydrateRows((props.htmlData as any)?.rows)
  ) {
    rows.value = Array.from({ length: 5 }, (_, i) => createEmptyInternalTransactionRow(i + 1))
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

function createEmptyRow(seq: number, investeeName = '', investeeId = ''): InternalTransactionRow {
  return createEmptyInternalTransactionRow(seq, investeeName, investeeId)
}

/** 对单行重新计算公式列 */
function recalcRow(row: InternalTransactionRow): void {
  recalcInternalTransactionRow(row)
}

function recalcAll(): void {
  for (const row of rows.value) {
    recalcRow(row)
  }
}

function updateField(rowId: string, field: keyof InternalTransactionRow, value: any): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  ;(row as any)[field] = value
  persistRows()
}

function handleInvesteeChange(rowId: string, value: string): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  const v = String(value ?? '').trim()
  if (!v) {
    row.investeeId = undefined
    row.investeeName = ''
    persistRows()
    return
  }
  const byId = investeeOptions.value.find((o) => o.investeeId && o.investeeId === v)
  const byName = investeeOptions.value.find((o) => o.name === v)
  const matched = byId || byName
  if (matched) {
    row.investeeId = matched.investeeId || undefined
    row.investeeName = matched.name
    if (matched.investmentRatio != null && matched.investmentRatio > 0 && !parseNum(row.investmentRatio)) {
      row.investmentRatio = matched.investmentRatio
      recalcRow(row)
    }
  } else {
    // allow-create：自由文本，无 ID
    row.investeeId = undefined
    row.investeeName = v
  }
  persistRows()
}

function handleTypeChange(rowId: string, value: '顺流' | '逆流'): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.transactionType = value
  recalcRow(row)
  persistRows()
}

function handleAmountChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.transactionAmount = value
  recalcRow(row)
  persistRows()
}

function handleMarginChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.grossMargin = value
  recalcRow(row)
  persistRows()
}

function handleProfitOverride(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.unrealizedProfit = value
  row.unrealizedProfitManual = true
  recalcRow(row)
  persistRows()
}

function handleClearProfitManual(rowId: string): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  clearUnrealizedProfitManual(row)
  persistRows()
}

function handleRatioChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.investmentRatio = value
  recalcRow(row)
  persistRows()
}

function handlePriorChange(rowId: string, value: number): void {
  const row = rows.value.find((r) => r.id === rowId)
  if (!row) return
  row.priorElimination = value
  recalcRow(row)
  persistRows()
}

async function handleAddRow(): Promise<void> {
  if (investeeOptions.value.length) {
    try {
      const { value } = await ElMessageBox.prompt(
        '选择或输入被投资单位（可从 G7-4 合营/联营中选择）',
        '新增内部交易行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: investeeOptions.value.map((o) => o.name).slice(0, 5).join(' / ') || '被投资单位',
        },
      )
      const name = String(value ?? '').trim()
      if (!name) {
        ElMessage.warning('被投资单位名称不能为空')
        return
      }
      const matched = investeeOptions.value.find(
        (o) => o.name === name || o.investeeId === name,
      )
      const newRow = createEmptyRow(
        rows.value.length + 1,
        matched?.name || name,
        matched?.investeeId || '',
      )
      if (matched?.investmentRatio) {
        newRow.investmentRatio = matched.investmentRatio
      }
      rows.value.push(newRow)
      persistRows()
      ElMessage.success(`已新增: ${newRow.investeeName}`)
    } catch {
      // 取消
    }
    return
  }

  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入被投资单位名称（建议先维护 G7-4）',
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
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

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
      data: { conclusion: flatRows, remark: flatRows },
    },
  ])
  try {
    emitG7SourceRowsSaved({
      projectId: props.projectId,
      wpId: props.wpId,
      itemIds: [SECTION_KEY, ROWS_KEY],
    })
  } catch { /* ignore */ }
}

function persistConclusion(): void {
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: conclusion.value })
}

async function handleAiConclusion(): Promise<void> {
  if (isReadonly.value) return
  try {
    const res = await api.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/internal-transaction-conclusion`,
      {
        existingContent: conclusion.value,
        relatedContext: {
          sheet: 'G7-15',
          rowCount: rows.value.length,
          downstreamCount: rows.value.filter((r) => r.transactionType === '顺流').length,
          upstreamCount: rows.value.filter((r) => r.transactionType === '逆流').length,
          totalElimination: rows.value.reduce((s, r) => s + parseNum(r.eliminationAmount), 0),
          totalCurrentChange: rows.value.reduce((s, r) => s + parseNum(r.currentChange), 0),
          relatedPartyCount: rows.value.filter((r) => r.isRelatedParty).length,
          rows: rows.value.map((r) => ({
            investeeId: r.investeeId,
            investeeName: r.investeeName,
            transactionType: r.transactionType,
            transactionAmount: r.transactionAmount,
            grossMargin: r.grossMargin,
            unrealizedProfit: r.unrealizedProfit,
            investmentRatio: r.investmentRatio,
            eliminationAmount: r.eliminationAmount,
            priorElimination: r.priorElimination,
            currentChange: r.currentChange,
            isRelatedParty: r.isRelatedParty,
            auditConclusion: r.auditConclusion,
          })),
        },
      },
    )
    const aiText = extractG7AiText(res?.data)
    if (aiText) {
      conclusion.value = conclusion.value ? `${conclusion.value}\n${aiText}` : aiText
      persistConclusion()
      ElMessage.success('AI结论已生成')
    } else {
      generateLocalConclusion()
    }
  } catch {
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

async function handleDropdownCommand(command: string): Promise<void> {
  if (command === 'template') await importExport.exportTemplate('G7-15')
  else if (command === 'export') await importExport.exportData('G7-15')
  else if (command === 'import') fileInput.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importExport.importData('G7-15', file)
  if (!result) return
  await formData.load()
  refreshInvesteeOptions()
  if (loadRowsFromChecklist()) {
    ElMessage.success(`导入完成，已刷新 ${rows.value.length} 行`)
    try {
      await ElMessageBox.confirm(
        '导入已完成。是否将本年变动同步至 G7-14「内部交易抵销」列？',
        '同步至 G7-14',
        { confirmButtonText: '同步', cancelButtonText: '稍后', type: 'info' },
      )
      await syncToG714({ quiet: true })
    } catch {
      // 用户选择稍后
    }
  } else {
    ElMessage.warning('导入完成，但未解析到行数据')
  }
}

/** 将 G7-15 本年变动汇总写入 G7-14.internalTransactionAdj */
async function syncToG714(opts?: { quiet?: boolean }): Promise<boolean> {
  if (isReadonly.value || syncingToG714.value) return false
  const named = rows.value.filter((r) => r.investeeName || r.investeeId)
  if (!named.length) {
    ElMessage.warning('请先填写被投资单位与抵销数据')
    return false
  }
  syncingToG714.value = true
  try {
    await formData.load()
    const g714Raw = resolveG714PayloadFromChecklist(
      makeG714ConclusionGetter(formData.data.value, props.htmlData?.responses_snapshot),
    )
    const result = applyInternalElimToG714Payload(g714Raw, { rows: rows.value })
    if (!result.ok || !result.payload) {
      ElMessage.warning(result.message || '同步失败')
      return false
    }
    if (!opts?.quiet) {
      try {
        await ElMessageBox.confirm(
          `${result.message}。确认覆盖 G7-14「内部交易抵销」列？`,
          '同步至 G7-14',
          { confirmButtonText: '确认覆盖', cancelButtonText: '取消', type: 'warning' },
        )
      } catch {
        return false
      }
    }
    stampLastCrossSheetSync(
      result.payload,
      ['G7-15'],
      Array.isArray(result.payload.groups) ? result.payload.groups.length : 0,
    )
    formData.debouncedSaveBatch(buildG714DualWriteItems(result.payload))
    ElMessage.success(result.message)
    return true
  } finally {
    syncingToG714.value = false
  }
}

function getEliminationTooltip(row: InternalTransactionRow): string {
  if (row.transactionType === '顺流') {
    return `顺流: 应抵销 = 未实现利润(${fmtNum(row.unrealizedProfit)}) × 100% = ${fmtNum(row.eliminationAmount)}`
  }
  if (row.transactionType === '逆流') {
    return `逆流: 应抵销 = 未实现利润(${fmtNum(row.unrealizedProfit)}) × 持股比例(${row.investmentRatio}) = ${fmtNum(row.eliminationAmount)}`
  }
  return '请先选择交易类型'
}

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
.internal-transaction-table {
  font-size: var(--wp-font-size, 13px);
}
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  text-align: right;
}
.no-type-placeholder {
  color: #c0c4cc;
  font-size: 14px;
  display: inline-block;
  text-align: center;
  width: 100%;
}
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}
.conclusion-card {
  margin-top: 14px;
}
.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
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
.hidden-file-input {
  display: none;
}
.profit-cell {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
}
</style>
