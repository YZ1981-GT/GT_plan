<script setup lang="ts">
/**
 * D4TabInterviewSummary 鈥?D4-30 瀹㈡埛璁胯皥璁板綍姹囨€昏〃
 *
 * 杞疆琛細琛?17涓璋堢淮搴︼紝鍒?N涓鎴?
 * 涓夋ā寮忥細鍗＄墖瑙嗗浘(閫愬鎴峰～鍐? / 鐭╅樀瑙嗗浘(瀵规瘮) / 鍦ㄧ嚎缂栬緫
 * 搴曢儴10鏉＄孩瀛楄璋堟牳瀵规彁绀?
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
// 瀵煎叆 xlsx 鎴愬姛鍚庨噸杞?allResponses锛堜富鍏ュ彛 provide锛夛紝鍚﹀垯鐣岄潰鍋滅暀鍦ㄦ棫鍊?
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// 鈹€鈹€鈹€ 璁胯皥缁村害瀹氫箟 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const INTERVIEW_FIELDS = [
  { key: 'time', label: '璁胯皥鏃堕棿' },
  { key: 'reason', label: '璁胯皥鍘熷洜', placeholder: '鍙戣浜虹X澶у鎴?鏈湡鏂板瀹㈡埛/閲囪喘浠锋牸寮傚父瀹㈡埛' },
  { key: 'method', label: '璁胯皥鏂瑰紡', placeholder: '瀹炲湴璧拌/瑙嗛璁胯皥/鐢佃瘽璁胯皥' },
  { key: 'regAddress', label: '琚璋堝叕鍙告敞鍐屽湴鍧€' },
  { key: 'visitAddress', label: '瀹炲湴璧拌鍏徃鍦板潃' },
  { key: 'interviewee', label: '鎺ュ彈璁胯皥浜哄憳鍙婅韩浠?, placeholder: '韬唤淇℃伅銆佽亴鍔′俊鎭€佸叿浣撹礋璐ｇ殑宸ヤ綔绛? },
  { key: 'auditor', label: '鍙備笌璁胯皥鐨勫璁′汉鍛? },
  { key: 'others', label: '鍙備笌璁胯皥鐨勫叾浠栦汉鍛? },
  { key: 'travelInfo', label: '璁胯皥浜哄憳琛岀▼淇℃伅', placeholder: '杞︾エ/鏈虹エ/浣忓鍙戠エ澶嶅嵃浠舵垨鐓х墖' },
  { key: 'onSiteConfirm', label: '鏄惁鐜板満鍑借瘉' },
  { key: 'keyPoints', label: '璁胯皥鍏虫敞瑕佺偣' },
  { key: 'contractCheck', label: '鍚堝悓鎵ц鏍稿鎯呭喌' },
  { key: 'amountMatch', label: '浜ゆ槗閲戦鏍稿鏄惁涓€鑷? },
  { key: 'balanceMatch', label: '寰€鏉ヤ綑棰濇牳瀵规槸鍚︿竴鑷? },
  { key: 'conclusion', label: '璁胯皥缁撹' },
  { key: 'indexRef', label: '璁胯皥琛ㄧ储寮? },
]

interface InterviewCustomer { id: string; name: string; fields: Record<string, string> }

// 鑷畾涔夌淮搴︼紙鐢ㄦ埛鍙坊鍔犻澶栨鏌ラ」锛屽搴旀簮妯℃澘涓?鈥︹€?琛岋級
const customDimensions = ref<{ key: string; label: string }[]>([])

const customers = ref<InterviewCustomer[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function loadData() {
  const r = props.allResponses.get('D4-30-customers')
  if (r?.remark) {
    try {
      const p = JSON.parse(r.remark)
      if (p && typeof p === 'object' && !Array.isArray(p)) {
        // 鏂版牸寮? { customers: [...], customDimensions: [...] }
        customers.value = p.customers || []
        customDimensions.value = p.customDimensions || []
        return
      }
      if (Array.isArray(p)) { customers.value = p; customDimensions.value = []; return }
    } catch {}
  }
  customers.value = []; customDimensions.value = []
}
function loadNote() { auditNote.value = props.allResponses.get('D4-30-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-30-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-30-customers')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-30-note')?.remark, loadNote, { immediate: true })

async function handleAddCustomer() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('璇疯緭鍏ュ鎴峰悕绉?, '娣诲姞璁胯皥瀹㈡埛', { confirmButtonText: '纭', cancelButtonText: '鍙栨秷', inputPattern: /\S+/, inputErrorMessage: '涓嶈兘涓虹┖' }); if (value?.trim()) { customers.value.push({ id: `iv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, name: value.trim(), fields: {} }); activeIdx.value = customers.value.length - 1; persistAll() } } catch {} }
function removeCustomer(id: string) { if (props.isReadonly) return; customers.value = customers.value.filter(c => c.id !== id); persistAll() }
function updateField(custId: string, fieldKey: string, value: string) { if (props.isReadonly) return; const c = customers.value.find(x => x.id === custId); if (c) { c.fields[fieldKey] = value; persistAll() } }
function updateName(id: string, name: string) { if (props.isReadonly) return; const c = customers.value.find(x => x.id === id); if (c) { c.name = name; persistAll() } }

async function addCustomDimension() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('璇疯緭鍏ヨ嚜瀹氫箟妫€鏌ラ」鍚嶇О', '娣诲姞妫€鏌ョ淮搴?, { confirmButtonText: '纭', cancelButtonText: '鍙栨秷', inputPattern: /\S+/, inputErrorMessage: '涓嶈兘涓虹┖' })
    if (value?.trim()) {
      const key = `custom_${Date.now().toString(36)}`
      customDimensions.value.push({ key, label: value.trim() })
      persistAll()
    }
  } catch {}
}
function removeCustomDimension(key: string) { if (props.isReadonly) return; customDimensions.value = customDimensions.value.filter(d => d.key !== key); persistAll() }

// 鍚堝苟鍥哄畾缁村害 + 鑷畾涔夌淮搴?
const allFields = computed(() => [...INTERVIEW_FIELDS, ...customDimensions.value.map(d => ({ key: d.key, label: d.label, placeholder: '' }))])

function persistAll() {
  props.allResponses.set('D4-30-customers', { item_id: 'D4-30-customers', conclusion: null, remark: JSON.stringify({ customers: customers.value, customDimensions: customDimensions.value }) })
  props.allResponses.set('D4-30-note', { item_id: 'D4-30-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-30-conclusion', { item_id: 'D4-30-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-30-customers','D4-30-note','D4-30-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-30-customers','D4-30-note','D4-30-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('鍗＄墖瑙嗗浘'); const modeOptions = ['鍗＄墖瑙嗗浘', '鐭╅樀瑙嗗浘', '鍦ㄧ嚎缂栬緫']
const activeIdx = ref(0)
const activeCustomer = computed(() => customers.value[activeIdx.value] || null)

const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 杈呭姪鐢熸垚' : 'AI 鏈嶅姟鏆備笉鍙敤')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '鍩轰簬瀹㈡埛璁胯皥姹囨€?D4-30)缁撴灉鐢熸垚瀹¤璇存槑', customerCount: customers.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 鏈敓鎴愬唴瀹?); return }; await ElMessageBox.confirm(t, 'AI 鐢熸垚', { confirmButtonText: '濉叆', cancelButtonText: '鍙栨秷', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 鐢熸垚澶辫触') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '鍩轰簬璁胯皥姹囨€荤粨鏋滅敓鎴愬璁＄粨璁?, noteText: auditNote.value, customerCount: customers.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 鏈敓鎴愬唴瀹?); return }; await ElMessageBox.confirm(t, 'AI 鐢熸垚', { confirmButtonText: '濉叆', cancelButtonText: '鍙栨秷', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 鐢熸垚澶辫触') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
async function handleImportFile(f: any) { const r = await importData('D4-30', f.raw || f); if (r) await reloadWorkpaperData?.() }
</script>

<template>
<div class="d4-interview-summary">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">瀵煎叆瀵煎嚭 鈻?/el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-30')">瀵煎嚭妯℃澘</el-dropdown-item><el-dropdown-item @click="exportData('D4-30')">瀵煎嚭鏁版嵁</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>瀵煎叆鏁版嵁</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-31" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-30-interview')">馃挰 澶嶆牳</el-button></div></div>

  <!-- 浠〃鏉?-->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ customers.length }}<span class="stat-unit">瀹?/span></div><div class="stat-label">宸茶璋堝鎴?/div></div>
  </div>

  <!-- 鈺愨晲鈺?鍗＄墖瑙嗗浘 鈺愨晲鈺?-->
  <template v-if="editorMode === '鍗＄墖瑙嗗浘'">
    <!-- 浣跨敤璇存槑 -->
    <div class="usage-guide">
      <span class="usage-icon">馃挕</span>
      <span class="usage-text">鐐瑰嚮涓嬫柟"娣诲姞瀹㈡埛"鍒涘缓璁胯皥璁板綍鍗＄墖锛岄€愰」濉啓璁胯皥鏃堕棿銆佹柟寮忋€佸叧娉ㄨ鐐圭瓑淇℃伅銆傚彲娣诲姞鑷畾涔夋鏌ラ」銆傚垏鎹?鐭╅樀瑙嗗浘"妯悜瀵规瘮澶氫釜瀹㈡埛鐨勮璋堟儏鍐点€?/span>
    </div>
    <div class="customer-tabs">
      <el-tabs v-model="activeIdx" type="card" @tab-remove="(name:any) => removeCustomer(customers[Number(name)]?.id)">
        <el-tab-pane v-for="(cust, idx) in customers" :key="cust.id" :label="cust.name||`瀹㈡埛${idx+1}`" :name="idx" :closable="!isReadonly" />
      </el-tabs>
    </div>
    <div v-if="activeCustomer" class="card-content">
      <div class="card-header"><el-input v-model="activeCustomer.name" size="default" :disabled="isReadonly" class="customer-name-input" @change="updateName(activeCustomer.id, activeCustomer.name)" /></div>
      <div v-for="field in allFields" :key="field.key" class="field-row">
        <label>{{ field.label }}</label>
        <el-input :model-value="activeCustomer.fields[field.key]||''" size="small" :disabled="isReadonly" :placeholder="field.placeholder||''" @input="(v:string)=>updateField(activeCustomer.id, field.key, v)" />
        <el-button v-if="customDimensions.some(d => d.key === field.key)" link type="danger" size="small" :disabled="isReadonly" @click="removeCustomDimension(field.key)" title="鍒犻櫎姝よ嚜瀹氫箟椤?>脳</el-button>
      </div>
      <div class="add-dimension-bar">
        <el-button size="small" text :disabled="isReadonly" @click="addCustomDimension">+ 娣诲姞鑷畾涔夋鏌ラ」</el-button>
      </div>
    </div>
    <el-empty v-else description="璇锋坊鍔犲鎴峰紑濮嬭褰曡璋? :image-size="80">
      <el-button type="primary" :disabled="isReadonly" @click="handleAddCustomer"><el-icon :size="14"><Plus /></el-icon> 娣诲姞瀹㈡埛</el-button>
    </el-empty>
  </template>

  <!-- 鈺愨晲鈺?鐭╅樀瑙嗗浘 鈺愨晲鈺?-->
  <template v-else-if="editorMode === '鐭╅樀瑙嗗浘'">
    <el-table :data="allFields" border class="matrix-table" max-height="550">
      <el-table-column label="椤圭洰" min-width="140" fixed><template #default="{ row }">{{ row.label }}</template></el-table-column>
      <el-table-column v-for="cust in customers" :key="cust.id" :label="cust.name" min-width="130" align="center"><template #default="{ row }"><span>{{ cust.fields[row.key] || '鈥? }}</span></template></el-table-column>
    </el-table>
    <div v-if="!customers.length" style="padding:20px 0;text-align:center;"><el-empty description="鏆傛棤璁胯皥鏁版嵁" :image-size="60" /></div>
  </template>

  <!-- 鈺愨晲鈺?鍦ㄧ嚎缂栬緫 鈺愨晲鈺?-->
  <template v-else-if="editorMode === '鍦ㄧ嚎缂栬緫'">
    <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="瀹㈡埛璁胯皥璁板綍姹囨€昏〃D4-30" :readonly="isReadonly" /></div>
  </template>

  <!-- 闈濷O鍏变韩鍖?-->
  <template v-if="editorMode !== '鍦ㄧ嚎缂栬緫'">
    <!-- 瀹¤鎰忚鍖?-->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">瀹¤鎰忚鍖?/span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">馃 AI杈呭姪璇存槑</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">馃 AI杈呭姪缁撹</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>瀹¤璇存槑</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="璁板綍璁胯皥鍙戠幇" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>瀹¤缁撹</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="缁煎悎鍒ゆ柇" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>

    <!-- 绾㈠瓧鎻愮ず锛堣璋堟牳瀵瑰拰娉ㄦ剰浜嬮」锛?-->
    <details class="tips-collapse">
      <summary class="tips-summary">鈿狅笍 璁胯皥鏍稿鍜屾敞鎰忎簨椤癸紙鎻愮ず锛?/summary>
      <div class="tips-body">
        <p class="tips-intro">鎻愮ず1锛氳蛋璁跨殑鑼冨洿鈥斺€斾富瑕佸鎴凤紙濡傚墠鍗佸悕瀹㈡埛锛夛紱鏂板鐨勪富瑕佸鎴凤紱瀛樺湪鐤戣檻鐨勯噸瑕佸鎴枫€?/p>
        <p class="tips-intro">鎻愮ず2锛氳璋堥渶鏍稿鍜屾敞鎰忎簨椤癸細</p>
        <ol class="tips-list">
          <li>璧拌鍦板潃涓庢敞鍐屽湴鍧€鏄惁涓€鑷达紵涓嶄竴鑷寸殑鍘熷洜鏄惁鍚堢悊锛熷叕鍙稿熀鏈儏鍐垫槸鍚︿笌宸ュ晢淇℃伅鏌ヨ涓€鑷达紵璧拌鍏徃鍦板潃鏄惁涓庣櫨搴﹀湴鍥剧瓑鏌ヨ璧拌鍦板潃涓€鑷达紵</li>
          <li>浜ゆ槗鍐呭鏄惁涓庤蛋璁垮叕鍙稿疄闄呬笟鍔¤寖鍥翠竴鑷达紵</li>
          <li>浜ゆ槗閲戦鏄惁涓庤蛋璁垮叕鍙歌妯★紙娉ㄥ唽璧勬湰銆佷汉鏁般€佽澶囨暟閲忕瓑锛夊尮閰嶏紵</li>
          <li>浜ゆ槗浠锋牸鏄惁涓庡悓琛屼笟绫讳技浜ゆ槗涓€鑷达紵</li>
          <li>鏄惁鏍稿疄璧拌瀵硅薄韬唤锛?/li>
          <li>鏄惁鏍规嵁璧拌鍏徃鍙婅璋堝璞″叿浣撴儏鍐典慨鏀硅璋堥棶鍗凤紵</li>
          <li>鏄惁鐜板満鍙栧緱鐩栧叕绔犵殑鍑借瘉鍥炲嚱锛堜氦鏄撱€佸線鏉ャ€佸叧鑱旀柟鍏崇郴纭锛夛紵</li>
          <li>鏄惁鍚屼负瀹㈡埛鍜屼緵搴斿晢锛熺悊鐢辨槸鍚﹀悎鐞嗭紵</li>
          <li>鏄惁瀛樺湪寮傚父鎯呭喌锛堝鍦板潃涓庤瀹¤鍗曚綅鍏宠仈鏂圭浉鍚屾垨鐩歌繎銆佸凡澶勪簬鍋滀骇鐘舵€併€佷骇鑳藉埄鐢ㄧ巼寮傚父銆佹棤娉曡瘉鏄庣浉鍏充骇鍝佹潵鑷瀹¤鍗曚綅锛夛紵</li>
          <li>淇濈暀璁胯皥瀵硅薄韬唤璇佸鍗颁欢銆佸悕鐗?宸ョ墝澶嶅嵃浠躲€佷笌璁胯皥瀵硅薄鍚堝奖锛堝巶鍖洪棬鍙ｃ€佷粨搴撱€佽溅闂寸瓑鍦帮級銆佽蛋璁垮叕鍙稿伐浣滅幇鍦虹収鐗囥€?/li>
        </ol>
      </div>
    </details>
  </template>
</div>
</template>

<style scoped>
.d4-interview-summary{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.stats-dashboard{display:flex;gap:12px;margin-bottom:16px;padding:12px 16px;background:linear-gradient(135deg,#f8f9fe 0%,#f0f4ff 100%);border-radius:10px;border:1px solid #e4e7ed}.stat-card{padding:8px 14px;min-width:100px;border-radius:8px;background:#fff;border:1px solid #ebeef5;box-shadow:0 1px 3px rgba(0,0,0,.04)}.stat-card.stat-primary{border-left:3px solid #409eff}.stat-value{font-size:18px;font-weight:700;color:#303133}.stat-unit{font-size:12px;color:#909399;margin-left:2px}.stat-label{font-size:12px;color:#909399;margin-top:2px}
.customer-tabs{display:flex;align-items:center;gap:8px;margin-bottom:12px}.customer-tabs :deep(.el-tabs){flex:1}.customer-tabs :deep(.el-tabs__header){margin-bottom:0}
.usage-guide{display:flex;align-items:flex-start;gap:8px;margin-bottom:14px;padding:10px 14px;background:#f0f9eb;border-radius:6px;border:1px solid #e1f3d8}.usage-icon{font-size:16px;flex-shrink:0;margin-top:1px}.usage-text{font-size:12px;color:#529b2e;line-height:1.6}
.card-content{border:1px solid #ebeef5;border-radius:8px;padding:16px;background:#fafbfc}.card-header{margin-bottom:12px}.customer-name-input{max-width:280px}.customer-name-input :deep(.el-input__inner){font-size:15px;font-weight:600}
.field-row{display:flex;align-items:center;gap:12px;margin-bottom:8px}.field-row label{min-width:140px;font-size:12px;color:#606266;flex-shrink:0}.field-row :deep(.el-input){flex:1}
.add-dimension-bar{margin-top:12px;padding-top:8px;border-top:1px dashed #e4e7ed}
.matrix-table{font-size: var(--wp-font-size, 13px);margin-bottom:20px}.matrix-table :deep(.el-table__cell){padding:5px 6px;font-size: var(--wp-font-size, 13px)}
:deep(.el-empty){padding:32px 0}
.audit-opinion-card{margin-top:20px;margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.tips-collapse{margin-bottom:16px;border-radius:6px;border:1px solid #fde2e2;border-left:3px solid #f56c6c;background:#fef0f0}.tips-summary{cursor:pointer;padding:10px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#f56c6c}.tips-body{padding:8px 14px 14px;font-size:12px;color:#606266;line-height:1.9}.tips-intro{margin-bottom:6px;font-weight:500}.tips-list{margin:0;padding-left:18px}.tips-list li{margin-bottom:3px}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
