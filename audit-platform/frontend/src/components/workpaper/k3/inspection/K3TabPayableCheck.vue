<!--
  K3TabPayableCheck.vue — K3-7 其他应付款检查表（凭证级测试）

  忠实反映致同源模板 K3-7（其他应付款版，镜像 K1-12）：
    一、审计目标（存在/偿还义务/计价分摊 三认定）
    二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
    三、测试（1.本期发生额检查 2.期后付款检查，凭证级明细 + 抽凭引擎 + 核对内容勾选）
    四、审计说明（检查比例表：本期借方/本期贷方/期末余额 → 账面/检查/比例）
    五、审计结论

  复用 useK1VoucherCheck（通用凭证检查状态）。科目 2241 其他应付款。
-->
<template>
  <div class="k3-tab-payable-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认审计目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>期后付款反向截止（完整性）</div>
      <div class="guide-step"><span class="gs-no">5</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">K3-7 其他应付款检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他应付款是存在的，且已记录在恰当的账户中；</li>
        <li><b>义务：</b>记录的其他应付款是被审计单位应当履行的偿还义务；</li>
        <li><b>计价和分摊：</b>其他应付款以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

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
            placeholder="大额（XX金额以上）、关联方/关联交易形成的款项、异常款项全部测试" @change="persist" />
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
        <div class="cg-item">
          <label>期末余额（检查比例基准）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.endBalance" :controls="false" :disabled="isReadonly" size="small" placeholder="期末余额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" size="small"
            placeholder="使用IDEA（XX抽样工具）选择XX数量、金额XX的样本进行测试，抽样过程和结果见相关底稿" @change="persist" />
        </div>
      </div>
    </el-card>

    <!-- 三、测试 1. 本期发生额检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 1. 本期发生额检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('occurrence')"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="360" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="债权人名称" min-width="130">
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
        <el-table-column label="对方明细科目" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetDetailAccount" size="small" placeholder="明细科目" @change="persist" /><span v-else>{{ row.offsetDetailAccount || '-' }}</span></template>
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
              <template #content><div v-for="(lbl, i) in k3CheckLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(lbl, i) in k3CheckLabels" :key="i" :value="i" :label="i + 1" />
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

    <!-- 三、测试 2. 期后付款检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 2. 期后付款检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('post')"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addPostCollectionRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="postCollectionRows" border size="small" :max-height="300" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="债权人名称" min-width="130">
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
        <el-table-column label="付款金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="期末已入账" width="95" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRecordedAtYearEnd" size="small" placeholder="—" @change="persist">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待定" value="待定" />
            </el-select>
            <el-tag v-else :type="row.isRecordedAtYearEnd === '否' ? 'danger' : row.isRecordedAtYearEnd === '是' ? 'success' : 'info'" size="small">{{ row.isRecordedAtYearEnd || '—' }}</el-tag>
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
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removePostCollectionRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计　期后付款：{{ fmtAmt(k3PostPaymentChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 三、测试 — 反向截止测试提示（负债完整性核心程序） -->
    <div class="methodology-context">
      <p><strong>反向截止测试（完整性认定核心程序）</strong>：从资产负债表日后的银行付款记录中选取样本，追查至报告期末是否已恰当记录为负债。负债类科目审计重点为<strong>完整性</strong>——即期末是否存在应付已付但未入账的负债。</p>
      <p>操作要点：① 获取次年1-6月序时账2241借方凭证（偿付=借方减少）→ ② 追查发票/合同确认负债确认日 → ③ 若负债确认日在资产负债表日前且期末未入账 → 标记"疑似未入账负债"并考虑调整。</p>
    </div>

    <!-- 四、审计说明（检查比例表）-->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="k3CheckRatios" border size="small" class="ratio-table">
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
      <el-alert v-if="k3LowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%）：{{ k3LowRatioWarnings.map(r => r.direction).join('、') }}，应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、结果；拟调整事项及分录、未调整事项及其影响等" @change="persist" />
      </div>
    </el-card>

    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填债权人）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
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
      <summary>编制提示（CAS 1314）</summary>
      <ul>
        <li>审计目标对应三项认定：存在、义务、计价和分摊</li>
        <li>样本选取：测试总体扣除特定样本得抽样总体；大额、关联方、异常款项应全部测试</li>
        <li>本期发生额检查：逐笔核对凭证与原始单据，关注挂账合理性</li>
        <li>期后付款检查：截止日后付款与期末余额比对，验证期末余额真实性</li>
        <li>检查比例 = 检查金额 / 账面金额；比例偏低（&lt;30%）须扩样或说明</li>
        <li>抽凭引擎复用序时账，科目 2241 其他应付款</li>
      </ul>
    </details>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 其他应付款(2241)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2241" phase="final" :workpaper-id="props.wpId" :project-id="props.projectId" :year="year" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/** K3TabPayableCheck.vue — K3-7 其他应付款检查表（凭证级测试，复用 useK1VoucherCheck） */
import { ref, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'
import http from '@/utils/http'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()
const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const year = computed(() => props.year ?? new Date().getFullYear())
const allResponsesRef = computed(() => props.allResponses)

const {
  itemId, checkLabels,
  criteria, occurrenceRows, postCollectionRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked, postCollectionChecked,
  load, addOccurrenceRow, addPostCollectionRow, removeOccurrenceRow, removePostCollectionRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: 'K3-7-voucher-check' })

/**
 * 🔴 K3检查比例修正：期末余额检查金额=期后付款表借方合计（非贷方）
 * K1(应收)期后收款=贷方 → postCollectionChecked=Σ creditAmount ✓
 * K3(应付)期后付款=借方 → 应用Σ debitAmount
 * useK1VoucherCheck的postCollectionChecked用creditAmount是K1视角，K3需覆盖
 */
const k3PostPaymentChecked = computed(() =>
  postCollectionRows.value.reduce((s, r) => s + (Number(r.debitAmount) || 0), 0),
)

/**
 * 覆盖检查比例表：期末余额行用k3PostPaymentChecked替代postCollectionChecked
 */
const k3CheckRatios = computed(() => {
  const base = checkRatios.value
  if (base.length < 3) return base
  // 第3行是"期末余额"，需用借方合计
  return [
    base[0], // 本期借方
    base[1], // 本期贷方
    {
      ...base[2],
      checkedAmount: k3PostPaymentChecked.value,
      ratio: (base[2].bookAmount && base[2].bookAmount > 0) ? k3PostPaymentChecked.value / base[2].bookAmount : null,
    },
  ]
})

/** K3覆盖低比例警告（使用k3CheckRatios） */
const k3LowRatioWarnings = computed(() =>
  k3CheckRatios.value.filter(r => r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0),
)

/**
 * K3 核对标签覆盖：第5项"债务人"→"债权人"（K3是应付/负债，对方是债权人非债务人）
 */
const k3CheckLabels = checkLabels.map((label, i) =>
  i === 4 ? '债权人与交易对手核对一致' : label,
)

onMounted(() => load())

function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = k3CheckLabels.map((_, i) => vals.includes(i))
  persist()
}

const samplingVisible = ref(false)
const samplingTarget = ref<'occurrence' | 'post'>('occurrence')
function openSampling(target: 'occurrence' | 'post') { samplingTarget.value = target; samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) {
  fillFromSamples(samplingTarget.value, payload?.samples ?? [])
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
function handleAiGenerate() {
  // 接真实AI端点生成审计说明
  http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
    prompt: '请生成其他应付款(2241)凭证检查表审计说明，包含：测试总体覆盖情况、抽样方法合理性、检查比例分析、异常事项说明',
    context: JSON.stringify({
      科目: '2241其他应付款',
      方向: '贷方/负债类',
      认定: '存在/义务/计价和分摊',
      审计重点: '完整性(负债易少计)+反向截止',
      检查笔数_本期: String(occurrenceRows.value.length),
      检查笔数_期后: String(postCollectionRows.value.length),
      异常笔数: String(abnormalRows.value.length),
      借方检查比例: checkRatios.value[0]?.ratio != null ? `${(checkRatios.value[0].ratio * 100).toFixed(1)}%` : '未计算',
      贷方检查比例: checkRatios.value[1]?.ratio != null ? `${(checkRatios.value[1].ratio * 100).toFixed(1)}%` : '未计算',
    }),
    existingContent: auditNote.value || '',
    section: 'K3-7-voucher-check',
  }).then((res: any) => {
    const content = res?.data?.data?.content || res?.data?.content || ''
    if (content && !auditNote.value) {
      auditNote.value = content
      persist()
    } else if (content) {
      // 追加而非覆盖
      auditNote.value = `${auditNote.value}\n${content}`
      persist()
    }
  }).catch(() => { /* AI不可用静默降级 */ })
}
function handleReview() { openReviewDialog('K3-7-check') }
</script>

<style scoped>
.k3-tab-payable-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context { border-left: 4px solid var(--el-color-warning, #e6a23c); background: #fffbeb; padding: 10px 14px; margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
.methodology-context p { margin: 0 0 6px; }
.methodology-context p:last-child { margin-bottom: 0; }
.guide-banner { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%); border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
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
