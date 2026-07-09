<template>
  <div class="i4-tab-disclosure-listed">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 原值变动矩阵（期初+增加-摊销-减少=期末）自动从审定表取数</div>
        <div class="guide-step"><span class="step-num">②</span> 累计摊销变动矩阵（期初+本期摊销-减少=期末）</div>
        <div class="guide-step"><span class="step-num">③</span> 净值 = 原值期末 - 累计摊销期末</div>
        <div class="guide-step"><span class="step-num">④</span> 摊销方法/重大明细/其他说明 文字描述（AI辅助）</div>
      </div>
    </div>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS 附注披露要求（上市公司版）</div>
      <div class="methodology-content">
        按《企业会计准则第6号——无形资产》应用指南及信息披露编报规则：上市公司应披露长期待摊费用的原值变动、累计摊销变动、净值及摊销方法；对于重大的长期待摊费用项目应单独列示并说明受益期限、剩余摊销期限等。本表14行×13列，42个公式。
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

        <!-- 矩阵表子节 -->
        <template v-if="section.hasTable && (section.key === 'prepaid_original' || section.key === 'prepaid_amortization')">
          <el-table
            :data="getMatrixData(section.key)"
            border
            stripe
            size="small"
            class="matrix-table"
          >
            <el-table-column prop="item" label="费用项目" min-width="140" fixed />
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
                    @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'increase', v)"
                  />
                </template>
                <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期摊销" width="120" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.amortization"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'amortization', v)"
                  />
                </template>
                <span v-else class="amount-cell">{{ fmtAmt(row.amortization) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期减少(其他)" width="130" align="right">
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number
                    :model-value="row.decrease"
                    :controls="false"
                    size="small"
                    @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'decrease', v)"
                  />
                </template>
                <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末余额" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="= 期初 + 增加 - 摊销 - 减少">
                  {{ fmtAmt(row.endBalance) }}
                </span>
              </template>
            </el-table-column>
          </el-table>

          <!-- 合计行 -->
          <div class="totals-row">
            <span class="totals-label">合计</span>
            <span class="totals-value">期初: {{ fmtAmt(getSectionTotal(section.key, 'beginBalance')) }}</span>
            <span class="totals-value">增加: {{ fmtAmt(getSectionTotal(section.key, 'increase')) }}</span>
            <span class="totals-value">摊销: {{ fmtAmt(getSectionTotal(section.key, 'amortization')) }}</span>
            <span class="totals-value">减少: {{ fmtAmt(getSectionTotal(section.key, 'decrease')) }}</span>
            <span class="totals-value totals-end">期末: {{ fmtAmt(getSectionTotal(section.key, 'endBalance')) }}</span>
          </div>
        </template>

        <!-- 净值子节 -->
        <template v-if="section.key === 'prepaid_net_value'">
          <div class="net-value-summary">
            <div class="net-item">
              <span class="net-label">原值期末余额：</span>
              <span class="net-amount">{{ fmtAmt(disclosureState.originalTotal.value.endBalance) }}</span>
            </div>
            <div class="net-item">
              <span class="net-label">累计摊销期末：</span>
              <span class="net-amount">{{ fmtAmt(disclosureState.amortizationTotal.value.endBalance) }}</span>
            </div>
            <div class="net-item net-result">
              <span class="net-label">净值（原值 - 累计摊销）：</span>
              <span class="net-amount formula-cell" title="= 原值期末 - 累计摊销期末">
                {{ fmtAmt(disclosureState.netValueTotal.value) }}
              </span>
            </div>
          </div>
        </template>

        <!-- 动态行子节（重大明细） -->
        <template v-if="section.hasDynamicRows">
          <el-table :data="disclosureState.sectionRows.value[section.key] ?? []" border size="small" class="dynamic-table">
            <el-table-column prop="name" label="项目名称" min-width="150">
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
            <el-table-column prop="description" label="说明" min-width="200">
              <template #default="{ row }">
                <template v-if="!isReadonly">
                  <el-input v-model="row.description" size="small" @blur="handleDynamicRowChange(section.key, row.rowId, 'description', row.description)" />
                </template>
                <span v-else>{{ row.description }}</span>
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
        <template v-if="section.hasNoteText">
          <el-input
            :model-value="disclosureState.sectionNotes.value[section.key] ?? ''"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            :placeholder="`请填写${section.title}相关披露文字`"
            @blur="(e: FocusEvent) => disclosureState.saveSectionNote(section.key, (e.target as HTMLTextAreaElement).value)"
          />
        </template>
      </el-card>
    </template>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司版附注：14行×13列，42个公式</li>
        <li>原值变动 + 累计摊销变动 → 净值自动计算</li>
        <li>数据优先从审定表I4-1自动取数（收到 substantive:adjudicated 事件后刷新）</li>
        <li>重大明细动态行：弹窗输入名称后新增</li>
        <li>说明文字可使用AI辅助生成初稿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabDisclosureListed.vue — 附注披露（上市公司版）
 *
 * 14行×13列，42公式
 * - 原值变动矩阵 + 累计摊销变动矩阵
 * - 净值 = 原值期末 - 累计摊销期末
 * - 动态行（重大明细）
 * - AI辅助文字描述
 * - EventBus: subscribe 'substantive:adjudicated', publish 'disclosure:note-text-updated'
 * - Uses useI4Disclosure composable (variant='listed')
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 4.9
 * Requirements: 7.1-7.2
 */
import { ref, computed, inject } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI4Disclosure, type I4DisclosureMatrixRow } from '../../composables/useI4Disclosure'

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

