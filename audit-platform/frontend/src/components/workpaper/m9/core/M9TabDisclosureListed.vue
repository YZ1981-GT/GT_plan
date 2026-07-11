<template>
  <div class="m9-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
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
        <strong>上市公司附注披露要求（30×18）：</strong>
        按CAS30"其他综合收益"准则要求，分"以后不能重分类进损益"和"以后能重分类进损益"
        两大类分别列示税前金额、所得税影响和税后净额。数据自动从审定表/明细表拉取
        （subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 不能重分类进损益的OCI ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一、以后不能重分类进损益的其他综合收益</span>
          <el-button size="small" @click="handleAI('section-non-reclass')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="nonReclassRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="本期税前发生额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.preTaxAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateNonReclassRow($index, 'preTaxAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.preTaxAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所得税影响" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.taxEffect"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateNonReclassRow($index, 'taxEffect', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税后净额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.preTaxAmount - row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年同期" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorYearAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateNonReclassRow($index, 'priorYearAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorYearAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 能重分类进损益的OCI ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>二、以后将重分类进损益的其他综合收益</span>
          <el-button size="small" @click="handleAI('section-reclass')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="reclassRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="本期税前发生额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.preTaxAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateReclassRow($index, 'preTaxAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.preTaxAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所得税影响" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.taxEffect"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateReclassRow($index, 'taxEffect', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税后净额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.preTaxAmount - row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年同期" min-width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorYearAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateReclassRow($index, 'priorYearAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorYearAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 3: OCI合计 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>三、其他综合收益合计</span>
          <el-button size="small" @click="handleAI('section-total')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="不可重分类税后净额合计">{{ fmtAmount(nonReclassTotalNet) }}</el-descriptions-item>
        <el-descriptions-item label="可重分类税后净额合计">{{ fmtAmount(reclassTotalNet) }}</el-descriptions-item>
        <el-descriptions-item label="OCI税后净额合计">{{ fmtAmount(totalNet) }}</el-descriptions-item>
        <el-descriptions-item label="上年同期合计">{{ fmtAmount(totalPriorYear) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- ═══ Section 4: 其他综合收益补充说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>四、其他综合收益相关说明</span>
          <el-button size="small" @click="handleAI('section-remark')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="ociRemarkNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明各项其他综合收益的具体组成、变动原因及对所有者权益的影响..."
        @change="handleOciRemarkChange"
      />
    </el-card>

    <!-- ═══ Section 5: 转出至留存收益说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>五、OCI转出至留存收益说明</span>
          <el-button size="small" @click="handleAI('section-transfer')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="transferNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明本期从其他综合收益转入留存收益的项目及金额（如处置其他权益工具投资转回等）..."
        @change="handleTransferNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从M9-1审定表和M9-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司按CAS30分两大类披露：不可重分类+可重分类</li>
        <li>每项列示：税前发生额-所得税影响=税后净额</li>
        <li>格式：30行×18列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M9TabDisclosureListed — 附注披露信息（上市公司）30×18
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 4.5
 * Requirements: 5.2, 5.3, 5.4
 *
 * 功能：
 * - 上市公司附注模板（30×18）
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - 两大类OCI分别列示（不可重分类/可重分类）
 * - 税前-所得税=税后净额公式列
 * - AI辅助按钮 each section
 * - autosize textarea for 文本段
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM9FormData } from '../../composables/useM9FormData'
import { calcAfterTaxNet } from '../../composables/useM9OciEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM9FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State: 不可重分类OCI行 ─────────────────────────────────────────────────

interface DisclosureRow {
  item: string
  preTaxAmount: number
  taxEffect: number
  priorYearAmount: number
}

const nonReclassRows = ref<DisclosureRow[]>([
  { item: '1. 重新计量设定受益计划变动额（J2）', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '2. 权益法下不能转损益的其他综合收益', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '3. 其他权益工具投资公允价值变动（G8）', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '4. 企业自身信用风险公允价值变动', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '小计', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
])

// ─── State: 可重分类OCI行 ───────────────────────────────────────────────────

const reclassRows = ref<DisclosureRow[]>([
  { item: '1. 权益法下可转损益的其他综合收益', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '2. 其他债权投资公允价值变动', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '3. 金融资产重分类计入其他综合收益的金额', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '4. 其他债权投资信用减值准备', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '5. 现金流量套期储备', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '6. 外币财务报表折算差额', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
  { item: '小计', preTaxAmount: 0, taxEffect: 0, priorYearAmount: 0 },
])

// ─── State: 文本区 ──────────────────────────────────────────────────────────

const ociRemarkNote = ref('')
const transferNote = ref('')

// ─── Computed ────────────────────────────────────────────────────────────────

const nonReclassTotalNet = computed(() => {
  return nonReclassRows.value.reduce((sum, row) => sum + calcAfterTaxNet(row.preTaxAmount, row.taxEffect), 0)
})

const reclassTotalNet = computed(() => {
  return reclassRows.value.reduce((sum, row) => sum + calcAfterTaxNet(row.preTaxAmount, row.taxEffect), 0)
})

const totalNet = computed(() => nonReclassTotalNet.value + reclassTotalNet.value)

const totalPriorYear = computed(() => {
  const nonR = nonReclassRows.value.reduce((sum, row) => sum + row.priorYearAmount, 0)
  const r = reclassRows.value.reduce((sum, row) => sum + row.priorYearAmount, 0)
  return nonR + r
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateNonReclassRow(index: number, field: keyof DisclosureRow, val: number) {
  if (index >= 0 && index < nonReclassRows.value.length) {
    (nonReclassRows.value[index] as any)[field] = val
    formData.debouncedSave(`M9-disclosure-listed-nonReclass-${index}-${field}`, { remark: String(val) })
  }
}

function updateReclassRow(index: number, field: keyof DisclosureRow, val: number) {
  if (index >= 0 && index < reclassRows.value.length) {
    (reclassRows.value[index] as any)[field] = val
    formData.debouncedSave(`M9-disclosure-listed-reclass-${index}-${field}`, { remark: String(val) })
  }
}

function handleOciRemarkChange() {
  formData.debouncedSave('M9-disclosure-listed-remark', { remark: ociRemarkNote.value || null })
}

function handleTransferNoteChange() {
  formData.debouncedSave('M9-disclosure-listed-transfer', { remark: transferNote.value || null })
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.('M9-disclosure-listed', '附注披露（上市）') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData()
}

onMounted(async () => {
  await formData.loadData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m9-tab-disclosure-listed { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.el-table) { font-size: 13px; }
.formula-cell { color: #409eff; border-bottom: 1px dashed #409eff; cursor: help; }
.m9-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.m9-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m9-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
