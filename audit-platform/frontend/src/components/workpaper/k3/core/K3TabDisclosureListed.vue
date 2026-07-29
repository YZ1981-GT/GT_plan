<template>
  <div class="k3-disclosure-listed">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 按性质分类披露（保证金/借款/往来等）</div>
        <div class="guide-step"><span class="step-num">②</span> 按账龄分析披露（1年内/1-2年/2-3年/3年以上）</div>
        <div class="guide-step"><span class="step-num">③</span> 前五名其他应付款明细</div>
        <div class="guide-step"><span class="step-num">④</span> 自动从K3-1审定表取数 + AI辅助文字说明</div>
      </div>
    </div>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS37 其他应付款附注披露要求（上市公司）</div>
      <div class="methodology-content">
        按《企业会计准则第37号——金融工具列报》及上市公司年报格式，其他应付款应披露：
        按款项性质列示期末余额和期初余额；按账龄分析列示；前五名其他应付款明细（单位名称/性质/期末余额/账龄/占比）；
        重要的长期未支付款项的原因及估计支付时间。负债类科目关注完整性认定。
      </div>
    </div>

    <div class="head-actions" style="margin-bottom:12px;text-align:right;">
      <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
    </div>

    <!-- 多section卡片 -->
    <template v-for="(section, sIdx) in sections" :key="section.id">
      <el-card shadow="never" class="disclosure-card">
        <template #header>
          <div class="section-title-row">
            <span class="section-title">{{ section.title }}</span>
            <div class="title-actions">
              <el-button v-if="section.hasTextArea" size="small" type="primary" link :disabled="isReadonly" @click="handleAiGenerate(sIdx)">
                <el-icon><MagicStick /></el-icon> AI生成
              </el-button>
              <el-button size="small" type="default" link @click="handleReview(`disc-listed-${section.id}`)">💬</el-button>
            </div>
          </div>
        </template>

        <!-- 结构化表格区 -->
        <el-table
          v-if="section.rows.length > 0"
          :data="section.rows"
          border
          stripe
          size="small"
          :max-height="section.rows.length > 30 ? 480 : undefined"
          class="disclosure-table"
        >
          <el-table-column prop="item" label="项目" min-width="160" fixed />
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly && !row.isAutoFilled">
                <el-input-number :model-value="row.endBalance" :controls="false" size="small" @change="(v: number) => handleCellEdit(sIdx, row.rowIdx, 'endBalance', v)" />
              </template>
              <span v-else :class="{ 'formula-cell': row.isFormula, 'auto-fill': row.isAutoFilled }">{{ fmtAmt(row.endBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="120" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly && !row.isAutoFilled">
                <el-input-number :model-value="row.beginBalance" :controls="false" size="small" @change="(v: number) => handleCellEdit(sIdx, row.rowIdx, 'beginBalance', v)" />
              </template>
              <span v-else :class="{ 'auto-fill': row.isAutoFilled }">{{ fmtAmt(row.beginBalance) }}</span>
            </template>
          </el-table-column>
          <!-- 按账龄section显示动态账龄列（from useAgingConfig） -->
          <template v-if="section.hasAgingColumns">
            <el-table-column
              v-for="band in agingBands"
              :key="band.key"
              :label="band.label"
              width="100"
              align="right"
            >
              <template #default="{ row }">
                <template v-if="!isReadonly && !row.isAutoFilled">
                  <el-input-number :model-value="row.agingData?.[band.key] ?? 0" :controls="false" size="small" @change="(v: number) => handleAgingCellEdit(sIdx, row.rowIdx, band.key, v)" />
                </template>
                <span v-else :class="{ 'over3y-highlight': band.key !== 'within1' && band.key !== 'y1to2' && band.key !== 'y2to3' && (row.agingData?.[band.key] || 0) > 0 }">{{ fmtAmt(row.agingData?.[band.key]) }}</span>
              </template>
            </el-table-column>
          </template>
          <!-- 按性质section显示占比列 -->
          <el-table-column v-if="section.hasProportion" label="占比(%)" width="90" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="占比=本项/合计">{{ row.proportion != null ? row.proportion.toFixed(2) : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => handleCellEdit(sIdx, row.rowIdx, 'remark', v)" />
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- 文字说明区 -->
        <template v-if="section.hasTextArea">
          <el-divider v-if="section.rows.length > 0" content-position="left">文字说明</el-divider>
          <el-input
            v-model="section.textContent"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 12 }"
            :disabled="isReadonly"
            :placeholder="`请填写${section.title}的文字说明...`"
            @change="handleNoteTextChange(sIdx)"
          />
        </template>
      </el-card>
    </template>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注格式（约45行×15列），按性质/账龄分类披露</li>
        <li>监听 substantive:adjudicated(2241) 自动同步审定数据（浅蓝色=跨sheet自动取数）</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>负债类科目关注完整性认定：3年以上未支付款项需说明原因</li>
        <li>前五名其他应付款需从K3-2明细表自动取前五大金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabDisclosureListed.vue — 附注披露信息（上市公司）45×15
 *
 * Spec: k3-other-payables Task 4.6
 * Requirements: 8.1
 *
 * 45行×15列结构化表格，包含：
 * - 按性质分类披露（保证金/借款/往来款等）
 * - 按账龄分析披露（1年内/1-2年/2-3年/3年以上）
 * - 前五名其他应付款
 * - 重要长期未支付款项说明
 *
 * EventBus: subscribe 'substantive:adjudicated' → auto-refresh
 *           publish 'disclosure:note-text-updated' on text change
 */
import { reactive, ref, computed, inject, onMounted, onBeforeUnmount, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useAgingConfig, type AgingBand } from '@/composables/useAgingConfig'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildK3SyncPayload } from '../../composables/k3NoteSectionMap'

const K3_ACCOUNT_CODE = '2241'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// 动态账龄段（与K3-1/K3-2共享同一项目配置）
const { segments: agingSegments, bands: agingBands } = useAgingConfig(toRef(props, 'projectId'), 'K3')

// ═══ 数据模型 ═══
interface DisclosureRow {
  rowIdx: number
  item: string
  endBalance: number
  beginBalance: number
  /** 动态账龄数据 keyed by segment key (e.g. within1/y1to2/y2to3/over3/y3to4/y4to5/over5) */
  agingData: Record<string, number>
  proportion: number | null
  remark: string
  isFormula?: boolean
  isAutoFilled?: boolean
}

interface DisclosureSection {
  id: string
  title: string
  rows: DisclosureRow[]
  hasTextArea: boolean
  hasAgingColumns: boolean
  hasProportion: boolean
  textContent: string
}

// ═══ 构建45行分配到5个section ═══
function makeRow(item: string, idx: number, opts?: Partial<DisclosureRow>): DisclosureRow {
  return {
    rowIdx: idx, item, endBalance: 0, beginBalance: 0,
    agingData: {},
    proportion: null, remark: '',
    ...opts,
  }
}

function buildSections(): DisclosureSection[] {
  // (一) 按性质分类
  const natureItems = ['保证金及押金', '应付暂收款', '代收代付款', '借款', '应付赔偿款', '应付租金', '其他', '合计']
  const natureRows = natureItems.map((item, i) => makeRow(item, i, { isFormula: item === '合计' }))

  // (二) 按账龄分析
  const agingItems = ['1年以内', '1至2年', '2至3年', '3年以上', '合计']
  const agingRows = agingItems.map((item, i) => makeRow(item, i, { isFormula: item === '合计' }))

  // (三) 前五名
  const topFiveRows: DisclosureRow[] = Array.from({ length: 5 }, (_, i) => makeRow(`第${i + 1}名`, i))
  topFiveRows.push(makeRow('小计', 5, { isFormula: true }))

  // (四) 重要长期未支付款项
  const longTermItems = ['项目1', '项目2', '项目3', '项目4', '项目5', '小计']
  const longTermRows = longTermItems.map((item, i) => makeRow(item, i, { isFormula: item === '小计' }))

  return [
    { id: 'nature', title: '（一）按款项性质分类', rows: natureRows, hasTextArea: true, hasAgingColumns: false, hasProportion: true, textContent: '' },
    { id: 'aging', title: '（二）按账龄分析', rows: agingRows, hasTextArea: true, hasAgingColumns: true, hasProportion: true, textContent: '' },
    { id: 'top-five', title: '（三）期末余额前五名的其他应付款', rows: topFiveRows, hasTextArea: true, hasAgingColumns: false, hasProportion: true, textContent: '' },
    { id: 'long-term', title: '（四）重要的长期未支付款项', rows: longTermRows, hasTextArea: true, hasAgingColumns: false, hasProportion: false, textContent: '' },
    { id: 'other', title: '（五）其他披露事项', rows: [], hasTextArea: true, hasAgingColumns: false, hasProportion: false, textContent: '' },
  ]
}

const sections = reactive<DisclosureSection[]>(buildSections())

// ═══ 自动取数 from allResponses ═══
function applyAutoFill(): void {
  const endBal = getResponseNumber('K3-1-payable-end')
  const beginBal = getResponseNumber('K3-1-payable-begin')

  // 按性质section的合计行自动填充
  const natureSection = sections.find(s => s.id === 'nature')
  if (natureSection) {
    const totalRow = natureSection.rows.find(r => r.item === '合计')
    if (totalRow) {
      totalRow.endBalance = endBal
      totalRow.beginBalance = beginBal
      totalRow.isAutoFilled = true
    }
  }

  // 按账龄section合计行自动填充
  const agingSection = sections.find(s => s.id === 'aging')
  if (agingSection) {
    const totalRow = agingSection.rows.find(r => r.item === '合计')
    if (totalRow) {
      totalRow.endBalance = endBal
      totalRow.beginBalance = beginBal
      totalRow.isAutoFilled = true
    }
  }

  recalcProportions()
}

function getResponseNumber(key: string): number {
  const item = props.allResponses.get(key)
  if (!item) return 0
  const val = item.value ?? item
  return typeof val === 'number' ? val : parseFloat(val) || 0
}

function recalcProportions(): void {
  for (const section of sections) {
    if (!section.hasProportion) continue
    const totalRow = section.rows.find(r => r.isFormula)
    const total = totalRow?.endBalance || 0
    for (const row of section.rows) {
      if (!row.isFormula && total > 0) {
        row.proportion = (row.endBalance / total) * 100
      } else if (!row.isFormula) {
        row.proportion = null
      }
    }
  }
}

// ═══ EventBus: subscribe 'substantive:adjudicated' ═══
function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K3_ACCOUNT_CODE || payload.wpCode === 'K3') {
    applyAutoFill()
  }
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  loadSavedData()
  applyAutoFill()
})