const disclosureState = useI4Disclosure(
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

// ─── Matrix Data Access ──────────────────────────────────────────────────────

function getMatrixData(sectionKey: string): I4DisclosureMatrixRow[] {
  if (sectionKey === 'prepaid_original') return disclosureState.originalRows.value
  if (sectionKey === 'prepaid_amortization') return disclosureState.amortizationRows.value
  return []
}

function getSectionTotal(sectionKey: string, field: keyof I4DisclosureMatrixRow): number {
  if (sectionKey === 'prepaid_original') {
    return (disclosureState.originalTotal.value as any)[field] ?? 0
  }
  if (sectionKey === 'prepaid_amortization') {
    return (disclosureState.amortizationTotal.value as any)[field] ?? 0
  }
  return 0
}

// ─── Matrix Edit ─────────────────────────────────────────────────────────────

function handleMatrixEdit(sectionKey: string, rowId: string, field: keyof I4DisclosureMatrixRow, val: number): void {
  const layer = sectionKey === 'prepaid_original' ? 'original' : 'amortization'
  disclosureState.updateMatrixCell(layer, rowId, field, val)
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
  openReviewDialog(`I4 附注上市-${sectionKey}`)
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i4-tab-disclosure-listed { padding: 16px; font-size: 13px; }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; }
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

/* 合计行 */
.totals-row {
  display: flex; align-items: center; gap: 16px;
  padding: 8px 12px; background: var(--el-fill-color-lighter);
  border-radius: 4px; font-size: 12px; margin-top: 4px;
}
.totals-label { font-weight: 600; min-width: 40px; }
.totals-value { font-variant-numeric: tabular-nums; }
.totals-end { font-weight: 600; color: var(--el-color-primary); }

/* 净值摘要 */
.net-value-summary { padding: 12px; }
.net-item { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.net-label { font-size: 13px; color: var(--el-text-color-regular); }
.net-amount { font-weight: 600; font-variant-numeric: tabular-nums; }
.net-result { padding-top: 8px; border-top: 1px solid var(--el-border-color-lighter); }
.net-result .net-amount { color: var(--el-color-primary); font-size: 16px; }

/* 动态行 */
.dynamic-table { margin-bottom: 8px; }
.add-row-btn { margin-top: 4px; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
