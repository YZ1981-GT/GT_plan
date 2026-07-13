<template>
  <div class="k4-disclosure-listed">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 汇总表按项目列示期末/上年年末数（自动取数 K4-1）</div>
        <div class="guide-step"><span class="step-num">②</span> 短期应付债券明细（面值/票面利率/发行日期/期限/发行金额）</div>
        <div class="guide-step"><span class="step-num">③</span> 短期应付债券续表（计提利息/溢折价摊销/偿还/是否违约）</div>
        <div class="guide-step"><span class="step-num">④</span> 递延收益-政府补助情况（本期增减/形成原因）+ AI辅助</div>
      </div>
    </div>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">其他流动负债附注披露要求（上市公司）</div>
      <div class="methodology-content">
        按上市公司年报格式，其他流动负债披露：汇总表（短期应付债券/政府补助/待转销项税额/应付退货款）；
        短期应付债券应披露债券名称、面值、票面利率、发行日期、债券期限、发行金额，以及本期发行/按面值计提利息/溢折价摊销/本期偿还/期末数/是否违约；
        计入递延收益的政府补助按项目披露本期增减及形成原因。受益期在一年以内的政府补助在其他流动负债列报。
      </div>
    </div>

    <!-- （一）汇总表 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">（一）其他流动负债汇总</span>
          <el-button size="small" type="default" link @click="handleReview('disc-listed-summary')">💬</el-button>
        </div>
      </template>
      <el-table :data="summaryRows" border stripe size="small" class="disclosure-table">
        <el-table-column prop="item" label="项目" min-width="160" fixed />
        <el-table-column label="期末数" width="150" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly && !row.isTotal">
              <el-input-number :model-value="row.endBalance" :controls="false" size="small" @change="(v: number) => onSummaryEdit(row, 'endBalance', v)" />
            </template>
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末数" width="150" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly && !row.isTotal">
              <el-input-number :model-value="row.beginBalance" :controls="false" size="small" @change="(v: number) => onSummaryEdit(row, 'beginBalance', v)" />
            </template>
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="形成原因/备注" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && !row.isTotal" :model-value="row.remark" size="small" @change="(v: string) => onSummaryEdit(row, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- （二）短期应付债券明细 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">（二）短期应付债券明细</span>
          <el-button v-if="!isReadonly" size="small" @click="addBondRow()">＋ 新增债券</el-button>
        </div>
      </template>
      <el-table :data="bondRows" border size="small" class="disclosure-table">
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column label="债券名称" min-width="150">
          <template #default="{ row }"><el-input v-model="row.name" :disabled="isReadonly" size="small" @change="persistBonds" /></template>
        </el-table-column>
        <el-table-column label="面值" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.faceValue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistBonds" /></template>
        </el-table-column>
        <el-table-column label="票面利率" width="100" align="right">
          <template #default="{ row }"><el-input-number v-model="row.couponRate" :disabled="isReadonly" :controls="false" :precision="4" :step="0.001" size="small" class="dnum" @change="persistBonds" /></template>
        </el-table-column>
        <el-table-column label="发行日期" width="130">
          <template #default="{ row }"><el-input v-model="row.issueDate" :disabled="isReadonly" size="small" placeholder="YYYY-MM-DD" @change="persistBonds" /></template>
        </el-table-column>
        <el-table-column label="债券期限" width="110">
          <template #default="{ row }"><el-input v-model="row.term" :disabled="isReadonly" size="small" placeholder="如：1年" @change="persistBonds" /></template>
        </el-table-column>
        <el-table-column label="发行金额" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.issueAmount" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistBonds" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeBondRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
        <template #append><div class="table-total">发行金额小计：{{ fmtAmt(bondIssueTotal) }}</div></template>
      </el-table>
    </el-card>

    <!-- （三）短期应付债券（续）-->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">（三）短期应付债券（续）</span>
          <el-button v-if="!isReadonly" size="small" @click="addBondContRow()">＋ 新增</el-button>
        </div>
      </template>
      <el-table :data="bondContRows" border size="small" class="disclosure-table">
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column label="债券名称" min-width="140">
          <template #default="{ row }"><el-input v-model="row.name" :disabled="isReadonly" size="small" @change="persistBondCont" /></template>
        </el-table-column>
        <el-table-column label="上年年末数" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.beginBalance" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistBondCont" /></template>
        </el-table-column>
        <el-table-column label="本期发行" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.issued" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistBondCont" /></template>
        </el-table-column>
        <el-table-column label="按面值计提利息" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.interestAccrued" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistBondCont" /></template>
        </el-table-column>
        <el-table-column label="溢折价摊销" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.premiumAmort" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistBondCont" /></template>
        </el-table-column>
        <el-table-column label="本期偿还" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.repaid" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistBondCont" /></template>
        </el-table-column>
        <el-table-column label="期末数" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="上年年末+本期发行+计提利息+溢折价摊销−本期偿还" placement="top">
              <span class="formula-cell">{{ fmtAmt(bondContEnd(row)) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="是否违约" width="100" align="center">
          <template #default="{ row }">
            <el-select v-model="row.defaulted" :disabled="isReadonly" size="small" placeholder="选择" @change="persistBondCont">
              <el-option label="否" value="否" /><el-option label="是" value="是" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeBondContRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
      </el-table>
      <el-alert v-if="hasDefault" type="warning" :closable="false" show-icon class="default-warn">
        <template #title>存在违约债券，应关注交叉违约条款及披露充分性</template>
      </el-alert>
    </el-card>

    <!-- （四）递延收益-政府补助情况 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-title-row">
          <span class="section-title">（四）递延收益-政府补助情况</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="addGrantRow()">＋ 新增补助</el-button>
          </div>
        </div>
      </template>
      <el-table :data="grantRows" border size="small" class="disclosure-table">
        <el-table-column type="index" label="序" width="44" align="center" />
        <el-table-column label="补助项目" min-width="160">
          <template #default="{ row }"><el-input v-model="row.item" :disabled="isReadonly" size="small" @change="persistGrants" /></template>
        </el-table-column>
        <el-table-column label="上年年末数" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.beginBalance" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistGrants" /></template>
        </el-table-column>
        <el-table-column label="本期增加" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.increase" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistGrants" /></template>
        </el-table-column>
        <el-table-column label="本期减少" width="120" align="right">
          <template #default="{ row }"><el-input-number v-model="row.decrease" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="dnum" @change="persistGrants" /></template>
        </el-table-column>
        <el-table-column label="期末数" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="上年年末+本期增加−本期减少" placement="top">
              <span class="formula-cell">{{ fmtAmt(grantEnd(row)) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="形成原因" min-width="150">
          <template #default="{ row }"><el-input v-model="row.reason" :disabled="isReadonly" size="small" @change="persistGrants" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeGrantRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
        <template #append><div class="table-total">期末合计：{{ fmtAmt(grantEndTotal) }}</div></template>
      </el-table>
      <el-divider content-position="left">文字说明</el-divider>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="请填写其他流动负债披露文字说明（政府补助形成原因、债券违约情况说明等）..."
        @change="onNoteTextChange"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>汇总表期末/上年年末数应与 K4-1 审定表一致（监听 substantive:adjudicated 自动取数）</li>
        <li>短期应付债券续表期末数 = 上年年末 + 本期发行 + 按面值计提利息 + 溢折价摊销 − 本期偿还</li>
        <li>存在违约债券时应关注交叉违约条款并充分披露</li>
        <li>计入递延收益的政府补助，受益期一年以内在其他流动负债列报（详见附注政府补助）</li>
        <li>负债类科目关注完整性认定：确保所有应披露的其他流动负债已完整列示</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * Spec: k4-other-current-liabilities Task 4.6（源模板对齐重建）
 * 对齐致同源模板：汇总表(4类型) + 短期应付债券明细 + 续表(含是否违约) + 递延收益-政府补助情况。
 *
 * EventBus: subscribe 'substantive:adjudicated' → 汇总表自动取数
 *           publish 'disclosure:note-text-updated' on text change
 * 科目：2245 其他流动负债（负债类）
 */
import { ref, reactive, computed, inject, onMounted, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick, Delete } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

const K4_ACCOUNT_CODE = '2245'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── 数据模型 ─────────────────────────────────────────────────────────────────
interface SummaryRow { item: string; endBalance: number; beginBalance: number; remark: string; isTotal?: boolean }
interface BondRow { name: string; faceValue: number; couponRate: number; issueDate: string; term: string; issueAmount: number }
interface BondContRow { name: string; beginBalance: number; issued: number; interestAccrued: number; premiumAmort: number; repaid: number; defaulted: string }
interface GrantRow { item: string; beginBalance: number; increase: number; decrease: number; reason: string }

const SUMMARY_TYPES = ['短期应付债券', '政府补助', '待转销项税额', '应付退货款']

const summaryRows = reactive<SummaryRow[]>([
  ...SUMMARY_TYPES.map(item => ({ item, endBalance: 0, beginBalance: 0, remark: '' })),
  { item: '合计', endBalance: 0, beginBalance: 0, remark: '', isTotal: true },
])
const bondRows = ref<BondRow[]>([])
const bondContRows = ref<BondContRow[]>([])
const grantRows = ref<GrantRow[]>([])
const noteText = ref('')

// ─── 计算 ─────────────────────────────────────────────────────────────────────
function recalcSummaryTotal(): void {
  const total = summaryRows.find(r => r.isTotal)
  if (!total) return
  total.endBalance = summaryRows.filter(r => !r.isTotal).reduce((s, r) => s + (r.endBalance || 0), 0)
  total.beginBalance = summaryRows.filter(r => !r.isTotal).reduce((s, r) => s + (r.beginBalance || 0), 0)
}
const bondIssueTotal = computed(() => bondRows.value.reduce((s, r) => s + (r.issueAmount || 0), 0))
function bondContEnd(r: BondContRow): number {
  return (r.beginBalance || 0) + (r.issued || 0) + (r.interestAccrued || 0) + (r.premiumAmort || 0) - (r.repaid || 0)
}
const hasDefault = computed(() => bondContRows.value.some(r => r.defaulted === '是'))
function grantEnd(r: GrantRow): number { return (r.beginBalance || 0) + (r.increase || 0) - (r.decrease || 0) }
const grantEndTotal = computed(() => grantRows.value.reduce((s, r) => s + grantEnd(r), 0))

// ─── 汇总表自动取数（K4-1 审定合计）─────────────────────────────────────────────
function applyAutoFill(): void {
  const auditedTotal = getResponseNumber('K4-1-audited-total')
  const bondRow = summaryRows.find(r => r.item === '短期应付债券')
  // 仅在用户未手工填写时用审定合计作为参考（填到合计的备注提示）
  if (auditedTotal && bondRow && !bondRow.endBalance && summaryRows.filter(r => !r.isTotal).every(r => !r.endBalance)) {
    const total = summaryRows.find(r => r.isTotal)
    if (total) total.remark = `K4-1审定合计参考：${auditedTotal.toLocaleString('zh-CN')}`
  }
  recalcSummaryTotal()
}
function getResponseNumber(key: string): number {
  const item = props.allResponses.get(key)
  if (!item) return 0
  const val = item.remark ?? item.conclusion ?? item.value ?? item
  const n = typeof val === 'number' ? val : parseFloat(val)
  return Number.isFinite(n) ? n : 0
}

// ─── 持久化 ───────────────────────────────────────────────────────────────────
function persistSummary(): void {
  recalcSummaryTotal()
  emit('save', 'K4-disc-listed-summary', { remark: JSON.stringify(summaryRows) })
}
function persistBonds(): void { emit('save', 'K4-disc-listed-bonds', { remark: JSON.stringify(bondRows.value) }) }
function persistBondCont(): void { emit('save', 'K4-disc-listed-bond-cont', { remark: JSON.stringify(bondContRows.value) }) }
function persistGrants(): void { emit('save', 'K4-disc-listed-grants', { remark: JSON.stringify(grantRows.value) }) }
function persistNote(): void { emit('save', 'K4-disc-listed-note', { remark: noteText.value }) }

function onSummaryEdit(row: SummaryRow, field: string, value: any): void {
  ;(row as any)[field] = value ?? (field === 'remark' ? '' : 0)
  persistSummary()
}
function onNoteTextChange(): void {
  persistNote()
  try {
    eventBus.emit('disclosure:note-text-updated', { accountCode: K4_ACCOUNT_CODE, section: 'listed', text: noteText.value })
  } catch { /* silent */ }
}

// ─── 行操作 ───────────────────────────────────────────────────────────────────
function addBondRow(): void { bondRows.value.push({ name: '', faceValue: 0, couponRate: 0, issueDate: '', term: '', issueAmount: 0 }); persistBonds() }
function removeBondRow(i: number): void { bondRows.value.splice(i, 1); persistBonds() }
function addBondContRow(): void { bondContRows.value.push({ name: '', beginBalance: 0, issued: 0, interestAccrued: 0, premiumAmort: 0, repaid: 0, defaulted: '否' }); persistBondCont() }
function removeBondContRow(i: number): void { bondContRows.value.splice(i, 1); persistBondCont() }
function addGrantRow(): void { grantRows.value.push({ item: '', beginBalance: 0, increase: 0, decrease: 0, reason: '' }); persistGrants() }
function removeGrantRow(i: number): void { grantRows.value.splice(i, 1); persistGrants() }

// ─── AI辅助 ───────────────────────────────────────────────────────────────────
async function handleAiGenerate(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请生成其他流动负债附注（上市公司格式）中递延收益-政府补助及债券情况的披露文字说明',
      context: '科目:其他流动负债(2245) 负债类 含短期应付债券/政府补助/待转销项税额/应付退货款 关注完整性认定',
      existingContent: noteText.value || '',
      section: 'k4-disc-listed',
    })
    const generated = res.data?.data?.content || res.data?.content || ''
    if (!generated) { ElMessage.warning('AI未生成内容'); return }
    await ElMessageBox.confirm(
      `AI生成内容预览：\n\n${generated.slice(0, 300)}${generated.length > 300 ? '...' : ''}`,
      'AI生成确认',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    noteText.value = noteText.value ? `${noteText.value}\n${generated}` : generated
    onNoteTextChange()
    ElMessage.success('已填入AI生成内容')
  } catch { /* cancelled or error */ }
}

// ─── 加载（读 responses_snapshot 的 remark 键）────────────────────────────────
function _parse(key: string): any {
  const saved = props.allResponses.get(key)
  const raw = saved?.remark ?? saved?.conclusion ?? saved?.value ?? null
  if (!raw) return null
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw } catch { return null }
}
function loadSavedData(): void {
  const s = _parse('K4-disc-listed-summary')
  if (Array.isArray(s) && s.length) {
    for (const saved of s) {
      const target = summaryRows.find(r => r.item === saved.item)
      if (target) { target.endBalance = saved.endBalance || 0; target.beginBalance = saved.beginBalance || 0; target.remark = saved.remark || '' }
    }
  }
  const b = _parse('K4-disc-listed-bonds'); if (Array.isArray(b)) bondRows.value = b
  const bc = _parse('K4-disc-listed-bond-cont'); if (Array.isArray(bc)) bondContRows.value = bc
  const g = _parse('K4-disc-listed-grants'); if (Array.isArray(g)) grantRows.value = g
  const note = props.allResponses.get('K4-disc-listed-note')
  noteText.value = (note?.remark ?? note?.conclusion ?? note?.value ?? '') || ''
  recalcSummaryTotal()
}

// ─── EventBus ─────────────────────────────────────────────────────────────────
function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K4_ACCOUNT_CODE || payload.wpCode === 'K4') applyAutoFill()
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
})
onBeforeUnmount(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
})

function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k4-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.methodology-block { border-left: 4px solid #f59e0b; background: #fffbeb; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px; }
.methodology-title { font-weight: 600; color: #92400e; margin-bottom: 4px; font-size: 12px; }
.methodology-content { font-size: 12px; color: #78350f; line-height: 1.6; }
.disclosure-card { margin-bottom: 12px; }
.disclosure-card :deep(.el-card__header) { padding: 8px 14px; }
.disclosure-card :deep(.el-card__body) { padding: 12px 14px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; font-size: 14px; }
.title-actions { display: flex; gap: 8px; align-items: center; }
.disclosure-table { font-size: var(--wp-font-size, 13px); }
.dnum { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: #606266; font-weight: 600; }
.default-warn { margin-top: 10px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
