<template>
  <div class="i2-material-check">
    <div class="section-header">
      <span class="section-title">I2-8 研发材料投入检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li>确认利润表中记录的研发材料费用已发生，与被审计单位有关，且已记录于恰当的账户（发生、权利和义务、分类）。</li>
        <li>确认与研发费用有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性、计价和分摊、列报）。</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        先界定测试总体与抽样标准 → 再按「账簿凭证 ↔ 领料单/出库单」双栏逐项核对 →
        检查比例＝样本借方合计 ÷ 本期材料发生额（总体为 0 时显示 N/A，避免 #DIV/0!）。
        重点核对领用人员是否为该项目研发人员，领料单项目与账面归集是否一致，防止生产领料混入研发。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-7" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">样本 {{ summary.sampleCount }} 项</el-tag>
        <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">异常 {{ summary.anomalyCount }}</el-tag>
        <el-tag v-if="summary.qtyMismatchCount > 0" size="small" type="warning">数量不符 {{ summary.qtyMismatchCount }}</el-tag>
        <el-tag v-if="summary.projectMismatchCount > 0" size="small" type="warning">项目不符 {{ summary.projectMismatchCount }}</el-tag>
        <el-tag size="small" :type="coverageTagType">检查比例 {{ coverageLabel }}</el-tag>
        <el-button
          v-if="summary.anomalyCount > 0"
          size="small"
          type="danger"
          plain
          :disabled="isReadonly"
          @click="handleAnomalyToI23"
        >
          异常→I2-3
        </el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-7')">← I2-7</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-9')">I2-9 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="coverageLow"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      title="检查比例偏低：请扩大样本量，或在四、审计说明中解释原因。"
    />
    <el-alert
      v-if="populationStale"
      type="error"
      :closable="false"
      show-icon
      class="check-alert"
      title="抽样总体已过期：I2-7 材料费已变化，请点击「从 I2-7 带入」刷新，或确认手工总体仍适用。"
    />

    <!-- 二、样本选取标准与依据 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、样本选取标准与依据</span>
          <div class="title-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedMaterialTotal.amount > 0)"
              @click="syncPopulationFromI27"
            >
              从 {{ linkedMaterialTotal.source || 'I2-7' }} 带入本期材料费
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>

      <div class="test-content-hint">
        <p>测试内容说明：</p>
        <ol>
          <li v-for="(item, i) in I2_MATERIAL_TEST_CONTENT" :key="i">{{ item }}</li>
        </ol>
      </div>

      <el-descriptions :column="2" border size="small" class="sample-desc">
        <el-descriptions-item label="测试总体">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.populationDesc"
            size="small"
            placeholder="账面研发材料借方发生额总体"
          />
          <span v-else>{{ sampleMeta.populationDesc }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="本期发生额（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="sampleMeta.populationAmount"
              :controls="false"
              size="small"
              :precision="2"
              @change="(v: number | undefined) => setPopulationAmount(v ?? 0, true)"
            />
            <span v-else class="amt">{{ fmtNum(sampleMeta.populationAmount) }}</span>
            <el-tag v-if="linkedMaterialTotal.source" size="small" type="info">
              源 {{ linkedMaterialTotal.source }}: {{ fmtNum(linkedMaterialTotal.amount) }}
            </el-tag>
            <el-tag v-if="sampleMeta.populationManual" size="small" type="warning">手工</el-tag>
            <el-tag v-if="populationStale" size="small" type="danger">I2-7已变·总体过期</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.specificSample"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
          />
          <span v-else>{{ sampleMeta.specificSample }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法 / 过程">
          <div class="method-cell">
            <el-select
              v-if="!isReadonly"
              v-model="sampleMeta.sampleMethod"
              size="small"
              filterable
              allow-create
              style="width: 140px"
            >
              <el-option v-for="m in I2_MATERIAL_SAMPLE_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ sampleMeta.sampleMethod }}</span>
            <el-input
              v-if="!isReadonly"
              v-model="sampleMeta.sampleProcess"
              size="small"
              placeholder="如：IDEA 随机抽取 / 系统抽样间隔…"
              style="flex:1"
            />
            <span v-else>{{ sampleMeta.sampleProcess || '—' }}</span>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="检查合计（样本）">
          <span class="amt">{{ fmtNum(summary.checkedTotal) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="检查比例 / 告警阈值">
          <span :class="{ 'warn-coverage': coverageLow }">{{ coverageLabel }}</span>
          <span class="sep">/</span>
          <el-input-number
            v-if="!isReadonly"
            v-model="sampleMeta.coverageThreshold"
            :min="1"
            :max="100"
            :controls="false"
            size="small"
            style="width:72px"
          />
          <span v-else>{{ sampleMeta.coverageThreshold }}%</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 三、审计过程 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>三、审计过程 — 账簿 ↔ 领料单核对</span>
          <div class="title-actions">
            <el-segmented
              v-model="columnViewMode"
              :options="[
                { label: '精简', value: 'compact' },
                { label: '完整', value: 'full' },
              ]"
              size="small"
            />
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
          </div>
        </div>
      </template>

      <el-alert type="info" :closable="false" show-icon class="focus-tip" title="核对重点：领用人员是否为该项目研发人员；出库单/领料单上的研发项目是否与账面归集一致。" />

      <el-table
        :data="rows"
        border
        size="small"
        class="check-table"
        max-height="520"
        :row-class-name="rowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="#" width="40" fixed align="center" />

        <el-table-column label="记账凭证资料" align="center">
          <el-table-column prop="projectName" label="项目名称" min-width="120" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.projectName" size="small" @change="onRowChange(row)" />
              <span v-else>{{ row.projectName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="voucherNo" label="凭证编号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" />
              <span v-else>{{ row.voucherNo || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnViewMode === 'full'" prop="businessDesc" label="业务内容" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.businessDesc" size="small" />
              <span v-else>{{ row.businessDesc || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="inventoryName" label="存货名称" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.inventoryName" size="small" placeholder="品名" />
              <span v-else>{{ row.inventoryName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnViewMode === 'full'" prop="unit" label="单位" width="70">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.unit" size="small" />
              <span v-else>{{ row.unit || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="quantity" label="数量" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.quantity"
                size="small"
                :controls="false"
                :precision="2"
                style="width:100%"
                @change="onRowChange(row)"
              />
              <span v-else>{{ row.quantity }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="debitAmount" label="借方金额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.debitAmount"
                size="small"
                :controls="false"
                :precision="2"
                style="width:100%"
              />
              <span v-else class="amt">{{ fmtNum(row.debitAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnViewMode === 'full'" prop="counterpartAccount" label="对方科目" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.counterpartAccount" size="small" />
              <span v-else>{{ row.counterpartAccount || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnViewMode === 'full'" prop="counterpartDetail" label="对方明细" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.counterpartDetail" size="small" />
              <span v-else>{{ row.counterpartDetail || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="出库单/领料单资料" align="center">
          <el-table-column prop="slipDateNo" label="日期编号" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.slipDateNo" size="small" placeholder="领用单号" />
              <span v-else>{{ row.slipDateNo || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="recipient" label="领用人员" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.recipient" size="small" />
              <span v-else>{{ row.recipient || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnViewMode === 'full'" prop="recipientDept" label="领用部门" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.recipientDept" size="small" />
              <span v-else>{{ row.recipientDept || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="slipProject" label="研发项目" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.slipProject" size="small" @change="onRowChange(row)" />
              <span v-else :class="{ 'mismatch-text': hasProjectMismatch(row) }">{{ row.slipProject || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="slipQty" label="数量" width="90" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.slipQty"
                size="small"
                :controls="false"
                :precision="2"
                style="width:100%"
                :class="{ 'mismatch-input': hasQtyMismatch(row) }"
                @change="onRowChange(row)"
              />
              <span v-else :class="{ 'mismatch-text': hasQtyMismatch(row) }">{{ row.slipQty }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="indexRef" label="索引号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isAbnormal" label="是否异常" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.isAbnormal"
              size="small"
              clearable
              filterable
              allow-create
              style="width:100%"
              :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }"
            >
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
              <el-option label="数量不符" value="数量不符" />
              <el-option label="项目不符" value="项目不符" />
              <el-option label="领用人非研发" value="领用人非研发" />
              <el-option label="生产混入" value="生产混入" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }">{{ row.isAbnormal || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" text @click="handleOcr($index)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="审核结论" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" placeholder="结论" style="width:100%">
              <el-option label="相符" value="相符" />
              <el-option label="不符" value="不符" />
              <el-option label="待查" value="待查" />
            </el-select>
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>合计（样本借方）：<b>{{ fmtNum(summary.checkedTotal) }}</b></span>
        <span>本期发生额：<b>{{ fmtNum(summary.periodTotal) }}</b></span>
        <span :class="{ 'warn-coverage': coverageLow }">
          检查比例：<b>{{ coverageLabel }}</b>
        </span>
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>四、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="记录样本选取过程、账证不符事项、异常领用及应对措施…"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>五、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="基于检查结果，对研发材料投入的发生、准确性与归集恰当性给出结论…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 开发支出(1717) 材料投入检查" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="1717"
        phase="final"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, inject, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI2MaterialCheck,
  I2_MATERIAL_TEST_CONTENT,
  I2_MATERIAL_SAMPLE_METHODS,
  hasQtyMismatch,
  hasProjectMismatch,
  type I2MaterialCheckRow,
} from '../../composables/useI2MaterialCheck'
import {
  appendI23DraftAje,
  pickOcrField,
  runWorkpaperOcr,
  writeSheetCompletionMarker,
} from '../../composables/i2EnhancementHelpers'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const columnViewMode = ref<'compact' | 'full'>('compact')
const samplingVisible = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())

const allResponsesRef = toRef(props, 'allResponses')
const {
  rows,
  sampleMeta,
  auditNote,
  auditConclusion,
  summary,
  linkedMaterialTotal,
  coverageLow,
  coverageLabel,
  coverageTagType,
  populationStale,
  addRow,
  removeRow,
  applySuggestAbnormal,
  syncPopulationFromI27,
  setPopulationAmount,
  persistAll,
  saveAuditNote,
  saveAuditConclusion,
} = useI2MaterialCheck(allResponsesRef, { saveResponse: props.saveResponse })

function onRowChange(row: I2MaterialCheckRow) {
  applySuggestAbnormal(row)
}

function handleAddRow() {
  addRow()
}

async function handleSave() {
  await persistAll()
  const rate = summary.value.coverageRate
  const progress = rate == null
    ? (summary.value.sampleCount > 0 ? 40 : 10)
    : Math.max(10, Math.min(100, Math.round(rate)))
  await writeSheetCompletionMarker({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    sheetCode: 'I2-8',
    progress,
    ok: !coverageLow.value && summary.value.sampleCount > 0 && summary.value.anomalyCount === 0,
    detail: {
      sampleCount: summary.value.sampleCount,
      coverageRate: rate,
      anomalyCount: summary.value.anomalyCount,
    },
  })
  emit('save')
  ElMessage.success('材料投入检查表已保存')
}

function handleSampling() {
  if (!props.wpId || !props.projectId) {
    ElMessage.warning('缺少工作底稿或项目上下文，无法打开抽凭引擎')
    return
  }
  samplingVisible.value = true
}

function onSamplesFilled(payload: { samples?: any[] }) {
  const samples = payload?.samples ?? []
  let n = 0
  for (const s of samples) {
    const debit = Number(s?.debitAmount) || Number(s?.creditAmount) || 0
    addRow({
      voucherNo: String(s?.voucherNo ?? ''),
      debitAmount: debit,
      businessDesc: String(s?.summary ?? ''),
      projectName: '',
    })
    n++
  }
  samplingVisible.value = false
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已回填 ${n} 笔抽样凭证` : '未回填新凭证')
}

async function handleOcr(idx: number) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.jpg,.jpeg,.png,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const fields = await runWorkpaperOcr(props.wpId, file)
      const date = pickOcrField(fields, 'date', 'voucherDate', 'slipDate')
      const number = pickOcrField(fields, 'number', 'voucherNo', 'slipNo', 'docNo')
      const amount = pickOcrField(fields, 'amount', 'debitAmount', 'totalAmount')
      await ElMessageBox.confirm(
        `OCR 识别结果：\n日期: ${date || '-'}\n单号: ${number || '-'}\n金额: ${amount || '-'}\n\n确认填入第 ${idx + 1} 行？`,
        'OCR 识别结果确认',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      const row = rows.value[idx]
      if (!row) return
      if (number) {
        row.voucherNo = row.voucherNo || number
        row.slipDateNo = row.slipDateNo || (date ? `${date} ${number}` : number)
      } else if (date) {
        row.slipDateNo = row.slipDateNo || date
      }
      if (amount) {
        const n = Number(amount.replace(/,/g, ''))
        if (Number.isFinite(n)) row.debitAmount = n
      }
      onRowChange(row)
      ElMessage.success('OCR 结果已填入')
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.error(e?.message || 'OCR 识别失败')
    }
  }
  input.click()
}

async function handleAnomalyToI23() {
  const anomalous = rows.value.filter((r) => isAbnormalFlag(r.isAbnormal))
  if (!anomalous.length) {
    ElMessage.info('当前无异常样本')
    return
  }
  const amount = anomalous.reduce((s, r) => s + (Number(r.debitAmount) || 0), 0)
  await appendI23DraftAje({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    draft: {
      description: `I2-8 材料投入检查异常 ${anomalous.length} 笔，合计 ${amount}`,
      debitAmount: amount > 0 ? amount : 0,
      indexRef: 'I2-8',
      remark: '来源:材料投入检查异常一键生成',
    },
  })
  ElMessage.success(`已向 I2-3 生成调整草稿（${anomalous.length} 笔）`)
  emit('navigate-sheet', 'I2-3')
}

function handleReview() {
  openReviewDialog('I2-8-研发材料投入检查')
}

function isAbnormalFlag(v: string): boolean {
  const s = (v || '').trim()
  return s !== '' && s !== '否'
}

function rowClassName({ row }: { row: I2MaterialCheckRow }) {
  if (isAbnormalFlag(row.isAbnormal) || hasQtyMismatch(row) || hasProjectMismatch(row)) {
    return 'row-abnormal'
  }
  return ''
}

function getSummary({ columns }: { columns: { property?: string }[] }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    if (col.property === 'debitAmount') return fmtNum(summary.value.checkedTotal)
    if (col.property === 'quantity') {
      const q = rows.value.reduce((s, r) => s + (Number(r.quantity) || 0), 0)
      return q ? q.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : ''
    }
    if (col.property === 'slipQty') {
      const q = rows.value.reduce((s, r) => s + (Number(r.slipQty) || 0), 0)
      return q ? q.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : ''
    }
    return ''
  })
}

function fmtNum(v: number): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-material-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6;
}
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 10px; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.check-alert { margin-bottom: 10px; }
.block-card { margin-bottom: 14px; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.test-content-hint {
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px;
  padding: 8px 12px; margin-bottom: 12px; font-size: 12px; color: #475569; line-height: 1.6;
}
.test-content-hint ol { margin: 4px 0 0; padding-left: 18px; }
.sample-desc { margin-top: 4px; }
.pop-cell, .method-cell { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; width: 100%; }
.focus-tip { margin-bottom: 10px; }
.check-table { font-size: var(--wp-font-size, 13px); width: 100%; }
.amt { font-variant-numeric: tabular-nums; }
.warn-coverage { color: #dc2626; font-weight: 600; }
.sep { margin: 0 6px; color: #94a3b8; }
.mismatch-text { color: #dc2626; font-weight: 500; }
.abnormal-cell { color: #dc2626; }
.summary-bar {
  display: flex; gap: 24px; flex-wrap: wrap; margin-top: 10px;
  padding: 8px 12px; background: #f8fafc; border-radius: 4px; font-size: 12px; color: #334155;
}
.audit-note-card, .audit-conclusion-card { margin-top: 14px; }
:deep(.row-abnormal) { background: #fef2f2 !important; }
:deep(.mismatch-input .el-input__inner) { color: #dc2626; }
</style>
