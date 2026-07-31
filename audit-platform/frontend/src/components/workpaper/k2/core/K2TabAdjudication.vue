<template>
  <div class="k2-tab-adjudication">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>
        K2-1 审定表审定<strong>其他流动资产</strong>（报表行 <code>BS-014</code> →
        <code>TB('1901','期末余额')</code>，借方/资产类）。资产类期末 = 期初 + 借方 − 贷方；
        审定数 = 未审 + AJE + RJE。三角勾稽：期末 = 期初 + 借 − 贷，差额须为 0。
      </p>
      <p>
        源模板逐字要求「<strong>根据实际情况列示；不存在的项目请删除</strong>」→
        本表明细项目行为<strong>动态行</strong>，按客户实际情况增删改名，
        四表库有明细子科目时可一键带入。
      </p>
    </div>

    <!-- 四表库取数溯源（报表行 → 标准码 → 客户原始码） -->
    <K2FourTableSourcePanel :source-codes="props.tbSourceCodes" />

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>记录的其他流动资产在资产负债表日确实存在且已恰当记录；</li>
        <li><b>完整性：</b>所有应当记录的其他流动资产均已记录，相关披露完整；</li>
        <li><b>权利和义务：</b>记录的其他流动资产确为被审计单位拥有或控制；</li>
        <li><b>计价和分摊：</b>其他流动资产以恰当金额包括在报表中，计价调整已恰当记录，披露充分适当；</li>
        <li><b>列报与披露：</b>已按企业会计准则规定作出恰当列报。</li>
      </ol>
    </el-alert>

    <!-- Section标题 + AI/复核按钮右对齐 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>K2-1 其他流动资产审定表</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">
              <el-icon><Plus /></el-icon> 新增项目行
            </el-button>
            <el-button
              size="small"
              plain
              :disabled="isReadonly || !hasPrefill"
              @click="handleSeedFromTb"
            >
              <el-icon><Download /></el-icon> 从四表库带入未审数
            </el-button>
            <el-button size="small" plain :disabled="isReadonly" @click="handleFillFromDetail">
              从 K2-2 明细带入
            </el-button>
            <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="adjPull.loading.value" @click="openBringInAdjustment">
              <el-icon><Download /></el-icon> 带入调整
            </el-button>
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-overall')">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-1')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 三角勾稽校验 Banner -->
      <div class="reconciliation-banner" :class="reconciliation.isBalanced ? 'balanced' : 'unbalanced'">
        <el-icon v-if="reconciliation.isBalanced" color="#67c23a"><CircleCheck /></el-icon>
        <el-icon v-else color="#f56c6c"><WarningFilled /></el-icon>
        <span v-if="reconciliation.isBalanced">✓ 三角勾稽平衡（期末=期初+借-贷）</span>
        <span v-else>✗ 三角勾稽不平，差额: {{ fmtAmt(reconciliation.diff) }}</span>
      </div>

      <!-- 跨Sheet交叉验证徽章 -->
      <div class="cross-sheet-badge" v-if="crossSheetResult">
        <el-tag :type="crossSheetResult.isMatch ? 'success' : 'warning'" size="small" effect="plain">
          K2-1合计 vs K2-2明细:
          {{ crossSheetResult.isMatch ? '一致 ✓' : `差额 ${fmtAmt(crossSheetResult.diff)}` }}
        </el-tag>
      </div>

      <!-- 空表引导（宁缺勿造：不预置固定行） -->
      <el-empty
        v-if="rows.length === 0"
        description="尚未列示明细项目"
        :image-size="72"
      >
        <p class="empty-hint">
          请按客户实际情况新增项目行（源模板示例：{{ K2_TEMPLATE_ROW_EXAMPLES.join(' / ') }}）；
          四表库已有 1901 明细子科目时可点「从四表库带入未审数」。
        </p>
      </el-empty>

      <!-- 审定表主体 -->
      <el-table
        v-else
        :data="displayRows"
        border stripe size="small" class="adj-table"
        :max-height="540"
        :row-class-name="getRowClassName"
      >
        <!-- 项目（动态行名可编辑） -->
        <el-table-column label="项目" min-width="190" fixed>
          <template #default="{ row }">
            <span v-if="row.rowKey === 'subtotal'" class="subtotal-label">{{ row.label }}</span>
            <div v-else class="label-cell">
              <el-input
                v-if="!isReadonly"
                v-model="labelDrafts[row.rowKey]"
                size="small"
                placeholder="项目名称"
                :aria-label="`项目名称 ${row.label}`"
                @blur="commitLabel(row.rowKey)"
                @keyup.enter="commitLabel(row.rowKey)"
              />
              <span v-else>{{ row.label }}</span>
              <el-tooltip v-if="row.foreignWarning" :content="row.foreignWarning" placement="top">
                <el-tag type="danger" size="small" effect="plain">口径存疑</el-tag>
              </el-tooltip>
              <el-tag v-else-if="row.source === 'tb'" type="success" size="small" effect="plain">
                四表
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.begin"
              :aria-label="`期初 ${row.label}`"
              @change="(v: number) => updateField(row.rowKey, 'begin', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>

        <!-- 本期借方 -->
        <el-table-column label="本期借方" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.debit"
              :aria-label="`本期借方 ${row.label}`"
              @change="(v: number) => updateField(row.rowKey, 'debit', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>

        <!-- 本期贷方 -->
        <el-table-column label="本期贷方" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.credit"
              :aria-label="`本期贷方 ${row.label}`"
              @change="(v: number) => updateField(row.rowKey, 'credit', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>

        <!-- 期末（公式列） -->
        <el-table-column label="期末" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: 期末=期初+借方-贷方" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.end) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 未审数（四表库带入，可手工覆盖） -->
        <el-table-column label="未审数" min-width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.unadjusted"
              :aria-label="`未审数 ${row.label}`"
              @change="(v: number) => updateField(row.rowKey, 'unadj', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>

        <!-- AJE（可编辑） -->
        <el-table-column label="AJE" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.aje"
              :aria-label="`账项调整 ${row.label}`"
              @change="(v: number) => updateField(row.rowKey, 'aje', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>

        <!-- RJE（可编辑） -->
        <el-table-column label="RJE" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.rje"
              :aria-label="`重分类调整 ${row.label}`"
              @change="(v: number) => updateField(row.rowKey, 'rje', v)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>

        <!-- 审定数（公式列） -->
        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: 审定=未审+AJE+RJE" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 变动率（公式列） -->
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: 变动率=(审定-上期审定)/|上期审定|" placement="top">
              <span class="formula-cell" :class="getChangeRateClass(row.changeRate)">
                {{ formatChangeRate(row.changeRate) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              :aria-label="`备注 ${row.label}`"
              @input="(v: string) => updateField(row.rowKey, 'remark', v)"
            />
            <span v-else class="amount-cell">{{ row.remark || '' }}</span>
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              size="small"
              type="danger"
              link
              @click="handleRemoveRow(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-note')">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写其他流动资产审定说明..."
        :disabled="isReadonly"
        @blur="saveNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('adj-conclusion')">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('K2-1-conclusion')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..."
        :disabled="isReadonly"
        @blur="saveConclusion"
      />
    </el-card>

    <!-- 与TB核对区 -->
    <el-card shadow="never" class="block-card" style="margin-top:12px">
      <template #header>
        <div class="section-title">
          <span>与试算平衡表核对</span>
          <el-tag size="small" type="info">科目 {{ tbAccountLabel }}</el-tag>
        </div>
      </template>
      <div class="tb-reconcile-grid">
        <div class="tb-row">
          <span class="tb-label">K2-1 审定合计</span>
          <span class="tb-value">{{ fmtAmt(subtotalRow.audited) }}</span>
        </div>
        <div class="tb-row">
          <span class="tb-label">试算平衡表数（{{ tbAccountLabel }}）</span>
          <span class="tb-value tb-auto">{{ fmtAmt(props.tbData.audited) }}</span>
        </div>
        <div class="tb-row" :class="{ 'tb-diff-warn': !tbMatched }">
          <span class="tb-label">差异</span>
          <span class="tb-value">{{ fmtAmt(tbDiff) }}</span>
          <el-tag v-if="tbMatched" type="success" size="small" effect="plain" style="margin-left:8px">✓ 核对一致</el-tag>
          <el-tag v-else type="danger" size="small" effect="plain" style="margin-left:8px">✗ 差异需排查</el-tag>
        </div>
      </div>
    </el-card>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" @click="handleWritebackTB" :loading="publishing">
        确认审定 → 回写TB（{{ tbAccountLabel }}）
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>科目由报表行 <code>BS-014 其他流动资产</code> 的映射规则解析得出（实证 <code>TB('1901','期末余额')</code>），不再硬编码前缀</li>
        <li>明细项目行按客户实际情况增删改名（源模板：不存在的项目请删除）；行名是「从 K2-2 带入」与附注推送的匹配键，必须唯一</li>
        <li>「口径存疑」标记的行属于<strong>别的报表行</strong>（预付款项→BS-008/F1、合同资产→D6、押金保证金→K1），列在本表会重复计入资产，请核实后删除</li>
        <li>审定数 = 未审数 + AJE + RJE；资产类期末 = 期初 + 借方 − 贷方</li>
        <li>三角勾稽：期末 = 期初 + 借 − 贷，绿色表示平衡，红色表示差异</li>
        <li>公式列（期末/审定数/变动率）虚线下划线 + 鼠标悬停显示公式来源</li>
        <li>跨 Sheet 验证：K2-1 合计应与 K2-2 明细表合计一致</li>
        <li>「确认审定」将回写 trial_balance 并发布 EventBus 事件通知附注刷新</li>
        <li>「带入调整」：按解析出的科目拉取调整分录，逐笔选目标项目行累加到 AJE/RJE</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      :subject-label="`${tbAccountLabel} 其他流动资产`"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabAdjudication.vue — K2-1 其他流动资产审定表（动态明细行 + 四表取数溯源）
 *
 * 🔴 两处历史缺陷已修（详见 `useK2Adjudication.ts` / `_k2_other_current_assets.py`）：
 * ① 科目写成 `1231`（应收款项坏账准备）→ 改由报表行 `BS-014` 映射解析（`1901`）；
 * ② 明细行硬编码 8 行且混入别循环科目 → 改动态行（增删改名 + 四表带入 + 明细带入）。
 *
 * Spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 3.3
 * Requirements: 2.2, 2.3, 2.5, 2.7
 */
import { ref, computed, inject, toRef, watch } from 'vue'
import { MagicStick, CircleCheck, WarningFilled, Download, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { fmtAmount } from '@/stores/displayPrefs'
import { useK2Adjudication, type K2AdjRow } from '../../composables/useK2Adjudication'
import { useK2CrossSheet } from '../../composables/useK2CrossSheet'
import { K2_TEMPLATE_ROW_EXAMPLES } from '../../composables/k2AdjudicationRows'
import type { TbSourceCodes } from '../../composables/shared/tbSourceCodes'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import K2FourTableSourcePanel from './K2FourTableSourcePanel.vue'

// ─── Props / Emits ────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  /** 试算平衡表核对数（由宿主按解析出的标准码汇总，不再是硬编码 1231） */
  tbData: { unadjusted: number; audited: number }
  prefill?: Array<Record<string, unknown>>
  /** 四表取数溯源（render 下发 `tb_source_codes`） */
  tbSourceCodes?: TbSourceCodes | null
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'remove', itemIds: string[]): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Inject ───────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composables ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  subtotalRow,
  reconciliation,
  auditNote,
  auditConclusion,
  updateField,
  addRow,
  renameRow,
  removeRow,
  rowItemIds,
  pullFromDetail,
  seedFromPrefill,
} = useK2Adjudication(allResponsesRef as any, {
  prefill: toRef(props, 'prefill') as any,
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
  onRemove: (itemIds: string[]) => {
    emit('remove', itemIds)
  },
})

const { adjudicationVsDetail } = useK2CrossSheet(allResponsesRef as any)

/** 回写 / 带入调整用的科目码 —— 取溯源解析结果，缺省回退 1901 */
const tbAccountCode = computed(() => {
  const codes = props.tbSourceCodes?.gross_standard?.filter(Boolean) || []
  return codes[0] || '1901'
})
const tbAccountLabel = computed(() => tbAccountCode.value)

// ─── 从集中登记带入调整（其他流动资产，资产借方） ───────────────────────────
// `useAdjudicationBringIn` 的 subjectPrefix/subjectCode 是**普通字符串**（不接受 ref），
// 故在 setup 期取值 —— render 已在挂载前解析好 `tb_source_codes`，缺省回退 1901 与
// 解析结果一致（实证四准则 BS-014 均为 TB('1901')）。
const bringInAccountCode = tbAccountCode.value
const { adjPull, visible: bringInVisible, rowOptions: bringInRowOptions, open: openBringInAdjustment, apply: onBringInApply } = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: bringInAccountCode,
  direction: 'debit', // 资产借方：净发生额 = 借 − 贷
  subjectCode: bringInAccountCode,
  wpCode: 'K2',
  subjectLabel: '其他流动资产',
  rows: computed(() => rows.value.map(r => ({ rowKey: r.rowKey, name: r.label, aje: r.aje, rje: r.rje }))),
  updateCell: (rowKey: string, field: any, value: number) => updateField(rowKey, field, value),
  totalAudited: () => subtotalRow.value.audited,
})

