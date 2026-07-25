<!--
  M1TabDividendCheck.vue — M1-6 应付股利（利润）检查表（凭证级测试）

  忠实反映致同源模板 M1-6：
    一、测试目标（存在/准确性计价分摊 两认定）
    二、样本选取标准与规模
    三、测试（凭证级明细：日期/凭证编号/业务内容/对方科目/对方明细科目/借方/贷方 + 支持性文件 + 核对内容1-5 + 索引 + 是否异常 + 备注）
    四、审计说明（检查比例表：本期借方/本期贷方 → 账面/检查/比例）
    五、审计结论

  复用 useK1VoucherCheck（通用凭证检查状态）。科目 2232 应付股利（贷方/负债类）。
  源模板无"期后"段——仅本期发生额检查+检查比例（与K4-4同级）。
-->
<template>
  <div class="m1-tab-dividend-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认测试目标（两认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <div class="section-head-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="sheet-title">M1-6 应付股利（利润）检查表</h3>
      </div>
      <div class="head-actions">
        <el-button size="small" type="primary" link :loading="aiLoading" @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、测试目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的应付股利（利润）是存在的，且已记录在恰当的账户中；</li>
        <li><b>准确性、计价和分摊：</b>应付股利（利润）以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- P2: 覆盖率进度条 -->
    <div v-if="criteria.populationDebitAmount > 0 || criteria.populationCreditAmount > 0" class="coverage-bars">
      <div class="coverage-item">
        <span class="coverage-label">借方覆盖</span>
        <el-progress :percentage="debitCoveragePercent" :stroke-width="12" :color="debitCoveragePercent < 30 ? '#f56c6c' : debitCoveragePercent < 60 ? '#e6a23c' : '#67c23a'" :format="() => debitCoveragePercent.toFixed(1) + '%'" style="flex:1" />
        <span class="coverage-hint">{{ fmtAmt(occurrenceDebitChecked) }} / {{ fmtAmt(criteria.populationDebitAmount) }}</span>
      </div>
      <div class="coverage-item">
        <span class="coverage-label">贷方覆盖</span>
        <el-progress :percentage="creditCoveragePercent" :stroke-width="12" :color="creditCoveragePercent < 30 ? '#f56c6c' : creditCoveragePercent < 60 ? '#e6a23c' : '#67c23a'" :format="() => creditCoveragePercent.toFixed(1) + '%'" style="flex:1" />
        <span class="coverage-hint">{{ fmtAmt(occurrenceCreditChecked) }} / {{ fmtAmt(criteria.populationCreditAmount) }}</span>
      </div>
    </div>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>

      <!-- P2: M1-5 宣告差异联动提示 -->
      <el-alert v-if="m5DiffHint" type="warning" :closable="false" show-icon class="m5-diff-hint">
        <template #title>M1-5测算表提示：{{ m5DiffHint }}</template>
      </el-alert>

      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（借方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（贷方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small" placeholder="大额（XX金额以上）、关联方股利、异常款项全部测试" @change="persist" />
        </div>
        <div class="cg-item">
          <label>抽样总体</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.samplingPopulationCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.samplingPopulationAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样样本量</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.sampleSize" :controls="false" :disabled="isReadonly" size="small" placeholder="样本量" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样方法</label>
          <el-select v-model="criteria.samplingMethod" :disabled="isReadonly" size="small" @change="persist">
            <el-option label="随机选样" value="随机选样" />
            <el-option label="系统选样" value="系统选样" />
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随意选样（非统计抽样）" value="随意选样" />
          </el-select>
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" size="small" placeholder="使用IDEA（XX抽样工具）选择XX数量、金额XX的样本进行测试" @change="persist" />
        </div>
      </div>
    </el-card>

    <!-- 三、测试（本期发生额检查） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 本期发生额检查</span>
          <div>
            <el-popover placement="bottom-end" :width="200" trigger="click">
              <template #reference>
                <el-button size="small" circle><el-icon><Setting /></el-icon></el-button>
              </template>
              <div class="col-prefs-panel">
                <div class="col-prefs-title">⚙ 列设置</div>
                <el-checkbox v-for="col in VOUCHER_COLS" :key="col.key" v-model="colVisible[col.key]" @change="persistColPrefs">{{ col.label }}</el-checkbox>
                <el-button size="small" text type="primary" style="margin-top:6px" @click="resetColPrefs">重置默认</el-button>
              </div>
            </el-popover>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">+ 手工新增</el-button>
          </div>
        </div>
      </template>
      <div class="methodology-context-inner">
        对本期发生的应付股利（利润）增减变动，检查支持性文件，确定会计处理是否正确。借方=实际支付（减少义务），贷方=宣告分配（增加义务）。
      </div>
      <el-table :data="occurrenceRows" border size="small" :max-height="420" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="日期" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方明细科目" min-width="120" v-if="colVisible.offsetSubAccount">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" /><span v-else>{{ row.offsetSubAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="贷方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="120" v-if="colVisible.supportingDoc">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" placeholder="决议/付款凭证" @change="persist" /><span v-else>{{ row.supportingDoc || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="核对内容" width="180" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content><div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
              <span class="col-help">核对内容 &#9432;</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(lbl, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90" v-if="colVisible.indexNo">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" /><span v-else>{{ row.indexNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="是否异常" width="80" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column label="备注说明" min-width="120" v-if="colVisible.remark">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="选取原因" width="130" v-if="colVisible.selectionReason">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.selectionReason" size="small" style="width:100%" placeholder="原因" filterable allow-create @change="persist">
              <el-option v-for="opt in SELECTION_REASONS" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.selectionReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计 借方：{{ fmtAmt(occurrenceDebitChecked) }} 贷方：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例表）-->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">四、审计说明 — 检查比例</span>
          <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </div>
      </template>
      <el-table :data="m1CheckRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="120" />
        <el-table-column label="账面金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span></template></el-table-column>
        <el-table-column label="检查金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template></el-table-column>
        <el-table-column label="检查比例" width="130" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'" size="small" effect="plain">{{ (row.ratio * 100).toFixed(1) }}%</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="180">
          <template #default="{ row }">
            <span v-if="row.ratio != null && row.ratio < 0.3" class="ratio-low-hint">如果检查比例较低应扩大检查样本量或说明原因</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、结果；拟调整事项及分录、未调整事项及其影响等" @change="persist" />
      </div>
    </el-card>

    <!-- 异常凭证摘要 -->
    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">&#9888;&#65039; 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.businessContent || '（未填业务内容）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常，可以确认" value="A" />
        <el-option label="B、经审计调整后可确认" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 1314）</summary>
      <ul>
        <li>测试目标对应两项认定：存在、准确性/计价和分摊</li>
        <li>样本选取：测试总体扣除特定样本得抽样总体；大额、关联方股利、异常款项全部测试</li>
        <li>凭证检查：逐笔核对凭证与原始单据（股东会/董事会决议、付款审批单、银行回单）</li>
        <li>借方=实际支付股利（减少义务），贷方=宣告分配股利（增加义务）</li>
        <li>核对内容5项：凭证与原始单据相符 / 业务内容真实合理 / 会计科目正确 / 金额计算准确 / 截止期间正确</li>
        <li>检查比例 = 检查金额 / 账面金额；比例偏低（&lt;30%）须扩样或说明</li>
        <li>抽凭引擎复用序时账，科目 2232 应付股利</li>
        <li>编制说明：企业根据股东大会或类似机构审议批准的利润分配方案，按应支付的现金股利或利润，借记"利润分配"科目，贷记"应付股利"科目</li>
      </ul>
    </details>

    <!-- 抽凭引擎弹窗 -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 应付股利(2232)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2232" phase="current" :workpaper-id="props.wpId" :project-id="props.projectId" :year="year" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabDividendCheck.vue — M1-6 应付股利（利润）检查表（凭证级测试）
 *
 * 重建对齐源模板：复用 useK1VoucherCheck（通用凭证检查状态）。
 * 科目 2232 应付股利（贷方/负债类）。
 * 源模板无"期后"段——仅本期发生额检查+检查比例（与K4-4同级）。
 * 抽凭引擎 account-code=2232, phase=current。
 */
import { ref, computed, inject, onMounted, onUnmounted, reactive, defineAsyncComponent } from 'vue'
import { MagicStick, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'
import { useM1FormData } from '../../composables/useM1FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { eventBus } from '@/utils/eventBus'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const isReadonly = computed(() => props.isReadonly)
const year = computed(() => props.year ?? new Date().getFullYear())

// ─── FormData (for persistence) ─────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── useK1VoucherCheck ──────────────────────────────────────────────────────

const ITEM_ID = 'M1-6-voucher-check'

const {
  itemId, checkLabels,
  criteria, occurrenceRows, postCollectionRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: formData.allResponses, itemId: ITEM_ID })

// ─── 检查比例（源模板M1-6仅本期借方/本期贷方两行，无期末余额行） ─────────────

const m1CheckRatios = computed(() => {
  return checkRatios.value.filter(r => r.direction !== '期末余额')
})

// ─── P1: 列设置⚙ ────────────────────────────────────────────────────────────

const COL_PREFS_KEY = 'm1-6-column-prefs'

interface VoucherColDef { key: string; label: string; defaultVisible: boolean }

const VOUCHER_COLS: VoucherColDef[] = [
  { key: 'offsetSubAccount', label: '对方明细科目', defaultVisible: true },
  { key: 'supportingDoc', label: '支持性文件', defaultVisible: true },
  { key: 'indexNo', label: '索引号', defaultVisible: true },
  { key: 'remark', label: '备注说明', defaultVisible: true },
  { key: 'selectionReason', label: '选取原因', defaultVisible: false },
]

const colVisible = reactive<Record<string, boolean>>(
  Object.fromEntries(VOUCHER_COLS.map(c => [c.key, c.defaultVisible]))
)

// Load saved prefs
;(() => {
  try {
    const raw = localStorage.getItem(COL_PREFS_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as Record<string, boolean>
      for (const [k, v] of Object.entries(saved)) {
        if (k in colVisible) colVisible[k] = v
      }
    }
  } catch { /* ignore */ }
})()

function persistColPrefs(): void {
  localStorage.setItem(COL_PREFS_KEY, JSON.stringify({ ...colVisible }))
}

function resetColPrefs(): void {
  for (const col of VOUCHER_COLS) colVisible[col.key] = col.defaultVisible
  persistColPrefs()
}

// ─── P1: 测试原因选项 ──────────────────────────────────────────────────────

const SELECTION_REASONS = [
  '大额',
  '关联方',
  '大额交易频繁',
  '异常',
  '重要股东',
  '外币',
  '其他',
]

// ─── P2: 覆盖率进度条 ──────────────────────────────────────────────────────

const debitCoveragePercent = computed(() => {
  if (criteria.value.populationDebitAmount <= 0) return 0
  return Math.min((occurrenceDebitChecked.value / criteria.value.populationDebitAmount) * 100, 100)
})

const creditCoveragePercent = computed(() => {
  if (criteria.value.populationCreditAmount <= 0) return 0
  return Math.min((occurrenceCreditChecked.value / criteria.value.populationCreditAmount) * 100, 100)
})

// ─── P2: M1-5测算表交叉联动 ────────────────────────────────────────────────

const m5DiffHint = ref('')

function handleM5DeclareWarning(payload: any): void {
  const shareholders = payload?.shareholders || payload?.items || []
  if (Array.isArray(shareholders) && shareholders.length > 0) {
    const names = shareholders.map((s: any) => s.name || s.shareholderName || '').filter(Boolean)
    if (names.length > 0) {
      m5DiffHint.value = `以下股东宣告差异超阈值，建议纳入特定样本：${names.join('、')}`
    }
  }
}

// ─── AI loading state ───────────────────────────────────────────────────────

const aiLoading = ref(false)

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  load()
  // Subscribe to M1-5 declare diff warning
  eventBus.on('m1:declare-diff-warning' as any, handleM5DeclareWarning)
})

onUnmounted(() => {
  eventBus.off('m1:declare-diff-warning' as any, handleM5DeclareWarning)
})

// ─── Helpers ────────────────────────────────────────────────────────────────

function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

// ─── 抽凭引擎 ──────────────────────────────────────────────────────────────

const samplingVisible = ref(false)
function openSampling() { samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) {
  fillFromSamples('occurrence', payload?.samples ?? [])
  samplingVisible.value = false
  persist()
}

// ─── Persistence ────────────────────────────────────────────────────────────

function persist() {
  const data = serialize()
  formData.allResponses.value.set(ITEM_ID, { item_id: ITEM_ID, conclusion: null, remark: data })
  formData.debouncedSave(ITEM_ID, { remark: data })
}

function onConclusionOption(val: string) {
  const map: Record<string, string> = {
    A: '未见异常，可以确认。',
    B: '经审计调整后可确认。',
    C: '由于存在上述重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
  }
  if (map[val] && !conclusion.value) conclusion.value = map[val]
  persist()
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function abnormalRowClass({ row }: { row: K1VoucherRow }): string {
  return row.abnormal ? 'abnormal-row' : ''
}

async function handleAiGenerate() {
  if (isReadonly.value) return
  aiLoading.value = true
  try {
    const context: Record<string, string> = {
      科目: '2232 应付股利 / 凭证检查表（M1-6）',
      凭证笔数: String(occurrenceRows.value.length),
      本期借方检查: fmtAmt(occurrenceDebitChecked.value),
      本期贷方检查: fmtAmt(occurrenceCreditChecked.value),
      异常笔数: String(abnormalRows.value.length),
      借方覆盖率: debitCoveragePercent.value.toFixed(1) + '%',
      贷方覆盖率: creditCoveragePercent.value.toFixed(1) + '%',
    }
    const text = await generateAiText({ section: 'm1-6-voucher-check', context, existingContent: auditNote.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    auditNote.value = text
    persist()
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = false }
}

function handleReview() { openReviewDialog('M1-6-voucher-check') }
</script>

<style scoped>
.m1-tab-dividend-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%); border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.section-head-left { display: flex; align-items: center; gap: 8px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.criteria-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 18px; }
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item.cg-full { grid-column: 1 / -1; }
.cg-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.cg-inline { display: flex; align-items: center; gap: 5px; }
.cg-unit { font-size: 12px; color: var(--el-text-color-secondary); }
.num-sm { width: 78px; }
.num-md { width: 130px; }
.methodology-context-inner { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 12px; border-radius: 0 4px 4px 0; font-size: 12px; color: #78350f; line-height: 1.6; }
.voucher-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.col-help { cursor: help; border-bottom: 1px dashed var(--el-border-color); }
.check-group { display: flex; flex-wrap: wrap; gap: 0 4px; }
.check-group :deep(.el-checkbox) { margin-right: 4px; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }
.voucher-table :deep(.abnormal-row td) { background-color: #fef2f2 !important; }
.ratio-table { max-width: 720px; }
.ratio-low-hint { font-size: 11px; color: var(--el-color-danger); }
.muted { color: var(--el-text-color-placeholder); }
.note-block { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
.note-block label { font-size: 12px; color: var(--el-text-color-secondary); }
.abnormal-summary { margin-bottom: 10px; padding: 10px 12px; border-radius: 6px; background: #fef2f2; border: 1px solid #fecaca; }
.as-header { font-weight: 600; color: var(--el-color-danger); margin-bottom: 6px; }
.as-list { padding-left: 18px; margin: 0; line-height: 1.7; color: var(--el-color-danger-dark-2); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }

/* P2: 覆盖率进度条 */
.coverage-bars { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; padding: 10px 14px; background: linear-gradient(135deg, #f0fdf4, #ecfdf5); border: 1px solid #bbf7d0; border-radius: 6px; }
.coverage-item { display: flex; align-items: center; gap: 10px; }
.coverage-label { font-size: 12px; font-weight: 500; color: #166534; white-space: nowrap; min-width: 60px; }
.coverage-hint { font-size: 11px; color: #6b7280; white-space: nowrap; }

/* P1: 列设置面板 */
.col-prefs-panel { display: flex; flex-direction: column; gap: 4px; }
.col-prefs-title { font-size: 13px; font-weight: 600; margin-bottom: 4px; color: #303133; }

/* P2: M1-5联动提示 */
.m5-diff-hint { margin-bottom: 12px; }
</style>
