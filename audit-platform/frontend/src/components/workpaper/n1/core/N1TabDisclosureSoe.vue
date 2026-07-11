<template>
  <div class="n1-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（国有企业）</h3>
        <el-tag type="success" size="small">国企 74×256</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-soe')">
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
        <strong>国有企业递延所得税资产附注披露（74×256，SASAC格式）：</strong>
        按SASAC标准列示递延所得税资产各项目明细、变动情况、确认依据。
        国企格式宽表（256列），包含更详细的分类及确认条件说明。
        需额外披露未确认的可抵扣暂时性差异及可弥补亏损金额、确认充足性判断。
        数据自动从N1-1审定表/N1-2明细表/N1-5亏损检查拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 递延所得税资产确认项目明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一、递延所得税资产确认项目明细</span>
          <el-button size="small" @click="handleAI('section-recognized-detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="recognizedDetailRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="可抵扣暂时性差异项目" min-width="180" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal }">{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="130" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计税基础" width="130" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.taxBase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可抵扣暂时性差异" width="150" align="right">
          <template #header>
            <el-tooltip content="账面价值 − 计税基础（资产项: 账面 < 计税基础）" placement="top">
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
        <el-table-column label="递延所得税资产" width="150" align="right">
          <template #header>
            <el-tooltip content="可抵扣暂时性差异 × 适用税率" placement="top">
              <span class="formula-col-header">递延所得税资产</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.deferredTaxAsset) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="确认依据" min-width="180">
          <template #default="{ row }">
            <span>{{ row.basis || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 余额变动表（更详细：期初/增加/减少/期末） ═══ -->
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
        <el-table-column label="年初余额" width="130" align="right">
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
        <el-table-column label="变动原因" min-width="160">
          <template #default="{ row }">
            <span>{{ row.changeReason || '—' }}</span>
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
            <el-tooltip content="谨慎性原则不确认：预计未来应纳税所得额不足以利用" placement="top">
              <span class="formula-col-header">未确认递延税资产</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="unrecognized-amount">{{ fmtAmount(row.unrecognizedAsset) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="未确认原因/充足性说明" min-width="220">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.reason"
              size="small"
              placeholder="预计未来应纳税所得额不足/弥补期限已到期..."
              @change="(val: string) => updateUnrecognizedReason($index, val)"
            />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 4: 可弥补亏损到期年度明细 ═══ -->
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
        <el-table-column label="亏损金额" width="130" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.lossAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="expiryYear" label="弥补截止年度" width="120" align="center" />
        <el-table-column label="已弥补" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.recovered) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未弥补" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'warning-amount': row.isExpired }">{{ fmtAmount(row.unrecovered) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预计未来应纳税所得额" width="170" align="right">
          <template #header>
            <el-tooltip content="用于判断可弥补亏损确认充足性" placement="top">
              <span class="formula-col-header">预计未来应纳税所得额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span>{{ fmtAmount(row.futureTaxableIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可确认递延税资产" width="150" align="right">
          <template #header>
            <el-tooltip content="min(未弥补亏损, 预计未来应纳税所得额) × 税率" placement="top">
              <span class="formula-col-header">可确认递延税资产</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.recognizableAsset) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isExpired ? 'danger' : row.isInsufficient ? 'warning' : 'success'" size="small">
              {{ row.isExpired ? '已到期' : row.isInsufficient ? '不足' : '充足' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 5: 确认充足性判断说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>五、确认充足性判断说明</span>
          <el-button size="small" @click="handleAI('section-sufficiency')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="sufficiencyNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明管理层对未来应纳税所得额的预测依据、确认递延所得税资产的判断过程..."
        @change="handleSufficiencyNoteChange"
      />
    </el-card>

    <!-- ═══ Section 6: 与N3对应关系+N5联动 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>六、与N3递延所得税负债对应关系及N5联动</span>
          <el-button size="small" @click="handleAI('section-n3-n5')">
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
        <el-descriptions-item label="是否同一纳税主体">
          <el-tag :type="canOffset ? 'success' : 'warning'" size="small">
            {{ canOffset ? '是（可抵销净额列示）' : '否（分别列示）' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="本期变动额（供N5核对）">
          <span class="formula-value">{{ fmtAmount(deferredTaxChange.change) }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-input
        v-model="n3CorrespondenceNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="说明与N3递延所得税负债的抵销/分列情况，以及N5递延所得税费用核对..."
        @change="handleN3NoteChange"
        style="margin-top: 12px"
      />
    </el-card>

    <!-- ═══ Section 7: 审计说明及结论 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>七、审计说明及结论</span>
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
        placeholder="说明递延所得税资产附注披露的完整性、准确性，是否符合SASAC相关要求..."
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企格式74行×256列（SASAC标准，比上市公司更宽更详细）</li>
        <li>需列示确认依据、账面价值/计税基础双列及确认充足性判断</li>
        <li>数据优先从N1-1审定表、N1-2明细表、N1-5亏损检查表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新附注数据</li>
        <li>递延所得税资产 = 可抵扣暂时性差异 × 适用税率</li>
        <li>可弥补亏损确认：min(未弥补, 预计未来应纳税所得额) × 税率</li>
        <li>资产类借方科目1811：期末 = 期初 + 借方(确认) − 贷方(转回)</li>
        <li>弥补期限：一般5年，高新/科技型中小企业10年</li>
        <li>同一纳税主体可抵销净额列示，不同主体分别列示</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabDisclosureSoe — 递延所得税资产附注披露（国有企业）74×256
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 4.7
 * Requirements: 6.2-6.4
 *
 * 功能：
 * - 按SASAC标准格式渲染国有企业递延所得税资产附注结构(74行×256列，宽表)
 * - 比上市公司更详细：含账面价值/计税基础/确认依据/确认充足性说明
 * - 已确认递延税资产项目明细（含确认依据列）
 * - 余额变动表：年初→确认→转回→期末+变动原因
 * - 未确认递延税资产的可抵扣暂时性差异及可弥补亏损金额
 * - 可弥补亏损到期年度明细（含预计未来应纳税所得额+可确认额）
 * - 确认充足性判断说明
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
const canOffset = ref(true) // 是否同一纳税主体可抵销
const sufficiencyNote = ref('')
const n3CorrespondenceNote = ref('')
const conclusionNote = ref('')

// ─── Section 1: 已确认递延所得税资产明细 (含账面价值/计税基础) ────────────────

interface RecognizedDetailRow {
  item: string
  bookValue: number
  taxBase: number
  deductibleDiff: number
  taxRate: number
  deferredTaxAsset: number
  basis: string
  _isTotal?: boolean
}

const recognizedDetailRows = computed<RecognizedDetailRow[]>(() => {
  const resp = formData.allResponses.value.get('N1-2-rows')
  let rows: RecognizedDetailRow[] = []

  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) {
        rows = parsed.map((r: any) => ({
          item: r.item || r.projectName || '—',
          bookValue: Number(r.bookValue ?? 0),
          taxBase: Number(r.taxBase ?? 0),
          deductibleDiff: Number(r.deductibleDiff ?? r.temporaryDifference ?? 0),
          taxRate: Number(r.taxRate ?? r.applicableTaxRate ?? 0.25),
          deferredTaxAsset: Number(r.endDeferredTaxAsset ?? r.deferredTaxAsset ?? 0),
          basis: r.basis || r.recognitionBasis || '',
        }))
      }
    } catch { /* fallback */ }
  }

  // 默认分类
  if (rows.length === 0) {
    const defaultCategories = [
      '资产减值准备', '可弥补亏损', '预提费用/预计负债',
      '递延收益', '公允价值变动', '坏账准备', '固定资产折旧差异', '其他',
    ]
    rows = defaultCategories.map(item => ({
      item, bookValue: 0, taxBase: 0, deductibleDiff: 0,
      taxRate: 0.25, deferredTaxAsset: 0, basis: '',
    }))
  }

  // 合计行
  const totals = rows.reduce((acc, r) => ({
    deductibleDiff: acc.deductibleDiff + r.deductibleDiff,
    deferredTaxAsset: acc.deferredTaxAsset + r.deferredTaxAsset,
  }), { deductibleDiff: 0, deferredTaxAsset: 0 })

  rows.push({
    item: '合计', bookValue: 0, taxBase: 0,
    deductibleDiff: totals.deductibleDiff, taxRate: 0,
    deferredTaxAsset: totals.deferredTaxAsset, basis: '',
    _isTotal: true,
  })
  return rows
})

// ─── Section 2: 余额变动表 ──────────────────────────────────────────────────

interface MovementRow {
  item: string
  beginBalance: number
  recognized: number
  reversed: number
  endBalance: number
  changeReason: string
  _isTotal?: boolean
}

const movementRows = computed<MovementRow[]>(() => {
  const resp = formData.allResponses.value.get('N1-2-rows')
  let rows: MovementRow[] = []

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
            beginBalance: begin,
            recognized,
            reversed,
            endBalance: calcAssetEndBalance(begin, recognized, reversed),
            changeReason: r.changeReason || '',
          }
        })
      }
    } catch { /* fallback */ }
  }

  // 合计行
  const totals = rows.reduce((acc, r) => ({
    beginBalance: acc.beginBalance + r.beginBalance,
    recognized: acc.recognized + r.recognized,
    reversed: acc.reversed + r.reversed,
    endBalance: acc.endBalance + r.endBalance,
  }), { beginBalance: 0, recognized: 0, reversed: 0, endBalance: 0 })

  rows.push({ item: '合计', ...totals, changeReason: '', _isTotal: true })
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
  const resp = formData.allResponses.value.get('N1-disclosure-soe-unrecognized')
  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) return parsed
    } catch { /* fallback */ }
  }
  return [
    { item: '未确认的可抵扣暂时性差异', amount: 0, unrecognizedAsset: 0, reason: '' },
    { item: '未确认的可弥补亏损', amount: 0, unrecognizedAsset: 0, reason: '' },
    { item: '未确认的资产减值准备差异', amount: 0, unrecognizedAsset: 0, reason: '' },
  ]
})

