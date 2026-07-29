<template>
  <div class="k4-disclosure-soe">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 按性质分类披露（预提/待转销项/代扣等）</div>
        <div class="guide-step"><span class="step-num">②</span> 增减变动分析</div>
        <div class="guide-step"><span class="step-num">③</span> 自动从K4-1审定表取数</div>
        <div class="guide-step"><span class="step-num">④</span> AI辅助生成披露文字说明</div>
      </div>
      <div style="margin-top:8px">
        <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
      </div>
    </div>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS37 其他流动负债附注披露要求（国有企业适用）</div>
      <div class="methodology-content">
        按《企业会计准则第37号——金融工具列报》及国有企业报表附注格式，其他流动负债应披露：
        按项目性质列示期末余额和期初余额；增减变动分析。国企版使用"一、二、三..."中文编号格式，
        侧重负债完整性认定。约14行×12列精简结构。
      </div>
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
              <el-button size="small" type="default" link @click="handleReview(`disc-soe-${section.id}`)">💬</el-button>
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
          class="disclosure-table"
        >
          <el-table-column prop="item" label="项目" min-width="150" fixed />
          <el-table-column label="期末余额" width="120" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly && !row.isAutoFilled">
                <el-input-number :model-value="row.endBalance" :controls="false" size="small" @change="(v: number) => handleCellEdit(sIdx, row.rowIdx, 'endBalance', v)" />
              </template>
              <span v-else :class="{ 'formula-cell': row.isFormula, 'auto-fill': row.isAutoFilled }" :title="row.isFormula ? '公式计算' : row.isAutoFilled ? '跨sheet自动取数' : ''">{{ fmtAmt(row.endBalance) }}</span>
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
          <el-table-column label="增减额" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="增减额=期末-期初">{{ fmtAmt((row.endBalance || 0) - (row.beginBalance || 0)) }}</span>
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
            :autosize="{ minRows: 2, maxRows: 10 }"
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
        <li>国企附注格式（约14行×12列），按性质分类精简披露</li>
        <li>监听 substantive:adjudicated(2245) 自动同步审定数据（浅蓝色=跨sheet自动取数）</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>与上市公司版区别：使用中文编号（一、二...）；无到期期限分析；无占比列</li>
        <li>负债类科目关注完整性认定：确保所有应入账的其他流动负债已完整披露</li>
        <li>政府补助：受益期≤1年→其他流动负债(K4)，&gt;1年→递延收益(K7)，两者按同一补助项目合计=总授予金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabDisclosureSoe.vue — 附注披露信息（国有企业版）14×12
 *
 * Spec: k4-other-current-liabilities Task 4.6
 * Requirements: 5.1
 *
 * 14行×12列精简结构化表格，包含：
 * - 按性质分类（预提费用/待转销项税额/代扣代缴等）
 * - 增减变动分析
 *
 * EventBus: subscribe 'substantive:adjudicated' → auto-refresh
 *           publish 'disclosure:note-text-updated' on text change
 *
 * 科目：2245 其他流动负债（负债类）
 */