onBeforeUnmount(() => {
  autoSync.cancelPending()
  eventBus.off('substantive:adjudicated', handleAdjudicated)
})

// ═══ 单元格编辑 ═══
function handleCellEdit(sIdx: number, rowIdx: number, field: string, value: any): void {
  const section = sections[sIdx]
  if (!section) return
  const row = section.rows[rowIdx]
  if (!row) return
  ;(row as any)[field] = value ?? 0
  recalcProportions()
  persistSection(sIdx)
}

/** 动态账龄单元格编辑（agingData keyed） */
function handleAgingCellEdit(sIdx: number, rowIdx: number, segKey: string, value: number): void {
  const section = sections[sIdx]
  if (!section) return
  const row = section.rows[rowIdx]
  if (!row) return
  if (!row.agingData) row.agingData = {}
  row.agingData[segKey] = value ?? 0
  persistSection(sIdx)
}

// ═══ 文本变化 → publish EventBus ═══
function handleNoteTextChange(sIdx: number): void {
  persistSection(sIdx)
  publishNoteText()
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function publishNoteText(): void {
  const allText = sections
    .filter(s => s.hasTextArea && s.textContent)
    .map(s => `【${s.title}】\n${s.textContent}`)
    .join('\n\n')
  try {
    eventBus.emit('disclosure:note-text-updated', {
      accountCode: K3_ACCOUNT_CODE,
      section: 'listed',
      text: allText,
    })
  } catch { /* silent */ }
}

// ═══ AI辅助 ═══
async function handleAiGenerate(sIdx: number): Promise<void> {
  const section = sections[sIdx]
  if (!section) return

  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: `请生成其他应付款附注（上市公司格式）中"${section.title}"的披露文字说明`,
      context: `科目:其他应付款(2241) 负债类 期末余额来自K3-1审定表 关注完整性认定`,
      existingContent: section.textContent || '',
      section: section.id,
    })
    const generated = res.data?.data?.content || res.data?.content || ''
    if (!generated) { ElMessage.warning('AI未生成内容'); return }

    await ElMessageBox.confirm(
      `AI生成内容预览：\n\n${generated.slice(0, 300)}${generated.length > 300 ? '...' : ''}`,
      'AI生成确认',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    section.textContent = section.textContent ? `${section.textContent}\n${generated}` : generated
    handleNoteTextChange(sIdx)
    ElMessage.success('已填入AI生成内容')
  } catch { /* cancelled or error */ }
}

