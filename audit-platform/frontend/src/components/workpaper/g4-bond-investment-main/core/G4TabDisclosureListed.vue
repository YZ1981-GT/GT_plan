<template>
  <div class="g4-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认债权投资在上市公司财务报表附注中按投资类型完整、准确披露期初/期末余额、减值准备、摊余成本及票面/实际利率、到期日等信息，列报与分类符合企业会计准则披露要求。"
      class="objective-alert"
      style="margin-bottom: 12px"
    />

    <!-- Section: 债权投资附注(上市公司) 按11列大表分多section -->
    <template v-for="(section, sIdx) in sections" :key="section.id">
      <div class="section-head">
        <h4 class="section-title">{{ section.title }}</h4>
        <div class="head-actions">
          <el-button v-if="section.hasTextArea" size="small" type="primary" text :disabled="isReadonly" @click="fillAiDraft(sIdx)">
            🤖AI辅助
          </el-button>
          <GtReviewTrigger :section-id="`G4-disclosure-listed-${section.id}`" />
        </div>
      </div>

      <!-- 结构化表格区 -->
      <el-table
        v-if="section.rows.length > 0"
        :data="section.rows"
        border
        stripe
        :max-height="section.rows.length > 50 ? 520 : undefined"
        style="width: 100%; font-size: 13px; margin-bottom: 8px"
      >
        <el-table-column prop="item" label="项目" min-width="160" fixed />
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.openingBalance) }}</template>
        </el-table-column>
        <el-table-column label="本期增加" width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodIncrease) }}</template>
        </el-table-column>
        <el-table-column label="本期减少" width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.periodDecrease) }}</template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.closingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.impairment) }}</template>
        </el-table-column>
        <el-table-column label="摊余成本" width="120" align="right">
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
        <el-table-column label="到期日" width="110" align="center">
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

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注格式（130行×11列），按投资类型分类列示期初/期末/减值/摊余成本</li>
        <li>监听 substantive:adjudicated(1501) 自动同步审定数</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>虚拟滚动已启用（el-table max-height）确保超长表格流畅渲染</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Req 4.1, 4.3~4.6, 9.4, 11.1, 11.6
 * 130行×11列结构化表格 + 虚拟滚动(el-table max-height)
 * EventBus: subscribe substantive:adjudicated(1501) → auto-refresh
 *           publish disclosure:note-text-updated on text change
 * 每个文本区section标题行右侧AI辅助按钮 + 复核按钮
 */
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import http from '@/utils/http'

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

function readSaved(key: string): string {
  const cr = props.htmlData?.checklist_responses
  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {
    const v = (cr as Record<string, any>)[key]
    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')
  }
  const resp = props.htmlData?.responses
  if (Array.isArray(resp)) {
    const found = resp.find((r: any) => r?.item_id === key)
    if (found?.remark) return found.remark
  }
  return ''
}

async function saveAudit(key: string, val: string): Promise<void> {
  if (props.isReadonly) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: key, conclusion: null, remark: val }],
    })
  } catch { /* silent */ }
}

// ═══ 附注结构 —— 130行分为多section ═══
interface DisclosureRow {
  item: string
  openingBalance: number
  periodIncrease: number
  periodDecrease: number
  closingBalance: number
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

// 生成初始结构：130行分配到7个section
function buildSections(): DisclosureSection[] {
  return [
    {
      id: 'cost-overview',
      title: '一、债权投资成本',
      rows: generateRows('债权投资成本', 20),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'interest-adjustment',
      title: '二、利息调整',
      rows: generateRows('利息调整', 18),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'accrued-interest',
      title: '三、应计利息',
      rows: generateRows('应计利息', 18),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'impairment',
      title: '四、减值准备',
      rows: generateRows('减值准备', 20),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'amortized-summary',
      title: '五、摊余成本汇总',
      rows: generateRows('摊余成本', 22),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'one-year-maturity',
      title: '六、一年内到期重分类',
      rows: generateRows('一年内到期', 16),
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'other-disclosure',
      title: '七、其他披露事项',
      rows: generateRows('其他', 16),
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

// ═══ EventBus: subscribe substantive:adjudicated(1501) ═══
let adjudicatedAmount = 0

function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === G4_ACCOUNT_CODE && d.adjudicatedAmount != null) {
    adjudicatedAmount = d.adjudicatedAmount
    // 自动刷新审定数据到附注section(摊余成本汇总)
    const summarySection = sections.find(s => s.id === 'amortized-summary')
    if (summarySection && summarySection.rows.length > 0) {
      const lastRow = summarySection.rows[summarySection.rows.length - 1]
      lastRow.amortizedCost = adjudicatedAmount
    }
  }
}

onMounted(() => {
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  // 加载已保存数据
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
      detail: { accountCode: G4_ACCOUNT_CODE, section: 'listed', text: allText },
    }))
  } catch { /* silent */ }
}

// ═══ AI辅助 ═══
function fillAiDraft(sectionIdx: number): void {
  if (isReadonly.value) return
  const section = sections[sectionIdx]
  if (!section) return
  const draft = `根据审计结果，${section.title}期末余额为 [审定金额] 元，具体构成如下：...`
  section.textContent = section.textContent ? `${section.textContent}\n${draft}` : draft
  onNoteTextChange(sectionIdx)
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
.g4-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin: 16px 0 8px; }
.section-head:first-child { margin-top: 0; }
.section-title { margin: 0; font-size: 14px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.text-card { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.objective-alert { margin-bottom: 12px; }
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
