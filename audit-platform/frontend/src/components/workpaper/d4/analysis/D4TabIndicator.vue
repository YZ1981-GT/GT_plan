<script setup lang="ts">
/**
 * D4TabIndicator — D4-6 重要指标分析表
 *
 * 对齐源模板真实结构：
 * 一、审计目标（3条固定）
 * 二、审计过程（AI辅助填充审计步骤）
 * 指标分析表（12行 × 7列）
 * 三、审计说明
 * 四、审计结论
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import { useD4ImportExport } from '../../composables/useD4ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// 双模式（结构化视图 / 在线编辑）
const editorMode = ref<'structured' | 'onlyoffice'>('structured')
const ooHealthy = ref(false)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
])
async function checkOoHealth() {
  try {
    const res = await http.get(`/api/workpapers/onlyoffice/health`, { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()

// ─── 审计目标（固定文本） ─────────────────────────────────────────────
const auditObjectives = [
  '1. 利润表中记录的营业收入已发生，且与被审计单位有关；',
  '2. 所有应当记录的营业收入均已记录；',
  '3. 与营业收入有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。',
]

// ─── 审计过程（AI可填充） ─────────────────────────────────────────────
const auditProcess = ref('')
function loadAuditProcess() {
  auditProcess.value = props.allResponses.get('D4-6-audit-process')?.remark || ''
}
watch(() => props.allResponses.get('D4-6-audit-process')?.remark, () => loadAuditProcess(), { immediate: true })

function updateAuditProcess(val: string) {
  if (props.isReadonly) return
  auditProcess.value = val
  persist('D4-6-audit-process', val)
}

// ─── 指标表 ──────────────────────────────────────────────────────────
interface IndicatorRow {
  key: string
  name: string
  formula?: string
  source?: string
  current: number
  prior: number
  diff1: number | null
  analysis1: string
  industryAvg: number | null
  diff2: number | null
  analysis2: string
}

const DEFAULT_INDICATORS: Array<{ key: string; name: string; formula: string; source: string }> = [
  { key: 'ar-to-assets', name: '应收账款/总资产', formula: '应收账款余额 / 资产总额', source: 'TB 科目1122 / 资产总计' },
  { key: 'ar-turnover-days', name: '应收账款周转天数=应收账款平均余额/(销售收入/365)', formula: '(期初AR+期末AR)/2 / (收入/365)', source: 'TB 科目1122+6001' },
  { key: 'ar-turnover-times', name: '应收账款周转次数=销售收入/应收账款平均余额', formula: '收入 / (期初AR+期末AR)/2', source: 'TB 科目6001/1122' },
  { key: 'last-quarter-ratio', name: '（末月/最后一个季度）销售情况/当期销售（金额或销量）', formula: '末季销售 / 全年销售', source: 'TB月度明细 科目6001' },
  { key: 'discount-ratio', name: '销售折扣/销售额', formula: '折扣金额 / 销售收入', source: 'TB 科目6001(折扣)' },
  { key: 'allowance-ratio', name: '销售折让/销售额', formula: '折让金额 / 销售收入', source: 'TB 科目6001(折让)' },
  { key: 'return-ratio', name: '销货退回/销售额', formula: '退货金额 / 销售收入', source: 'TB 科目6001(退货)' },
  { key: 'bad-debt-ratio', name: '坏账准备金额/应收账款余额', formula: '坏账准备 / 应收账款', source: 'TB 科目1231/1122' },
  { key: 'revenue-per-employee', name: '人均创收=销售收入/员工总数', formula: '收入 / 员工数', source: 'TB 科目6001 / project_info' },
  { key: 'net-profit-margin', name: '销售净利率=净利润/销售收入', formula: '净利润 / 收入', source: 'TB 科目4103/6001' },
  { key: 'profit-per-employee', name: '人均创利=净利润/员工总数', formula: '净利润 / 员工数', source: 'TB 科目4103 / project_info' },
  { key: 'sales-to-material', name: '当期销售金额/主要原材料采购金额', formula: '销售收入 / 原材料采购', source: 'TB 科目6001/4001(材料)' },
]

const indicators = ref<IndicatorRow[]>([])

function loadIndicators() {
  const resp = props.allResponses.get('D4-6-indicators-v2')
  if (resp?.remark) {
    try { const p = JSON.parse(resp.remark); if (Array.isArray(p) && p.length) { indicators.value = p; return } } catch {}
  }
  indicators.value = DEFAULT_INDICATORS.map(d => ({
    key: d.key, name: d.name, formula: d.formula, source: d.source,
    current: 0, prior: 0, diff1: null, analysis1: '',
    industryAvg: null, diff2: null, analysis2: '',
  }))
}
watch(() => props.allResponses.get('D4-6-indicators-v2')?.remark, () => loadIndicators(), { immediate: true })

const computedIndicators = computed(() => indicators.value.map(row => {
  const diff1 = row.prior !== 0 ? (row.current - row.prior) / Math.abs(row.prior) : null
  const diff2 = row.industryAvg != null && row.industryAvg !== 0
    ? (row.current - row.industryAvg) / Math.abs(row.industryAvg) : null
  return { ...row, diff1, diff2 }
}))

function updateIndicator(idx: number, field: keyof IndicatorRow, val: any) {
  if (props.isReadonly) return
  ;(indicators.value[idx] as any)[field] = val
  persistIndicators()
}

// ─── 审计说明 / 审计结论 ──────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
function loadNoteConclusion() {
  auditNote.value = props.allResponses.get('D4-6-note')?.remark || ''
  auditConclusion.value = props.allResponses.get('D4-6-conclusion')?.remark || ''
}
watch(() => props.allResponses.get('D4-6-note')?.remark, () => loadNoteConclusion(), { immediate: true })

function updateNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persist('D4-6-note', val) }
function updateConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persist('D4-6-conclusion', val) }

// ─── 格式化 ──────────────────────────────────────────────────────────
function fmtPercent(val: number | null): string {
  if (val == null) return '-'
  return (val * 100).toFixed(1) + '%'
}
function getTooltip(row: IndicatorRow, col: string): string {
  if (!row.formula) return ''
  if (col === 'diff1') return `公式: ③=(①-②)/②\n${row.formula}\n来源: ${row.source || ''}`
  if (col === 'diff2') return `公式: ⑥=(①-⑤)/⑤\n${row.formula}\n来源: ${row.source || ''}`
  return `${row.formula}\n来源: ${row.source || ''}`
}

// ─── AI辅助 ──────────────────────────────────────────────────────────
const aiAvailable = ref(false)
const aiLoadingKey = ref<string | null>(null)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

async function callD4Ai(section: string, existing: string): Promise<string> {
  const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
    section, existingContent: existing, relatedContext: {},
  }, { _silent: true } as any)
  return res.data?.data?.content ?? res.data?.content ?? ''
}

async function generateAuditProcess() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'process'
  try {
    const ctx = `审计目标：${auditObjectives.join(' ')}\n指标列表：${DEFAULT_INDICATORS.map(d => d.name).join('、')}\n请生成D4-6重要指标分析表的审计过程描述，说明获取数据来源、计算指标、与同行业对比的具体步骤。`
    const text = await callD4Ai('analysis-note', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计过程', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateAuditProcess(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const ctx = computedIndicators.value.map(r =>
      `${r.name}: 本期=${r.current}, 上期=${r.prior}, 差异1=${fmtPercent(r.diff1)}, 行业=${r.industryAvg ?? '-'}, 差异2=${fmtPercent(r.diff2)}`
    ).join('\n')
    const text = await callD4Ai('analysis-note', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const abnormals = computedIndicators.value.filter(r => r.diff1 != null && Math.abs(r.diff1) > 0.3)
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n异常指标：${abnormals.length ? abnormals.map(r => `${r.name}变动${fmtPercent(r.diff1)}`).join('、') : '无'}`
    const text = await callD4Ai('adj-conclusion', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

// ─── AI一键填充变动原因 ──────────────────────────────────────────────
async function aiFillAllAnalysis() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'fill-analysis'
  try {
    const rows = computedIndicators.value
    const ctx = rows.map(r =>
      `${r.name}: 本期=${r.current}, 上期=${r.prior}, 差异1=${fmtPercent(r.diff1)}, 行业均值=${r.industryAvg ?? '未填'}, 差异2=${fmtPercent(r.diff2)}`
    ).join('\n')
    const prompt = `以下是D4-6重要指标分析表的12项指标数据。请为每项指标生成"变化原因及合理性分析"，按JSON数组返回，每行含analysis1(与上期对比的变化原因)和analysis2(与行业对比的变化原因)。如果差异为"-"或接近0则填"变动不大，属于正常波动"。语言简洁专业。\n\n${ctx}`
    const text = await callD4Ai('analysis-note', prompt)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    // 尝试解析JSON
    let parsed: Array<{ analysis1?: string; analysis2?: string }> = []
    try {
      const match = text.match(/\[[\s\S]*\]/)
      if (match) parsed = JSON.parse(match[0])
    } catch {
      // 降级：尝试逐行解析
      try { parsed = JSON.parse(text) } catch { /* ignore */ }
    }
    if (parsed.length > 0) {
      await ElMessageBox.confirm(
        `AI 已为 ${parsed.length} 项指标生成变动原因分析，是否填入？`,
        'AI 一键填充',
        { confirmButtonText: '填入全部', cancelButtonText: '取消', type: 'info' },
      )
      parsed.forEach((item, idx) => {
        if (idx < indicators.value.length) {
          if (item.analysis1) indicators.value[idx].analysis1 = item.analysis1
          if (item.analysis2) indicators.value[idx].analysis2 = item.analysis2
        }
      })
      persistIndicators()
      ElMessage.success('已填充变动原因分析')
    } else {
      ElMessage.warning('AI 返回格式无法解析，请手动填写')
    }
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 填充失败') }
  finally { aiLoadingKey.value = null }
}

