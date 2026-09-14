<!--
  K2TabCheck.vue — K2-6 其他流动资产检查表（凭证级测试）

  忠实反映致同源模板 K2-6（镜像 K1-12 简化版）：
    一、测试目标（存在/权利义务/计价分摊 三认定）
    二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
    三、测试（本期发生额检查，凭证级明细 + 抽凭引擎 + 核对内容勾选）
    四、审计说明（检查比例表：本期借方/本期贷方 → 账面/检查/比例）
    五、审计结论

  复用 useK1VoucherCheck（通用凭证检查状态）。科目由报表行 BS-014 解析（实证 1901 其他流动资产，借方/资产类）。
  源模板无"期后检查"段，但保留完整样本选取功能和抽凭引擎。
-->
<template>
  <div class="k2-tab-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认测试目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">K2-6 其他流动资产检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、测试目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他流动资产是存在的，且已记录在恰当的账户中；</li>
        <li><b>权利和义务：</b>记录的其他流动资产由被审计单位拥有或控制；</li>
        <li><b>计价和分摊：</b>其他流动资产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>其他流动资产（报表行 BS-014，实证科目 1901）为<strong>借方/资产类</strong>科目。检查内容：①原始凭证齐全 ②记账凭证与原始凭证相符 ③账务处理正确 ④记录于恰当的会计期间 ⑤其他（如摊销是否正确）。关注待摊费用摊销期限、预缴税费抵扣时效、合同取得成本增量性。</p>
    </div>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（借方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（贷方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额（XX金额以上）、关联方交易、异常摊销款项全部测试" @change="persist" />
        </div>
        <div class="cg-item">
          <label>抽样总体</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.samplingPopulationCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.samplingPopulationAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样样本量</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.sampleSize" :controls="false" :disabled="isReadonly" size="small" placeholder="样本量" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样方法</label>
          <el-select v-model="criteria.samplingMethod" :disabled="isReadonly" size="small" @change="persist">
            <el-option label="随机选样" value="随机选样" />
            <el-option label="系统选样" value="系统选样" />
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随意选样（非统计抽样）" value="随意选样" />
          </el-select>
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" size="small"
            placeholder="使用IDEA（XX抽样工具）选择XX数量、金额XX的样本进行测试，抽样过程和结果见相关底稿" @change="persist" />
        </div>
      </div>
    </el-card>

    <!-- 三、测试 — 本期发生额检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 本期发生额检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="460" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="明细项目" min-width="130">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="日期" width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方明细科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" /><span v-else>{{ row.offsetSubAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="贷方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="核对内容" width="180" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content><div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(lbl, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="80" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" /><span v-else>{{ row.indexNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="备注说明" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计　借方：{{ fmtAmt(occurrenceDebitChecked) }}　贷方：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例表）-->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="k2CheckRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="120" />
        <el-table-column label="账面金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span></template></el-table-column>
        <el-table-column label="检查金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template></el-table-column>
        <el-table-column label="检查比例" width="130" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'" size="small" effect="plain">{{ (row.ratio * 100).toFixed(1) }}%</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%）：{{ lowRatioWarnings.map(r => r.direction).join('、') }}，应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、结果；拟调整事项及分录、未调整事项及其影响等" @change="persist" />
      </div>
    </el-card>

    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">
        ⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）
        <el-button v-if="!isReadonly" size="small" type="danger" plain style="margin-left:12px" @click="handlePushAbnormalToK23">推送至K2-3</el-button>
      </div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填明细项目）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS 1314 / CAS 14）</summary>
      <ul>
        <li>测试目标对应三项认定：存在、权利和义务、计价和分摊</li>
        <li>核对内容标准：①原始凭证齐全 ②记账凭证与原始凭证相符 ③账务处理正确 ④记录于恰当会计期间 ⑤摊销/减值处理正确</li>
        <li>样本选取：测试总体扣除特定样本得抽样总体；大额、异常摊销、合同取得成本应全部测试</li>
        <li>检查比例 = 检查金额 / 账面金额；比例偏低（&lt;30%）须扩样或说明</li>
        <li>关注待摊费用是否在受益期内均匀摊销，预缴税费是否在抵扣时效内</li>
        <li>抽凭引擎复用序时账，科目由报表行 BS-014 解析（实证 1901 其他流动资产，借方/资产类）</li>
      </ul>
    </details>

    <el-dialog v-model="samplingVisible" :title="`抽凭引擎 — 其他流动资产（${k2CheckAccountCode}）`" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" :account-code="k2CheckAccountCode" phase="final" :workpaper-id="props.wpId" :project-id="props.projectId" :year="year" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabCheck.vue — K2-6 其他流动资产检查表（凭证级测试，复用 useK1VoucherCheck）
 *
 * 科目由报表行 BS-014 解析（实证 1901 其他流动资产，借方/资产类）。
 * 源模板无"期后检查"段，但保留完整样本选取功能、抽凭引擎、核对内容、结论模板。
 */
import { ref, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'
import { K2_ACCOUNT_NAME, k2AccountCode } from '../../composables/k2AccountScope'
import type { TbSourceCodes } from '../../composables/shared/tbSourceCodes'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  /** 四表取数溯源（render 下发 `tb_source_codes`）—— 决定抽凭引擎的科目 */
  tbSourceCodes?: TbSourceCodes | null
  isReadonly: boolean
  year?: number
}>()

/**
 * 抽凭 / 事件科目码 —— 由报表行 `BS-014` 解析（实证 `1901`）。
 * 🔴 历史写死 `1231`，抽凭引擎会抽**应收款项坏账准备**的凭证。
 */
const k2CheckAccountCode = computed(() => k2AccountCode(props.tbSourceCodes))
const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const year = computed(() => props.year ?? new Date().getFullYear())
const allResponsesRef = computed(() => props.allResponses)

const {
  itemId, checkLabels,
  criteria, occurrenceRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: 'K2-6-voucher-check' })

