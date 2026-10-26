<template>
  <div v-loading="loading" class="es-sheet" data-testid="entry-summary-sheet">
    <div class="es-head">
      <div class="es-head-main">
        <h3>抵销分录汇总表</h3>
        <el-tag size="small" effect="plain">与合并试算同一口径</el-tag>
        <template v-if="summary">
          <el-tag size="small" type="info" effect="plain">已审批 {{ summary.totals.entry_count }} 笔</el-tag>
          <el-tag size="small" effect="plain" :type="summary.totals.balanced ? 'success' : 'danger'" data-testid="es-balance">
            {{ summary.totals.balanced ? '借贷平衡' : `借贷不平：差额 ${summary.totals.difference}` }}
          </el-tag>
        </template>
      </div>
      <div class="es-head-actions">
        <el-button size="small" data-testid="es-goto-elim" @click="emit('goto-sheet', 'elimination')">前往合并抵消分录</el-button>
        <el-button size="small" :loading="loading" data-testid="es-refresh" @click="load">🔄 刷新</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="es-note" :title="BASIS_NOTE" />

    <el-alert v-if="loadError" type="error" :closable="false" show-icon class="es-note" data-testid="es-error" :title="loadError" />

    <template v-else-if="summary">
      <el-alert v-if="summary.warnings.length" type="warning" :closable="false" show-icon class="es-note"
        data-testid="es-warnings" :title="`需关注 ${summary.warnings.length} 项`">
        <div v-for="(text, i) in summary.warnings" :key="i" class="es-warning-line">{{ text }}</div>
        <el-button v-if="summary.reconcile.persisted_stale" size="small" type="warning" class="es-repush"
          data-testid="es-repush" @click="requestPush">重新推送</el-button>
      </el-alert>

      <div class="es-section-title">按分录类型</div>
      <el-table :data="summary.by_type" border size="small" show-summary :summary-method="typeSummary"
        empty-text="暂无已审批的抵销分录" data-testid="es-by-type">
        <el-table-column prop="type_label" label="分录类型" min-width="140" />
        <el-table-column label="笔数" width="70" align="center">
          <template #default="{ row }">{{ row.entry_count }}</template>
        </el-table-column>
        <el-table-column label="借方" width="150" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.debit" /></template>
        </el-table-column>
        <el-table-column label="贷方" width="150" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.credit" /></template>
        </el-table-column>
        <el-table-column label="净额（按科目方向）" width="160" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.net" /></template>
        </el-table-column>
        <el-table-column label="含草稿净额" width="150" align="right">
          <template #default="{ row }">
            <span :class="{ 'es-draft-diff': differs(row.net, row.draft_net) }" :title="differs(row.net, row.draft_net) ? DRAFT_TIP : ''">
              <GtAmountCell :value="row.draft_net" />
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="es-section-title">
        <span>明细（差额户 × 科目 × 分录类型）</span>
        <el-select v-if="nodeOptions.length > 1" v-model="nodeFilter" size="small" clearable placeholder="全部差额户"
          class="es-node-filter" data-testid="es-node-filter">
          <el-option v-for="o in nodeOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </div>
      <el-table :data="visibleRows" border size="small" max-height="460" empty-text="暂无明细" data-testid="es-rows">
        <el-table-column label="差额户" min-width="190">
          <template #default="{ row }">
            <span>{{ row.node_label }}</span>
            <el-tag v-if="!row.hosted_here" size="small" type="info" effect="plain" class="es-hosted">在下级合并项目录入</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="科目" min-width="190">
          <template #default="{ row }">{{ row.account_code }} {{ row.account_name || '' }}</template>
        </el-table-column>
        <el-table-column prop="type_label" label="分录类型" width="120" />
        <el-table-column label="笔数" width="64" align="center">
          <template #default="{ row }">{{ row.entry_count }}</template>
        </el-table-column>
        <el-table-column label="借方" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.debit" /></template>
        </el-table-column>
        <el-table-column label="贷方" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.credit" /></template>
        </el-table-column>
        <el-table-column label="净额" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.net" /></template>
        </el-table-column>
        <el-table-column label="含草稿净额" width="140" align="right">
          <template #default="{ row }">
            <span :class="{ 'es-draft-diff': differs(row.net, row.draft_net) }" :title="differs(row.net, row.draft_net) ? DRAFT_TIP : ''">
              <GtAmountCell :value="row.draft_net" />
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div class="es-section-title">与合并试算对账</div>
      <el-tag v-if="summary.reconcile.matched" type="success" effect="plain" data-testid="es-reconcile-ok">
        逐科目调整合计、抵销合计与合并试算一致
      </el-tag>
      <el-table v-else :data="summary.reconcile.mismatches" border size="small" data-testid="es-mismatch">
        <el-table-column label="科目" min-width="190">
          <template #default="{ row }">{{ row.account_code }} {{ row.account_name || '' }}</template>
        </el-table-column>
        <el-table-column label="本表调整" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.summary_adjustment" /></template>
        </el-table-column>
        <el-table-column label="试算调整" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.trial_adjustment" /></template>
        </el-table-column>
        <el-table-column label="本表抵销" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.summary_elimination" /></template>
        </el-table-column>
        <el-table-column label="试算抵销" width="140" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.trial_elimination" /></template>
        </el-table-column>
      </el-table>

      <template v-if="summary.orphans.length">
        <div class="es-section-title">未归属分录（不计入本表与合并数）</div>
        <el-table :data="summary.orphans" border size="small" data-testid="es-orphans">
          <el-table-column prop="entry_no" label="分录编号" width="150" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">{{ row.review_status_label || row.review_status || '—' }}</template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="280" />
        </el-table>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 合并抵销分录汇总表（spec consol-autotree-linkage-closure R9 / design §3.7，从 ConsolWorksheetTabs 抽出）。
 *
 * 只读 `GET /consolidation/worksheet/entry-summary`：金额全部来自合并计算口径（与合并试算、报表差额表同一份），
 * 前端不重算，只做展示：按类型合计、差额户 × 科目 × 类型明细、与合并试算对账、未归属分录、问题提示。
 * 挂载即读（每次进入本表都重读）；父组件在分录变化 / 推送完成后调用暴露的 `load`。
 */
