<!--
  J1TabGeneralCheck.vue — J1-8 应付职工薪酬检查表（凭证级测试 · 卡片+矩阵）

  致同源模板 J1-8：
    一、测试目标（发生/完整性准确性/截止）
    二、样本选取标准与规模
    三、测试（三区凭证检查：贷方计提+借方发放+期后支付）——卡片视图/矩阵视图双模
    四、审计说明 — 检查比例
    五、审计结论

  复用 useK1VoucherCheck（科目 2211 应付职工薪酬 贷方/负债类）。
  卡片视图：每笔凭证一张可展开卡片，含证据区 📎 上传 + OCR 识别回填。
  矩阵视图：紧凑核对状态矩阵，一屏纵览。
-->
<template>
  <div class="j1-general-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认测试目标</div>
      <div class="guide-step"><span class="gs-no">2</span>样本选取标准</div>
      <div class="guide-step"><span class="gs-no">3</span>凭证级测试（三区）</div>
      <div class="guide-step"><span class="gs-no">4</span>检查比例+结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">J1-8 应付职工薪酬检查表</h3>
      <div class="head-actions">
        <el-segmented v-model="viewMode" :options="viewOptions" size="small" />
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('voucher')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('voucher')">导出数据</el-dropdown-item>
              <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
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
        <li><b>发生：</b>利润表中记录的应付职工薪酬计提已发生且与被审计单位有关；</li>
        <li><b>完整性与准确性：</b>所有应计提的职工薪酬均已记录，金额恰当（人数×单价×月数与审批一致）；</li>
        <li><b>截止：</b>薪酬计提/发放已记录于正确的会计期间（跨期计提完整性）。</li>
      </ol>
    </el-alert>

    <!-- 方法论（琥珀色） -->
    <div class="methodology-context">
      <p>应付职工薪酬（2211）为<strong>贷方/负债类</strong>科目（期末=期初+贷方-借方）。贷方检查对应<strong>计提/增加</strong>（检查凭证+薪酬计算表/审批单）；借方检查对应<strong>发放/减少</strong>（付款审批单+银行回单+代扣代缴凭证）；期后支付检查用于验证资产负债表日应付未付薪酬的<strong>完整性</strong>（是否存在漏提）。核对要点：①原始凭证齐全 ②与记账凭证相符 ③计算正确（人数/比例/月份） ④审批手续完整 ⑤期间归属正确。</p>
    </div>

    <!-- 在线编辑（OnlyOffice 编辑整张 J1-8 sheet） -->
    <div v-if="viewMode === 'excel'" class="oo-wrap">
      <el-alert type="info" :closable="false" show-icon class="oo-tip">
        <template #title>在线编辑模式直接编辑 J1-8 Excel 原表（与卡片/矩阵为同一底稿的不同呈现，适合习惯 Excel 操作或复杂公式场景）。</template>
      </el-alert>
      <GtOnlyOfficeSheet :wp-id="props.wpId" sheet-name="检查表J1-8" :project-id="props.projectId" />
    </div>

    <!-- 结构化视图（卡片/矩阵） -->
    <template v-else>
    <!-- 二、样本选取 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（贷方发生额）<el-button v-if="!isReadonly" size="small" type="primary" link :loading="autoFetchLoading" @click="autoFetchPopulation" style="margin-left:6px">🔄 自动取数</el-button></label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（借方发生额）<el-button v-if="!isReadonly" size="small" type="primary" link :loading="autoFetchLoading" @click="autoFetchPopulation" style="margin-left:6px">🔄 自动取数</el-button></label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额单笔计提（XX万以上）、关联方代付、非常规薪酬项目全部测试" @change="persist" />
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
          <div class="sampling-process-row">
            <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" size="small"
              placeholder="使用IDEA选取XX笔贷方计提+XX笔借方发放进行检查" @change="persist" />
            <el-button v-if="!isReadonly" size="small" type="primary" plain :loading="aiSamplingLoading" @click="generateSamplingProcess" class="ai-sampling-btn">🤖</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 三、测试 — 三区 -->
    <template v-for="grp in groups" :key="grp.key">
      <el-card shadow="never" class="section-card">
        <template #header>
          <div class="card-header-row">
            <span class="card-title">{{ grp.title }}</span>
            <div class="grp-actions">
              <span class="grp-total">合计 {{ fmtAmt(grp.total.value) }}</span>
              <el-button v-if="!isReadonly && grp.key !== 'post'" size="small" type="primary" plain @click="openSampling(grp.key)"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
              <el-button v-if="!isReadonly" size="small" @click="addRow(grp.key)">＋ 新增凭证</el-button>
            </div>
          </div>
        </template>

        <!-- 卡片视图 -->
        <div v-if="viewMode === 'card'">
          <J1VoucherCard
            v-for="(row, idx) in grp.rows.value"
            :key="row.id"
            :row="row"
            :seq="idx + 1"
            :direction="grp.key"
            :check-labels="grp.key === 'debit' ? debitCheckLabels : checkLabels"
            :is-readonly="isReadonly"
            :ocr-loading-id="ocrLoadingId"
            @change="persist"
            @remove="(id) => removeRow(grp.key, id)"
            @upload="onCardUpload"
          />
          <el-empty v-if="grp.rows.value.length === 0" description="暂无凭证，点击「＋新增凭证」或「抽凭」" :image-size="60" />
        </div>

        <!-- 矩阵视图 -->
        <el-table v-else :data="grp.rows.value" border size="small" :max-height="400" class="matrix-table" :row-class-name="abnormalRowClass">
          <el-table-column label="#" type="index" width="42" align="center" />
          <el-table-column label="薪酬项目" min-width="120">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
          </el-table-column>
          <el-table-column label="凭证编号" width="110">
            <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
          </el-table-column>
          <el-table-column :label="grp.key === 'credit' ? '贷方金额' : '借方/支付金额'" width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row[grp.key === 'credit' ? 'creditAmount' : 'debitAmount']" :controls="false" size="small" class="amount-input" @change="persist" />
              <span v-else class="amount-cell">{{ fmtAmt(row[grp.key === 'credit' ? 'creditAmount' : 'debitAmount']) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="核对内容（点击色块切换）" min-width="190" align="center">
            <template #header>
              <el-tooltip placement="top">
                <template #content><div v-for="(lbl, i) in (grp.key === 'debit' ? debitCheckLabels : checkLabels)" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
                <span class="col-help">核对内容 ⓘ</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="matrix-cells">
                <span
                  v-for="(lbl, i) in (grp.key === 'debit' ? debitCheckLabels : checkLabels)"
                  :key="i"
                  class="mx-cell"
                  :class="{ on: row.checks[i], off: !row.checks[i] }"
                  :title="lbl"
                  @click="toggleCheck(row, i)"
                >{{ i + 1 }}</span>
              </span>
            </template>
          </el-table-column>
          <el-table-column label="证据" width="70" align="center">
            <template #default="{ row }">
              <el-tag v-if="attachmentCount(row) > 0" size="small" type="success" effect="plain">📎{{ attachmentCount(row) }}</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="异常" width="64" align="center">
            <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
            <template #default="{ row }"><el-button size="small" type="danger" link @click="removeRow(grp.key, row.id)">删除</el-button></template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <!-- 四、审计说明 — 检查比例 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="j1CheckRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="140" />
        <el-table-column label="本期发生额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span></template></el-table-column>
        <el-table-column label="检查金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template></el-table-column>
        <el-table-column label="检查比例" width="130" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'" size="small" effect="plain">{{ (row.ratio * 100).toFixed(1) }}%</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%），应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <div class="note-label-row">
          <label>审计说明</label>
          <el-button v-if="!isReadonly" size="small" type="primary" plain :loading="aiNoteLoading" @click="generateAuditNote">🤖 AI补充异常分析</el-button>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="说明检查过程/发现/比例合理性..." @change="persist" />
      </div>
    </el-card>

    <!-- 异常摘要 -->
    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>
    </template>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 9 职工薪酬 + 审计准则）</summary>
      <ul>
        <li>科目 2211 应付职工薪酬（贷方/负债类），期末=期初+贷方-借方</li>
        <li>贷方检查=计提/增加（工资/社保/公积金/福利/工会经费），核对薪酬计算表+审批</li>
        <li>借方检查=发放/减少（银行转账/现金/代扣代缴），核对付款审批+银行回单+个税代扣</li>
        <li>核对内容：①原始凭证齐全 ②与记账凭证相符 ③计算正确 ④审批手续完整 ⑤期间归属正确</li>
        <li>期后支付检查：资产负债表日后支付的薪酬中属于报告期应计未计部分→漏提</li>
        <li>重点关注：年终奖跨期计提/社保基数调整/高管薪酬/辞退福利确认</li>
      </ul>
    </details>

    <!-- 抽凭引擎 -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 应付职工薪酬(2211)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2211" :phase="samplingPhase" :workpaper-id="props.wpId" :project-id="props.projectId" :year="yearNum" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * J1TabGeneralCheck — J1-8 应付职工薪酬凭证级检查表（卡片+矩阵+OCR）
 * 科目 2211（贷方/负债类）。三区：贷方计提+借方发放+期后支付。
 * 复用 useK1VoucherCheck composable + useJ1VoucherOcr 行级 OCR。
 * 自持久化模式（J1 composable-internal persist pattern）。
 */
import { ref, reactive, computed, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'
import { useJ1VoucherOcr } from '@/composables/workpaper/j1/useJ1VoucherOcr'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import J1VoucherCard from './J1VoucherCard.vue'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('../../GtOnlyOfficeSheet.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const isReadonly = computed(() => false)
const yearNum = computed(() => {
  const d = props.htmlData as any
  return d?.year ?? new Date().getFullYear()
})

// 视图模式
const viewMode = ref<'card' | 'matrix' | 'excel'>('card')
const viewOptions = [
  { label: '📇 卡片视图', value: 'card' },
  { label: '▦ 矩阵视图', value: 'matrix' },
  { label: '📊 在线编辑', value: 'excel' },
]

// ─── 本地 allResponses Map（自持久化） ────────────────────────────────────────
const localAllResponses = ref(new Map<string, any>())
const allResponsesRef = computed(() => localAllResponses.value)
const ITEM_ID = 'J1-8-voucher-check'

const {
  checkLabels,
  criteria, occurrenceRows, postCollectionRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceCreditChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  addPostCollectionRow, removePostCollectionRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: ITEM_ID })

const { ocrLoadingId, uploadAndMerge } = useJ1VoucherOcr(computed(() => props.wpId))
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)

// 借方检查的核对内容标签（发放）
const debitCheckLabels = [
  '付款审批单齐全', '银行回单/转账凭证', '代扣代缴凭证（个税/社保/公积金）', '与薪酬发放表相符', '发放金额与审批一致',
]

const j1CheckRatios = computed(() => checkRatios.value)

// 期后支付区（独立管理）
const postPeriodRows = ref<K1VoucherRow[]>([])
const postDebitChecked = computed(() => postCollectionRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))
const postPeriodTotal = computed(() => postPeriodRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))

