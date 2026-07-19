<template>
  <div class="g7-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：按上市公司附注格式披露长期股权投资的分类汇总、重要合营/联营企业信息、结构化主体、持股5%以上被投资单位及对外投资限制性条件，确认披露完整、准确并与审定数一致。
    </el-alert>

    <!-- 附注披露信息（上市公司）：253行×13列，虚拟滚动 -->
    <el-skeleton v-if="!htmlData" :rows="8" animated />
    <template v-else>
      <!-- 虚拟滚动容器：max-height + 分段懒加载 -->
      <div
        ref="scrollContainerRef"
        class="virtual-scroll-container"
        @scroll="onScrollThrottled"
      >
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
                AI辅助
              </el-button>
              <GtReviewTrigger :section-id="`G7-disclosure-listed-${section.id}`" />
            </div>
          </div>

          <!-- 结构化表格区（13列） -->
          <el-table
            v-if="section.visibleRows.length > 0"
            :data="section.visibleRows"
            border
            stripe
            :max-height="section.visibleRows.length > 30 ? 520 : undefined"
            style="width: 100%; font-size: 13px; margin-bottom: 8px"
          >
            <!-- Col 1: 项目 -->
            <el-table-column prop="item" label="项目" min-width="180" fixed />
            <!-- Col 2: 被投资单位 -->
            <el-table-column prop="investeeName" label="被投资单位" min-width="140" />
            <!-- Col 3: 控制类型 -->
            <el-table-column prop="controlType" label="控制类型" width="100" />
            <!-- Col 4: 持股比例 -->
            <el-table-column label="持股比例" width="100" align="right">
              <template #default="{ row }">{{ fmtPercent(row.holdingRatio) }}</template>
            </el-table-column>
            <!-- Col 5: 计量方法 -->
            <el-table-column prop="measurementMethod" label="计量方法" width="90" />
            <!-- Col 6: 期初余额 -->
            <el-table-column label="期初余额" width="130" align="right">
              <template #default="{ row }">{{ fmtAmount(row.openingBalance) }}</template>
            </el-table-column>
            <!-- Col 7: 本期增加 -->
            <el-table-column label="本期增加" width="130" align="right">
              <template #default="{ row }">{{ fmtAmount(row.periodIncrease) }}</template>
            </el-table-column>
            <!-- Col 8: 本期减少 -->
            <el-table-column label="本期减少" width="130" align="right">
              <template #default="{ row }">{{ fmtAmount(row.periodDecrease) }}</template>
            </el-table-column>
            <!-- Col 9: 期末余额 -->
            <el-table-column label="期末余额" width="130" align="right">
              <template #default="{ row }">
                <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.closingBalance) }}</span>
              </template>
            </el-table-column>
            <!-- Col 10: 减值准备 -->
            <el-table-column label="减值准备" width="120" align="right">
              <template #default="{ row }">{{ fmtAmount(row.impairment) }}</template>
            </el-table-column>
            <!-- Col 11: 账面价值 -->
            <el-table-column label="账面价值" width="130" align="right">
              <template #default="{ row }">
                <span :class="{ 'formula-cell': row.isFormula }">{{ fmtAmount(row.bookValue) }}</span>
              </template>
            </el-table-column>
            <!-- Col 12: 投资收益 -->
            <el-table-column label="投资收益" width="120" align="right">
              <template #default="{ row }">{{ fmtAmount(row.investmentIncome) }}</template>
            </el-table-column>
            <!-- Col 13: 备注 -->
            <el-table-column prop="remark" label="备注" min-width="120">
              <template #default="{ row }">{{ row.remark || '-' }}</template>
            </el-table-column>
          </el-table>

          <!-- 懒加载占位：显示还有多少行未加载 -->
          <div v-if="section.totalRows > section.visibleRows.length" class="lazy-load-hint">
            <el-button size="small" text type="info" @click="loadMoreRows(sIdx)">
              加载更多（剩余 {{ section.totalRows - section.visibleRows.length }} 行）
            </el-button>
          </div>

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
      </div>

      <!-- 底部AI辅助按钮 -->
      <div class="bottom-ai-actions">
        <el-button type="primary" size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="fillAiDraftAll">
          AI辅助生成全部附注
        </el-button>
      </div>

      <!-- 编制提示 -->
      <details class="prep-hint">
        <summary>编制提示</summary>
        <ul>
          <li>上市公司附注格式（253行×13列），已启用分段懒加载</li>
          <li>5个section：成本法/权益法分类汇总 + 重要合营联营 + 结构化主体 + 持股5%以上 + 限制性条件</li>
          <li>13列：项目|被投资单位|控制类型|持股比例|计量方法|期初余额|本期增加|本期减少|期末余额|减值准备|账面价值|投资收益|备注</li>
          <li>分段懒加载：每段50行，滚动到底部自动加载下一段</li>
          <li>监听 substantive:adjudicated(1511) 自动同步审定数（按控制类型分组）</li>
          <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
          <li>虚拟滚动 + 滚动节流(requestAnimationFrame 16ms)</li>
        </ul>
      </details>

    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/
 * Requirements: 4.1, 4.3, 6.3, 6.5, 6.6
 *
 * 253行×13列（上市公司附注）
 * 5个section:
 *   (一) 按成本法/权益法分类汇总 (~60行)
 *   (二) 重要合营/联营企业信息 (~70行)
 *   (三) 不纳入合并范围的结构化主体 (~40行)
 *   (四) 持股5%以上被投资单位信息 (~50行)
 *   (五) 对外投资限制性条件 (~33行)
 *
 * 分段懒加载(每段50行) + 滚动节流(requestAnimationFrame 16ms)
 * EventBus: subscribe substantive:adjudicated(1511) → auto-refresh
 *           publish disclosure:note-text-updated on text change
 * AI辅助按钮 + 复核按钮（每个section标题行右侧）
 */
