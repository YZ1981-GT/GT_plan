<script setup lang="ts">
/**
 * D4TabOtherMargin — D4-33 其他业务毛利率分析表
 *
 * 固定16行(12月+合计+上年数+变动额+变动比例) × 动态业务类型列(每类3子列:收入/成本/毛利率)
 * 毛利率=(收入-成本)/收入 自动计算；合计=12月之和；变动额=合计-上年；变动比例=变动额/上年
 * 双模式 + AI + 导入导出
 */
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

interface BizType { id: string; name: string }
interface MonthEntry { revenue: number | string; cost: number | string }
interface StoreData { bizTypes: BizType[]; months: Record<string, MonthEntry[]>; priorYear: Record<string, MonthEntry> }

const MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
const store = ref<StoreData>({ bizTypes: [], months: {}, priorYear: {} })
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function pn(v: any): number { if (!v || v === '') return 0; const n = parseFloat(String(v)); return isNaN(n) ? 0 : n }
function fmtMargin(rev: number, cost: number): string { if (!rev) return '—'; return ((rev - cost) / rev * 100).toFixed(2) + '%' }
function fmtAmt(v: number): string { return v ? v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—' }

// 获取某业务类型某月数据
function getMonth(bizId: string, monthIdx: number): MonthEntry { return store.value.months[bizId]?.[monthIdx] || { revenue: '', cost: '' } }
function getPrior(bizId: string): MonthEntry { return store.value.priorYear[bizId] || { revenue: '', cost: '' } }

// 合计（12月之和）
function getTotal(bizId: string, field: 'revenue' | 'cost'): number {
  const arr = store.value.months[bizId] || []
  return arr.reduce((s, m) => s + pn(m[field]), 0)
}

function loadData() {
  const r = props.allResponses.get('D4-33-data')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (p?.bizTypes) { store.value = p; return } } catch {} }
  // 默认预填3个业务类型（对齐源模板）
  const defaultTypes: BizType[] = [
    { id: 'biz-rent-fixed', name: '出租固定资产' },
    { id: 'biz-rent-intangible', name: '出租无形资产' },
    { id: 'biz-sell-material', name: '销售材料' },
  ]
  const months: Record<string, MonthEntry[]> = {}
  const priorYear: Record<string, MonthEntry> = {}
  for (const t of defaultTypes) {
    months[t.id] = Array.from({ length: 12 }, () => ({ revenue: '', cost: '' }))
    priorYear[t.id] = { revenue: '', cost: '' }
  }
  store.value = { bizTypes: defaultTypes, months, priorYear }
}
function loadNote() { auditNote.value = props.allResponses.get('D4-33-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-33-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-33-data')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-33-note')?.remark, loadNote, { immediate: true })

async function addBizType() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入业务类型名称', '添加其他业务类型', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' })
    if (value?.trim()) {
      const id = `biz-${Date.now().toString(36)}`
      store.value.bizTypes.push({ id, name: value.trim() })
      store.value.months[id] = Array.from({ length: 12 }, () => ({ revenue: '', cost: '' }))
      store.value.priorYear[id] = { revenue: '', cost: '' }
      persistAll()
    }
  } catch {}
}
function removeBizType(id: string) {
  if (props.isReadonly) return
  store.value.bizTypes = store.value.bizTypes.filter(b => b.id !== id)
  delete store.value.months[id]
  delete store.value.priorYear[id]
  persistAll()
}

function updateMonth(bizId: string, monthIdx: number, field: 'revenue' | 'cost', value: any) {
  if (props.isReadonly) return
  if (!store.value.months[bizId]) store.value.months[bizId] = Array.from({ length: 12 }, () => ({ revenue: '', cost: '' }))
  store.value.months[bizId][monthIdx][field] = value
  persistAll()
}
function updatePrior(bizId: string, field: 'revenue' | 'cost', value: any) {
  if (props.isReadonly) return
  if (!store.value.priorYear[bizId]) store.value.priorYear[bizId] = { revenue: '', cost: '' }
  store.value.priorYear[bizId][field] = value
  persistAll()
}

