<template>
  <div class="h6-tab-adjudication">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实固定资产清理（1606 过渡科目）清理收入、清理支出（账面价值/清理费用/税费）及清理净损益计算准确、结转完整，确认期末余额清零，为 H10 资产处置损益及财务报表列报提供审定依据。"
    />

    <!-- 工具栏：底稿索引 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H6-1" :context-project-id="props.projectId" /></span>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>科目1606固定资产清理（借方/资产类，过渡科目）：期末余额 = 期初 + 借方 - 贷方；审定数 = 未审数 + AJE + RJE。清理过程结构：清理收入 - 清理支出(账面价值+清理费用+税费) = 清理净损益。<strong>过渡科目期末余额应为0</strong>（清理完毕结转H10）。</p>
    </div>

    <!-- 过渡科目期末校验警告 -->
    <el-alert v-if="!state.transitCheck.value.isZero" type="error" :closable="false" show-icon
      style="margin-bottom: 12px">
      <template #title>{{ state.transitCheck.value.warning }}</template>
    </el-alert>

    <!-- H10交叉验证警告 -->
    <el-alert v-if="!state.h10CrossCheck.value.isMatch && h10HasData" type="warning"
      :closable="false" show-icon style="margin-bottom: 12px">
      <template #title>{{ state.h10CrossCheck.value.warning }}</template>
    </el-alert>

    <!-- 跨sheet校验警告 -->
    <el-alert v-if="crossSheetWarning" type="warning" :closable="false" show-icon
      style="margin-bottom: 12px">
      <template #title>{{ crossSheetWarning }}</template>
    </el-alert>

    <!-- Section 1: 清理收入 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>一、清理收入</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-1-income')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="incomeDisplayRows" border stripe size="small" class="adj-table"
        :row-class-name="rowClassName">
        <el-table-column prop="name" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.isSubtotal }">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.beginBalance"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'beginBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.debitAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'debitAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.creditAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'creditAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末 = 期初 + 借方 - 贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.unadjusted"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'unadjusted', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.aje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'aje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.rje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'rje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + AJE + RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="45" v-if="!props.isReadonly">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal" size="small" type="danger" link
              @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!props.isReadonly">
        <el-button size="small" @click="handleAddRow('income')">+ 新增清理收入项</el-button>
      </div>
    </el-card>

    <!-- Section 2: 清理支出（账面价值/清理费用/税费） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、清理支出（账面价值 / 清理费用 / 税费）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-1-expense')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="expenseDisplayRows" border stripe size="small" class="adj-table"
        :row-class-name="rowClassName">
        <el-table-column prop="name" label="项目" min-width="160" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.isSubtotal }">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.beginBalance"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'beginBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.debitAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'debitAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.creditAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'creditAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末 = 期初 + 借方 - 贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.unadjusted"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'unadjusted', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.aje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'aje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.rje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'rje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定 = 未审 + AJE + RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="45" v-if="!props.isReadonly">
          <template #default="{ row }">
            <el-button v-if="!row.isSubtotal" size="small" type="danger" link
              @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="add-row-bar" v-if="!props.isReadonly">
        <el-button size="small" @click="handleAddRow('expense')">+ 新增清理支出项</el-button>
      </div>
    </el-card>

    <!-- Section 3: 清理净损益 = 清理收入 - 清理支出 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、清理净损益（= 清理收入 - 清理支出）</span>
        </div>
      </template>
      <el-table :data="[gainLossRow]" border size="small" class="adj-table gain-loss-table">
        <el-table-column prop="name" label="项目" min-width="140" fixed>
          <template #default><span class="subtotal-label">清理净损益</span></template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(gainLossRow.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(gainLossRow.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(gainLossRow.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default>
            <span class="formula-cell" title="收入期末 - 支出期末">{{ fmtAmt(gainLossRow.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(gainLossRow.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(gainLossRow.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default>
            <span class="formula-cell">{{ fmtAmt(gainLossRow.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default>
            <span class="formula-cell" title="净损益审定 = 收入审定 - 支出审定">{{ fmtAmt(state.disposalGainLoss.value) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Section 4: 余额行（期初/本期发生/期末） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>四、过渡科目余额（1606）</span>
          <div class="section-header-actions">
            <el-tag v-if="state.transitCheck.value.isZero" type="success" size="small">✓ 期末余额为0</el-tag>
            <el-tag v-else type="danger" size="small">⚠ 期末≠0</el-tag>
          </div>
        </div>
      </template>

      <el-table :data="balanceDisplayRows" border stripe size="small" class="adj-table"
        :row-class-name="rowClassName">
        <el-table-column prop="name" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-label': row.isSubtotal }">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.beginBalance"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'beginBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.debitAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'debitAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.creditAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'creditAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'error-amount': row.name.includes('期末') && !state.transitCheck.value.isZero }"
              title="期末 = 期初 + 借方 - 贷方">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.unadjusted"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'unadjusted', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.aje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'aje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isSubtotal && !props.isReadonly" v-model="row.rje"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'rje', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'error-amount': row.name.includes('期末') && !state.transitCheck.value.isZero }"
              title="审定 = 未审 + AJE + RJE">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- TB取数 + 差异核对 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header"><span>TB取数核对（科目1606）</span></div>
      </template>
      <div class="tb-compare">
        <div class="tb-row">
          <span class="tb-label">期末审定数(H6-1)：</span>
          <span class="tb-value">{{ fmtAmt(state.endBalanceAudited.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB未审数(1606)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbUnadjusted.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">TB审定数(1606)：</span>
          <span class="tb-value">{{ fmtAmt(state.tbAudited.value) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">差异(期末-TB审定)：</span>
          <span class="tb-value" :class="{ 'error-amount': !state.isTbMatch.value }">
            {{ fmtAmt(state.tbDiff.value) }}
          </span>
        </div>
        <div class="tb-row">
          <span class="tb-label">清理净损益：</span>
          <span class="tb-value">{{ fmtAmt(state.disposalGainLoss.value) }}</span>
        </div>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-1-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="props.isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-1-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..." :disabled="props.isReadonly"
        @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button type="primary" @click="handlePublish" :loading="publishing">
        确认审定 → 回写TB(1606)
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>科目1606固定资产清理（资产类/借方/过渡科目）：期末=期初+借方-贷方</li>
        <li>过渡科目期末余额应为0：清理完毕后全部结转至H10资产处置损益</li>
        <li>清理过程：清理收入 - 清理支出(账面价值+费用+税费) = 清理净损益</li>
        <li>审定数=未审数+AJE+RJE；净损益行自动汇总不可编辑</li>
        <li>H10交叉验证：清理净损益应与H10资产处置损益一致</li>
        <li>"确认审定"将回写trial_balance(1606)并发布EventBus事件'substantive:adjudicated'</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabAdjudication.vue — H6-1 审定表（59公式+过渡科目期末=0校验+H10交叉验证+TB回写）
 *
 * 清理过程结构：清理收入 | 清理支出(账面价值/清理费用/税费) | 清理净损益 | 余额行
 * 列：项目 | 期初余额 | 本期借方 | 本期贷方 | 期末余额 | 未审数 | AJE | RJE | 审定数
 * 公式：期末=期初+借-贷 | 审定=未审+AJE+RJE | 净损益=收入-支出 | 过渡科目期末=0
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 4.2
 * Requirements: 2.1-2.9
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH6Adjudication, type H6AdjudicationRow } from '../../composables/useH6Adjudication'
import { useH6CrossSheet } from '../../composables/useH6CrossSheet'
import { calcSubtotal } from '../../composables/useH6FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
// 父入口提供的持久化函数（更新共享 Map + 防抖 PUT checklist-responses）。Bug C 修复：此前仅写内存 Map。
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})
const publishing = ref(false)

// ─── Composable: useH6Adjudication ──────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const state = useH6Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
  onWritebackTB: async (amount: number) => {
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { wpCode: 'H6', accountCode: '1606', auditedAmount: amount },
    }))
  },
})

// ─── Composable: useH6CrossSheet ────────────────────────────────────────────
const crossSheet = useH6CrossSheet(allResponsesRef as any)

// ─── H10数据存在性判断 ──────────────────────────────────────────────────────
const h10HasData = computed(() => {
  const h10Resp = props.allResponses.get('H10-disposal-income')
  return h10Resp != null && h10Resp.remark != null
})

// ─── Display Rows ────────────────────────────────────────────────────────────

interface DisplayRow extends H6AdjudicationRow {
  isSubtotal: boolean
}

/** 清理收入行（含小计） */
const incomeDisplayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = state.incomeRows.value.map(r => ({ ...r, isSubtotal: r.isSubtotal ?? false }))
  if (rows.length > 1) {
    rows.push({
      rowId: 'income-subtotal',
      name: '清理收入小计',
      category: 'income',
      beginBalance: calcSubtotal(state.incomeRows.value.map(r => r.beginBalance)),
      debitAmount: calcSubtotal(state.incomeRows.value.map(r => r.debitAmount)),
      creditAmount: calcSubtotal(state.incomeRows.value.map(r => r.creditAmount)),
      endBalance: calcSubtotal(state.incomeRows.value.map(r => r.endBalance)),
      unadjusted: calcSubtotal(state.incomeRows.value.map(r => r.unadjusted)),
      aje: calcSubtotal(state.incomeRows.value.map(r => r.aje)),
      rje: calcSubtotal(state.incomeRows.value.map(r => r.rje)),
      audited: calcSubtotal(state.incomeRows.value.map(r => r.audited)),
      isSubtotal: true,
    })
  }
  return rows
})

/** 清理支出行（含小计） */
const expenseDisplayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = state.expenseRows.value.map(r => ({ ...r, isSubtotal: r.isSubtotal ?? false }))
  const sub = state.expenseSubtotal.value
  rows.push({
    rowId: 'expense-subtotal',
    name: '清理支出小计',
    category: 'expense',
    beginBalance: sub.beginBalance,
    debitAmount: sub.debitAmount,
    creditAmount: sub.creditAmount,
    endBalance: sub.endBalance,
    unadjusted: sub.unadjusted,
    aje: sub.aje,
    rje: sub.rje,
    audited: sub.audited,
    isSubtotal: true,
  })
  return rows
})

/** 余额行（期初/本期发生/期末） */
const balanceDisplayRows = computed<DisplayRow[]>(() => {
  return state.balanceRows.value.map(r => ({ ...r, isSubtotal: r.isSubtotal ?? false }))
})

/** 净损益汇总行（收入 - 支出） */
const gainLossRow = computed(() => {
  const incomeAudited = calcSubtotal(state.incomeRows.value.map(r => r.audited))
  const expenseAudited = state.expenseSubtotal.value.audited
  const incomeBegin = calcSubtotal(state.incomeRows.value.map(r => r.beginBalance))
  const expenseBegin = state.expenseSubtotal.value.beginBalance
  const incomeDebit = calcSubtotal(state.incomeRows.value.map(r => r.debitAmount))
  const expenseDebit = state.expenseSubtotal.value.debitAmount
  const incomeCredit = calcSubtotal(state.incomeRows.value.map(r => r.creditAmount))
  const expenseCredit = state.expenseSubtotal.value.creditAmount
  const incomeEnd = calcSubtotal(state.incomeRows.value.map(r => r.endBalance))
  const expenseEnd = state.expenseSubtotal.value.endBalance
  const incomeUnadj = calcSubtotal(state.incomeRows.value.map(r => r.unadjusted))
  const expenseUnadj = state.expenseSubtotal.value.unadjusted
  const incomeAje = calcSubtotal(state.incomeRows.value.map(r => r.aje))
  const expenseAje = state.expenseSubtotal.value.aje
  const incomeRje = calcSubtotal(state.incomeRows.value.map(r => r.rje))
  const expenseRje = state.expenseSubtotal.value.rje

  return {
    rowId: 'gain-loss',
    name: '清理净损益',
    category: 'gainLoss' as const,
    beginBalance: incomeBegin - expenseBegin,
    debitAmount: incomeDebit - expenseDebit,
    creditAmount: incomeCredit - expenseCredit,
    endBalance: incomeEnd - expenseEnd,
    unadjusted: incomeUnadj - expenseUnadj,
    aje: incomeAje - expenseAje,
    rje: incomeRje - expenseRje,
    audited: incomeAudited - expenseAudited,
    isSubtotal: true,
  }
})

// ─── 跨sheet校验警告 ─────────────────────────────────────────────────────────
const crossSheetWarning = computed<string>(() => {
  const check = crossSheet.adjudicationVsDetail.value
  if (!check.isMatch && check.diff !== 0) {
    const sign = check.diff > 0 ? '+' : ''
    return `审定净损益≠H6-2明细合计，差额：${sign}${fmtAmt(check.diff)}元`
  }
  return ''
})

// ─── Actions ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }) {
  if (row.isSubtotal) return 'subtotal-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: number | null) {
  state.updateCell(rowId, field, value ?? 0)
}

