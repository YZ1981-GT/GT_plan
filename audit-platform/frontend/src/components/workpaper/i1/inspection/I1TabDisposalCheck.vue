<template>
  <div class="i1-tab-disposal-check">
    <div class="methodology-context">
      <p>
        <strong>编制逻辑（对齐 Excel I1-6）：</strong>
        先定性核验减少方式合规（核销审批/出售手续公允/其他方式），再定量复核账面结转与清理净损益。
        净值 = 原值 − 累计摊销 − 减值；清理净损益 = 清理收入 − 清理费用 − 净值（源表 I=H−G−E）。
        房地产开发企业：待售房屋占用土地使用权应转入开发成本；自建厂房的土地与建筑物应分别摊销/折旧。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：通过检查合同、凭证及相关资料，核实无形资产减少的存在/发生、所有权以及计价和分摊。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-6" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.rows.value.length }} 项</el-tag>
        <el-tag v-if="state.anomalyCount.value" size="small" type="danger">
          异常 {{ state.anomalyCount.value }}
        </el-tag>
        <el-tag v-if="!state.prepValidation.value.ok" size="small" type="danger">
          编制校验 {{ state.prepValidation.value.messages.length }}
        </el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-2')">← I1-2</el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-1')">→ 审定表</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" :disabled="isReadonly" @click="handleSeed">从 I1-2 带入减少</el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handlePublishH10">
          发布联动 H10
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="showSamplingDialog = true">🎲 抽凭</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
        <el-button size="small" circle @click="openReview('I1-6')">💬</el-button>
      </div>
    </div>

    <el-alert
      v-if="!state.prepValidation.value.ok"
      type="warning"
      :closable="false"
      show-icon
      class="mb-8"
      :title="state.prepValidation.value.messages[0]"
      :description="state.prepValidation.value.messages.slice(1, 4).join('；') || undefined"
    />

    <el-card shadow="never" class="main-card">
      <template #header>
        <div class="section-title">
          <span>无形资产减少检查表 I1-6（定性合规 + 定量金额合并）</span>
        </div>
      </template>

      <el-table
        :data="state.rows.value"
        border
        stripe
        size="small"
        max-height="520"
        class="check-table"
        row-key="rowId"
        show-summary
        :summary-method="getSummary"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="#" width="44" align="center" fixed />

        <el-table-column prop="name" label="资产名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.name"
              size="small"
              @change="(v: string) => state.updateField(row.rowId, 'name', v)"
            />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="counterpartAccount" label="对方科目" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.counterpartAccount"
              size="small"
              placeholder="如 1606"
              @change="(v: string) => state.updateField(row.rowId, 'counterpartAccount', v)"
            />
            <span v-else>{{ row.counterpartAccount || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="disposalMethod" label="减少方式" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.disposalMethod"
              size="small"
              style="width: 98px"
              @change="(v: string) => state.updateField(row.rowId, 'disposalMethod', v)"
            >
              <el-option v-for="m in I1_DISPOSAL_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.disposalMethod || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 核销检查 -->
        <el-table-column label="核销检查" align="center">
          <el-table-column label="经审批" width="72" align="center">
            <template #default="{ row }">
              <YnSelect
                :model-value="row.writeOffApproved"
                :disabled="isReadonly || !isWriteOff(row.disposalMethod)"
                @change="(v) => state.updateField(row.rowId, 'writeOffApproved', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="金额正确" width="72" align="center">
            <template #default="{ row }">
              <YnSelect
                :model-value="row.writeOffAmountCorrect"
                :disabled="isReadonly || !isWriteOff(row.disposalMethod)"
                @change="(v) => state.updateField(row.rowId, 'writeOffAmountCorrect', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="入账正确" width="72" align="center">
            <template #default="{ row }">
              <YnSelect
                :model-value="row.writeOffEntryCorrect"
                :disabled="isReadonly || !isWriteOff(row.disposalMethod)"
                @change="(v) => state.updateField(row.rowId, 'writeOffEntryCorrect', v)"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 出售检查 -->
        <el-table-column label="出售检查" align="center">
          <el-table-column label="经审批" width="72" align="center">
            <template #default="{ row }">
              <YnSelect
                :model-value="row.saleApproved"
                :disabled="isReadonly || !isSale(row.disposalMethod)"
                @change="(v) => state.updateField(row.rowId, 'saleApproved', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="手续完备" width="72" align="center">
            <template #default="{ row }">
              <YnSelect
                :model-value="row.saleProceduresComplete"
                :disabled="isReadonly || !isSale(row.disposalMethod)"
                @change="(v) => state.updateField(row.rowId, 'saleProceduresComplete', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="价格公允" width="72" align="center">
            <template #default="{ row }">
              <YnSelect
                :model-value="row.salePriceFair"
                :disabled="isReadonly || !isSale(row.disposalMethod)"
                @change="(v) => state.updateField(row.rowId, 'salePriceFair', v)"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="其他减少" align="center">
          <el-table-column prop="otherMethodDesc" label="方式说明" min-width="90">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.otherMethodDesc"
                size="small"
                :disabled="!isOther(row.disposalMethod)"
                @change="(v: string) => state.updateField(row.rowId, 'otherMethodDesc', v)"
              />
              <span v-else>{{ row.otherMethodDesc || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合规" width="72" align="center">
            <template #default="{ row }">
              <YnSelect
                :model-value="row.otherCompliant"
                :disabled="isReadonly || !isOther(row.disposalMethod)"
                @change="(v) => state.updateField(row.rowId, 'otherCompliant', v)"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="voucherDate" label="日期" width="120">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              :model-value="row.voucherDate || row.disposalDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width: 110px"
              @change="(v: string) => {
                state.updateField(row.rowId, 'voucherDate', v || '')
                state.updateField(row.rowId, 'disposalDate', v || '')
              }"
            />
            <span v-else>{{ row.voucherDate || row.disposalDate || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="voucherNo" label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.voucherNo"
              size="small"
              @change="(v: string) => state.updateField(row.rowId, 'voucherNo', v)"
            />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="attachmentIndex" label="附件索引" width="90">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.attachmentIndex"
              size="small"
              placeholder="I1-6-x"
              @change="(v: string) => state.updateField(row.rowId, 'attachmentIndex', v)"
            />
            <span v-else>{{ row.attachmentIndex || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 定量金额 -->
        <el-table-column label="本期减少账面" align="center">
          <el-table-column prop="originalCost" label="原值" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.originalCost"
                :controls="false"
                size="small"
                :precision="2"
                style="width: 88px"
                @change="(v: number | undefined) => state.updateField(row.rowId, 'originalCost', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.originalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="accAmort" label="累计摊销" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.accAmort"
                :controls="false"
                size="small"
                :precision="2"
                style="width: 88px"
                @change="(v: number | undefined) => state.updateField(row.rowId, 'accAmort', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.accAmort) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="impairment" label="减值准备" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.impairment"
                :controls="false"
                size="small"
                :precision="2"
                style="width: 88px"
                @change="(v: number | undefined) => state.updateField(row.rowId, 'impairment', v ?? 0)"
              />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairment) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="netBookValue" label="账面价值" width="100" align="right">
            <template #header>
              <span class="formula-header" title="= 原值 − 累计摊销 − 减值（E=B−C−D）">账面价值</span>
            </template>
            <template #default="{ row }">
              <span class="formula-cell amt-cell">{{ fmtAmt(row.netBookValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="disposalCost" label="清理费用" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.disposalCost"
              :controls="false"
              size="small"
              :precision="2"
              style="width: 88px"
              @change="(v: number | undefined) => state.updateField(row.rowId, 'disposalCost', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.disposalCost) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="disposalIncome" label="清理收入" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.disposalIncome"
              :controls="false"
              size="small"
              :precision="2"
              style="width: 88px"
              @change="(v: number | undefined) => state.updateField(row.rowId, 'disposalIncome', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.disposalIncome) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="disposalGainLoss" label="清理净损益" width="110" align="right">
          <template #header>
            <span class="formula-header" title="= 清理收入 − 清理费用 − 账面价值（I=H−G−E）">清理净损益</span>
          </template>
          <template #default="{ row }">
            <span
              class="formula-cell amt-cell"
              :class="{ 'error-amount': row.disposalGainLoss < 0 }"
            >{{ fmtAmt(row.disposalGainLoss) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="勾稽一致" width="80" align="center">
          <template #default="{ row }">
            <YnSelect
              :model-value="row.reconciled"
              :disabled="isReadonly"
              @change="(v) => state.updateField(row.rowId, 'reconciled', v)"
            />
          </template>
        </el-table-column>

        <el-table-column prop="conclusion" label="结论" width="90" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.conclusion"
              size="small"
              style="width: 78px"
              @change="(v: string) => state.updateField(row.rowId, 'conclusion', v)"
            >
              <el-option label="无异常" value="无异常" />
              <el-option label="有异常" value="有异常" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>原值合计 <b class="amt-cell">{{ fmtAmt(state.totalCost.value) }}</b></span>
        <span>账面价值 <b class="amt-cell">{{ fmtAmt(state.totalNet.value) }}</b></span>
        <span>清理费用 <b class="amt-cell">{{ fmtAmt(state.totalDisposalCost.value) }}</b></span>
        <span>清理收入 <b class="amt-cell">{{ fmtAmt(state.totalIncome.value) }}</b></span>
        <span>
          净损益
          <b class="amt-cell" :class="{ 'error-amount': state.totalGainLoss.value < 0 }">
            {{ fmtAmt(state.totalGainLoss.value) }}
          </b>
        </span>
        <GtIndexChip value="wp:H10" :context-project-id="projectId" context="资产处置收益 H10" />
        <GtIndexChip value="wp:I1-1" :context-project-id="projectId" />
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>三、审计说明</span></div></template>
      <el-input
        :model-value="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="处置审批核对、出售公允性、清理净损益复核、与审定表/明细表本期减少勾稽、土地使用权转入开发成本等特殊事项…"
        @change="(v: string) => state.saveNote(v)"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <el-button size="small" plain :disabled="isReadonly" @click="fillDraft">填入结论模板</el-button>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="handlePublishH10">
            📤 发布联动 H10
          </el-button>
        </div>
      </template>
      <el-input
        :model-value="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="对本期无形资产减少的审计结论…"
        @change="(v: string) => state.saveConclusion(v)"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制说明</summary>
      <ol>
        <li>净值 E = 原值 − 累计摊销 − 减值；清理净损益 I = 清理收入 − 清理费用 − 净值。</li>
        <li>核销/报废重点查审批与结转；出售/转让重点查手续完备与协议公允。</li>
        <li>房地产开发：待售房屋占用的土地使用权应转入存货/开发成本；自建厂房土地与建筑物分别摊销折旧。</li>
        <li>「从 I1-2 带入减少」按原值减少金额识别；抽凭可补凭证号与日期。</li>
        <li>点「发布联动 H10」按行写入 disposal:source-updated（sourceWp=I1 → intangible_disposal）。</li>
        <li>本表将 Excel 上下两区合并为一行，避免资产名称双表不同步。</li>
      </ol>
    </details>

    <el-dialog
      v-model="showSamplingDialog"
      title="抽凭引擎（科目 1701 无形资产-减少）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && wpId && projectId"
        :project-id="projectId"
        :workpaper-id="wpId"
        account-code="1701"
        phase="final"
        :year="year ?? new Date().getFullYear()"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabDisposalCheck.vue — I1-6 无形资产减少检查表
 * 对齐 Excel：定性合规 + 定量金额；净损益 = 收入 − 费用 − 净值
 */
import { computed, inject, ref, defineComponent, h } from 'vue'
import { ElMessage, ElMessageBox, ElSelect, ElOption } from 'element-plus'
import {
  useI1DisposalCheck,
  I1_DISPOSAL_METHODS,
  type I1DisposalCheckRow,
} from '../../composables/useI1DisposalCheck'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{
  wpId: string
  projectId: string
  year?: number
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save', itemId?: string, value?: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const showSamplingDialog = ref(false)

const state = useI1DisposalCheck({
  allResponses: allResponsesRef as any,
  onSave: (itemId, value) => emit('save', itemId, value),
  onPublishEvent(event, payload) {
    // 仅 eventBus：crossWpEventBridge 转发到 window，避免 H10 双次入库
    eventBus.emit(event as any, payload)
  },
})

/** 紧凑 Y/N 下拉 */
const YnSelect = defineComponent({
  name: 'YnSelect',
  props: {
    modelValue: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
  },
  emits: ['change'],
  setup(p, { emit: e }) {
    return () => h(
      ElSelect,
      {
        modelValue: p.modelValue,
        size: 'small',
        disabled: p.disabled,
        style: 'width:62px',
        'onUpdate:modelValue': (v: string) => e('change', v),
        onChange: (v: string) => e('change', v),
      },
      {
        default: () => [
          h(ElOption, { label: '—', value: '' }),
          h(ElOption, { label: '是', value: 'Y' }),
          h(ElOption, { label: '否', value: 'N' }),
        ],
      },
    )
  },
})

function isWriteOff(m: string): boolean {
  return ['核销', '报废', '到期注销'].includes(m)
}
function isSale(m: string): boolean {
  return ['出售', '转让'].includes(m)
}
function isOther(m: string): boolean {
  return ['其他', '转入开发成本'].includes(m)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入无形资产名称', '新增减少项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value.trim())
  } catch { /* cancelled */ }
}

function handleSeed() {
  const r = state.seedFromDetail()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function handlePublishH10() {
  const r = state.publishDisposalToH10()
  ElMessage({ type: r.ok ? 'success' : 'warning', message: r.message })
}

function fillDraft() {
  state.fillConclusionDraft()
  ElMessage.success('已填入结论模板')
}

function onSampleFilled(samples: any[]) {
  showSamplingDialog.value = false
  const n = state.appendFromSamples(samples)
  if (n) ElMessage.success(`已从抽凭加入 ${n} 行`)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function rowClassName({ row }: { row: I1DisposalCheckRow }): string {
  if (row.conclusion === '有异常' || row.reconciled === 'N') return 'row-anomaly'
  return ''
}

function getSummary({ columns }: { columns: any[] }) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) {
      sums[idx] = '合计'
      return
    }
    const p = col.property
    if (p === 'originalCost') sums[idx] = fmtAmt(state.totalCost.value)
    else if (p === 'accAmort') sums[idx] = fmtAmt(state.totalAccAmort.value)
    else if (p === 'impairment') sums[idx] = fmtAmt(state.totalImpairment.value)
    else if (p === 'netBookValue') sums[idx] = fmtAmt(state.totalNet.value)
    else if (p === 'disposalCost') sums[idx] = fmtAmt(state.totalDisposalCost.value)
    else if (p === 'disposalIncome') sums[idx] = fmtAmt(state.totalIncome.value)
    else if (p === 'disposalGainLoss') sums[idx] = fmtAmt(state.totalGainLoss.value)
    else sums[idx] = ''
  })
  return sums
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-disposal-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #6b5900;
  line-height: 1.6;
}

.objective-alert { margin-bottom: 12px; }
.mb-8 { margin-bottom: 8px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.nav-chip { cursor: pointer; }

.main-card { margin-bottom: 12px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.check-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.error-amount { color: var(--el-color-danger); font-weight: 600; }
:deep(.row-anomaly) { background: #fef0f0 !important; }

.summary-bar {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
  padding: 10px 12px;
  margin-top: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
}

.note-card { margin-bottom: 12px; }
.compile-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
