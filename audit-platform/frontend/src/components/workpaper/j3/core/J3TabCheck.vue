<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * J3TabCheck — J3-2 应付职工薪酬/股份支付检查表
 *
 * 对齐源模板「股份支付检查表J3-2」全 43 行结构：
 *  审计目标(5) + 二、审计过程[1.增减变动准确性测算(19列超宽表，引导式录入+差异勾稽) · 2.凭证检查表]
 *  + 三、审计说明 + 四、审计结论 + 现金结算专项提示(2 点)
 *
 * 宽表(19列)套 J3-1 引导式录入向导范式（点点点+测算vs账面差异实时分析）。
 * 持久化到 checklist_responses.remark（item_id J3-2-*），复用父 GtJ3 的 saveImmediate + allResponses。
 */
import { ref, reactive, computed, onMounted, watch } from 'vue'
import http from '@/utils/http'
import GtIndexChip from '../../GtIndexChip.vue'
import GtThTip from '../../GtThTip.vue'
import J3VariationDialog, { type VariationRow } from './J3VariationDialog.vue'

interface RespItem { item_id: string; conclusion: string | null; remark: string | null }
const props = defineProps<{
  wpId: string
  projectId: string
  year?: string | number
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, RespItem>
  isReadonly?: boolean
  saveImmediate?: (items: RespItem[]) => Promise<void> | void
}>()
const isReadonly = computed(() => props.isReadonly ?? false)

const KEY = { variation: 'J3-2-variation', vouchers: 'J3-2-vouchers', note: 'J3-2-note', conclusion: 'J3-2-conclusion' }

