<template>
  <div class="i5-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：确认其他非流动资产附注披露信息的完整性、准确性，变动矩阵与审定表数据一致。" />

    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 其他非流动资产变动矩阵（期初+增加-减少=期末）自动从审定表取数</div>
        <div class="guide-step"><span class="step-num">②</span> 重大明细需单独列示（含原因说明及占比）</div>
        <div class="guide-step"><span class="step-num">③</span> 受限资产及其他说明（AI辅助）</div>
        <div class="guide-step"><span class="step-num">④</span> 上市公司版 20行×7列，41个公式</div>
      </div>
    </div>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS 附注披露要求（上市公司版）</div>
      <div class="methodology-content">
        按《企业会计准则》应用指南及信息披露编报规则：上市公司应披露其他非流动资产的期初余额、本期增加、本期减少及期末余额变动情况；重大项目应单独列示并说明原因及占总额比例。本表20行×7列，41个公式。科目1911其他非流动资产，资产类借方，期末=期初+增加-减少。
      </div>
    </div>

    <!-- 子节卡片 -->
    <template v-for="section in disclosureState.sections.value" :key="section.key">
      <el-card shadow="never" class="disclosure-card">
        <template #header>
          <div class="section-title-row">
            <span class="section-title">{{ section.title }}</span>
            <div class="title-actions">
              <el-button
                v-if="section.hasNoteText"
                size="small"
                type="primary"
                link
                :loading="disclosureState.isAiGenerating.value"
                @click="handleAiGenerate(section.key)"
              >
                <el-icon><MagicStick /></el-icon> AI生成
              </el-button>
              <el-button size="small" type="default" link @click="handleReview(section.key)">💬</el-button>
            </div>
          </div>
        </template>

        <!-- 变动矩阵表（上市公司7列：项目/期初/增加/减少/期末/原因说明/占比） -->
        <template v-if="section.hasTable && section.key === 'asset_movement'">
          <el-table
            :data="disclosureState.movementRows.value"
            border
            stripe
            size="small"
            class="matrix-table"
          >
            <el-table-column prop="item" label="资产项目" min-width="140" fixed />
            <el-table-column label="期初余额" width="120" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.beginBalance"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(row.rowId, 'beginBalance', v)"
                  />
                </template>
                <span v-else :class="['amount-cell', { 'auto-fill': row.isAutoFilled }]">
                  {{ fmtAmt(row.beginBalance) }}
                  <el-tag v-if="row.isAutoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
                </span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" width="120" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.increase"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(row.rowId, 'increase', v)"
                  />
                </template>
                <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期减少" width="120" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.decrease"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(row.rowId, 'decrease', v)"
                  />
                </template>
                <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末余额" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="= 期初 + 增加 - 减少">
                  {{ fmtAmt(row.endBalance) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="原因说明" min-width="160">
              <template #default="{ row }">
                <template v-if="!isReadonly">
                  <el-input
                    :model-value="row.remark ?? ''"
                    size="small"
                    placeholder="变动原因"
                    @blur="(e: FocusEvent) => handleRemarkEdit(row.rowId, (e.target as HTMLInputElement).value)"
                  />
                </template>
                <span v-else class="remark-cell">{{ row.remark ?? '' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="占比" width="90" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="= 期末余额 / 合计期末余额">
                  {{ fmtPercent(row.endBalance, disclosureState.movementTotal.value.endBalance) }}
                </span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 合计行 -->
          <div class="totals-row">
            <span class="totals-label">合计</span>
            <span class="totals-value">期初: {{ fmtAmt(disclosureState.movementTotal.value.beginBalance) }}</span>
            <span class="totals-value">增加: {{ fmtAmt(disclosureState.movementTotal.value.increase) }}</span>
            <span class="totals-value">减少: {{ fmtAmt(disclosureState.movementTotal.value.decrease) }}</span>
            <span class="totals-value totals-end">期末: {{ fmtAmt(disclosureState.movementTotal.value.endBalance) }}</span>
            <span class="totals-value">占比: 100%</span>
          </div>
        </template>

        <!-- 重大明细动态行（含原因说明占比） -->
        <template v-if="section.hasDynamicRows">
          <el-table :data="disclosureState.sectionRows.value[section.key] ?? []" border size="small" class="dynamic-table">
            <el-table-column prop="name" label="项目名称" min-width="140">
              <template #default="{ row }">
                <template v-if="!isReadonly">
                  <el-input v-model="row.name" size="small" @blur="handleDynamicRowChange(section.key, row.rowId, 'name', row.name)" />
                </template>
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="金额" width="130" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly">
                  <el-input-number v-model="row.amount" :controls="false" size="small" @change="handleDynamicRowChange(section.key, row.rowId, 'amount', row.amount)" />
                </template>
                <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="原因说明" min-width="160">
              <template #default="{ row }">
                <template v-if="!isReadonly">
                  <el-input v-model="row.description" size="small" @blur="handleDynamicRowChange(section.key, row.rowId, 'description', row.description)" />
                </template>
                <span v-else>{{ row.description }}</span>
              </template>
            </el-table-column>
            <el-table-column label="占比" width="90" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="= 金额 / 合计期末余额">
                  {{ fmtPercent(row.amount, disclosureState.movementTotal.value.endBalance) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="disclosureState.removeDynamicRow(section.key, row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button v-if="!isReadonly" size="small" type="primary" text class="add-row-btn" @click="handleAddDynamicRow(section.key)">
            + 新增重大明细
          </el-button>
        </template>

        <!-- 说明文本子节 -->
        <template v-if="section.hasNoteText && !section.hasDynamicRows">
          <el-input
            :model-value="disclosureState.sectionNotes.value[section.key] ?? ''"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            :placeholder="`请填写${section.title}相关披露文字`"
            @blur="(e: FocusEvent) => disclosureState.saveSectionNote(section.key, (e.target as HTMLTextAreaElement).value)"
          />
        </template>

        <!-- 重大明细的说明文字（AI可生成） -->
        <template v-if="section.hasNoteText && section.hasDynamicRows">
          <el-divider content-position="left" class="note-divider">说明文字</el-divider>
          <el-input
            :model-value="disclosureState.sectionNotes.value[section.key] ?? ''"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            :disabled="isReadonly"
            :placeholder="`请填写${section.title}相关补充说明`"
            @blur="(e: FocusEvent) => disclosureState.saveSectionNote(section.key, (e.target as HTMLTextAreaElement).value)"
          />
        </template>
      </el-card>
    </template>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="请填写审计说明..."
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="请填写审计结论..."
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司版附注：20行×7列，41个公式</li>
        <li>资产类借方科目1911：期末 = 期初 + 增加 - 减少</li>
        <li>7列：项目/期初/增加/减少/期末/原因说明/占比</li>
        <li>数据优先从审定表I5-1自动取数（收到 substantive:adjudicated 事件后刷新）</li>
        <li>重大明细动态行：弹窗输入名称后新增，含占比计算</li>
        <li>说明文字可使用AI辅助生成初稿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabDisclosureListed.vue — 附注披露（上市公司版）
 *
 * 20行×7列，41公式
 * - 其他非流动资产变动矩阵（项目/期初/增加/减少/期末/原因说明/占比）
 * - 重大明细动态行（含原因说明+占比）
 * - 受限资产说明 + 其他说明（AI辅助）
 * - EventBus: subscribe 'substantive:adjudicated', publish 'disclosure:note-text-updated'
 * - Uses useI5Disclosure composable (variant='listed')
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 4.6
 * Requirements: 5.1-5.2
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI5Disclosure, type I5DisclosureMatrixRow } from '../../composables/useI5Disclosure'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const disclosureState = useI5Disclosure(
  computed(() => props.wpId),
  computed(() => props.projectId),
  computed(() => props.allResponses),
  {
    variant: ref('listed'),
    onSave: (itemId: string, value: any) => {
      const serialized = typeof value === 'string' ? value : JSON.stringify(value)
      emit('save', itemId, serialized)
    },
  },
)

// ─── Matrix Edit ─────────────────────────────────────────────────────────────

function handleMatrixEdit(rowId: string, field: keyof I5DisclosureMatrixRow, val: number): void {
  disclosureState.updateMatrixCell(rowId, field, val)
}

function handleRemarkEdit(rowId: string, value: string): void {
  // Persist remark to the row (remark isn't in I5DisclosureMatrixRow type but may exist on raw data)
  const row = disclosureState.movementRows.value.find((r) => r.rowId === rowId)
  if (row) {
    ;(row as any).remark = value
    disclosureState.updateMatrixCell(rowId, 'item' as any, row.item) // trigger persist
  }
}

// ─── Dynamic Rows ────────────────────────────────────────────────────────────

async function handleAddDynamicRow(sectionKey: string): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入重大明细项目名称', '新增明细', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    disclosureState.addDynamicRow(sectionKey, name)
  } catch { /* cancel */ }
}

function handleDynamicRowChange(sectionKey: string, rowId: string, field: string, value: any): void {
  disclosureState.updateDynamicRow(sectionKey, rowId, field as any, value)
}

// ─── AI ──────────────────────────────────────────────────────────────────────

async function handleAiGenerate(sectionKey: string): Promise<void> {
  const text = await disclosureState.generateNoteText(sectionKey)
  if (text) {
    await disclosureState.applyAiGeneratedNote(sectionKey, text)
  }
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview(sectionKey: string): void {
  openReviewDialog(`I5 附注上市-${sectionKey}`)
}

// ─── Audit Note / Conclusion (AN+AC) persistence ─────────────────────────────

const NOTE_KEY = 'I5-disclosure-listed-audit-note'
const CONCLUSION_KEY_AC = 'I5-disclosure-listed-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  emit('save', NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY_AC, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY_AC, item)
  emit('save', CONCLUSION_KEY_AC, val)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY_AC)
  if (c?.remark) auditConclusion.value = c.remark
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | null | undefined, total: number | null | undefined): string {
  if (val == null || total == null || total === 0) return '-'
  const pct = (val / total) * 100
  return `${pct.toFixed(2)}%`
}
</script>

<style scoped>
.i5-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 审计目标 */
.objective-alert { margin-bottom: 14px; }

/* 审计说明/结论 el-card */
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

/* 琥珀色方法论块 */
.methodology-block {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-title { font-weight: 600; color: #78350f; margin-bottom: 4px; }

/* 子节卡片 */
.disclosure-card { margin-bottom: 16px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-size: 14px; font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 4px; }

/* 矩阵表 */
.matrix-table { margin-bottom: 8px; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.amount-cell { font-variant-numeric: tabular-nums; }
.auto-fill { color: var(--el-color-info); }
.auto-badge { margin-left: 4px; }
.remark-cell { color: var(--el-text-color-regular); font-size: 12px; }

/* 合计行 */
.totals-row {
  display: flex; align-items: center; gap: 16px;
  padding: 8px 12px; background: var(--el-fill-color-lighter);
  border-radius: 4px; font-size: 12px; margin-top: 4px;
}
.totals-label { font-weight: 600; min-width: 40px; }
.totals-value { font-variant-numeric: tabular-nums; }
.totals-end { font-weight: 600; color: var(--el-color-primary); }

/* 动态行 */
.dynamic-table { margin-bottom: 8px; }
.add-row-btn { margin-top: 4px; }
.note-divider { margin: 12px 0 8px; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