// ─── Local State ──────────────────────────────────────────────────────────────

const publishing = ref(false)

/** 行名编辑草稿（`el-input` 只绑 `@change` 会被 EP 重置，故用本地 v-model + blur 提交） */
const labelDrafts = ref<Record<string, string>>({})

watch(
  rows,
  (list) => {
    const next: Record<string, string> = {}
    for (const r of list) next[r.rowKey] = labelDrafts.value[r.rowKey] ?? r.label
    labelDrafts.value = next
  },
  { immediate: true, deep: false },
)

const hasPrefill = computed(() => (props.prefill?.length ?? 0) > 0)

// ─── Display Data ─────────────────────────────────────────────────────────────

/** 数据行 + 合计行 */
const displayRows = computed((): K2AdjRow[] => [...rows.value, subtotalRow.value])

/** 跨sheet交叉验证结果 */
const crossSheetResult = computed(() => adjudicationVsDetail.value)

const tbDiff = computed(() => subtotalRow.value.audited - (props.tbData?.audited ?? 0))
const tbMatched = computed(() => Math.abs(tbDiff.value) < 0.01)

// ─── 动态行操作 ───────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入其他流动资产明细项目名称（源模板示例：'
      + `${K2_TEMPLATE_ROW_EXAMPLES.join(' / ')}）`,
      '新增项目行',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：待抵扣进项税',
        inputValidator: (val) => (!val?.trim() ? '项目名称不能为空' : true),
      },
    )
    const res = addRow(String(value ?? ''))
    if (!res.ok) { ElMessage.warning(res.message || '新增失败'); return }
    ElMessage.success('已新增项目行')
  } catch {
    // 用户取消
  }
}