async function handleAddRow(category: 'income' | 'expense') {
  try {
    const label = category === 'income' ? '清理收入' : '清理支出'
    const { value } = await ElMessageBox.prompt(`请输入${label}项目名称`, `新增${label}项`, {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value, category)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  state.deleteRow(rowId)
}

async function handlePublish() {
  publishing.value = true
  try {
    await state.publishAdjudicated()
  } finally {
    publishing.value = false
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h6-tab-adjudication { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 12px;
}
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.block-card { margin-bottom: 16px; }
.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.adj-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.formula-cell {
  display: block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
  color: var(--el-text-color-primary);
}

.subtotal-label { font-weight: 700; }
:deep(.subtotal-row) { background-color: #f0f9eb !important; font-weight: 600; }
.gain-loss-table :deep(tr) { background-color: #fef3cd !important; font-weight: 700; }

.add-row-bar { margin-top: 8px; }

.tb-compare { display: flex; flex-wrap: wrap; gap: 16px; padding: 8px 0; }
.tb-row { display: flex; align-items: center; gap: 8px; }
.tb-label { color: var(--el-text-color-secondary); min-width: 150px; }
.tb-value { font-weight: 500; font-variant-numeric: tabular-nums; }

.error-amount { color: #f56c6c; font-weight: 600; }
.audit-note-card { margin-bottom: 12px; }
.action-bar { display: flex; justify-content: flex-end; margin-bottom: 12px; padding-top: 8px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
