<template>
  <div class="k2-disclosure-soe">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 其他流动资产变动矩阵（期初+增加-减少=期末）自动从K2-2审定数取数</div>
        <div class="guide-step"><span class="step-num">②</span> 按项目分类列示（国企格式，中文序号）</div>
        <div class="guide-step"><span class="step-num">③</span> 重大明细需单独列示（含变动原因）</div>
        <div class="guide-step"><span class="step-num">④</span> 国企版 13行×13列，AI辅助生成说明文字</div>
      </div>
    </div>

    <!-- 同步到附注按钮 -->
    <div style="margin-bottom: 12px; text-align: right;">
      <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
    </div>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">CAS 附注披露要求（国有企业适用）</div>
      <div class="methodology-content">
        按《企业会计准则》及国有企业报表附注格式，应披露其他流动资产按项目分类列示期末余额及变动情况。
        国企版使用"一、二、三..."中文编号格式。科目1231其他流动资产，资产类借方，期末=期初+增加-减少。
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
          <el-table-column prop="item" label="项目" min-width="140" fixed />
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
          <el-table-column label="本期增加" width="120" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly && !row.isAutoFilled">
                <el-input-number :model-value="row.increase" :controls="false" size="small" @change="(v: number) => handleCellEdit(sIdx, row.rowIdx, 'increase', v)" />
              </template>
              <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="120" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly && !row.isAutoFilled">
                <el-input-number :model-value="row.decrease" :controls="false" size="small" @change="(v: number) => handleCellEdit(sIdx, row.rowIdx, 'decrease', v)" />
              </template>
              <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动原因" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="变动原因" @change="(v: string) => handleCellEdit(sIdx, row.rowIdx, 'remark', v)" />
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
            :autosize="{ minRows: 3, maxRows: 10 }"
            :disabled="isReadonly"
            :placeholder="`请填写${section.title}相关披露文字...`"
            @change="handleNoteTextChange(sIdx)"
          />
        </template>
      </el-card>
    </template>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注：13行×13列，按项目分类披露变动情况（中文序号格式）</li>
        <li>科目1231其他流动资产（资产类借方）：期末=期初+增加-减少</li>
        <li>数据优先从K2-2明细表审定数自动取数（收到 substantive:adjudicated 事件后刷新）</li>
        <li>国企版增加"变动原因"列代替"占比"列</li>
        <li>说明文字可使用AI辅助生成初稿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabDisclosureSoe.vue — 附注披露信息（国有企业）
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 4.6
 * Requirements: 7.1
 *
 * 13行×13列结构化表格，国企版：
 * - 其他流动资产变动矩阵（项目/期末/期初/增加/减少/变动原因）
 * - 按项目分类（中文编号格式）
 * - 重大明细+变动原因说明
 *
 * EventBus: subscribe 'substantive:adjudicated' → auto-refresh
 *           subscribe 'adjustment:created' → auto-refresh
 *           publish 'disclosure:note-text-updated' on text change
 */
import { reactive, inject, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildK2SyncPayload } from '../../composables/k2NoteSectionMap'

