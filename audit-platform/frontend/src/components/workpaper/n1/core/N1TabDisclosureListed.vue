<template>
  <div class="n1-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市 54×11</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-listed')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司递延所得税资产附注披露（54×11，CSRC标准格式）：</strong>
        按可抵扣暂时性差异项目列示递延所得税资产的期初余额、本期确认/转回、期末余额。
        需额外披露未确认递延所得税资产的可抵扣暂时性差异及可弥补亏损金额。
        数据自动从N1-1审定表/N1-2明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 已确认递延所得税资产明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一、已确认递延所得税资产明细</span>
          <el-button size="small" @click="handleAI('section-recognized')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="recognizedRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="可抵扣暂时性差异项目" min-width="180" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal }">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可抵扣暂时性差异" width="150" align="right">
          <template #header>
            <el-tooltip content="账面价值 − 计税基础（资产项目）" placement="top">
              <span class="formula-col-header">可抵扣暂时性差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.deductibleDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="适用税率" width="90" align="center">
          <template #default="{ row }">
            <span>{{ row._isTotal ? '' : fmtPercent(row.taxRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期确认" width="130" align="right">
          <template #header>
            <el-tooltip content="借方增加（确认递延税资产）" placement="top">
              <span class="formula-col-header">本期确认</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.recognized) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转回" width="130" align="right">
          <template #header>
            <el-tooltip content="贷方减少（转回递延税资产）" placement="top">
              <span class="formula-col-header">本期转回</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.reversed) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 确认(借方) − 转回(贷方)（资产类）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 余额变动表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>二、递延所得税资产余额变动表</span>
          <el-button size="small" @click="handleAI('section-movement')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="movementRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="项目" min-width="180" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal }">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="140" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="140" align="right">
          <template #header>
            <el-tooltip content="借方确认新增递延税资产" placement="top">
              <span class="formula-col-header">本期增加</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="140" align="right">
          <template #header>
            <el-tooltip content="贷方转回减少递延税资产" placement="top">
              <span class="formula-col-header">本期减少</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="140" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 增加 − 减少" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 3: 未确认递延所得税资产 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>三、未确认递延所得税资产的可抵扣暂时性差异及可弥补亏损</span>
          <el-button size="small" @click="handleAI('section-unrecognized')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="unrecognizedRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="可抵扣暂时性差异/可弥补亏损" width="200" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未确认递延税资产" width="160" align="right">
          <template #header>
            <el-tooltip content="谨慎性原则不确认：未来应纳税所得额不足" placement="top">
              <span class="formula-col-header">未确认递延税资产</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="unrecognized-amount">{{ fmtAmount(row.unrecognizedAsset) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="未确认原因" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.reason"
              size="small"
              placeholder="如：预计未来应纳税所得额不足"
              @change="(val: string) => updateUnrecognizedReason($index, val)"
            />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 4: 可弥补亏损到期明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>四、可弥补亏损到期年度明细</span>
          <el-button size="small" @click="handleAI('section-loss-expiry')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="lossExpiryRows" border size="small" style="width: 100%">
        <el-table-column prop="year" label="亏损年度" width="100" align="center" />
        <el-table-column label="亏损金额" width="140" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.lossAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expiryYear" label="到期年度" width="100" align="center" />
        <el-table-column label="已弥补" width="130" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.recovered) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未弥补" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'warning-amount': row.isExpired }">{{ fmtAmount(row.unrecovered) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否到期" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isExpired ? 'danger' : 'success'" size="small">
              {{ row.isExpired ? '已到期' : '未到期' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 5: 与N3对应关系+N5联动 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>五、与N3递延所得税负债对应关系</span>
          <el-button size="small" @click="handleAI('section-n3-correspondence')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="N1递延所得税资产（期末）">
          <span class="formula-value">{{ fmtAmount(n1ToN3.assetPart) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="N3递延所得税负债（期末）">
          <span class="formula-value">{{ fmtAmount(n1ToN3.liabilityPart) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="本期变动额（供N5核对）">
          <span class="formula-value">{{ fmtAmount(deferredTaxChange.change) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="来源说明">
          <span>N1-4测算表同源产出资产/负债两部分</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- ═══ Section 6: 审计说明/结论 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>六、审计说明及结论</span>
          <el-button size="small" @click="handleAI('section-conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusionNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明递延所得税资产附注披露的完整性、准确性，是否符合CAS18相关要求..."
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从N1-1审定表和N1-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新附注数据</li>
        <li>上市公司需额外披露：未确认递延税资产的可抵扣暂时性差异及可弥补亏损</li>
        <li>可弥补亏损到期年度需逐年列示（一般5年，高新10年）</li>
        <li>递延所得税资产 = 可抵扣暂时性差异 × 适用税率</li>
        <li>资产类借方科目1811：期末 = 期初 + 借方(确认) − 贷方(转回)</li>
        <li>本期变动额（期末−期初）供N5递延所得税费用核对</li>
        <li>同一纳税主体可抵销净额列示，不同主体分别列示</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabDisclosureListed — 递延所得税资产附注披露（上市公司）54×11
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 4.7
 * Requirements: 6.2-6.4
 *
 * 功能：
 * - 按CSRC标准格式渲染上市公司递延所得税资产附注结构(54行×11列)
 * - 已确认递延税资产明细（by category: 资产减值/可弥补亏损/预提/递延收益/公允价值变动/其他）
 * - 余额变动表：期初→增加→减少→期末
 * - 未确认递延税资产的可抵扣暂时性差异及可弥补亏损金额
 * - 可弥补亏损到期年度明细
 * - N3对应关系 + N5联动本期变动额
 * - Subscribe 'substantive:adjudicated' → auto refresh
 * - Publish 'disclosure:note-text-updated'
 * - AI辅助按钮 per section
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useN1FormData } from '../../composables/useN1FormData'
import { useN1CrossSheet } from '../../composables/useN1CrossSheet'
import { calcAssetEndBalance } from '../../composables/useN1FormulaEngine'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── CrossSheet (N3 correspondence + deferred tax change) ────────────────────

const crossSheet = useN1CrossSheet(formData.allResponses)
const n1ToN3 = computed(() => crossSheet.n1ToN3Correspondence.value)
const deferredTaxChange = computed(() => crossSheet.deferredTaxChange.value)

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)
const conclusionNote = ref('')

// ─── Section 1: 已确认递延所得税资产明细 (from N1-2 rows) ────────────────────

interface RecognizedRow {
  item: string
  deductibleDiff: number
  taxRate: number
  beginBalance: number
  recognized: number
  reversed: number
  endBalance: number
  _isTotal?: boolean
}

const recognizedRows = computed<RecognizedRow[]>(() => {
  const resp = formData.allResponses.value.get('N1-2-rows')
  let rows: RecognizedRow[] = []

  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) {
        rows = parsed.map((r: any) => {
          const begin = Number(r.beginDeferredTaxAsset ?? r.beginBalance ?? 0)
          const recognized = Number(r.currentRecognized ?? r.recognized ?? 0)
          const reversed = Number(r.currentReversed ?? r.reversed ?? 0)
          return {
            item: r.item || r.projectName || '—',
            deductibleDiff: Number(r.deductibleDiff ?? r.temporaryDifference ?? 0),
            taxRate: Number(r.taxRate ?? r.applicableTaxRate ?? 0.25),
            beginBalance: begin,
            recognized,
            reversed,
            endBalance: calcAssetEndBalance(begin, recognized, reversed),
          }
        })
      }
    } catch { /* fallback empty */ }
  }

  // 若无数据，使用默认分类结构
  if (rows.length === 0) {
    const defaultCategories = [
      '资产减值准备', '可弥补亏损', '预提费用/预计负债',
      '递延收益', '公允价值变动', '其他',
    ]
    rows = defaultCategories.map(item => ({
      item, deductibleDiff: 0, taxRate: 0.25,
      beginBalance: 0, recognized: 0, reversed: 0, endBalance: 0,
    }))
  }

  // 合计行
  const totals = rows.reduce((acc, r) => ({
    deductibleDiff: acc.deductibleDiff + r.deductibleDiff,
    beginBalance: acc.beginBalance + r.beginBalance,
    recognized: acc.recognized + r.recognized,
    reversed: acc.reversed + r.reversed,
    endBalance: acc.endBalance + r.endBalance,
  }), { deductibleDiff: 0, beginBalance: 0, recognized: 0, reversed: 0, endBalance: 0 })

  rows.push({
    item: '合计',
    deductibleDiff: totals.deductibleDiff,
    taxRate: 0,
    beginBalance: totals.beginBalance,
    recognized: totals.recognized,
    reversed: totals.reversed,
    endBalance: totals.endBalance,
    _isTotal: true,
  })
  return rows
})

// ─── Section 2: 余额变动表 ──────────────────────────────────────────────────

interface MovementRow {
  item: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  _isTotal?: boolean
}

const movementRows = computed<MovementRow[]>(() => {
  // 从已确认表推导变动
  const recognized = recognizedRows.value.filter(r => !r._isTotal)
  const rows: MovementRow[] = recognized.map(r => ({
    item: r.item,
    beginBalance: r.beginBalance,
    increase: r.recognized,
    decrease: r.reversed,
    endBalance: r.endBalance,
  }))

  const totals = rows.reduce((acc, r) => ({
    beginBalance: acc.beginBalance + r.beginBalance,
    increase: acc.increase + r.increase,
    decrease: acc.decrease + r.decrease,
    endBalance: acc.endBalance + r.endBalance,
  }), { beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 })

  rows.push({ item: '合计', ...totals, _isTotal: true })
  return rows
})

// ─── Section 3: 未确认递延所得税资产 ─────────────────────────────────────────

interface UnrecognizedRow {
  item: string
  amount: number
  unrecognizedAsset: number
  reason: string
}

const unrecognizedRows = computed<UnrecognizedRow[]>(() => {
  const resp = formData.allResponses.value.get('N1-disclosure-listed-unrecognized')
  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) return parsed
    } catch { /* fallback */ }
  }
  // 默认结构
  return [
    { item: '未确认的可抵扣暂时性差异', amount: 0, unrecognizedAsset: 0, reason: '' },
    { item: '未确认的可弥补亏损', amount: 0, unrecognizedAsset: 0, reason: '' },
  ]
})

function updateUnrecognizedReason(index: number, val: string) {
  const rows = [...unrecognizedRows.value]
  if (index >= 0 && index < rows.length) {
    rows[index] = { ...rows[index], reason: val }
    formData.debouncedSave('N1-disclosure-listed-unrecognized', { conclusion: JSON.stringify(rows) })
  }
}

// ─── Section 4: 可弥补亏损到期明细 ───────────────────────────────────────────

interface LossExpiryRow {
  year: string
  lossAmount: number
  expiryYear: string
  recovered: number
  unrecovered: number
  isExpired: boolean
}

const lossExpiryRows = computed<LossExpiryRow[]>(() => {
  const resp = formData.allResponses.value.get('N1-5-loss-expiry-rows')
  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) {
        return parsed.map((r: any) => ({
          year: r.year || r.lossYear || '—',
          lossAmount: Number(r.lossAmount ?? 0),
          expiryYear: r.expiryYear || r.compensationDeadline || '—',
          recovered: Number(r.recovered ?? r.compensated ?? 0),
          unrecovered: Number(r.unrecovered ?? r.uncompensated ?? 0),
          isExpired: Boolean(r.isExpired),
        }))
      }
    } catch { /* fallback */ }
  }
  return []
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

// ─── Note changes + publish ──────────────────────────────────────────────────

function handleConclusionChange() {
  formData.debouncedSave('N1-disclosure-listed-conclusion', { remark: conclusionNote.value || null })
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N1',
    section: 'conclusion-listed',
    timestamp: Date.now(),
  })
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  // AI辅助 placeholder — 后续集成 AI 对话
}

function handleReview() {
  openReviewDialog?.('N1-disclosure-listed', '附注披露（上市）')
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const conclusionResp = formData.allResponses.value.get('N1-disclosure-listed-conclusion')
  if (conclusionResp?.remark) conclusionNote.value = conclusionResp.remark
}

// ─── EventBus: 审定变化刷新 ─────────────────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => {
    restoreData()
    // Publish disclosure updated event
    eventBus.emit('disclosure:note-text-updated', {
      wpCode: 'N1',
      section: 'auto-refresh-listed',
      timestamp: Date.now(),
    })
  })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
})
</script>

<style scoped>
.n1-tab-disclosure-listed { padding: 12px; font-size: 13px; }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.methodology-text strong { color: #b88230; }

.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
.unrecognized-amount { color: #e6a23c; font-weight: 500; }
.warning-amount { color: #f56c6c; font-weight: 500; }

:deep(.el-table) { font-size: 13px; }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }

.n1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.n1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