// 源模板 K2-6 检查比例仅 本期借方/本期贷方（无期末余额行）
const k2CheckRatios = computed(() => checkRatios.value.filter(r => r.direction !== '期末余额'))

onMounted(() => {
  load()
  applyBookAmountsFromK21()
})

function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

const samplingVisible = ref(false)
function openSampling() { samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) {
  fillFromSamples('occurrence', payload?.samples ?? [])
  samplingVisible.value = false
  persist()
}

function persist() {
  const data = serialize()
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: data })
  emit('save', itemId, { remark: data })
}
function onConclusionOption(val: string) {
  const map: Record<string, string> = {
    A: '未见异常。',
    B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
    C: '由于存在重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
  }
  if (map[val] && !conclusion.value) conclusion.value = map[val]
  persist()
}
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function abnormalRowClass({ row }: { row: K1VoucherRow }): string { return row.abnormal ? 'abnormal-row' : '' }

/** AI辅助——真正调用AI端点生成审计说明 */
async function handleAiGenerate() {
  try {
    const context: Record<string, string> = {
      accountCode: k2CheckAccountCode.value,
      accountName: K2_ACCOUNT_NAME,
      sheet: 'K2-6',
      sampleCount: String(occurrenceRows.value.length),
      abnormalCount: String(abnormalRows.value.length),
      debitChecked: String(occurrenceDebitChecked.value),
      creditChecked: String(occurrenceCreditChecked.value),
      checkRatioSummary: k2CheckRatios.value.map(r => `${r.direction}:${r.ratio != null ? (r.ratio * 100).toFixed(1) + '%' : '未计算'}`).join('; '),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请根据其他流动资产凭证检查表的测试结果，生成审计说明：概述抽样过程、核对结果、异常事项及结论建议，不得虚构未提供的样本与金额',
      context,
      existingContent: auditNote.value,
      section: 'K2-6-voucher-note',
    })
    const generated = res?.data?.data?.content || res?.data?.content || ''
    if (generated) {
      auditNote.value = generated
      persist()
      ElMessage.success('AI审计说明已生成')
    } else {
      ElMessage.warning('AI未生成内容')
    }
  } catch {
    ElMessage.warning('AI生成失败')
  }
}