// 三区分组定义（供 v-for 渲染卡片/矩阵）
const groups = [
  { key: 'credit' as const, title: '三-A、贷方检查（计提/增加）', rows: occurrenceRows, total: occurrenceCreditChecked },
  { key: 'debit' as const, title: '三-B、借方检查（发放/减少）', rows: postCollectionRows, total: postDebitChecked },
  { key: 'post' as const, title: '三-C、期后支付检查（完整性验证）', rows: postPeriodRows, total: postPeriodTotal },
]

function addRow(key: 'credit' | 'debit' | 'post') {
  if (key === 'credit') addOccurrenceRow()
  else if (key === 'debit') addPostCollectionRow()
  else postPeriodRows.value.push({
    id: `pp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    debtorName: '', date: '', voucherNo: '', businessContent: '',
    offsetAccount: '', offsetSubAccount: '', creditAmount: 0, debitAmount: 0,
    supportingDoc: '', checks: [false, false, false, false, false],
    abnormal: false, indexNo: '', remark: '',
  })
  persist()
}
function removeRow(key: 'credit' | 'debit' | 'post', id: string) {
  if (key === 'credit') removeOccurrenceRow(id)
  else if (key === 'debit') removePostCollectionRow(id)
  else postPeriodRows.value = postPeriodRows.value.filter(r => r.id !== id)
  persist()
}

// 矩阵视图核对色块切换
function toggleCheck(row: K1VoucherRow, i: number) {
  if (isReadonly.value) return
  const next = [...row.checks]
  next[i] = !next[i]
  row.checks = next
  persist()
}
function attachmentCount(row: any): number {
  const a = row.attachments
  return a ? Object.keys(a).length : 0
}

// 卡片证据上传 → OCR
function onCardUpload(payload: { rowId: string; file: File; evidenceKey: string }) {
  const allRows = [...occurrenceRows.value, ...postCollectionRows.value, ...postPeriodRows.value]
  const row = allRows.find(r => r.id === payload.rowId)
  if (!row) return
  const direction: 'credit' | 'debit' | 'post' =
    occurrenceRows.value.some(r => r.id === payload.rowId) ? 'credit'
    : postCollectionRows.value.some(r => r.id === payload.rowId) ? 'debit' : 'post'
  uploadAndMerge(payload.rowId, payload.file, direction, (id, patch) => {
    const target = allRows.find(r => r.id === id) as any
    if (target) {
      Object.assign(target, patch)
      // 同步 OCR 结果到对应外部单据的独立字段
      if (!target.evidence) target.evidence = { calc: { month: '', amount: 0, approved: '' }, approval: { dateNo: '', approved: '' }, bank: { date: '', summary: '', amount: 0 } }
      const amt = patch.creditAmount ?? patch.debitAmount
      const key = payload.evidenceKey
      if (key === 'calc') {
        if (patch.date) target.evidence.calc.month = patch.date
        if (amt) target.evidence.calc.amount = amt
      } else if (key === 'approval') {
        if (patch.voucherNo || patch.date) target.evidence.approval.dateNo = patch.voucherNo || patch.date
      } else if (key === 'bank') {
        if (patch.date) target.evidence.bank.date = patch.date
        if (amt) target.evidence.bank.amount = amt
        if (patch.businessContent) target.evidence.bank.summary = patch.businessContent
      }
    }
    persist()
  })
}

// ─── selfLoad 从 checklist-responses 恢复 ────────────────────────────────────
async function reloadFromServer() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items: Array<{ item_id: string; remark?: string; conclusion?: string }> = res.data?.data || res.data || []
    for (const item of items) {
      if (item.item_id === ITEM_ID) {
        localAllResponses.value.set(ITEM_ID, { item_id: ITEM_ID, remark: item.remark, conclusion: item.conclusion })
      }
      if (item.item_id === 'J1-8-post-period') {
        try { postPeriodRows.value = JSON.parse(item.remark || '[]') } catch { /* */ }
      }
    }
    load()
  } catch (e) {
    console.warn('[J1-8] selfLoad failed:', e)
  }
}
onMounted(reloadFromServer)

// 导入数据（xlsx）→ 成功后从服务端重载三区
function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0]
    if (!f) return
    const ok = await importData('voucher', f)
    if (ok) await reloadFromServer()
  }
  input.click()
}

// ─── Persistence ─────────────────────────────────────────────────────────────
let persistTimer: ReturnType<typeof setTimeout> | null = null
function persist() {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(doPersist, 800)
}
async function doPersist() {
  try {
    const data = serialize()
    localAllResponses.value.set(ITEM_ID, { item_id: ITEM_ID, remark: data, conclusion: null })
    const items = [
      { item_id: ITEM_ID, remark: data, conclusion: conclusion.value || null },
      { item_id: 'J1-8-post-period', remark: JSON.stringify(postPeriodRows.value), conclusion: null },
    ]
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
  } catch (e) {
    console.warn('[J1-8] persist failed:', e)
  }
}

// ─── 抽凭 ────────────────────────────────────────────────────────────────────
const samplingVisible = ref(false)
const samplingPhase = ref<'current' | 'post'>('current')
function openSampling(direction: 'credit' | 'debit' | 'post') {
  samplingPhase.value = direction === 'credit' ? 'current' : 'post'
  samplingVisible.value = true
}
function onSamplesFilled(payload: { samples: any[] }) {
  const target = samplingPhase.value === 'current' ? 'occurrence' : 'post'
  fillFromSamples(target, payload?.samples ?? [])
  samplingVisible.value = false
  persist()
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
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function abnormalRowClass({ row }: { row: K1VoucherRow }): string { return row.abnormal ? 'abnormal-row' : '' }

// ─── AI ──────────────────────────────────────────────────────────────────────
const aiSamplingLoading = ref(false)
const aiNoteLoading = ref(false)
const autoFetchLoading = ref(false)

async function autoFetchPopulation() {
  if (isReadonly.value) return
  autoFetchLoading.value = true
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { year: yearNum.value }, _silent: true,
    } as any)
    const items = res.data?.data || res.data || []
    const allRows = Array.isArray(items) ? items : []
    const matched = allRows.filter((r: any) => {
      const code = r.standard_account_code || r.account_code || ''
      return code === '2211' || code.startsWith('2211')
    })
    if (matched.length > 0) {
      let creditTotal = 0, debitTotal = 0
      for (const tb of matched) {
        creditTotal += Math.abs(tb.credit_amount || tb.period_credit || 0)
        debitTotal += Math.abs(tb.debit_amount || tb.period_debit || 0)
      }
      if (creditTotal === 0 && debitTotal === 0 && matched[0].unadjusted_amount) {
        creditTotal = Math.abs(matched[0].unadjusted_amount)
      }
      if (creditTotal > 0) criteria.value.populationCreditAmount = creditTotal
      if (debitTotal > 0) criteria.value.populationDebitAmount = debitTotal
      persist()
      ElMessage.success(`已从试算表取数（科目2211系${matched.length}条）：贷方${fmtAmt(creditTotal)}，借方${fmtAmt(debitTotal)}`)
    } else {
      ElMessage.warning('试算表中未找到科目2211，请确认四表库已导入该科目')
    }
  } catch {
    ElMessage.warning('自动取数失败，请手动填写')
  } finally {
    autoFetchLoading.value = false
  }
}

async function generateSamplingProcess() {
  if (isReadonly.value) return
  aiSamplingLoading.value = true
  try {
    const ctx = {
      '测试总体(贷方)': `${criteria.value.populationCreditCount || 0}笔/${criteria.value.populationCreditAmount || 0}元`,
      '测试总体(借方)': `${criteria.value.populationDebitCount || 0}笔/${criteria.value.populationDebitAmount || 0}元`,
      '特定样本': criteria.value.specificSample || '未填',
      '抽样总体': `${criteria.value.samplingPopulationCount || 0}笔/${criteria.value.samplingPopulationAmount || 0}元`,
      '样本量': `${criteria.value.sampleSize || 0}笔`,
      '抽样方法': criteria.value.samplingMethod || '未选择',
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'j1-8-sampling-process',
      prompt: '根据以下样本选取标准信息，生成简洁的抽样过程描述：',
      context: ctx,
      existingContent: criteria.value.samplingProcess || '',
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) { criteria.value.samplingProcess = text; persist() }
  } catch { /* silent */ }
  finally { aiSamplingLoading.value = false }
}

async function generateAuditNote() {
  if (isReadonly.value) return
  aiNoteLoading.value = true
  try {
    const abnormalList = abnormalRows.value.map(r => `${r.debtorName || '未填'}(凭证${r.voucherNo || '-'}): ${r.remark || '未说明'}`)
    const ratioInfo = j1CheckRatios.value.map(r => `${r.direction} 检查比例${r.ratio != null ? (r.ratio * 100).toFixed(1) + '%' : '—'}`)
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'j1-8-audit-note',
      prompt: '根据检查比例与异常凭证情况，生成审计说明，重点对异常项进行分析补充：',
      context: {
        '检查比例': ratioInfo.join('；'),
        '异常凭证': abnormalList.length ? abnormalList.join('；') : '无异常',
        '贷方检查笔数': occurrenceRows.value.length,
        '借方检查笔数': postCollectionRows.value.length,
      },
      existingContent: auditNote.value || '',
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) { auditNote.value = text; persist() }
  } catch { ElMessage.warning('AI 生成失败') }
  finally { aiNoteLoading.value = false }
}

async function handleAiGenerate() {
  try {
    await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'voucher-check',
      prompt: '请基于已检查的薪酬凭证情况，生成审计说明',
      context: { itemId: ITEM_ID, occurrenceCount: occurrenceRows.value.length, postCount: postCollectionRows.value.length },
    })
  } catch { /* */ }
}
function handleReview() { /* 复核对话暂桩 */ }
</script>

<style scoped>
.j1-general-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%); border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 10px; align-items: center; }
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
.grp-actions { display: flex; align-items: center; gap: 10px; }
.grp-total { font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }
.criteria-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 18px; }
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item.cg-full { grid-column: 1 / -1; }
.cg-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.cg-inline { display: flex; align-items: center; gap: 5px; }
.sampling-process-row { display: flex; gap: 6px; align-items: flex-start; }
.sampling-process-row .el-textarea { flex: 1; }
.ai-sampling-btn { flex-shrink: 0; margin-top: 2px; }
.cg-unit { font-size: 12px; color: var(--el-text-color-secondary); }
.num-sm { width: 78px; }
.num-md { width: 130px; }
.oo-wrap { margin-bottom: 10px; }
.oo-tip { margin-bottom: 10px; }
.matrix-table { font-size: var(--wp-font-size, 13px); }
.matrix-table :deep(th), .matrix-table :deep(td) { font-size: 13px; }
.matrix-table :deep(.abnormal-row td) { background-color: #fef2f2 !important; }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.col-help { cursor: help; border-bottom: 1px dashed var(--el-border-color); }
.matrix-cells { display: inline-flex; gap: 4px; }
.mx-cell { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 4px; font-size: 12px; cursor: pointer; user-select: none; transition: all 0.15s; }
.mx-cell.on { background: #10b981; color: #fff; font-weight: 600; }
.mx-cell.off { background: #f1f5f9; color: #94a3b8; }
.mx-cell:hover { transform: scale(1.1); }
.ratio-table { max-width: 640px; }
.ratio-warn { margin-top: 12px; }
.muted { color: var(--el-text-color-placeholder); }
.note-block { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
.note-label-row { display: flex; align-items: center; justify-content: space-between; }
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