function persistAll() {
  props.allResponses.set('D4-33-data', { item_id: 'D4-33-data', conclusion: null, remark: JSON.stringify(store.value) })
  props.allResponses.set('D4-33-note', { item_id: 'D4-33-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-33-conclusion', { item_id: 'D4-33-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-33-data','D4-33-note','D4-33-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-33-data','D4-33-note','D4-33-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于其他业务毛利率分析(D4-33)生成审计说明', bizTypeCount: store.value.bizTypes.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于毛利率分析结果生成审计结论', noteText: auditNote.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
</script>

<template>
<div class="d4-other-margin">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-33')">导出模板</el-dropdown-item><el-dropdown-item @click="exportData('D4-33')">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-33',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-3" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-33-margin')">💬 复核</el-button></div></div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 业务类型管理 -->
    <div class="biz-management">
      <span class="biz-label">业务类型：</span>
      <el-tag v-for="biz in store.bizTypes" :key="biz.id" closable :disable-transitions="false" :disabled="isReadonly" @close="removeBizType(biz.id)" size="default" type="info">{{ biz.name }}</el-tag>
      <el-button size="small" :disabled="isReadonly" @click="addBizType"><el-icon :size="14"><Plus /></el-icon> 添加</el-button>
    </div>

    <!-- 矩阵表格（横向滚动） -->
    <div class="table-wrapper" v-if="store.bizTypes.length">
      <table class="margin-table" border="1">
        <thead>
          <tr class="header-row-1">
            <th rowspan="2" class="col-month">月份</th>
            <th colspan="3" class="col-total">合计</th>
            <th v-for="biz in store.bizTypes" :key="biz.id" colspan="3" class="col-biz">{{ biz.name }}</th>
          </tr>
          <tr class="header-row-2">
            <th>收入</th><th>成本</th><th>毛利率</th>
            <template v-for="biz in store.bizTypes" :key="biz.id+'h'"><th>收入</th><th>成本</th><th>毛利率</th></template>
          </tr>
        </thead>
        <tbody>
          <!-- 12月 -->
          <tr v-for="(m, mIdx) in MONTHS" :key="mIdx">
            <td class="col-month">{{ m }}</td>
            <!-- 合计列（自动汇总所有业务类型） -->
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).revenue), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).cost), 0)) }}</td>
            <td class="auto-cell margin-cell">{{ fmtMargin(store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).revenue), 0), store.bizTypes.reduce((s, b) => s + pn(getMonth(b.id, mIdx).cost), 0)) }}</td>
            <!-- 各业务类型 -->
            <template v-for="biz in store.bizTypes" :key="biz.id+mIdx">
              <td><input type="number" :value="getMonth(biz.id, mIdx).revenue || ''" :disabled="isReadonly" @change="(e: any) => updateMonth(biz.id, mIdx, 'revenue', e.target.value)" /></td>
              <td><input type="number" :value="getMonth(biz.id, mIdx).cost || ''" :disabled="isReadonly" @change="(e: any) => updateMonth(biz.id, mIdx, 'cost', e.target.value)" /></td>
              <td class="auto-cell margin-cell">{{ fmtMargin(pn(getMonth(biz.id, mIdx).revenue), pn(getMonth(biz.id, mIdx).cost)) }}</td>
            </template>
          </tr>
          <!-- 合计行 -->
          <tr class="summary-row">
            <td class="col-month">合计</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'revenue'), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'cost'), 0)) }}</td>
            <td class="auto-cell margin-cell">{{ fmtMargin(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'revenue'), 0), store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'cost'), 0)) }}</td>
            <template v-for="biz in store.bizTypes" :key="biz.id+'t'">
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'revenue')) }}</td>
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'cost')) }}</td>
              <td class="auto-cell margin-cell">{{ fmtMargin(getTotal(biz.id, 'revenue'), getTotal(biz.id, 'cost')) }}</td>
            </template>
          </tr>
          <!-- 上年数 -->
          <tr class="prior-row">
            <td class="col-month">上年数</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).revenue), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).cost), 0)) }}</td>
            <td class="auto-cell margin-cell">{{ fmtMargin(store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).revenue), 0), store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).cost), 0)) }}</td>
            <template v-for="biz in store.bizTypes" :key="biz.id+'p'">
              <td><input type="number" :value="getPrior(biz.id).revenue || ''" :disabled="isReadonly" @change="(e: any) => updatePrior(biz.id, 'revenue', e.target.value)" /></td>
              <td><input type="number" :value="getPrior(biz.id).cost || ''" :disabled="isReadonly" @change="(e: any) => updatePrior(biz.id, 'cost', e.target.value)" /></td>
              <td class="auto-cell margin-cell">{{ fmtMargin(pn(getPrior(biz.id).revenue), pn(getPrior(biz.id).cost)) }}</td>
            </template>
          </tr>
          <!-- 变动额 -->
          <tr class="delta-row">
            <td class="col-month">变动额</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'revenue'), 0) - store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).revenue), 0)) }}</td>
            <td class="auto-cell">{{ fmtAmt(store.bizTypes.reduce((s, b) => s + getTotal(b.id, 'cost'), 0) - store.bizTypes.reduce((s, b) => s + pn(getPrior(b.id).cost), 0)) }}</td>
            <td class="auto-cell margin-cell">—</td>
            <template v-for="biz in store.bizTypes" :key="biz.id+'d'">
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'revenue') - pn(getPrior(biz.id).revenue)) }}</td>
              <td class="auto-cell">{{ fmtAmt(getTotal(biz.id, 'cost') - pn(getPrior(biz.id).cost)) }}</td>
              <td class="auto-cell margin-cell">—</td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <el-empty v-else description="请先添加业务类型" :image-size="60"><el-button type="primary" :disabled="isReadonly" @click="addBizType"><el-icon :size="14"><Plus /></el-icon> 添加业务类型</el-button></el-empty>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="分析各业务类型毛利率变动的合理性" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断其他业务收入毛利率是否合理" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="其他业务毛利率分析表D4-33" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-other-margin{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.biz-management{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px;padding:8px 14px;background:#faf5ff;border-radius:6px;border:1px solid #e8d5f5}.biz-label{font-size:12px;color:#9b59b6;font-weight:500}
