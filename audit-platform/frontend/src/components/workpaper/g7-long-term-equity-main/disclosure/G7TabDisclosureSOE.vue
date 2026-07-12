<template>
  <div class="g7-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：按国企附注格式披露长期股权投资信息，在上市公司披露基础上增加国有资本保值增值率、对外投资决策程序合规性及境外投资信息，确认披露完整、准确并符合国资监管要求。
    </el-alert>

    <!-- 附注披露信息（国企）：355行×17列，全平台最长附注 -->
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
                :disabled="isReadonly"
                @click="fillAiDraft(sIdx)"
              >
                🤖AI辅助
              </el-button>
              <GtReviewTrigger :section-id="`G7-disclosure-soe-${section.id}`" />
            </div>
          </div>

          <!-- 结构化表格区（17列） -->
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
            <!-- Col 13: 其他综合收益 -->
            <el-table-column label="其他综合收益" width="120" align="right">
              <template #default="{ row }">{{ fmtAmount(row.oci) }}</template>
            </el-table-column>
            <!-- Col 14: 国有持股比例(SOE) -->
            <el-table-column label="国有持股比例" width="110" align="right">
              <template #default="{ row }">{{ fmtPercent(row.stateHoldingRatio) }}</template>
            </el-table-column>
            <!-- Col 15: 保值增值率(SOE) -->
            <el-table-column label="保值增值率" width="110" align="right">
              <template #default="{ row }">{{ fmtPercent(row.preservationRate) }}</template>
            </el-table-column>
            <!-- Col 16: 合规性标识(SOE) -->
            <el-table-column label="合规性" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.complianceFlag != null" :type="row.complianceFlag ? 'success' : 'danger'" size="small">
                  {{ row.complianceFlag ? '合规' : '不合规' }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <!-- Col 17: 备注 -->
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
        <el-button type="primary" size="small" :disabled="isReadonly" @click="fillAiDraftAll">
          🤖 AI辅助生成全部附注
        </el-button>
      </div>

      <!-- 编制提示 -->
      <details class="prep-hint">
        <summary>编制提示</summary>
        <ul>
          <li>国企附注格式（355行×17列），全平台最长附注，已启用分段懒加载</li>
          <li>8个section：在上市公司5节基础上增加 国有资本保值增值率/投资决策合规性/境外投资 3个国企专属section</li>
          <li>17列 = 上市13列 + 国有持股比例/保值增值率/合规性标识/境外相关 4列</li>
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
 * G7TabDisclosureSOE.vue — 附注披露信息（国企）
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/
 * Requirements: 4.2, 4.3, 6.3, 6.5, 6.6
 *
 * 355行×17列（全平台最长附注）
 * 8个section = 上市公司5节 + 国有资本保值增值率 + 投资决策合规性 + 境外投资
 * 分段懒加载(每段50行) + 滚动节流(requestAnimationFrame 16ms)
 * EventBus: subscribe substantive:adjudicated(1511) → auto-refresh
 *           publish disclosure:note-text-updated on text change
 * AI辅助按钮 + 复核按钮（每个section标题行右侧）
 */
import { reactive, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

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
interface DisclosureRowSOE {
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
  oci: number
  stateHoldingRatio: number | null
  preservationRate: number | null
  complianceFlag: boolean | null
  remark: string
  isFormula?: boolean
}

interface DisclosureSectionSOE {
  id: string
  title: string
  allRows: DisclosureRowSOE[]
  visibleRows: DisclosureRowSOE[]
  totalRows: number
  hasTextArea: boolean
  textContent: string
}

// ═══ 355行分配到8个section ═══
function buildSections(): DisclosureSectionSOE[] {
  const sectionDefs = [
    { id: 'cost-equity-summary', title: '（一）按成本法/权益法分类汇总', rowCount: 55 },
    { id: 'important-jv-associate', title: '（二）重要合营/联营企业信息', rowCount: 60 },
    { id: 'unconsolidated-entity', title: '（三）不纳入合并范围的结构化主体', rowCount: 35 },
    { id: 'over-5pct-investee', title: '（四）持股5%以上被投资单位信息', rowCount: 50 },
    { id: 'investment-restriction', title: '（五）对外投资限制性条件', rowCount: 30 },
    { id: 'state-capital-preservation', title: '（六）国有资本保值增值率', rowCount: 45 },
    { id: 'investment-decision-compliance', title: '（七）对外投资决策程序合规性', rowCount: 40 },
    { id: 'overseas-investment', title: '（八）境外投资信息', rowCount: 40 },
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

function generateRows(sectionId: string, count: number): DisclosureRowSOE[] {
  const rows: DisclosureRowSOE[] = []
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
      oci: 0,
      stateHoldingRatio: null,
      preservationRate: null,
      complianceFlag: null,
      remark: '',
      isFormula: i === count,
    })
  }
  return rows
}

const sections = reactive<DisclosureSectionSOE[]>(buildSections())

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
  // 当滚动到底部 200px 范围内时，加载所有未满的section的下一段
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
    if (res?.data?.data?.html_data?.disclosureSOE) {
      loadFromHtmlData(res.data.data.html_data.disclosureSOE)
    }
  } catch {
    // 静默：非纯被动监听，mounted时主动拉取，失败不阻塞
  }
}

onMounted(() => {
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  if (props.htmlData) {
    loadFromHtmlData(props.htmlData.disclosureSOE)
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
      detail: { accountCode: G7_ACCOUNT_CODE, section: 'soe', text: allText },
    }))
  } catch { /* silent */ }
}

// ═══ AI辅助（单section） ═══
function fillAiDraft(sectionIdx: number): void {
  if (isReadonly.value) return
  const section = sections[sectionIdx]
  if (!section) return

  // 按section id生成不同的AI草稿
  const draftMap: Record<string, string> = {
    'cost-equity-summary': '根据审计结果，长期股权投资按成本法核算的子公司投资期末余额为 [金额] 元；按权益法核算的合营企业投资期末余额为 [金额] 元，联营企业投资期末余额为 [金额] 元。',
    'important-jv-associate': '重要合营/联营企业基本信息及财务数据如下。本期权益法确认投资收益合计 [金额] 元，其他综合收益份额 [金额] 元。',
    'unconsolidated-entity': '公司不纳入合并范围的结构化主体包括 [主体名称]。未纳入合并的原因为 [原因说明]。',
    'over-5pct-investee': '持股比例5%以上的被投资单位信息如下，主要集中于 [行业] 领域。',
    'investment-restriction': '对外投资存在以下限制性条件：[条件描述]。涉及质押/冻结的长期股权投资账面价值为 [金额] 元。',
    'state-capital-preservation': '本年度国有资本保值增值率为 [比率]%。期初国有资本 [金额] 元，期末国有资本 [金额] 元，保值增值额 [金额] 元。',
    'investment-decision-compliance': '本年度对外投资决策程序执行情况：共计 [数量] 项投资决策，其中经股东会/董事会审议 [数量] 项，符合"三重一大"决策程序要求。',
    'overseas-investment': '境外投资基本情况：共持有 [数量] 家境外子公司/联营企业股权，分布于 [国家/地区]，境外投资总额 [金额] 元。',
  }

  const draft = draftMap[section.id] || `${section.title}相关信息如下：[待填写]`
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
function loadFromHtmlData(data: any): void {
  if (!data?.sections) return
  const saved = data.sections as DisclosureSectionSOE[]
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
.g7-disclosure-soe {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.audit-objective {
  margin-bottom: 12px;
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
