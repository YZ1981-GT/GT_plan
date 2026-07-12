<template>
  <div class="n3-tab-disclosure">
    <!-- ═══ 标题 + 模板切换 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">附注披露信息</h3>
        <el-segmented
          v-model="templateMode"
          :options="templateOptions"
          size="small"
        />
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-overview')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>递延所得税负债附注披露：</strong>
        列示各应纳税暂时性差异项目对应的递延所得税负债期初余额、本期确认/转回、期末余额。
        数据自动从N3-2明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
        负债类贷方科目：期末 = 期初 + 确认(贷方) − 转回(借方)。
      </div>
    </div>

    <!-- ═══ Section 1: 概述 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一、递延所得税负债概述</span>
          <el-button size="small" @click="handleAI('section-overview')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overviewNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="概述递延所得税负债的确认原则、适用税率及主要差异来源..."
        @change="handleNoteChange('overview', overviewNote)"
      />
    </el-card>

    <!-- ═══ Section 2: 应纳税暂时性差异明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>二、应纳税暂时性差异明细</span>
          <el-button size="small" @click="handleAI('section-diff-detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="diffDetailRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="应纳税暂时性差异项目" min-width="200" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal }">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应纳税暂时性差异" width="160" align="right">
          <template #header>
            <el-tooltip content="账面价值 − 计税基础（资产项）" placement="top">
              <span class="formula-col-header">应纳税暂时性差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.taxableDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="适用税率" width="100" align="center">
          <template #default="{ row }">
            <span>{{ row._isTotal ? '' : fmtPercent(row.taxRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="递延所得税负债" width="160" align="right">
          <template #header>
            <el-tooltip content="应纳税暂时性差异 × 适用税率" placement="top">
              <span class="formula-col-header">递延所得税负债</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.deferredTaxLiability) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 3: 期初期末余额变动表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>三、递延所得税负债余额变动表</span>
          <el-button size="small" @click="handleAI('section-balance-change')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="balanceChangeRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="项目" min-width="200" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal }">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="140" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期确认" width="140" align="right">
          <template #header>
            <el-tooltip content="贷方增加（确认递延税负债）" placement="top">
              <span class="formula-col-header">本期确认</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.recognized) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转回" width="140" align="right">
          <template #header>
            <el-tooltip content="借方减少（转回递延税负债）" placement="top">
              <span class="formula-col-header">本期转回</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.reversed) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="140" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 确认(贷方) − 转回(借方)（负债类）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 4: 特殊项说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>四、未确认递延所得税负债的特殊项说明</span>
          <el-button size="small" @click="handleAI('section-special-items')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="specialItemsNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明未确认递延所得税负债的应纳税暂时性差异（如商誉初始确认差异、拟长期持有的长期股权投资相关差异等）..."
        @change="handleNoteChange('special-items', specialItemsNote)"
      />
    </el-card>

    <!-- ═══ Section 5: N1对应关系 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>五、与N1递延所得税资产的对应关系</span>
          <el-button size="small" @click="handleAI('section-n1-correspondence')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div class="n1-correspondence">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="N1递延所得税资产（期末）">
            <span class="formula-value">{{ fmtAmount(n1Correspondence.assetPart) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="N3递延所得税负债（期末）">
            <span class="formula-value">{{ fmtAmount(n1Correspondence.liabilityPart) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="是否同一纳税主体">
            <el-tag :type="n1Correspondence.canOffset ? 'success' : 'warning'" size="small">
              {{ n1Correspondence.canOffset ? '是（可抵销净额列示）' : '否（分别列示）' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="本期变动额（供N5核对）">
            <span class="formula-value">{{ fmtAmount(taxChange.change) }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <el-input
        v-model="n1CorrespondenceNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="说明与N1递延所得税资产的抵销/分列情况..."
        @change="handleNoteChange('n1-correspondence', n1CorrespondenceNote)"
        style="margin-top: 12px"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从N3-2明细表自动拉取（应纳税暂时性差异项目）</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新附注数据</li>
        <li>上市公司：按CAS18要求披露各项应纳税暂时性差异及对应递延税负债</li>
        <li>国企：增加与N1抵销说明+同一纳税主体判定</li>
        <li>递延所得税负债 = 应纳税暂时性差异 × 适用税率</li>
        <li>未确认递延税负债的特殊项：商誉初始确认/长期股权投资拟长期持有</li>
        <li>本期变动额（期末-期初）供N5递延所得税费用核对</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N3TabDisclosure — 递延所得税负债附注披露
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 4.5
 * Requirements: 5.2-5.4
 *
 * 功能：
 * - 上市/国企模板切换（el-segmented）
 * - 应纳税暂时性差异明细（from N3-2 via allResponses）
 * - 期初期末余额变动表
 * - Subscribe 'substantive:adjudicated' → auto refresh
 * - Publish 'disclosure:note-text-updated'
 * - Sections: 概述 / 差异明细 / 变动表 / 特殊项说明 / N1对应关系
 * - AI辅助按钮per section
 * - autosize textarea for narrative
 * - 复核按钮
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useN3FormData } from '../../composables/useN3FormData'
import { useN3CrossSheet } from '../../composables/useN3CrossSheet'
import { calcLiabilityEndBalance } from '../../composables/useN3FormulaEngine'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN3FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── CrossSheet (N1 correspondence + deferred tax change) ────────────────────

const crossSheet = useN3CrossSheet(formData.allResponses)
const n1Correspondence = computed(() => crossSheet.n3ToN1Correspondence.value)
const taxChange = computed(() => crossSheet.deferredTaxChange.value)

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)

/** 上市/国企模板切换 */
const templateMode = ref<'listed' | 'soe'>('listed')
const templateOptions = [
  { label: '上市公司', value: 'listed' },
  { label: '国有企业', value: 'soe' },
]

/** 叙述性textarea */
const overviewNote = ref('')
const specialItemsNote = ref('')
const n1CorrespondenceNote = ref('')

// ─── 应纳税暂时性差异明细 (from N3-2 rows via allResponses) ─────────────────

interface DiffDetailRow {
  item: string
  taxableDiff: number
  taxRate: number
  deferredTaxLiability: number
  _isTotal?: boolean
}

const diffDetailRows = computed<DiffDetailRow[]>(() => {
  // 从 allResponses 获取 N3-2 明细行数据
  const resp = formData.allResponses.value.get('N3-2-rows')
  let rows: DiffDetailRow[] = []

  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) {
        rows = parsed.map((r: any) => ({
          item: r.item || r.projectName || '—',
          taxableDiff: Number(r.taxableDiff ?? r.taxableTemporaryDifference ?? 0),
          taxRate: Number(r.taxRate ?? r.applicableTaxRate ?? 0.25),
          deferredTaxLiability: Number(r.endDeferredTaxLiability ?? r.deferredTaxLiability ?? 0),
        }))
      }
    } catch { /* fallback empty */ }
  }

  // 合计行
  const totalDiff = rows.reduce((s, r) => s + r.taxableDiff, 0)
  const totalLiab = rows.reduce((s, r) => s + r.deferredTaxLiability, 0)
  rows.push({
    item: '合计',
    taxableDiff: totalDiff,
    taxRate: 0,
    deferredTaxLiability: totalLiab,
    _isTotal: true,
  })
  return rows
})

// ─── 期初期末余额变动表 ──────────────────────────────────────────────────────

interface BalanceChangeRow {
  item: string
  beginBalance: number
  recognized: number
  reversed: number
  endBalance: number
  _isTotal?: boolean
}

const balanceChangeRows = computed<BalanceChangeRow[]>(() => {
  // 从 allResponses 获取 N3-2 行数据（含期初/确认/转回）
  const resp = formData.allResponses.value.get('N3-2-rows')
  let rows: BalanceChangeRow[] = []

  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) {
        rows = parsed.map((r: any) => {
          const begin = Number(r.beginDeferredTaxLiability ?? r.beginBalance ?? 0)
          const recognized = Number(r.currentRecognized ?? r.recognized ?? 0)
          const reversed = Number(r.currentReversed ?? r.reversed ?? 0)
          return {
            item: r.item || r.projectName || '—',
            beginBalance: begin,
            recognized,
            reversed,
            endBalance: calcLiabilityEndBalance(begin, recognized, reversed),
          }
        })
      }
    } catch { /* fallback empty */ }
  }

  // 合计行
  const totalBegin = rows.reduce((s, r) => s + r.beginBalance, 0)
  const totalRecognized = rows.reduce((s, r) => s + r.recognized, 0)
  const totalReversed = rows.reduce((s, r) => s + r.reversed, 0)
  rows.push({
    item: '合计',
    beginBalance: totalBegin,
    recognized: totalRecognized,
    reversed: totalReversed,
    endBalance: calcLiabilityEndBalance(totalBegin, totalRecognized, totalReversed),
    _isTotal: true,
  })
  return rows
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: { _isTotal?: boolean } }): string {
  return row._isTotal ? 'total-row' : ''
}