function n(v: unknown): number { const x = typeof v === 'number' ? v : parseFloat(String(v ?? '')); return Number.isFinite(x) ? x : 0 }
function fmt(v: number | null | undefined): string { if (v === null || v === undefined || v === 0) return '-'; return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

// ── 1. 增减变动准确性测算表（19 列，引导式录入） ──────────────────────────────
let vSeq = 1
const variationRows = reactive<VariationRow[]>([])
function diffSalary(r: VariationRow) { return n(r.calcSalary) - n(r.bookSalary) }
function diffExpense(r: VariationRow) { return n(r.calcExpense) - n(r.bookExpense) }
const vTotals = computed(() => ({
  totalPeople: variationRows.reduce((s, r) => s + n(r.totalPeople), 0),
  leftPeople: variationRows.reduce((s, r) => s + n(r.leftPeople), 0),
  exercisePeople: variationRows.reduce((s, r) => s + n(r.exercisePeople), 0),
  calcSalary: variationRows.reduce((s, r) => s + n(r.calcSalary), 0),
  bookSalary: variationRows.reduce((s, r) => s + n(r.bookSalary), 0),
  diffSalary: variationRows.reduce((s, r) => s + diffSalary(r), 0),
  cashPaid: variationRows.reduce((s, r) => s + n(r.cashPaid), 0),
  calcExpense: variationRows.reduce((s, r) => s + n(r.calcExpense), 0),
  bookExpense: variationRows.reduce((s, r) => s + n(r.bookExpense), 0),
  diffExpense: variationRows.reduce((s, r) => s + diffExpense(r), 0),
}))

const varDialogVisible = ref(false)
const editingVar = ref<VariationRow | null>(null)
function openAddVar() { if (isReadonly.value) return; editingVar.value = null; varDialogVisible.value = true }
function openEditVar(row: VariationRow) { if (isReadonly.value) return; editingVar.value = { ...row }; varDialogVisible.value = true }
function onVarSave(row: VariationRow) {
  const idx = variationRows.findIndex(r => r.id === row.id)
  if (idx >= 0) variationRows.splice(idx, 1, { ...row })
  else variationRows.push({ ...row, id: vSeq++ })
  scheduleSave()
}
function removeVar(id: number) {
  if (isReadonly.value) return
  const i = variationRows.findIndex(r => r.id === id)
  if (i >= 0) { variationRows.splice(i, 1); scheduleSave() }
}

// ── 2. 凭证检查表（行内录入） ─────────────────────────────────────────────────
interface VoucherRow {
  id: number; date: string; voucherType: string; voucherNo: string; businessContent: string
  detailAccount: string; counterAccount: string; debit: number; credit: number; attachment: string; conclusion: string
}
let vcSeq = 1
const voucherRows = reactive<VoucherRow[]>([])
function addVoucher() {
  if (isReadonly.value) return
  voucherRows.push({ id: vcSeq++, date: '', voucherType: '', voucherNo: '', businessContent: '', detailAccount: '', counterAccount: '', debit: 0, credit: 0, attachment: '', conclusion: '' })
  scheduleSave()
}
function removeVoucher(id: number) {
  if (isReadonly.value) return
  const i = voucherRows.findIndex(r => r.id === id)
  if (i >= 0) { voucherRows.splice(i, 1); scheduleSave() }
}

// ── 现金结算专项提示（源模板提示 2 点） ───────────────────────────────────────
const CASH_TIPS = [
  '检查完成等待期后的服务或达到规定业绩条件以后才可行权的以现金结算的股份支付：在等待期内每个资产负债表日，是否以可行权情况的最佳估计为基础，按承担负债的公允价值金额将当期取得的服务计入成本或费用；资产负债表日后续信息表明当期承担债务的公允价值与以前估计不同的，是否进行调整；并在可行权日调整至实际可行权水平。',
  '检查可行权日之后，以现金结算的股份支付当期公允价值的变动金额，是否借记或贷记"公允价值变动损益"。',
]

// ── 审计说明 / 结论 ───────────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
const aiLoading = ref('')

// ── 加载 / 保存 ───────────────────────────────────────────────────────────────
function parseArr<T>(id: string): T[] | null { const raw = props.allResponses?.get(id)?.remark; if (!raw) return null; try { const p = JSON.parse(raw); return Array.isArray(p) ? p : null } catch { return null } }
function load() {
  const v = parseArr<VariationRow>(KEY.variation)
  if (v) { variationRows.splice(0, variationRows.length, ...v.map((r, i) => ({ ...r, id: r.id ?? i + 1 }))); vSeq = Math.max(0, ...variationRows.map(r => r.id)) + 1 }
  const vc = parseArr<VoucherRow>(KEY.vouchers)
  if (vc) { voucherRows.splice(0, voucherRows.length, ...vc.map((r, i) => ({ ...r, id: r.id ?? i + 1 }))); vcSeq = Math.max(0, ...voucherRows.map(r => r.id)) + 1 }
  const nt = props.allResponses?.get(KEY.note)?.remark; if (nt) auditNote.value = nt
  const cc = props.allResponses?.get(KEY.conclusion)?.remark; if (cc) auditConclusion.value = cc
}
let timer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (isReadonly.value || !props.saveImmediate) return
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    props.saveImmediate?.([
      { item_id: KEY.variation, conclusion: null, remark: JSON.stringify(variationRows) },
      { item_id: KEY.vouchers, conclusion: null, remark: JSON.stringify(voucherRows) },
      { item_id: KEY.note, conclusion: null, remark: auditNote.value },
      { item_id: KEY.conclusion, conclusion: null, remark: auditConclusion.value },
    ])
  }, 800)
}

// ── AI 辅助 ───────────────────────────────────────────────────────────────────
async function aiGen(target: 'note' | 'conclusion') {
  if (isReadonly.value) return
  aiLoading.value = target
  try {
    const context: Record<string, string> = {
      科目: '应付职工薪酬-股份支付检查表（J3-2，CAS 11）',
      测算行数: String(variationRows.length),
      应付薪酬差异合计: fmt(vTotals.value.diffSalary),
      当期费用差异合计: fmt(vTotals.value.diffExpense),
      凭证检查笔数: String(voucherRows.length),
    }
    const existing = target === 'note' ? auditNote.value : auditConclusion.value
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, { section: `j3-2-${target}`, context, existingContent: existing })
    const d = (res as { data?: Record<string, any> })?.data
    const text = d?.data?.content || d?.content || d?.data?.text || d?.text || ''
    if (text) { if (target === 'note') auditNote.value = text; else auditConclusion.value = text; scheduleSave() }
  } catch { /* 静默 */ } finally { aiLoading.value = '' }
}

onMounted(load)
watch(() => props.allResponses, load, { deep: false })
</script>

