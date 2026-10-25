<template>
  <div class="s17-non-recurring-detail">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实非经常性损益各项目的识别、归类与金额准确，确认合并与个别报表口径的一致性，并与营业外收支等科目核对相符。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ 非经常性损益明细（S17-1 审定表 / S17-2 合并 / S17-3 个别） ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>{{ sheetTitle }}</span>
          <div class="header-actions">
            <el-segmented
              v-model="activeView"
              :options="viewOptions"
              size="small"
            />
            <!-- 后端能力尚未提供：入口保留可见但不可用。 -->
            <el-button size="small" disabled>导入导出（开发中）</el-button>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              :loading="saving"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleOpenReview('s17-detail', sheetTitle)">
              复核
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="handleAiAssist">
              🤖 AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <!-- 编制提示 -->
      <details class="compile-hint">
        <summary>编制提示</summary>
        <div class="methodology-context">
          <p>本表用于记录和审核非经常性损益各项目明细。</p>
          <p>非经常性损益：与公司正常经营业务无直接关系，或虽与正常经营业务相关，但由于其性质特殊和偶发性，影响报表使用人对公司经营成果和盈利能力做出正常判断的各项收入、支出。</p>
          <p>S17-1 为审定汇总表；S17-2 为合并报表口径；S17-3 为个别报表口径。</p>
          <p>注意与 S15（每股收益/净资产收益率）、S20（收入扣除）底稿的交叉勾稽。</p>
        </div>
      </details>

      <!-- ─── S17-1 审定表视图 ─── -->
      <div v-if="activeView === 'adjudication'">
        <el-table
          :data="adjudicationRows"
          border
          size="small"
          style="width: 100%; font-size: 13px"
          show-summary
          :summary-method="getAdjSummary"
          :cell-class-name="cellClassName"
        >
          <el-table-column prop="itemName" label="非经常性损益项目" min-width="220" />
          <el-table-column prop="currentAmount" label="本期金额" min-width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly && row.editable"
                v-model="row.currentAmount"
                size="small"
                style="width: 100%"
                @change="markDirty"
              />
              <span v-else>{{ fmt(row.currentAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="priorAmount" label="上期金额" min-width="130" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="上期比较数据">{{ fmt(row.priorAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="taxImpact" label="所得税影响" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="参见 S17-21 所得税影响计算">
                {{ fmt(row.taxImpact) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="netAmount" label="税后净额" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell audited-amount" title="税后净额 = 本期金额 - 所得税影响">
                {{ fmt(row.netAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="indexRef" label="索引号" width="100" align="center">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
              <span v-else class="text-placeholder">—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- ─── S17-2 合并报表口径视图 ─── -->
      <div v-if="activeView === 'consolidated'">
        <el-table
          :data="consolidatedRows"
          border
          size="small"
          style="width: 100%; font-size: 13px"
          show-summary
          :summary-method="getDetailSummary"
          :cell-class-name="cellClassName"
        >
          <el-table-column type="index" label="序号" width="55" align="center" />
          <el-table-column prop="itemName" label="非经常性损益项目" min-width="250" />
          <el-table-column prop="amount" label="金额" min-width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly && row.editable"
                v-model="row.amount"
                size="small"
                style="width: 100%"
                @change="markDirty"
              />
              <span v-else>{{ fmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="source" label="来源科目" min-width="150">
            <template #default="{ row }">
              <span>{{ row.source || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="basis" label="认定依据" min-width="180">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.basis"
                size="small"
                placeholder="认定为非经常性的依据"
                @change="markDirty"
              />
              <span v-else>{{ row.basis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="crossRef" label="勾稽" width="130" align="center">
            <template #default="{ row }">
              <div class="cross-ref-chips">
                <GtIndexChip v-if="row.crossRefS15" :value="row.crossRefS15" />
                <GtIndexChip v-if="row.crossRefS20" :value="row.crossRefS20" />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="auditResult" label="审核结果" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                v-model="row.auditResult"
                size="small"
                placeholder="—"
                @change="markDirty"
              >
                <el-option label="确认" value="confirmed" />
                <el-option label="调整" value="adjusted" />
                <el-option label="剔除" value="excluded" />
              </el-select>
              <el-tag v-else :type="resultTagType(row.auditResult)" size="small">
                {{ resultLabel(row.auditResult) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- ─── S17-3 个别报表口径视图 ─── -->
      <div v-if="activeView === 'individual'">
        <el-table
          :data="individualRows"
          border
          size="small"
          style="width: 100%; font-size: 13px"
          show-summary
          :summary-method="getDetailSummary"
          :cell-class-name="cellClassName"
        >
          <el-table-column type="index" label="序号" width="55" align="center" />
          <el-table-column prop="itemName" label="非经常性损益项目" min-width="250" />
          <el-table-column prop="amount" label="金额" min-width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!isReadonly && row.editable"
                v-model="row.amount"
                size="small"
                style="width: 100%"
                @change="markDirty"
              />
              <span v-else>{{ fmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="source" label="来源科目" min-width="150">
            <template #default="{ row }">
              <span>{{ row.source || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="basis" label="认定依据" min-width="180">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.basis"
                size="small"
                placeholder="认定依据"
                @change="markDirty"
              />
              <span v-else>{{ row.basis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="auditResult" label="审核结果" width="100" align="center">
            <template #default="{ row }">
              <el-select
                v-if="!isReadonly"
                v-model="row.auditResult"
                size="small"
                placeholder="—"
                @change="markDirty"
              >
                <el-option label="确认" value="confirmed" />
                <el-option label="调整" value="adjusted" />
                <el-option label="剔除" value="excluded" />
              </el-select>
              <el-tag v-else :type="resultTagType(row.auditResult)" size="small">
                {{ resultLabel(row.auditResult) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 动态行 -->
      <div v-if="!isReadonly" class="row-actions">
        <el-button size="small" type="primary" plain @click="addDetailRow">+ 新增项目</el-button>
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审核结论</span>
          <div class="header-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAiConclusion">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对非经常性损益各项目的认定和金额确认情况的总体结论..."
        @change="markDirty"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * S17NonRecurringDetailSheet.vue — S17-1/S17-2/S17-3 非经常性损益明细
 *
 * 功能：
 * - 三个视图切换：S17-1 审定表(41×6) / S17-2 合并(42×8) / S17-3 个别(33×6)
 * - 非经常性损益项目明细记录与审核
 * - GtIndexChip 跨底稿引用（与 S15/S20 交叉勾稽）
 * - 动态行新增
 * - 审核结果：确认/调整/剔除
 * - readonly 禁止编辑
 * - 13px 字体 + AI 辅助
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.3
 * Requirements: 8.2, 8.3
 */
import { ref, computed, inject, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { fmtAmount } from '@/utils/formatters'
import { sChecklistItemIds, type SChecklistComponentType } from './sChecklistItemIds'
import { loadSChecklistHtmlData } from './sChecklistRenderData'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

const COMPONENT_TYPE = 's17-nonrecurring-detail' as const

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

const props = defineProps<{
  wpId: string
  projectId: string
  readonly?: boolean
  sheetName?: string
  componentType?: SChecklistComponentType
  htmlData?: Record<string, any> | null
}>()
const isReadonly = computed(() => props.readonly === true)

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {}
)

function handleOpenReview(sectionId: string, sectionLabel: string) {
  openReviewDialog(sectionId, sectionLabel)
}

// ─── 视图切换 ────────────────────────────────────────────────────────────────

const viewOptions = [
  { label: '审定表S17-1', value: 'adjudication' },
  { label: '合并S17-2', value: 'consolidated' },
  { label: '个别S17-3', value: 'individual' },
] as const

type S17View = (typeof viewOptions)[number]['value']

/** render-config 提供的 canonical sheet_name → S17 detail view。 */
const S17_VIEW_BY_SHEET_NAME: Record<string, S17View> = {
  'S17-1': 'adjudication',
  'S17-2': 'consolidated',
  'S17-3': 'individual',
  '审定表S17-1': 'adjudication',
  '审核表（合并）S17-2': 'consolidated',
  '审核表（个别报表）S17-3': 'individual',
}

function resolveS17View(sheetName?: string): S17View {
  return S17_VIEW_BY_SHEET_NAME[sheetName || ''] ?? 'adjudication'
}

const activeView = ref<S17View>(resolveS17View(props.sheetName))

const sheetTitle = computed(() => {
  if (activeView.value === 'adjudication') return '审定表 S17-1 — 非经常性损益汇总'
  if (activeView.value === 'consolidated') return '审核表（合并）S17-2 — 非经常性损益明细'
  return '审核表（个别报表）S17-3 — 非经常性损益明细'
})

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface AdjRow {
  id: string; itemName: string; currentAmount: number; priorAmount: number
  taxImpact: number; netAmount: number; indexRef: string; editable: boolean
}

interface DetailRow {
  id: string; itemName: string; amount: number; source: string
  basis: string; crossRefS15: string; crossRefS20: string
  auditResult: string; editable: boolean
}

const adjudicationRows = ref<AdjRow[]>([])
const consolidatedRows = ref<DetailRow[]>([])
const individualRows = ref<DetailRow[]>([])
const conclusion = ref('')
const saving = ref(false)
const isDirty = ref(false)

// ─── 默认非经常性损益项目 ────────────────────────────────────────────────────

const DEFAULT_NR_ITEMS = [
  { itemName: '非流动资产处置损益', source: '营业外收入/营业外支出', crossRefS15: 'S15', crossRefS20: 'S20' },
  { itemName: '越权审批或无正式批准文件的税收返还、减免', source: '其他收益', crossRefS15: '', crossRefS20: '' },
  { itemName: '计入当期损益的政府补助', source: '其他收益/营业外收入', crossRefS15: 'S15', crossRefS20: '' },
  { itemName: '计入当期损益的对非金融企业收取的资金占用费', source: '财务费用', crossRefS15: '', crossRefS20: '' },
  { itemName: '委托他人投资或管理资产的损益', source: '投资收益', crossRefS15: 'S15', crossRefS20: '' },
  { itemName: '各种形式的政府补助', source: '其他收益', crossRefS15: '', crossRefS20: '' },
  { itemName: '债务重组损益', source: '营业外收入/营业外支出', crossRefS15: 'S15', crossRefS20: 'S20' },
  { itemName: '非货币性资产交换损益', source: '营业外收入/营业外支出', crossRefS15: 'S15', crossRefS20: 'S20' },
  { itemName: '企业取得子公司、联营企业及合营企业的投资成本小于取得投资时应享有被投资单位可辨认净资产公允价值产生的收益', source: '营业外收入', crossRefS15: '', crossRefS20: '' },
  { itemName: '同一控制下企业合并产生的子公司期初至合并日的当期净损益', source: '—', crossRefS15: '', crossRefS20: '' },
  { itemName: '与公司正常经营业务无关的或有事项产生的损益', source: '营业外收入/营业外支出', crossRefS15: '', crossRefS20: 'S20' },
  { itemName: '除同公司正常经营业务相关的有效套期保值业务外的持有损益', source: '公允价值变动收益', crossRefS15: '', crossRefS20: '' },
  { itemName: '单独进行减值测试的应收款项减值准备转回', source: '信用减值损失', crossRefS15: '', crossRefS20: '' },
  { itemName: '对外委托贷款取得的损益', source: '利息收入', crossRefS15: '', crossRefS20: '' },
  { itemName: '采用公允价值模式进行后续计量的投资性房地产公允价值变动产生的损益', source: '公允价值变动收益', crossRefS15: '', crossRefS20: '' },
]

// ─── 辅助 ────────────────────────────────────────────────────────────────────

function resultLabel(r: string): string {
  return r === 'confirmed' ? '确认' : r === 'adjusted' ? '调整' : r === 'excluded' ? '剔除' : '—'
}

function resultTagType(r: string): '' | 'success' | 'warning' | 'danger' {
  return r === 'confirmed' ? 'success' : r === 'adjusted' ? 'warning' : r === 'excluded' ? 'danger' : ''
}

function markDirty() { isDirty.value = true }

function cellClassName({ column }: any) {
  if (['本期金额', '税后净额', '金额'].includes(column.label)) return 'formula-column'
  return ''
}

function addDetailRow() {
  if (isReadonly.value) return
  const target = activeView.value === 'consolidated' ? consolidatedRows : individualRows
  const idx = target.value.length
  target.value.push({
    id: `s17-detail-${Date.now()}-${idx}`,
    itemName: '',
    amount: 0,
    source: '',
    basis: '',
    crossRefS15: '',
    crossRefS20: '',
    auditResult: '',
    editable: true,
  })
  markDirty()
}

// ─── 合计 ────────────────────────────────────────────────────────────────────

function getAdjSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '合计'; return }
    const prop = col.property
    if (['currentAmount', 'priorAmount', 'taxImpact', 'netAmount'].includes(prop)) {
      sums[i] = fmt(data.reduce((s: number, r: any) => s + (Number(r[prop]) || 0), 0))
    } else { sums[i] = '' }
  })
  return sums
}

function getDetailSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = '合计'; return }
    if (col.property === 'amount') {
      sums[i] = fmt(data.reduce((s: number, r: any) => s + (Number(r.amount) || 0), 0))
    } else { sums[i] = '' }
  })
  return sums
}

// ─── AI ──────────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中，将自动核对非经常性损益项目的完整性与准确性')
}

function handleAiConclusion() {
  ElMessage.info('AI将根据审核结果自动生成非经常性损益审核结论')
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave() {
  if (isReadonly.value || saving.value) return
  saving.value = true
  try {
    const payload = {
      adjudication_rows: adjudicationRows.value,
      consolidated_rows: consolidatedRows.value,
      individual_rows: individualRows.value,
      conclusion: conclusion.value,
    }
    await http.put(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      {
        project_id: props.projectId,
        items: [{
          item_id: sChecklistItemIds['s17-nonrecurring-detail'],
          conclusion: null,
          remark: JSON.stringify(payload),
        }],
      }
    )
    isDirty.value = false
    ElMessage.success('非经常性损益明细已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败：${err?.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}

// ─── 加载 ────────────────────────────────────────────────────────────────────

async function loadData() {
  try {
    const htmlData = await loadSChecklistHtmlData({
      wpId: props.wpId,
      htmlData: props.htmlData,
      componentType: props.componentType ?? COMPONENT_TYPE,
      sheetName: props.sheetName,
    })

    if (htmlData?.adjudication_rows?.length) {
      adjudicationRows.value = htmlData.adjudication_rows
    } else {
      adjudicationRows.value = DEFAULT_NR_ITEMS.map((item, idx) => ({
        id: `s17-1-${idx}`,
        itemName: item.itemName,
        currentAmount: 0,
        priorAmount: 0,
        taxImpact: 0,
        netAmount: 0,
        indexRef: '',
        editable: true,
      }))
    }

    if (htmlData?.consolidated_rows?.length) {
      consolidatedRows.value = htmlData.consolidated_rows
    } else {
      consolidatedRows.value = DEFAULT_NR_ITEMS.map((item, idx) => ({
        id: `s17-2-${idx}`,
        itemName: item.itemName,
        amount: 0,
        source: item.source,
        basis: '',
        crossRefS15: item.crossRefS15,
        crossRefS20: item.crossRefS20,
        auditResult: '',
        editable: true,
      }))
    }

    if (htmlData?.individual_rows?.length) {
      individualRows.value = htmlData.individual_rows
    } else {
      individualRows.value = DEFAULT_NR_ITEMS.slice(0, 10).map((item, idx) => ({
        id: `s17-3-${idx}`,
        itemName: item.itemName,
        amount: 0,
        source: item.source,
        basis: '',
        crossRefS15: '',
        crossRefS20: '',
        auditResult: '',
        editable: true,
      }))
    }

    if (htmlData?.conclusion) {
      conclusion.value = htmlData.conclusion
    }
  } catch {
    // 降级使用默认数据
    adjudicationRows.value = DEFAULT_NR_ITEMS.map((item, idx) => ({
      id: `s17-1-${idx}`,
      itemName: item.itemName,
      currentAmount: 0, priorAmount: 0, taxImpact: 0, netAmount: 0,
      indexRef: '', editable: true,
    }))
    consolidatedRows.value = DEFAULT_NR_ITEMS.map((item, idx) => ({
      id: `s17-2-${idx}`,
      itemName: item.itemName,
      amount: 0, source: item.source, basis: '',
      crossRefS15: item.crossRefS15, crossRefS20: item.crossRefS20,
      auditResult: '', editable: true,
    }))
    individualRows.value = DEFAULT_NR_ITEMS.slice(0, 10).map((item, idx) => ({
      id: `s17-3-${idx}`,
      itemName: item.itemName,
      amount: 0, source: item.source, basis: '',
      crossRefS15: '', crossRefS20: '',
      auditResult: '', editable: true,
    }))
  }
}

watch(
  () => [props.sheetName, props.componentType, props.htmlData],
  () => {
    activeView.value = resolveS17View(props.sheetName)
    void loadData()
  },
)

onMounted(() => { loadData() })
</script>

<style scoped>
.s17-non-recurring-detail { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.compile-hint { margin-bottom: 12px; font-size: var(--wp-font-size, 13px); }
.compile-hint summary { cursor: pointer; color: #909399; font-size: 12px; margin-bottom: 8px; }
.methodology-context { padding: 10px 14px; border-left: 4px solid #e6a23c; background-color: #fdf6ec; font-size: var(--wp-font-size, 13px); line-height: 1.7; color: #606266; }
.methodology-context p { margin: 4px 0; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.audited-amount { font-weight: 600; color: #303133; }
.text-placeholder { color: #c0c4cc; }
.row-actions { margin-top: 12px; }
.cross-ref-chips { display: flex; gap: 4px; flex-wrap: wrap; justify-content: center; }
:deep(.formula-column) { background-color: #fafafa; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
</style>