import { reactive, ref, computed, onMounted, onBeforeUnmount, toRef } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { api } from '@/services/apiProxy'
import { useG7MainAiGenerate } from '../../composables/useG7MainAiGenerate'

const G7_ACCOUNT_CODE = '1511'
/** 每段懒加载行数 */
const LAZY_CHUNK_SIZE = 50

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const scrollContainerRef = ref<HTMLDivElement | null>(null)
const wpIdRef = toRef(props, 'wpId')
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useG7MainAiGenerate(wpIdRef)

// ═══ 格式化 ═══
function fmtAmount(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(v: number | null | undefined): string {
  if (v == null) return '-'
  return `${(v * 100).toFixed(2)}%`
}

const isReadonly = computed(() => props.isReadonly)

// ═══ 数据模型 ═══
interface DisclosureRowListed {
  item: string
  investeeName: string
  controlType: string
  holdingRatio: number | null
  measurementMethod: string
  openingBalance: number
  periodIncrease: number
  periodDecrease: number
  closingBalance: number
  impairment: number
  bookValue: number
  investmentIncome: number
  remark: string
  isFormula?: boolean
}

interface DisclosureSectionListed {
  id: string
  title: string
  allRows: DisclosureRowListed[]
  visibleRows: DisclosureRowListed[]
  totalRows: number
  hasTextArea: boolean
  textContent: string
}

// ═══ 253行分配到5个section ═══
function buildSections(): DisclosureSectionListed[] {
  const sectionDefs = [
    { id: 'cost-equity-summary', title: '（一）按成本法/权益法分类汇总', rowCount: 60 },
    { id: 'important-jv-associate', title: '（二）重要合营/联营企业信息', rowCount: 70 },
    { id: 'unconsolidated-entity', title: '（三）不纳入合并范围的结构化主体', rowCount: 40 },
    { id: 'over-5pct-investee', title: '（四）持股5%以上被投资单位信息', rowCount: 50 },
    { id: 'investment-restriction', title: '（五）对外投资限制性条件', rowCount: 33 },
  ]

  return sectionDefs.map(def => {
    const allRows = generateRows(def.id, def.rowCount)
    const visibleRows = allRows.slice(0, LAZY_CHUNK_SIZE)
    return {
      id: def.id,
      title: def.title,
      allRows,
      visibleRows,
      totalRows: def.rowCount,
      hasTextArea: true,
      textContent: '',
    }
  })
}

function generateRows(sectionId: string, count: number): DisclosureRowListed[] {
  const rows: DisclosureRowListed[] = []
  for (let i = 1; i <= count; i++) {
    rows.push({
      item: `${sectionId}-${i}`,
      investeeName: '',
      controlType: '',
      holdingRatio: null,
      measurementMethod: '',
      openingBalance: 0,
      periodIncrease: 0,
      periodDecrease: 0,
      closingBalance: 0,
      impairment: 0,
      bookValue: 0,
      investmentIncome: 0,
      remark: '',
      isFormula: i === count,
    })
  }
  return rows
}

const sections = reactive<DisclosureSectionListed[]>(buildSections())

// ═══ 分段懒加载：每段50行 ═══
function loadMoreRows(sectionIdx: number): void {
  const section = sections[sectionIdx]
  if (!section) return
  const currentLen = section.visibleRows.length
  const nextChunk = section.allRows.slice(currentLen, currentLen + LAZY_CHUNK_SIZE)
  section.visibleRows.push(...nextChunk)
}

// ═══ 滚动节流(requestAnimationFrame 16ms) ═══
let rafPending = false

function onScrollThrottled(): void {
  if (rafPending) return
  rafPending = true
  requestAnimationFrame(() => {
    rafPending = false
    checkLazyLoad()
  })
}

function checkLazyLoad(): void {
  const container = scrollContainerRef.value
  if (!container) return
  const { scrollTop, scrollHeight, clientHeight } = container
  // 当滚动到底部 200px 范围内时，加载未满section的下一段
  if (scrollHeight - scrollTop - clientHeight < 200) {
    for (let i = 0; i < sections.length; i++) {
      if (sections[i].visibleRows.length < sections[i].totalRows) {
        loadMoreRows(i)
        break // 每次只加载一个section的下一段，避免一次性加载太多
      }
    }
  }
}

// ═══ EventBus: subscribe substantive:adjudicated(1511) ═══
interface AdjudicatedPayload {
  accountCode: string
  adjudicatedAmount: number
  byControlType?: {
    subsidiary: number
    jointVenture: number
    associate: number
  }
}

function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<AdjudicatedPayload>).detail
  if (d?.accountCode !== G7_ACCOUNT_CODE) return
  // 自动刷新审定数据到分类汇总section
  const summarySection = sections.find(s => s.id === 'cost-equity-summary')
  if (summarySection && summarySection.visibleRows.length > 0) {
    const lastRow = summarySection.visibleRows[summarySection.visibleRows.length - 1]
    lastRow.closingBalance = d.adjudicatedAmount
    lastRow.bookValue = d.adjudicatedAmount - (lastRow.impairment || 0)
  }
  // 按控制类型分发到子公司/合营联营行
  if (d.byControlType) {
    updateByControlType(d.byControlType)
  }
}

