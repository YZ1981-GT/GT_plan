<!--
  K7TabDeferredCheck.vue — K7-5 递延收益检查表（凭证级测试）

  忠实反映致同源模板 K7-5（镜像 K1-12 简化版）：
    一、审计目标（存在/义务/计价分摊 三认定）
    二、样本选取标准与规模
    三、测试（政府补助凭证检查，含测试原因 checkbox + 核对内容1-5）
    四、审计说明（检查比例：仅贷方 — 源模板特点）
    五、审计结论

  复用 useK1VoucherCheck。科目 2401 递延收益（贷方/负债类）。
  宽表：列设置功能（⚙ popover 选择隐藏列）。
-->
<template>
  <div class="k7-tab-check">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认审计目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">K7-5 递延收益检查表</h3>
      <div class="head-actions">
        <el-popover placement="bottom-end" :width="260" trigger="click">
          <template #reference>
            <el-button size="small">⚙ 列设置</el-button>
          </template>
          <div class="col-prefs">
            <div class="col-prefs-title">显示/隐藏列</div>
            <el-checkbox v-for="col in columnDefs" :key="col.key" v-model="col.visible" size="small" @change="persistColumnPrefs">
              {{ col.label }}
            </el-checkbox>
            <el-divider style="margin:8px 0" />
            <el-button size="small" link @click="resetColumnPrefs">重置默认</el-button>
          </div>
        </el-popover>
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的递延收益是存在的，且已记录在恰当的账户中；</li>
        <li><b>义务：</b>记录的递延收益是被审计单位应当履行的偿还义务（附条件政府补助）；</li>
        <li><b>计价和分摊：</b>递延收益以恰当的金额包括在财务报表中，分摊方法符合 CAS16 政府补助准则。</li>
      </ol>
    </el-alert>

    <!-- 方法论 -->
    <div class="methodology-context">
      <p>递延收益（2401）为<strong>贷方/负债类</strong>科目。检查政府补助相关原始凭证（银行回单/补助文件/验收报告），确定业务真实性、入账金额及会计处理正确。检查重点：①是否与日常活动相关 ②款项是否实际收到 ③分类正确（与资产/与收益） ④是否满足确认条件 ⑤分摊方法是否适当。</p>
    </div>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（贷方发生额）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额政府补助、验收条件项目全部测试" @change="persist" />
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
          <label>测试原因</label>
          <el-checkbox-group v-model="testReasons" :disabled="isReadonly" size="small" @change="persist">
            <el-checkbox label="大额" /><el-checkbox label="关联方" /><el-checkbox label="大额交易频繁" /><el-checkbox label="异常" /><el-checkbox label="其他" />
          </el-checkbox-group>
        </div>
      </div>
    </el-card>

    <!-- 三、测试 — 政府补助凭证检查 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 政府补助凭证检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="460" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column v-if="isColVisible('debtorName')" label="政府补助项目" min-width="140">
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
        <el-table-column v-if="isColVisible('offsetSubAccount')" label="对方明细科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" /><span v-else>{{ row.offsetSubAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('debitAmount')" label="借方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('creditAmount')" label="贷方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
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
        <el-table-column v-if="isColVisible('abnormal')" label="是否异常" width="80" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('indexNo')" label="索引号" width="90">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" /><span v-else>{{ row.indexNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('remark')" label="备注说明" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计　贷方：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例：仅贷方）-->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="k7CheckRatios" border size="small" class="ratio-table">
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
      <el-alert v-if="lowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%），应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、结果等" @change="persist" />
      </div>
    </el-card>

    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填项目）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS16 政府补助）</summary>
      <ul>
        <li>递延收益 = 与资产相关的政府补助 + 补偿以后期间费用的与收益相关的政府补助</li>
        <li>核对内容：①原始凭证齐全(银行回单/批文) ②记账凭证与原始凭证相符 ③会计处理正确(CAS16总额法/净额法) ④记录于恰当会计期间 ⑤分类正确(与资产/与收益)</li>
        <li>检查比例 = 贷方检查金额 / 本期贷方发生额（仅贷方，源模板设计）</li>
        <li>抽凭引擎复用序时账，科目 2401 递延收益（贷方/负债类）</li>
      </ul>
    </details>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 递延收益(2401)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2401" phase="final" :workpaper-id="props.wpId" :project-id="props.projectId" :year="year" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabDeferredCheck.vue — K7-5 递延收益检查表（凭证级测试 + 列设置）
 * 科目 2401 递延收益（贷方/负债类）。源模板检查比例仅贷方。
 * 宽表功能：列设置 popover（隐藏/显示列，localStorage 持久化）。
 */
import { ref, reactive, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()
const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const year = computed(() => props.year ?? new Date().getFullYear())
const allResponsesRef = computed(() => props.allResponses)

const {
  itemId, checkLabels,
  criteria, occurrenceRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceCreditChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: 'K7-5-voucher-check' })

// K7-5 检查比例仅贷方（源模板设计）
const k7CheckRatios = computed(() => checkRatios.value.filter(r => r.direction === '本期贷方'))

// 测试原因 checkbox（源模板特色）
const testReasons = ref<string[]>([])

onMounted(() => load())

// ─── 列设置（宽表功能）─────────────────────────────────────────────────────────
const COLUMN_PREFS_KEY = 'k7-5-column-prefs'
interface ColDef { key: string; label: string; visible: boolean }
const columnDefs = reactive<ColDef[]>([
  { key: 'debtorName', label: '政府补助项目', visible: true },
  { key: 'date', label: '日期', visible: true },
  { key: 'voucherNo', label: '凭证编号', visible: true },
  { key: 'businessContent', label: '业务内容', visible: true },
  { key: 'offsetAccount', label: '对方科目', visible: true },
  { key: 'offsetSubAccount', label: '对方明细科目', visible: false },
  { key: 'debitAmount', label: '借方金额', visible: true },
  { key: 'creditAmount', label: '贷方金额', visible: true },
  { key: 'checks', label: '核对内容', visible: true },
  { key: 'abnormal', label: '是否异常', visible: true },
  { key: 'indexNo', label: '索引号', visible: true },
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
  for (const col of columnDefs) col.visible = col.key !== 'offsetSubAccount'
  persistColumnPrefs()
}
loadColumnPrefs()

// ─── Handlers ────────────────────────────────────────────────────────────────
function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

const samplingVisible = ref(false)
function openSampling() { samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) {
  fillFromSamples('occurrence', payload?.samples ?? [])
  samplingVisible.value = false
  persist()
}

function persist() {
  const data = serialize()
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: data })
  emit('save', itemId, { remark: data })
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
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function abnormalRowClass({ row }: { row: K1VoucherRow }): string { return row.abnormal ? 'abnormal-row' : '' }
function handleAiGenerate() { emit('save', 'K7-5-ai-trigger', { remark: 'deferred-voucher-check' }) }
function handleReview() { openReviewDialog('K7-5-check') }
</script>

<style scoped>
.k7-tab-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
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
</style>