function commitLabel(rowKey: string): void {
  const draft = labelDrafts.value[rowKey] ?? ''
  const current = rows.value.find((r) => r.rowKey === rowKey)?.label ?? ''
  if (draft.trim() === current) return
  const res = renameRow(rowKey, draft)
  if (!res.ok) {
    ElMessage.warning(res.message || '改名失败')
    labelDrafts.value = { ...labelDrafts.value, [rowKey]: current }
  }
}

async function handleRemoveRow(row: K2AdjRow): Promise<void> {
  const affected = rowItemIds(row.rowKey)
  try {
    await ElMessageBox.confirm(
      affected.length > 0
        ? `删除「${row.label}」将同时清除该行 ${affected.length} 项已录数据，确认删除？`
        : `确认删除「${row.label}」？`,
      '删除项目行',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const res = removeRow(row.rowKey)
  if (!res.ok) { ElMessage.warning(res.message || '删除失败'); return }
  ElMessage.success('已删除项目行')
}

function handleSeedFromTb(): void {
  if (!hasPrefill.value) {
    ElMessage.info('四表库暂无其他流动资产明细子科目数据')
    return
  }
  const touched = seedFromPrefill()
  ElMessage[touched ? 'success' : 'info'](
    touched ? '已从四表库带入明细项目与未审数' : '各项目已有录入值，未覆盖（手工优先）',
  )
}

/** 从 K2-2 明细表按项目名称聚合带入未审数 */
function handleFillFromDetail(): void {
  const res = pullFromDetail()
  if (res.filled === 0 && res.created === 0) {
    ElMessage.warning('K2-2 明细表暂无数据，请先编制明细表')
    return
  }
  const parts = [`已带入 ${res.filled} 行未审数`]
  if (res.created > 0) parts.push(`新建 ${res.created} 个项目行`)
  if (res.unmatched.length > 0) parts.push(`${res.unmatched.length} 个零余额项目未建行`)
  ElMessage.success(parts.join('，'))
}

// ─── 保存 ─────────────────────────────────────────────────────────────────────

function saveNote() {
  emit('save', 'K2-1-audit-note', { remark: auditNote.value })
}

function saveConclusion() {
  emit('save', 'K2-1-audit-conclusion', { remark: auditConclusion.value })
}

/** 确认审定 → 回写TB + EventBus 通知 */
async function handleWritebackTB() {
  publishing.value = true
  try {
    const auditedTotal = subtotalRow.value.audited
    await http.put(`/api/projects/${props.projectId}/trial-balance/writeback`, {
      account_code: tbAccountCode.value,
      audited_amount: auditedTotal,
    })
    emit('save', 'K2-1-audited-total', { remark: String(auditedTotal) })
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'K2',
      accountCode: tbAccountCode.value,
      auditedAmount: auditedTotal,
      adjudicatedAmount: auditedTotal,
      timestamp: Date.now(),
    })
    ElMessage.success(`审定数已回写TB（${tbAccountCode.value} 其他流动资产）`)
  } catch {
    ElMessage.error('TB回写失败')
  } finally {
    publishing.value = false
  }
}

