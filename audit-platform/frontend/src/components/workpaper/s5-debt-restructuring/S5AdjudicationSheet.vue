<template>
  <div class="s5-adjudication">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：分别核实债权人与债务人视角的债务重组损益计算（债权人=D8-E8+F8；债务人=C16-E16-F16-G16），并将重组损益标注为非经常性损益在附注披露。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ 第一部分：作为债权人 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>一、作为债权人 — 债务重组利得（损失）</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              @click="handleSave"
            >保存</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s5-creditor', '作为债权人')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="creditorRows"
        border
        style="width: 100%; font-size: 13px"
        :cell-class-name="cellClassName"
      >
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column prop="origBook" label="债权原账面价值" min-width="140" align="right">
          <template #header>
            <el-tooltip content="D8 = 原账面价值 (origBook)" placement="top">
              <span class="formula-header">债权原账面价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.origBook"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalcCreditor"
            />
            <span v-else>{{ fmt(row.origBook) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="origFair" label="债权原公允价值" min-width="140" align="right">
          <template #header>
            <el-tooltip content="E8 = 公允价值 (origFair)" placement="top">
              <span class="formula-header">债权原公允价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.origFair"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalcCreditor"
            />
            <span v-else>{{ fmt(row.origFair) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recvFair" label="受让资产公允价值" min-width="140" align="right">
          <template #header>
            <el-tooltip content="F8 = 受让成本/受让资产公允价值 (recvFair)" placement="top">
              <span class="formula-header">受让资产公允价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.recvFair"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalcCreditor"
            />
            <span v-else>{{ fmt(row.recvFair) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="gainLoss" label="重组损益" min-width="140" align="right">
          <template #default="{ row }">
            <el-tooltip
              content="=D8-E8+F8 → origBook - origFair + recvFair"
              placement="top"
            >
              <span class="formula-cell">{{ fmt(row.gainLoss) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 第二部分：作为债务人 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>二、作为债务人 — 债务重组利得（损失）</span>
          <div class="header-actions">
            <el-button
              size="small"
              @click="handleOpenReview('s5-debtor', '作为债务人')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="debtorRows"
        border
        style="width: 100%; font-size: 13px"
        :cell-class-name="cellClassName"
      >
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column prop="debtBook" label="所清偿债务账面价值" min-width="160" align="right">
          <template #header>
            <el-tooltip content="C16 = 所清偿债务账面价值 (debtBook)" placement="top">
              <span class="formula-header">所清偿债务账面价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.debtBook"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalcDebtor"
            />
            <span v-else>{{ fmt(row.debtBook) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetBook" label="转让资产账面价值" min-width="160" align="right">
          <template #header>
            <el-tooltip content="E16+F16 = 转让金融资产账面 + 非金融资产账面 (合并为 assetBook)" placement="top">
              <span class="formula-header">转让资产账面价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.assetBook"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalcDebtor"
            />
            <span v-else>{{ fmt(row.assetBook) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="equityFair" label="权益工具公允价值" min-width="160" align="right">
          <template #header>
            <el-tooltip content="G16 = 权益工具公允价值 (equityFair)" placement="top">
              <span class="formula-header">权益工具公允价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.equityFair"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="recalcDebtor"
            />
            <span v-else>{{ fmt(row.equityFair) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="gainLoss" label="重组损益" min-width="140" align="right">
          <template #default="{ row }">
            <el-tooltip
              content="=C16-E16-F16-G16 → debtBook - assetBook - equityFair"
              placement="top"
            >
              <span class="formula-cell">{{ fmt(row.gainLoss) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 非经常性损益标注（Req 3.5） ═══ -->
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
              @click="handleOpenReview('s5-disclosure', '非经常性损益披露')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <div class="non-recurring-hint">
        <p class="hint-text">
          根据中国证监会《公开发行证券的公司信息披露解释性公告第1号——非经常性损益》，债务重组损益属于非经常性损益项目，应在附注中单独披露。
        </p>
      </div>
      <el-input
        v-if="!isReadonly"
        v-model="disclosureTextLocal"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="债务重组损益披露文本（如：本期确认债务重组收益 XX 元，系 A 公司豁免本公司应付款项所形成...）"
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
              @click="handleOpenReview('s5-audit-note', '审计说明')"
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
      <p>1. 审定表分「作为债权人」与「作为债务人」两部分，分别计算重组损益。</p>
      <p>2. 债权人公式：重组损益 = 债权原账面价值 - 债权原公允价值 + 受让资产公允价值（=D8-E8+F8）。</p>
      <p>3. 债务人公式：重组损益 = 所清偿债务账面价值 - 转让资产账面价值 - 权益工具公允价值（=C16-E16-F16-G16）。</p>
      <p>4. 公式列（重组损益）为只读自动计算，不可手工覆盖。</p>
      <p>5. 该损益须标注为非经常性损益并在附注披露（证监会第1号公告），系统将发布 disclosure:note-text-updated 事件。</p>
      <p>6. 保存后审定金额将回写试算表（v2 正数口径，仅 flush 不 commit）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S5AdjudicationSheet.vue — 审定表 S5-1 + 非经常性损益标注
 *
 * 功能：
 * - 分「作为债权人」与「作为债务人」两部分（Req 3.1）
 * - useS5FormulaEngine: calcCreditorGainLoss + calcDebtorGainLoss
 * - 公式列只读（gainLoss）+ 虚线下划线 + tooltip 显示公式来源
 * - 非经常性损益标注（附注披露区）（Req 3.5）
 * - EventBus disclosure:note-text-updated 联动
 * - AI 辅助生成披露文本
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.2
 * Requirements: 1.5, 3.1, 3.5
 */
import { ref, inject, watch } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'
import { calcCreditorGainLoss, calcDebtorGainLoss } from '../composables/useS5FormulaEngine'
import type { CreditorInput, DebtorInput } from '../composables/useS5FormulaEngine'

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

// ─── 债权人数据 ──────────────────────────────────────────────────────────────

interface CreditorRow {
  item: string
  origBook: number
  origFair: number
  recvFair: number
  gainLoss: number
  editable: boolean
}

const creditorRows = ref<CreditorRow[]>([
  {
    item: '债务重组事项一',
    origBook: 0,
    origFair: 0,
    recvFair: 0,
    gainLoss: 0,
    editable: true,
  },
])

// ─── 债务人数据 ──────────────────────────────────────────────────────────────

interface DebtorRow {
  item: string
  debtBook: number
  assetBook: number
  equityFair: number
  gainLoss: number
  editable: boolean
}

const debtorRows = ref<DebtorRow[]>([
  {
    item: '债务重组事项一',
    debtBook: 0,
    assetBook: 0,
    equityFair: 0,
    gainLoss: 0,
    editable: true,
  },
])

// ─── 使用 useS5FormulaEngine 计算公式列 ─────────────────────────────────────

function recalcCreditor() {
  for (const row of creditorRows.value) {
    const input: CreditorInput = {
      origBook: row.origBook,
      origFair: row.origFair,
      recvFair: row.recvFair,
      otherCost: 0,
    }
    row.gainLoss = calcCreditorGainLoss(input)
  }
}

function recalcDebtor() {
  for (const row of debtorRows.value) {
    const input: DebtorInput = {
      debtBook: row.debtBook,
      assetBook: row.assetBook,
      equityFair: row.equityFair,
    }
    row.gainLoss = calcDebtorGainLoss(input)
  }
}

// ─── 公式列标记（CSS） ──────────────────────────────────────────────────────

function cellClassName({ column }: any): string {
  if (column?.property === 'gainLoss') return 'formula-col'
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
    type: '债务重组损益',
    creditorRows: creditorRows.value.map(r => ({ item: r.item, gainLoss: r.gainLoss })),
    debtorRows: debtorRows.value.map(r => ({ item: r.item, gainLoss: r.gainLoss })),
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
  recalcCreditor()
  recalcDebtor()
  emit('save')
}
</script>

<style scoped>
.s5-adjudication {
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

.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
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
  font-size: var(--wp-font-size, 13px);
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
