<script setup lang="ts">
/**
 * D4TabRelatedPrice — D4-21 关联方销售收入情况及价格公允性分析
 *
 * 多级表头：基本信息(浅绿) / 本年度分析(浅蓝) / 上年度参考(浅紫) / 备注
 * 双模式：表格视图 / 在线编辑
 * 自动计算：销售额占比 / 差异率(关联vs非关联) / 差异率(关联vs公允)
 * >10%黄色 / >20%红色行高亮
 * AI辅助审计意见 + OCR + 导入导出
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4RelatedPrice, type RelatedPriceRow } from '../../composables/useD4RelatedPrice'
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
  relatedSalesTotal,
  proportionToRevenue,
  auditNote,
  auditConclusion,
  getDiffRateColor,
  addRow,
  removeRow,
  updateCell,
} = useD4RelatedPrice({
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

// ─── Stats ───────────────────────────────────────────────────────────
const highDiffCount = computed(() => rows.value.filter(r => Math.abs(r.priceDiffRate) > 10).length)

// ─── Formatters ──────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (!v) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPercent(v: number): string {
  if (!v && v !== 0) return '—'
  if (v === 0) return '—'
  return v.toFixed(2) + '%'
}

// ─── Row class: >10% yellow / >20% red ──────────────────────────────
function getRowClass({ row }: { row: RelatedPriceRow }): string {
  const color = getDiffRateColor(row.priceDiffRate)
  if (color === 'red') return 'row-red'
  if (color === 'yellow') return 'row-yellow'
  return ''
}

// ─── OCR ─────────────────────────────────────────────────────────────
async function handleOcrUpload(rowId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) { ElMessage.info('OCR完成，未识别到可填充字段'); return }
    // Auto-fill recognized fields
    if (fields.customerName || fields.relatedCustomer) updateCell(rowId, 'relatedCustomer', String(fields.customerName || fields.relatedCustomer))
    if (fields.product || fields.productName) updateCell(rowId, 'product', String(fields.product || fields.productName))
    if (fields.relatedPrice || fields.unitPrice) updateCell(rowId, 'relatedPrice', Number(fields.relatedPrice || fields.unitPrice) || 0)
    if (fields.nonRelatedPrice) updateCell(rowId, 'nonRelatedPrice', Number(fields.nonRelatedPrice) || 0)
    ElMessage.success('OCR结果已填入')
  } catch { ElMessage.warning('OCR识别失败') }
}

// ─── AI opinion generation ───────────────────────────────────────────
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'related-price',
      existingContent: auditNote.value || '',
      relatedContext: {
        task: '基于关联方销售收入及价格公允性分析结果，生成审计说明',
        relatedSalesTotal: relatedSalesTotal.value,
        proportionToRevenue: proportionToRevenue.value,
        rowCount: rows.value.length,
        highDiffCount: highDiffCount.value,
      },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    auditNote.value = text
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
        task: '基于关联方价格公允性分析结果，生成审计结论',
        noteText: auditNote.value || '',
        relatedSalesTotal: relatedSalesTotal.value,
        proportionToRevenue: proportionToRevenue.value,
        rowCount: rows.value.length,
        highDiffCount: highDiffCount.value,
      },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    auditConclusion.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiConclusionLoading.value = false }
}

// ─── Import/Export ───────────────────────────────────────────────────
function handleExportTemplate() { exportTemplate('D4-21') }
function handleExportData() { exportData('D4-21') }
async function handleImportFile(uploadFile: any) { await importData('D4-21', uploadFile.raw || uploadFile) }
</script>

<template>
  <div class="d4-related-price">
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
        <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-21-price')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 统计仪表板 ═══ -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ relatedSalesTotal ? fmtAmount(relatedSalesTotal) : '—' }}</div>
        <div class="stat-label">关联方销售合计</div>
      </div>
      <div class="stat-card stat-rate">
        <div class="stat-value">{{ proportionToRevenue > 0 ? fmtPercent(proportionToRevenue) : '—' }}</div>
        <div class="stat-label">占收入比例</div>
      </div>
      <div class="stat-card" :class="highDiffCount > 0 ? 'stat-warn' : 'stat-ok'">
        <div class="stat-value">{{ highDiffCount }}<span class="stat-unit">笔</span></div>
        <div class="stat-label">价格差异率>10%</div>
      </div>
    </div>

    <!-- ═══ 非OO内容区 ═══ -->
    <template v-if="editorMode !== '在线编辑'">
      <!-- 方法论折叠 -->
      <details class="methodology-collapse">
        <summary class="methodology-summary">📖 审计目标与关联方价格公允性分析过程（点击展开）</summary>
        <div class="methodology-body">
          <p class="method-objective"><strong>审计目标：</strong>关联方交易价格公允性——关联方销售收入的定价是否公允、是否存在利用关联交易操纵利润的情况。</p>
          <div class="method-steps">
            <p class="method-step"><span class="step-num">步骤一</span>获取关联方清单及本期关联方销售明细（产品、数量、金额、单价等）。</p>
            <p class="method-step"><span class="step-num">步骤二</span>获取同类产品非关联方销售单价作为可比基准。</p>
            <p class="method-step"><span class="step-num">步骤三</span>计算关联方销售单价与非关联方单价的差异率，标注异常项。</p>
            <p class="method-step"><span class="step-num">步骤四</span>分析差异原因，评价关联方交易定价的公允性并形成审计结论。</p>
          </div>
        </div>
      </details>

      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="从关联方清单中识别本期有销售交易的关联方" placement="bottom" :show-after="300">
          <span class="guide-chip">①获取关联方清单</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="记录各关联方的产品名称、销售数量、销售额等交易数据" placement="bottom" :show-after="300">
          <span class="guide-chip">②记录交易数据</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="获取非关联方同类产品销售单价及可比公允价格，计算差异率" placement="bottom" :show-after="300">
          <span class="guide-chip">③比较价格公允性</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="分析差异率超过阈值项目的原因，判断是否合理" placement="bottom" :show-after="300">
          <span class="guide-chip">④评价差异原因</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="填写审计说明与结论（可AI辅助生成）" placement="bottom" :show-after="300">
          <span class="guide-chip">⑤填审计意见</span>
        </el-tooltip>
      </div>

      <!-- ═══ 主表格 ═══ -->
      <el-table :data="rows" border stripe class="price-table" :row-class-name="getRowClass">
        <el-table-column label="序号" width="55" align="center" fixed>
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>

        <!-- 基本信息分组（浅绿） -->
        <el-table-column label="基本信息" align="center" class-name="col-basic">
          <el-table-column label="关联方客户名称" min-width="130">
            <template #default="{ row }">
              <el-input v-model="row.relatedCustomer" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'relatedCustomer', row.relatedCustomer)" />
            </template>
          </el-table-column>
          <el-table-column label="关联关系" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.reason" size="small" :disabled="isReadonly" placeholder="如：母子公司" @change="updateCell(row.rowId, 'reason', row.reason)" />
            </template>
          </el-table-column>
          <el-table-column label="产品名称" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.product" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'product', row.product)" />
            </template>
          </el-table-column>
          <el-table-column label="销售数量" min-width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.relatedPrice" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'relatedPrice', row.relatedPrice)" />
            </template>
          </el-table-column>
          <el-table-column label="销售额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.nonRelatedPrice" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'nonRelatedPrice', row.nonRelatedPrice)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 本年度分析分组（浅蓝） -->
        <el-table-column label="本年度分析" align="center" class-name="col-analysis">
          <el-table-column label="销售额占比" min-width="90" align="right">
            <template #default="{ row }">
              <span class="auto-calc" title="自动计算：该产品销售额÷同类产品销售额合计">{{ row.nonRelatedPrice && relatedSalesTotal ? ((row.nonRelatedPrice / relatedSalesTotal) * 100).toFixed(2) + '%' : '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="平均单价" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="(row as any).avgUnitPrice" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'avgUnitPrice', (row as any).avgUnitPrice)" />
            </template>
          </el-table-column>
          <el-table-column label="非关联方平均单价" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-model="(row as any).nonRelatedAvgPrice" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'nonRelatedAvgPrice', (row as any).nonRelatedAvgPrice)" />
            </template>
          </el-table-column>
          <el-table-column label="差异率" min-width="80" align="right">
            <template #default="{ row }">
              <span :class="['auto-calc', getDiffRateColor(row.priceDiffRate)]" title="自动计算：(关联单价-非关联单价)÷非关联单价×100%">{{ fmtPercent(row.priceDiffRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="可比公允价格" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="(row as any).fairPrice" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'fairPrice', (row as any).fairPrice)" />
            </template>
          </el-table-column>
          <el-table-column label="差异率(公允)" min-width="90" align="right">
            <template #default="{ row }">
              <span class="auto-calc" :class="(row as any).fairPrice && (row as any).avgUnitPrice ? getDiffRateColor((((row as any).avgUnitPrice - (row as any).fairPrice) / (row as any).fairPrice) * 100) : ''" title="自动计算：(关联单价-公允价格)÷公允价格×100%">{{ (row as any).fairPrice && (row as any).avgUnitPrice ? (((( row as any).avgUnitPrice - (row as any).fairPrice) / (row as any).fairPrice) * 100).toFixed(2) + '%' : '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 上年度参考分组（浅紫） -->
        <el-table-column label="上年度参考" align="center" class-name="col-prior">
          <el-table-column label="上年度占比" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model="(row as any).priorProportion" size="small" :disabled="isReadonly" placeholder="如 5.2%" @change="updateCell(row.rowId, 'priorProportion', (row as any).priorProportion)" />
            </template>
          </el-table-column>
          <el-table-column label="上年度平均单价" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="(row as any).priorAvgPrice" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.rowId, 'priorAvgPrice', (row as any).priorAvgPrice)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 备注列 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="updateCell(row.rowId, 'remark', row.remark)" />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column label="操作" width="90" fixed="right" align="center">
          <template #default="{ row }">
            <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly"
              @change="(f: any) => handleOcrUpload(row.rowId, f.raw || f)" style="display:inline-block;">
              <el-button link size="small" :disabled="isReadonly" title="OCR识别附件">📎</el-button>
            </el-upload>
            <el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)">
              <template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 阈值图例 + 添加行 -->
      <div class="add-row-bar">
        <div class="threshold-legend">
          <span class="legend-item yellow">■ 差异率>10%（关注）</span>
          <span class="legend-item red">■ 差异率>20%（重大偏离）</span>
        </div>
        <el-button :disabled="isReadonly" @click="addRow"><el-icon :size="16" style="margin-right:4px;"><Plus /></el-icon>添加行</el-button>
      </div>

      <!-- ═══ 审计意见区 ═══ -->
      <el-card class="audit-opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-chips">
              <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
              <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
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
            <label>审计说明</label>
            <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" v-model="auditNote" :disabled="isReadonly" placeholder="记录关联方销售收入情况、价格公允性分析过程、差异原因及合理性判断" />
          </div>
          <div class="opinion-field">
            <label>审计结论</label>
            <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" v-model="auditConclusion" :disabled="isReadonly" placeholder="基于价格公允性分析结果，判断关联方交易定价是否公允、是否存在利用关联交易操纵利润的情形" />
          </div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示</summary>
        <ol class="tips-list">
          <li>获取关联方清单，确认本期发生销售交易的关联方客户。</li>
          <li>逐笔记录各关联方交易的产品名称、销售数量、销售额及平均单价。</li>
          <li>获取同类产品对非关联方的销售平均单价作为可比基准，计算差异率。</li>
          <li>对差异率超过10%的项目应追查原因，分析是否因批量折扣、合同约定等合理因素导致。</li>
          <li>综合判断关联方交易定价是否公允，是否存在利用关联交易转移利润的风险。</li>
        </ol>
      </details>
    </template>

    <!-- ═══ OnlyOffice 模式 ═══ -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container">
        <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId"
          sheet-name="关联方销售情况及价格分析D4-21" :readonly="isReadonly" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-related-price { padding: 16px 20px; font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 130px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-rate { border-left: 3px solid #67c23a; }
.stat-card.stat-warn { border-left: 3px solid #f56c6c; }
.stat-card.stat-ok { border-left: 3px solid #67c23a; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }
.methodology-collapse { margin-bottom: 14px; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c; background: #fffbf0; }
.methodology-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #b88230; }
.methodology-body { padding: 8px 14px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
.method-objective { margin-bottom: 8px; }
.method-steps { padding-left: 4px; }
.method-step { margin-bottom: 4px; }
.step-num { display: inline-block; background: #e6a23c; color: #fff; border-radius: 3px; padding: 1px 6px; font-size: 11px; margin-right: 6px; }
.guide-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.guide-strip-label { font-weight: 600; color: #67c23a; font-size: 12px; }
.guide-chip { background: #fff; border: 1px solid #c2e7b0; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #529b2e; cursor: help; }
.guide-chip:hover { background: #f0f9eb; }
.guide-arrow { color: #a8abb2; font-size: 12px; }
.price-table { font-size: 13px; }
.price-table :deep(.el-table__cell) { padding: 6px 0; }
.price-table :deep(.col-basic .el-table__cell) { background-color: #f0faf0 !important; }
.price-table :deep(.col-analysis .el-table__cell) { background-color: #f0f5ff !important; }
.price-table :deep(.col-prior .el-table__cell) { background-color: #f8f0ff !important; }
.auto-calc { color: #909399; font-style: italic; border-bottom: 1px dashed #c0c4cc; cursor: help; }
.auto-calc.red { color: #f56c6c; font-weight: 600; font-style: normal; }
.auto-calc.yellow { color: #e6a23c; font-weight: 600; font-style: normal; }
:deep(.row-red td) { background-color: #fef0f0 !important; }
:deep(.row-yellow td) { background-color: #fdf6ec !important; }
.add-row-bar { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 24px; }
.threshold-legend { display: flex; gap: 16px; font-size: 12px; color: #606266; }
.legend-item.yellow { color: #e6a23c; }
.legend-item.red { color: #f56c6c; }
.audit-opinion-card { margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-actions { margin-left: auto; display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #f56c6c; }
.tips-list { margin: 8px 14px 12px; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
</style>
