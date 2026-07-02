<script setup lang="ts">
/**
 * D4TabInvoiceCompare — D4-23 收入与开具发票金额比较分析
 *
 * 固定12月行 × 10列矩阵：账面收入(浅绿) vs 开票金额(浅蓝)
 * 自动计算：营业收入合计/开票金额合计/差异
 * 差异≠0行黄色高亮，合计行固定底部
 * 双模式 + AI辅助 + 导入导出
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4InvoiceCompare, parseNum } from '../../composables/useD4InvoiceCompare'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────
const {
  rows, auditNote, auditConclusion, totals, diffCount,
  updateCell, updateAuditNote, updateAuditConclusion,
} = useD4InvoiceCompare({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  isReadonly: computed(() => props.isReadonly),
})

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Mode / AI ───────────────────────────────────────────────────────
const editorMode = ref<string>('表格视图')
const modeOptions = ['表格视图', '在线编辑']

const aiAvailable = ref(false)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

// ─── Format ──────────────────────────────────────────────────────────
function fmtAmount(v: number | string): string {
  const n = parseNum(v)
  if (n === 0) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: any }) {
  if (row.diff !== 0 && (parseNum(row.mainRevenue) || parseNum(row.vatAmount))) return 'row-diff'
  return ''
}

// ─── AI ──────────────────────────────────────────────────────────────
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'analysis-note',
      existingContent: auditNote.value || '',
      relatedContext: {
        task: '基于收入与开具发票金额比较分析(D4-23)的月度对比数据，分析差异原因并生成审计说明',
        totalRevenue: totals.value.revenueTotal,
        totalInvoice: totals.value.invoiceTotal,
        totalDiff: totals.value.diff,
        diffMonths: diffCount.value,
      },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiNoteLoading.value = false }
}

async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-conclusion',
      existingContent: auditConclusion.value || '',
      relatedContext: {
        task: '基于收入与发票金额比较结果，生成审计结论',
        noteText: auditNote.value || '',
        totalDiff: totals.value.diff,
        diffMonths: diffCount.value,
      },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiConclusionLoading.value = false }
}

// ─── Import/Export ───────────────────────────────────────────────────
function handleExportTemplate() { exportTemplate('D4-23') }
function handleExportData() { exportData('D4-23') }
async function handleImportFile(uploadFile: any) { await importData('D4-23', uploadFile.raw || uploadFile) }
</script>

<template>
  <div class="d4-invoice-compare">
    <!-- ═══ 顶部工具条 ═══ -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      </div>
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false"
                  :disabled="isReadonly || importing" @change="handleImportFile">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-2" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-23-invoice')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 统计仪表板 ═══ -->
    <div class="stats-dashboard">
      <div class="stat-card stat-revenue">
        <div class="stat-value">{{ fmtAmount(totals.revenueTotal) }}</div>
        <div class="stat-label">营业收入合计</div>
      </div>
      <div class="stat-card stat-invoice">
        <div class="stat-value">{{ fmtAmount(totals.invoiceTotal) }}</div>
        <div class="stat-label">开票金额合计</div>
      </div>
      <div class="stat-card" :class="totals.diff !== 0 ? 'stat-warn' : 'stat-ok'">
        <div class="stat-value">{{ fmtAmount(totals.diff) }}</div>
        <div class="stat-label">差异合计</div>
      </div>
      <div class="stat-card stat-count">
        <div class="stat-value">{{ diffCount }}<span class="stat-unit">月</span></div>
        <div class="stat-label">存在差异</div>
      </div>
    </div>

    <!-- ═══ 非OO内容区 ═══ -->
    <template v-if="editorMode !== '在线编辑'">
      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="获取各月主营业务收入和其他业务收入数据" placement="bottom" :show-after="300">
          <span class="guide-chip">①填写账面收入</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="从税控系统获取各月增值税发票和普通发票开具数据" placement="bottom" :show-after="300">
          <span class="guide-chip">②填写开票数据</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="系统自动计算营业收入合计、开票合计、差异" placement="bottom" :show-after="300">
          <span class="guide-chip">③核对差异</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="对差异月份追查原因，填写审计说明与结论" placement="bottom" :show-after="300">
          <span class="guide-chip">④分析结论</span>
        </el-tooltip>
      </div>

      <!-- ═══ 主表格 ═══ -->
      <el-table :data="rows" border class="invoice-table" :row-class-name="rowClassName" show-summary :summary-method="getSummary">
        <!-- 月份 -->
        <el-table-column label="月份" width="65" fixed align="center">
          <template #default="{ row }">{{ row.month }}</template>
        </el-table-column>

        <!-- 本期账面确认收入（浅绿） -->
        <el-table-column label="本期账面确认收入" align="center" class-name="col-revenue">
          <el-table-column label="主营业务收入" min-width="120" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-model="row.mainRevenue" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell($index, 'mainRevenue', row.mainRevenue)" />
            </template>
          </el-table-column>
          <el-table-column label="其他业务收入" min-width="120" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-model="row.otherRevenue" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell($index, 'otherRevenue', row.otherRevenue)" />
            </template>
          </el-table-column>
          <el-table-column label="营业收入合计" min-width="120" align="right">
            <template #default="{ row }">
              <span class="auto-calc" title="自动计算：主营业务收入 + 其他业务收入">{{ fmtAmount(row.revenueTotal) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 本期开具发票的金额（浅蓝） -->
        <el-table-column label="本期开具发票的金额" align="center" class-name="col-invoice">
          <el-table-column label="增值税发票金额" min-width="120" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-model="row.vatAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell($index, 'vatAmount', row.vatAmount)" />
            </template>
          </el-table-column>
          <el-table-column label="增值税发票份数" min-width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-model="row.vatCount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" :precision="0" @change="updateCell($index, 'vatCount', row.vatCount)" />
            </template>
          </el-table-column>
          <el-table-column label="普通发票金额" min-width="120" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-model="row.normalAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell($index, 'normalAmount', row.normalAmount)" />
            </template>
          </el-table-column>
          <el-table-column label="普通发票份数" min-width="100" align="right">
            <template #default="{ row, $index }">
              <el-input-number v-model="row.normalCount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" :precision="0" @change="updateCell($index, 'normalCount', row.normalCount)" />
            </template>
          </el-table-column>
          <el-table-column label="开票金额合计" min-width="120" align="right">
            <template #default="{ row }">
              <span class="auto-calc" title="自动计算：增值税发票金额 + 普通发票金额">{{ fmtAmount(row.invoiceTotal) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 差异 -->
        <el-table-column label="差异" min-width="110" align="right">
          <template #default="{ row }">
            <span class="auto-calc" :class="{ 'diff-warn': row.diff !== 0 }" title="自动计算：营业收入合计 - 开票金额合计">{{ fmtAmount(row.diff) }}</span>
          </template>
        </el-table-column>

        <!-- 索引号 -->
        <el-table-column label="索引号" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell($index, 'indexRef', row.indexRef)" />
          </template>
        </el-table-column>
      </el-table>

      <!-- ═══ 审计意见区 ═══ -->
      <el-card class="audit-opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-chips">
              <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
            </div>
            <div class="opinion-actions">
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly || !aiAvailable" @click="genNote">🤖 AI辅助说明</el-button>
              </el-tooltip>
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button>
              </el-tooltip>
            </div>
          </div>
        </template>
        <div class="opinion-body">
          <div class="opinion-field">
            <label>三、审计说明</label>
            <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote" :disabled="isReadonly" placeholder="分析收入确认金额与开票金额存在差异的原因（如跨期收入、预收款开票、免税收入等）" @input="(v: string) => updateAuditNote(v)" />
          </div>
          <div class="opinion-field">
            <label>四、审计结论</label>
            <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断收入确认与开票金额的差异是否合理，是否存在虚假收入或隐瞒收入的迹象" @input="(v: string) => updateAuditConclusion(v)" />
          </div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示</summary>
        <ol class="tips-list">
          <li>账面收入数据应与D4-2收入明细表、试算平衡表核对一致。</li>
          <li>开票数据应从防伪税控系统或金税系统导出，确保数据来源可靠。</li>
          <li>差异原因通常包括：跨期收入确认、预收款先开票、免税或简易计税收入、视同销售等。</li>
          <li>对持续存在大额差异的月份应重点关注，评估是否存在虚开发票或收入舞弊风险。</li>
          <li>索引号列用于关联到具体的核查证据或说明底稿。</li>
        </ol>
      </details>
    </template>

    <!-- ═══ OnlyOffice 模式 ═══ -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container">
        <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId"
          sheet-name="收入与开具发票金额比较分析D4-23" :readonly="isReadonly" />
      </div>
    </template>
  </div>
</template>

<script lang="ts">
// getSummary as non-setup for el-table
function getSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    // Auto-sum numeric columns
    const prop = ['', 'mainRevenue', 'otherRevenue', 'revenueTotal', 'vatAmount', 'vatCount', 'normalAmount', 'normalCount', 'invoiceTotal', 'diff', ''][index] || ''
    if (prop && data.length) {
      const sum = data.reduce((acc: number, row: any) => {
        const v = typeof row[prop] === 'number' ? row[prop] : parseFloat(row[prop]) || 0
        return acc + v
      }, 0)
      sums[index] = sum === 0 ? '—' : sum.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    } else {
      sums[index] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.d4-invoice-compare { padding: 16px 20px; font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 120px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-revenue { border-left: 3px solid #67c23a; }
.stat-card.stat-invoice { border-left: 3px solid #409eff; }
.stat-card.stat-warn { border-left: 3px solid #e6a23c; }
.stat-card.stat-ok { border-left: 3px solid #67c23a; }
.stat-card.stat-count { border-left: 3px solid #909399; }
.stat-value { font-size: 16px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }

.guide-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.guide-strip-label { font-weight: 600; color: #67c23a; font-size: 12px; }
.guide-chip { background: #fff; border: 1px solid #c2e7b0; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #529b2e; cursor: help; }
.guide-chip:hover { background: #f0f9eb; }
.guide-arrow { color: #a8abb2; font-size: 12px; }

.invoice-table { font-size: 13px; margin-bottom: 24px; }
.invoice-table :deep(.el-table__cell) { padding: 5px 4px; }
.invoice-table :deep(.col-revenue .el-table__cell) { background-color: #f0faf0 !important; }
.invoice-table :deep(.col-invoice .el-table__cell) { background-color: #f0f5ff !important; }
.invoice-table :deep(.row-diff td) { background-color: #fdf6ec !important; }

.auto-calc { color: #909399; font-style: italic; border-bottom: 1px dashed #c0c4cc; cursor: help; }
.auto-calc.diff-warn { color: #e6a23c; font-weight: 600; font-style: normal; }

.audit-opinion-card { margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-actions { margin-left: auto; display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500; }

.tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #f56c6c; }
.tips-list { margin: 8px 14px 12px; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }

.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
</style>
