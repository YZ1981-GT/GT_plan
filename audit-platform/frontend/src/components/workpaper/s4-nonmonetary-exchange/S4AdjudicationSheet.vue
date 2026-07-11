<template>
  <div class="s4-adjudication">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认非货币性资产交换以公允价值计量的交换损益（=换出公允价值-换出账面价值）与换入资产入账成本的计算准确，并将交换损益标注为非经常性损益在附注披露。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ 审定表 S4-1 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审定表 S4-1 — 非货币性资产交换</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              @click="handleSave"
            >保存</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s4-adjudication', '审定表S4-1')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="adjudicationRows"
        border
        style="width: 100%; font-size: 13px"
        :cell-class-name="cellClassName"
      >
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="换出资产" align="center">
          <el-table-column prop="outBookValue" label="账面价值" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.editable"
                v-model="row.outBookValue"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="recalculate"
              />
              <span v-else>{{ fmt(row.outBookValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="outFairValue" label="公允价值" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.editable"
                v-model="row.outFairValue"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="recalculate"
              />
              <span v-else>{{ fmt(row.outFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="换入资产" align="center">
          <el-table-column prop="inFairValue" label="公允价值" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && row.editable"
                v-model="row.inFairValue"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="recalculate"
              />
              <span v-else>{{ fmt(row.inFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="taxes" label="相关税费" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.taxes"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalculate"
            />
            <span v-else>{{ fmt(row.taxes) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="gainLoss" label="交换损益" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip
              content="交换损益 = 换出公允价值 - 换出账面价值"
              placement="top"
            >
              <span class="formula-cell">{{ fmt(row.gainLoss) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="inCost" label="换入成本" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip
              content="换入成本 = 换出公允价值 + 相关税费"
              placement="top"
            >
              <span class="formula-cell">{{ fmt(row.inCost) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 非经常性损益标注（Req 2.5） ═══ -->
    <el-card shadow="never" class="audit-section disclosure-card">
      <template #header>
        <div class="section-header">
          <span>附注披露 — 非经常性损益标注</span>
          <div class="header-actions">
            <el-tag type="warning" size="small">非经常性损益</el-tag>
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              :loading="disclosureState?.aiLoading?.value"
              @click="handleAiDisclosure"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s4-disclosure', '非经常性损益披露')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <div class="non-recurring-hint">
        <p class="hint-text">
          根据中国证监会《公开发行证券的公司信息披露解释性公告第1号——非经常性损益》，非货币性资产交换损益属于非经常性损益项目，应在附注中单独披露。
        </p>
      </div>
      <el-input
        v-if="!isReadonly"
        v-model="disclosureTextLocal"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="非货币性资产交换损益披露文本（如：本期发生非货币性资产交换收益 XX 元，系以 A 资产换入 B 资产所确认的交换收益...）"
        @input="handleDisclosureChange"
      />
      <div v-else class="disclosure-text">{{ disclosureTextLocal || '—' }}</div>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiNote"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s4-audit-note', '审计说明')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写审计说明"
      />
      <div v-else class="note-text">{{ auditNote || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 审定表按公允价值计量口径计算交换损益：损益 = 换出公允价值 - 换出账面价值。</p>
      <p>2. 换入资产入账成本 = 换出公允价值 + 相关税费。</p>
      <p>3. 公式列（交换损益/换入成本）为只读自动计算，不可手工覆盖。</p>
      <p>4. 该损益须标注为非经常性损益并在附注披露（证监会第1号公告），系统将发布 disclosure:note-text-updated 事件。</p>
      <p>5. 保存后审定金额将回写试算表（v2 正数口径，仅 flush 不 commit）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S4AdjudicationSheet.vue — 审定表 S4-1 + 非经常性损益标注
 *
 * 功能：
 * - 展示非货币性资产交换审定表（换入/换出/公允价值/损益）
 * - useS4FormulaEngine 计算交换损益与换入成本
 * - 公式列只读（gainLoss/inCost）+ 虚线下划线 + tooltip
 * - 非经常性损益标注（附注披露区）
 * - EventBus disclosure:note-text-updated 联动
 * - AI 辅助生成披露文本
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.1
 * Requirements: 1.5, 2.1, 2.5
 */
import { ref, inject, watch } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'
import { calcExchangeGainLoss } from '../composables/useS4FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 披露 EventBus ───────────────────────────────────────────────────────────

const disclosureState = inject<any>('sEstimateDisclosure')

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

// ─── 审定表数据 ──────────────────────────────────────────────────────────────

interface AdjudicationRow {
  item: string
  outBookValue: number
  outFairValue: number
  inFairValue: number
  taxes: number
  gainLoss: number
  inCost: number
  editable: boolean
}

const adjudicationRows = ref<AdjudicationRow[]>([
  {
    item: '交换事项一',
    outBookValue: 0,
    outFairValue: 0,
    inFairValue: 0,
    taxes: 0,
    gainLoss: 0,
    inCost: 0,
    editable: true,
  },
])

// ─── 使用 useS4FormulaEngine 计算公式列 ─────────────────────────────────────

function recalculate() {
  for (const row of adjudicationRows.value) {
    const result = calcExchangeGainLoss({
      inFairValue: row.inFairValue,
      outFairValue: row.outFairValue,
      outBookValue: row.outBookValue,
      taxes: row.taxes,
    })
    row.gainLoss = result.gainLoss
    row.inCost = result.inCost
  }
}

// ─── 公式列标记（CSS） ──────────────────────────────────────────────────────

function cellClassName({ column }: any): string {
  if (column?.property === 'gainLoss' || column?.property === 'inCost') return 'formula-col'
  return ''
}

// ─── 非经常性损益披露文本 ────────────────────────────────────────────────────

const disclosureTextLocal = ref('')
const auditNote = ref('')

// 同步父组件 disclosureText
watch(
  () => disclosureState?.disclosureText?.value,
  (val: string) => {
    if (val && val !== disclosureTextLocal.value) {
      disclosureTextLocal.value = val
    }
  },
  { immediate: true },
)

function handleDisclosureChange(val: string | Event) {
  const text = typeof val === 'string' ? val : (val.target as HTMLTextAreaElement)?.value || ''
  disclosureTextLocal.value = text
  disclosureState?.onDisclosureTextChange?.(text, 'non-recurring-gain-loss')
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

async function handleAiDisclosure() {
  const generated = await disclosureState?.generateDisclosureWithAi?.('non-recurring-gain-loss', {
    type: '非货币性资产交换损益',
    rows: adjudicationRows.value.map(r => ({ item: r.item, gainLoss: r.gainLoss })),
  })
  if (generated) {
    disclosureTextLocal.value = generated
  }
}

function handleAiNote() {
  // TODO: AI 辅助生成审计说明
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

function handleSave() {
  recalculate()
  emit('save')
}
</script>

<style scoped>
.s4-adjudication {
  padding: 12px;
}

.audit-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

:deep(.formula-col) {
  background-color: #fafafa;
}

.disclosure-card {
  border-left: 3px solid #e6a23c;
}

.non-recurring-hint {
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #fdf6ec;
  border-radius: 4px;
}

.hint-text {
  margin: 0;
  font-size: 12px;
  color: #e6a23c;
  line-height: 1.6;
}

.disclosure-text,
.note-text {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
  color: #303133;
}

.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}

.edit-hints summary {
  cursor: pointer;
  user-select: none;
}

.edit-hints p {
  margin: 4px 0;
  line-height: 1.5;
}
</style>
