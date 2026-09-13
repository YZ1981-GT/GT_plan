<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabFundFlow 鈥?D4-32 瀹㈡埛銆佷緵搴斿晢绛夎祫閲戞祦姘存鏌?
 *
 * 6缁勫姩鎬佽琛ㄦ牸锛堜富瑕佷緵搴斿晢/涓昏瀹㈡埛/鎺ц偂鑲′笢/瀹為檯鎺у埗浜?鍏抽敭绠＄悊浜哄憳/鍏朵粬鍏宠仈鏂癸級
 * 姣忕粍鍏变韩9鍒楋細搴忓彿/鍗曚綅鍚嶇О/鏈湡浜ゆ槗閲戦/鍗犳瘮/寮€鎴烽摱琛?璐﹀彿/鑾峰彇閫斿緞/鏄惁寮傚父/绱㈠紩鍙?
 * 寮傚父琛岀孩鑹查珮浜?+ AI杈呭姪 + 鍙屾ā寮廜O + 瀵煎叆瀵煎嚭
 */
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import D4IpoFindingWriteback, { type D4IpoFinding } from './D4IpoFindingWriteback.vue'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
// 瀵煎叆 xlsx 鎴愬姛鍚庨噸杞?allResponses锛堜富鍏ュ彛 provide锛夛紝鍚﹀垯鐣岄潰鍋滅暀鍦ㄦ棫鍊?
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// 鈹€鈹€鈹€ Types 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const GROUPS = [
  { key: 'supplier', label: '涓昏渚涘簲鍟?, color: '#f0faf0' },
  { key: 'customer', label: '涓昏瀹㈡埛', color: '#f0f5ff' },
  { key: 'shareholder', label: '鎺ц偂鑲′笢', color: '#faf5ff' },
  { key: 'controller', label: '瀹為檯鎺у埗浜?, color: '#fdf6ec' },
  { key: 'management', label: '鍏抽敭绠＄悊浜哄憳', color: '#fef0f0' },
  { key: 'related', label: '鍏朵粬鍏宠仈鏂?, color: '#f5f5f5' },
]

interface FlowRow {
  id: string; name: string; amount: number | string; ratio: string
  bank: string; account: string; method: string; hasAnomaly: string; indexRef: string
}
interface GroupData { key: string; rows: FlowRow[] }

const groups = ref<GroupData[]>(GROUPS.map(g => ({ key: g.key, rows: [] })))
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(name?: string): FlowRow {
  return { id: `ff-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, name: name || '', amount: '', ratio: '', bank: '', account: '', method: '', hasAnomaly: '', indexRef: '' }
}

function loadData() {
  const r = props.allResponses.get('D4-32-groups')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (Array.isArray(p) && p.length === 6) { groups.value = p; return } } catch {} }
  groups.value = GROUPS.map(g => ({ key: g.key, rows: [] }))
}
function loadNote() { auditNote.value = props.allResponses.get('D4-32-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-32-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-32-groups')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-32-note')?.remark, loadNote, { immediate: true })

async function addRow(groupKey: string) {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('璇疯緭鍏ュ崟浣嶅悕绉版垨濮撳悕', '娣诲姞妫€鏌ュ璞?, { confirmButtonText: '纭', cancelButtonText: '鍙栨秷', inputPattern: /\S+/, inputErrorMessage: '涓嶈兘涓虹┖' })
    if (value?.trim()) { const g = groups.value.find(x => x.key === groupKey); if (g) { g.rows.push(createRow(value.trim())); persistAll() } }
  } catch {}
}
function removeRow(groupKey: string, rowId: string) { if (props.isReadonly) return; const g = groups.value.find(x => x.key === groupKey); if (g) { g.rows = g.rows.filter(r => r.id !== rowId); persistAll() } }
function updateCell(groupKey: string, rowId: string, field: keyof FlowRow, value: any) { if (props.isReadonly) return; const g = groups.value.find(x => x.key === groupKey); if (!g) return; const row = g.rows.find(r => r.id === rowId); if (row) { (row as any)[field] = value; persistAll() } }

function persistAll() {
  props.allResponses.set('D4-32-groups', { item_id: 'D4-32-groups', conclusion: null, remark: JSON.stringify(groups.value) })
  props.allResponses.set('D4-32-note', { item_id: 'D4-32-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-32-conclusion', { item_id: 'D4-32-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-32-groups','D4-32-note','D4-32-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-32-groups','D4-32-note','D4-32-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('琛ㄦ牸瑙嗗浘'); const modeOptions = ['琛ㄦ牸瑙嗗浘', '鍦ㄧ嚎缂栬緫']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 杈呭姪鐢熸垚' : 'AI 鏈嶅姟鏆備笉鍙敤')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const totalRows = groups.value.reduce((s, g) => s + g.rows.length, 0); const anomalyCount = groups.value.reduce((s, g) => s + g.rows.filter(r => r.hasAnomaly === '鏄?).length, 0); const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '鍩轰簬璧勯噾娴佹按妫€鏌?D4-32)缁撴灉鐢熸垚瀹¤璇存槑', totalRows, anomalyCount } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 鏈敓鎴愬唴瀹?); return }; await ElMessageBox.confirm(t, 'AI 鐢熸垚', { confirmButtonText: '濉叆', cancelButtonText: '鍙栨秷', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 鐢熸垚澶辫触') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '鍩轰簬璧勯噾娴佹按妫€鏌ョ粨鏋滅敓鎴愬璁＄粨璁?, noteText: auditNote.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 鏈敓鎴愬唴瀹?); return }; await ElMessageBox.confirm(t, 'AI 鐢熸垚', { confirmButtonText: '濉叆', cancelButtonText: '鍙栨秷', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 鐢熸垚澶辫触') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
async function handleImportFile(f: any) { const r = await importData('D4-32', f.raw || f); if (r) await reloadWorkpaperData?.() }

// Stats
const totalRows = computed(() => groups.value.reduce((s, g) => s + g.rows.length, 0))
const anomalyCount = computed(() => groups.value.reduce((s, g) => s + g.rows.filter(r => r.hasAnomaly === '鏄?).length, 0))

function rowClassName({ row }: { row: FlowRow }) { return row.hasAnomaly === '鏄? ? 'row-anomaly' : '' }

// 鈹€鈹€鈹€ 椋庨櫓鍙戠幇锛氫粎銆屾槸鍚﹀彂鐜板紓甯镐氦鏄?'鏄?銆嶆爣璁帮紙'鍚?/绌轰笉鍒ゅ紓甯革級鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const GROUP_LABEL: Record<string, string> = { supplier: '涓昏渚涘簲鍟?, customer: '涓昏瀹㈡埛', shareholder: '鎺ц偂鑲′笢', controller: '瀹為檯鎺у埗浜?, management: '鍏抽敭绠＄悊浜哄憳', related: '鍏朵粬鍏宠仈鏂? }
const riskFindings = computed<D4IpoFinding[]>(() => {
  const out: D4IpoFinding[] = []
  for (const g of groups.value) {
    for (const r of g.rows) {
      if (r.hasAnomaly === '鏄?) {
        out.push({ key: `d4-32-${r.id}`, label: `${GROUP_LABEL[g.key] || g.key} 路 ${r.name || '瀵硅薄'}锛氬紓甯歌祫閲戝線鏉, indexRef: r.indexRef || 'D4-32' })
      }
    }
  }
  return out
})
</script>