// ─── 导出模板 / 导出数据 / 导入（复用 useD4ImportExport，与D4-3一致） ──
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
})

function handleExportTemplate() { exportTemplate('D4-6') }
function handleExportData() { exportData('D4-6') }
function handleImportUpload(file: File): boolean {
  importData('D4-6', file).then((result) => {
    if (result && result.rowCount > 0) loadIndicators() // 刷新表格
  })
  return false
}

// ─── 持久化 ──────────────────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function persist(itemId: string, value: string) {
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value })
  debounceSave()
}
function persistIndicators() {
  props.allResponses.set('D4-6-indicators-v2', { item_id: 'D4-6-indicators-v2', conclusion: null, remark: JSON.stringify(indicators.value) })
  debounceSave()
}
function debounceSave() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
}
function flushSave() {
  const keys = ['D4-6-audit-process', 'D4-6-indicators-v2', 'D4-6-note', 'D4-6-conclusion']
  const items = keys.map(k => props.allResponses.get(k)).filter(Boolean)
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
}
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
</script>


<template>
  <div class="d4-indicator">

    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === 'structured'">    <!-- 一、审计目标 -->
    <section class="sec">
      <h4 class="sec-title">一、审计目标</h4>
      <div class="objective-list">
        <p v-for="(obj, i) in auditObjectives" :key="i" class="objective-item">{{ obj }}</p>
      </div>
    </section>

    <!-- 二、审计过程 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">二、审计过程</h4>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain
            :loading="aiLoadingKey === 'process'"
            :disabled="isReadonly || !aiAvailable"
            @click="generateAuditProcess">🤖 AI辅助</el-button>
        </el-tooltip>
      </div>
      <el-input
        type="textarea" :rows="3"
        :model-value="auditProcess" :disabled="isReadonly"
        placeholder="请描述审计过程中执行的具体步骤（如：获取被审计单位营业收入明细表，与总账核对一致后，计算并比较以下财务指标……）"
        @input="(v: string) => updateAuditProcess(v)"
      />
    </section>

    <!-- 指标分析表 -->
    <section class="sec">
      <!-- 工具栏（与D4-3一致：下拉导入导出 + AI一键填充） -->
      <div class="table-toolbar">
        <div class="toolbar-left">
          <el-dropdown size="small" trigger="click" :disabled="isReadonly">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload
                    :show-file-list="false"
                    accept=".xlsx,.xls"
                    :before-upload="handleImportUpload"
                    :disabled="importing"
                  >
                    <span>{{ importing ? '导入中...' : '导入数据' }}</span>
                  </el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tag size="small" type="info">共 {{ indicators.length }} 项指标</el-tag>
        </div>
        <div class="toolbar-right">
          <el-tooltip :content="aiAvailable ? 'AI一键填充所有指标的变动原因分析' : 'AI 服务暂不可用'" placement="top">
            <el-button size="small" type="success" plain
              :loading="aiLoadingKey === 'fill-analysis'"
              :disabled="isReadonly || !aiAvailable"
              @click="aiFillAllAnalysis">🤖 AI一键填充变动原因</el-button>
          </el-tooltip>
        </div>
      </div>

      <el-table :data="computedIndicators" border class="indicator-table"
        :header-cell-style="{ fontSize: '13px', fontWeight: '600', background: '#f5f7fa', textAlign: 'center' }">
        <el-table-column prop="name" label="指标名称" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tooltip v-if="row.formula" :content="`${row.formula}\n来源: ${row.source}`" placement="right" :show-after="200">
              <span class="has-formula">{{ row.name }}</span>
            </el-tooltip>
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期 ①" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-model="row.current" :controls="false" size="small" :disabled="isReadonly"
              :precision="2" class="num-input" @change="() => updateIndicator($index, 'current', row.current)" />
          </template>
        </el-table-column>
        <el-table-column label="上期 ②" width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-model="row.prior" :controls="false" size="small" :disabled="isReadonly"
              :precision="2" class="num-input" @change="() => updateIndicator($index, 'prior', row.prior)" />
          </template>
        </el-table-column>
        <el-table-column label="差异1 ③=(①-②)/②" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip :content="getTooltip(row, 'diff1')" placement="top" :show-after="200" :disabled="!row.formula">
              <span :class="['computed-val', { 'has-formula': row.formula, 'val-exceed': row.diff1 != null && Math.abs(row.diff1) > 0.3 }]">
                {{ fmtPercent(row.diff1) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="变化原因及合理性分析1 ④" min-width="160">
          <template #default="{ row, $index }">
            <el-input v-model="row.analysis1" size="small" :disabled="isReadonly" placeholder="分析"
              @input="() => updateIndicator($index, 'analysis1', row.analysis1)" />
          </template>
        </el-table-column>
        <el-table-column label="同行业公司平均值 ⑤" width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-model="row.industryAvg" :controls="false" size="small" :disabled="isReadonly"
              :precision="2" class="num-input" @change="() => updateIndicator($index, 'industryAvg', row.industryAvg)" />
          </template>
        </el-table-column>
        <el-table-column label="差异2 ⑥=(①-⑤)/⑤" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip :content="getTooltip(row, 'diff2')" placement="top" :show-after="200" :disabled="!row.formula">
              <span :class="['computed-val', { 'has-formula': row.formula, 'val-exceed': row.diff2 != null && Math.abs(row.diff2) > 0.3 }]">
                {{ fmtPercent(row.diff2) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="变化原因及合理性分析2 ⑦" min-width="160">
          <template #default="{ row, $index }">
            <el-input v-model="row.analysis2" size="small" :disabled="isReadonly" placeholder="分析"
              @input="() => updateIndicator($index, 'analysis2', row.analysis2)" />
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 三、审计说明 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">三、审计说明</h4>
        <div class="sec-actions">
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'"
              :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button>
          </el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-6-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="3" :model-value="auditNote" :disabled="isReadonly"
        placeholder="请输入审计说明..." @input="(v: string) => updateNote(v)" />
    </section>

    <!-- 四、审计结论 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">四、审计结论</h4>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'"
            :disabled="isReadonly || !aiAvailable" @click="generateConclusion">🤖 AI辅助</el-button>
        </el-tooltip>
      </div>
      <el-input type="textarea" :rows="3" :model-value="auditConclusion" :disabled="isReadonly"
        placeholder="请输入审计结论..." @input="(v: string) => updateConclusion(v)" />
    </section>
  
    </template>

    <!-- OnlyOffice 在线编辑 -->
    <template v-else>
      <div style="min-height: 600px; height: calc(100vh - 280px);">
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          sheet-name="重要指标分析D4-6"
          :readonly="isReadonly"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-indicator { padding: 16px; }
.sec { margin-bottom: 20px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 8px; }
.sec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sec-actions { display: flex; gap: 8px; }
.objective-list { padding: 10px 14px; background: #f5f7fa; border-radius: 6px; }
.objective-item { margin: 0 0 4px; font-size: var(--wp-font-size, 13px); color: #303133; line-height: 1.7; }
.objective-item:last-child { margin-bottom: 0; }
.indicator-table { font-size: var(--wp-font-size, 13px); }
.indicator-table :deep(.el-table__cell) { font-size: var(--wp-font-size, 13px); padding: 6px 0; }
.table-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.toolbar-left { display: flex; gap: 8px; }
.toolbar-right { display: flex; gap: 8px; }
.num-input { width: 100%; }
.num-input :deep(.el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.has-formula { border-bottom: 1px dashed #909399; cursor: help; }
.computed-val { font-size: var(--wp-font-size, 13px); }
.val-exceed { color: #f56c6c; font-weight: 600; }

.mode-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
