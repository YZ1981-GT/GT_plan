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
        <el-button
          size="small"
          type="success"
          :loading="syncing"
          @click="syncToDisclosureNotes"
        >
          同步到附注（{{ N1_NOTE_SECTION.soe }}）
        </el-button>
        <el-dropdown split-button size="small" type="primary" @click="jumpToNote('soe')">
          ↩ 跳转回附注（{{ N1_NOTE_SECTION.soe }}）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="jumpToNote('soe')">国企版（{{ N1_NOTE_SECTION.soe }}）</el-dropdown-item>
              <el-dropdown-item @click="jumpToNote('listed')">上市版（{{ N1_NOTE_SECTION.listed }}）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('disclosure-soe')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger :section-id="`N1-附注国企-${N1_NOTE_SECTION.soe}`" label="💬 复核" />
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
      <!-- hasData=false 时提示待编制（Req 4.4） -->
      <el-alert
        v-if="!lossPayload.hasData"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #title>
          待 N1-5 编制
        </template>
        <template v-if="lossPayload.isLegacyEstimate" #default>
          检测到旧版 N1-5 数据（推算值，非审计师确认／不确认录入），请完成 N1-5 新模型编制后刷新。
        </template>
      </el-alert>
      <el-table v-if="lossExpiryRows.length > 0" :data="lossExpiryRows" border size="small" style="width: 100%">
        <el-table-column prop="expiryYear" label="到期年度" width="100" align="center" />
        <el-table-column label="不确认金额" width="140" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.unrecognized) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期不确认金额" width="140" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.priorUnrecognized) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="不确认原因/依据" min-width="200" />
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

    <!-- ═══ 披露说明与结论 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>披露说明与结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusionNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明递延所得税资产确认依据、未确认原因及披露完整性核对结论..."
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
// @ts-ignore
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useN1FormData } from '../../composables/useN1FormData'
import { useN1CrossSheet } from '../../composables/useN1CrossSheet'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { N1_NOTE_SECTION, buildN1SyncPayload } from '../../composables/n1NoteSectionMap'
import { generateN1Text } from '../../composables/useN1AiText'
import {
  deriveDisclosureDetailRows,
  deriveDisclosureLossRows,
  deriveUnrecognizedFromLoss,
  deriveUnrecognizedLossPayload,
} from '../../composables/useN1DisclosureSource'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 审计年度（决定亏损弥补期限届满判断；缺省回退当前年） */
  year?: number
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// 复核入口由 GtReviewTrigger 内部 inject('openReviewDialog') 承载，本组件不再自持

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
const aiLoading = ref(false)

// 保存后自动同步到附注（防抖/非阻塞/失败静默/只读 gate；与手动按钮同源 syncToDisclosureNotes）
const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })

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
  // 真源键 N1-2-detail-rows + 派生金额同一 engine 重算（原读 N1-2-rows 是死链）
  let rows: RecognizedDetailRow[] = deriveDisclosureDetailRows(formData.allResponses.value).map(
    (r) => ({
      item: r.item,
      bookValue: r.bookValue,
      taxBase: r.taxBase,
      deductibleDiff: r.deductibleDiff,
      taxRate: r.taxRate,
      deferredTaxAsset: r.endBalance,
      basis: r.basis,
    }),
  )

  // 默认分类（对齐源模板附注(1)已确认递延所得税资产 7 类）
  if (rows.length === 0) {
    const defaultCategories = [
      '资产减值准备', '可抵扣亏损', '内部交易未实现利润',
      '公允价值变动', '租赁负债', '购入摊销年限小于税法规定的资产', '其他',
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
  const rows: MovementRow[] = deriveDisclosureDetailRows(formData.allResponses.value).map((r) => ({
    item: r.item,
    beginBalance: r.beginBalance,
    recognized: r.recognized,
    reversed: r.reversed,
    endBalance: r.endBalance,
    changeReason: '',
  }))

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
  amount: number | null
  unrecognizedAsset: number | null
  reason: string
}

/** N1-5 新模型取数（Req 4.1 / 4.4 / 4.5） */
const lossPayload = computed(() =>
  deriveUnrecognizedLossPayload(formData.allResponses.value),
)

const unrecognizedRows = computed<UnrecognizedRow[]>(() => {
  const resp = formData.allResponses.value.get('N1-disclosure-soe-unrecognized')
  let saved: UnrecognizedRow[] | null = null
  if (resp?.conclusion) {
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (Array.isArray(parsed)) saved = parsed
    } catch { /* fallback */ }
  }

  // 可弥补亏损未确认部分改由 deriveUnrecognizedLossPayload 供数（Req 4.1）
  // hasData = false 时金额传 null（不写 0，buildN1SyncPayload 的 nz() 保证不塌 0）
  const payload = lossPayload.value
  const lossAmount: number | null = payload.hasData ? payload.totalUnrecognized : null
  const lossAsset: number | null = lossAmount != null
    ? Math.round(lossAmount * 0.25 * 100) / 100
    : null

  const base: UnrecognizedRow[] = saved ?? [
    { item: '未确认的可抵扣暂时性差异', amount: 0, unrecognizedAsset: 0, reason: '' },
    { item: '未确认的可弥补亏损', amount: null, unrecognizedAsset: null, reason: '' },
    { item: '未确认的资产减值准备差异', amount: 0, unrecognizedAsset: 0, reason: '' },
  ]

  return base.map((r) =>
    r.item.includes('可弥补亏损')
      ? {
          ...r,
          // N1-5 新模型供数（Req 4.1）；hasData=false 时 null
          amount: lossAmount,
          unrecognizedAsset: lossAsset,
          reason: payload.hasData && payload.rows.length > 0
            ? payload.rows.map(lr => lr.reason).filter(Boolean).join('；') || r.reason
            : r.reason,
        }
      : r,
  )
})

