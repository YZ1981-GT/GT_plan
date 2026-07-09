<template>
  <div class="i3-tab-disclosure-listed">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 商誉原值/减值准备变动矩阵（跨sheet自动取数I3-1/I3-6）</div>
        <div class="guide-step"><span class="step-num">②</span> 净值=原值期末-减值期末（商誉无摊销！）</div>
        <div class="guide-step"><span class="step-num">③</span> CGU分摊情况 动态行+可收回金额</div>
        <div class="guide-step"><span class="step-num">④</span> 关键假设/敏感性/结论 文字说明+AI辅助</div>
      </div>
    </div>

    <!-- 琥珀色方法论块 CAS8 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS8 资产减值 + 企业会计准则解释第5号 商誉披露要求</div>
      <div class="methodology-content">
        按《企业会计准则第8号——资产减值》及应用指南，上市公司应披露：商誉账面原值及变动；累计减值准备及变动；商誉分摊至各资产组(组合)的情况；减值测试过程及方法（含可收回金额确定方式）；关键假设及其确定依据；敏感性分析；减值测试结论。商誉不摊销，仅年度减值测试，减值不可转回。
      </div>
    </div>

    <!-- 8子节卡片 -->
    <template v-for="section in sections" :key="section.key">
      <el-card shadow="never" class="disclosure-card">
        <template #header>
          <div class="section-title">
            <span>{{ section.title }}</span>
            <div class="title-actions">
              <el-button
                v-if="section.hasNoteText"
                size="small"
                type="primary"
                link
                :loading="isAiGenerating"
                @click="handleAiGenerate(section.key)"
              >
                <el-icon><MagicStick /></el-icon> AI生成
              </el-button>
              <el-button size="small" type="default" link @click="handleReview(`disc-listed-${section.key}`)">💬</el-button>
            </div>
          </div>
        </template>

        <!-- 矩阵表子节 -->
        <template v-if="section.hasTable">
          <el-table
            :data="getMatrixRows(section.key)"
            border
            stripe
            size="small"
            class="matrix-table"
          >
            <el-table-column prop="investee" label="被投资单位(CGU)" min-width="160" fixed />
            <el-table-column label="期初余额" width="130" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.beginBalance"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'beginBalance', v)"
                  />
                </template>
                <span v-else :class="['amount-cell', { 'auto-fill': row.isAutoFilled }]">
                  {{ fmtAmt(row.beginBalance) }}
                  <el-tag v-if="row.isAutoFilled" size="small" type="info" class="auto-badge">自动取数</el-tag>
                </span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" width="130" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.increase"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'increase', v)"
                  />
                </template>
                <span v-else :class="['amount-cell', { 'auto-fill': row.isAutoFilled }]">{{ fmtAmt(row.increase) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期减少" width="130" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.decrease"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'decrease', v)"
                  />
                </template>
                <span v-else :class="['amount-cell', { 'auto-fill': row.isAutoFilled }]">{{ fmtAmt(row.decrease) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末余额" width="130" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtAmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 合计行 -->
          <div class="matrix-subtotal" v-if="section.key === 'goodwill_book_value'">
            合计: 期初 <span class="amount-cell">{{ fmtAmt(bookValueTotal.beginBalance) }}</span>
            | 增加(新并购) <span class="amount-cell">{{ fmtAmt(bookValueTotal.increase) }}</span>
            | 减少(减值) <span class="amount-cell">{{ fmtAmt(bookValueTotal.decrease) }}</span>
            | 期末 <span class="amount-cell formula-cell">{{ fmtAmt(bookValueTotal.endBalance) }}</span>
          </div>
          <div class="matrix-subtotal" v-else-if="section.key === 'goodwill_impairment'">
            合计: 期初 <span class="amount-cell">{{ fmtAmt(impairmentTotal.beginBalance) }}</span>
            | 计提 <span class="amount-cell">{{ fmtAmt(impairmentTotal.increase) }}</span>
            | 转出 <span class="amount-cell">{{ fmtAmt(impairmentTotal.decrease) }}</span>
            | 期末 <span class="amount-cell formula-cell">{{ fmtAmt(impairmentTotal.endBalance) }}</span>
            <div class="impairment-warning">⚠️ 商誉减值不可转回，"本期减少"仅限处置/注销</div>
          </div>
          <div class="matrix-subtotal" v-else-if="section.key === 'sensitivity_analysis'">
            敏感性矩阵（WACC±1% / 增长率±0.5%）
          </div>
          <div class="matrix-subtotal" v-else-if="section.key === 'impairment_result'">
            合计减值: <span class="amount-cell formula-cell">{{ fmtAmt(impairmentTotal.increase) }}</span>
          </div>

          <div class="auto-fill-hint" v-if="['goodwill_book_value','goodwill_impairment'].includes(section.key)">
            💡 数据自动从审定表I3-1/减值测试I3-6取入（浅蓝色=跨sheet自动取数）
          </div>
        </template>

        <!-- 动态行子节（CGU分摊） -->
        <template v-if="section.hasDynamicRows">
          <el-divider v-if="section.hasTable" content-position="left">CGU分摊明细</el-divider>
          <el-table :data="getDynamicRows(section.key)" border stripe size="small">
            <el-table-column type="index" width="40" />
            <el-table-column prop="name" label="资产组(CGU)名称" min-width="160">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="handleDynamicChange(section.key, row.rowId, 'name', row.name)" />
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="分摊商誉账面" width="130" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" @change="(v: number) => handleDynamicChange(section.key, row.rowId, 'amount', v)" />
                <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="分摊依据/可收回金额" min-width="200">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.description" size="small" @change="handleDynamicChange(section.key, row.rowId, 'description', row.description)" />
                <span v-else>{{ row.description }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="handleRemoveDynamic(section.key, row.rowId)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="dynamic-actions" v-if="!isReadonly">
            <el-button size="small" @click="handleAddDynamic(section.key)">+ 新增CGU</el-button>
          </div>
        </template>

        <!-- 文字说明区（AI可生成） -->
        <template v-if="section.hasNoteText">
          <el-divider v-if="section.hasTable || section.hasDynamicRows" content-position="left">文字说明</el-divider>
          <el-input
            v-model="sectionNotes[section.key]"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            :placeholder="getPlaceholder(section.key)"
            @change="handleNoteChange(section.key)"
          />
        </template>
      </el-card>
    </template>

    <!-- 净值合计汇总 -->
    <el-card shadow="never" class="summary-card">
      <template #header><span class="summary-title">商誉账面净值合计</span></template>
      <div class="summary-content">
        <div class="summary-formula">
          净值 = 商誉原值期末 <span class="amount-cell">{{ fmtAmt(bookValueTotal.endBalance) }}</span>
          − 减值准备期末 <span class="amount-cell">{{ fmtAmt(impairmentTotal.endBalance) }}</span>
          = <span class="amount-cell net-value">{{ fmtAmt(netValueTotal) }}</span>
        </div>
        <div class="summary-note">商誉不摊销，净值=原值−累计减值</div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>（1）商誉账面价值变动矩阵：期初/增加(新并购)/减少(减值)/期末</li>
        <li>（2）减值准备变动矩阵：期初/计提/转出(处置)/期末，商誉减值不可转回！</li>
        <li>（3）减值测试过程：说明可收回金额确定方式（公允-处置费 or 使用价值DCF）</li>
        <li>（4）CGU分摊：逐CGU列示分摊商誉额及可收回金额确定依据</li>
        <li>（5）关键假设：折现率/增长率/预测期/终值假设及确定依据</li>
        <li>（6）敏感性分析：关键参数变动对可收回金额的影响</li>
        <li>（7）结论：是否需计提减值、金额及会计处理</li>
        <li>（8）其他：如有并购、处置等特殊事项说明</li>
        <li>适用上市公司年报附注披露要求（CAS8/企业会计准则解释第5号）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabDisclosureListed.vue — I3 商誉附注披露信息（上市公司版）
 * 41行×8列，38公式 (Req 9.1-9.3)
 *
 * 8 sections:
 *   goodwill_book_value / goodwill_impairment / impairment_test_process / cgu_allocation
 *   key_assumptions / sensitivity_analysis / impairment_result / other_disclosure
 *
 * 商誉特殊：无摊销！仅原值+减值+净额+减值测试过程
 *
 * - 从审定表I3-1+减值测试I3-6自动取数 (Req 9.2)
 * - AI辅助生成文字描述 (Req 9.3)
 * - EventBus: subscribe 'substantive:adjudicated' 刷新 + publish 'disclosure:note-text-updated'
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 4.10
 */
import { ref, computed, inject, toRef, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import {
  useI3Disclosure,
  LISTED_SECTIONS,
  type I3DisclosureMatrixRow,
} from '../../composables/useI3Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  crossSheetAutoFill?: Record<string, number>
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const sections = LISTED_SECTIONS

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  isAiGenerating,
  bookValueRows,
  impairmentRows,
  sectionRows,
  sectionNotes,
  bookValueTotal,
  impairmentTotal,
  netValueTotal,
  applyAutoFill,
  addDynamicRow,
  removeDynamicRow,
  updateDynamicRow,
  updateMatrixCell,
  saveSectionNote,
  generateNoteText,
  applyAiGeneratedNote,
  dispose: disposeDisclosure,
} = useI3Disclosure(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    variant: ref('listed') as any,
    crossSheetAutoFill: computed(() => props.crossSheetAutoFill ?? {}),
    onSave(itemId: string, value: any) {
      emit('save', itemId, value)
    },
  },
)

// ─── EventBus: subscribe 'substantive:adjudicated' → auto-refresh (Req 9.2) ─

function handleAdjudicated(e: Event): void {
  const detail = (e as CustomEvent).detail
  // 仅响应I3相关科目(1711)或无过滤条件的全局广播
  if (!detail || detail.wpCode === 'I3' || detail.accountCode === '1711') {
    applyAutoFill()
  }
}

onMounted(() => {
  applyAutoFill()
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
})
onUnmounted(() => {
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  disposeDisclosure()
})

// ─── Matrix rows by section ──────────────────────────────────────────────────

function getMatrixRows(sectionKey: string): I3DisclosureMatrixRow[] {
  switch (sectionKey) {
    case 'goodwill_book_value': return bookValueRows.value
    case 'goodwill_impairment': return impairmentRows.value
    case 'sensitivity_analysis': return _buildSensitivityRows()
    case 'impairment_result': return _buildResultRows()
    default: return []
  }
}

/** 敏感性分析矩阵 — 根据CGU分摊构造 */
function _buildSensitivityRows(): I3DisclosureMatrixRow[] {
  const cguRows = sectionRows.value['cgu_allocation'] ?? []
  return cguRows.map((cgu) => ({
    rowId: `sens-${cgu.rowId}`,
    investee: cgu.name || '未命名CGU',
    beginBalance: cgu.amount ?? 0,       // 商誉分摊额
    increase: 0,                          // WACC+1%时差异(待填)
    decrease: 0,                          // WACC-1%时差异(待填)
    endBalance: cgu.amount ?? 0,          // 可收回金额(待填)
    isAutoFilled: false,
  }))
}

/** 减值结果矩阵 — 按CGU汇总 */
function _buildResultRows(): I3DisclosureMatrixRow[] {
  const cguRows = sectionRows.value['cgu_allocation'] ?? []
  return cguRows.map((cgu) => ({
    rowId: `result-${cgu.rowId}`,
    investee: cgu.name || '未命名CGU',
    beginBalance: cgu.amount ?? 0,       // 商誉分摊额
    increase: 0,                          // 可收回金额(待填)
    decrease: 0,                          // 减值金额(待填)
    endBalance: (cgu.amount ?? 0),        // 减值后净额
    isAutoFilled: false,
  }))
}

// ─── Dynamic rows ────────────────────────────────────────────────────────────

function getDynamicRows(key: string) {
  return sectionRows.value[key] ?? []
}

async function handleAddDynamic(sectionKey: string) {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产组(CGU)名称', '新增CGU行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX子公司/XX事业部',
    })
    if (value?.trim()) {
      addDynamicRow(sectionKey, value.trim())
    }
  } catch { /* cancelled */ }
}