<template>
<div class="d4-fund-flow">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">瀵煎叆瀵煎嚭 鈻?/el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-32')">瀵煎嚭妯℃澘</el-dropdown-item><el-dropdown-item @click="exportData('D4-32')">瀵煎嚭鏁版嵁</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>瀵煎叆鏁版嵁</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><D4IpoFindingWriteback wp-code="D4-32" :all-responses="allResponses" :is-readonly="isReadonly" :findings="riskFindings" /><GtIndexChip value="wp:E1-31" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-32-fund')">馃挰 澶嶆牳</el-button></div></div>

  <!-- 浠〃鏉?-->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ totalRows }}<span class="stat-unit">鏉?/span></div><div class="stat-label">妫€鏌ヨ褰?/div></div>
    <div class="stat-card" :class="anomalyCount > 0 ? 'stat-warn' : 'stat-ok'"><div class="stat-value">{{ anomalyCount }}<span class="stat-unit">鏉?/span></div><div class="stat-label">鍙戠幇寮傚父</div></div>
  </div>

  <template v-if="editorMode !== '鍦ㄧ嚎缂栬緫'">
    <!-- 鏂规硶璁?-->
    <details class="methodology-collapse">
      <summary class="methodology-summary">馃摉 瀹¤鐩爣涓庤祫閲戞祦姘存鏌ヨ繃绋嬶紙鐐瑰嚮灞曞紑锛?/summary>
      <div class="methodology-body">
        <p><strong>瀹¤鐩爣锛?/strong>鍒╂鼎琛ㄤ腑璁板綍鐨勮惀涓氭敹鍏ュ凡鍙戠敓锛屼笖涓庤瀹¤鍗曚綅鏈夊叧锛屽凡璁板綍浜庢伆褰撶殑璐︽埛銆?/p>
        <p><strong>瀹¤杩囩▼锛?/strong></p>
        <p class="method-step"><span class="step-num">1</span>鑾峰彇琚璁″崟浣嶄富瑕佷緵搴斿晢銆佸鎴疯祫閲戞祦姘达紝妫€鏌ユ槸鍚︿笌琚璁″崟浣嶆帶鑲¤偂涓溿€佸疄闄呮帶鍒朵汉浠ュ強鍏朵粬鍏宠仈鏂瑰瓨鍦ㄥぇ棰濊祫閲戝線鏉ワ紝濡傛湁锛屽簲纭畾璇ョ瓑璧勯噾寰€鏉ユ槸鍚︿笌琚璁″崟浣嶆敹鍏ヨ垶寮婃湁鍏炽€?/p>
        <p class="method-step"><span class="step-num">2</span>鑾峰彇琚璁″崟浣嶆帶鑲¤偂涓溿€佸疄闄呮帶鍒朵汉銆佸叧閿鐞嗕汉鍛樹互鍙婂叾浠栧叧鑱旀柟閾惰璐︽埛璧勯噾娴佹按锛屾鏌ユ槸鍚﹀瓨鍦ㄥ墠杩板悇鏂规彁渚涜祫閲戦厤鍚堣瀹¤鍗曚綅铏氭瀯鏀跺叆鐨勬儏鍐点€?/p>
      </div>
    </details>

    <!-- 鈺愨晲鈺?6缁勮〃鏍?鈺愨晲鈺?-->
    <div v-for="(group, gIdx) in GROUPS" :key="group.key" class="group-section" :style="{ borderLeftColor: group.color }">
      <div class="group-header">
        <span class="group-title">{{ group.label }}</span>
        <el-button size="small" :disabled="isReadonly" @click="addRow(group.key)"><el-icon :size="12"><Plus /></el-icon> 娣诲姞</el-button>
      </div>
      <el-table v-if="groups[gIdx].rows.length" :data="groups[gIdx].rows" border stripe size="small" class="flow-table" :row-class-name="rowClassName">
        <el-table-column label="#" width="40" align="center"><template #default="{ $index }">{{ $index+1 }}</template></el-table-column>
        <el-table-column label="鍗曚綅鍚嶇О/濮撳悕" min-width="110"><template #default="{ row }"><el-input v-model="row.name" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'name',row.name)" /></template></el-table-column>
        <el-table-column label="鏈湡浜ゆ槗閲戦" min-width="110" align="right"><template #default="{ row }"><WpAmountInput v-model="row.amount" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(group.key,row.id,'amount',row.amount)" /></template></el-table-column>
        <el-table-column label="鍗犳瘮" width="70"><template #default="{ row }"><el-input v-model="row.ratio" size="small" :disabled="isReadonly" placeholder="%" @change="updateCell(group.key,row.id,'ratio',row.ratio)" /></template></el-table-column>
        <el-table-column label="寮€鎴烽摱琛? min-width="100"><template #default="{ row }"><el-input v-model="row.bank" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'bank',row.bank)" /></template></el-table-column>
        <el-table-column label="璐﹀彿" min-width="120"><template #default="{ row }"><el-input v-model="row.account" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'account',row.account)" /></template></el-table-column>
        <el-table-column label="鑾峰彇閫斿緞" min-width="90"><template #default="{ row }"><el-input v-model="row.method" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'method',row.method)" /></template></el-table-column>
        <el-table-column label="寮傚父" width="65" align="center"><template #default="{ row }"><el-select v-model="row.hasAnomaly" size="small" :disabled="isReadonly" placeholder="鈥? @change="updateCell(group.key,row.id,'hasAnomaly',row.hasAnomaly)"><el-option label="鏄? value="鏄? /><el-option label="鍚? value="鍚? /></el-select></template></el-table-column>
        <el-table-column label="绱㈠紩" width="65"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'indexRef',row.indexRef)" /></template></el-table-column>
        <el-table-column width="45" align="center"><template #default="{ row }"><el-popconfirm title="鍒犻櫎锛? @confirm="removeRow(group.key,row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">脳</el-button></template></el-popconfirm></template></el-table-column>
      </el-table>
      <div v-else class="group-empty">鏆傛棤璁板綍锛岀偣鍑?娣诲姞"鎸夐挳鏂板妫€鏌ュ璞?/div>
    </div>

    <!-- 瀹¤鎰忚鍖?-->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">瀹¤鎰忚鍖?/span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">馃 AI杈呭姪璇存槑</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">馃 AI杈呭姪缁撹</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>涓夈€佸璁¤鏄?/label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="璁板綍璧勯噾娴佹按妫€鏌ヤ腑鍙戠幇鐨勫紓甯告儏鍐? @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>鍥涖€佸璁＄粨璁?/label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="缁煎悎鍒ゆ柇鏄惁瀛樺湪璧勯噾閰嶅悎铏氭瀯鏀跺叆鐨勬儏鍐? @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <template v-if="editorMode==='鍦ㄧ嚎缂栬緫'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="瀹㈡埛銆佷緵搴斿晢绛夎祫閲戞祦姘存鏌4-32" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-fund-flow{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.stats-dashboard{display:flex;gap:12px;margin-bottom:16px;padding:12px 16px;background:linear-gradient(135deg,#f8f9fe 0%,#f0f4ff 100%);border-radius:10px;border:1px solid #e4e7ed}.stat-card{padding:8px 14px;min-width:100px;border-radius:8px;background:#fff;border:1px solid #ebeef5;box-shadow:0 1px 3px rgba(0,0,0,.04)}.stat-card.stat-primary{border-left:3px solid #409eff}.stat-card.stat-warn{border-left:3px solid #f56c6c}.stat-card.stat-ok{border-left:3px solid #67c23a}.stat-value{font-size:18px;font-weight:700;color:#303133}.stat-unit{font-size:12px;color:#909399;margin-left:2px}.stat-label{font-size:12px;color:#909399;margin-top:2px}
.methodology-collapse{margin-bottom:14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0}.methodology-summary{cursor:pointer;padding:8px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#b88230}.methodology-body{padding:8px 14px 12px;font-size:12px;color:#606266;line-height:1.8}.method-step{margin-bottom:6px}.step-num{display:inline-block;background:#e6a23c;color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-right:6px}
.group-section{margin-bottom:16px;border-left:3px solid #e4e7ed;padding-left:12px;border-radius:0 6px 6px 0}
.group-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.group-title{font-size: var(--wp-font-size, 13px);font-weight:600;color:#303133}
.flow-table{font-size: var(--wp-font-size, 13px)}.flow-table :deep(.el-table__cell){padding:4px 3px}.flow-table :deep(.row-anomaly td){background-color:#fef0f0 !important}
.group-empty{padding:12px;text-align:center;font-size:12px;color:#c0c4cc;background:#fafbfc;border-radius:4px;border:1px dashed #e4e7ed}
.audit-opinion-card{margin-top:20px;margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
