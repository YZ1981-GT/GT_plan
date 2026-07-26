<template>
  <div class="h3-tab-transfer-review">
    <!-- 编制提示（对齐 Excel 底部5条准则摘要） -->
    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><strong>1. 转换认定：</strong>须有确凿证据——董事会等类似机构书面决议 + 用途实际改变（如自用→出租）。</p>
        <p><strong>2. 转换日：</strong>一般为租赁开始日；空置建筑物准备出租时，若决议明确出租意图且短期内不变，可用决议日。</p>
        <p><strong>3. 公允模式前提：</strong>同时满足活跃房地产市场 + 能持续取得同类可比市场价格信息。</p>
        <p><strong>4. 公允价值确定：</strong>优先活跃市场报价 → 近期交易价格调整 → 未来租金/现金流现值。</p>
        <p><strong>5. 后续计量：</strong>公允价值模式不计提折旧/摊销，资产负债表日按公允价值调整账面。</p>
        <p><strong>6. 部分转换：</strong>若仅转换资产的一部分，须在「转换比例%」列填写实际比例，系统自动按比例计算入账金额。</p>
        <p><strong>7. 存货→投资（CAS3第14条）：</strong>差额（公允-账面）一律计入当期损益，不进OCI。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产转换的时点、金额与会计处理恰当性；验证各方向差额处理合规（OCI/损益）；转出=转入平衡。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-6" :context-project-id="projectId" /></span>
      <el-tag size="small" :type="measurementModel === 'fair_value' ? 'warning' : 'info'">
        {{ measurementModel === 'fair_value' ? '公允价值模式' : '成本模式' }}
      </el-tag>
      <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
      <el-tag v-if="hasImbalance" size="small" type="danger">⚠ {{ totalSummary.imbalanceCount }} 笔转出≠转入</el-tag>
      <el-tag v-if="totalSummary.materialityWarnings.length" size="small" type="warning">
        ⚠ {{ totalSummary.materialityWarnings.length }} 笔超重要性水平
      </el-tag>
    </div>

    <!-- 汇总仪表板 -->
    <div class="summary-bar">
      <div class="summary-item">
        <span class="label">H1转入（自用→投资）</span>
        <span class="value">{{ fmtNum(totalSummary.fromH1) }}</span>
      </div>
      <div class="summary-item">
        <span class="label">H1转出（投资→自用）</span>
        <span class="value">{{ fmtNum(totalSummary.toH1) }}</span>
      </div>
      <div class="summary-item">
        <span class="label">H2转入（在建→投资）</span>
        <span class="value">{{ fmtNum(totalSummary.fromH2) }}</span>
      </div>
      <div class="summary-item">
        <span class="label">存货转入</span>
        <span class="value">{{ fmtNum(totalSummary.fromInventory) }}</span>
      </div>
      <div class="summary-item">
        <span class="label">净转入</span>
        <span class="value" :class="{ 'text-danger': totalSummary.netTransfer < 0 }">{{ fmtNum(totalSummary.netTransfer) }}</span>
      </div>
      <div v-if="totalSummary.transferRatio > 0" class="summary-item">
        <span class="label">占资产总额</span>
        <span class="value" :class="{ 'text-danger': totalSummary.transferRatio > 0.1 }">
          {{ (totalSummary.transferRatio * 100).toFixed(1) }}%
        </span>
      </div>
      <template v-if="measurementModel === 'fair_value'">
        <div class="summary-item">
          <span class="label">OCI合计</span>
          <span class="value">{{ fmtNum(totalSummary.ociTotal) }}</span>
        </div>
        <div class="summary-item">
          <span class="label">损益影响</span>
          <span class="value" :class="{ 'text-danger': totalSummary.plTotal < 0 }">{{ fmtNum(totalSummary.plTotal) }}</span>
        </div>
      </template>
    </div>

    <!-- 重要性预警面板 -->
    <el-card v-if="totalSummary.materialityWarnings.length" shadow="never" class="materiality-card">
      <template #header>
        <div class="card-header">
          <span>⚠ 重要性预警（{{ totalSummary.materialityWarnings.length }} 笔超阈值）</span>
          <span class="meta-inputs">
            <span class="meta-label">重要性水平：</span>
            <el-input-number
              v-model="materialityThreshold"
              :min="0" :step="10000" :controls="false"
              size="small" style="width:120px"
              :disabled="isReadonly"
              @change="saveMeta"
            />
            <span class="meta-label" style="margin-left:12px">资产总额：</span>
            <el-input-number
              v-model="assetTotal"
              :min="0" :step="100000" :controls="false"
              size="small" style="width:140px"
              :disabled="isReadonly"
              @change="saveMeta"
            />
          </span>
        </div>
      </template>
      <el-table :data="totalSummary.materialityWarnings" size="small" border>
        <el-table-column prop="assetName" label="资产名称" min-width="140" />
        <el-table-column prop="direction" label="方向" width="120">
          <template #default="{ row }">{{ DIRECTION_LABELS[row.direction] }}</template>
        </el-table-column>
        <el-table-column prop="amount" label="转换金额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="text-danger font-bold">{{ fmtNum(row.amount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 重要性参数设置（无预警时也显示） -->
    <div v-else class="materiality-params">
      <span class="meta-label">重要性水平：</span>
      <el-input-number
        v-model="materialityThreshold"
        :min="0" :step="10000" :controls="false"
        size="small" style="width:120px"
        :disabled="isReadonly"
        @change="saveMeta"
      />
      <span class="meta-label" style="margin-left:12px">资产总额（用于计算转换比率）：</span>
      <el-input-number
        v-model="assetTotal"
        :min="0" :step="100000" :controls="false"
        size="small" style="width:140px"
        :disabled="isReadonly"
        @change="saveMeta"
      />
    </div>

    <!-- 方法论上下文 -->
    <div class="method-context">
      <div class="context-bar">
        <strong>CAS3 第12-15条：</strong>转换日为用途实际改变日。
        <template v-if="measurementModel === 'fair_value'">
          自用→投资：公允&gt;账面→OCI，公允&lt;账面→当期损益；投资→自用以公允价值入账；
          在建/存货→投资以公允价值入账，差额→当期损益。
        </template>
        <template v-else>
          成本模式下以账面净值 × 转换比例转换，不产生公允价值变动损益。
        </template>
        <strong style="margin-left:8px">H3-5联动：</strong>转换数据自动同步至增减检查表，再由 H3-5 驱动 H1/H2 联动。
      </div>
    </div>

    <!-- (A) 自用 → 投资 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(A) 自用 → 投资性房地产</span>
          <span class="action-btns">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('selfToInvest')">+ 新增</el-button>
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H1-1 审定表')">→ H1固定资产</el-tag>
          </span>
        </div>
      </template>
      <TransferDirectionTable
        :rows="selfToInvestRows"
        direction="selfToInvest"
        :measurement-model="measurementModel"
        :is-readonly="isReadonly"
        @change="onRowChange"
        @remove="removeRow"
      />
    </el-card>

    <!-- (B) 投资 → 自用 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(B) 投资性房地产 → 自用</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('investToSelf')">+ 新增</el-button>
        </div>
      </template>
      <TransferDirectionTable
        :rows="investToSelfRows"
        direction="investToSelf"
        :measurement-model="measurementModel"
        :is-readonly="isReadonly"
        @change="onRowChange"
        @remove="removeRow"
      />
    </el-card>

    <!-- (C) 在建 → 投资 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(C) 在建工程 → 投资性房地产</span>
          <span class="action-btns">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('cipToInvest')">+ 新增</el-button>
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H2-1 审定表')">→ H2在建工程</el-tag>
          </span>
        </div>
      </template>
      <TransferDirectionTable
        :rows="cipToInvestRows"
        direction="cipToInvest"
        :measurement-model="measurementModel"
        :is-readonly="isReadonly"
        @change="onRowChange"
        @remove="removeRow"
      />
    </el-card>

    <!-- (D) 存货 → 投资（CAS3 第14条） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(D) 存货 → 投资性房地产 <el-tag size="small" type="warning" style="margin-left:6px">CAS3第14条</el-tag></span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow('inventoryToInvest')">+ 新增</el-button>
        </div>
      </template>
      <TransferDirectionTable
        :rows="inventoryToInvestRows"
        direction="inventoryToInvest"
        :measurement-model="measurementModel"
        :is-readonly="isReadonly"
        @change="onRowChange"
        @remove="removeRow"
      />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-6')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-6')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：转换时点判定依据（董事会决议/用途改变）、部分转换比例合理性、差额处理（OCI/损益）、转出=转入验证、与H1/H2勾稽、存货转入CAS3第14条核查。"
        :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>四、审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="A、转换时点与金额处理恰当、转出转入平衡。B、除下列事项外未见异常。C、转换处理存在重大问题，不可确认。"
        :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>

    <!-- 勾稽 H1/H2 互转 -->
    <el-card shadow="never" style="margin-top:16px">
      <template #header>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span style="font-weight:600;font-size:13px">勾稽 H1/H2 互转</span>
          <div style="display:flex;gap:8px;align-items:center">
            <el-tag v-if="transferReconcileStatus === 'ok'" type="success" size="small">一致</el-tag>
            <el-tag v-else-if="transferReconcileStatus === 'warning'" type="warning" size="small">存在差异</el-tag>
            <el-tag v-else type="info" size="small">对方数据不可用</el-tag>
            <el-button size="small" :loading="reconcileLoading" @click="loadTransferReconcile">勾稽 H1/H2</el-button>
          </div>
        </div>
      </template>
      <el-table v-if="transferReconcileData" :data="transferReconcileTableRows" border size="small" style="font-size:12px">
        <el-table-column prop="direction" label="方向" width="180" />
        <el-table-column label="H3 金额" align="right" width="140">
          <template #default="{ row }">{{ fmtR(row.h3Value) }}</template>
        </el-table-column>
        <el-table-column label="对方金额" align="right" width="140">
          <template #default="{ row }">{{ row.counterValue != null ? fmtR(row.counterValue) : '—' }}</template>
        </el-table-column>
        <el-table-column label="差异" align="right" width="120">
          <template #default="{ row }">
            <span :style="{ color: row.diff != null && Math.abs(row.diff) > 1 ? 'var(--el-color-warning)' : '' }">
              {{ row.diff != null ? fmtR(row.diff) : '—' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div style="margin-top:8px;display:flex;gap:8px">
        <GtIndexChip value="wp:H1" :context-project-id="projectId" />
        <GtIndexChip value="wp:H2" :context-project-id="projectId" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabTransferReview.vue — H3-6 互转审核表
 * 四方向（含存货→投资）+ 转换比例接入公式 + 字段分离 + 重要性预警 + H3-5联动
 */
import { ref, computed, inject, toRef, onMounted, defineComponent, h } from 'vue'
import { ElInput, ElInputNumber, ElSelect, ElOption, ElButton, ElTag, ElTable, ElTableColumn } from 'element-plus'
import { useH3TransferReview, CATEGORY_LABELS } from '../../composables/useH3TransferReview'
import type { TransferDirection, H3TransferRow, AssetCategory } from '../../composables/useH3TransferReview'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import { pullH1TransferForH3, pullH2TransferForH3, buildH3TransferReconcile } from '../../composables/h3TransferReconcile'
import type { TransferReconcileResult } from '../../composables/h3TransferReconcile'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const DIRECTION_LABELS: Record<TransferDirection, string> = {
  selfToInvest: '自用→投资',
  investToSelf: '投资→自用',
  cipToInvest: '在建→投资',
  inventoryToInvest: '存货→投资',
}

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel: 'cost' | 'fair_value'
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: toRef(props, 'measurementModel') as any,
})