function updateUnrecognizedReason(index: number, val: string) {
  const rows = [...unrecognizedRows.value]
  if (index >= 0 && index < rows.length) {
    rows[index] = { ...rows[index], reason: val }
    formData.debouncedSave('N1-disclosure-soe-unrecognized', { conclusion: JSON.stringify(rows) })
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  }
}

// ─── Section 4: 可弥补亏损到期明细（改由 deriveUnrecognizedLossPayload 供数）──

interface LossExpiryRow {
  expiryYear: string
  unrecognized: number
  priorUnrecognized: number
  reason: string
}

/** 审计年度（决定弥补期限届满判断）：props.year 优先，回退当前年 */
const auditYear = computed(() => props.year || new Date().getFullYear())

const lossExpiryRows = computed<LossExpiryRow[]>(() => {
  // 新取数：deriveUnrecognizedLossPayload 按到期年度聚合不确认口径行（Req 4.1）
  const payload = lossPayload.value
  if (!payload.hasData) return []
  return payload.rows
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

/**
 * 附注章节（权威源 note_template_variant_matrix.json）：
 * 递延所得税资产和递延所得税负债 → 国企 八、31（与 N1 上市 五、30 同一账务概念，N1/N3 共节）。
 * 载荷必须带 accountCode/projectId/sectionIds，否则附注模块定向刷新匹配不到。
 */
const N1_NOTE_SECTION_SOE = N1_NOTE_SECTION.soe

function _emitNoteUpdated(section: string, text?: string) {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N1',
    section,
    accountCode: '1811',
    projectId: props.projectId,
    sectionIds: [N1_NOTE_SECTION_SOE],
    ...(text !== undefined ? { text } : {}),
    timestamp: Date.now(),
  } as any)
}