.table-wrapper{overflow-x:auto;margin-bottom:24px;border-radius:6px;border:1px solid #ebeef5}
.margin-table{width:100%;border-collapse:collapse;font-size: var(--wp-font-size, 13px);min-width:600px}
.margin-table th,.margin-table td{padding:6px 8px;border:1px solid #ebeef5;text-align:center;white-space:nowrap}
.margin-table thead{background:#f5f7fa}
.header-row-1 th{font-weight:600;font-size: var(--wp-font-size, 13px)}
.header-row-2 th{font-size:12px;font-weight:400;color:#606266}
.col-month{font-weight:500;background:#fafbfc;min-width:50px;text-align:center}
.col-total{background:#f0faf0;color:#303133}
.col-biz{background:#f0f5ff;color:#303133}
.auto-cell{color:#909399;font-style:italic;background:#fafbfc}
.margin-cell{font-weight:500}
.summary-row td{background:#f0f9eb !important;font-weight:600}
.prior-row td{background:#fdf6ec !important}
.delta-row td{background:#f0f5ff !important}
.margin-table input{width:80px;border:1px solid #dcdfe6;border-radius:3px;padding:2px 6px;font-size: var(--wp-font-size, 13px);text-align:right;outline:none}
.margin-table input:focus{border-color:#409eff}
.margin-table input:disabled{background:#f5f7fa;color:#909399;border-color:#ebeef5}
.audit-opinion-card{margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
:deep(.el-empty){padding:32px 0}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