import { reactive, inject, onMounted, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import type { WorkpaperRuntimeContext } from '../../composables/useWorkpaperScaffold'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const K4_ACCOUNT_CODE = '2245'

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
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ═══ 数据模型 ═══
interface DisclosureRow {
  rowIdx: number
  item: string
  endBalance: number
  beginBalance: number
  remark: string
  isFormula?: boolean
  isAutoFilled?: boolean
}

interface DisclosureSection {
  id: string
  title: string
  rows: DisclosureRow[]
  hasTextArea: boolean
  textContent: string
}

// ═══ 构建14行分配到3个section ═══
function makeRow(item: string, idx: number, opts?: Partial<DisclosureRow>): DisclosureRow {
  return {
    rowIdx: idx, item, endBalance: 0, beginBalance: 0, remark: '',
    ...opts,
  }
}

function buildSections(): DisclosureSection[] {
  // 一、按项目性质分类（~9行）
  const natureItems = [
    '预提费用', '待转销项税额', '代扣代缴款项', '待认证进项税额',
    '应付短期利息', '其他', '合计',
  ]
  const natureRows = natureItems.map((item, i) => makeRow(item, i, { isFormula: item === '合计' }))

  // 二、增减变动说明（~3行）
  const changeItems = ['本期增加', '本期减少', '净变动']
  const changeRows = changeItems.map((item, i) => makeRow(item, i, { isFormula: item === '净变动' }))

  return [
    { id: 'nature', title: '一、按项目性质分类', rows: natureRows, hasTextArea: true, textContent: '' },
    { id: 'change', title: '二、增减变动说明', rows: changeRows, hasTextArea: true, textContent: '' },
    { id: 'k7-reconcile', title: '三、政府补助与K7递延收益勾稽', rows: [], hasTextArea: true, textContent: '' },
    { id: 'other', title: '四、其他披露事项', rows: [], hasTextArea: true, textContent: '' },
  ]
}

const sections = reactive<DisclosureSection[]>(buildSections())

// ═══ 自动取数 from allResponses ═══
function applyAutoFill(): void {
  const endBal = getResponseNumber('K4-1-liability-end')
  const beginBal = getResponseNumber('K4-1-liability-begin')

  // 按性质合计行自动填充
  const natureSection = sections.find(s => s.id === 'nature')
  if (natureSection) {
    const totalRow = natureSection.rows.find(r => r.item === '合计')
    if (totalRow) {
      totalRow.endBalance = endBal
      totalRow.beginBalance = beginBal
      totalRow.isAutoFilled = true
    }
  }
}

function getResponseNumber(key: string): number {
  const item = props.allResponses.get(key)
  if (!item) return 0
  const val = item.value ?? item
  return typeof val === 'number' ? val : parseFloat(val) || 0
}

// ═══ EventBus: subscribe 'substantive:adjudicated' + 'adjustment:created' ═══
function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K4_ACCOUNT_CODE || payload.wpCode === 'K4') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.accountCode === K4_ACCOUNT_CODE || payload.wpCode === 'K4') {
    applyAutoFill()
  }
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
  loadSavedData()
  applyAutoFill()
})

onBeforeUnmount(() => {
  autoSync.cancelPending()
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ═══ 单元格编辑 ═══
function handleCellEdit(sIdx: number, rowIdx: number, field: string, value: any): void {
  const section = sections[sIdx]
  if (!section) return
  const row = section.rows[rowIdx]
  if (!row) return
  ;(row as any)[field] = value ?? 0
  persistSection(sIdx)
}

// ═══ 文本变化 → publish EventBus ═══
function handleNoteTextChange(sIdx: number): void {
  persistSection(sIdx)
  publishNoteText()
}

function publishNoteText(): void {
  const allText = sections
    .filter(s => s.hasTextArea && s.textContent)
    .map(s => `【${s.title}】\n${s.textContent}`)
    .join('\n\n')
  try {
    eventBus.emit('disclosure:note-text-updated', {
      accountCode: K4_ACCOUNT_CODE,
      section: 'soe',
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
      prompt: `请生成其他流动负债附注（国企格式）中"${section.title}"的披露文字说明`,
      context: {
        科目: '2245 其他流动负债（负债类）',
        格式: '国有企业报表附注',
        当前节: section.title,
        行数: String(section.rows.length),
        关注认定: '完整性（负债易少计）',
        K7提示: '政府补助受益期>1年部分在递延收益K7列报',
      },
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
  const rows = sections.flatMap(s => s.rows.filter(r => !r.isFormula).map(r => ({ project: r.item, endAmount: r.endBalance ?? 0, priorAmount: r.beginBalance ?? 0 })))
  const narrative = sections.filter(s => s.textContent).map(s => s.textContent).join('\n\n')
  const payload = {
    wp_id: props.wpId,
    sheet_name: 'K4-note-soe',
    section_id: '八、48',
    current_standard: 'soe_standalone',
    sub_table_data: { rows },
    _note_texts: narrative ? [{ section: 'main', title: '说明', text: narrative }] : [],
  }
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K4', variant: 'soe', accountCode: '2245',
      projectId: props.projectId, sectionIds: ['八、48'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

function persistSection(sIdx: number): void {
  const section = sections[sIdx]
  if (!section) return
  emit('save', `K4-disc-soe-${section.id}`, JSON.stringify({
    rows: section.rows,
    textContent: section.textContent,
  }))
  scheduleAutoSnapshot()
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function scheduleAutoSnapshot(): void {
  try { runtime?.version?.scheduleAutoSnapshot?.() } catch { /* silent */ }
}

function loadSavedData(): void {
  for (let i = 0; i < sections.length; i++) {
    const section = sections[i]
    const saved = props.allResponses.get(`K4-disc-soe-${section.id}`)
    if (saved?.value) {
      try {
        const parsed = typeof saved.value === 'string' ? JSON.parse(saved.value) : saved.value
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
.k4-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }

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

/* 编制提示 */
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