function handleSufficiencyNoteChange() {
  formData.debouncedSave('N1-disclosure-soe-sufficiency', { remark: sufficiencyNote.value || null })
  _emitNoteUpdated('sufficiency-soe', sufficiencyNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleN3NoteChange() {
  formData.debouncedSave('N1-disclosure-soe-n3-correspondence', { remark: n3CorrespondenceNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleConclusionChange() {
  formData.debouncedSave('N1-disclosure-soe-conclusion', { remark: conclusionNote.value || null })
  _emitNoteUpdated('conclusion-soe', conclusionNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 同步到附注（结构化推送，owner=N1，见 n1NoteSectionMap 顶部所有权说明） ──

const router = useRouter()
const auditCtx = useAuditContext()
const syncing = ref(false)

/** 推送年度：props.year 优先，回退审计上下文；不依赖后端默认自然年 */
const syncYear = computed(() => props.year || auditCtx.year.value || new Date().getFullYear())

function buildSnapshot() {
  const assetRows = recognizedDetailRows.value
    .filter((r) => !r._isTotal)
    .map((r, i) => ({
      item: r.item,
      endBalance: r.deferredTaxAsset,
      // 期初余额取自变动表同名行（明细同源，按序号对齐）
      priorBalance: movementRows.value[i] && !movementRows.value[i]._isTotal
        ? movementRows.value[i].beginBalance
        : null,
    }))
  const liabEnd = n1ToN3.value.liabilityPart
  return {
    assetRows,
    liabilitySubtotal: {
      endBalance: liabEnd ? liabEnd : null,
      priorBalance: null,
    },
    unrecognizedRows: unrecognizedRows.value.map((r) => ({ item: r.item, amount: r.amount })),
    lossExpiryRows: lossExpiryRows.value.map((r) => ({
      expiryYear: r.expiryYear,
      unrecovered: r.unrecovered,
    })),
    notes: {
      conclusion: conclusionNote.value,
      sufficiency: sufficiencyNote.value,
      n3: n3CorrespondenceNote.value,
    },
  }
}

async function syncToDisclosureNotes() {
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法同步')
    return
  }
  syncing.value = true
  try {
    const payload = buildN1SyncPayload('soe', buildSnapshot(), {
      wpId: props.wpId,
      year: syncYear.value,
    })
    const resp: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = resp?.data?.data ?? resp?.data
    if (data?.success) {
      ElMessage.success(
        `已${data.created ? '新建' : '更新'}附注 ${data.section_id}：${data.rows_synced} 行`
        + (data.texts_synced ? `，正文 ${data.texts_synced} 段` : ''),
      )
      if (!n1ToN3.value.liabilityPart) {
        ElMessage.info('负债段暂无数据，待 N3 递延所得税负债编制后重新同步')
      }
      _emitNoteUpdated('sync-soe')
    } else {
      ElMessage.error('附注同步返回异常，请重试')
    }
  } catch (err: any) {
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
    ElMessage.error(`附注同步失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally {
    syncing.value = false
  }
}

/** 反向跳转：披露表 → 附注章节（仅导航，不改数据） */
function jumpToNote(variant: DisclosureVariant) {
  const route = buildNoteJumpRoute(props.projectId || '', 'N1', variant, syncYear.value)
  if (!route) {
    ElMessage.warning('缺少项目上下文，无法跳转附注')
    return
  }
  router.push(route)
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

/**
 * AI 辅助（真回填）。
 * - `section-sufficiency` → 回填确认充足性判断说明；`conclusion` → 回填披露说明与结论；其余 → 顾问式弹窗
 * - context 值全部转字符串（后端 dict[str,str]，此前传 wpId/对象导致 422 静默失败）
 */
async function handleAI(section: string) {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const isSufficiency = section === 'section-sufficiency'
    const isConclusion = section === 'conclusion'
    const text = await generateN1Text({
      wpId: props.wpId,
      section: `n1-disclosure-soe-${section}`,
      prompt: isSufficiency
        ? '请撰写确认充足性判断说明：管理层对未来应纳税所得额的预测依据、预测的合理性复核过程、据此确认（或不确认）递延所得税资产的判断结论。'
        : isConclusion
          ? '请撰写国企版递延所得税资产附注披露说明与结论：确认依据、未确认部分原因、抵销与列示口径、与审定表/明细表勾稽是否一致。'
          : `请基于递延所得税资产附注（国企）"${section}"区段数据给出披露复核建议。`,
      context: {
        章节: N1_NOTE_SECTION.soe,
        审计年度: String(syncYear.value ?? ''),
        递延税资产合计: String(n1ToN3.value.assetPart),
        递延税负债合计: String(n1ToN3.value.liabilityPart),
        本期变动额: String(deferredTaxChange.value.change),
        是否同一纳税主体可抵销: canOffset.value ? '是' : '否',
      },
      existingContent: isSufficiency
        ? sufficiencyNote.value
        : isConclusion
          ? conclusionNote.value
          : '',
    })
    if (!text) return
    if (isSufficiency) {
      sufficiencyNote.value = text
      handleSufficiencyNoteChange()
      ElMessage.success('AI 已生成确认充足性判断说明')
    } else if (isConclusion) {
      conclusionNote.value = text
      handleConclusionChange()
      ElMessage.success('AI 已生成披露说明与结论')
    } else {
      const { ElMessageBox } = await import('element-plus')
      await ElMessageBox.alert(text, 'AI 披露复核建议', { confirmButtonText: '知道了' }).catch(() => {})
    }
  } finally {
    aiLoading.value = false
  }
}

// 复核入口改用 GtReviewTrigger（自带蓝/红点，内部 inject openReviewDialog）

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
    _emitNoteUpdated('auto-refresh-soe')
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
  autoSync.cancelPending()
})
</script>

<style scoped>
.n1-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }

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
.unrecognized-amount { color: #e6a23c; font-weight: 500; }
.warning-amount { color: #f56c6c; font-weight: 500; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }

.n1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
