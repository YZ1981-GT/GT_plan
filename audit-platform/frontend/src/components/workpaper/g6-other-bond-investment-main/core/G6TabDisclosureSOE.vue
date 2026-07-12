<template>
  <div class="g6-disclosure-soe">
    <!-- Section: 其他债权投资附注(国企) 69行×6列分多section -->
    <template v-for="(section, sIdx) in sections" :key="section.id">
      <div class="section-head">
        <h4 class="section-title">{{ section.title }}</h4>
        <div class="head-actions">
          <el-button v-if="section.hasTextArea" size="small" type="primary" text :disabled="isReadonly" @click="fillAiDraft(sIdx)">
            🤖AI辅助
          </el-button>
          <GtReviewTrigger :section-id="`G6-disclosure-soe-${section.id}`" />
        </div>
      </div>

      <!-- 结构化表格区（虚拟滚动 max-height） -->
      <el-table
        v-if="section.rows.length > 0"
        :data="section.rows"
        border
        stripe
        :max-height="section.rows.length > 25 ? 480 : undefined"
        style="width: 100%; font-size: 13px; margin-bottom: 8px"
      >
        <el-table-column prop="item" label="项目" min-width="200" fixed />
        <el-table-column label="期初余额" width="140" align="right">
          <template #default="{ row }">{{ fmtAmount(row.openingBalance) }}</template>
        </el-table-column>
        <el-table-column label="本期增加" width="140" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodIncrease) }}</template>
        </el-table-column>
        <el-table-column label="本期减少" width="140" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodDecrease) }}</template>
        </el-table-column>
        <el-table-column label="期末余额" width="140" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.closingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
      </el-table>

      <!-- 文本区 -->
      <el-card v-if="section.hasTextArea" shadow="never" class="text-card">
        <el-input
          v-model="section.textContent"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 16 }"
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
        <li>国企附注格式（69行×6列），按分类列示期初/增减/期末余额</li>
        <li>监听 substantive:adjudicated(1503) 自动同步审定数</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>虚拟滚动已启用（el-table max-height）确保流畅渲染</li>
        <li>国企附注较上市简化，聚焦余额变动披露</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabDisclosureSOE.vue — 附注披露信息（国企）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-main/ Task 7.3
 * Requirements: 4.2, 4.3, 7.5, 7.6
 *
 * 69行×6列结构化表格 + 虚拟滚动(el-table max-height)
 * EventBus: subscribe substantive:adjudicated(1503) → auto-refresh
 *           publish disclosure:note-text-updated on text change
 * 多section结构 + 每个文本区section标题行右侧AI辅助按钮 + 复核按钮
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

// ═══ 附注结构 —— 69行分为多section ═══
interface DisclosureRow {
  item: string
  openingBalance: number
  periodIncrease: number
  periodDecrease: number
  closingBalance: number
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

// 生成初始结构：69行分配到5个section
function buildSections(): DisclosureSection[] {
  return [
    {
      id: 'balance-overview',
      title: '一、其他债权投资余额',
      rows: generateRows('余额', 16),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'impairment-provision',
      title: '二、减值准备',
      rows: generateRows('减值', 14),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'fv-oci-change',
      title: '三、公允价值变动（其他综合收益累计）',
      rows: generateRows('OCI累计', 14),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'maturity-analysis',
      title: '四、期限分析',
      rows: generateRows('期限', 13),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'other-info',
      title: '五、其他信息',
      rows: generateRows('其他', 12),
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
      openingBalance: 0,
      periodIncrease: 0,
      periodDecrease: 0,
      closingBalance: 0,
      remark: '',
      isFormula: i === count,
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
    // 自动刷新审定数据到附注section(余额汇总)
    const balanceSection = sections.find(s => s.id === 'balance-overview')
    if (balanceSection && balanceSection.rows.length > 0) {
      const lastRow = balanceSection.rows[balanceSection.rows.length - 1]
      lastRow.closingBalance = adjudicatedAmount
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
      detail: { accountCode: G6_ACCOUNT_CODE, section: 'soe', text: allText },
    }))
  } catch { /* silent */ }
}

// ═══ AI辅助（单section） ═══
function fillAiDraft(sectionIdx: number): void {
  if (isReadonly.value) return
  const section = sections[sectionIdx]
  if (!section) return
  const draft = `根据审计结果，${section.title}期末余额为 [审定金额] 元。其他债权投资(FVOCI-Debt)按公允价值计量且变动计入其他综合收益，具体情况如下：...`
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
  if (!props.htmlData?.disclosureSOE?.sections) return
  const saved = props.htmlData.disclosureSOE.sections as DisclosureSection[]
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
.g6-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
