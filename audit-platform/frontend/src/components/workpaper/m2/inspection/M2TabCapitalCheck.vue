<!--
  M2TabCapitalCheck.vue — M2-5 实收资本（股本）检查表（凭证级测试）

  忠实反映致同源模板 M2-5（27×18 凭证级检查表）：
    一、测试目标（存在/权利义务/计价分摊 三认定）
    二、测试（凭证级明细：日期/凭证编号/业务内容/对方科目/对方明细科目/借方/贷方
         + 支持性文件 + 核对内容1-5 + 索引号/是否异常/备注）
    三、审计说明（检查比例：本期增加金额/检查金额/比例）
    四、审计结论

  复用 useK1VoucherCheck（通用凭证检查状态）。科目 4001 实收资本。
  M2无期后段——实收资本变动是离散事件（增资/减资），非日常收付。
  仅展示 occurrenceRows + checkRatios 中本期贷方行（增资额）。
-->
<template>
  <div class="m2-tab-capital-check">
    <!-- ═══ 引导区 ═══ -->
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认测试目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <!-- ═══ 标题行 ═══ -->
    <div class="section-head">
      <h3 class="sheet-title">M2-5 实收资本（股本）检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link :loading="aiLoading === 'note'" :disabled="isReadonly" @click="handleAiGenerate('note')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 一、测试目标 ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、测试目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的实收资本是存在的，且已经记录在恰当的账户中；</li>
        <li><b>权利和义务：</b>记录的实收资本由被审计单位拥有或控制；</li>
        <li><b>准确性、计价和分摊：</b>实收资本以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>检查要点：</strong>
        审阅公司章程、股东（大）会/董事会会议记录中相关规定。收集与所有者权益账户变动有关的股东（大）会决议、董事会会议纪要、合同、协议、公司章程及营业执照、公司设立批文、验资报告以及政府主管部门/财政部门批复、资产评估报告等文件资料，并更新永久性档案。
        核对内容：1.原始凭证是否齐全；2.记账凭证与原始凭证是否相符；3.账务处理是否正确；4.是否记录于恰当的会计期间；5.其他。
      </div>
    </div>

    <!-- ═══ 二、样本选取标准与规模 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、样本选取标准与规模</span></template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（借方/减资）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly" size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly" size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（贷方/增资）</label>
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
            placeholder="大额增减资、非货币资产出资、关联方之间的股权转让等全部测试" @change="persist" />
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
        <div class="cg-item">
          <label>本期增加金额（检查比例基准）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.endBalance" :controls="false" :disabled="isReadonly" size="small" placeholder="本期增加金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" size="small"
            placeholder="本期实收资本增减变动笔数较少，全部纳入检查；或使用XX抽样工具选择XX数量的样本进行测试" @change="persist" />
        </div>
      </div>
    </el-card>

    <!-- ═══ 三、测试 — 凭证检查表 ═══ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 本期实收资本增减变动检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling"><el-icon><MagicStick /></el-icon> 抽凭</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <el-table :data="occurrenceRows" border size="small" :max-height="420" class="voucher-table" :row-class-name="abnormalRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="日期" width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" /><span v-else>{{ row.date || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" /><span v-else>{{ row.voucherNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="160">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.businessContent" size="small" placeholder="增资/减资/非货币出资..." @change="persist" /><span v-else>{{ row.businessContent || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="110">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" /><span v-else>{{ row.offsetAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="对方明细科目" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" /><span v-else>{{ row.offsetSubAccount || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="贷方金额" min-width="110" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small" class="amount-input" @change="persist" /><span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="核对内容" width="180" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content><div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div></template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group" @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(_, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" /><span v-else>{{ row.indexNo || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="是否异常" width="80" align="center">
          <template #default="{ row }"><el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" /></template>
        </el-table-column>
        <el-table-column label="备注说明" min-width="120">
          <template #default="{ row }"><el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" /><span v-else>{{ row.remark || '-' }}</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center" fixed="right">
          <template #default="{ row }"><el-button size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删除</el-button></template>
        </el-table-column>
        <template #append><div class="table-total">合计　借方(减资)：{{ fmtAmt(occurrenceDebitChecked) }}　贷方(增资)：{{ fmtAmt(occurrenceCreditChecked) }}</div></template>
      </el-table>
    </el-card>

    <!-- ═══ 四、审计说明（检查比例）═══ -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">四、审计说明 — 检查比例</span></template>
      <el-table :data="m2CheckRatios" border size="small" class="ratio-table">
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
        <template #title>检查比例偏低（&lt;30%）：{{ lowRatioWarnings.map(r => r.direction).join('、') }}，应扩大检查样本量或说明原因</template>
      </el-alert>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly" placeholder="概述测试情况、结果；拟调整事项及分录、未调整事项及其影响等" @change="persist" />
      </div>
    </el-card>

    <!-- ═══ 异常凭证摘要 ═══ -->
    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）</div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id"><b>{{ r.debtorName || '（未填出资人）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}</li>
      </ul>
    </div>

    <!-- ═══ 五、审计结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">五、审计结论</span>
          <el-button size="small" :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="handleAiGenerate('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select" placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>测试目标对应三项认定：存在、权利和义务、准确性/计价和分摊</li>
        <li>样本选取：实收资本本期增减变动笔数通常较少，如≤10笔可全部检查</li>
        <li>核对内容五项：①原始凭证是否齐全 ②记账凭证与原始凭证是否相符 ③账务处理是否正确 ④是否记录于恰当的会计期间 ⑤其他</li>
        <li>支持性文件包括：验资报告、股东（大）会决议、董事会决议、公司章程、营业执照变更、评估报告（非货币出资）</li>
        <li>检查比例 = 检查金额(贷方合计) / 本期增加金额；实收资本变动少通常应100%检查</li>
        <li>抽凭引擎科目 4001 实收资本/股本（贷方/权益类）</li>
        <li>关注：非货币资产出资是否经评估确认价值、出资期限是否逾期、外币出资汇率折算（见M2-4）</li>
      </ul>
    </details>

    <!-- ═══ 抽凭引擎 ═══ -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 实收资本/股本(4001)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible"
        account-code="4001"
        phase="current"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="year"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabCapitalCheck.vue — M2-5 实收资本（股本）检查表（凭证级测试）
 *
 * 对齐源模板 M2-5（27×18）：凭证级检查表（非验资核对表）
 * 科目 4001 实收资本/股本（贷方/权益类）
 * 仅本期发生额检查（无期后段——实收资本变动是离散事件）
 * 检查比例 = 贷方检查金额 / 本期增加金额
 *
 * 复用 useK1VoucherCheck composable，itemId = M2-5-voucher-check
 */
import { ref, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useK1VoucherCheck, type K1VoucherRow, type K1CheckRatioRow } from '../../composables/useK1VoucherCheck'
import { useM2FormData } from '../../composables/useM2FormData'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  year?: number
}>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

const year = computed(() => props.year ?? new Date().getFullYear())

// ─── FormData（自包含加载） ──────────────────────────────────────────────────

const formData = useM2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const allResponsesRef = computed(() => formData.allResponses.value)

// ─── 复用 useK1VoucherCheck（M2-5-voucher-check） ────────────────────────────

const {
  itemId, checkLabels,
  criteria, occurrenceRows, auditNote, conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked,
  load, addOccurrenceRow, removeOccurrenceRow,
  fillFromSamples, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any, itemId: 'M2-5-voucher-check' })

// ─── M2特殊：检查比例仅展示"本期贷方（增资额）"一行 ─────────────────────────────

const m2CheckRatios = computed<K1CheckRatioRow[]>(() => {
  // M2源模板：检查比例 = 检查金额(贷方合计) / 本期增加金额
  // 也展示借方(减资)供参考
  const mk = (direction: string, book: number, checked: number): K1CheckRatioRow => ({
    direction, bookAmount: book, checkedAmount: checked,
    ratio: book > 0 ? checked / book : null,
  })
  return [
    mk('本期贷方（增资）', criteria.value.populationCreditAmount, occurrenceCreditChecked.value),
    mk('本期借方（减资）', criteria.value.populationDebitAmount, occurrenceDebitChecked.value),
  ]
})

// ─── Load ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  load()
})

// ─── 核对内容勾选 ────────────────────────────────────────────────────────────

function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

// ─── 抽凭引擎 ───────────────────────────────────────────────────────────────

const samplingVisible = ref(false)

function openSampling() { samplingVisible.value = true }
function onSamplesFilled(payload: { samples: any[] }) {
  fillFromSamples('occurrence', payload?.samples ?? [])
  samplingVisible.value = false
  persist()
}

// ─── 持久化 ──────────────────────────────────────────────────────────────────

function persist() {
  const data = serialize()
  formData.allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: data })
  formData.debouncedSave(itemId, { remark: data })
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

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function abnormalRowClass({ row }: { row: K1VoucherRow }): string { return row.abnormal ? 'abnormal-row' : '' }

// ─── AI + 复核 ───────────────────────────────────────────────────────────────

async function handleAiGenerate(target: 'note' | 'conclusion' = 'conclusion') {
  if (props.isReadonly) return
  aiLoading.value = target
  try {
    const context: Record<string, string> = {
      科目: '4001 实收资本/股本（凭证级检查表）',
      本期增加金额: fmtAmt(criteria.value.endBalance),
      贷方增资检查金额: fmtAmt(occurrenceCreditChecked.value),
      借方减资检查金额: fmtAmt(occurrenceDebitChecked.value),
      检查凭证笔数: String(occurrenceRows.value.length),
      异常凭证笔数: String(abnormalRows.value.length),
    }
    const existing = target === 'note' ? auditNote.value : conclusion.value
    const text = await generateAiText({ section: `m2-5-voucher-check-${target}`, context, existingContent: existing })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (target === 'note') auditNote.value = text; else conclusion.value = text
    persist()
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = ''
  }
}
function handleReview() { openReviewDialog?.('M2-5-voucher-check') }
</script>

<style scoped>
.m2-tab-capital-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }

