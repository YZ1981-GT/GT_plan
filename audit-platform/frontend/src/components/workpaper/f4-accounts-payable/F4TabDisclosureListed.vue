<script setup lang="ts">
/**
 * F4TabDisclosureListed — 附注披露信息（上市公司）
 * 对齐源表：按性质披露（联动F4-1审定数、可无限量添加行）+
 * 账龄超过1年的重要应付账款（联动F4-5长期挂账检查表）。
 */
import { computed, inject, onBeforeUnmount, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useF4DisclosureListed,
  F4_LISTED_NATURE_OPTIONS,
} from '../composables/useF4DisclosureListed'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  natureRows,
  natureClosingTotal,
  naturePriorTotal,
  adjClosingTotal,
  adjPriorTotal,
  closingMatchesAdjudication,
  priorMatchesAdjudication,
  agingRows,
  agingTotal,
  pendingSyncCount,
  addNatureRow,
  removeNatureRow,
  updateNatureCell,
  addAgingRow,
  removeAgingRow,
  updateAgingCell,
  syncFromLongOutstanding,
  disclosureText,
  isSyncing,
  syncToNotes,
  noteSection,
} = useF4DisclosureListed({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

const totalsConsistent = computed(() =>
  closingMatchesAdjudication.value && priorMatchesAdjudication.value,
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
    natureRows: natureRows.value.map((row) => ({
      item: row.label,
      closingBalance: row.closingBalance,
      priorBalance: row.priorBalance,
      linkedToAdjudication: row.linked,
    })),
    totals: {
      closing: natureClosingTotal.value,
      prior: naturePriorTotal.value,
      matchesAdjudication: totalsConsistent.value,
    },
    overOneYearRows: agingRows.value.map((row) => ({
      creditor: row.creditor,
      amount: row.amount,
      reason: row.reason,
      linkedToF45: row.linked,
    })),
    overOneYearTotal: agingTotal.value,
  }
}

async function generateDisclosure(): Promise<void> {
  const generated = await generateAndConfirm(
    'disclosure-listed',
    disclosureText.value,
    aiContext(),
    'AI 生成 · 附注披露内容（上市公司）',
  )
  if (generated) disclosureText.value = generated
}

function onAdjudicated(event: Event): void {
  const detail = (event as CustomEvent).detail
  if (detail?.accountCode === '2202') {
    ElMessage.info('F4-1审定数据已更新，披露表金额已自动联动，请复核')
  }
}
window.addEventListener('substantive:adjudicated', onAdjudicated)
onBeforeUnmount(() => window.removeEventListener('substantive:adjudicated', onAdjudicated))
</script>

<template>
  <div class="f4-tab-disclosure-listed">
    <details class="guidance-details">
      <summary>📋 编制思路与联动逻辑</summary>
      <div class="guidance-content">
        <p>1. 按性质披露：货款、工程款等固定项目自动取自F4-1审定表（期末余额=期末审定数、上年年末余额=期初审定数），带🔗标记的行不可改金额。</p>
        <p>2. 可无限量添加行：新增的手工行可自行填写项目与金额，用于补充F4-1未涵盖的披露项目。</p>
        <p>3. 账龄超过1年的重要应付账款：点击"从F4-5同步"自动带入长期挂账检查表中挂账超过1年的债权人、金额及挂账原因，也可手工补行。</p>
        <p>4. 披露合计与F4-1审定合计不一致时红色预警，应先核对审定表或手工行。</p>
        <p>5. 两张表编制完成后点击右上角<strong>「⇄ 同步到附注」</strong>，把行数据与披露文字整表推送到附注「{{ noteSection }} 应付账款」（含「其中，账龄超过1年的重要应付账款」子表）。</p>
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
      title="审计目标：核实应付账款(2202)在上市公司财务报表附注中的列报完整、分类准确，账龄超过1年的重要应付账款已披露未偿还或未结转原因。"
    />

    <el-alert v-if="!totalsConsistent" type="error" :closable="false" class="warning-alert">
      披露合计与F4-1审定表不一致：
      <span v-if="!closingMatchesAdjudication">
        期末披露 {{ amount(natureClosingTotal) }} ≠ 审定 {{ amount(adjClosingTotal) }}；
      </span>
      <span v-if="!priorMatchesAdjudication">
        上年年末披露 {{ amount(naturePriorTotal) }} ≠ 期初审定 {{ amount(adjPriorTotal) }}。
      </span>
    </el-alert>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <span class="section-label">一、应付账款附注披露信息（按性质）</span>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addNatureRow">+ 添加行</el-button>
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
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-listed')">复核</el-button>
      </div>
    </div>

    <el-table :data="natureRows" border size="small" class="disclosure-table">
      <el-table-column label="项目" min-width="180">
        <template #default="{ row }">
          <span v-if="row.linked" class="linked-label">🔗 {{ row.label }}</span>
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.label"
            size="small"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入披露项目"
            style="width:100%"
            @change="(value: string) => updateNatureCell(row.rowId, 'label', value)"
          >
            <el-option v-for="opt in F4_LISTED_NATURE_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="170" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.linked" content="联动F4-1期末审定数，请在审定表或明细表中修改">
            <span class="linked-amount">{{ amount(row.closingBalance) }}</span>
          </el-tooltip>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.closingBalance"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(value: number | undefined) => updateNatureCell(row.rowId, 'closingBalance', value ?? 0)"
          />
          <span v-else>{{ amount(row.closingBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上年年末余额" width="170" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.linked" content="联动F4-1期初审定数">
            <span class="linked-amount">{{ amount(row.priorBalance) }}</span>
          </el-tooltip>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorBalance"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(value: number | undefined) => updateNatureCell(row.rowId, 'priorBalance', value ?? 0)"
          />
          <span v-else>{{ amount(row.priorBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button
            v-if="!row.linked"
            link
            type="danger"
            size="small"
            :disabled="isReadonly"
            @click="removeNatureRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="total-strip">
      <span>合计</span>
      <span class="num" :class="{ danger: !closingMatchesAdjudication }">{{ amount(natureClosingTotal) }}</span>
      <span class="num" :class="{ danger: !priorMatchesAdjudication }">{{ amount(naturePriorTotal) }}</span>
      <span class="spacer"></span>
    </div>

    <div class="section-toolbar second-section">
      <div class="toolbar-left">
        <span class="section-label">二、其中，账龄超过1年的重要应付账款</span>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSync">
          ⇄ 从F4-5同步
          <el-badge v-if="pendingSyncCount" :value="pendingSyncCount" class="sync-badge" />
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="addAgingRow">+ 手工添加</el-button>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F4-5" :context-project-id="projectId" />
      </div>
    </div>

    <el-table :data="agingRows" border size="small" class="disclosure-table">
      <el-table-column label="项目（债权人）" min-width="180">
        <template #default="{ row }">
          <span v-if="row.linked" class="linked-label">🔗 {{ row.creditor }}</span>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.creditor"
            size="small"
            placeholder="债权人名称"
            @change="(value: string) => updateAgingCell(row.rowId, 'creditor', value)"
          />
          <span v-else>{{ row.creditor }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="160" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.linked" content="联动F4-5挂账金额，请在长期挂账检查表中修改">
            <span class="linked-amount">{{ amount(row.amount) }}</span>
          </el-tooltip>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.amount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(value: number | undefined) => updateAgingCell(row.rowId, 'amount', value ?? 0)"
          />
          <span v-else>{{ amount(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="未偿还或未结转的原因" min-width="240">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reason"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            :placeholder="row.linked ? '默认取F4-5挂账原因，可修改补充' : '填写未偿还或未结转的原因'"
            @change="(value: string) => updateAgingCell(row.rowId, 'reason', value)"
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
            @click="removeAgingRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="total-strip aging-total">
      <span>合计</span>
      <span class="num">{{ amount(agingTotal) }}</span>
      <span class="spacer"></span>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">附注披露文字</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateDisclosure"
            >🤖 AI生成披露</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-disclosure-listed')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="disclosureText"
        type="textarea"
        :autosize="{ minRows: 8, maxRows: 24 }"
        :disabled="isReadonly"
        placeholder="根据上方披露表编写上市公司附注披露文字（按性质分类、账龄超过1年的重要应付账款及原因等）..."
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 10px 0 8px; }
.second-section { margin-top: 20px; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.section-label { font-weight: 600; font-size: 14px; color: #303133; }
.sync-badge { margin-left: 4px; }
.disclosure-table { width: 100%; }
.disclosure-table :deep(.el-input-number) { width: 100%; }
.linked-label { font-weight: 600; color: #315a8a; }
.linked-amount { color: #7b4ba3; font-weight: 600; border-bottom: 1px dashed #b7bcc5; cursor: help; }
.total-strip {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 170px 170px 70px;
  padding: 8px 12px;
  background: #f3f5f8;
  border: 1px solid #dcdfe6;
  border-top: none;
  font-weight: 700;
}
.total-strip.aging-total { grid-template-columns: minmax(180px, 1fr) 160px minmax(240px, 1fr) 70px; }
.total-strip .num { text-align: right; }
.total-strip .danger { color: #d03050; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; }
</style>