function updateUnrecognizedReason(index: number, val: string) {
  const rows = [...unrecognizedRows.value]
  if (index >= 0 && index < rows.length) {
    rows[index] = { ...rows[index], reason: val }
    formData.debouncedSave('N1-disclosure-soe-unrecognized', { conclusion: JSON.stringify(rows) })
  }
}

// ─── Section 4: 可弥补亏损到期年度明细 ───────────────────────────────────────

interface LossExpiryRow {
  year: string
  lossAmount: number
  expiryYear: string
  recovered: number
  unrecovered: number
  futureTaxableIncome: number
  recognizableAsset: number
  isExpired: boolean
  isInsufficient: boolean
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
          futureTaxableIncome: Number(r.futureTaxableIncome ?? 0),
          recognizableAsset: Number(r.recognizableAsset ?? 0),
          isExpired: Boolean(r.isExpired),
          isInsufficient: Boolean(r.isInsufficient),
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

function handleSufficiencyNoteChange() {
  formData.debouncedSave('N1-disclosure-soe-sufficiency', { remark: sufficiencyNote.value || null })
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N1', section: 'sufficiency-soe', timestamp: Date.now(),
  })
}

function handleN3NoteChange() {
  formData.debouncedSave('N1-disclosure-soe-n3-correspondence', { remark: n3CorrespondenceNote.value || null })
}