const {
  rows, selfToInvestRows, investToSelfRows, cipToInvestRows, inventoryToInvestRows,
  hasImbalance, totalSummary,
  materialityThreshold, assetTotal, saveMeta,
  addRow: addTransferRow, updateTransferRow, removeRow: removeTransferRow,
} = useH3TransferReview({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
  measurementModel: toRef(props, 'measurementModel') as any,
})

const NOTE_KEY = 'H3-6-audit-note'
const CONCLUSION_KEY = 'H3-6-audit-conclusion'

// ─── 勾稽 H1/H2 互转 ────────────────────────────────────────────────────────
const reconcileLoading = ref(false)
const transferReconcileData = ref<TransferReconcileResult | null>(null)
const transferReconcileStatus = computed(() => transferReconcileData.value?.status ?? 'unavailable')
const transferReconcileTableRows = computed(() => {
  const d = transferReconcileData.value
  if (!d) return []
  return [
    { direction: '自用→投资(从H1转入)', h3Value: d.h3FromH1, counterValue: d.h1DisposalToInvest, diff: d.diffFromH1 },
    { direction: '投资→自用(转出到H1)', h3Value: d.h3ToH1, counterValue: d.h1AdditionFromInvest, diff: d.diffToH1 },
    { direction: '在建→投资(从H2转入)', h3Value: d.h3FromH2, counterValue: d.h2CipToInvest, diff: d.diffFromH2 },
  ]
})

