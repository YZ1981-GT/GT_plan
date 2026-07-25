<template>
  <div class="h7-tab-adjudication-fair">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：确认公允价值模式下生产性生物资产（科目1621）的期末公允价值计量可靠，
        公允价值变动损益确认恰当且计入当期损益，列报与披露充分。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
        <el-icon><Download /></el-icon>带入调整
      </el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H7-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="warning">公允价值模式</el-tag>
    </div>

    <!-- 公允价值变动审定 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>生产性生物资产公允价值（科目1621）</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-1-fair')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="[fairRow]" border stripe size="small" class="adj-table">
        <el-table-column prop="category" label="项目" min-width="150" fixed />
        <el-table-column label="期初公允价值" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.begin" :controls="false" size="small" class="amt-input" @change="onFair()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.increase" :controls="false" size="small" class="amt-input" @change="onFair()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.decrease" :controls="false" size="small" class="amt-input" @change="onFair()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值变动损益" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.fvChange" :controls="false" size="small" class="amt-input" @change="onFair()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.fvChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末公允价值" min-width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少+公允价值变动损益">{{ fmtAmt(fairEnd(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell tb-auto" title="TB自动取数(1621期末余额)">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.aje" :controls="false" size="small" class="amt-input" @change="onFair()" />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="审定=未审+AJE">{{ fmtAmt(num(row.unadjusted) + num(row.aje)) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 公允价值变动损益汇总 -->
    <el-card shadow="never" class="fv-card">
      <template #header><div class="section-title"><span>公允价值变动损益</span></div></template>
      <div class="net-row">
        <span>计入当期损益的公允价值变动 = </span>
        <span class="formula-cell net-value" title="公允价值变动损益(计入公允价值变动损益科目6101)">{{ fmtAmt(num(fairRow.fvChange)) }}</span>
        <el-tag size="small" :type="num(fairRow.fvChange) >= 0 ? 'success' : 'danger'" style="margin-left:8px">
          {{ num(fairRow.fvChange) >= 0 ? '收益' : '损失' }}
        </el-tag>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('H7-1-fair-note')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写审计说明（公允价值确定方法、估值层级、变动合理性等）..." :disabled="isReadonly" @blur="persist('H7-1-fair-note', auditNote)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计结论</span></div></template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="A、未见异常。B、除上述调整事项外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。" @blur="persist('H7-1-fair-conclusion', auditConclusion)" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" :loading="publishing" @click="handlePublish">确认审定 → 回写TB(1621)</el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>依据《企业会计准则第5号——生物资产》，公允价值模式仅在有确凿证据表明公允价值能够持续可靠取得时采用。</li>
        <li>期末公允价值 = 期初 + 本期增加 - 本期减少 + 公允价值变动损益。</li>
        <li>公允价值变动计入当期损益（公允价值变动损益），不计提折旧与减值。</li>
        <li>未审数从试算表(1621)自动取入(只读)，审定数=未审+AJE。</li>
        <li>应关注公允价值层级(L1/L2/L3)、估值技术与关键参数，参见 H7-13 公允价值复核表。</li>
        <li>"确认审定"将回写 trial_balance(1621) 并发布 substantive:adjudicated 事件供附注刷新。</li>
        <li>"带入调整"：从集中登记按科目 1621 拉取调整分录，累加到公允价值调整列(AJE)，带入后审定数自动更新并联动附注。</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1621 生产性生物资产（公允价值模式）"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabAdjudicationFair.vue — H7-1 审定表（公允价值模式）
 *
 * 公允价值变动审定(期初+增加-减少+公允价值变动损益) + TB回写1621。
 * 消费 useH7AdjudicationFair(getString 种子) + api.put 持久化(remark 存储)。
 *
 * Spec: .kiro/specs/h7-biological-assets/  Requirements: 双计量·公允价值模式审定
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { useProjectStore } from '@/stores/project'
import { useAuditContext } from '@/composables/useAuditContext'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7AdjudicationFair } from '../../composables/useH7AdjudicationFair'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'