.guide-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 14px 16px; margin-bottom: 16px; background: linear-gradient(135deg, #e8f4fd 0%, #f0f9ff 100%); border-radius: 8px; border: 1px solid #d9ecff; }
.guide-step { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #303133; }
.gs-no { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: #409eff; color: #fff; font-size: 11px; font-weight: 700; flex-shrink: 0; }

.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 700; color: #303133; }
.head-actions { display: flex; align-items: center; gap: 8px; }

.audit-objective { margin-bottom: 14px; }
:deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; font-size: 13px; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 10px 14px; border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #78350f; line-height: 1.6; }

.section-card { margin-bottom: 14px; }
.section-card :deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
.card-title { font-size: 13px; font-weight: 600; color: #303133; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }

.criteria-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.cg-item label { display: block; margin-bottom: 4px; font-size: 12px; color: #606266; font-weight: 500; }
.cg-full { grid-column: span 2; }
.cg-inline { display: flex; align-items: center; gap: 6px; }
.cg-unit { font-size: 12px; color: #909399; }
.num-sm { width: 90px; }
.num-md { width: 140px; }

.voucher-table { font-size: var(--wp-font-size, 13px); }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.amount-input { width: 100%; }
.amount-cell { font-variant-numeric: tabular-nums; }
.col-help { border-bottom: 1px dashed #909399; cursor: help; font-size: 12px; }
.check-group { display: flex; gap: 2px; }
:deep(.abnormal-row) { background: #fef0f0 !important; }
.table-total { padding: 8px 12px; font-size: 12px; font-weight: 600; color: #303133; background: #f5f7fa; }

.ratio-table { margin-bottom: 12px; }
.ratio-warn { margin-top: 8px; margin-bottom: 12px; }
.muted { color: #c0c4cc; }

.note-block { margin-top: 12px; }
.note-block label { display: block; margin-bottom: 4px; font-size: 12px; color: #606266; font-weight: 500; }

.abnormal-summary { margin-bottom: 14px; padding: 10px 14px; background: #fef0f0; border: 1px solid #fbc4c4; border-radius: 6px; }
.as-header { font-size: 13px; font-weight: 600; color: #f56c6c; margin-bottom: 6px; }
.as-list { padding-left: 18px; font-size: 12px; line-height: 1.6; color: #303133; margin: 0; }

.conclusion-card { margin-bottom: 14px; }
.concl-select { margin-bottom: 8px; width: 100%; }

.compile-hint { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 12px; color: #606266; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; font-size: 13px; }
.compile-hint ul { padding-left: 18px; margin: 8px 0 0; line-height: 1.8; }
</style>
