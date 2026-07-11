<template>
  <div class="h1-tab-disclosure-soe">
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 固定资产总表（跨sheet自动取数）</div>
        <div class="guide-step"><span class="step-num">②</span> 闲置/融资租入/经营租出/受限/已提足 五子节</div>
      </div>
    </div>

    <template v-for="section in sections" :key="section.key">
      <el-card shadow="never" class="disclosure-card">
        <template #header>
          <div class="section-title">
            <span>{{ section.title }}</span>
            <div class="title-actions">
              <el-button size="small" type="primary" link @click="handleAiGenerate(section.key)">
                <el-icon><MagicStick /></el-icon> AI
              </el-button>
              <el-button size="small" type="default" link @click="handleReview(`disc-soe-${section.key}`)">💬</el-button>
            </div>
          </div>
        </template>

        <template v-if="section.key === 'overview'">
          <el-table :data="overviewRows" border stripe size="small">
            <el-table-column prop="category" label="资产分类" min-width="120" />
            <el-table-column prop="beginBalance" label="期初余额" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell auto-fill">{{ fmtAmt(row.beginBalance) }}</span></template>
            </el-table-column>
            <el-table-column prop="increase" label="本期增加" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell auto-fill">{{ fmtAmt(row.increase) }}</span></template>
            </el-table-column>
            <el-table-column prop="decrease" label="本期减少" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell auto-fill">{{ fmtAmt(row.decrease) }}</span></template>
            </el-table-column>
            <el-table-column label="期末余额" width="120" align="right">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span></template>
            </el-table-column>
          </el-table>
          <div class="auto-fill-hint">💡 数据自动从H1-1/H1-2取入</div>
        </template>

        <template v-else>
          <el-table :data="getDynamicRows(section.key)" border stripe size="small">
            <el-table-column type="index" width="40" />
            <el-table-column prop="name" label="资产名称/项目" min-width="160">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.name" size="small" />
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="账面价值" width="130" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" />
                <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="200">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.description" size="small" />
                <span v-else>{{ row.description }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="dynamic-actions" v-if="!isReadonly">
            <el-button size="small" @click="addDynamicRow(section.key)">+ 新增行</el-button>
          </div>
          <div class="subtotal-row">合计: <span class="amount-cell">{{ fmtAmt(getDynamicSubtotal(section.key)) }}</span></div>
        </template>
      </el-card>
    </template>

    <el-card shadow="never" class="note-card">
      <template #header><span>附注披露审计说明</span></template>
      <el-input v-model="disclosureNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企版披露格式，标题用"一、二、三..."</li>
        <li>概览表数据自动取入，其余子节按实际情况填写</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Disclosure, SOE_SECTIONS } from '../../composables/useH1Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const disclosureNote = ref('')
const sections = SOE_SECTIONS

const { costMatrixRows: overviewRows, sectionRows: dynamicRowsMap, addDynamicRow: _addDynamic } = useH1Disclosure(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { variant: ref('soe') },
)

function getDynamicRows(key: string) { return dynamicRowsMap.value?.[key] ?? [] }
function getDynamicSubtotal(key: string): number {
  return getDynamicRows(key).reduce((s: number, r: any) => s + (Number(r.amount) || 0), 0)
}
function addDynamicRow(key: string) { _addDynamic(key) }
function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-disclosure-soe { padding: 16px; font-size: 13px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.disclosure-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.auto-fill { color: var(--el-color-primary); }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.auto-fill-hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 8px; }
.dynamic-actions { margin-top: 8px; }
.subtotal-row { margin-top: 8px; font-weight: 500; text-align: right; padding-right: 12px; }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