const K2_ACCOUNT_CODE = '1231'

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

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ═══ 数据模型 ═══
interface DisclosureRow {
  rowIdx: number
  item: string
  endBalance: number
  beginBalance: number
  increase: number
  decrease: number
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

// ═══ 构建sections（国企格式中文编号） ═══
function buildSections(): DisclosureSection[] {
  return [
    {
      id: 'movement',
      title: '一、其他流动资产变动情况',
      rows: [
        { rowIdx: 0, item: '合同取得成本', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 1, item: '预付款项-待转', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 2, item: '待摊费用', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 3, item: '待抵扣进项税额', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 4, item: '待认证进项税额', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 5, item: '增值税留抵税额', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 6, item: '理财产品', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 7, item: '其他', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '' },
        { rowIdx: 8, item: '合计', endBalance: 0, beginBalance: 0, increase: 0, decrease: 0, remark: '', isFormula: true },
      ],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'significant',
      title: '二、重大其他流动资产明细',
      rows: [],
      hasTextArea: true,
      textContent: '',
    },
    {
      id: 'other',
      title: '三、其他需要说明的事项',
      rows: [],
      hasTextArea: true,
      textContent: '',
    },
  ]
}

const sections = reactive<DisclosureSection[]>(buildSections())

// ═══ 自动取数 from allResponses（K2-2审定数） ═══
function applyAutoFill(): void {
  const endBal = getResponseNumber('K2-1-audited-total')
  const beginBal = getResponseNumber('K2-1-begin-total')

  const movementSection = sections.find(s => s.id === 'movement')
  if (movementSection) {
    const totalRow = movementSection.rows.find(r => r.item === '合计')
    if (totalRow) {
      totalRow.endBalance = endBal
      totalRow.beginBalance = beginBal
      totalRow.increase = endBal - beginBal > 0 ? endBal - beginBal : 0
      totalRow.decrease = beginBal - endBal > 0 ? beginBal - endBal : 0
      totalRow.isAutoFilled = true
    }
  }

  recalcFormulas()
}

function getResponseNumber(key: string): number {
  const item = props.allResponses.get(key)
  if (!item) return 0
  const val = item.value ?? item
  return typeof val === 'number' ? val : parseFloat(val) || 0
}

function recalcFormulas(): void {
  for (const section of sections) {
    // 非公式行：期末 = 期初 + 增加 - 减少
    for (const row of section.rows) {
      if (!row.isFormula && !row.isAutoFilled) {
        row.endBalance = row.beginBalance + row.increase - row.decrease
      }
    }
    // 合计行汇总
    const totalRow = section.rows.find(r => r.isFormula)
    if (totalRow && !totalRow.isAutoFilled) {
      const dataRows = section.rows.filter(r => !r.isFormula)
      totalRow.endBalance = dataRows.reduce((s, r) => s + r.endBalance, 0)
      totalRow.beginBalance = dataRows.reduce((s, r) => s + r.beginBalance, 0)
      totalRow.increase = dataRows.reduce((s, r) => s + r.increase, 0)
      totalRow.decrease = dataRows.reduce((s, r) => s + r.decrease, 0)
    }
  }
}

// ═══ EventBus: subscribe 'substantive:adjudicated' + 'adjustment:created' ═══
function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K2_ACCOUNT_CODE || payload.wpCode === 'K2') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload || payload.accountCode === K2_ACCOUNT_CODE || payload.wpCode === 'K2') {
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
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
  autoSync.cancelPending()
})

// ═══ 单元格编辑 ═══
function handleCellEdit(sIdx: number, rowIdx: number, field: string, value: any): void {
  const section = sections[sIdx]
  if (!section) return
  const row = section.rows[rowIdx]
  if (!row) return
  ;(row as any)[field] = value ?? (typeof value === 'number' ? 0 : '')
  recalcFormulas()
  persistSection(sIdx)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ═══ 同步到附注 ═══
async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const movementSection = sections.find(s => s.id === 'movement')
  const disclosureRows = (movementSection?.rows || []).filter(r => !r.isFormula).map(r => ({
    project: r.item,
    endAmount: r.endBalance || 0,
    priorAmount: r.beginBalance || 0,
  }))
  const narrativeText = sections.filter(s => s.hasTextArea && s.textContent).map(s => s.textContent).join('\n')
  const payload = buildK2SyncPayload('soe', props.wpId || '', disclosureRows, narrativeText)
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K2', variant: 'soe', accountCode: '1231',
      projectId: props.projectId, sectionIds: ['八、14'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
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
      accountCode: K2_ACCOUNT_CODE,
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
      prompt: `请生成其他流动资产(1231)附注中"${section.title}"的披露文字说明（国企格式）`,
      context: '科目:其他流动资产(1231) 资产类借方 期末=期初+增加-减少 国有企业附注格式',
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
  emit('save', `K2-disc-soe-${section.id}`, JSON.stringify({
    rows: section.rows,
    textContent: section.textContent,
  }))
}

function loadSavedData(): void {
  for (let i = 0; i < sections.length; i++) {
    const section = sections[i]
    const saved = props.allResponses.get(`K2-disc-soe-${section.id}`)
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
.k2-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }

/* 琥珀色方法论 */
.methodology-block { border-left: 4px solid #d97706; background: #fffbeb; border-radius: 4px; padding: 12px 16px; margin-bottom: 12px; font-size: 12px; color: #92400e; line-height: 1.7; }
.methodology-title { font-weight: 600; color: #78350f; margin-bottom: 4px; }

/* 卡片 */
.disclosure-card { margin-bottom: 12px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; font-size: 14px; }
.title-actions { display: flex; gap: 8px; align-items: center; }

/* 表格 */
.disclosure-table { font-size: var(--wp-font-size, 13px); }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.amount-cell { font-variant-numeric: tabular-nums; }
.auto-fill { color: var(--el-color-primary); }

/* 编制提示 */
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