function handleRemoveDynamic(sectionKey: string, rowId: string) {
  removeDynamicRow(sectionKey, rowId)
}

function handleDynamicChange(sectionKey: string, rowId: string, field: string, value: any) {
  updateDynamicRow(sectionKey, rowId, field as any, value)
}

// ─── Matrix edit ─────────────────────────────────────────────────────────────

function handleMatrixEdit(sectionKey: string, rowId: string, field: string, value: number) {
  const layer = sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment'
  updateMatrixCell(layer, rowId, field as keyof I3DisclosureMatrixRow, value ?? 0)
}

// ─── Note text ───────────────────────────────────────────────────────────────

function handleNoteChange(sectionKey: string) {
  saveSectionNote(sectionKey, sectionNotes.value[sectionKey] ?? '')
}

// ─── AI generation ───────────────────────────────────────────────────────────

async function handleAiGenerate(sectionKey: string) {
  const existing = sectionNotes.value[sectionKey] ?? ''
  const generated = await generateNoteText(sectionKey, existing)
  if (!generated) return

  try {
    await ElMessageBox.confirm(
      `AI生成内容预览：\n\n${generated.slice(0, 200)}${generated.length > 200 ? '...' : ''}`,
      'AI生成确认',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    await applyAiGeneratedNote(sectionKey, generated)
    ElMessage.success('已填入AI生成内容')
  } catch { /* cancelled */ }
}

// ─── Review dialog ───────────────────────────────────────────────────────────

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── Placeholders ────────────────────────────────────────────────────────────

function getPlaceholder(sectionKey: string): string {
  const map: Record<string, string> = {
    impairment_test_process: '请描述减值测试过程：可收回金额确定方式（公允价值减处置费用/使用价值DCF）、评估机构、测试时点...',
    cgu_allocation: '请说明商誉分摊至各资产组(组合)的依据，是否与内部管理报告层级一致...',
    key_assumptions: '请说明减值测试关键假设：折现率(WACC)确定方法、收入增长率预测依据、预测期及终值假设...',
    sensitivity_analysis: '请描述敏感性分析结果：关键参数(折现率/增长率/收入)变动±X%对可收回金额的影响...',
    impairment_result: '请说明减值测试结论：是否需计提减值、各CGU减值金额及会计处理...',
    other_disclosure: '如有并购、处置、业绩对赌等特殊事项请在此说明...',
  }
  return map[sectionKey] ?? `请填写${sectionKey}的文字说明...`
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i3-tab-disclosure-listed { padding: 16px; font-size: 13px; }

/* 蓝色渐变引导区 */
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }

/* 琥珀色方法论 */
.methodology-block { border-left: 4px solid #f59e0b; background: #fffbeb; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px; }
.methodology-title { font-weight: 600; color: #92400e; margin-bottom: 4px; font-size: 12px; }
.methodology-content { font-size: 12px; color: #78350f; line-height: 1.6; }

/* 卡片 */
.disclosure-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; align-items: center; }

/* 金额 */
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.auto-fill { color: var(--el-color-primary); }
.auto-badge { margin-left: 4px; vertical-align: middle; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.auto-fill-hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 8px; }

/* 合计 */
.matrix-subtotal { margin-top: 8px; font-weight: 500; text-align: right; padding-right: 12px; font-size: 12px; }
.impairment-warning { color: var(--el-color-danger); font-size: 11px; margin-top: 4px; font-weight: 400; }
.dynamic-actions { margin-top: 8px; }

/* 净值汇总 */
.summary-card { margin-bottom: 12px; border: 2px solid var(--el-color-primary-light-5); }
.summary-title { font-weight: 600; color: var(--el-color-primary); }
.summary-content { padding: 8px 0; }
.summary-formula { font-size: 14px; line-height: 2; }
.summary-note { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 4px; }
.net-value { font-weight: 700; font-size: 16px; color: var(--el-color-primary); }

/* 矩阵表 */
.matrix-table { font-size: 13px; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
