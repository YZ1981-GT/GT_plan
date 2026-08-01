<!--
  N2TabTaxCheck.vue — N2-11 应交税费检查表（凭证级测试）

  忠实反映致同源模板 K1-12 凭证检查范式（复用 useK1VoucherCheck）：
    一、审计目标（完整性/存在/计价准确性 三认定）
    二、样本选取标准与规模（+ 测试原因 checkbox）
    三、测试（应交税费凭证级检查，含核对内容 1-5）
    四、审计说明（检查比例：本期借方/本期贷方 — 应交税费为损益/负债往来，过滤期末余额行）
    五、审计结论（模板 A/B/C 一键套用）

  科目 2221 应交税费（贷方/负债类）。宽表：列设置 ⚙ popover。
  自持久化（useN2FormData），item_id: N2-11-voucher-check / N2-11-test-meta。
-->
<template>
  <div class="n2-tab-tax-check">
    <!-- 引导区 -->
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认审计目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与测试原因</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">N2-11 应交税费检查表</h3>
      <div class="head-actions">
        <el-popover placement="bottom-end" :width="260" trigger="click">
          <template #reference>
            <el-button size="small">⚙ 列设置</el-button>
          </template>
          <div class="col-prefs">
            <div class="col-prefs-title">显示/隐藏列</div>
            <el-checkbox
              v-for="col in columnDefs"
              :key="col.key"
              v-model="col.visible"
              size="small"
              @change="persistColumnPrefs"
            >
              {{ col.label }}
            </el-checkbox>
            <el-divider style="margin:8px 0" />
            <el-button size="small" link @click="resetColumnPrefs">重置默认</el-button>
          </div>
        </el-popover>
        <el-button size="small" type="primary" link :loading="noteAiLoading" @click="handleNoteAi">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>完整性：</b>所有应当计提缴纳的税费均已完整记录，无漏计漏缴（负债完整性为重点）；</li>
        <li><b>存在：</b>资产负债表中记录的应交税费于资产负债表日确实存在，属被审计单位应履行的纳税义务；</li>
        <li><b>计价和分摊：</b>各税种以恰当金额记录，计税依据、税率及计提缴纳金额计算准确、期间归属正确。</li>
      </ol>
    </el-alert>

    <!-- 方法论 -->
    <div class="methodology-context">
      <p>应交税费（2221）为<strong>贷方/负债类</strong>科目。逐笔检查计提/缴纳凭证与原始单据（纳税申报表/完税凭证/银行回单），核对：①原始凭证是否齐全 ②记账凭证与原始凭证是否相符 ③会计科目及税种分类是否正确 ④计税依据×税率=应交金额是否准确 ⑤是否记录于恰当会计期间。</p>
    </div>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（本期借方/缴纳）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（本期贷方/计提）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
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
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额计提/缴纳、税收优惠事项、异常税种全部测试" @change="persist" />
        </div>
        <div class="cg-item cg-full">
          <label>测试原因</label>
          <el-checkbox-group v-model="testReasons" :disabled="isReadonly" size="small" @change="persistTestMeta">
            <el-checkbox label="大额" />
            <el-checkbox label="关联方" />
            <el-checkbox label="大额交易频繁" />
            <el-checkbox label="异常" />
            <el-checkbox label="其他" />
          </el-checkbox-group>
        </div>
      </div>
    </el-card>

    <!-- 三、测试 — 应交税费凭证检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 应交税费凭证检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="460" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="税种/项目" min-width="130" fixed>
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('date')" label="日期" width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('voucherNo')" label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('businessContent')" label="业务内容" min-width="150">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('offsetAccount')" label="对方科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('offsetSubAccount')" label="明细科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" /><span v-else>{{ row.offsetSubAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('debitAmount')" label="借方(缴纳)" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('creditAmount')" label="贷方(计提)" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('supportingDoc')" label="支持性文件" min-width="130">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" placeholder="申报表/完税凭证/银行回单" @change="persist" /><span v-else>{{ row.supportingDoc || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('checks')" label="核对内容" width="180" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content><div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(lbl, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('indexNo')" label="索引号" width="90">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" /><span v-else>{{ row.indexNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('abnormal')" label="是否异常" width="80" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('remark')" label="备注说明" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计　借方：{{ fmtAmt(occurrenceDebitChecked) }}　贷方：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例：本期借方/本期贷方）-->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="n2CheckRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="140" />
        <el-table-column label="账面金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span></template></el-table-column>
        <el-table-column label="检查金额" align="right"><template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template></el-table-column>
        <el-table-column label="检查比例" width="130" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'" size="small" effect="plain">{{ (row.ratio * 100).toFixed(1) }}%</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lowN2RatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%），应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <div class="note-head">
          <label>审计说明</label>
          <el-button size="small" type="primary" link :loading="noteAiLoading" @click="handleNoteAi"><el-icon><MagicStick /></el-icon> AI辅助说明</el-button>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、检查比例、发现的问题等" @change="persist" />
      </div>
    </el-card>

    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填项目）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">五、审计结论</span>
          <el-button size="small" type="primary" link :loading="conclusionAiLoading" @click="handleConclusionAi"><el-icon><MagicStick /></el-icon> AI辅助结论</el-button>
        </div>
      </template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板（一键套用）" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>逐笔核对：①原始凭证齐全（申报表/完税凭证/银行回单）②记账凭证与原始凭证相符 ③会计科目/税种分类正确 ④计税依据×税率=应交金额计算准确 ⑤记录于恰当会计期间</li>
        <li>检查比例 = 检查金额 / 本期发生额（本期借方缴纳、本期贷方计提；应交税费往来性质，过滤期末余额行）</li>
        <li>抽凭引擎复用序时账，科目 2221 应交税费（贷方/负债类）</li>
        <li>对存在问题的税种，详细描述差异原因并获取管理层解释</li>
      </ul>
    </details>

    <!-- 抽凭引擎 -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 应交税费(2221)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible"
        account-code="2221"
        phase="final"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabTaxCheck.vue — N2-11 应交税费检查表（凭证级测试，复用 useK1VoucherCheck）
 *
 * 科目 2221 应交税费（贷方/负债类）。源模板 K1-12 凭证检查范式。
 * 自持久化（useN2FormData）：item_id N2-11-voucher-check（凭证/说明/结论）+ N2-11-test-meta（测试原因）。
 * 检查比例仅本期借方/本期贷方（过滤期末余额行）。宽表列设置 ⚙。
 */
import { ref, reactive, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'
import { useN2FormData } from '../../composables/useN2FormData'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
  year?: string
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── FormData（自持久化）─────────────────────────────────────────────────────

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const isReadonly = computed(() => props.isReadonly ?? false)
const samplingYear = computed(() => props.year || String(new Date().getFullYear()))

// ─── useK1VoucherCheck（N2-11-voucher-check）──────────────────────────────────

const ITEM_ID = 'N2-11-voucher-check'

const {
  itemId, checkLabels,
  criteria, occurrenceRows, auditNote, conclusion, conclusionOption,
  checkRatios, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: formData.allResponses as any, itemId: ITEM_ID })

// N2-11 检查比例仅本期借方/本期贷方（过滤期末余额行 — 应交税费往来性质）
const n2CheckRatios = computed(() => checkRatios.value.filter(r => r.direction !== '期末余额'))
const lowN2RatioWarnings = computed(() => n2CheckRatios.value.filter(r => r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0))

// 测试原因 checkbox（persist N2-11-test-meta）
const testReasons = ref<string[]>([])

// ─── 列设置（宽表功能）─────────────────────────────────────────────────────────

const COLUMN_PREFS_KEY = 'n2-11-column-prefs'
interface ColDef { key: string; label: string; visible: boolean }
const columnDefs = reactive<ColDef[]>([
  { key: 'date', label: '日期', visible: true },
  { key: 'voucherNo', label: '凭证编号', visible: true },
  { key: 'businessContent', label: '业务内容', visible: true },
  { key: 'offsetAccount', label: '对方科目', visible: true },
  { key: 'offsetSubAccount', label: '明细科目', visible: false },
  { key: 'debitAmount', label: '借方(缴纳)', visible: true },
  { key: 'creditAmount', label: '贷方(计提)', visible: true },
  { key: 'supportingDoc', label: '支持性文件', visible: false },
  { key: 'checks', label: '核对内容', visible: true },
  { key: 'indexNo', label: '索引号', visible: false },
  { key: 'abnormal', label: '是否异常', visible: true },
  { key: 'remark', label: '备注说明', visible: true },
])
function isColVisible(key: string): boolean { return columnDefs.find(c => c.key === key)?.visible ?? true }
function persistColumnPrefs(): void {
  try { localStorage.setItem(COLUMN_PREFS_KEY, JSON.stringify(columnDefs.map(c => ({ key: c.key, visible: c.visible })))) } catch { /* */ }
}
function loadColumnPrefs(): void {
  try {
    const saved = localStorage.getItem(COLUMN_PREFS_KEY)
    if (!saved) return
    const prefs: Array<{ key: string; visible: boolean }> = JSON.parse(saved)
    for (const p of prefs) {
      const col = columnDefs.find(c => c.key === p.key)
      if (col) col.visible = p.visible
    }
  } catch { /* */ }
}
function resetColumnPrefs(): void {
  const hiddenByDefault = new Set(['offsetSubAccount', 'supportingDoc', 'indexNo'])
  for (const col of columnDefs) col.visible = !hiddenByDefault.has(col.key)
  persistColumnPrefs()
}
loadColumnPrefs()

// ─── 核对内容勾选 ─────────────────────────────────────────────────────────────

function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

// ─── 抽凭 ────────────────────────────────────────────────────────────────────

const samplingVisible = ref(false)
function openSampling() { samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) {
  fillFromSamples('occurrence', payload?.samples ?? [])
  samplingVisible.value = false
  persist()
  ElMessage.success(`已回填 ${(payload?.samples ?? []).length} 笔抽样凭证`)
}

// ─── 持久化 ──────────────────────────────────────────────────────────────────

function persist() {
  formData.debouncedSave(ITEM_ID, { remark: serialize() })
}

function persistTestMeta() {
  formData.debouncedSave('N2-11-test-meta', { conclusion: JSON.stringify(testReasons.value) })
}

function onConclusionOption(val: string) {
  const map: Record<string, string> = {
    A: '未见异常。',
    B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
    C: '由于存在重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
  }
  if (map[val] && !conclusion.value) conclusion.value = map[val]
  persist()
}

// ─── AI 真回填 ───────────────────────────────────────────────────────────────

const noteAiLoading = ref(false)
const conclusionAiLoading = ref(false)

function _buildAiContext(): Record<string, string> {
  return {
    科目: '2221 应交税费（负债类）',
    凭证笔数: String(occurrenceRows.value.length),
    本期借方检查合计: occurrenceDebitChecked.value.toFixed(2),
    本期贷方检查合计: occurrenceCreditChecked.value.toFixed(2),
    异常凭证笔数: String(abnormalRows.value.length),
  }
}

async function _aiGenerate(section: string, prompt: string, existing: string): Promise<string> {
  const h = (await import('@/utils/http')).default
  const res: any = await h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
    section,
    prompt,
    existingContent: existing || '',
    context: _buildAiContext(),
  })
  return res?.data?.data?.content ?? res?.data?.content ?? res?.content ?? ''
}

async function handleNoteAi() {
  noteAiLoading.value = true
  try {
    const text = await _aiGenerate(
      'n2-tax-check-note',
      '请基于应交税费凭证级检查结果，撰写审计说明（说明抽凭范围、检查比例、核对结果及异常发现，简洁专业）。',
      auditNote.value,
    )
    if (text) {
      auditNote.value = text
      persist()
      ElMessage.success('AI 已生成审计说明')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败')
  } finally {
    noteAiLoading.value = false
  }
}

async function handleConclusionAi() {
  conclusionAiLoading.value = true
  try {
    const text = await _aiGenerate(
      'n2-tax-check-conclusion',
      '请基于应交税费检查表数据，给出综合审计结论。',
      conclusion.value,
    )
    if (text) {
      conclusion.value = text
      persist()
      ElMessage.success('AI 已生成审计结论')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败')
  } finally {
    conclusionAiLoading.value = false
  }
}

// ─── 复核 ────────────────────────────────────────────────────────────────────

function handleReview() {
  openReviewDialog?.('N2-11-应交税费检查')
}

// ─── 工具 ────────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function abnormalRowClass({ row }: { row: K1VoucherRow }): string { return row.abnormal ? 'abnormal-row' : '' }

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreTestMeta(): void {
  const resp = formData.allResponses.value.get('N2-11-test-meta')
  if (resp?.conclusion) {
    try {
      const arr = JSON.parse(resp.conclusion)
      if (Array.isArray(arr)) testReasons.value = arr.filter((x) => typeof x === 'string')
    } catch { /* ignore */ }
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  load()
  restoreTestMeta()
})
</script>

<style scoped>
.n2-tab-tax-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%); border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.col-prefs { max-height: 320px; overflow-y: auto; }
.col-prefs-title { font-weight: 600; margin-bottom: 8px; font-size: 13px; }
.col-prefs :deep(.el-checkbox) { display: block; margin-bottom: 4px; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
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
.voucher-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.col-help { cursor: help; border-bottom: 1px dashed var(--el-border-color); }
.check-group { display: flex; flex-wrap: wrap; gap: 0 4px; }
.check-group :deep(.el-checkbox) { margin-right: 4px; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }
.voucher-table :deep(.abnormal-row td) { background-color: #fef2f2 !important; }
.ratio-table { max-width: 640px; }
.ratio-warn { margin-top: 12px; }
.muted { color: var(--el-text-color-placeholder); }
.note-block { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
.note-head { display: flex; align-items: center; justify-content: space-between; }
.note-head label { font-size: 12px; color: var(--el-text-color-secondary); }
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
</style>
