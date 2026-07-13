<!--
  J1TabGeneralCheck.vue — J1-8 应付职工薪酬检查表（凭证级测试）

  致同源模板 J1-8（三区凭证检查）：
    一、测试目标（存在/完整性/权利义务 三认定）
    二、样本选取标准与规模（抽测原因 checkbox）
    三、测试（1.贷方检查(计提/增加) 2.借方检查(发放/减少) 3.期后支付检查）
    四、审计说明（检查比例：本期贷方/本期借方）
    五、审计结论

  复用 useK1VoucherCheck。科目 2211 应付职工薪酬（贷方/负债类）。
-->
<template>
  <div class="j1-tab-general">
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认测试目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行贷方/借方/期后测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">J1-8 应付职工薪酬检查表</h3>
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

    <!-- 一、测试目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、测试目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的应付职工薪酬是存在的，且已记录在恰当的账户中；</li>
        <li><b>完整性：</b>所有应记录的应付职工薪酬均已记录（负债完整性认定为主）；</li>
        <li><b>义务：</b>记录的应付职工薪酬是被审计单位应当履行的偿还义务。</li>
      </ol>
    </el-alert>

    <!-- 方法论 -->
    <div class="methodology-context">
      <p>应付职工薪酬（2211）为<strong>贷方/负债类</strong>科目。贷方检查对应计提/增加（核对职工薪酬计算表），借方检查对应发放/减少（核对付款审批单/银行回单）。期后支付检查验证期末应计未付薪酬的完整性。关注：①原始凭证齐全 ②记账凭证与原始凭证相符 ③账务处理正确 ④记录于恰当会计期间 ⑤是否经过恰当审批。</p>
    </div>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（贷方/计提）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（借方/发放）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额计提/发放、异常薪酬支出全部测试" @change="persist" />
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
          <label>抽测原因</label>
          <el-checkbox-group v-model="testReasons" :disabled="isReadonly" size="small" @change="persist">
            <el-checkbox label="大额" /><el-checkbox label="关联方" /><el-checkbox label="大额交易频繁" /><el-checkbox label="异常" /><el-checkbox label="其他" />
          </el-checkbox-group>
        </div>
      </div>
    </el-card>

    <!-- 三、测试 1. 贷方检查（计提/增加） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 1. 贷方检查（计提/增加）</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('occurrence')"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="320" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column v-if="isColVisible('debtorName')" label="项目" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('date')" label="日期" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('voucherNo')" label="凭证编号" width="100">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('businessContent')" label="业务内容" min-width="130">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('offsetAccount')" label="对方科目" min-width="100">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('creditAmount')" label="贷方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column v-if="isColVisible('checks')" label="核对" width="160" align="center">
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(_, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('abnormal')" label="异常" width="70" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">贷方合计：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 三、测试 2. 借方检查（发放/减少） + 3. 期后支付 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 2. 借方检查（发放）+ 3. 期后支付</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('post')"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addPostCollectionRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="postCollectionRows" border size="small" :max-height="280" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="项目" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" /><span v-else>{{ row.debtorName || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="日期" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="130">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="异常" width="70" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removePostCollectionRow(row.id); persist()">删</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">借方/期后合计：{{ fmtAmt(postCollectionChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例）-->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="checkRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="120" />
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
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
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
      <summary>编制提示（CAS 9 职工薪酬）</summary>
      <ul>
        <li>贷方检查：核对职工薪酬计算表（人数×基数×比例），确认审批流程</li>
        <li>借方检查：核对付款审批单+银行回单，确认发放金额与计提一致</li>
        <li>期后支付：关注期后支付摘要是否提及上期、金额是否超过计提</li>
        <li>检查比例 = 检查金额 / 账面金额；偏低须扩样或说明</li>
        <li>抽凭引擎科目 2211 应付职工薪酬（贷方/负债类）</li>
      </ul>
    </details>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 应付职工薪酬(2211)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine v-if="samplingVisible" account-code="2211" :phase="samplingTarget === 'occurrence' ? 'current' : 'post'" :workpaper-id="props.wpId" :project-id="props.projectId" :year="year" @filled="onSamplesFilled" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1VoucherCheck, type K1VoucherRow } from '../../composables/useK1VoucherCheck'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()
const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const isReadonly = computed(() => false) // J1 子组件自管 readonly
const year = computed(() => new Date().getFullYear())
const allResponsesRef = ref<Map<string, any>>(new Map())

// 从 htmlData 加载已有数据
onMounted(() => {
  if (props.htmlData) {
    const snap = (props.htmlData as any).responses_snapshot || (props.htmlData as any).allResponses || {}
    if (typeof snap === 'object') {
      for (const [k, v] of Object.entries(snap)) allResponsesRef.value.set(k, v)
    }
  }
  load()
})

const {
  itemId, checkLabels,
  criteria, occurrenceRows, postCollectionRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceCreditChecked, postCollectionChecked,
  load, addOccurrenceRow, addPostCollectionRow, removeOccurrenceRow, removePostCollectionRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef, itemId: 'J1-8-voucher-check' })

const testReasons = ref<string[]>([])

// ─── 列设置 ──────────────────────────────────────────────────────────────────
const COLUMN_PREFS_KEY = 'j1-8-column-prefs'
interface ColDef { key: string; label: string; visible: boolean }
const columnDefs = reactive<ColDef[]>([
  { key: 'debtorName', label: '项目', visible: true },
  { key: 'date', label: '日期', visible: true },
  { key: 'voucherNo', label: '凭证编号', visible: true },
  { key: 'businessContent', label: '业务内容', visible: true },
  { key: 'offsetAccount', label: '对方科目', visible: true },
  { key: 'creditAmount', label: '贷方金额', visible: true },
  { key: 'checks', label: '核对内容', visible: true },
  { key: 'abnormal', label: '是否异常', visible: true },
])
function isColVisible(key: string): boolean { return columnDefs.find(c => c.key === key)?.visible ?? true }
function persistColumnPrefs(): void { try { localStorage.setItem(COLUMN_PREFS_KEY, JSON.stringify(columnDefs.map(c => ({ key: c.key, visible: c.visible })))) } catch { /* */ } }
function resetColumnPrefs(): void { for (const col of columnDefs) col.visible = true; persistColumnPrefs() }
;(function loadColumnPrefs() { try { const saved = localStorage.getItem(COLUMN_PREFS_KEY); if (!saved) return; const prefs: Array<{ key: string; visible: boolean }> = JSON.parse(saved); for (const p of prefs) { const col = columnDefs.find(c => c.key === p.key); if (col) col.visible = p.visible } } catch { /* */ } })()

// ─── Handlers ────────────────────────────────────────────────────────────────
function checkedValues(row: K1VoucherRow): number[] { return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0) }
function setChecks(row: K1VoucherRow, vals: number[]): void { row.checks = checkLabels.map((_, i) => vals.includes(i)); persist() }

const samplingVisible = ref(false)
const samplingTarget = ref<'occurrence' | 'post'>('occurrence')
function openSampling(target: 'occurrence' | 'post') { samplingTarget.value = target; samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) { fillFromSamples(samplingTarget.value, payload?.samples ?? []); samplingVisible.value = false; persist() }

function persist() {
  const data = serialize()
  allResponsesRef.value.set(itemId, { item_id: itemId, conclusion: null, remark: data })
  // J1 子组件自行 persist — 通过 useJ1FormData 的 saveResponses
  // 这里直接调用 formData 的 setResponse + saveResponses
  emit('save', itemId, { remark: data })
}
function onConclusionOption(val: string) {
  const map: Record<string, string> = { A: '未见异常。', B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。', C: '由于存在重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。' }
  if (map[val] && !conclusion.value) conclusion.value = map[val]
  persist()
}
function fmtAmt(val: number | null | undefined): string { if (val == null) return '-'; return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function abnormalRowClass({ row }: { row: K1VoucherRow }): string { return row.abnormal ? 'abnormal-row' : '' }
function handleAiGenerate() { emit('save', 'J1-8-ai-trigger', { remark: 'general-check' }) }
function handleReview() { openReviewDialog('J1-8-check') }
</script>

<style scoped>
.j1-tab-general { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
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
