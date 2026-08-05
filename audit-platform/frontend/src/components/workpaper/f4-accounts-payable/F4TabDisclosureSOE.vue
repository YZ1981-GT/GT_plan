<script setup lang="ts">
/**
 * F4TabDisclosureSOE — 附注披露信息（国企）
 * 对齐源表：按账龄披露期末/期初余额（全联动F4-1按账龄审定数）+
 * 账龄超过1年的重要应付账款（联动F4-5长期挂账检查表）。
 * 披露文字通过 disclosure:note-text-updated(type='soe') 联动国企附注模块。
 */
import { computed, inject, onBeforeUnmount, toRef, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF4DisclosureSOE } from '../composables/useF4DisclosureSOE'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import { F4_GROSS_FALLBACK_STANDARD } from '../composables/f4AccountScope'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import GtIndexChip from '../GtIndexChip.vue'
import WpAmountInput from '../shared/WpAmountInput.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  agingRows,
  agingClosingTotal,
  agingOpeningTotal,
  natureTotals,
  closingMatchesNature,
  openingMatchesNature,
  importantRows,
  importantTotal,
  overOneYearAgingTotal,
  pendingSyncCount,
  syncFromLongOutstanding,
  addImportantRow,
  removeImportantRow,
  updateImportantCell,
  disclosureText,
  isSyncing,
  syncToNotes,
  noteSection,
} = useF4DisclosureSOE({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

// 保存后自动同步到附注（防抖 / 非阻塞 / 失败静默 / 只读 gate；与手动按钮同源 syncToNotes）。
// 触发源为披露表实际数据（账龄行 / 重要应付账款行 / 披露正文），详见上市 Tab 同位注释。
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

watch(
  [agingRows, importantRows, disclosureText],
  () => { autoSync.scheduleAutoSync(syncToNotes) },
  { deep: true },
)

// 账龄区间跟随项目账龄配置；"其他/未分类"（残差行）仅在有余额时展示（合计不受影响）
const visibleAgingRows = computed(() =>
  agingRows.value.filter((row) =>
    row.rowKey !== 'aging-other'
    || Math.abs(row.closingBalance) >= 0.005
    || Math.abs(row.openingBalance) >= 0.005,
  ),
)

const totalsConsistent = computed(() =>
  closingMatchesNature.value && openingMatchesNature.value,
)

// 重要应付账款合计与按账龄区1年以上合计核对（前者不应超过后者）
const importantExceedsAging = computed(() =>
  importantTotal.value - overOneYearAgingTotal.value > 0.005,
)

function amount(value: number): string {
  if (Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function handleSync(): void {
  const added = syncFromLongOutstanding()
  if (added > 0) ElMessage.success(`已从F4-5同步 ${added} 条账龄超过1年的应付账款`)
  else ElMessage.info('F4-5中账龄超过1年的项目均已同步')
}

function aiContext() {
  return {
    agingRows: agingRows.value.map((row) => ({
      aging: row.label,
      closingBalance: row.closingBalance,
      openingBalance: row.openingBalance,
    })),
    totals: {
      closing: agingClosingTotal.value,
      opening: agingOpeningTotal.value,
      matchesNatureClassification: totalsConsistent.value,
    },
    overOneYearImportantRows: importantRows.value.map((row) => ({
      creditor: row.creditor,
      amount: row.amount,
      reason: row.reason,
      linkedToF45: row.linked,
    })),
    overOneYearImportantTotal: importantTotal.value,
    overOneYearAgingTotal: overOneYearAgingTotal.value,
  }
}

async function generateDisclosure(): Promise<void> {
  const generated = await generateAndConfirm(
    'disclosure-soe',
    disclosureText.value,
    aiContext(),
    'AI 生成 · 附注披露内容（国企）',
  )
  if (generated) disclosureText.value = generated
}

function onAdjudicated(event: Event): void {
  const detail = (event as CustomEvent).detail
  if (detail?.accountCode === F4_GROSS_FALLBACK_STANDARD) {
    ElMessage.info('F4-1审定数据已更新，披露表账龄金额已自动联动，请复核')
  }
}
window.addEventListener('substantive:adjudicated', onAdjudicated)
onBeforeUnmount(() => window.removeEventListener('substantive:adjudicated', onAdjudicated))
</script>

<template>
  <div class="f4-tab-disclosure-soe">
    <details class="guidance-details">
      <summary>📋 编制思路与联动逻辑</summary>
      <div class="guidance-content">
        <p>1. 按账龄披露：账龄档位跟随<strong>项目账龄配置</strong>（3年段／5年段／自定义），各档自动取自F4-1审定表按账龄分类（期末余额=期末审定数、期初余额=期初审定数），本表不可直接改数；“1年以上”合计按段起始天数≥366派生，不含“其他/未分类”残差行。</p>
        <p>2. 账龄超过1年的重要应付账款：点击"从F4-5同步"自动带入长期挂账检查表中挂账超过1年的债权单位、期末余额及未偿还原因，也可手工补行。</p>
        <p>3. 按账龄披露合计与F4-1按性质审定合计交叉核对，不一致时红色预警；重要应付账款合计不应超过1年以上账龄的披露合计。</p>
        <p>4. 披露文字保存后自动联动国企附注模块（应付账款2202）；点击<strong>「⇄ 同步到附注」</strong>把两张表的行数据整表推送到附注「{{ noteSection }} 应付账款」。</p>
        <p>5. <strong>账龄行名换算</strong>：底稿沿用源模板用词「1至2年（含2年）」，附注模版用词为「1至2年」；推送时自动按附注模版投影（鼠标悬停账龄可见附注行名），「其他/未分类」残差行不进附注但计入合计。</p>
      </div>
    </details>

    <div class="methodology-note">
      <p><strong>源模板提示：</strong>账龄超过1年的大额应付账款，应说明未偿还或未结转的原因，并在资产负债表日后事项中说明是否偿还；账龄超过3年以上的应付账款应说明未偿还的原因。</p>
      <p>存在供应商融资安排（反向保理／供应链融资平台）的，还应按《企业会计准则解释第17号》在附注「现金流量表补充资料—供应商融资安排」中披露，底稿见 F4-9 供应商融资检查表。</p>
    </div>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实应付账款(2202)在国有企业财务报表附注中按账龄列报完整、分类准确，账龄超过1年的重要应付账款已披露债权单位及未偿还原因。"
    />

    <el-alert v-if="!totalsConsistent" type="error" :closable="false" class="warning-alert">
      按账龄披露合计与F4-1按性质审定合计不一致：
      <span v-if="!closingMatchesNature">
        期末 {{ amount(agingClosingTotal) }} ≠ 按性质审定 {{ amount(natureTotals.closing) }}；
      </span>
      <span v-if="!openingMatchesNature">
        期初 {{ amount(agingOpeningTotal) }} ≠ 按性质期初审定 {{ amount(natureTotals.opening) }}。
      </span>
      请先在F4-1中核对两个分类口径。
    </el-alert>

    <el-alert v-if="importantExceedsAging" type="warning" :closable="false" class="warning-alert">
      重要应付账款合计 {{ amount(importantTotal) }} 超过按账龄披露的1年以上合计 {{ amount(overOneYearAgingTotal) }}，请核对手工行金额或F4-1账龄划分。
    </el-alert>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <span class="section-label">一、应付账款附注披露信息（按账龄）</span>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F4-1" :context-project-id="projectId" />
        <GtIndexChip :value="`Note:${noteSection}`" :context-project-id="projectId" />
        <el-button
          size="small"
          type="success"
          plain
          :disabled="isReadonly"
          :loading="isSyncing"
          @click="syncToNotes"
        >⇄ 同步到附注</el-button>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-soe')">复核</el-button>
      </div>
    </div>

    <el-table :data="visibleAgingRows" border size="small" class="disclosure-table">
      <el-table-column label="账龄" min-width="180">
        <template #default="{ row }">
          <el-tooltip
            v-if="row.noteLabel && row.noteLabel !== row.label"
            :content="`附注列示行名：${row.noteLabel}（附注模版用词）`"
          >
            <span class="linked-label note-label-hint">🔗 {{ row.label }}</span>
          </el-tooltip>
          <span v-else class="linked-label">🔗 {{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="170" align="right">
        <template #default="{ row }">
          <el-tooltip content="联动F4-1按账龄期末审定数，请在审定表或明细表中修改">
            <span class="linked-amount">{{ amount(row.closingBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="170" align="right">
        <template #default="{ row }">
          <el-tooltip content="联动F4-1按账龄期初审定数">
            <span class="linked-amount">{{ amount(row.openingBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>
    <div class="total-strip">
      <span>合计</span>
      <span class="num" :class="{ danger: !closingMatchesNature }">{{ amount(agingClosingTotal) }}</span>
      <span class="num" :class="{ danger: !openingMatchesNature }">{{ amount(agingOpeningTotal) }}</span>
    </div>

    <div class="section-toolbar second-section">
      <div class="toolbar-left">
        <span class="section-label">二、账龄超过1年的重要应付账款</span>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSync">
          ⇄ 从F4-5同步
          <el-badge v-if="pendingSyncCount" :value="pendingSyncCount" class="sync-badge" />
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="addImportantRow">+ 手工添加</el-button>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F4-5" :context-project-id="projectId" />
      </div>
    </div>

    <el-table :data="importantRows" border size="small" class="disclosure-table">
      <el-table-column label="债权单位名称" min-width="180">
        <template #default="{ row }">
          <span v-if="row.linked" class="linked-label">🔗 {{ row.creditor }}</span>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.creditor"
            size="small"
            placeholder="债权单位名称"
            @change="(value: string) => updateImportantCell(row.rowId, 'creditor', value)"
          />
          <span v-else>{{ row.creditor }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="160" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.linked" content="联动F4-5挂账金额，请在长期挂账检查表中修改">
            <span class="linked-amount">{{ amount(row.amount) }}</span>
          </el-tooltip>
          <WpAmountInput
            v-else-if="!isReadonly"
            :model-value="row.amount"
            :disabled="isReadonly"
            @update:model-value="(value: number) => updateImportantCell(row.rowId, 'amount', value)"
          />
          <span v-else>{{ amount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未偿还原因" min-width="240">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reason"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            :placeholder="row.linked ? '默认取F4-5挂账原因，可修改补充' : '填写未偿还原因'"
            @change="(value: string) => updateImportantCell(row.rowId, 'reason', value)"
          />
          <span v-else>{{ row.reason }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button
            link
            type="danger"
            size="small"
            :disabled="isReadonly"
            @click="removeImportantRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="total-strip important-total">
      <span>合计</span>
      <span class="num" :class="{ danger: importantExceedsAging }">{{ amount(importantTotal) }}</span>
      <span class="spacer"></span>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">附注披露文字（联动国企附注模块）</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateDisclosure"
            >🤖 AI生成披露</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-soe')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="disclosureText"
        type="textarea"
        :autosize="{ minRows: 8, maxRows: 24 }"
        :disabled="isReadonly"
        placeholder="根据上方披露表编写国企附注披露文字（按账龄分类、账龄超过1年的重要应付账款及未偿还原因等），保存后自动同步至国企附注模块..."
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #315a8a;
  border-radius: 4px;
  background: #eef4fa;
}
.guidance-details summary { cursor: pointer; color: #315a8a; font-weight: 600; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.audit-objective, .warning-alert { margin-bottom: 10px; }
.methodology-note {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  background: #fdf6ec;
  color: #7d5a1a;
  line-height: 1.65;
}
.methodology-note p { margin: 3px 0; }
.note-label-hint { border-bottom: 1px dashed #b7bcc5; cursor: help; }
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 10px 0 8px; }
.second-section { margin-top: 20px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.section-label { font-weight: 600; font-size: 14px; color: #303133; }
.sync-badge { margin-left: 4px; }
.disclosure-table { width: 100%; }
.linked-label { font-weight: 600; color: #315a8a; }
.linked-amount { color: #7b4ba3; font-weight: 600; border-bottom: 1px dashed #b7bcc5; cursor: help; }
.total-strip {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 170px 170px;
  padding: 8px 12px;
  background: #f3f5f8;
  border: 1px solid #dcdfe6;
  border-top: none;
  font-weight: 700;
}
.total-strip.important-total { grid-template-columns: minmax(180px, 1fr) 160px minmax(240px, 1fr) 70px; }
.total-strip .num { text-align: right; }
.total-strip .danger { color: #d03050; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
