<template>
  <div class="k1-disclosure-soe">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 按账龄分析披露（1年内/1-2年/2-3年/3年以上）</div>
        <div class="guide-step"><span class="step-num">②</span> 按性质分类披露（国企格式，中文序号）</div>
        <div class="guide-step"><span class="step-num">③</span> 坏账准备计提与变动情况披露</div>
        <div class="guide-step"><span class="step-num">④</span> 自动从K1-1审定表取数 + AI辅助文字说明</div>
      </div>
    </div>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS22 其他应收款附注披露要求（国有企业适用）</div>
      <div class="methodology-content">
        按《企业会计准则第22号——金融工具确认和计量》及国有企业报表附注格式，应披露：
        其他应收款按账龄列示期末余额；按款项性质分类列示；坏账准备变动情况（期初/本期计提/本期转回/本期核销/期末）；
        期末重要其他应收款明细。国企版使用"一、二、三..."中文编号格式。
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
          :max-height="section.rows.length > 25 ? 450 : undefined"
          class="disclosure-table"
        >
          <el-table-column prop="item" label="项目" min-width="150" fixed />
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
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly && !row.isAutoFilled">
                <el-input-number :model-value="row.badDebtProvision" :controls="false" size="small" @change="(v: number) => handleCellEdit(sIdx, row.rowIdx, 'badDebtProvision', v)" />
              </template>
              <span v-else :class="{ 'auto-fill': row.isAutoFilled }">{{ fmtAmt(row.badDebtProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="账面价值=期末余额-坏账准备">{{ fmtAmt(row.bookValue) }}</span>
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
        <li>国企附注格式（130行×10列），按账龄/性质/坏账变动分类披露</li>
        <li>监听 substantive:adjudicated(1221) 自动同步审定数据（浅蓝色=跨sheet自动取数）</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
        <li>与上市公司版区别：使用中文编号（一、二、三...）；列数较少；无前五名明细要求</li>
        <li>适用国有企业报表附注披露格式（CAS22/CAS37）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabDisclosureSoe.vue — 附注披露信息（国有企业版）
 *
 * Spec: k1-other-receivables Task 4.7
 * Requirements: 10.1-10.3
 *
 * 130行×10列结构化表格，包含：
 * - 按账龄披露（1年内/1-2年/2-3年/3年以上）
 * - 按性质分类披露
 * - 坏账准备变动情况
 * - 重要其他应收款明细
 *
 * EventBus: subscribe 'substantive:adjudicated' → auto-refresh
 *           publish 'disclosure:note-text-updated' on text change
 */
import { reactive, inject, onMounted, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

const K1_ACCOUNT_CODE = '1221'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ═══ 数据模型 ═══
interface DisclosureRow {
  rowIdx: number
  item: string
  endBalance: number
  beginBalance: number
  badDebtProvision: number
  bookValue: number
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

// ═══ 构建130行分配到5个section ═══
function makeRows(items: string[], formulaItem: string): DisclosureRow[] {
  return items.map((item, i) => ({
    rowIdx: i, item, endBalance: 0, beginBalance: 0,
    badDebtProvision: 0, bookValue: 0, remark: '',
    isFormula: item === formulaItem,
  }))
}

function buildSections(): DisclosureSection[] {
  const importantRows: DisclosureRow[] = Array.from({ length: 10 }, (_, i) => ({
    rowIdx: i, item: `项目${i + 1}`, endBalance: 0, beginBalance: 0,
    badDebtProvision: 0, bookValue: 0, remark: '',
  }))
  importantRows.push({ rowIdx: 10, item: '小计', endBalance: 0, beginBalance: 0, badDebtProvision: 0, bookValue: 0, remark: '', isFormula: true })

  return [
    { id: 'aging', title: '一、按账龄列示其他应收款', rows: makeRows(['1年以内', '1至2年', '2至3年', '3年以上', '合计'], '合计'), hasTextArea: true, textContent: '' },
    { id: 'nature', title: '二、按款项性质分类列示', rows: makeRows(['保证金及押金', '备用金', '应收暂付款', '代垫款项', '其他', '合计'], '合计'), hasTextArea: true, textContent: '' },
    { id: 'bad-debt-change', title: '三、坏账准备变动情况', rows: makeRows(['期初余额', '本期计提', '本期转回', '本期核销', '期末余额'], '期末余额'), hasTextArea: true, textContent: '' },
    { id: 'important', title: '四、期末重要其他应收款明细', rows: importantRows, hasTextArea: true, textContent: '' },
    { id: 'other', title: '五、其他披露事项', rows: [], hasTextArea: true, textContent: '' },
  ]
}

const sections = reactive<DisclosureSection[]>(buildSections())

// ═══ 自动取数 from allResponses ═══
function applyAutoFill(): void {
  const endBal = getResponseNumber('K1-1-receivable-end')
  const beginBal = getResponseNumber('K1-1-receivable-begin')
  const badDebtEnd = getResponseNumber('K1-1-baddebt-end')

  // 按账龄section的合计行自动填充
  const agingSection = sections.find(s => s.id === 'aging')
  if (agingSection) {
    const totalRow = agingSection.rows.find(r => r.item === '合计')
    if (totalRow) {
      totalRow.endBalance = endBal
      totalRow.beginBalance = beginBal
      totalRow.badDebtProvision = badDebtEnd
      totalRow.bookValue = endBal - badDebtEnd
      totalRow.isAutoFilled = true
    }
  }

  // 按性质合计行
  const natureSection = sections.find(s => s.id === 'nature')
  if (natureSection) {
    const totalRow = natureSection.rows.find(r => r.item === '合计')
    if (totalRow) {
      totalRow.endBalance = endBal
      totalRow.beginBalance = beginBal
      totalRow.isAutoFilled = true
    }
  }

  recalcBookValues()
}

function getResponseNumber(key: string): number {
  const item = props.allResponses.get(key)
  if (!item) return 0
  const val = item.value ?? item
  return typeof val === 'number' ? val : parseFloat(val) || 0
}

function recalcBookValues(): void {
  for (const section of sections) {
    for (const row of section.rows) {
      row.bookValue = row.endBalance - row.badDebtProvision
    }
  }
}

// ═══ EventBus: subscribe 'substantive:adjudicated' ═══
function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K1_ACCOUNT_CODE || payload.wpCode === 'K1') {
    applyAutoFill()
  }
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  loadSavedData()
  applyAutoFill()
})

onBeforeUnmount(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
})

// ═══ 单元格编辑 ═══
function handleCellEdit(sIdx: number, rowIdx: number, field: string, value: any): void {
  const section = sections[sIdx]
  if (!section) return
  const row = section.rows[rowIdx]
  if (!row) return
  ;(row as any)[field] = value ?? 0
  recalcBookValues()
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
      accountCode: K1_ACCOUNT_CODE,
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
      prompt: `请生成其他应收款附注（国企格式）中"${section.title}"的披露文字说明`,
      context: `科目:其他应收款(1221) 期末余额来自K1-1审定表 国有企业报表附注格式`,
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
function persistSection(sIdx: number): void {
  const section = sections[sIdx]
  if (!section) return
  emit('save', `K1-disc-soe-${section.id}`, JSON.stringify({
    rows: section.rows,
    textContent: section.textContent,
  }))
}

function loadSavedData(): void {
  for (let i = 0; i < sections.length; i++) {
    const section = sections[i]
    const saved = props.allResponses.get(`K1-disc-soe-${section.id}`)
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
.k1-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }

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