function handleReview() { openReviewDialog('K2-6-check') }

/** 从K2-1审定表带入账面借贷方发生额（填充检查比例分母） */
function applyBookAmountsFromK21(): void {
  // 读K2-1审定表的本期借方/贷方合计
  const adjRows = props.allResponses.get('K2-1-adj-rows')
  const raw = adjRows?.remark ?? adjRows?.value ?? null
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        const totalRow = parsed.find((r: any) => r.rowKey === 'subtotal')
        if (totalRow) {
          if (!criteria.value.bookDebitOccurrence && totalRow.debit) {
            criteria.value.bookDebitOccurrence = Number(totalRow.debit)
          }
          if (!criteria.value.bookCreditOccurrence && totalRow.credit) {
            criteria.value.bookCreditOccurrence = Number(totalRow.credit)
          }
          if (!criteria.value.populationDebitAmount && totalRow.debit) {
            criteria.value.populationDebitAmount = Number(totalRow.debit)
          }
          if (!criteria.value.populationCreditAmount && totalRow.credit) {
            criteria.value.populationCreditAmount = Number(totalRow.credit)
          }
        }
      }
    } catch { /* silent */ }
  }
  // 尝试从TB自动取入
  const tbDebit = props.allResponses.get('K2-tb-period-debit')
  const tbCredit = props.allResponses.get('K2-tb-period-credit')
  if (tbDebit?.remark && !criteria.value.bookDebitOccurrence) {
    criteria.value.bookDebitOccurrence = Number(tbDebit.remark) || 0
  }
  if (tbCredit?.remark && !criteria.value.bookCreditOccurrence) {
    criteria.value.bookCreditOccurrence = Number(tbCredit.remark) || 0
  }
}

/** 推送异常凭证至K2-3调整分录 */
function handlePushAbnormalToK23(): void {
  if (abnormalRows.value.length === 0) return
  const entries = abnormalRows.value.map(r => ({
    summary: `凭证检查异常-${r.debtorName || r.voucherNo}：${r.remark || '待说明'}`,
    debitAccount: r.offsetAccount || '待确认',
    debitAmount: r.debitAmount || 0,
    creditAccount: '其他流动资产',
    creditAmount: r.creditAmount || 0,
    source: 'K2-6',
  }))
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K2',
      accountCode: k2CheckAccountCode.value,
      source: 'K2-6-abnormal',
      suggestedEntries: entries,
    })
    ElMessage.success(`已推送 ${entries.length} 笔异常凭证至K2-3`)
  } catch {
    ElMessage.warning('推送失败')
  }
}
</script>

<style scoped>
.k2-tab-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%); border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.criteria-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 18px; }
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item.cg-full { grid-column: 1 / -1; }
.cg-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.cg-inline { display: flex; align-items: center; gap: 5px; }
.cg-unit { font-size: 12px; color: var(--el-text-color-secondary); }
.num-sm { width: 78px; }
.num-md { width: 130px; }
.voucher-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.col-help { cursor: help; border-bottom: 1px dashed var(--el-border-color); }
.check-group { display: flex; flex-wrap: wrap; gap: 0 4px; }
.check-group :deep(.el-checkbox) { margin-right: 4px; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }
.voucher-table :deep(.abnormal-row td) { background-color: #fef2f2 !important; }
.ratio-table { max-width: 640px; }
.ratio-warn { margin-top: 12px; }
.muted { color: var(--el-text-color-placeholder); }
.note-block { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
.note-block label { font-size: 12px; color: var(--el-text-color-secondary); }
.abnormal-summary { margin-bottom: 10px; padding: 10px 12px; border-radius: 6px; background: #fef2f2; border: 1px solid #fecaca; }
.as-header { font-weight: 600; color: var(--el-color-danger); margin-bottom: 6px; }
.as-list { padding-left: 18px; margin: 0; line-height: 1.7; color: var(--el-color-danger-dark-2); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
