<template>
  <div class="k6-tab-disclosure-listed">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="openReview('K6-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS42第29-30条：持有待售的非流动资产或处置组应在附注中披露：(1)非流动资产或处置组的描述；(2)预计处置方式和时间安排；(3)已确认的减值损失及其金额；(4)报告期间处置组所产生的营业利润或亏损。上市公司按证监会格式披露。</p>
    </div>

    <!-- Section 1: 持有待售资产变动表 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>一、持有待售资产</span>
          <el-tag v-if="hasAutoData" type="primary" size="small" effect="light">跨sheet自动取数</el-tag>
        </div>
      </template>

      <el-table :data="assetTable" border size="small" style="width: 100%" max-height="350">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="账面原值" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计折旧" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.accumulatedDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值" width="110" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.fairValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售费用" width="100" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.sellingCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允净额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.fairValueNet) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <strong :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.closingBalance) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.remark"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="变动原因"
              @blur="(e: FocusEvent) => handleFieldChange(row.id, 'remark', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 2: 持有待售负债（底稿侧变动分析；附注两列口径见下方「附注表·持有待售负债」） -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>二、持有待售负债变动（底稿分析·不进附注）</span>
          <el-tag type="info" size="small" effect="plain">附注 五、11 请填下方「附注表·持有待售负债」</el-tag>
        </div>
      </template>

      <el-table :data="liabilityTable" border size="small" style="width: 100%" max-height="300">
        <el-table-column prop="category" label="项目" width="140" fixed />
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <strong :class="{ 'auto-data': row.isAutoFill }">{{ fmtAmt(row.closingBalance) }}</strong>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal"
              :model-value="row.remark"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="负债项说明"
              @blur="(e: FocusEvent) => handleLiabFieldChange(row.id, 'remark', (e.target as HTMLTextAreaElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 附注要求的 4 张表（改造前底稿完全没有录入位置） -->
    <K6NoteBlockTables variant="listed" :blocks="noteBlocks" :is-readonly="isReadonly" />

    <!-- Section 3: CAS42(3)(4) 减值损失 + 处置组损益 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>三、已确认减值损失及处置组损益（CAS42第30条）</span>
          <el-tag v-if="impairmentAutoFilled" type="primary" size="small" effect="light">减值自动取数</el-tag>
        </div>
      </template>
      <div class="cas42-fields">
        <div class="cas42-field">
          <span class="cas42-label">(3) 本期已确认减值损失金额</span>
          <WpAmountInput
            :model-value="impairmentLoss"
            :disabled="isReadonly"
            class="cas42-input"
            @change="(v?: number) => { impairmentLoss = v ?? 0; persistCas42() }"
          />
          <span class="cas42-hint">（来自K6-5减值测试/K6-1减值合计）</span>
        </div>
        <div class="cas42-field">
          <span class="cas42-label">(4) 报告期间处置组营业利润/亏损</span>
          <WpAmountInput
            :model-value="disposalGroupProfit"
            :disabled="isReadonly"
            class="cas42-input"
            @change="(v?: number) => { disposalGroupProfit = v ?? 0; persistCas42() }"
          />
          <span class="cas42-hint">（正=利润，负=亏损，计入终止经营损益）</span>
        </div>
        <div class="cas42-field">
          <span class="cas42-label">列报为终止经营</span>
          <el-select v-model="isDiscontinuedOp" :disabled="isReadonly" size="small" class="cas42-select" @change="persistCas42">
            <el-option label="是" value="yes" />
            <el-option label="否" value="no" />
          </el-select>
        </div>
      </div>
    </el-card>

    <!-- Section 4: 处置安排及说明 -->
    <el-card shadow="never" class="disclosure-section">
      <template #header>
        <div class="section-card-header">
          <span>四、非流动资产或处置组描述、处置方式和时间安排</span>
          <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="disposalNarrative"
        :disabled="isReadonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="描述非流动资产/处置组、预计处置方式和时间安排（CAS42第30条(1)(2)，可AI辅助生成）"
        @blur="handleNarrativeSave"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司格式（约79行×11列），分持有待售资产/负债/处置安排三大部分</li>
        <li>监听 substantive:adjudicated 自动同步K6-1审定数据（浅蓝色=跨sheet自动取数）</li>
        <li>公允价值净额=公允价值-预计出售费用（虚线公式列）</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>金额单位默认"元"，千分位分隔</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabDisclosureListed.vue — 附注披露（上市公司）
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.6
 * Requirements: 8.1
 *
 * 功能：
 * - 上市公司版附注披露 (79行×11列)
 * - subscribe 'substantive:adjudicated' 刷新
 * - AI辅助生成 (section='overall-opinion')
 * - autosize textarea for notes
 * - 审计说明 + 结论 el-card
 */