async function handleAiGenerate(section: string) {
  try {
    const context: Record<string, string> = {
      accountCode: tbAccountCode.value,
      accountName: '其他流动资产',
      reportRowCode: props.tbSourceCodes?.row_code || 'BS-014',
      sheet: 'K2-1',
      section,
      itemLabels: rows.value.map((r) => r.label).join('、'),
      auditedTotal: String(subtotalRow.value.audited ?? 0),
      unadjustedTotal: String(subtotalRow.value.unadjusted ?? 0),
      reconciliationStatus: reconciliation.value.isBalanced ? '三角勾稽平衡' : `不平衡，差额${reconciliation.value.diff}`,
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: section === 'adj-note'
        ? '请按源模板口径生成其他流动资产（报表行BS-014）审定表的审计说明，概述审定过程与结果，不得虚构未提供的项目与金额'
        : section === 'adj-conclusion'
          ? '请按源模板口径生成其他流动资产（报表行BS-014）审定表的审计结论，不得虚构未提供的项目与金额'
          : '请按源模板口径生成其他流动资产（报表行BS-014）审定表的综合分析说明，不得虚构未提供的项目与金额',
      context,
      existingContent: section === 'adj-note' ? auditNote.value : auditConclusion.value,
      section,
    })
    const generated = (res?.data?.data ?? res?.data)?.content || ''
    if (!generated) { ElMessage.warning('AI未生成内容'); return }
    if (section === 'adj-note' || section === 'adj-overall') {
      auditNote.value = generated
      saveNote()
    } else if (section === 'adj-conclusion') {
      auditConclusion.value = generated
      saveConclusion()
    }
    ElMessage.success('AI内容已填入')
  } catch {
    ElMessage.warning('AI生成失败或已取消')
  }
}

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── Formatters ───────────────────────────────────────────────────────────────