<template>
  <div class="j3-tab-check">
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：①应付职工薪酬（股份支付）存在且记录于恰当账户；②所有应记录的及相关披露均已记录/包括（完整性）；③由被审计单位拥有或控制；④以恰当金额列示，计价/分摊调整已恰当记录，相关披露已恰当计量与描述；⑤已恰当汇总/分解且表述清楚。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="doc-title">应付职工薪酬-股份支付检查表</h3>
      <GtIndexChip value="wp:J3-1" :context-project-id="projectId" />
    </div>

    <!-- 现金结算专项提示（方法论） -->
    <details class="methodology-block" open>
      <summary>📖 现金结算股份支付检查要点（方法论参考 · CAS 11）</summary>
      <ol class="guide-list">
        <li v-for="(t, i) in CASH_TIPS" :key="i">{{ t }}</li>
      </ol>
    </details>

    <div class="proc-title">二、审计过程</div>

    <!-- 1. 增减变动准确性测算表 -->
    <div class="sec-head">
      <h4 class="sec-title">1. 抽查本期增减变动的准确性及会计处理的适当性</h4>
      <div class="toolbar-right">
        <el-tag size="small" type="info">共 {{ variationRows.length }} 条</el-tag>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="openAddVar">+ 引导式新增测算</el-button>
      </div>
    </div>
    <el-table :data="variationRows" border size="small" class="wp-table" style="width: 100%">
      <el-table-column label="序号" type="index" width="50" align="center" fixed />
      <el-table-column min-width="120" fixed>
        <template #header><GtThTip text="股份支付种类" /></template>
        <template #default="{ row }">{{ row.category || '-' }}</template>
      </el-table-column>
      <el-table-column width="110">
        <template #header><GtThTip text="时间" /></template>
        <template #default="{ row }">{{ row.time || '-' }}</template>
      </el-table-column>
      <el-table-column width="120" align="right">
        <template #header><GtThTip text="每股股票/每份增值权公允价值" /></template>
        <template #default="{ row }">{{ fmt(row.unitFV) }}</template>
      </el-table-column>
      <el-table-column width="120" align="right">
        <template #header><GtThTip text="每股股票/每份增值权支付现金" /></template>
        <template #default="{ row }">{{ fmt(row.unitCash) }}</template>
      </el-table-column>
      <el-table-column width="90" align="right">
        <template #header><GtThTip text="股份支付总人数" /></template>
        <template #default="{ row }">{{ row.totalPeople || '-' }}</template>
      </el-table-column>
      <el-table-column width="80" align="right">
        <template #header><GtThTip text="离职人数" /></template>
        <template #default="{ row }">{{ row.leftPeople || '-' }}</template>
      </el-table-column>
      <el-table-column width="80" align="right">
        <template #header><GtThTip text="行权人数" /></template>
        <template #default="{ row }">{{ row.exercisePeople || '-' }}</template>
      </el-table-column>
      <el-table-column width="100" align="right">
        <template #header><GtThTip text="每人获得的股份数量" /></template>
        <template #default="{ row }">{{ row.sharesPerPerson || '-' }}</template>
      </el-table-column>
      <el-table-column width="100" align="right">
        <template #header><GtThTip text="连续服务年限" /></template>
        <template #default="{ row }">{{ row.serviceYears || '-' }}</template>
      </el-table-column>
      <el-table-column width="120" align="right">
        <template #header><GtThTip text="测算应付职工薪酬金额" /></template>
        <template #default="{ row }">{{ fmt(row.calcSalary) }}</template>
      </el-table-column>
      <el-table-column width="120" align="right">
        <template #header><GtThTip text="账面应付职工薪酬金额" /></template>
        <template #default="{ row }">{{ fmt(row.bookSalary) }}</template>
      </el-table-column>
      <el-table-column width="110" align="right" class-name="auto-calc-col">
        <template #header><GtThTip text="差异（测算应付 − 账面应付）" /></template>
        <template #default="{ row }"><span :class="{ 'diff-warn': Math.abs(diffSalary(row)) >= 0.01 }">{{ fmt(diffSalary(row)) }}</span></template>
      </el-table-column>
      <el-table-column width="110" align="right">
        <template #header><GtThTip text="支付现金金额" /></template>
        <template #default="{ row }">{{ fmt(row.cashPaid) }}</template>
      </el-table-column>
      <el-table-column width="150" align="right">
        <template #header><GtThTip text="测算当期费用/公允价值变动金额" /></template>
        <template #default="{ row }">{{ fmt(row.calcExpense) }}</template>
      </el-table-column>
      <el-table-column width="150" align="right">
        <template #header><GtThTip text="账面记录当期费用/公允价值变动金额" /></template>
        <template #default="{ row }">{{ fmt(row.bookExpense) }}</template>
      </el-table-column>
      <el-table-column width="110" align="right" class-name="auto-calc-col">
        <template #header><GtThTip text="差异（测算费用 − 账面费用）" /></template>
        <template #default="{ row }"><span :class="{ 'diff-warn': Math.abs(diffExpense(row)) >= 0.01 }">{{ fmt(diffExpense(row)) }}</span></template>
      </el-table-column>
      <el-table-column width="110" align="center">
        <template #header><GtThTip text="是否为雇员或其他提供类似服务的人员" /></template>
        <template #default="{ row }"><el-tag v-if="row.isEmployee" :type="row.isEmployee === '是' ? 'success' : 'danger'" size="small">{{ row.isEmployee }}</el-tag><span v-else>-</span></template>
      </el-table-column>
      <el-table-column width="100" align="center">
        <template #header><GtThTip text="主要条款及条件与股份支付薪酬工具是否一致" /></template>
        <template #default="{ row }"><el-tag v-if="row.termsConsistent" :type="row.termsConsistent === '是' ? 'success' : 'danger'" size="small">{{ row.termsConsistent }}</el-tag><span v-else>-</span></template>
      </el-table-column>
      <el-table-column width="100" align="center">
        <template #header><GtThTip text="授权日与行权日之间是否存在重大时间间隔" /></template>
        <template #default="{ row }"><el-tag v-if="row.bigTimeGap" :type="row.bigTimeGap === '否' ? 'success' : 'warning'" size="small">{{ row.bigTimeGap }}</el-tag><span v-else>-</span></template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="90" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openEditVar(row)">编辑</el-button>
          <el-button type="danger" link size="small" @click="removeVar(row.id)">删</el-button>
        </template>
      </el-table-column>
      <template #empty><span class="empty-hint">暂无测算数据。点击"+ 引导式新增测算"打开录入向导（含测算 vs 账面差异勾稽分析）。</span></template>
    </el-table>
    <div v-if="variationRows.length" class="totals-bar">
      合计：总人数 {{ vTotals.totalPeople }} ｜ 离职 {{ vTotals.leftPeople }} ｜ 行权 {{ vTotals.exercisePeople }} ｜
      测算应付 {{ fmt(vTotals.calcSalary) }} ｜ 账面应付 {{ fmt(vTotals.bookSalary) }} ｜
      <span :class="{ 'diff-warn': Math.abs(vTotals.diffSalary) >= 0.01 }">应付差异 {{ fmt(vTotals.diffSalary) }}</span> ｜
      测算费用 {{ fmt(vTotals.calcExpense) }} ｜ 账面费用 {{ fmt(vTotals.bookExpense) }} ｜
      <span :class="{ 'diff-warn': Math.abs(vTotals.diffExpense) >= 0.01 }">费用差异 {{ fmt(vTotals.diffExpense) }}</span>
    </div>

    <!-- 2. 凭证检查表 -->
    <div class="sec-head">
      <h4 class="sec-title">2. 抽查本期增减变动凭证（准确性及会计处理适当性）</h4>
      <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addVoucher">+ 新增凭证</el-button>
    </div>
    <el-table :data="voucherRows" border size="small" class="wp-table" style="width: 100%">
      <el-table-column label="日期" width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="scheduleSave" /><span v-else>{{ row.date }}</span></template>
      </el-table-column>
      <el-table-column label="凭证种类" width="100">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherType" size="small" @change="scheduleSave" /><span v-else>{{ row.voucherType }}</span></template>
      </el-table-column>
      <el-table-column label="凭证编号" width="110">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="scheduleSave" /><span v-else>{{ row.voucherNo }}</span></template>
      </el-table-column>
      <el-table-column label="业务内容" min-width="160">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="scheduleSave" /><span v-else>{{ row.businessContent }}</span></template>
      </el-table-column>
      <el-table-column label="明细科目" width="130">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.detailAccount" size="small" @change="scheduleSave" /><span v-else>{{ row.detailAccount }}</span></template>
      </el-table-column>
      <el-table-column label="对方科目" width="130">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" @change="scheduleSave" /><span v-else>{{ row.counterAccount }}</span></template>
      </el-table-column>
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }"><WpAmountInput v-if="!isReadonly" v-model="row.debit" size="small" @change="scheduleSave" /><span v-else>{{ fmt(row.debit) }}</span></template>
      </el-table-column>
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }"><WpAmountInput v-if="!isReadonly" v-model="row.credit" size="small" @change="scheduleSave" /><span v-else>{{ fmt(row.credit) }}</span></template>
      </el-table-column>
      <el-table-column label="附件" width="120">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.attachment" size="small" placeholder="附件索引/说明" @change="scheduleSave" /><span v-else>{{ row.attachment }}</span></template>
      </el-table-column>
      <el-table-column label="结论" min-width="140">
        <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="scheduleSave" /><span v-else>{{ row.conclusion }}</span></template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
        <template #default="{ row }"><el-button type="danger" link size="small" @click="removeVoucher(row.id)">删</el-button></template>
      </el-table-column>
      <template #empty><span class="empty-hint">暂无凭证。点击"+ 新增凭证"抽查本期增减变动凭证。</span></template>
    </el-table>

    <!-- 三、审计说明 -->
    <div class="note-wrap">
      <div class="note-hd"><span>三、审计说明</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'note'" :disabled="isReadonly" @click="aiGen('note')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="概述测试情况与结果：测算与账面差异及原因、会计处理适当性、拟调整/未调整事项及其影响等。" @change="scheduleSave" />
    </div>

    <!-- 四、审计结论 -->
    <div class="note-wrap">
      <div class="note-hd"><span>四、审计结论</span>
        <el-button size="small" type="primary" plain :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="aiGen('conclusion')">🤖 AI辅助</el-button>
      </div>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="请输入审计结论，或点击 AI 辅助生成（如：未见异常；或除上述调整事项外其余未见异常等）。" @change="scheduleSave" />
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按股份支付种类分别测算应付职工薪酬与当期费用/公允价值变动，与账面比对，差异自动计算，须查明差异原因。</p>
        <p>2. 权益结算按授予日公允价值等待期内分摊（贷记资本公积 M4）；现金结算每个资产负债表日按公允价值重新计量（贷记应付职工薪酬 J1），可行权日后公允价值变动计入"公允价值变动损益"。</p>
        <p>3. 逐笔抽查增减变动凭证，核对明细/对方科目、借贷方金额与附件，形成结论。</p>
        <p>4. 检查结论存在不符合事项的，须在审计说明中列明并评估对财务报表的影响。</p>
      </div>
    </details>

    <!-- 引导式新增/编辑测算弹窗 -->
    <J3VariationDialog v-model="varDialogVisible" :row="editingVar" :is-readonly="isReadonly" @save="onVarSave" />
  </div>
</template>

<style scoped>
.j3-tab-check { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.doc-title { font-size: 15px; font-weight: 600; margin: 0; }
.methodology-block { margin-bottom: 14px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 4px; padding: 8px 12px; }
.methodology-block summary { cursor: pointer; font-weight: 600; color: #b88230; }
.guide-list { margin: 10px 0 2px; padding-left: 20px; font-size: 12px; color: #8c6d1f; line-height: 1.7; }
.guide-list li { margin-bottom: 6px; }
.proc-title { font-size: 14px; font-weight: 600; color: #303133; margin: 8px 0; }
.sec-head { display: flex; align-items: center; justify-content: space-between; margin: 18px 0 8px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.wp-table { width: 100%; font-size: 13px; }
.wp-table :deep(.el-table__cell) { padding: 3px 4px; font-size: 13px; }
.wp-table :deep(.el-input-number) { width: 100%; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.empty-hint { font-size: 12px; color: #909399; }
.totals-bar { margin-top: 8px; padding: 6px 12px; background: #f5f7fa; border-radius: 4px; font-size: 13px; font-weight: 500; color: #303133; }
.note-wrap { margin-top: 14px; }
.note-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: #303133; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
