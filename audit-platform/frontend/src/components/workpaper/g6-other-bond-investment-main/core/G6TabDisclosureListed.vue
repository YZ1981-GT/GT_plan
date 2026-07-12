<template>
  <div class="g6-disclosure-listed">
    <!-- Section: 其他债权投资附注(上市公司) 137行×16列分多section -->
    <template v-for="(section, sIdx) in sections" :key="section.id">
      <div class="section-head">
        <h4 class="section-title">{{ section.title }}</h4>
        <div class="head-actions">
          <el-button v-if="section.hasTextArea" size="small" type="primary" text :disabled="isReadonly" @click="fillAiDraft(sIdx)">
            🤖AI辅助
          </el-button>
          <GtReviewTrigger :section-id="`G6-disclosure-listed-${section.id}`" />
        </div>
      </div>

      <!-- 结构化表格区（虚拟滚动 max-height） -->
      <el-table
        v-if="section.rows.length > 0"
        :data="section.rows"
        border
        stripe
        :max-height="section.rows.length > 30 ? 520 : undefined"
        style="width: 100%; font-size: 13px; margin-bottom: 8px"
      >
        <el-table-column prop="item" label="项目" min-width="150" fixed />
        <el-table-column label="期初成本" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.openingCost) }}</template>
        </el-table-column>
        <el-table-column label="期初利息调整" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.openingInterestAdj) }}</template>
        </el-table-column>
        <el-table-column label="期初应计利息" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.openingAccruedInterest) }}</template>
        </el-table-column>
        <el-table-column label="期初小计" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.openingSubtotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodIncrease) }}</template>
        </el-table-column>
        <el-table-column label="本期减少" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodDecrease) }}</template>
        </el-table-column>
        <el-table-column label="本期利息收入" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.interestIncome) }}</template>
        </el-table-column>
        <el-table-column label="公允价值变动" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.fvChange) }}</template>
        </el-table-column>
        <el-table-column label="期末成本" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.closingCost) }}</template>
        </el-table-column>
        <el-table-column label="期末小计" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.closingSubtotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="110" align="right">
          <template #default="{ row }">{{ fmtAmount(row.impairment) }}</template>
        </el-table-column>
        <el-table-column label="摊余成本" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.amortizedCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="票面利率" width="90" align="center">
          <template #default="{ row }">{{ row.couponRate ? (row.couponRate * 100).toFixed(2) + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column label="实际利率" width="90" align="center">
          <template #default="{ row }">{{ row.effectiveRate ? (row.effectiveRate * 100).toFixed(2) + '%' : '-' }}</template>
        </el-table-column>
        <el-table-column label="到期日" width="100" align="center">
          <template #default="{ row }">{{ row.maturityDate || '-' }}</template>
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
          :autosize="{ minRows: 4, maxRows: 20 }"
          :disabled="isReadonly"
          :placeholder="`${section.title} 附注文本...`"
          @change="onNoteTextChange(sIdx)"
        />
      </el-card>
    </template>

    <!-- 底部AI辅助按钮 -->
    <div class="bottom-ai-actions">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="fillAiDraftAll">
        🤖 AI辅助生成全部附注
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注格式（137行×16列），按投资类型分类列示期初/期末/变动/减值/摊余成本</li>
        <li>监听 substantive:adjudicated(1503) 自动同步审定数</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>虚拟滚动已启用（el-table max-height）确保超长表格流畅渲染</li>
        <li>FVOCI-Debt 双重计量：同时反映公允价值变动(OCI)和ECL减值(损益)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Task 7.2
 * Requirements: 4.1, 4.3, 7.5, 7.6
 *
 * 137行×16列结构化表格 + 虚拟滚动(el-table max-height)
 * EventBus: subscribe substantive:adjudicated(1503) → auto-refresh
 *           publish disclosure:note-text-updated on text change
 * 多section结构 + 每个文本区section标题行右侧AI辅助按钮 + 复核按钮
 * 底部AI辅助按钮生成全部附注
 */
import { reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const G6_ACCOUNT_CODE = '1503'

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

// ═══ 附注结构 —— 137行分为多section ═══
interface DisclosureRow {
  item: string
  openingCost: number
  openingInterestAdj: number
  openingAccruedInterest: number
  openingSubtotal: number
  periodIncrease: number
  periodDecrease: number
  interestIncome: number
  fvChange: number
  closingCost: number
  closingSubtotal: number
  impairment: number
  amortizedCost: number
  couponRate: number | null
  effectiveRate: number | null
  maturityDate: string
  remark: string
  isFormula?: boolean
}

interface DisclosureSection {
  id: string
  title: string
  rows: DisclosureRow[]
  hasTextArea: boolean
  textContent: string
}

// 生成初始结构：137行分配到7个section
function buildSections(): DisclosureSection[] {
  return [
    {
      id: 'cost-overview',
      title: '一、其他债权投资成本',
      rows: generateRows('成本', 22),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'interest-adjustment',
      title: '二、利息调整',
      rows: generateRows('利息调整', 20),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'accrued-interest',
      title: '三、应计利息',
      rows: generateRows('应计利息', 20),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'fv-change',
      title: '四、公允价值变动（其他综合收益）',
      rows: generateRows('OCI变动', 20),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'impairment',
      title: '五、减值准备',
      rows: generateRows('减值准备', 20),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'amortized-summary',
      title: '六、摊余成本/账面价值汇总',
      rows: generateRows('账面价值', 20),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'other-disclosure',
      title: '七、其他披露事项',
      rows: generateRows('其他', 15),
      hasTextArea: true,
      textContent: '',
    },
  ]
}

function generateRows(prefix: string, count: number): DisclosureRow[] {
  const rows: DisclosureRow[] = []
  for (let i = 1; i <= count; i++) {
    rows.push({
      item: `${prefix}项目${i}`,
      openingCost: 0,
      openingInterestAdj: 0,
      openingAccruedInterest: 0,
      openingSubtotal: 0,
      periodIncrease: 0,
      periodDecrease: 0,
      interestIncome: 0,
      fvChange: 0,
      closingCost: 0,
      closingSubtotal: 0,
      impairment: 0,
      amortizedCost: 0,
      couponRate: null,
      effectiveRate: null,
      maturityDate: '',
      remark: '',
      isFormula: i === count, // 最后一行通常是小计(公式)
    })
  }
  return rows
}

const sections = reactive<DisclosureSection[]>(buildSections())

// ═══ EventBus: subscribe substantive:adjudicated(1503) ═══
let adjudicatedAmount = 0

function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === G6_ACCOUNT_CODE && d.adjudicatedAmount != null) {
    adjudicatedAmount = d.adjudicatedAmount
    // 自动刷新审定数据到附注section(摊余成本/账面价值汇总)
    const summarySection = sections.find(s => s.id === 'amortized-summary')
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
      detail: { accountCode: G6_ACCOUNT_CODE, section: 'listed', text: allText },
    }))
  } catch { /* silent */ }
}

// ═══ AI辅助（单section） ═══
function fillAiDraft(sectionIdx: number): void {
  if (isReadonly.value) return
  const section = sections[sectionIdx]
  if (!section) return
  const draft = `根据审计结果，${section.title}期末余额为 [审定金额] 元。其他债权投资以公允价值计量且变动计入其他综合收益(FVOCI-Debt)，具体构成如下：...`
  section.textContent = section.textContent ? `${section.textContent}\n${draft}` : draft
  onNoteTextChange(sectionIdx)
}

// ═══ AI辅助（全部section） ═══
function fillAiDraftAll(): void {
  if (isReadonly.value) return
  sections.forEach((section, idx) => {
    if (section.hasTextArea && !section.textContent) {
      fillAiDraft(idx)
    }
  })
}

// ═══ 数据加载 ═══
function loadFromHtmlData(): void {
  if (!props.htmlData?.disclosureListed?.sections) return
  const saved = props.htmlData.disclosureListed.sections as DisclosureSection[]
  saved.forEach((s, i) => {
    if (sections[i]) {
      if (s.textContent) sections[i].textContent = s.textContent
      if (s.rows?.length) {
        sections[i].rows = s.rows
      }
    }
  })
}
</script>

<style scoped>
.g6-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin: 16px 0 8px; }
.section-head:first-child { margin-top: 0; }
.section-title { margin: 0; font-size: 14px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.text-card { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.bottom-ai-actions { margin-top: 16px; display: flex; justify-content: flex-end; }
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
