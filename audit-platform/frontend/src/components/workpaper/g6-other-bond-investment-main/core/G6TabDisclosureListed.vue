<template>
  <div class="g6-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认其他债权投资(FVOCI-Debt)上市公司附注披露的完整性与准确性，成本/公允价值变动(OCI)/减值/摊余成本等列示与审定数勾稽一致，符合披露准则要求。"
      style="margin-bottom: 12px"
    />
    <!-- Section: 其他债权投资附注(上市公司) 137行×16列分多section -->
    <template v-for="(section, sIdx) in sections" :key="section.id">
      <div class="section-head">
        <h4 class="section-title">{{ section.title }}</h4>
        <div class="head-actions">
          <el-button
            v-if="section.hasTextArea"
            size="small"
            type="primary"
            text
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="fillAiDraft(sIdx)"
          >
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
      <el-button type="primary" size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="fillAiDraftAll">
        🤖 AI辅助生成全部附注
      </el-button>
    </div>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li><b>编制目的</b>：按上市公司附注格式列示其他债权投资（成本／公允价值变动(OCI)／减值／摊余成本等），与审定数勾稽。</li>
        <li><b>建议顺序</b>：先完成 G6-1 审定（及必要的 G6-4 回写）→ 打开本表核对各 section 金额 → 补充文字披露 → 再联动正式附注模块。</li>
        <li>G6-1 保存审定后会触发自动刷新（科目 1503）；若金额未更新，回到 G6-1 确认已保存并重新进入本表。</li>
        <li>按 section 核对：期初/期末余额、本期变动、OCI 公允价值变动、ECL 减值、摊余成本口径是否与 G6-1/G6-2/G6-3 一致。</li>
        <li>文字区可按 section 使用 AI 辅助初稿，须人工改写为项目事实与准则表述；重大项目应能索引到 G6-2。</li>
        <li>编辑保存后会联动附注模块文本；正式对外附注以附注模块为准，本表为披露工作底稿。</li>
        <li>FVOCI-Debt 双重计量：公允价值变动进 OCI，减值损失进损益；披露中勿混用两套口径。</li>
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
import { reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useG6MainAiGenerate } from '../../composables/useG6MainAiGenerate'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import { dispatchG6SaveItems } from '../../composables/g6CrossHelpers'

const G6_ACCOUNT_CODE = '1503'
const LISTED_TEXT_KEY = 'G6-disclosure-listed-text'
const LISTED_SECTIONS_KEY = 'G6-disclosure-listed-sections'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses?: Map<string, ChecklistResponse>
}>()

// ═══ 格式化金额 ═══
function fmtAmount(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const isReadonly = computed(() => props.isReadonly)
const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG6MainAiGenerate(wpIdRef)

function dispatchSave(itemId: string, val: string): void {
  if (props.isReadonly) return
  const item: ChecklistResponse = { item_id: itemId, conclusion: null, remark: val }
  try {
    dispatchG6SaveItems(props.wpId, [item])
  } catch { /* silent */ }
}

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
  loadListedContent()
})
onBeforeUnmount(() => {
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
})

watch(
  () => [
    props.allResponses?.get(LISTED_SECTIONS_KEY)?.remark ?? '',
    props.allResponses?.get(LISTED_TEXT_KEY)?.remark ?? '',
  ],
  (next, prev) => {
    if (!prev) return
    if (next[0] === prev[0] && next[1] === prev[1]) return
    loadListedContent()
  },
)

// ═══ EventBus: publish disclosure:note-text-updated + 持久化 ═══
function onNoteTextChange(_sectionIdx: number): void {
  const allText = sections
    .filter(s => s.hasTextArea && s.textContent)
    .map(s => `【${s.title}】\n${s.textContent}`)
    .join('\n\n')
  dispatchSave(LISTED_TEXT_KEY, allText)
  dispatchSave(
    LISTED_SECTIONS_KEY,
    JSON.stringify(
      sections
        .filter(s => s.hasTextArea)
        .map(s => ({ id: s.id, textContent: s.textContent || '' })),
    ),
  )
  try {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { accountCode: G6_ACCOUNT_CODE, section: 'listed', text: allText },
    }))
  } catch { /* silent */ }
}

// ═══ AI辅助（单section） ═══
async function fillAiDraft(sectionIdx: number): Promise<void> {
  if (isReadonly.value) return
  const section = sections[sectionIdx]
  if (!section) return
  const text = await generateAndConfirm(
    'disclosure-listed-note',
    section.textContent || '',
    { sectionTitle: section.title },
    'AI 附注披露',
  )
  if (text) {
    section.textContent = text
    onNoteTextChange(sectionIdx)
  }
}

// ═══ AI辅助（全部section） ═══
async function fillAiDraftAll(): Promise<void> {
  if (isReadonly.value) return
  const existing = sections
    .filter(s => s.hasTextArea && s.textContent)
    .map(s => `【${s.title}】\n${s.textContent}`)
    .join('\n\n')
  const text = await generateAndConfirm(
    'disclosure-text',
    existing,
    { format: 'listed' },
    'AI 全部附注',
  )
  if (!text) return
  // 填入第一个空文本区；若均已有内容则追加到末尾 section
  const emptyIdx = sections.findIndex(s => s.hasTextArea && !s.textContent)
  const targetIdx = emptyIdx >= 0 ? emptyIdx : sections.findIndex(s => s.hasTextArea)
  if (targetIdx < 0) return
  sections[targetIdx].textContent = text
  onNoteTextChange(targetIdx)
}

// ═══ 数据加载：checklist 结构化 → 标题文本块 → htmlData 渲染壳 ═══
function applyListedTextBlob(blob: string): void {
  if (!blob.trim()) return
  const re = /【([^】]+)】\n?([\s\S]*?)(?=【|$)/g
  let match: RegExpExecArray | null
  while ((match = re.exec(blob)) !== null) {
    const title = match[1].trim()
    const text = match[2].trim()
    const section = sections.find(s => s.title === title || s.title.includes(title) || title.includes(s.title))
    if (section) section.textContent = text
  }
}

function loadListedContent(): void {
  const sectionsRaw = props.allResponses?.get(LISTED_SECTIONS_KEY)?.remark
    || props.allResponses?.get(LISTED_SECTIONS_KEY)?.conclusion
  if (sectionsRaw) {
    try {
      const arr = JSON.parse(String(sectionsRaw))
      if (Array.isArray(arr)) {
        for (const item of arr) {
          const section = sections.find(s => s.id === item?.id)
          if (section && item?.textContent != null) {
            section.textContent = String(item.textContent)
          }
        }
        return
      }
    } catch { /* fall through */ }
  }

  const textBlob = props.allResponses?.get(LISTED_TEXT_KEY)?.remark
    || props.allResponses?.get(LISTED_TEXT_KEY)?.conclusion
  if (textBlob) {
    applyListedTextBlob(String(textBlob))
    return
  }

  loadFromHtmlData()
}

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