/** 金额格式单一真源 = `stores/displayPrefs.fmtAmount`（千分符 + 2 位 + 单位偏好） */
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return fmtAmount(val)
}

function formatChangeRate(rate: number | null): string {
  if (rate == null) return '-'
  return `${rate >= 0 ? '+' : ''}${rate.toFixed(1)}%`
}

function getChangeRateClass(rate: number | null): string {
  if (rate == null) return ''
  if (Math.abs(rate) > 50) return 'rate-warning'
  if (Math.abs(rate) > 20) return 'rate-attention'
  return ''
}

function getRowClassName({ row }: { row: K2AdjRow }): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row'
  if (row.foreignWarning) return 'foreign-row'
  return ''
}
</script>

<style scoped>
.k2-tab-adjudication {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}
.methodology-context p { margin: 0 0 6px; }
.methodology-context p:last-child { margin-bottom: 0; }
.methodology-context code {
  background: #fff3cd;
  padding: 0 3px;
}
.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }

/* 三角勾稽 Banner */
.reconciliation-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}
.reconciliation-banner.balanced {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  color: #67c23a;
}
.reconciliation-banner.unbalanced {
  background: #fef0f0;
  border: 1px solid #fde2e2;
  color: #f56c6c;
}

/* 跨Sheet验证徽章 */
.cross-sheet-badge {
  margin-bottom: 12px;
}

/* 卡片布局 */
.block-card {
  margin-bottom: 16px;
}
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.title-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
  flex-wrap: wrap;
}

/* 空表引导 */
.empty-hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
  max-width: 560px;
}

/* 审定表 */
.adj-table {
  font-size: var(--wp-font-size, 13px);
}
.label-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.amount-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* TB自动取入（只读灰色斜体） */
.tb-auto {
  color: var(--el-text-color-secondary);
  font-style: italic;
}

/* 合计行样式 */
.subtotal-label {
  font-weight: 600;
}
:deep(.subtotal-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
/* 口径存疑行（属于别的报表行的历史遗留行） */
:deep(.foreign-row) {
  background-color: #fef6f6 !important;
}

/* 变动率警告色 */
.rate-warning {
  color: var(--el-color-danger);
  font-weight: 600;
}
.rate-attention {
  color: var(--el-color-warning);
  font-weight: 500;
}

/* 审计说明/结论卡片 */
.note-card {
  margin-bottom: 12px;
}

/* 操作按钮 */
.action-bar {
  margin-top: 16px;
  text-align: right;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
.compile-hint code {
  background: #f0f2f5;
  padding: 0 3px;
}

/* TB核对区 */
.tb-reconcile-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tb-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  border-radius: 4px;
}
.tb-label {
  min-width: 200px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.tb-value {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  font-size: 13px;
}
.tb-diff-warn {
  background: #fef0f0;
  border: 1px solid #fde2e2;
}
</style>
