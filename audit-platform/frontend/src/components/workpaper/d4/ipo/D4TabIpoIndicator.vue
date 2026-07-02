<script setup lang="ts">
/**
 * D4TabIpoIndicator — D4-22 主营业务收入重要指标分析表
 *
 * 固定12行KPI指标 × 动态列(本期/上期/N个同行业公司) + 合理性分析
 * 自动计算：人均创收/ROP/运输费率(虚线下划线+tooltip)
 * 双模式：表格视图 / 在线编辑
 * AI辅助审计意见 + 导入导出
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4KeyIndicator, INDICATOR_DEFINITIONS } from '../../composables/useD4KeyIndicator'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'

// ─── Props ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────
const {
  rows,
  peerCompanies,
  auditNote,
  auditConclusion,
  transportExpense,
  filledCount,
  totalIndicators,
  peerCount,
  analysisFilledCount,
  addPeer,
  removePeer,
  renamePeer,
  updateCell,
  updatePeerCell,
  updateTransportExpense,
  updateAuditNote,
  updateAuditConclusion,
} = useD4KeyIndicator({
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

// ─── Add peer company ────────────────────────────────────────────────
async function handleAddPeer() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入同行业公司名称', '添加同行业公司', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value?.trim()) addPeer(value.trim())
  } catch { /* cancelled */ }
}

// ─── AI opinion ──────────────────────────────────────────────────────
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
        task: '基于主营业务收入重要指标分析表(D4-22)的指标数据及同行业对比，生成审计说明',
        indicators: rows.value.filter(r => r.currentPeriod !== '').map(r => ({
          label: r.label, currentPeriod: r.currentPeriod, priorPeriod: r.priorPeriod,
        })),
        peerCount: peerCount.value,
        filledCount: filledCount.value,
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
        task: '基于重要指标分析结果及同行业对比，生成审计结论',
        noteText: auditNote.value || '',
        filledCount: filledCount.value,
        analysisFilledCount: analysisFilledCount.value,
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
function handleExportTemplate() { exportTemplate('D4-22') }
function handleExportData() { exportData('D4-22') }
async function handleImportFile(uploadFile: any) { await importData('D4-22', uploadFile.raw || uploadFile) }

// ─── AI batch fill analysis ─────────────────────────────────────────
const aiAnalysisLoading = ref(false)

async function genAllAnalysis() {
  if (props.isReadonly || !aiAvailable.value) return
  // 收集已填指标数据
  const filledIndicators = rows.value.filter(r => r.currentPeriod !== '' || r.priorPeriod !== '').map(r => ({
    key: r.key,
    label: r.label,
    currentPeriod: r.currentPeriod,
    priorPeriod: r.priorPeriod,
    peers: r.peers,
    isAutoCalc: r.isAutoCalc,
  }))
  if (!filledIndicators.length) { ElMessage.warning('请先填写指标数据后再生成分析'); return }

  aiAnalysisLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'policy-evaluation',
      existingContent: '',
      relatedContext: {
        task: '为主营业务收入重要指标分析表的每个指标逐项生成合理性分析。请以JSON数组返回，每项包含key(指标key)和analysis(分析文本)字段。分析应关注本期vs上期的变动趋势、与同行业的对比差异、变动是否与业务发展一致。',
        indicators: filledIndicators,
        peerNames: peerCompanies.value.map(p => p.name),
        format: 'json_array',
      },
    }, { _silent: true } as any)
    const content = res.data?.data?.content ?? res.data?.content ?? ''
    if (!content) { ElMessage.warning('AI 未生成内容'); return }

    // 尝试解析JSON数组
    let analyses: { key: string; analysis: string }[] = []
    try {
      // 尝试直接解析
      const parsed = JSON.parse(content)
      if (Array.isArray(parsed)) analyses = parsed
    } catch {
      // 尝试提取代码块中的JSON
      const match = content.match(/\[[\s\S]*\]/)
      if (match) {
        try { analyses = JSON.parse(match[0]) } catch { /* fallback */ }
      }
    }

    if (analyses.length) {
      // 预览确认
      const previewText = analyses.slice(0, 3).map((a: any) => `• ${rows.value.find(r => r.key === a.key)?.label || a.key}: ${a.analysis}`).join('\n') + (analyses.length > 3 ? `\n...共${analyses.length}项` : '')
      await ElMessageBox.confirm(previewText, `AI 生成 · 合理性分析（${analyses.length}项）`, { confirmButtonText: '全部填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '650px', whiteSpace: 'pre-wrap' } } as any)
      // 填入
      for (const item of analyses) {
        if (item.key && item.analysis) {
          updateCell(item.key, 'analysis', item.analysis)
        }
      }
      ElMessage.success(`已填入${analyses.length}项合理性分析`)
    } else {
      // 降级：把整段文本填到审计说明
      await ElMessageBox.confirm(content, 'AI 生成（未能解析为逐项格式，将填入审计说明）', { confirmButtonText: '填入说明', cancelButtonText: '取消', type: 'warning', customStyle: { maxWidth: '600px' } })
      updateAuditNote(content)
    }
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiAnalysisLoading.value = false }
}