async function loadTransferReconcile() {
  reconcileLoading.value = true
  try {
    const h1Data = await pullH1TransferForH3(props.projectId)
    const h2Data = await pullH2TransferForH3(props.projectId)
    const h3Summary = {
      fromH1: totalSummary.value?.fromH1 ?? 0,
      toH1: totalSummary.value?.toH1 ?? 0,
      fromH2: totalSummary.value?.fromH2 ?? 0,
    }
    transferReconcileData.value = buildH3TransferReconcile(h3Summary, h1Data, h2Data)
  } catch {
    transferReconcileData.value = null
  } finally {
    reconcileLoading.value = false
  }
}

function fmtR(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function addRow(direction: TransferDirection) { addTransferRow(direction) }
function removeRow(rowId: string) { removeTransferRow(rowId) }

function onRowChange(direction: string, row: H3TransferRow) {
  updateTransferRow(direction, 0, row)
  // 注意：联动已在 composable 的 _persist → _syncToH35 中自动完成，无需此处重复发送
}

function fmtNum(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}
function openReview(section: string) { openReviewDialog(section) }

// ─── 内联子表组件（按方向 + 计量模式动态渲染列） ───────────────────────────
const TransferDirectionTable = defineComponent({
  name: 'TransferDirectionTable',
  props: {
    rows: { type: Array as () => H3TransferRow[], required: true },
    direction: { type: String as () => TransferDirection, required: true },
    measurementModel: { type: String, required: true },
    isReadonly: { type: Boolean, default: false },
  },
  emits: ['change', 'remove'],
  setup(p, { emit: e }) {
    const isFair = computed(() => p.measurementModel === 'fair_value')

    const allCategories: { value: AssetCategory; label: string }[] = Object.entries(CATEGORY_LABELS)
      .map(([value, label]) => ({ value: value as AssetCategory, label }))

    function onField(row: H3TransferRow) { e('change', p.direction, row) }

    function numInput(row: H3TransferRow, field: keyof H3TransferRow, title?: string) {
      return h(ElInput, {
        modelValue: row[field] as number,
        size: 'small', disabled: p.isReadonly, type: 'number', title,
        'onUpdate:modelValue': (v: string) => { (row as any)[field] = Number(v) || 0; onField(row) },
      })
    }

    function textInput(row: H3TransferRow, field: keyof H3TransferRow, placeholder?: string) {
      return h(ElInput, {
        modelValue: row[field] as string,
        size: 'small', disabled: p.isReadonly, placeholder,
        'onUpdate:modelValue': (v: string) => { (row as any)[field] = v; onField(row) },
      })
    }

    function formulaCell(value: number, title: string, danger = false) {
      return h('span', {
        class: ['formula-value', danger && value < 0 ? 'text-danger' : ''],
        title,
      }, fmtNum(value))
    }

    function verifyTag(row: H3TransferRow) {
      const ok = Math.abs(row.transferOut - row.transferIn) < 0.01
      return h(ElTag, { type: ok ? 'success' : 'danger', size: 'small' }, () => ok ? '✓' : '✗')
    }

    return () => {
      const cols: any[] = [
        // 固定基础列
        h(ElTableColumn, { prop: 'assetCategory', label: '类别', width: 110, fixed: true }, {
          default: ({ row }: { row: H3TransferRow }) => h(ElSelect, {
            modelValue: row.assetCategory, size: 'small', disabled: p.isReadonly,
            'onUpdate:modelValue': (v: AssetCategory) => { row.assetCategory = v; onField(row) },
          }, () => allCategories.map((c) => h(ElOption, { key: c.value, label: c.label, value: c.value }))),
        }),
        h(ElTableColumn, { prop: 'assetName', label: '名称', minWidth: 110, fixed: true }, {
          default: ({ row }: { row: H3TransferRow }) => textInput(row, 'assetName'),
        }),
        h(ElTableColumn, { prop: 'conversionMethod', label: '转换方式', width: 100 }, {
          default: ({ row }: { row: H3TransferRow }) => textInput(row, 'conversionMethod'),
        }),
        h(ElTableColumn, { prop: 'transferDate', label: '转换日', width: 110 }, {
          default: ({ row }: { row: H3TransferRow }) => textInput(row, 'transferDate', 'YYYY-MM-DD'),
        }),
        // 转换比例（接入公式）
        h(ElTableColumn, { prop: 'conversionRatio', label: '比例%', width: 72, align: 'right' }, {
          default: ({ row }: { row: H3TransferRow }) => h(ElInputNumber, {
            modelValue: row.conversionRatio, size: 'small', disabled: p.isReadonly,
            min: 0.01, max: 100, precision: 2, controls: false,
            'onUpdate:modelValue': (v: number | undefined) => { row.conversionRatio = v ?? 100; onField(row) },
          }),
        }),
      ]

      // 转出方（自用/在建/存货）原始价值 ①②③④
      if (p.direction !== 'investToSelf') {
        cols.push(h(ElTableColumn, { label: '转出方转换日价值' }, () => [
          h(ElTableColumn, { label: '①原值', minWidth: 90, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'originalValue', '原值'),
          }),
          h(ElTableColumn, { label: '②折旧/摊销', minWidth: 90, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'accumulatedDepreciation', '折旧'),
          }),
          h(ElTableColumn, { label: '③减值', minWidth: 80, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'impairmentProvision', '减值'),
          }),
          h(ElTableColumn, { label: '④净值', minWidth: 90, align: 'right', className: 'formula-col' }, {
            default: ({ row }: { row: H3TransferRow }) => formulaCell(row.netValue, '④=①-②-③'),
          }),
          h(ElTableColumn, { label: '④×比例', minWidth: 90, align: 'right', className: 'formula-col' }, {
            default: ({ row }: { row: H3TransferRow }) => formulaCell(row.selfBookValue, '④×转换比例/100，用于公允模式OCI/PL计算'),
          }),
        ]))
      }

      // 投资方（成本模式）⑤⑥⑦⑧
      if (!isFair.value || p.direction === 'investToSelf') {
        cols.push(h(ElTableColumn, { label: '投资性房地产（成本模式）' }, () => [
          h(ElTableColumn, { label: '⑤原值', minWidth: 90, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'investOriginal', '原值'),
          }),
          h(ElTableColumn, { label: '⑥折旧', minWidth: 80, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'investAccumDepr', '折旧'),
          }),
          h(ElTableColumn, { label: '⑦减值', minWidth: 80, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'investImpairment', '减值'),
          }),
          h(ElTableColumn, { label: '⑧净值', minWidth: 90, align: 'right', className: 'formula-col' }, {
            default: ({ row }: { row: H3TransferRow }) => formulaCell(row.investNet, '⑧=⑤-⑥-⑦'),
          }),
        ]))
      }

      // 投资方（公允价值模式）⑨⑩ — 与 selfBookValue 完全独立
      if (isFair.value && p.direction !== 'investToSelf') {
        cols.push(h(ElTableColumn, { label: '投资性房地产（公允价值模式）' }, () => [
          h(ElTableColumn, { label: '⑨账面', minWidth: 90, align: 'right', className: 'formula-col' }, {
            // 投资方账面（⑨）= selfBookValue（只读，从转出方比例后净值自动填充）
            default: ({ row }: { row: H3TransferRow }) => formulaCell(row.investBookValue, '⑨ 投资方账面=转出方净值×比例（自动）'),
          }),
          h(ElTableColumn, { label: '⑩公允（转换日）', minWidth: 110, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'fairValue', '⑩ 转换日公允价值（按实际比例填入）'),
          }),
          h(ElTableColumn, { label: '面积', width: 80, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'area', '面积(㎡)'),
          }),
          h(ElTableColumn, { label: '参考单价', minWidth: 90, align: 'right' }, {
            default: ({ row }: { row: H3TransferRow }) => numInput(row, 'refUnitPrice', '单价'),
          }),
          h(ElTableColumn, { label: '单价来源', minWidth: 90 }, {
            default: ({ row }: { row: H3TransferRow }) => textInput(row, 'refPriceSource'),
          }),
        ]))
      }

      // 投资→自用：入账价值
      if (p.direction === 'investToSelf') {
        const label = isFair.value ? '转换日公允(入账)' : '账面净值(入账)'
        cols.push(h(ElTableColumn, { label, minWidth: 120, align: 'right' }, {
          default: ({ row }: { row: H3TransferRow }) => isFair.value
            ? numInput(row, 'fairValue', '公允价值模式：转换日公允价值')
            : formulaCell(row.entryValue, '成本模式：以⑧净值×比例入账'),
        }))
      }

      // 转换影响（公允模式）
      if (isFair.value) {
        // 存货→投资：差额计损益（无OCI）；自用→投资：OCI + 损益
        if (p.direction === 'selfToInvest') {
          cols.push(h(ElTableColumn, { label: '转换影响' }, () => [
            h(ElTableColumn, { label: '当期损益（⑩<⑨）', minWidth: 110, align: 'right', className: 'formula-col' }, {
              default: ({ row }: { row: H3TransferRow }) => formulaCell(row.plAmount, '公允<账面时计入当期损益', true),
            }),
            h(ElTableColumn, { label: 'OCI（⑩>⑨）', minWidth: 100, align: 'right', className: 'formula-col' }, {
              default: ({ row }: { row: H3TransferRow }) => formulaCell(row.ociAmount, '公允>账面时计入其他综合收益'),
            }),
          ]))
        } else if (p.direction === 'cipToInvest' || p.direction === 'inventoryToInvest') {
          cols.push(h(ElTableColumn, { label: '损益影响', minWidth: 100, align: 'right', className: 'formula-col' }, {
            default: ({ row }: { row: H3TransferRow }) => formulaCell(row.plAmount, '公允-账面净值，计入当期损益', true),
          }))
        }
      }

      // 入账价值 + 勾稽验证
      cols.push(
        h(ElTableColumn, { label: '入账价值', minWidth: 100, align: 'right', className: 'formula-col' }, {
          default: ({ row }: { row: H3TransferRow }) => formulaCell(row.entryValue, `入账价值（已按${row.conversionRatio}%比例计算）`),
        }),
        h(ElTableColumn, { prop: 'transferOut', label: '转出方金额', minWidth: 105, align: 'right' }, {
          default: ({ row }: { row: H3TransferRow }) => numInput(row, 'transferOut', '转出方账实核对金额'),
        }),
        h(ElTableColumn, { prop: 'transferIn', label: '转入方金额', minWidth: 105, align: 'right' }, {
          default: ({ row }: { row: H3TransferRow }) => numInput(row, 'transferIn', '转入方账实核对金额'),
        }),
        h(ElTableColumn, { label: '验证', width: 60, align: 'center' }, {
          default: ({ row }: { row: H3TransferRow }) => verifyTag(row),
        }),
        h(ElTableColumn, { prop: 'reason', label: '转换原因', minWidth: 100 }, {
          default: ({ row }: { row: H3TransferRow }) => textInput(row, 'reason'),
        }),
        h(ElTableColumn, { prop: 'approvalDoc', label: '批准文件', minWidth: 100 }, {
          default: ({ row }: { row: H3TransferRow }) => textInput(row, 'approvalDoc'),
        }),
        h(ElTableColumn, { prop: 'remark', label: '备注', minWidth: 80 }, {
          default: ({ row }: { row: H3TransferRow }) => textInput(row, 'remark'),
        }),
        h(ElTableColumn, { label: '', width: 50, fixed: 'right' }, {
          default: ({ row }: { row: H3TransferRow }) => !p.isReadonly
            ? h(ElButton, { size: 'small', type: 'danger', link: true, onClick: () => e('remove', row.rowId) }, () => '删')
            : null,
        }),
      )

      return h(ElTable, {
        data: p.rows, border: true, size: 'small', class: 'audit-table',
        emptyText: '暂无转换记录，点击「+ 新增」添加',
      }, () => cols)
    }
  },
})
</script>

<style scoped>
.h3-tab-transfer-review { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.7; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.summary-bar { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; padding: 10px 14px; background: #f5f7fa; border-radius: 6px; }
.summary-item { display: flex; flex-direction: column; gap: 2px; }
.summary-item .label { font-size: 11px; color: #909399; }
.summary-item .value { font-weight: 600; font-variant-numeric: tabular-nums; }

.materiality-card { margin-bottom: 14px; border-color: #e6a23c; }
.materiality-card :deep(.el-card__header) { background: #fdf6ec; }
.materiality-params { display: flex; align-items: center; gap: 6px; margin-bottom: 14px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 13px; }
.meta-label { color: #606266; }
.meta-inputs { display: flex; align-items: center; gap: 6px; }
.font-bold { font-weight: 700; }

.method-context { margin-bottom: 16px; }
.context-bar { border-left: 3px solid #d97706; background: #fffbe6; padding: 10px 14px; border-radius: 4px; font-size: 12px; line-height: 1.6; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; align-items: center; gap: 8px; }
.nav-chip { cursor: pointer; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.text-danger { color: var(--el-color-danger); }
</style>
