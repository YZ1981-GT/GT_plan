<!--
  G7TabInvestmentCostTest.vue — G7-13 投资成本测试（68行×17列→2区段Tab+虚拟滚动）

  2区段Tab切换（el-segmented）：
  - Tab1: 初始计量(9列): 被投资单位|投资日期|合并/非合并(下拉)|支付对价|直接相关费用|初始投资成本(公式)|净资产FV|享有份额(公式)|差额(公式)
  - Tab2: 商誉计算+调整(8列): 被投资单位|差额性质(自动判断:正=商誉绿色/负=营业外蓝色)|会计处理|FV调整明细(textarea)|调整后净资产|调整后享有份额|审计结论(下拉)|索引

  方法论上下文区域（琥珀色左边线+浅黄背景：CAS2投资成本判断规则）
  68行虚拟滚动 + 行同步 + 动态行增删
  底部审计结论textarea(AI辅助 cost-test-conclusion) + details编制提示折叠
  公式列：虚线下划线 + cursor:help + tooltip显示公式来源

  Spec: .kiro/specs/g7-long-term-equity-method/ Task 6.1
  Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 7.4, 7.5
-->
<template>
  <div class="g7-tab-investment-cost-test">
    <!-- 方法论上下文区域（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p class="methodology-title">CAS2 投资成本判断规则：</p>
      <ul class="methodology-list">
        <li>初始投资成本 &gt; 享有可辨认净资产FV份额 → 差额确认为<strong>商誉</strong>（不调整）</li>
        <li>初始投资成本 &lt; 享有可辨认净资产FV份额 → 差额计入<strong>营业外收入</strong>（调整初始成本）</li>
        <li>被投资方净资产公允价值需逐项辨认、调整（资产评估/审计确认）</li>
      </ul>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实长期股权投资初始投资成本的计量，验证商誉或营业外收入的确认是否符合 CAS2。"
      class="objective-alert"
    />

    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-13 合营联营企业投资成本测试表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-button size="small" :disabled="isReadonly || syncingCross" :loading="syncingCross" @click="syncFromRelated">
          从关联表带入
        </el-button>
        <el-button size="small" :disabled="isReadonly || syncingToG714 || !rows.length" :loading="syncingToG714" @click="pushToG714">
          同步至G7-14
        </el-button>
        <el-dropdown trigger="click" size="small" :disabled="importExport.importing.value" @command="handleDropdownCommand">
          <el-button size="small" :loading="importExport.importing.value">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item v-if="!isReadonly" command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-13-cost-test')">💬复核</el-button>
      </div>
    </div>
    <input
      ref="fileInput"
      type="file"
      accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      style="display:none"
      @change="onFileSelected"
    />

    <!-- 工具栏：索引 chip + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G7-13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 区段Tab -->
    <el-alert
      v-if="validationIssues.length"
      :type="validationIssues.some(i => i.level === 'error') ? 'error' : 'warning'"
      :closable="false"
      class="validation-alert"
      show-icon
    >
      <template #title>
        校验提示（{{ validationIssues.length }}）
      </template>
      <ul class="validation-list">
        <li v-for="(issue, idx) in validationIssues.slice(0, 8)" :key="`${issue.code}-${idx}`">
          {{ issue.message }}
        </li>
        <li v-if="validationIssues.length > 8">…另有 {{ validationIssues.length - 8 }} 条</li>
      </ul>
    </el-alert>

    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 表格（单一实例，列按Tab切换，68行虚拟滚动） -->
    <el-table
      :data="rows"
      border
      size="small"
      max-height="580"
      highlight-current-row
      row-key="id"
      class="cost-test-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <el-table-column label="行索引" width="88" align="center" fixed>
        <template #default="{ row }">
          <span class="chip-wrap">
            <GtIndexChip :value="`wp:G7-13#${row.seq}`" :context-project-id="projectId" />
          </span>
        </template>
      </el-table-column>

        <el-table-column label="被投资单位" width="150" fixed>
        <template #default="{ row }">
          <span class="investee-name">{{ row.investeeName }}</span>
          <el-tag v-if="row.investmentRatio" size="small" type="info" class="ratio-tag">
            {{ (Number(row.investmentRatio) * 100).toFixed(2) }}%
          </el-tag>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 初始计量(9列，含序号+被投资单位共9列显示) ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="投资日期" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.investDate" size="small"
              type="date" value-format="YYYY-MM-DD" style="width:100%"
              @update:model-value="(v: string) => updateField(row.id, 'investDate', v)" />
            <span v-else>{{ row.investDate }}</span>
          </template>
        </el-table-column>

        <el-table-column label="合并/非合并" min-width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.mergeType" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'mergeType', v)">
              <el-option value="合并" label="合并" />
              <el-option value="非合并" label="非合并" />
            </el-select>
            <span v-else>{{ row.mergeType }}</span>
          </template>
        </el-table-column>

        <el-table-column label="支付对价" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.consideration" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'consideration', v)" />
            <span v-else>{{ fmtNum(row.consideration) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="直接相关费用" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.directCosts" size="small" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'directCosts', v)" />
            <span v-else>{{ fmtNum(row.directCosts) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="初始投资成本" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="初始投资成本 = 支付对价 + 直接相关费用" placement="top">
              <span class="formula-cell">{{ fmtNum(row.initialCost) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="净资产公允价值" min-width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.netAssetFairValue" size="small" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'netAssetFairValue', v)" />
            <span v-else>{{ fmtNum(row.netAssetFairValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="享有份额" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="享有份额 = 净资产公允价值 × 持股比例" placement="top">
              <span class="formula-cell">{{ fmtNum(row.shareOfNetAssets) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="差额" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="差额 = 初始投资成本 - 享有份额（正=商誉,负=营业外收入）" placement="top">
              <span class="formula-cell" :class="differenceClass(row.difference)">
                {{ fmtNum(row.difference) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 商誉计算+调整(8列，含被投资单位共8) ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="差额性质" min-width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.difference > 0" type="success" size="small">商誉</el-tag>
            <el-tag v-else-if="row.difference < 0" type="primary" size="small">营业外收入</el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>

        <el-table-column label="会计处理" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.accountingTreatment" size="small"
              @change="(v: string) => updateField(row.id, 'accountingTreatment', v)" />
            <span v-else>{{ row.accountingTreatment }}</span>
          </template>
        </el-table-column>

        <el-table-column label="FV调整明细" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" type="textarea" :model-value="row.fvAdjustmentDetail"
              :autosize="{ minRows: 1, maxRows: 3 }" size="small"
              @change="(v: string) => updateField(row.id, 'fvAdjustmentDetail', v)" />
            <span v-else class="multiline-cell">{{ row.fvAdjustmentDetail }}</span>
          </template>
        </el-table-column>

        <el-table-column label="调整后净资产" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.adjustedNetAssets" size="small"
              :controls="false" :precision="2" class="compact-num"
              @change="(v: number) => updateFieldWithRecalc(row.id, 'adjustedNetAssets', v)" />
            <span v-else>{{ fmtNum(row.adjustedNetAssets) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="调整后享有份额" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="调整后享有份额 = 调整后净资产 × 持股比例" placement="top">
              <span class="formula-cell">{{ fmtNum(row.adjustedShareOfNetAssets) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="审计结论" min-width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.auditConclusion" size="small" style="width:100%"
              @change="(v: string) => updateField(row.id, 'auditConclusion', v)">
              <el-option value="无差异" label="无差异" />
              <el-option value="存在差异-可接受" label="存在差异-可接受" />
              <el-option value="存在差异-需调整" label="存在差异-需调整" />
            </el-select>
            <span v-else>{{ row.auditConclusion }}</span>
          </template>
        </el-table-column>

        <el-table-column label="证据索引" min-width="140" align="center">
          <template #default="{ row }">
            <div class="index-cell">
              <GtIndexChip
                v-if="row.indexRef"
                :value="row.indexRef"
                :context-project-id="projectId"
              />
              <el-input
                v-if="!isReadonly"
                :model-value="row.indexRef"
                size="small"
                placeholder="评估报告/协议"
                @change="(v: string) => updateField(row.id, 'indexRef', v)"
              />
              <span v-else-if="!row.indexRef" class="text-muted">—</span>
            </div>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm :title="`确认删除「${row.investeeName}」?`" @confirm="removeRow(row.id)">
            <template #reference>
              <el-button type="danger" link size="small">✕</el-button>
            </template>
          </el-popconfirm>
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

    <!-- 底部：审计结论 el-card + AI辅助按钮 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAiConclusion">
            🤖 AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对投资成本测试结果的综合评价（商誉/营业外收入确认是否合理）..."
        @change="persistRows"
      />
    </el-card>

    <!-- 编制提示 details 折叠 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>初始投资成本 = 支付对价 + 直接相关费用（审计/律师/评估等）</li>
        <li>享有份额 = 被投资方可辨认净资产公允价值 × 投资方持股比例</li>
        <li>调整后享有份额 = 调整后净资产 × 持股比例（公式列；填调整后净资产后自动重算）</li>
        <li>差额为正（初始成本 > 享有份额）：差额确认为商誉，不调整初始投资成本</li>
        <li>差额为负（初始成本 < 享有份额）：差额计入营业外收入，同时调增初始投资成本</li>
        <li>合并取得的长期股权投资，初始投资成本按合并对价确定</li>
        <li>非合并取得的长期股权投资，支付的对价+直接费用均计入初始成本</li>
        <li>被投资方净资产公允价值需参照评估报告逐项辨认调整</li>
        <li>持股比例从 G7-4「从关联表带入」写入行内 investmentRatio（小数）</li>
        <li>净资产公允价值可从 G7-5 所有者权益/净资产带入（账面代理，需评估复核为 FV）</li>
        <li>「同步至G7-14」：正差额→商誉明细；负差额→廉价购买备查+说明；有调整后份额时写 FV</li>
        <li>负差额同步后可推送建议 AJE（借1511/贷6301）至 G7-3，仅草稿需复核</li>
        <li>持久化：G7-13-rows 扁平数组（IE/consol）+ remark 信封兼容旧存</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { extractG7AiText } from '../../composables/g7AiText'
/**
 * G7TabInvestmentCostTest — G7-13 投资成本测试
 * 持久化：G7-13-rows 扁平数组 + remark 信封；G7-13-conclusion
 */
import { ref, reactive, inject, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum } from '../../composables/useG7EquityMethodFormulaEngine'
import {
  G7_4_ROWS_KEY,
  G7_5_ROWS_KEY,
  G7_13_ROWS_KEY,
  G7_14_ROWS_KEY,
  G7_14_SECTION_KEY,
  applyInvestmentCostToG714Payload,
  loadEquityInvestees,
  parseChecklistJson,
} from '../../composables/g7EquityMethodCrossSheet'
import {
  buildBargainSuggestedAdjustments,
  createEmptyInvestmentCostRow,
  extractNetAssetFvFromG75,
  hydrateInvestmentCostRows,
  recalcInvestmentCostRow,
  validateInvestmentCostRows,
} from '../../composables/g7InvestmentCostModel'
import { emitG7SourceRowsSaved } from '../../composables/g7DisclosureCrossSheet'
import GtIndexChip from '../../GtIndexChip.vue'
import { useG7EquityMethodFormData } from '../../composables/useG7EquityMethodFormData'
import type { InvestmentCostTestRow } from '../../composables/useG7EquityMethodFormData'
import { useG7EquityMethodImportExport } from '../../composables/useG7EquityMethodImportExport'
import { pushSuggestedAdjustmentsToG73 } from './g7EquityMethodPushG73'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => props.readonly ?? false)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

type TabKey = 'tab1' | 'tab2'
const activeTab = ref<TabKey>('tab1')
const segmentOptions = [
  { label: '初始计量(9)', value: 'tab1' },
  { label: '商誉计算+调整(8)', value: 'tab2' },
]

const selectedRowIndex = ref(-1)
function onCurrentChange(row: InvestmentCostTestRow | null) {
  if (row) selectedRowIndex.value = rows.findIndex(r => r.id === row.id)
}

const rows = reactive<InvestmentCostTestRow[]>([])
const conclusion = ref('')
const syncingCross = ref(false)
const syncingToG714 = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const auditFormData = useG7EquityMethodFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const importExport = useG7EquityMethodImportExport({
  wpId: computed(() => props.wpId),
})

const AUDIT_NOTE_KEY = 'G7-13-audit-note'
const ROWS_KEY = G7_13_ROWS_KEY
const CONCLUSION_KEY = 'G7-13-conclusion'
const auditNote = ref('')
const validationIssues = computed(() => validateInvestmentCostRows(rows))

function saveAuditNote(val: string): void {
  if (isReadonly.value) return
  auditNote.value = val
  auditFormData.debouncedSave(AUDIT_NOTE_KEY, { remark: val, conclusion: null })
}

function persistRows(): void {
  if (isReadonly.value) return
  const flatRows = JSON.stringify([...rows])
  const pagePayload = JSON.stringify({ rows: [...rows], conclusion: conclusion.value })
  if (typeof (auditFormData as any).debouncedSaveBatch === 'function') {
    auditFormData.debouncedSaveBatch([
      { itemId: ROWS_KEY, data: { conclusion: flatRows, remark: pagePayload } },
      { itemId: CONCLUSION_KEY, data: { conclusion: conclusion.value, remark: null } },
    ])
  } else {
    auditFormData.debouncedSave(ROWS_KEY, { conclusion: flatRows, remark: pagePayload })
    auditFormData.debouncedSave(CONCLUSION_KEY, { conclusion: conclusion.value, remark: null })
  }
  try {
    emitG7SourceRowsSaved({
      projectId: props.projectId,
      wpId: props.wpId,
      itemIds: [ROWS_KEY],
    })
  } catch { /* ignore */ }
}

function parseSaved(raw: unknown): unknown {
  if (raw == null || raw === '') return null
  if (typeof raw === 'object') return raw
  try { return JSON.parse(String(raw)) } catch { return null }
}

function hydrateRows(raw: unknown): boolean {
  if (raw == null) return false
  const list = hydrateInvestmentCostRows(raw)
  if (!list.length) return false
  rows.length = 0
  rows.push(...list)
  const parsed = typeof raw === 'string' ? parseSaved(raw) : raw
  if (typeof (parsed as any)?.conclusion === 'string') {
    conclusion.value = (parsed as any).conclusion
  }
  return true
}

function loadRowsFromChecklist(): boolean {
  const saved = auditFormData.data.value.get(ROWS_KEY)
  if (hydrateRows(parseSaved(saved?.conclusion)) || hydrateRows(parseSaved(saved?.remark))) {
    const c = auditFormData.data.value.get(CONCLUSION_KEY)
    if (c?.conclusion) conclusion.value = String(c.conclusion)
    return true
  }
  return false
}

function recalcRow(row: InvestmentCostTestRow): void {
  recalcInvestmentCostRow(row)
}

function createEmptyRow(seq: number, investeeName: string): InvestmentCostTestRow {
  return createEmptyInvestmentCostRow(seq, investeeName)
}

function updateField(id: string, field: keyof InvestmentCostTestRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value
  persistRows()
}

function updateFieldWithRecalc(id: string, field: keyof InvestmentCostTestRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value ?? 0
  recalcRow(row)
  persistRows()
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '被投资单位名称不能为空',
      inputValidator: (val: string) => {
        if (!val?.trim()) return '被投资单位名称不能为空'
        if (rows.some(r => r.investeeName === val.trim())) return `「${val.trim()}」已存在`
        return true
      },
    })
    if (value?.trim()) {
      rows.push(createEmptyRow(rows.length + 1, value.trim()))
      persistRows()
      ElMessage.success(`已添加「${value.trim()}」`)
    }
  } catch { /* cancel */ }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx < 0) return
  rows.splice(idx, 1)
  rows.forEach((r, i) => { r.seq = i + 1 })
  persistRows()
}

function generateLocalConclusion(): void {
  const total = rows.length
  const goodwill = rows.filter(r => parseNum(r.difference) > 0)
  const bargain = rows.filter(r => parseNum(r.difference) < 0)
  conclusion.value =
    `经检查，共测试 ${total} 家合营/联营企业投资成本。` +
    `其中 ${goodwill.length} 家初始成本大于享有份额（确认为商誉），` +
    `${bargain.length} 家初始成本小于享有份额（廉价购买/营业外收入）。` +
    '投资成本计量及差额性质判断符合 CAS2。'
  persistRows()
  ElMessage.success('已生成本地结论草稿')
}

async function handleAiConclusion() {
  if (isReadonly.value) return
  try {
    const res = await api.post(
      `/api/workpapers/${props.wpId}/g7-equity-method/ai/cost-test-conclusion`,
      {
        existingContent: conclusion.value,
        relatedContext: {
          sheet: 'G7-13',
          rowCount: rows.length,
          goodwillCount: rows.filter(r => parseNum(r.difference) > 0).length,
          bargainCount: rows.filter(r => parseNum(r.difference) < 0).length,
          rows: rows.slice(0, 20).map(r => ({
            investeeName: r.investeeName,
            initialCost: r.initialCost,
            shareOfNetAssets: r.shareOfNetAssets,
            difference: r.difference,
            differenceNature: r.differenceNature,
            investmentRatio: r.investmentRatio,
            auditConclusion: r.auditConclusion,
          })),
        },
      },
    )
    const text = extractG7AiText(res?.data)
    if (text) {
      conclusion.value = conclusion.value ? `${conclusion.value}\n${text}` : text
      persistRows()
      ElMessage.success('AI结论已生成')
    } else {
      generateLocalConclusion()
    }
  } catch {
    generateLocalConclusion()
  }
}

async function handleDropdownCommand(command: string) {
  if (command === 'template') await importExport.exportTemplate('G7-13')
  else if (command === 'export') await importExport.exportData('G7-13')
  else if (command === 'import') fileInput.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await importExport.importData('G7-13', file)
  if (!result) return
  await auditFormData.load()
  if (loadRowsFromChecklist()) {
    for (const r of rows) recalcRow(r)
    persistRows()
    ElMessage.success(`导入完成，已刷新 ${rows.length} 行`)
  } else {
    ElMessage.warning('导入完成，但未解析到行数据')
  }
}

async function syncFromRelated(): Promise<void> {
  if (isReadonly.value || syncingCross.value) return
  syncingCross.value = true
  try {
    await auditFormData.loadResponses()
    const investees = loadEquityInvestees(
      auditFormData.data.value.get(G7_4_ROWS_KEY)?.conclusion
      ?? props.htmlData?.responses_snapshot?.[G7_4_ROWS_KEY]?.conclusion
      ?? props.htmlData?.basicInfo,
    )
    if (!investees.length) {
      ElMessage.warning('未找到 G7-4 合营/联营企业，请先维护基本信息')
      return
    }
    let added = 0
    let ratioFilled = 0
    let fvFilled = 0
    for (const inv of investees) {
      let row = rows.find(r =>
        (inv.investeeId && r.investeeId && r.investeeId === inv.investeeId)
        || r.investeeName === inv.name,
      )
      if (!row) {
        row = createEmptyRow(rows.length + 1, inv.name)
        rows.push(row)
        added++
      }
      if (inv.investeeId && !row.investeeId) row.investeeId = inv.investeeId
      if (inv.investmentRatio != null && inv.investmentRatio > 0) {
        if (!parseNum(row.investmentRatio)) ratioFilled++
        row.investmentRatio = inv.investmentRatio
      }
      recalcRow(row)
    }

    const g75Raw =
      auditFormData.data.value.get(G7_5_ROWS_KEY)?.conclusion
      ?? props.htmlData?.responses_snapshot?.[G7_5_ROWS_KEY]?.conclusion
    const fvEntries = extractNetAssetFvFromG75(g75Raw)
    for (const entry of fvEntries) {
      const row = rows.find(r =>
        (entry.investeeId && r.investeeId && r.investeeId === entry.investeeId)
        || r.investeeName === entry.investeeName,
      )
      if (!row) continue
      if (entry.investeeId && !row.investeeId) row.investeeId = entry.investeeId
      // 仅空值时填入账面净资产作 FV 代理，不覆盖已评估数
      if (!parseNum(row.netAssetFairValue) && Math.abs(entry.bookNetAssets) > 0.005) {
        row.netAssetFairValue = entry.bookNetAssets
        if (!parseNum(row.adjustedNetAssets)) row.adjustedNetAssets = entry.bookNetAssets
        fvFilled++
        recalcRow(row)
      }
    }

    rows.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
    const fvHint = fvFilled
      ? `；G7-5 补净资产代理 ${fvFilled} 项（账面≠FV，请评估复核）`
      : (fvEntries.length ? '；G7-5 有净资产但行内已有 FV 未覆盖' : '')
    ElMessage.success(`已从关联表带入：新增 ${added} 家，补比例 ${ratioFilled} 项${fvHint}`)
  } catch {
    ElMessage.error('关联表带入失败')
  } finally {
    syncingCross.value = false
  }
}

async function pushBargainAjeToG73(): Promise<void> {
  const lines = buildBargainSuggestedAdjustments([...rows])
  if (!lines.length) {
    ElMessage.info('当前无廉价购买（负差额）行，无需推送')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将写入 ${lines.length} 行建议分录至 G7-3（借长期股权投资 / 贷营业外收入；仅替换同源【G7-13】廉价购买草稿），是否继续？`,
      '推送廉价购买建议分录',
      { type: 'warning', confirmButtonText: '推送至 G7-3', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const result = await pushSuggestedAdjustmentsToG73({
      projectId: props.projectId,
      currentWpId: props.wpId,
      lines,
    })
    if (result.ok) ElMessage.success(result.message)
    else ElMessage.warning(result.message)
  } catch {
    ElMessage.error('推送 G7-3 失败，请确认主表底稿已生成')
  }
}

async function pushToG714(): Promise<void> {
  if (isReadonly.value || syncingToG714.value || !rows.length) return
  syncingToG714.value = true
  try {
    await auditFormData.loadResponses()
    const g714Raw = parseChecklistJson(
      auditFormData.data.value.get(G7_14_SECTION_KEY)?.conclusion
      ?? auditFormData.data.value.get(G7_14_ROWS_KEY)?.conclusion
      ?? props.htmlData?.responses_snapshot?.[G7_14_SECTION_KEY]?.conclusion,
    )
    const result = applyInvestmentCostToG714Payload(g714Raw, [...rows])
    if (!result.ok || !result.payload) {
      ElMessage.warning(result.message)
      return
    }
    await ElMessageBox.confirm(
      `${result.message}。将覆盖 G7-14 中同源【G7-13】商誉/FV 明细，是否继续？`,
      '同步至 G7-14',
      { type: 'warning', confirmButtonText: '确认覆盖', cancelButtonText: '取消' },
    )
    const payloadStr = JSON.stringify(result.payload)
    if (typeof (auditFormData as any).debouncedSaveBatch === 'function') {
      auditFormData.debouncedSaveBatch([
        { itemId: G7_14_SECTION_KEY, data: { conclusion: payloadStr, remark: null } },
        { itemId: G7_14_ROWS_KEY, data: { conclusion: payloadStr, remark: null } },
      ])
    } else {
      auditFormData.debouncedSave(G7_14_SECTION_KEY, { conclusion: payloadStr, remark: null })
      auditFormData.debouncedSave(G7_14_ROWS_KEY, { conclusion: payloadStr, remark: null })
    }
    ElMessage.success(result.message)

    const bargainRows = rows.filter(r => parseNum(r.difference) < -0.005)
    if (bargainRows.length) {
      const names = bargainRows.slice(0, 3).map(r => r.investeeName).join('、')
      const more = bargainRows.length > 3 ? `等${bargainRows.length}家` : ''
      try {
        await ElMessageBox.confirm(
          `其中 ${bargainRows.length} 家为廉价购买（${names}${more}）。`
          + '请复核：①营业外收入是否入账 ②初始成本是否调增。'
          + '可一键推送建议 AJE（借1511/贷6301）至 G7-3。',
          '廉价购买后续动作',
          {
            type: 'info',
            distinguishCancelAndClose: true,
            confirmButtonText: '推送建议分录至 G7-3',
            cancelButtonText: '稍后处理',
          },
        )
        await pushBargainAjeToG73()
      } catch {
        /* 稍后处理 / 关闭 */
      }
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('同步至 G7-14 失败')
  } finally {
    syncingToG714.value = false
  }
}

function differenceClass(diff: number): string {
  if (diff > 0) return 'diff-goodwill'
  if (diff < 0) return 'diff-bargain'
  return ''
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

onMounted(async () => {
  await auditFormData.load()
  const n = auditFormData.data.value.get(AUDIT_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark

  const snapshot = props.htmlData?.responses_snapshot?.[ROWS_KEY]
  if (
    !loadRowsFromChecklist()
    && !hydrateRows(parseSaved(snapshot?.conclusion))
    && !hydrateRows(parseSaved(snapshot?.remark))
    && !hydrateRows(props.htmlData?.investmentCostTest)
    && !hydrateRows((props.htmlData as any)?.rows)
  ) {
    // empty start
  }

  const c = auditFormData.data.value.get(CONCLUSION_KEY)
  if (c?.conclusion && !conclusion.value) conclusion.value = String(c.conclusion)

  // 兼容旧 htmlData.basicInfo 比例
  const legacy = props.htmlData?.basicInfo
  if (Array.isArray(legacy)) {
    for (const b of legacy) {
      const name = String(b.investeeName || '').trim()
      const ratio = parseNum(b.investmentRatio ?? b.shareholdingRatio)
      if (!name || !ratio) continue
      const row = rows.find(r => r.investeeName === name)
      if (row && !parseNum(row.investmentRatio)) {
        row.investmentRatio = Math.abs(ratio) > 1.0001 ? ratio / 100 : ratio
        recalcRow(row)
      }
    }
  }
})

/** @deprecated 保留兼容；优先行内 investmentRatio */
function updateRatioMap(map: Record<string, number>) {
  for (const [name, ratio] of Object.entries(map || {})) {
    const row = rows.find(r => r.investeeName === name)
    if (row) {
      row.investmentRatio = Math.abs(ratio) > 1.0001 ? ratio / 100 : ratio
      recalcRow(row)
    }
  }
  if (rows.length) persistRows()
}

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) return
  hydrateRows(data.investmentCostTest || data)
}

function getData(): { rows: InvestmentCostTestRow[]; conclusion: string } {
  return { rows: [...rows], conclusion: conclusion.value }
}

defineExpose({ getData, loadFromHtmlData, persistRows, updateRatioMap })
</script>

<style scoped>
.g7-tab-investment-cost-test { padding: 12px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.7;
}
.methodology-title { margin: 0 0 6px; font-weight: 600; color: #92400e; }
.methodology-list { margin: 0; padding-left: 18px; color: #78350f; }
.methodology-list li { margin-bottom: 2px; }

/* 顶部工具栏 */
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }

/* 区段Tab */
.segment-bar { margin-bottom: 12px; }
.validation-alert { margin-bottom: 12px; }
.validation-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }

/* 表格 */
.cost-test-table { font-size: var(--wp-font-size, 13px); }
.compact-num { width: 100%; }
.investee-name { font-weight: 500; color: #303133; }
.ratio-tag { margin-left: 6px; vertical-align: middle; }
.index-cell { display: flex; flex-direction: column; gap: 4px; align-items: stretch; }
.multiline-cell { white-space: pre-wrap; word-break: break-all; font-size: 12px; line-height: 1.4; }
.text-muted { color: #c0c4cc; }

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* 差额颜色 */
.diff-goodwill { color: #67c23a; font-weight: 500; }
.diff-bargain { color: #409eff; font-weight: 500; }

/* 审计结论卡片 */
.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }

/* 编制提示 */
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