// ─── Progress rate ───────────────────────────────────────────────────
const progressRate = computed(() => Math.round((filledCount.value / totalIndicators.value) * 100))
</script>

<template>
  <div class="d4-key-indicator">
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
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-22-indicator')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 统计仪表板 ═══ -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ filledCount }}/{{ totalIndicators }}</div>
        <div class="stat-label">已填指标</div>
      </div>
      <div class="stat-card stat-peer">
        <div class="stat-value">{{ peerCount }}<span class="stat-unit">家</span></div>
        <div class="stat-label">同行业公司</div>
      </div>
      <div class="stat-card" :class="progressRate >= 80 ? 'stat-ok' : 'stat-warn'">
        <div class="stat-value">{{ progressRate }}%</div>
        <div class="stat-label">完成度</div>
      </div>
      <div class="stat-card stat-analysis">
        <div class="stat-value">{{ analysisFilledCount }}<span class="stat-unit">项</span></div>
        <div class="stat-label">已分析</div>
      </div>
    </div>

    <!-- ═══ 非OO内容区 ═══ -->
    <template v-if="editorMode !== '在线编辑'">
      <!-- 方法论折叠 -->
      <details class="methodology-collapse">
        <summary class="methodology-summary">📖 审计目标与重要指标分析过程（点击展开）</summary>
        <div class="methodology-body">
          <p class="method-objective"><strong>审计目标：</strong></p>
          <ol class="method-objectives">
            <li>利润表中记录的主营业务收入已发生，且与被审计单位有关；</li>
            <li>所有应当记录的营业收入均已记录；</li>
            <li>与主营业务收入有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。</li>
          </ol>
          <p class="method-process"><strong>审计过程：</strong></p>
          <p class="method-red-hint">向被审计单位询问，并获取年度预算、业绩考核指标等资料。</p>
        </div>
      </details>

      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="向被审计单位询问，获取年度预算、业绩考核指标等资料" placement="bottom" :show-after="300">
          <span class="guide-chip">①获取预算与考核资料</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="填写本期各项经营指标数据（部分可从试算表自动取数）" placement="bottom" :show-after="300">
          <span class="guide-chip">②填写本期指标</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="录入上期数据用于期间对比分析" placement="bottom" :show-after="300">
          <span class="guide-chip">③填写上期数据</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="添加同行业可比公司，获取其公开数据用于横向对比" placement="bottom" :show-after="300">
          <span class="guide-chip">④添加同行业对比</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="逐项分析各指标合理性，填写分析说明" placement="bottom" :show-after="300">
          <span class="guide-chip">⑤合理性分析</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="汇总形成审计说明与结论" placement="bottom" :show-after="300">
          <span class="guide-chip">⑥审计意见</span>
        </el-tooltip>
      </div>

      <!-- ═══ 运输费用输入（自动计算分子） + AI预填合理性分析 ═══ -->
      <div class="transport-input">
        <span class="transport-label">运输费用（用于自动计算"运输费用/营业收入"）：</span>
        <el-input-number
          :model-value="typeof transportExpense === 'string' ? parseFloat(String(transportExpense)) || undefined : (transportExpense as number) || undefined"
          size="small" :controls="false" :disabled="isReadonly" style="width:160px;" placeholder="输入运输费用"
          @change="(v: any) => updateTransportExpense(v ?? '')"
        />
        <div class="transport-spacer"></div>
        <el-tooltip :content="aiAvailable ? 'AI一键预填所有指标的合理性分析' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" type="primary" plain :loading="aiAnalysisLoading" :disabled="isReadonly || !aiAvailable" @click="genAllAnalysis">🤖 AI预填合理性分析</el-button>
        </el-tooltip>
      </div>

      <!-- ═══ 同行业公司管理 ═══ -->
      <div class="peer-management">
        <span class="peer-label">同行业公司：</span>
        <el-tag v-for="peer in peerCompanies" :key="peer.id" closable :disable-transitions="false"
          :disabled="isReadonly" @close="removePeer(peer.id)" size="default" type="info">
          {{ peer.name }}
        </el-tag>
        <el-button size="small" :disabled="isReadonly" @click="handleAddPeer">
          <el-icon :size="14"><Plus /></el-icon> 添加
        </el-button>
      </div>

      <!-- ═══ 主表格 ═══ -->
      <el-table :data="rows" border class="indicator-table">
        <!-- 指标名称（固定列） -->
        <el-table-column label="指标名称" min-width="220" fixed>
          <template #default="{ row }">
            <span :class="{ 'auto-calc-label': row.isAutoCalc }">
              {{ row.label }}
            </span>
            <el-tooltip v-if="row.formula" :content="'公式：' + row.formula" placement="right">
              <span class="formula-hint">ƒ</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 本期 -->
        <el-table-column label="本期" min-width="130" align="right" class-name="col-current">
          <template #default="{ row }">
            <span v-if="row.isAutoCalc" class="auto-calc-value" :title="'自动计算：' + (row.formula || '')">
              {{ row.currentPeriod || '—' }}
            </span>
            <el-input v-else v-model="row.currentPeriod" size="small" :disabled="isReadonly"
              @change="updateCell(row.key, 'currentPeriod', row.currentPeriod)" />
          </template>
        </el-table-column>

        <!-- 上期 -->
        <el-table-column label="上期" min-width="130" align="right" class-name="col-prior">
          <template #default="{ row }">
            <el-input v-model="row.priorPeriod" size="small" :disabled="isReadonly"
              @change="updateCell(row.key, 'priorPeriod', row.priorPeriod)" />
          </template>
        </el-table-column>

        <!-- 动态同行业公司列 -->
        <el-table-column
          v-for="(peer, pIdx) in peerCompanies" :key="peer.id"
          :label="peer.name" min-width="120" align="right" class-name="col-peer"
        >
          <template #header>
            <div class="peer-header">
              <el-input v-model="peer.name" size="small" :disabled="isReadonly" class="peer-name-input"
                @change="renamePeer(peer.id, peer.name)" />
            </div>
          </template>
          <template #default="{ row }">
            <el-input :model-value="row.peers[pIdx] ?? ''" size="small" :disabled="isReadonly"
              @change="(v: string) => updatePeerCell(row.key, pIdx, v)" />
          </template>
        </el-table-column>

        <!-- 合理性分析 -->
        <el-table-column label="合理性分析" min-width="200" class-name="col-analysis">
          <template #default="{ row }">
            <el-input v-model="row.analysis" size="small" :disabled="isReadonly"
              placeholder="分析变动原因及合理性"
              @change="updateCell(row.key, 'analysis', row.analysis)" />
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
              <GtIndexChip value="wp:D4-2" :context-project-id="projectId" />
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
            <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote"
              :disabled="isReadonly" placeholder="结合各项指标的纵向(期间)对比和横向(同行业)对比，分析主营业务收入变动的合理性" @input="(v: string) => updateAuditNote(v)" />
          </div>
          <div class="opinion-field">
            <label>四、审计结论</label>
            <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion"
              :disabled="isReadonly" placeholder="基于重要指标分析结果，综合判断主营业务收入变动是否合理、是否存在异常波动需进一步追查" @input="(v: string) => updateAuditConclusion(v)" />
          </div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示</summary>
        <ol class="tips-list">
          <li>向被审计单位询问，并获取年度预算、业绩考核指标等资料。</li>
          <li>"本期"填写审计年度数据，"上期"填写上一年度可比数据。</li>
          <li>同行业公司应选取业务模式、规模相近的上市公司或行业报告数据。</li>
          <li>自动计算指标（人均创收/ROP/运输费率）以虚线标识，需先填写基础数据后自动生成。</li>
          <li>合理性分析应关注：变动幅度是否合理、与同行业是否一致、与业务发展趋势是否匹配。</li>
          <li>对于异常波动指标，应结合其他底稿（D4-1审定表、D4-2收入明细）进一步追查原因。</li>
        </ol>
      </details>
    </template>

    <!-- ═══ OnlyOffice 模式 ═══ -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container">
        <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId"
          sheet-name="重要指标分析表D4-22" :readonly="isReadonly" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-key-indicator { padding: 16px 20px; font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 100px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-peer { border-left: 3px solid #9b59b6; }
.stat-card.stat-ok { border-left: 3px solid #67c23a; }
.stat-card.stat-warn { border-left: 3px solid #e6a23c; }
.stat-card.stat-analysis { border-left: 3px solid #409eff; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }

.methodology-collapse { margin-bottom: 14px; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c; background: #fffbf0; }
.methodology-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #b88230; }
.methodology-body { padding: 8px 14px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
.method-objectives { margin: 4px 0 8px 16px; padding: 0; }
.method-objectives li { margin-bottom: 2px; }
.method-process { margin-bottom: 4px; }
.method-red-hint { color: #f56c6c; font-style: italic; padding: 4px 8px; background: #fef0f0; border-radius: 3px; }

.guide-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.guide-strip-label { font-weight: 600; color: #67c23a; font-size: 12px; }
.guide-chip { background: #fff; border: 1px solid #c2e7b0; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #529b2e; cursor: help; }
.guide-chip:hover { background: #f0f9eb; }
.guide-arrow { color: #a8abb2; font-size: 12px; }

.transport-input { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 14px; background: #f5f7fa; border-radius: 6px; border: 1px solid #ebeef5; }
.transport-label { font-size: 12px; color: #606266; white-space: nowrap; }
.transport-spacer { flex: 1; }

.peer-management { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; padding: 8px 14px; background: #faf5ff; border-radius: 6px; border: 1px solid #e8d5f5; }
.peer-label { font-size: 12px; color: #9b59b6; font-weight: 500; }

.indicator-table { font-size: 13px; margin-bottom: 24px; }
.indicator-table :deep(.el-table__cell) { padding: 6px 4px; }
.indicator-table :deep(.col-current .el-table__cell) { background-color: #f0f9eb !important; }
.indicator-table :deep(.col-prior .el-table__cell) { background-color: #fdf6ec !important; }
.indicator-table :deep(.col-peer .el-table__cell) { background-color: #f5f0ff !important; }
.indicator-table :deep(.col-analysis .el-table__cell) { background-color: #f0f5ff !important; }

.auto-calc-label { color: #909399; font-style: italic; }
.formula-hint { display: inline-block; margin-left: 4px; font-size: 11px; color: #409eff; font-weight: 600; font-style: italic; cursor: help; border-bottom: 1px dashed #409eff; }
.auto-calc-value { color: #409eff; font-weight: 500; border-bottom: 1px dashed #a0cfff; cursor: help; }

.peer-header { display: flex; align-items: center; }
.peer-name-input { max-width: 100px; }
.peer-name-input :deep(.el-input__inner) { font-size: 12px; text-align: center; }

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