function fmtAmount(val: number): string {
  if (val === 0 || val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (!val) return '—'
  return `${(val * 100).toFixed(0)}%`
}

// ─── Note changes (textarea保存 + publish) ───────────────────────────────────

function handleNoteChange(section: string, value: string): void {
  formData.debouncedSave(`N3-disclosure-${section}`, { remark: value || null })
  // Publish disclosure updated event
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N3',
    section,
    timestamp: Date.now(),
  })
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  // AI辅助 placeholder — 后续集成 AI 对话
}

function handleReview() {
  openReviewDialog?.('N3-disclosure')
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const overviewResp = formData.allResponses.value.get('N3-disclosure-overview')
  if (overviewResp?.remark) overviewNote.value = overviewResp.remark

  const specialResp = formData.allResponses.value.get('N3-disclosure-special-items')
  if (specialResp?.remark) specialItemsNote.value = specialResp.remark

  const n1Resp = formData.allResponses.value.get('N3-disclosure-n1-correspondence')
  if (n1Resp?.remark) n1CorrespondenceNote.value = n1Resp.remark

  // 恢复模板模式
  const modeResp = formData.allResponses.value.get('N3-disclosure-template-mode')
  if (modeResp?.conclusion === 'soe') templateMode.value = 'soe'
}

// ─── EventBus: 审定变化刷新 ─────────────────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => restoreData())
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.n3-tab-disclosure { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.methodology-text strong { color: #b88230; }

.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }

.n1-correspondence { margin-bottom: 8px; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }

.n3-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