function handleConclusionChange() {
  formData.debouncedSave('N1-disclosure-soe-conclusion', { remark: conclusionNote.value || null })
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N1', section: 'conclusion-soe', timestamp: Date.now(),
  })
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  // AI辅助 placeholder — 后续集成 AI 对话
}

function handleReview() {
  openReviewDialog?.('N1-disclosure-soe', '附注披露（国企）')
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const suffResp = formData.allResponses.value.get('N1-disclosure-soe-sufficiency')
  if (suffResp?.remark) sufficiencyNote.value = suffResp.remark

  const n3Resp = formData.allResponses.value.get('N1-disclosure-soe-n3-correspondence')
  if (n3Resp?.remark) n3CorrespondenceNote.value = n3Resp.remark

  const conclusionResp = formData.allResponses.value.get('N1-disclosure-soe-conclusion')
  if (conclusionResp?.remark) conclusionNote.value = conclusionResp.remark

  // 恢复是否同一纳税主体
  const offsetResp = formData.allResponses.value.get('N1-disclosure-soe-can-offset')
  if (offsetResp?.conclusion) canOffset.value = offsetResp.conclusion === 'true'
}

// ─── EventBus: 审定变化刷新 ─────────────────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => {
    restoreData()
    eventBus.emit('disclosure:note-text-updated', {
      wpCode: 'N1', section: 'auto-refresh-soe', timestamp: Date.now(),
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
.n1-tab-disclosure-soe { padding: 12px; font-size: 13px; }

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