const projectStore = useProjectStore()

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))
const allResponsesRef = computed(() => localResponses.value)
const { getString } = useH7AdjudicationFair(allResponsesRef as any, {
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

function num(v: any): number { const n = Number(v); return Number.isFinite(n) ? n : 0 }

interface FairRow { category: string; begin: number; increase: number; decrease: number; fvChange: number; unadjusted: number; aje: number }
const fairRow = ref<FairRow>({ category: '生产性生物资产(公允价值)', begin: 0, increase: 0, decrease: 0, fvChange: 0, unadjusted: 0, aje: 0 })
const auditNote = ref('')
const auditConclusion = ref('')
const publishing = ref(false)

function fairEnd(r: FairRow): number { return num(r.begin) + num(r.increase) - num(r.decrease) + num(r.fvChange) }
const auditedFair = computed(() => num(fairRow.value.unadjusted) + num(fairRow.value.aje))

// ─── 从集中登记带入调整（1621 生产性生物资产，资产借方；单一调整列累加到 aje） ───
const bringInRows = computed(() => [
  { rowKey: 'fair', name: fairRow.value.category, aje: 0, rje: 0 },
])
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1621',
  direction: 'debit',
  subjectCode: '1621',
  wpCode: 'H7',
  subjectLabel: '生产性生物资产(1621)',
  rows: bringInRows,
  // 公允价值模式单一调整列（审定=未审+aje）：aje/rje 净额均累加至 fairRow.aje（增量累加）
  updateCell: (_rowKey: string, _field: any, value: number) => {
    const live = num(fairRow.value.aje)
    fairRow.value.aje = Math.round((live + value) * 100) / 100
    void persist('H7-1-fair', fairRow.value)
  },
  totalAudited: () => auditedFair.value,
})

async function loadOwn() {
  try {
    const list: any[] = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const m = new Map(localResponses.value)
    for (const r of (Array.isArray(list) ? list : [])) {
      if (r.item_id?.startsWith('H7-')) m.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
    }
    localResponses.value = m
  } catch { /* empty */ }
  const raw = getString('H7-1-fair')
  if (raw) { try { Object.assign(fairRow.value, JSON.parse(raw)) } catch { /* ignore */ } }
  auditNote.value = getString('H7-1-fair-note') || ''
  auditConclusion.value = getString('H7-1-fair-conclusion') || ''
  await loadTb()
}

async function loadTb() {
  if (!props.projectId) return
  try {
    const _year = projectStore.year ?? projectStore.auditYear ?? new Date().getFullYear()
    const res: any = await api.get(`/api/projects/${props.projectId}/trial-balance?year=${_year}&account_prefix=1621`)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? res?.items ?? [])
    let unadj = 0
    for (const it of list) {
      const code = String(it.standard_account_code ?? it.account_code ?? '')
      if (code.startsWith('1621')) unadj += num(it.unadjusted_amount)
    }
    if (unadj) fairRow.value.unadjusted = unadj
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

function onFair() { void persist('H7-1-fair', fairRow.value) }

async function handlePublish() {
  publishing.value = true
  try {
    await api.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: '1621',
      audited_amount: auditedFair.value,
    })
    eventBus.emit('substantive:adjudicated', {
      wpId: props.wpId, accountCode: '1621', auditedAmount: auditedFair.value, componentType: 'h7-biological-assets',
    })
    ElMessage.success('审定数已回写试算表(1621)')
  } catch { ElMessage.warning('回写失败，请手动确认试算表') } finally { publishing.value = false }
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => { void loadOwn() })
</script>

<style scoped>
.h7-tab-adjudication-fair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.adj-table { font-size: var(--wp-font-size, 13px); }
.adj-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.amt-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.tb-auto { color: var(--el-text-color-secondary); font-style: italic; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.fv-card { margin-bottom: 16px; }
.net-row { font-size: 14px; font-weight: 500; padding: 6px 0; }
.net-value { font-weight: 700; color: var(--el-color-primary); }
.note-card { margin-bottom: 16px; }
.action-bar { margin: 16px 0; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