import { computed, onMounted, ref, watch } from 'vue'
import Decimal from 'decimal.js'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { getConsolEntrySummary, type ConsolEntrySummary } from '@/services/consolidationApi'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ projectId: string; year: number }>()
const emit = defineEmits<{ 'goto-sheet': [sheetKey: string] }>()

const BASIS_NOTE = '只计已审批且归属到差额户的分录（与合并试算、合并报表差额表同一口径）；净额按科目自然方向归一（正数 = 余额增加，负数 = 余额减少）；「含草稿净额」另含草稿与待审批分录（不含已驳回），仅供预览，不进合并数'
const DRAFT_TIP = '与已审批净额不同：差额来自草稿或待审批分录'

const summary = ref<ConsolEntrySummary | null>(null)
const loading = ref(false)
const loadError = ref('')
const nodeFilter = ref<string>('')
let seq = 0

const nodeOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const r of summary.value?.rows || []) if (!seen.has(r.node_key)) seen.set(r.node_key, r.node_label)
  return [...seen].map(([value, label]) => ({ value, label }))
})
const visibleRows = computed(() => {
  const rows = summary.value?.rows || []
  return nodeFilter.value ? rows.filter((r) => r.node_key === nodeFilter.value) : rows
})

function dec(v: string | null | undefined): Decimal | null {
  if (v === null || v === undefined || v === '') return null
  try { return new Decimal(v) } catch { return null }
}

/** 含草稿净额与已审批净额不同（到分）⇒ 高亮；没有预览口径（null）不算不同 */
function differs(net: string | null | undefined, draftNet: string | null | undefined): boolean {
  const a = dec(net)
  const b = dec(draftNet)
  if (b === null) return false
  return a === null || !a.equals(b)
}

/** 合计行：笔数按分录去重（后端 totals.entry_count），借贷取后端合计；净额跨科目方向相加没有意义，留空 */
function typeSummary({ columns }: { columns: unknown[] }): string[] {
  const t = summary.value?.totals
  return columns.map((_c, i) => {
    if (i === 0) return '合计'
    if (!t) return ''
    if (i === 1) return String(t.entry_count)
    if (i === 2) return amountText(t.debit)
    if (i === 3) return amountText(t.credit)
    return ''
  })
}

function amountText(v: string | null | undefined): string {
  const d = dec(v)
  return d === null ? '' : d.toNumber().toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function requestPush() {
  eventBus.emit('consol-request-push')
}

async function load() {
  const pid = props.projectId
  const yr = props.year
  if (!pid || !yr) return
  const ticket = ++seq
  loading.value = true
  try {
    const res = await getConsolEntrySummary(pid, yr)
    if (ticket !== seq) return
    summary.value = res
    loadError.value = ''
    if (nodeFilter.value && !(res?.rows || []).some((r) => r.node_key === nodeFilter.value)) nodeFilter.value = ''
  } catch (err: any) {
    if (ticket !== seq) return
    summary.value = null
    loadError.value = `分录汇总表加载失败：${err?.message || '请稍后重试'}`
  } finally {
    if (ticket === seq) loading.value = false
  }
}

onMounted(load)
watch(() => [props.projectId, props.year], () => { nodeFilter.value = ''; void load() })

defineExpose({ load })
</script>

<style scoped>
.es-sheet { font-size: 13px; padding: 4px 0; }
.es-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.es-head-main { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.es-head-main h3 { margin: 0; font-size: 14px; }
.es-head-actions { display: flex; gap: 8px; }
.es-note { margin-bottom: 10px; }
.es-warning-line { line-height: 1.6; }
.es-repush { margin-top: 6px; }
.es-section-title { display: flex; align-items: center; gap: 12px; margin: 16px 0 8px; font-weight: 600; color: var(--gt-color-text-primary); }
.es-node-filter { width: 240px; }
.es-hosted { margin-left: 6px; }
.es-draft-diff { display: inline-block; padding: 0 4px; border-radius: 4px; background: var(--el-color-warning-light-9); color: var(--el-color-warning-dark-2); }
</style>
