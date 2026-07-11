<template>
  <div class="h7-tab-adjudication-cost">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：确认生产性生物资产（科目1621）成本模式下原值、累计折旧、减值准备的期末余额存在、完整、准确，
        净值列报恰当（成本 - 累计折旧 - 减值准备）。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">成本模式 · 共 3 区块</el-tag>
    </div>

    <!-- 一、生产性生物资产原值（1621） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、生产性生物资产原值（科目1621）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi('cost-orig')"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" link @click="handleReview('H7-1-cost-orig')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="origDisplayRows" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="项目" min-width="140" fixed />
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.editable && !isReadonly" v-model="row.begin" :controls="false" size="small" class="amt-input" @change="onOrig()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方(增加)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.editable && !isReadonly" v-model="row.debit" :controls="false" size="small" class="amt-input" @change="onOrig()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方(减少)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.editable && !isReadonly" v-model="row.credit" :controls="false" size="small" class="amt-input" @change="onOrig()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="资产类期末=期初+借方-贷方">{{ fmtAmt(assetEnd(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell tb-auto" title="TB自动取数(1621期末余额)">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.editable && !isReadonly" v-model="row.aje" :controls="false" size="small" class="amt-input" @change="onOrig()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.editable && !isReadonly" v-model="row.rje" :controls="false" size="small" class="amt-input" @change="onOrig()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE+RJE">{{ fmtAmt(auditedOf(row)) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 二、累计折旧（备抵） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、累计折旧（备抵科目）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi('cost-dep')"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" link @click="handleReview('H7-1-cost-dep')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="[depRow]" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="项目" min-width="140" fixed />
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" size="small" class="amt-input" @change="onDep()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方(减少)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" size="small" class="amt-input" @change="onDep()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方(计提)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" size="small" class="amt-input" @change="onDep()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵类期末=期初+贷方-借方">{{ fmtAmt(contraEnd(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" size="small" class="amt-input" @change="onDep()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=期末+AJE">{{ fmtAmt(contraEnd(row) + num(row.aje)) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、减值准备（备抵） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、减值准备（备抵科目）</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-1-cost-imp')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="[impRow]" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="项目" min-width="140" fixed />
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" size="small" class="amt-input" @change="onImp()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方(转回/核销)" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" size="small" class="amt-input" @change="onImp()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方(计提)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" size="small" class="amt-input" @change="onImp()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵类期末=期初+贷方-借方">{{ fmtAmt(contraEnd(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" size="small" class="amt-input" @change="onImp()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=期末+AJE">{{ fmtAmt(contraEnd(row) + num(row.aje)) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 四、净值与勾稽 -->
    <el-card shadow="never" class="net-card">
      <template #header><div class="section-title"><span>四、生产性生物资产净值</span></div></template>
      <div class="net-row">
        <span>净值 = 原值审定 - 累计折旧审定 - 减值准备审定 = </span>
        <span class="formula-cell net-value" title="净值=原值-累计折旧-减值准备">{{ fmtAmt(netValueAudited) }}</span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi('cost-note')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
            <el-button size="small" link @click="handleReview('H7-1-cost-note')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写审计说明/结论..." :disabled="isReadonly" @blur="persist('H7-1-cost-note', auditNote)" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" :loading="publishing" @click="handlePublish">确认审定 → 回写TB(1621)</el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>依据《企业会计准则第5号——生物资产》，成本模式下生产性生物资产按成本 - 累计折旧 - 减值准备计量。</li>
        <li>一.原值(1621)为资产类：期末=期初+借方(增加)-贷方(减少)。</li>
        <li>二.累计折旧为备抵类：期末=期初+贷方(计提)-借方(减少)。</li>
        <li>三.减值准备为备抵类：期末=期初+贷方(计提)-借方(转回/核销)。</li>
        <li>四.净值=原值审定-累计折旧审定-减值准备审定。</li>
        <li>审定数=未审数+AJE+RJE，未审数从试算表(1621)自动取入(只读)。</li>
        <li>"确认审定"将回写 trial_balance(1621) 并发布 substantive:adjudicated 事件供附注刷新。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabAdjudicationCost.vue — H7-1 审定表（成本模式）
 *
 * 三区块(原值1621/累计折旧/减值准备)审定 + 净值勾稽 + TB回写1621。
 * 消费 useH7AdjudicationCost(getNum/getString 种子读取) + useH7FormData.tbData(未审数) +
 * 持久化走 api.put checklist-responses(remark 存储, conclusion=null 规避白名单422)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 双计量·成本模式审定
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7AdjudicationCost } from '../../composables/useH7AdjudicationCost'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
// 消费 sheet-specific composable（getNum/getString 种子访问器）
const { getNum, getString } = useH7AdjudicationCost(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface AdjRow { rowId: string; category: string; editable: boolean; begin: number; debit: number; credit: number; unadjusted: number; aje: number; rje: number }

const origRow = ref<AdjRow>({ rowId: 'orig', category: '生产性生物资产原值', editable: true, begin: 0, debit: 0, credit: 0, unadjusted: 0, aje: 0, rje: 0 })
const depRow = ref<AdjRow>({ rowId: 'dep', category: '累计折旧', editable: true, begin: 0, debit: 0, credit: 0, unadjusted: 0, aje: 0, rje: 0 })
const impRow = ref<AdjRow>({ rowId: 'imp', category: '减值准备', editable: true, begin: 0, debit: 0, credit: 0, unadjusted: 0, aje: 0, rje: 0 })
const auditNote = ref('')
const publishing = ref(false)

const origDisplayRows = computed(() => [origRow.value])

function assetEnd(r: AdjRow): number { return num(r.begin) + num(r.debit) - num(r.credit) }
function contraEnd(r: AdjRow): number { return num(r.begin) + num(r.credit) - num(r.debit) }
function auditedOf(r: AdjRow): number { return num(r.unadjusted) + num(r.aje) + num(r.rje) }

const netValueAudited = computed(() =>
  auditedOf(origRow.value) - (contraEnd(depRow.value) + num(depRow.value.aje)) - (contraEnd(impRow.value) + num(impRow.value.aje)),
)

// ─── 种子 + 持久化 ─────────────────────────────────────────
function seedRow(itemId: string, target: { value: AdjRow }) {
  const raw = getString(itemId)
  if (raw) { try { Object.assign(target.value, JSON.parse(raw)) } catch { /* ignore */ } }
}

async function loadOwn() {
  try {
    const list: any[] = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const m = new Map(localResponses.value)
    for (const r of (Array.isArray(list) ? list : [])) {
      if (r.item_id?.startsWith('H7-')) m.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
    }
    localResponses.value = m
  } catch { /* first-time empty */ }
  seedRow('H7-1-cost-orig', origRow)
  seedRow('H7-1-cost-dep', depRow)
  seedRow('H7-1-cost-imp', impRow)
  auditNote.value = getString('H7-1-cost-note') || ''
  // 未审数从 TB seed（若持久化过）或保持 0，由 loadTb 覆盖
  await loadTb()
}

async function loadTb() {
  if (!props.projectId) return
  try {
    const res: any = await api.get(`/api/projects/${props.projectId}/trial-balance?account_prefix=1621`)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? res?.items ?? [])
    let unadj = 0
    for (const it of list) {
      const code = String(it.standard_account_code ?? it.account_code ?? '')
      if (code.startsWith('1621')) unadj += num(it.unadjusted_amount)
    }
    if (unadj) origRow.value.unadjusted = unadj
  } catch { /* TB 未导入 */ }
}

async function persist(itemId: string, value: any) {
  const remark = value == null ? null : (typeof value === 'string' ? value : JSON.stringify(value))
  localResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark })
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark }],
    })
  } catch { ElMessage.error('保存失败，请稍后重试') }
}

function onOrig() { void persist('H7-1-cost-orig', origRow.value) }
function onDep() { void persist('H7-1-cost-dep', depRow.value) }
function onImp() { void persist('H7-1-cost-imp', impRow.value) }

async function handlePublish() {
  publishing.value = true
  try {
    await api.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '1621',
      audited_amount: netValueAudited.value,
    })
    eventBus.emit('substantive:adjudicated', {
      wpId: props.wpId, accountCode: '1621', auditedAmount: netValueAudited.value, componentType: 'h7-biological-assets',
    })
    ElMessage.success('审定数已回写试算表(1621)')
  } catch { ElMessage.warning('回写失败，请手动确认试算表') } finally { publishing.value = false }
}

function handleAi(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => { void loadOwn() })
// 触发 getNum 消费（种子诊断，避免未使用告警）
void getNum
</script>

<style scoped>
.h7-tab-adjudication-cost { padding: 16px; font-size: 13px; }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.adj-table { font-size: 13px; }
.adj-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.net-card { margin-bottom: 16px; }
.net-row { font-size: 14px; font-weight: 500; padding: 6px 0; }
.net-value { font-weight: 700; color: var(--el-color-primary); }
.note-card { margin-bottom: 16px; }
.action-bar { margin: 16px 0; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
