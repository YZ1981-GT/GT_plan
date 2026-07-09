<template>
  <div class="i1-tab-disclosure-soe">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 原值/摊销/减值三层矩阵（跨sheet自动取数I1-1/I1-2）</div>
        <div class="guide-step"><span class="step-num">②</span> 净值合计=原值期末-摊销期末-减值期末</div>
        <div class="guide-step"><span class="step-num">③</span> 使用寿命不确定/所有权受限 动态行补充</div>
        <div class="guide-step"><span class="step-num">④</span> 摊销费用分配+AI辅助文字说明</div>
      </div>
    </div>

    <!-- 琥珀色方法论块 CAS30 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS30 无形资产披露要求（国有企业适用）</div>
      <div class="methodology-content">
        按《企业会计准则第6号——无形资产》及国有企业报表附注格式，应披露：各类无形资产原值/累计摊销/减值准备的变动；使用寿命不确定的无形资产判断依据；所有权受限情况；当期摊销费用归属科目分配。国企版使用"一、二、三..."中文编号。
      </div>
    </div>

    <!-- 7子节卡片 -->
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
              <el-button size="small" type="default" link @click="handleReview(`disc-soe-${section.key}`)">💬</el-button>
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
            <el-table-column prop="category" label="项目" min-width="140" fixed />
            <el-table-column label="期初余额" width="120" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.beginBalance"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'beginBalance', v)"
                  />
                </template>
                <span v-else :class="['amount-cell', { 'auto-fill': row.isAutoFilled }]">{{ fmtAmt(row.beginBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" width="120" align="right">
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
            <el-table-column label="本期减少" width="120" align="right">
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
            <el-table-column label="期末余额" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtAmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 合计行 -->
          <div class="matrix-subtotal" v-if="section.key === 'cost_overview'">
            合计: 期初 <span class="amount-cell">{{ fmtAmt(costTotal.beginBalance) }}</span>
            | 增加 <span class="amount-cell">{{ fmtAmt(costTotal.increase) }}</span>
            | 减少 <span class="amount-cell">{{ fmtAmt(costTotal.decrease) }}</span>
            | 期末 <span class="amount-cell formula-cell">{{ fmtAmt(costTotal.endBalance) }}</span>
          </div>
          <div class="matrix-subtotal" v-else-if="section.key === 'amort_overview'">
            合计: 期初 <span class="amount-cell">{{ fmtAmt(amortTotal.beginBalance) }}</span>
            | 计提 <span class="amount-cell">{{ fmtAmt(amortTotal.increase) }}</span>
            | 转出 <span class="amount-cell">{{ fmtAmt(amortTotal.decrease) }}</span>
            | 期末 <span class="amount-cell formula-cell">{{ fmtAmt(amortTotal.endBalance) }}</span>
          </div>
          <div class="matrix-subtotal" v-else-if="section.key === 'impairment_overview'">
            合计: 期初 <span class="amount-cell">{{ fmtAmt(impairmentTotal.beginBalance) }}</span>
            | 计提 <span class="amount-cell">{{ fmtAmt(impairmentTotal.increase) }}</span>
            | 转回 <span class="amount-cell">{{ fmtAmt(impairmentTotal.decrease) }}</span>
            | 期末 <span class="amount-cell formula-cell">{{ fmtAmt(impairmentTotal.endBalance) }}</span>
          </div>

          <div class="auto-fill-hint" v-if="['cost_overview','amort_overview','impairment_overview'].includes(section.key)">
            💡 数据自动从审定表I1/明细表I1-2取入（浅蓝色=跨sheet自动取数）
          </div>
        </template>

        <!-- 动态行子节 -->
        <template v-if="section.hasDynamicRows">
          <el-divider v-if="section.hasTable" content-position="left">明细项</el-divider>
          <el-table :data="getDynamicRows(section.key)" border stripe size="small">
            <el-table-column type="index" width="40" />
            <el-table-column prop="name" label="名称/项目" min-width="150">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="handleDynamicChange(section.key, row.rowId, 'name', row.name)" />
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="账面价值" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" @change="(v: number) => handleDynamicChange(section.key, row.rowId, 'amount', v)" />
                <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="180">
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
            <el-button size="small" @click="handleAddDynamic(section.key)">+ 新增行</el-button>
          </div>
        </template>

        <!-- 文字说明区（AI可生成） -->
        <template v-if="section.hasNoteText">
          <el-divider v-if="section.hasTable || section.hasDynamicRows" content-position="left">文字说明</el-divider>
          <el-input
            v-model="sectionNotes[section.key]"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            :disabled="isReadonly"
            :placeholder="`请填写${section.title}的文字说明...`"
            @change="handleNoteChange(section.key)"
          />
        </template>
      </el-card>
    </template>

    <!-- 净值合计汇总 -->
    <el-card shadow="never" class="summary-card">
      <template #header><span class="summary-title">无形资产账面净值合计</span></template>
      <div class="summary-content">
        <div class="summary-formula">
          净值 = 原值期末 <span class="amount-cell">{{ fmtAmt(costTotal.endBalance) }}</span>
          − 摊销期末 <span class="amount-cell">{{ fmtAmt(amortTotal.endBalance) }}</span>
          − 减值期末 <span class="amount-cell">{{ fmtAmt(impairmentTotal.endBalance) }}</span>
          = <span class="amount-cell net-value">{{ fmtAmt(netValueTotal) }}</span>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>（一）~（三）三层矩阵数据自动从审定表I1/明细表I1-2取入，如需修改请在源底稿调整</li>
        <li>（四）净值=原值−摊销−减值，自动计算不可编辑</li>
        <li>（五）使用寿命不确定的无形资产需逐项列示并说明判断依据</li>
        <li>（六）所有权受限（如抵押/质押）的无形资产需逐项列示</li>
        <li>（七）本期摊销费用按归属科目分配列示</li>
        <li>适用国有企业报表附注披露格式（CAS6/CAS30）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabDisclosureSoe.vue — 附注披露信息（国有企业版）
 * 67行×14列，26公式 (Req 14.1-14.4)
 *
 * 7 sections (Chinese numbering: 一/二/三...):
 *   cost_overview / amort_overview / impairment_overview / net_value
 *   indefinite_life / restricted / amort_expense
 *
 * - 从审定表/明细表/摊销表自动取数 (Req 14.2)
 * - AI辅助生成文字描述 (Req 14.3)
 * - EventBus publish 'disclosure:note-text-updated' (Req 14.4)
 */
import { ref, computed, inject, toRef, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI1Disclosure, SOE_SECTIONS, type I1DisclosureMatrixRow } from '../../composables/useI1Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  crossSheetAutoFill?: Record<string, number>
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const sections = SOE_SECTIONS

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  isAiGenerating,
  costMatrixRows,
  amortMatrixRows,
  impairmentMatrixRows,
  sectionRows,
  sectionNotes,
  costTotal,
  amortTotal,
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
} = useI1Disclosure(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    variant: ref('soe') as any,
    crossSheetAutoFill: computed(() => props.crossSheetAutoFill ?? {}),
    onSave(itemId: string, value: any) {
      emit('save', itemId, value)
    },
  },
)

// ─── EventBus: subscribe 'substantive:adjudicated' → auto-refresh (Req 14.2) ─
function handleAdjudicated(e: Event): void {
  const detail = (e as CustomEvent).detail
  // 仅响应I1相关科目(1701/1702/1703)或无过滤条件的全局广播
  if (!detail || detail.wpCode === 'I1' || ['1701', '1702', '1703'].includes(detail.accountCode)) {
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

function getMatrixRows(sectionKey: string): I1DisclosureMatrixRow[] {
  switch (sectionKey) {
    case 'cost_overview': return costMatrixRows.value
    case 'amort_overview': return amortMatrixRows.value
    case 'impairment_overview': return impairmentMatrixRows.value
    case 'net_value': return _buildNetValueRows()
    case 'amort_expense': return _buildAmortExpenseRows()
    default: return []
  }
}

function _buildNetValueRows(): I1DisclosureMatrixRow[] {
  return costMatrixRows.value.map((costRow) => {
    const amortRow = amortMatrixRows.value.find((r) => r.category === costRow.category)
    const impairRow = impairmentMatrixRows.value.find((r) => r.category === costRow.category)
    return {
      rowId: `net-${costRow.rowId}`,
      category: costRow.category,
      beginBalance: costRow.beginBalance - (amortRow?.beginBalance ?? 0) - (impairRow?.beginBalance ?? 0),
      increase: 0,
      decrease: 0,
      endBalance: costRow.endBalance - (amortRow?.endBalance ?? 0) - (impairRow?.endBalance ?? 0),
      isAutoFilled: true,
    }
  })
}

function _buildAmortExpenseRows(): I1DisclosureMatrixRow[] {
  const data = props.crossSheetAutoFill ?? {}
  const rows: I1DisclosureMatrixRow[] = []
  const categories = ['管理费用', '销售费用', '制造费用', '研发费用']
  for (const cat of categories) {
    const key = `disc_amort_${cat}`
    const amount = data[key] ?? 0
    if (amount !== 0 || costMatrixRows.value.length > 0) {
      rows.push({
        rowId: `amort-exp-${cat}`,
        category: cat,
        beginBalance: 0,
        increase: amount,
        decrease: 0,
        endBalance: amount,
        isAutoFilled: true,
      })
    }
  }
  return rows
}

// ─── Dynamic rows ────────────────────────────────────────────────────────────

function getDynamicRows(key: string) {
  return sectionRows.value[key] ?? []
}

async function handleAddDynamic(sectionKey: string) {
  try {
    const { value } = await ElMessageBox.prompt('请输入项目名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：土地使用权（xx地块）',
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
  const layer = sectionKey === 'cost_overview' ? 'cost'
    : sectionKey === 'amort_overview' ? 'amort'
    : 'impairment'
  updateMatrixCell(layer, rowId, field as keyof I1DisclosureMatrixRow, value ?? 0)
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

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-disclosure-soe { padding: 16px; font-size: 13px; }

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
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.auto-fill-hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 8px; }

/* 合计 */
.matrix-subtotal { margin-top: 8px; font-weight: 500; text-align: right; padding-right: 12px; font-size: 12px; }
.dynamic-actions { margin-top: 8px; }

/* 净值汇总 */
.summary-card { margin-bottom: 12px; border: 2px solid var(--el-color-primary-light-5); }
.summary-title { font-weight: 600; color: var(--el-color-primary); }
.summary-content { padding: 8px 0; }
.summary-formula { font-size: 14px; line-height: 2; }
.net-value { font-weight: 700; font-size: 16px; color: var(--el-color-primary); }

/* 矩阵表 */
.matrix-table { font-size: 13px; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
