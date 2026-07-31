<template>
  <div class="k7-tab-disclosure-soe">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>附注披露信息（国有企业）</h3>
      <div class="header-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
        <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview?.('K7-disclosure-soe')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>国企版附注按CAS16政府补助准则，分"与资产相关"和"与收益相关"两类披露递延收益变动。列结构比上市公司版少1列（无"形成原因详细说明"），共18行×10列。数据从K7-1审定表自动获取。</p>
    </div>

    <!-- ═══ 自动取数提示 ═══ -->
    <el-alert v-if="hasAutoData" type="success" :closable="true" style="margin-bottom:10px" show-icon>
      <template #title>已从K7-1审定表自动取数填充附注数据</template>
    </el-alert>

    <!-- ═══ 与资产相关递延收益 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">与资产相关的政府补助</span>
        </div>
      </template>
      <el-table :data="assetRelatedRows" border size="small" style="width:100%" show-summary :summary-method="assetSummary">
        <el-table-column prop="project" label="项目" min-width="160" />
        <el-table-column prop="beginBalance" label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly && !row.isTotal" :model-value="row.beginBalance" @change="(v: number | undefined) => updateAssetField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly && !row.isTotal" :model-value="row.increase" @change="(v: number | undefined) => updateAssetField(row.id, 'increase', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly && !row.isTotal" :model-value="row.decrease" @change="(v: number | undefined) => updateAssetField(row.id, 'decrease', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`期末 = 期初 + 增加 - 减少`">{{ fmtAmt(row.beginBalance + row.increase - row.decrease) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 与收益相关递延收益 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">与收益相关的政府补助</span>
        </div>
      </template>
      <el-table :data="incomeRelatedRows" border size="small" style="width:100%" show-summary :summary-method="incomeSummary">
        <el-table-column prop="project" label="项目" min-width="160" />
        <el-table-column prop="beginBalance" label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly && !row.isTotal" :model-value="row.beginBalance" @change="(v: number | undefined) => updateIncomeField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly && !row.isTotal" :model-value="row.increase" @change="(v: number | undefined) => updateIncomeField(row.id, 'increase', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly && !row.isTotal" :model-value="row.decrease" @change="(v: number | undefined) => updateIncomeField(row.id, 'decrease', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`期末 = 期初 + 增加 - 减少`">{{ fmtAmt(row.beginBalance + row.increase - row.decrease) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 其中：递延收益-政府补助情况（附注模版 八、56 表2，10 列） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">其中：递延收益-政府补助情况</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addGrantRow">
            + 补助项目
          </el-button>
        </div>
      </template>

      <!-- 源模板红字提示（方法论上下文） -->
      <div class="grant-hint">
        【提示：1、仅披露金额重大的政府补助项目；2、应和相关科目明细项"政府补助"金额核对一致。】
      </div>

      <el-table :data="grantRows" border size="small" style="width:100%" :summary-method="grantSummary" show-summary>
        <el-table-column prop="grantItem" label="补助项目" min-width="150" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.grantItem"
              size="small"
              placeholder="补助项目名称"
              @input="(v: string) => updateGrantField(row.id, 'grantItem', v)"
            />
            <span v-else>{{ row.grantItem || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.beginBalance" @change="(v: number | undefined) => updateGrantField(row.id, 'beginBalance', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="newGrant" label="本期新增补助金额" width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.newGrant" @change="(v: number | undefined) => updateGrantField(row.id, 'newGrant', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.newGrant) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="toPl" label="本期计入损益金额" width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.toPl" @change="(v: number | undefined) => updateGrantField(row.id, 'toPl', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.toPl) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="plLineItem" label="本期计入损益的列报项目" width="170">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.plLineItem || ''"
              size="small"
              placeholder="点选列报项目"
              filterable
              allow-create
              @change="(v: string) => updateGrantField(row.id, 'plLineItem', v)"
            >
              <el-option v-for="opt in PL_LINE_ITEMS" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.plLineItem || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="refund" label="本期返还的金额" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.refund" @change="(v: number | undefined) => updateGrantField(row.id, 'refund', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.refund) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="otherChange" label="其他变动" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.otherChange" @change="(v: number | undefined) => updateGrantField(row.id, 'otherChange', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.otherChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末 = 期初 + 本期新增 − 本期计入损益 − 本期返还 − 其他变动">
              {{ fmtAmt(grantEnd(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="grantKind" label="与资产相关/与收益相关" width="160">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.grantKind || ''"
              size="small"
              placeholder="点选"
              @change="(v: string) => updateGrantField(row.id, 'grantKind', v)"
            >
              <el-option label="与资产相关" value="与资产相关" />
              <el-option label="与收益相关" value="与收益相关" />
            </el-select>
            <span v-else>{{ row.grantKind || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="refundReason" label="本期返还的原因" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.refundReason"
              size="small"
              placeholder="有返还时填列"
              @input="(v: string) => updateGrantField(row.id, 'refundReason', v)"
            />
            <span v-else>{{ row.refundReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link :disabled="isReadonly" @click="removeGrantRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 勾稽：本表合计期末 = 主表「政府补助」行期末 -->
      <div class="grant-tie" :class="{ 'tie-bad': !grantTieOk }">
        勾稽：本表合计期末余额 {{ fmtAmt(grantTotalEnd) }}
        <span v-if="grantRows.length === 0">（暂无重要政府补助项目，不推送该表）</span>
        <template v-else>
          ｜与资产相关 + 与收益相关合计期末 {{ fmtAmt(mainTotalEnd) }}
          <el-tag :type="grantTieOk ? 'success' : 'danger'" size="small" effect="light">
            {{ grantTieOk ? '一致' : `差异 ${fmtAmt(grantTotalEnd - mainTotalEnd)}` }}
          </el-tag>
        </template>
      </div>
    </el-card>

    <!-- ═══ 附注说明文本 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">附注说明</span>
          <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="handleAiNarrative">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="附注说明文本（可AI辅助生成）"
        @blur="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>附注 八、56 共 2 张表：主表「递延收益」（5 列）+ 表2「其中：递延收益-政府补助情况」（10 列）</li>
        <li>主表按相关类型分组披露：与资产相关 / 与收益相关（比上市版少"形成原因"列）</li>
        <li>期末余额为公式列：主表 期末=期初+增加−减少；表2 期末=期初+新增−计入损益−返还−其他变动</li>
        <li>表2 仅披露金额重大的政府补助项目；无行时不推送该表（避免覆盖附注模板骨架）</li>
        <li>数据来源：K7-1审定表审定数据，subscribe EventBus自动刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabDisclosureSoe.vue — 附注披露信息（国有企业）18行×10列
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.6
 * Requirements: 6.1
 *
 * 功能：
 * - 按相关类型（与资产相关/与收益相关）披露（比上市版少形成原因详细说明列）
 * - Columns: 项目/期初余额/本期增加/本期减少/期末余额
 * - Auto data fetch from K7-1 审定表 (subscribe substantive:adjudicated EventBus)
 * - AI assisted (section: overall-opinion)
 */
import { ref, computed, onMounted, onUnmounted, inject, toRef, type Ref } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import {
  buildK7SyncPayload,
  grantDetailEndAmount,
  K7_NOTE_SECTION,
  type K7GrantDetailRow,
} from '../../composables/k7NoteSectionMap'

const K7_ACCOUNT_CODE = '2401'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包顶层 ref → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface DisclosureRow {
  id: string
  project: string
  beginBalance: number
  increase: number
  decrease: number
  isTotal?: boolean
  isAutoFill?: boolean
}

/** 附注 八、56 表2「其中：递延收益-政府补助情况」行（10 列） */
interface GrantRow {
  id: string
  grantItem: string
  beginBalance: number
  newGrant: number
  toPl: number
  plLineItem: string
  refund: number
  otherChange: number
  grantKind: string
  refundReason: string
}

/** 「本期计入损益的列报项目」可选值 —— CAS16 允许的两个列报项目 + 常见冲减项 */
const PL_LINE_ITEMS = ['其他收益', '营业外收入', '冲减相关成本费用', '冲减资产折旧/摊销'] as const

const assetRelatedRows = ref<DisclosureRow[]>([])
const incomeRelatedRows = ref<DisclosureRow[]>([])
const grantRows = ref<GrantRow[]>([])
const narrativeText = ref('')
const hasAutoData = ref(false)

// ─── 默认行 ──────────────────────────────────────────────────────────────────

function initDefaultRows(): void {
  const assetDefaults = ['设备购置补助', '厂房建设补助', '技改项目补助', '环保设备补助', '其他与资产相关补助']
  const incomeDefaults = ['研发费用补助', '稳岗补贴', '产业扶持资金', '出口退税补贴', '其他与收益相关补助']

  assetRelatedRows.value = assetDefaults.map((name, idx) => ({
    id: `asset-${idx}`,
    project: name,
    beginBalance: 0,
    increase: 0,
    decrease: 0,
  }))

  incomeRelatedRows.value = incomeDefaults.map((name, idx) => ({
    id: `income-${idx}`,
    project: name,
    beginBalance: 0,
    increase: 0,
    decrease: 0,
  }))
}

// ─── 加载已保存数据 ──────────────────────────────────────────────────────────

function loadSavedData(): void {
  const savedAsset = allResponsesRef.value.get('K7-disclosure-soe-asset-rows')
  if (savedAsset?.remark) {
    try {
      assetRelatedRows.value = JSON.parse(savedAsset.remark)
    } catch { initDefaultRows() }
  } else {
    initDefaultRows()
  }

  const savedIncome = allResponsesRef.value.get('K7-disclosure-soe-income-rows')
  if (savedIncome?.remark) {
    try {
      incomeRelatedRows.value = JSON.parse(savedIncome.remark)
    } catch { /* keep default */ }
  }

  const savedGrant = allResponsesRef.value.get('K7-disclosure-soe-grant-rows')
  if (savedGrant?.remark) {
    try {
      const parsed = JSON.parse(savedGrant.remark)
      if (Array.isArray(parsed)) grantRows.value = parsed.map(normalizeGrantRow)
    } catch { /* keep empty */ }
  }

  const savedNarrative = allResponsesRef.value.get('K7-disclosure-soe-narrative')
  if (savedNarrative?.remark) {
    narrativeText.value = savedNarrative.remark
  }
}

/** 反序列化补齐字段（旧载荷可能缺列），防 undefined 进公式变 NaN */
function normalizeGrantRow(raw: any, idx: number): GrantRow {
  const n = (v: any): number => (typeof v === 'number' && Number.isFinite(v) ? v : Number(v) || 0)
  return {
    id: String(raw?.id || `grant-${idx}-${Date.now()}`),
    grantItem: String(raw?.grantItem ?? ''),
    beginBalance: n(raw?.beginBalance),
    newGrant: n(raw?.newGrant),
    toPl: n(raw?.toPl),
    plLineItem: String(raw?.plLineItem ?? ''),
    refund: n(raw?.refund),
    otherChange: n(raw?.otherChange),
    grantKind: String(raw?.grantKind ?? ''),
    refundReason: String(raw?.refundReason ?? ''),
  }
}

// ─── 自动取数（从K7-1审定表） ────────────────────────────────────────────────

function applyAutoFill(): void {
  const adjData = allResponsesRef.value.get('K7-1-audited-by-type')
  if (adjData?.remark) {
    hasAutoData.value = true
    try {
      const data = JSON.parse(adjData.remark)
      if (data?.assetRelated) {
        for (const row of assetRelatedRows.value) {
          const src = data.assetRelated[row.project]
          if (src) {
            row.beginBalance = Number(src.beginBalance ?? 0)
            row.increase = Number(src.increase ?? 0)
            row.decrease = Number(src.decrease ?? 0)
            row.isAutoFill = true
          }
        }
      }
      if (data?.incomeRelated) {
        for (const row of incomeRelatedRows.value) {
          const src = data.incomeRelated[row.project]
          if (src) {
            row.beginBalance = Number(src.beginBalance ?? 0)
            row.increase = Number(src.increase ?? 0)
            row.decrease = Number(src.decrease ?? 0)
            row.isAutoFill = true
          }
        }
      }
    } catch { /* silent */ }
  }
}

// ─── 字段更新 ────────────────────────────────────────────────────────────────

function updateAssetField(id: string, field: string, value: any): void {
  const row = assetRelatedRows.value.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
    persistAssetRows()
  }
}

function updateIncomeField(id: string, field: string, value: any): void {
  const row = incomeRelatedRows.value.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
    persistIncomeRows()
  }
}

// ─── 持久化 ──────────────────────────────────────────────────────────────────

function persistAssetRows(): void {
  emit('save', 'K7-disclosure-soe-asset-rows', { remark: JSON.stringify(assetRelatedRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistIncomeRows(): void {
  emit('save', 'K7-disclosure-soe-income-rows', { remark: JSON.stringify(incomeRelatedRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 政府补助明细表（附注 八、56 表2） ──────────────────────────────────────

/** F51-7a~7d：期末 = 期初 + 本期新增 − 本期计入损益 − 本期返还 − 其他变动（读时推导，不持久化） */
function grantEnd(row: GrantRow): number {
  return grantDetailEndAmount(toGrantPayloadRow(row))
}

function toGrantPayloadRow(row: GrantRow): K7GrantDetailRow {
  return {
    grantItem: row.grantItem,
    beginBalance: row.beginBalance,
    newGrant: row.newGrant,
    toPl: row.toPl,
    plLineItem: row.plLineItem,
    refund: row.refund,
    otherChange: row.otherChange,
    grantKind: row.grantKind,
    refundReason: row.refundReason,
  }
}

function addGrantRow(): void {
  grantRows.value.push({
    id: `grant-${Date.now()}-${grantRows.value.length}`,
    grantItem: '',
    beginBalance: 0,
    newGrant: 0,
    toPl: 0,
    plLineItem: '',
    refund: 0,
    otherChange: 0,
    grantKind: '',
    refundReason: '',
  })
  persistGrantRows()
}

function removeGrantRow(id: string): void {
  grantRows.value = grantRows.value.filter(r => r.id !== id)
  persistGrantRows()
}

function updateGrantField(id: string, field: keyof GrantRow, value: any): void {
  const row = grantRows.value.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value
  persistGrantRows()
}

function persistGrantRows(): void {
  emit('save', 'K7-disclosure-soe-grant-rows', { remark: JSON.stringify(grantRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

const grantTotalEnd = computed(() => grantRows.value.reduce((s, r) => s + grantEnd(r), 0))

/** 主表（与资产相关 + 与收益相关）期末合计 —— 递延收益全部为政府补助，故应与表2 合计相等 */
const mainTotalEnd = computed(() =>
  [...assetRelatedRows.value, ...incomeRelatedRows.value]
    .filter(r => !r.isTotal)
    .reduce((s, r) => s + r.beginBalance + r.increase - r.decrease, 0),
)

/** 容差 0.01 元（平台勾稽统一口径） */
const grantTieOk = computed(
  () => grantRows.value.length === 0 || Math.abs(grantTotalEnd.value - mainTotalEnd.value) < 0.01,
)

function grantSummary({ columns, data }: { columns: any[]; data: GrantRow[] }): string[] {
  const amountProps = ['beginBalance', 'newGrant', 'toPl', 'refund', 'otherChange']
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (amountProps.includes(prop)) {
      return fmtAmt(data.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0))
    }
    // 期末余额是公式列（无 prop），按列序定位：标签 + 5 个录入列 + 列报项目 = 索引 7
    if (idx === 7) return fmtAmt(data.reduce((s, r) => s + grantEnd(r), 0))
    return ''
  })
}

function handleNarrativeSave(): void {
  emit('save', 'K7-disclosure-soe-narrative', { remark: narrativeText.value })
  // Publish disclosure:note-text-updated
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K7',
    variant: 'soe',
    text: narrativeText.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  // 附注 八、56 表1 只有 4 个值列（**无 形成原因**：源 xlsx A7:E7 / 附注模版 L3972 /
  // note headers 三源一致，国企 `DisclosureRow` 也没有 `reason` 字段）。
  // 表2「其中：递延收益-政府补助情况」已补录入区块 → 有行才推（空表会整表覆盖模板骨架）。
  const rows = [...assetRelatedRows.value, ...incomeRelatedRows.value]
    .filter(r => !r.isTotal)
    .map(r => ({
      project: r.project,
      beginBalance: r.beginBalance ?? 0,
      increase: r.increase ?? 0,
      decrease: r.decrease ?? 0,
    }))
  const payload = buildK7SyncPayload(
    'soe',
    props.wpId || '',
    rows,
    narrativeText.value,
    grantRows.value.map(toGrantPayloadRow),
  )
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K7', variant: 'soe', accountCode: '2401',
      projectId: props.projectId, sectionIds: [K7_NOTE_SECTION.soe],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── 合计汇总方法 ────────────────────────────────────────────────────────────

function assetSummary({ columns, data }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (['beginBalance', 'increase', 'decrease'].includes(prop)) {
      const total = data.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0)
      return fmtAmt(total)
    }
    if (idx === 4) {
      const total = data.reduce((s, r) => s + r.beginBalance + r.increase - r.decrease, 0)
      return fmtAmt(total)
    }
    return ''
  })
}

function incomeSummary({ columns, data }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (['beginBalance', 'increase', 'decrease'].includes(prop)) {
      const total = data.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0)
      return fmtAmt(total)
    }
    if (idx === 4) {
      const total = data.reduce((s, r) => s + r.beginBalance + r.increase - r.decrease, 0)
      return fmtAmt(total)
    }
    return ''
  })
}

// ─── AI ──────────────────────────────────────────────────────────────────────

/**
 * 🔴 原实现只 `emit('save', ...ai-trigger)` 写一个 marker、从不调 AI 端点 —— 按钮可见但空转。
 * prompt 写明源模板 / CAS16 口径 + 「不得虚构」约束（平台铁律：过短或无约束的 prompt
 * 会诱导模型自造披露内容）。
 */
const aiLoading = ref(false)

/** 把当前表体摘要成 context（值必须全为字符串，`/ai/generate-text` 要求 dict[str,str]） */
function buildAiContext(): Record<string, string> {
  const fmtRows = (list: DisclosureRow[]): string => list
    .filter(r => !r.isTotal && (r.beginBalance || r.increase || r.decrease))
    .map(r => `${r.project}：期初${fmtAmt(r.beginBalance)}｜增加${fmtAmt(r.increase)}｜减少${fmtAmt(r.decrease)}｜期末${fmtAmt(r.beginBalance + r.increase - r.decrease)}`)
    .join('；')
  const grantDetail = grantRows.value
    .filter(r => r.grantItem || r.beginBalance || r.newGrant || r.toPl)
    .map(r => `${r.grantItem || '未命名补助'}：期初${fmtAmt(r.beginBalance)}｜新增${fmtAmt(r.newGrant)}｜计入损益${fmtAmt(r.toPl)}（列报于${r.plLineItem || '未选'}）｜返还${fmtAmt(r.refund)}｜期末${fmtAmt(grantEnd(r))}｜${r.grantKind || '类型未选'}`)
    .join('；')
  return {
    科目: '2401 递延收益（国有企业版）',
    附注章节: K7_NOTE_SECTION.soe,
    与资产相关: fmtRows(assetRelatedRows.value) || '（暂无数据）',
    与收益相关: fmtRows(incomeRelatedRows.value) || '（暂无数据）',
    政府补助明细: grantDetail || '（暂无数据）',
    既有说明: narrativeText.value || '（空）',
  }
}

async function runAi(section: string, prompt: string): Promise<void> {
  if (!props.wpId || props.isReadonly || aiLoading.value) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt,
      context: buildAiContext(),
      existingContent: narrativeText.value || '',
    })
    const generated = (res.data?.data ?? res.data)?.content || ''
    if (!generated) {
      ElMessage.warning('AI 未生成内容')
      return
    }
    await ElMessageBox.confirm(
      `AI 生成内容预览：\n\n${generated.slice(0, 300)}${generated.length > 300 ? '…' : ''}`,
      'AI 生成确认',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    narrativeText.value = narrativeText.value ? `${narrativeText.value}\n${generated}` : generated
    handleNarrativeSave()
    ElMessage.success('已填入 AI 生成内容')
  } catch {
    /* 取消或失败：静默（与平台既有披露 Tab 一致） */
  } finally {
    aiLoading.value = false
  }
}

function handleAiGenerate(): Promise<void> {
  return runAi(
    'k7-disclosure-soe-overall',
    '请依据致同 2025 修订版底稿 K7 源模板与国企附注模版（八、56 递延收益）撰写附注整体披露说明：'
    + '按 CAS16《政府补助》说明与资产相关、与收益相关政府补助的种类及金额、'
    + '计入当期损益的政府补助金额及其列报项目（其他收益/营业外收入/冲减相关成本费用）、'
    + '本期返还的政府补助金额及原因，并说明递延收益的摊销方法与剩余摊销期限。'
    + '只能使用已提供的项目名称与金额，不得虚构补助项目、批文、金额或摊销年限，'
    + '无把握的内容留空由审计师补充。',
  )
}

function handleAiNarrative(): Promise<void> {
  return runAi(
    'k7-disclosure-soe-narrative',
    '请依据致同 2025 修订版底稿 K7 源模板与国企附注模版（八、56 递延收益）撰写附注说明文本：'
    + '逐项说明重要政府补助项目的批准文号/来源、与资产相关或与收益相关的判断依据、'
    + '确认与摊销方法（与资产相关按资产使用寿命分期计入其他收益）、'
    + '以及是否存在需返还的情形及其原因。口径依 CAS16 与财会〔2018〕15 号文披露要求。'
    + '只能使用已提供的项目名称与金额，不得虚构补助文件、拨付单位或金额，'
    + '无把握的内容留空由审计师补充。',
  )
}

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K7_ACCOUNT_CODE || payload.wpCode === 'K7') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.accountCode === K7_ACCOUNT_CODE || payload.wpCode === 'K7') {
    applyAutoFill()
  }
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
})

onUnmounted(() => {
  autoSync.cancelPending()
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── 格式化 ──────────────────────────────────────────────────────────────────

/** 只读金额展示：委托平台金额格式单一真源，保留底稿「0 显示 -」语义 */
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  return fmtAmount(val)
}
</script>

<style scoped>
.k7-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.disclosure-card { margin-bottom: 14px; }
.disclosure-card :deep(.el-card__header) { padding: 10px 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.formula-cell { text-decoration: underline dashed; cursor: help; color: #409eff; }
.grant-hint { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 8px 12px; margin-bottom: 10px; border-radius: 4px; color: #78350f; line-height: 1.6; }
.grant-tie { margin-top: 8px; padding: 6px 12px; background: #f4f4f5; border-radius: 4px; color: #606266; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.grant-tie.tie-bad { background: #fef0f0; color: #f56c6c; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table__footer-wrapper td) { font-weight: 600; }
.k7-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