// ═══ 持久化 ═══
async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const rows = sections.flatMap(s => s.rows.map(r => ({ project: r.item || '', endAmount: r.endBalance ?? 0, priorAmount: r.beginBalance ?? 0 })))
  const narrative = sections.filter(s => s.textContent).map(s => s.textContent).join('\n\n')
  const payload = buildK3SyncPayload('listed', props.wpId || '', rows, narrative)
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K3', variant: 'listed', accountCode: '2241',
      projectId: props.projectId, sectionIds: ['五、42'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

function persistSection(sIdx: number): void {
  const section = sections[sIdx]
  if (!section) return
  const data = JSON.stringify({ rows: section.rows, textContent: section.textContent })
  emit('save', `K3-disc-listed-${section.id}`, { remark: data })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function loadSavedData(): void {
  for (let i = 0; i < sections.length; i++) {
    const section = sections[i]
    const saved = props.allResponses.get(`K3-disc-listed-${section.id}`)
    // checklist_responses 格式: {item_id, conclusion, remark}
    const raw = saved?.remark ?? saved?.value ?? null
    if (raw) {
      try {
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
        if (parsed.rows?.length) section.rows = parsed.rows
        if (parsed.textContent) section.textContent = parsed.textContent
      } catch { /* ignore */ }
    }
  }
}

// ═══ 复核 ═══
function handleReview(id: string): void {
  openReviewDialog(id)
}

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k3-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }

/* 琥珀色方法论 */
.methodology-block { border-left: 4px solid #f59e0b; background: #fffbeb; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px; }
.methodology-title { font-weight: 600; color: #92400e; margin-bottom: 4px; font-size: 12px; }
.methodology-content { font-size: 12px; color: #78350f; line-height: 1.6; }

/* 卡片 */
.disclosure-card { margin-bottom: 12px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; font-size: 14px; }
.title-actions { display: flex; gap: 8px; align-items: center; }

/* 表格 */
.disclosure-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.auto-fill { color: var(--el-color-primary); }
.over3y-highlight { color: #e6a23c; font-weight: 600; }

/* 编制提示 */
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