function updateByControlType(byType: { subsidiary: number; jointVenture: number; associate: number }): void {
  const summarySection = sections.find(s => s.id === 'cost-equity-summary')
  if (!summarySection) return
  // 简化：前3行分别对应子公司/合营/联营合计
  if (summarySection.visibleRows.length >= 3) {
    summarySection.visibleRows[0].closingBalance = byType.subsidiary
    summarySection.visibleRows[0].measurementMethod = '成本法'
    summarySection.visibleRows[1].closingBalance = byType.jointVenture
    summarySection.visibleRows[1].measurementMethod = '权益法'
    summarySection.visibleRows[2].closingBalance = byType.associate
    summarySection.visibleRows[2].measurementMethod = '权益法'
  }
}

// ═══ mounted时主动拉取最新审定数 ═══
async function fetchLatestAdjudicated(): Promise<void> {
  try {
    const res = await (window as any).__httpClient?.get?.(
      `/api/workpapers/${props.wpId}/render-config`
    )
    if (res?.data?.data?.html_data?.disclosureListed) {
      loadFromHtmlData(res.data.data.html_data.disclosureListed)
    }
  } catch {
    // 静默：非纯被动监听，mounted时主动拉取，失败不阻塞
  }
}

onMounted(() => {
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  loadAuditResponses()
  if (props.htmlData) {
    loadFromHtmlData(props.htmlData.disclosureListed)
  } else {
    fetchLatestAdjudicated()
  }
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
      detail: { accountCode: G7_ACCOUNT_CODE, section: 'listed', text: allText },
    }))
  } catch { /* silent */ }
}

// ═══ AI辅助（单section）—— 比照 F2：走 g7-main/ai/disclosure-text ═══
async function fillAiDraft(sectionIdx: number): Promise<void> {
  if (isReadonly.value) return
  const section = sections[sectionIdx]
  if (!section) return

  const text = await generateAndConfirm(
    'disclosure-text',
    section.textContent || '',
    {
      sectionId: section.id,
      sectionTitle: section.title,
      disclosureType: 'listed',
      accountCode: G7_ACCOUNT_CODE,
    },
    `AI 生成：${section.title}`,
  )
  if (!text) return
  section.textContent = text
  onNoteTextChange(sectionIdx)
}

// ═══ AI辅助（全部section） ═══
async function fillAiDraftAll(): Promise<void> {
  if (isReadonly.value) return
  for (let idx = 0; idx < sections.length; idx++) {
    const section = sections[idx]
    if (section.hasTextArea && !section.textContent) {
      await fillAiDraft(idx)
    }
  }
}

// ═══ 数据加载 ═══
function loadFromHtmlData(data: any): void {
  if (!data?.sections) return
  const saved = data.sections as DisclosureSectionListed[]
  saved.forEach((s, i) => {
    if (sections[i]) {
      if (s.textContent) sections[i].textContent = s.textContent
      if (s.allRows?.length) {
        sections[i].allRows = s.allRows
        sections[i].totalRows = s.allRows.length
        // 懒加载：初始只展示前50行
        sections[i].visibleRows = s.allRows.slice(0, LAZY_CHUNK_SIZE)
      }
    }
  })
}
</script>

<style scoped>
.g7-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.audit-objective {
  margin-bottom: 12px;
}

  margin-top: 12px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 500;
}

.virtual-scroll-container {
  max-height: 720px;
  overflow-y: auto;
  padding-right: 4px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 16px 0 8px;
  position: sticky;
  top: 0;
  background: #fff;
  z-index: 5;
  padding: 4px 0;
}

.section-head:first-child {
  margin-top: 0;
}

.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.text-card {
  margin-bottom: 12px;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.lazy-load-hint {
  text-align: center;
  padding: 8px 0;
  color: #909399;
  font-size: 12px;
}

.bottom-ai-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.prep-hint {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}

.prep-hint summary {
  cursor: pointer;
}

.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