import { ref, computed, onMounted, onBeforeUnmount, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import K6NoteBlockTables from './K6NoteBlockTables.vue'
import { buildK6SyncPayload, K6_NOTE_SECTION } from '../../composables/k6NoteSectionMap'
import { useK6NoteBlocks } from '../../composables/useK6NoteBlocks'

const K6_ACCOUNT_CODE = '1481'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

/**
 * 附注 §五、11 要求的另外 4 张表（减值准备变动 / 非流动资产 / 处置组 / 持有待售负债）。
 * 改造前底稿完全没有这些录入位置 → 同步路径永远推不出这些表。
 */
const noteBlocks = useK6NoteBlocks({
  variant: 'listed',
  wpId: () => props.wpId,
  responses: () => props.allResponses,
  save: (itemId, remark) => emit('save', itemId, { remark }),
  onChanged: () => autoSync.scheduleAutoSync(syncToDisclosureNotes),
})

// ─── Data Models ─────────────────────────────────────────────────────────────

interface AssetDisclosureRow {
  id: string
  category: string
  originalCost: number
  accumulatedDep: number
  impairment: number
  bookValue: number       // 公式：原值 - 折旧 - 减值
  fairValue: number
  sellingCost: number
  fairValueNet: number    // 公式：公允 - 出售费用
  openingBalance: number
  closingBalance: number
  remark: string
  isTotal: boolean
  isAutoFill: boolean
}

interface LiabilityDisclosureRow {
  id: string
  category: string
  openingBalance: number
  increase: number
  decrease: number
  closingBalance: number
  remark: string
  isTotal: boolean
  isAutoFill: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────

const assetTable = ref<AssetDisclosureRow[]>([])
const liabilityTable = ref<LiabilityDisclosureRow[]>([])
const disposalNarrative = ref('')
const hasAutoData = ref(false)

// CAS42 第30条(3)(4) 减值损失 + 处置组损益
const impairmentLoss = ref(0)
const disposalGroupProfit = ref(0)
const isDiscontinuedOp = ref('')
const impairmentAutoFilled = ref(false)
const aiLoading = ref(false)

// ─── Init ────────────────────────────────────────────────────────────────────

function initDefaultAssetTable(): void {
  const categories = ['固定资产', '在建工程', '无形资产', '长期股权投资', '投资性房地产', '其他非流动资产']
  assetTable.value = [
    ...categories.map((cat, idx) => ({
      id: `asset-${idx}`,
      category: cat,
      originalCost: 0,
      accumulatedDep: 0,
      impairment: 0,
      bookValue: 0,
      fairValue: 0,
      sellingCost: 0,
      fairValueNet: 0,
      openingBalance: 0,
      closingBalance: 0,
      remark: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'asset-total',
      category: '合计',
      originalCost: 0,
      accumulatedDep: 0,
      impairment: 0,
      bookValue: 0,
      fairValue: 0,
      sellingCost: 0,
      fairValueNet: 0,
      openingBalance: 0,
      closingBalance: 0,
      remark: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

function initDefaultLiabTable(): void {
  const categories = ['应付账款', '其他应付款', '预收款项', '应付职工薪酬', '其他']
  liabilityTable.value = [
    ...categories.map((cat, idx) => ({
      id: `liab-${idx}`,
      category: cat,
      openingBalance: 0,
      increase: 0,
      decrease: 0,
      closingBalance: 0,
      remark: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'liab-total',
      category: '合计',
      openingBalance: 0,
      increase: 0,
      decrease: 0,
      closingBalance: 0,
      remark: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

// ─── Load ────────────────────────────────────────────────────────────────────

function loadSavedData(): void {
  const savedAssets = props.allResponses.get('K6-disclosure-listed-asset-table')
  if (savedAssets?.remark) {
    try { assetTable.value = JSON.parse(savedAssets.remark) }
    catch { initDefaultAssetTable() }
  } else {
    initDefaultAssetTable()
  }

  const savedLiab = props.allResponses.get('K6-disclosure-listed-liab-table')
  if (savedLiab?.remark) {
    try { liabilityTable.value = JSON.parse(savedLiab.remark) }
    catch { initDefaultLiabTable() }
  } else {
    initDefaultLiabTable()
  }

  const savedNarrative = props.allResponses.get('K6-disclosure-listed-narrative')
  if (savedNarrative?.remark) disposalNarrative.value = savedNarrative.remark

  noteBlocks.load()
  _loadCas42()
}

function applyAutoFill(): void {
  // 从K6-2明细表按类别聚合自动填充（K6-2 useK6Detail 持久化键为 K6-2-rows）
  const k6_2 = props.allResponses.get('K6-2-rows')
  const raw = k6_2?.remark ?? (typeof k6_2 === 'string' ? k6_2 : null)
  if (raw) {
    try {
      const rows = JSON.parse(raw)
      if (Array.isArray(rows) && rows.length > 0) {
        hasAutoData.value = true
        // 先清零非合计行的自动填充字段
        for (const row of assetTable.value) {
          if (row.isTotal) continue
          row.originalCost = 0; row.accumulatedDep = 0; row.impairment = 0
          row.bookValue = 0; row.fairValue = 0; row.sellingCost = 0; row.fairValueNet = 0
          row.closingBalance = 0; row.isAutoFill = false
        }
        // 按类别聚合K6-2明细
        for (const r of rows) {
          const cat = r.category || '其他非流动资产'
          let target = assetTable.value.find(x => !x.isTotal && x.category === cat)
          if (!target) target = assetTable.value.find(x => !x.isTotal && x.category === '其他非流动资产')
          if (!target) continue
          target.originalCost += Number(r.costValue) || 0
          target.accumulatedDep += Number(r.accumulatedDep) || 0
          target.impairment += Number(r.impairmentProvision) || 0
          target.bookValue += Number(r.bookValue) || 0
          target.fairValue += Number(r.fairValue) || 0
          target.sellingCost += Number(r.sellingCost) || 0
          target.fairValueNet += Number(r.fairValueNet) || 0
          target.closingBalance += Number(r.bookValue) || 0
          target.isAutoFill = true
        }
        recalcAssetTotals()
      }
    } catch { /* silent */ }
  }

  // 减值损失从K6-1减值合计 或 K6-5减值合计 自动带入（仅在未手工录入时）
  if (impairmentLoss.value === 0) {
    const k6_1_imp = props.allResponses.get('K6-1-impairment-total')
    const k6_5_imp = props.allResponses.get('K6-5-impairment-total')
    const impVal = Number(k6_1_imp?.remark ?? 0) || Number(k6_5_imp?.remark ?? 0) || 0
    if (impVal > 0) {
      impairmentLoss.value = impVal
      impairmentAutoFilled.value = true
    }
  }
}

function recalcAssetTotals(): void {
  const totalRow = assetTable.value.find(r => r.isTotal)
  if (totalRow) {
    const dataRows = assetTable.value.filter(r => !r.isTotal)
    totalRow.originalCost = dataRows.reduce((s, r) => s + r.originalCost, 0)
    totalRow.accumulatedDep = dataRows.reduce((s, r) => s + r.accumulatedDep, 0)
    totalRow.impairment = dataRows.reduce((s, r) => s + r.impairment, 0)
    totalRow.bookValue = dataRows.reduce((s, r) => s + r.bookValue, 0)
    totalRow.fairValue = dataRows.reduce((s, r) => s + r.fairValue, 0)
    totalRow.sellingCost = dataRows.reduce((s, r) => s + r.sellingCost, 0)
    totalRow.fairValueNet = dataRows.reduce((s, r) => s + r.fairValueNet, 0)
    totalRow.openingBalance = dataRows.reduce((s, r) => s + r.openingBalance, 0)
    totalRow.closingBalance = dataRows.reduce((s, r) => s + r.closingBalance, 0)
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleFieldChange(rowId: string, field: string, value: string): void {
  const row = assetTable.value.find(r => r.id === rowId)
  if (row) {
    ;(row as any)[field] = value
    persistAssetTable()
  }
}

function handleLiabFieldChange(rowId: string, field: string, value: string): void {
  const row = liabilityTable.value.find(r => r.id === rowId)
  if (row) {
    ;(row as any)[field] = value
    persistLiabTable()
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K6-disclosure-listed-narrative', { remark: disposalNarrative.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    wpCode: 'K6',
    variant: 'listed',
    text: disposalNarrative.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── CAS42(3)(4) 持久化 ──────────────────────────────────────────────────────

function persistCas42(): void {
  impairmentAutoFilled.value = false // 手工修改后取消自动标记
  emit('save', 'K6-disclosure-listed-cas42', {
    remark: JSON.stringify({
      impairmentLoss: impairmentLoss.value,
      disposalGroupProfit: disposalGroupProfit.value,
      isDiscontinuedOp: isDiscontinuedOp.value,
    }),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function _loadCas42(): void {
  const saved = props.allResponses.get('K6-disclosure-listed-cas42')
  if (saved?.remark) {
    try {
      const d = JSON.parse(saved.remark)
      impairmentLoss.value = Number(d.impairmentLoss) || 0
      disposalGroupProfit.value = Number(d.disposalGroupProfit) || 0
      isDiscontinuedOp.value = d.isDiscontinuedOp || ''
    } catch { /* ignore */ }
  }
}

// ─── AI辅助（真实接入/ai/generate-text） ─────────────────────────────────────

async function handleAiGenerate(): Promise<void> {
  if (props.isReadonly || aiLoading.value) return
  aiLoading.value = true
  try {
    const totalRow = assetTable.value.find(r => r.isTotal)
    const context: Record<string, string> = {
      '持有待售资产账面合计': String(totalRow?.bookValue ?? 0),
      '公允净额合计': String(totalRow?.fairValueNet ?? 0),
      '本期已确认减值损失': String(impairmentLoss.value),
      '处置组营业利润/亏损': String(disposalGroupProfit.value),
      '是否列报终止经营': isDiscontinuedOp.value === 'yes' ? '是' : isDiscontinuedOp.value === 'no' ? '否' : '未确定',
    }
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'k6-disclosure-listed',
      context,
      prompt: '根据持有待售资产/负债披露数据，生成上市公司附注披露说明（CAS42第30条：非流动资产或处置组描述、预计处置方式和时间安排、已确认减值损失金额、报告期间处置组营业利润或亏损）',
      existingContent: disposalNarrative.value,
    })
    const text = resp?.data?.content || resp?.data?.text || resp?.content || ''
    if (text) {
      disposalNarrative.value = text
      handleNarrativeSave()
      ElMessage.success('AI披露说明已生成')
    }
  } catch (e: any) {
    ElMessage.error('AI生成失败: ' + (e?.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

// ─── Persist ─────────────────────────────────────────────────────────────────

function persistAssetTable(): void {
  emit('save', 'K6-disclosure-listed-asset-table', { remark: JSON.stringify(assetTable.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function persistLiabTable(): void {
  emit('save', 'K6-disclosure-listed-liab-table', { remark: JSON.stringify(liabilityTable.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  // 附注 五、11 主表是两行表头 7 列：期末/上年年末 各 [账面余额, 减值准备, 账面价值]。
  // 上年年末仅 `openingBalance`（账面价值）有录入来源，账面余额/减值准备推 null（禁造数）。
  // 🔴 模板 `tables[1]` 的 name↔rows 错位（原「决策 B1 不推负债」的成因）已由
  // `fix_note_k_complex_structure.py` 正名 → 持有待售负债现在正常推送（2 列余额口径）。
  const rows = assetTable.value.filter(r => !r.isTotal).map(r => ({
    project: r.category,
    bookValue: r.bookValue ?? 0,
    impairment: r.impairment ?? 0,
    openingBalance: r.openingBalance ?? 0,
  }))
  const payload = buildK6SyncPayload('listed', props.wpId || '', {
    assets: rows,
    impairment: noteBlocks.impairment.value,
    nonCurrent: noteBlocks.nonCurrent.value,
    disposalGroup: noteBlocks.disposalGroup.value,
    listedLiabilities: noteBlocks.listedLiabilities.value,
    narrativeText: disposalNarrative.value,
  })
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K6', variant: 'listed', accountCode: '1481',
      projectId: props.projectId, sectionIds: [K6_NOTE_SECTION.listed],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── EventBus: subscribe 'substantive:adjudicated' ───────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K6_ACCOUNT_CODE || payload.wpCode === 'K6') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.wpCode === 'K6') {
    // 调整分录变化时刷新附注数据
    applyAutoFill()
  }
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
})

onBeforeUnmount(() => {
  autoSync.cancelPending()
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── Format ──────────────────────────────────────────────────────────────────

/** 只读金额展示：委托平台金额格式单一真源（千分符 + 2 位 + 单位偏好），保留「0 显示 -」语义 */
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return fmtAmount(v)
}
</script>

<style scoped>
.k6-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

.methodology-context {
  border-left: 3px solid #f0a500; background: #fef9e7; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #7d6608; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.disclosure-section { margin-bottom: 12px; }
.conclusion-card { margin-bottom: 12px; }
.section-card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

/* CAS42(3)(4) 字段 */
.cas42-fields { display: flex; flex-direction: column; gap: 12px; }
.cas42-field { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cas42-label { min-width: 220px; font-size: var(--wp-font-size, 13px); color: #303133; }
.cas42-input { width: 180px; }
.cas42-input :deep(.el-input__inner) { text-align: right; }
.cas42-select { width: 100px; }
.cas42-hint { font-size: 12px; color: #909399; }

.formula-col :deep(.cell) { border-bottom: 1px dashed #409eff; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.auto-data { color: #409eff; }

.k6-details-tip { margin-top: 16px; font-size: 12px; color: #666; }
.k6-details-tip summary { cursor: pointer; color: #409eff; font-weight: 500; }
.k6-details-tip ul { margin: 8px 0 0 16px; line-height: 1.8; }
</style>
