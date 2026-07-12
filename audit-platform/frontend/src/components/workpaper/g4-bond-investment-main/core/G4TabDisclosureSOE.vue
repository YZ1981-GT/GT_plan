<template>
  <div class="g4-disclosure-soe">
    <!-- Section: 债权投资附注(国企) 71行×7列分多section -->
    <template v-for="(section, sIdx) in sections" :key="section.id">
      <div class="section-head">
        <h4 class="section-title">{{ section.title }}</h4>
        <div class="head-actions">
          <el-button v-if="section.hasTextArea" size="small" type="primary" text :disabled="isReadonly" @click="fillAiDraft(sIdx)">
            🤖AI辅助
          </el-button>
          <GtReviewTrigger :section-id="`G4-disclosure-soe-${section.id}`" />
        </div>
      </div>

      <!-- 结构化表格区 -->
      <el-table
        v-if="section.rows.length > 0"
        :data="section.rows"
        border
        stripe
        :max-height="section.rows.length > 50 ? 480 : undefined"
        style="width: 100%; font-size: 13px; margin-bottom: 8px"
      >
        <el-table-column prop="item" label="项目" min-width="180" fixed />
        <el-table-column label="期初余额" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.openingBalance) }}</template>
        </el-table-column>
        <el-table-column label="本期增加" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodIncrease) }}</template>
        </el-table-column>
        <el-table-column label="本期减少" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodDecrease) }}</template>
        </el-table-column>
        <el-table-column label="期末余额" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.closingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摊余成本" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.amortizedCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
      </el-table>

      <!-- 文本区 -->
      <el-card v-if="section.hasTextArea" shadow="never" class="text-card">
        <el-input
          v-model="section.textContent"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 15 }"
          :disabled="isReadonly"
          :placeholder="`${section.title} 附注文本...`"
          @change="onNoteTextChange(sIdx)"
        />
      </el-card>
    </template>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注格式（71行×7列），简化列示期初/期末/摊余成本</li>
        <li>监听 substantive:adjudicated(1501) 自动同步审定数</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>超过50行启用虚拟滚动(el-table max-height)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabDisclosureSOE.vue — 附注披露信息（国企）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Req 4.2~4.6, 9.4, 11.1, 11.6
 * 71行×7列结构化表格 + 虚拟滚动(>50行阈值)
 * EventBus: subscribe substantive:adjudicated(1501) → auto-refresh
 *           publish disclosure:note-text-updated on text change
 * AI辅助按钮 + 复核按钮（每个section标题行右侧）
 */
import { reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const G4_ACCOUNT_CODE = '1501'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ═══ 格式化金额 ═══
function fmtAmount(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const isReadonly = computed(() => props.isReadonly)

// ═══ 附注结构 —— 71行分为多section ═══
interface DisclosureRowSOE {
  item: string
  openingBalance: number
  periodIncrease: number
  periodDecrease: number
  closingBalance: number
  amortizedCost: number
  remark: string
  isFormula?: boolean
}

interface DisclosureSectionSOE {
  id: string
  title: string
  rows: DisclosureRowSOE[]
  hasTextArea: boolean
  textContent: string
}

function buildSections(): DisclosureSectionSOE[] {
  return [
    {
      id: 'cost-overview',
      title: '一、债权投资——成本',
      rows: generateRows('成本', 14),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'interest-adjustment',
      title: '二、债权投资——利息调整',
      rows: generateRows('利息调整', 12),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'accrued-interest',
      title: '三、债权投资——应计利息',
      rows: generateRows('应计利息', 12),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'impairment',
      title: '四、减值准备',
      rows: generateRows('减值', 15),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'summary',
      title: '五、摊余成本合计',
      rows: generateRows('合计', 18),
      hasTextArea: true,
      textContent: '',
    },
  ]
}

function generateRows(prefix: string, count: number): DisclosureRowSOE[] {
  const rows: DisclosureRowSOE[] = []
  for (let i = 1; i <= count; i++) {
    rows.push({
      item: `${prefix}项目${i}`,
      openingBalance: 0,
      periodIncrease: 0,
      periodDecrease: 0,
      closingBalance: 0,
      amortizedCost: 0,
      remark: '',
      isFormula: i === count,
    })
  }
  return rows
}

const sections = reactive<DisclosureSectionSOE[]>(buildSections())

// ═══ EventBus: subscribe substantive:adjudicated(1501) ═══
let adjudicatedAmount = 0

function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === G4_ACCOUNT_CODE && d.adjudicatedAmount != null) {
    adjudicatedAmount = d.adjudicatedAmount
    // 自动刷新审定数据到合计section
    const summarySection = sections.find(s => s.id === 'summary')
    if (summarySection && summarySection.rows.length > 0) {
      const lastRow = summarySection.rows[summarySection.rows.length - 1]
      lastRow.amortizedCost = adjudicatedAmount
    }
  }
}

onMounted(() => {
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  loadFromHtmlData()
})
onBeforeUnmount(() => {
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
})

// ═══ EventBus: publish disclosure:note-text-updated ═══
function onNoteTextChange(_sectionIdx: number): void {
  const allText = sections
    .filter(s => s.hasTextArea && s.textContent)
    .map(s => `【${s.title}】\n${s.textContent}`)
    .join('\n\n')
  try {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { accountCode: G4_ACCOUNT_CODE, section: 'soe', text: allText },
    }))
  } catch { /* silent */ }
}

// ═══ AI辅助 ═══
function fillAiDraft(sectionIdx: number): void {
  if (isReadonly.value) return
  const section = sections[sectionIdx]
  if (!section) return
  const draft = `${section.title}期末余额为 [审定金额] 元。`
  section.textContent = section.textContent ? `${section.textContent}\n${draft}` : draft
  onNoteTextChange(sectionIdx)
}

// ═══ 数据加载 ═══
function loadFromHtmlData(): void {
  if (!props.htmlData?.disclosureSOE?.sections) return
  const saved = props.htmlData.disclosureSOE.sections as DisclosureSectionSOE[]
  saved.forEach((s, i) => {
    if (sections[i]) {
      if (s.textContent) sections[i].textContent = s.textContent
      if (s.rows?.length) sections[i].rows = s.rows
    }
  })
}
</script>

<style scoped>
.g4-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin: 16px 0 8px; }
.section-head:first-child { margin-top: 0; }
.section-title { margin: 0; font-size: 14px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.text-card { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
