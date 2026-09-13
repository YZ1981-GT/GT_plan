<script setup lang="ts">
/**
 * D4TabInterviewDetail 鈥?D4-31 瀹㈡埛璁胯皥璁板綍
 *
 * 缁撴瀯鍖栬璋堥棶鍗凤細4澶х珷鑺?+ 澶氶€?鍗曢€?鏉′欢灞曞紑
 * 鍏冧俊鎭?鈫?鍙楄浜轰粙缁?鈫?瀹㈡埛鍩烘湰鎯呭喌 鈫?涓氬姟鎯呭喌(7闂? 鈫?鍏宠仈鍏崇郴(3闂?
 * + 闄勪欢娓呭崟 + 绛惧瓧鍖?+ 鎵胯澹版槑 + CAS18鎻愮ず
 * AI杈呭姪鐢熸垚璁胯皥闂嵎鍐呭 + 鍙屾ā寮廜O
 */
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import D4IpoFindingWriteback, { type D4IpoFinding } from './D4IpoFindingWriteback.vue'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
// 瀵煎叆 xlsx 鎴愬姛鍚庨噸杞?allResponses锛堜富鍏ュ彛 provide锛夛紝鍚﹀垯鐣岄潰鍋滅暀鍦ㄦ棫鍊?
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
async function handleImportFile(f: any) { const r = await importData('D4-31', f.raw || f); if (r) await reloadWorkpaperData?.() }

// 鈹€鈹€鈹€ 闂嵎鏁版嵁妯″瀷 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
interface InterviewData {
  // 鍏冧俊鎭?
  target: string; timePlace: string; interviewee: string; interviewer: string
  // 涓€銆佸彈璁夸汉浠嬬粛
  introduction: string
  // 浜屻€佸鎴峰熀鏈儏鍐?
  companyName: string; regCapital: string; establishDate: string; bizNature: string
  legalRep: string; equityStructure: string
  // 涓夈€佷笟鍔℃儏鍐?
  q1_relation: string[]  // 澶氶€?
  q2a_payment: string    // 瀹㈡埛閲囪喘缁撶畻
  q2b_collection: string // 瀹㈡埛閿€鍞粨绠?
  q3a_hasContract: string // 鏄?鍚?
  q3b_quality: string
  q3c_returnClause: string // 鏄?鍚?
  q3d_returnAmount: string
  q3e_acceptance: string
  q3f_hasRebate: string  // 鏄?鍚?
  q3f_rebateMethod: string
  q3f_rebateAmount: string
  q3g_finalSold: string  // 鏄?鍚?
  q4_otherFunds: string  // 鏄?鍚?
  q5_otherMatters: string
  // 鍥涖€佸叧鑱斿叧绯?
  q6_hasShares: string   // 鏄?鍚?
  q6_hasPosition: string // 鏄?鍚?
  q6_hasTransaction: string // 鏄?鍚?
  // 绛惧瓧
  signInterviewee: string; signAuditor: string; signOther: string; signDate: string
}

const defaultData = (): InterviewData => ({
  target: '', timePlace: '', interviewee: '', interviewer: '',
  introduction: '',
  companyName: '', regCapital: '', establishDate: '', bizNature: '', legalRep: '', equityStructure: '',
  q1_relation: [], q2a_payment: '', q2b_collection: '',
  q3a_hasContract: '', q3b_quality: '', q3c_returnClause: '', q3d_returnAmount: '',
  q3e_acceptance: '', q3f_hasRebate: '', q3f_rebateMethod: '', q3f_rebateAmount: '',
  q3g_finalSold: '', q4_otherFunds: '', q5_otherMatters: '',
  q6_hasShares: '', q6_hasPosition: '', q6_hasTransaction: '',
  signInterviewee: '', signAuditor: '', signOther: '', signDate: '',
})

const formData = ref<InterviewData>(defaultData())
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function loadData() {
  const r = props.allResponses.get('D4-31-interview')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (p && typeof p === 'object') { formData.value = { ...defaultData(), ...p }; return } } catch {} }
  formData.value = defaultData()
}
watch(() => props.allResponses.get('D4-31-interview')?.remark, loadData, { immediate: true })

function persistAll() {
  props.allResponses.set('D4-31-interview', { item_id: 'D4-31-interview', conclusion: null, remark: JSON.stringify(formData.value) })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debounceTimer = null; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: [props.allResponses.get('D4-31-interview')].filter(Boolean) } })) }, 2000)
}
function update(field: keyof InterviewData, value: any) { if (props.isReadonly) return; (formData.value as any)[field] = value; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: [props.allResponses.get('D4-31-interview')].filter(Boolean) } })) } })

// 鈹€鈹€鈹€ 璁胯皥绾㈡棗鍙戠幇锛堜粎鏄惧紡'鏄?/鍏宠仈鍏崇郴鏍囪锛泀5 鍏朵粬浜嬮」闈炵┖浣滅暀鐥曞€欓€夛紝浜哄伐璁ゅ畾鍚庢墠鎺級鈹€鈹€鈹€
const riskFindings = computed<D4IpoFinding[]>(() => {
  const d = formData.value
  const out: D4IpoFinding[] = []
  const rel = Array.isArray(d.q1_relation) ? d.q1_relation : []
  if (rel.some(r => r.includes('渚涘簲鍟?) || r.includes('鍏宠仈鏂?))) {
    out.push({ key: 'd4-31-relation', label: `涓氬姟鍏崇郴绾㈡棗锛?{rel.filter(r => r.includes('渚涘簲鍟?) || r.includes('鍏宠仈鏂?)).join('銆?)}`, indexRef: 'D4-31' })
  }
  if (d.q4_otherFunds === '鏄?) out.push({ key: 'd4-31-otherfunds', label: '闄ら噰璐瀛樺湪鍏朵粬璧勯噾寰€鏉?, indexRef: 'D4-31' })
  if (d.q6_hasShares === '鏄?) out.push({ key: 'd4-31-shares', label: '鍏宠仈鏂瑰湪瀹㈡埛鎸佹湁鑲′唤', indexRef: 'D4-31' })
  if (d.q6_hasPosition === '鏄?) out.push({ key: 'd4-31-position', label: '鍏宠仈鏂瑰湪瀹㈡埛鎷呬换鑱屽姟', indexRef: 'D4-31' })
  if (d.q6_hasTransaction === '鏄?) out.push({ key: 'd4-31-transaction', label: '鍏宠仈鏂逛笌瀹㈡埛瀛樺湪浜ゆ槗', indexRef: 'D4-31' })
  if (d.q5_otherMatters && d.q5_otherMatters.trim()) out.push({ key: 'd4-31-other', label: `鍏朵粬閲嶈浜嬮」锛?{d.q5_otherMatters.trim().slice(0, 30)}`, indexRef: 'D4-31' })
  return out
})

const editorMode = ref<string>('闂嵎瑙嗗浘'); const modeOptions = ['闂嵎瑙嗗浘', '鍦ㄧ嚎缂栬緫']
const activeSection = ref('meta')
const showExample = ref(false)

// AI
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiLoading = ref(false)

async function aiGenerateIntro() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'interview-questions',
      existingContent: formData.value.introduction || '',
      relatedContext: { task: '鏍规嵁瀹㈡埛鍩烘湰鎯呭喌鐢熸垚璁胯皥浜轰粙缁嶆ā鏉挎枃瀛?, companyName: formData.value.companyName, target: formData.value.target },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (t) { await ElMessageBox.confirm(t, 'AI 鐢熸垚', { confirmButtonText: '濉叆', cancelButtonText: '鍙栨秷', type: 'info', customStyle: { maxWidth: '600px' } }); update('introduction', t) }
    else ElMessage.warning('AI 鏈敓鎴愬唴瀹?)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 鐢熸垚澶辫触') }
  finally { aiLoading.value = false }
}

// 閫夐」瀹氫箟
const RELATION_OPTIONS = ['瀹㈡埛鏄粓绔鎴?, '瀹㈡埛鏄粡閿€鍟?瀹㈡埛)', '瀹㈡埛鏄緵搴斿晢', '瀹㈡埛鏃㈡槸瀹㈡埛鍙堟槸渚涘簲鍟?, '瀹㈡埛鏄疉BC鐨勫叧鑱旀柟']
const PAYMENT_OPTIONS = ['棰勪粯娆炬柟寮?, '璐у埌浠樻鏂瑰紡', '璧婇攢鏂瑰紡', '棰勪粯娆炬柟寮忓拰璧婇攢鏂瑰紡鍏兼湁']
const COLLECTION_OPTIONS = ['棰勬敹娆炬柟寮?, '璐у埌鏀舵鏂瑰紡', '璧婇攢鏂瑰紡', '棰勬敹娆炬柟寮忓拰璧婇攢鏂瑰紡鍏兼湁']
const QUALITY_OPTIONS = ['鑹ソ', '涓€鑸?, '浜у搧璐ㄩ噺涓嶇ǔ瀹?, '浜у搧璐ㄩ噺宸?]
const RETURN_AMOUNT_OPTIONS = ['鏃?, '20涓囧厓浠ヤ笅', '20-50涓囧厓', '50-100涓囧厓', '100涓囧厓浠ヤ笂']
const ACCEPTANCE_OPTIONS = ['妫€楠屽悎鏍煎悗璁￠噺鍏ュ簱绛炬敹纭鏀跺埌璐х墿', '鐩存帴璁￠噺鍏ュ簱绛炬敹纭鏀跺埌璐х墿', '鍏朵粬鏂瑰紡璇锋弿杩?]
const REBATE_METHOD_OPTIONS = ['鐜伴噾', '鍏朵粬鏂瑰紡']
const REBATE_AMOUNT_OPTIONS = ['10涓囧厓浠ヤ笅', '10-50涓囧厓', '50-100涓囧厓', '100涓囧厓浠ヤ笂']

// 妗堜緥涓氦鏄撴牳瀵硅〃鏁版嵁
const exampleTradeItems = [
  { seq: 1, item: '浜ゆ槗妯″紡', info: '鍖呴攢', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 2, item: '浜ゆ槗鏍囩殑', info: 'AAA鏉愭枡', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 3, item: '浜ゆ槗瑙勬ā', info: '500-800鍚紙鍚◣閲戦绾?000-8000涓囷級', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 4, item: '浠樻鏂瑰紡', info: '閾惰鎵垮厬姹囩エ鎴栭摱琛岃浆璐?, source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 5, item: '璐︽湡鏃堕棿', info: '涓庡悎鍚屾潯娆句竴鑷?, source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 6, item: '浠樻鏈熼檺', info: '鍗佷釜鏈堜互鍐咃紝鍩烘湰鍦ㄦ湀涔嬪唴鍙戣揣锛堜竴鑸瘡鏈堝彂涓€娆¤揣锛?, source: '鍚堝悓鏉℃涓哄崄涓伐涔嬪唴' },
  { seq: 7, item: '璐﹂噾杩斿埄', info: '缁撳瓨宸楂樹簬鑻ヨ秴杩?7000涓囷紝鎸夊叏骞存湡鍒濆樊棰濅綑棰濆綋鏈堬紝鎸夊勾褰掕繕姣忓勾杩涜鍚堝悓閲戦', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 8, item: '璐﹂噾姘村钩', info: '鐣ラ珮浜庡悓琛屼笟閿€鍞按骞筹紝琛屼笟骞冲潎涓?.8-5%', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 9, item: '杩愯緭鏂瑰紡鍙婅垂鐢ㄦ壙鎷?, info: '鐏溅杩愯緭涓轰富锛屽皯閲忔苯杩?鍙夎溅杩愯緭锛涘彂杩愭椂鑷彁锛岃繍璐圭敱涔版柟XXX璐熸媴', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 10, item: '浜や粯鏂瑰紡', info: 'XYZ鏀跺埌璐э紝绛惧瓧纭鍗冲彲/浜や粯瀹屾瘯', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 11, item: '璐ㄩ噺淇濊瘉', info: '鏀惰揣楠屾敹鍚庡崄涓湀', source: '涓庡悎鍚屾潯娆句竴鑷? },
  { seq: 12, item: '楠屾敹鎴栨楠?, info: '鍑哄叿鏀舵嵁鍗冲彲鍒拌处璁ゆ敹鍏ユ/鏈?, source: '涓庡嚟璇佹鏌ョ粨璁轰竴鑷? },
  { seq: 13, item: '閫€璐с€佹崲璐ф潯浠?, info: '鍚堝悓5骞存潵锛屼粠鏈彂鐢熻繃涓€娆￠噸澶ц川閲忛棶棰樻崯锛屾崲璐?璧斿伩', source: '涓庡叧浜?鍏ュ鏉℃琛屼俊鎭竴鑷? },
  { seq: 14, item: '鏄惁娑夊強濮旀墭鍔犲伐', info: '鍚?, source: '' },
  { seq: 15, item: '鏄惁瀛樺湪鏉ユ枡鍔犲伐', info: '鍚?, source: '' },
  { seq: 16, item: '璧勯噾浜ゆ槗鎯呭喌', info: '鏃?, source: '' },
  { seq: 17, item: '绗笁鏂规敹娆?浠樻', info: '鏃?, source: '' },
  { seq: 18, item: '浠ｆ敹娆俱€佷唬浠樻', info: '鏃?, source: '' },
  { seq: 19, item: '鍏朵粬璧勯噾寰€鏉?, info: '鏃?, source: '' },
  { seq: 20, item: '鏄惁娑夌煡', info: '鍚?, source: '' },
]
</script>

<template>
<div class="d4-interview-detail">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-button size="small" type="warning" plain @click="showExample = true">馃摉 鏌ョ湅璁胯皥妗堜緥</el-button>
      <el-dropdown trigger="click" size="small"><el-button size="small">瀵煎叆瀵煎嚭 鈻?/el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-31')">瀵煎嚭妯℃澘</el-dropdown-item><el-dropdown-item @click="exportData('D4-31')">瀵煎嚭鏁版嵁</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>瀵煎叆鏁版嵁</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown>
      <D4IpoFindingWriteback wp-code="D4-31" :all-responses="allResponses" :is-readonly="isReadonly" :findings="riskFindings" />
      <GtIndexChip value="wp:D4-30" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-31-detail')">馃挰 澶嶆牳</el-button>
    </div>
  </div>

  <template v-if="editorMode === '闂嵎瑙嗗浘'">
    <!-- 宸︿晶瀵艰埅 + 鍙充晶鍐呭 -->
    <div class="questionnaire-layout">
      <nav class="section-nav">
        <div :class="['nav-item', { active: activeSection === 'meta' }]" @click="activeSection='meta'">鍏冧俊鎭?/div>
        <div :class="['nav-item', { active: activeSection === 'ch1' }]" @click="activeSection='ch1'">涓€銆佸彈璁夸汉浠嬬粛</div>
        <div :class="['nav-item', { active: activeSection === 'ch2' }]" @click="activeSection='ch2'">浜屻€佸鎴峰熀鏈儏鍐?/div>
        <div :class="['nav-item', { active: activeSection === 'ch3' }]" @click="activeSection='ch3'">涓夈€佷笟鍔℃儏鍐?/div>
        <div :class="['nav-item', { active: activeSection === 'ch4' }]" @click="activeSection='ch4'">鍥涖€佸叧鑱斿叧绯?/div>
        <div :class="['nav-item', { active: activeSection === 'sign' }]" @click="activeSection='sign'">绛惧瓧涓庢壙璇?/div>
      </nav>

      <div class="section-content">
        <!-- 鍏冧俊鎭?-->
        <div v-show="activeSection==='meta'" class="form-section">
          <h4>璁胯皥鍩烘湰淇℃伅</h4>
          <div class="form-grid">
            <div class="form-item"><label>璁胯皥瀵硅薄</label><el-input :model-value="formData.target" :disabled="isReadonly" @input="(v:string)=>update('target',v)" /></div>
            <div class="form-item"><label>璁胯皥鏃堕棿鍙婂湴鐐?/label><el-input :model-value="formData.timePlace" :disabled="isReadonly" @input="(v:string)=>update('timePlace',v)" /></div>
            <div class="form-item"><label>鎺ュ彈璁胯皥浜哄憳鍙婅亴鍔?/label><el-input :model-value="formData.interviewee" :disabled="isReadonly" @input="(v:string)=>update('interviewee',v)" /></div>
            <div class="form-item"><label>璁胯皥浜?/label><el-input :model-value="formData.interviewer" :disabled="isReadonly" @input="(v:string)=>update('interviewer',v)" /></div>
          </div>
          <div class="form-hint">馃挕 璁胯皥鍐呭搴旀牴鎹瀹¤鍗曚綅瀹為檯鎯呭喌銆佸叧娉ㄧ殑瀹㈡埛涓昏椋庨櫓鎯呭喌淇敼銆?/div>
        </div>

        <!-- 涓€銆佸彈璁夸汉浠嬬粛 -->
        <div v-show="activeSection==='ch1'" class="form-section">
          <div class="section-title-row"><h4>涓€銆佹帴鍙楄璋堜汉浠嬬粛</h4><el-button v-if="aiAvailable" size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="aiGenerateIntro">馃 AI鐢熸垚妯℃澘</el-button></div>
          <p class="field-hint">鍖呮嫭濮撳悕銆佷换鑱岀殑鍏徃銆佽亴鍔°€佸叿浣撹礋璐ｇ殑宸ヤ綔绛?/p>
          <el-input type="textarea" :autosize="{minRows:3,maxRows:10}" :model-value="formData.introduction" :disabled="isReadonly" placeholder="璇疯褰曞彈璁夸汉鍩烘湰浠嬬粛淇℃伅" @input="(v:string)=>update('introduction',v)" />
        </div>

        <!-- 浜屻€佸鎴峰熀鏈儏鍐?-->
        <div v-show="activeSection==='ch2'" class="form-section">
          <h4>浜屻€佸鎴风殑鍩烘湰鎯呭喌</h4>
          <p class="field-hint">闄勬湁鍏抽儴闂ㄧ洊绔犵‘璁ょ殑宸ュ晢鐧昏璇佹槑鏂囦欢銆佷富浣撶撼绋庤瘉鏄庣瓑</p>
          <div class="form-grid">
            <div class="form-item"><label>鍏徃鍚嶇О</label><el-input :model-value="formData.companyName" :disabled="isReadonly" @input="(v:string)=>update('companyName',v)" /></div>
            <div class="form-item"><label>娉ㄥ唽璧勬湰</label><el-input :model-value="formData.regCapital" :disabled="isReadonly" @input="(v:string)=>update('regCapital',v)" /></div>
            <div class="form-item"><label>鎴愮珛鏃ユ湡</label><el-input :model-value="formData.establishDate" :disabled="isReadonly" @input="(v:string)=>update('establishDate',v)" /></div>
            <div class="form-item"><label>缁忔祹鎬ц川</label><el-input :model-value="formData.bizNature" :disabled="isReadonly" @input="(v:string)=>update('bizNature',v)" /></div>
            <div class="form-item"><label>娉曞畾浠ｈ〃浜?/label><el-input :model-value="formData.legalRep" :disabled="isReadonly" @input="(v:string)=>update('legalRep',v)" /></div>
            <div class="form-item"><label>鑲℃潈缁撴瀯</label><el-input :model-value="formData.equityStructure" :disabled="isReadonly" @input="(v:string)=>update('equityStructure',v)" /></div>
          </div>
        </div>

        <!-- 涓夈€佷笟鍔℃儏鍐?-->
        <div v-show="activeSection==='ch3'" class="form-section">
          <h4>涓夈€佷笌瀹㈡埛涓氬姟鎯呭喌</h4>
          <!-- Q1 涓氬姟鍏崇郴 -->
          <div class="question-card">
            <div class="q-label">1. 瀹㈡埛涓庡彂琛屼汉鐨勪笟鍔″叧绯讳负</div>
            <el-checkbox-group :model-value="formData.q1_relation" :disabled="isReadonly" @change="(v:string[])=>update('q1_relation',v)">
              <el-checkbox v-for="opt in RELATION_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-checkbox>
            </el-checkbox-group>
          </div>
          <!-- Q2 缁撶畻鏂瑰紡 -->
          <div class="question-card">
            <div class="q-label">2. 瀹㈡埛涓庡彂琛屼汉鐨勭粨绠楁柟寮?/div>
            <div class="sub-question"><span class="sub-label">(1) 瀹㈡埛鍚戝彂琛屼汉鐨勯噰璐?/span>
              <el-radio-group :model-value="formData.q2a_payment" :disabled="isReadonly" @change="(v:string)=>update('q2a_payment',v)"><el-radio v-for="opt in PAYMENT_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group>
            </div>
            <div class="sub-question"><span class="sub-label">(2) 瀹㈡埛鍚戝彂琛屼汉鐨勯攢鍞?/span>
              <el-radio-group :model-value="formData.q2b_collection" :disabled="isReadonly" @change="(v:string)=>update('q2b_collection',v)"><el-radio v-for="opt in COLLECTION_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group>
            </div>
          </div>
          <!-- Q3 浜ゆ槗鎯呭喌 -->
          <div class="question-card">
            <div class="q-label">3. 20XX骞村害鑷充粖瀹㈡埛涓庡彂琛屼汉浜ゆ槗鎯呭喌</div>
            <div class="sub-question"><span class="sub-label">(1) 鎵€鏈変氦鏄撹涓烘槸鍚︾璁㈠悎鍚?/span><el-radio-group :model-value="formData.q3a_hasContract" :disabled="isReadonly" @change="(v:string)=>update('q3a_hasContract',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(2) 浜у搧璐ㄩ噺鎯呭喌锛堥€傜敤瀹㈡埛锛?/span><el-radio-group :model-value="formData.q3b_quality" :disabled="isReadonly" @change="(v:string)=>update('q3b_quality',v)"><el-radio v-for="opt in QUALITY_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(3) 鏄惁绾﹀畾閫€鎹㈣揣鏉℃</span><el-radio-group :model-value="formData.q3c_returnClause" :disabled="isReadonly" @change="(v:string)=>update('q3c_returnClause',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio></el-radio-group></div>
            <div v-if="formData.q3c_returnClause==='鏄?" class="sub-question condition-expand"><span class="sub-label">(4) 閫€鎹㈣揣閲戦</span><el-radio-group :model-value="formData.q3d_returnAmount" :disabled="isReadonly" @change="(v:string)=>update('q3d_returnAmount',v)"><el-radio v-for="opt in RETURN_AMOUNT_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(5) 浜у搧楠屾敹鍏ュ簱鎯呭喌</span><el-radio-group :model-value="formData.q3e_acceptance" :disabled="isReadonly" @change="(v:string)=>update('q3e_acceptance',v)"><el-radio v-for="opt in ACCEPTANCE_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            <div class="sub-question"><span class="sub-label">(6) 鏄惁瀛樺湪杩斿埄绾﹀畾</span><el-radio-group :model-value="formData.q3f_hasRebate" :disabled="isReadonly" @change="(v:string)=>update('q3f_hasRebate',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio></el-radio-group></div>
            <template v-if="formData.q3f_hasRebate==='鏄?">
              <div class="sub-question condition-expand"><span class="sub-label">A. 杩斿埄鏀粯鏂瑰紡</span><el-radio-group :model-value="formData.q3f_rebateMethod" :disabled="isReadonly" @change="(v:string)=>update('q3f_rebateMethod',v)"><el-radio v-for="opt in REBATE_METHOD_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
              <div class="sub-question condition-expand"><span class="sub-label">B. 杩斿埄閲戦</span><el-radio-group :model-value="formData.q3f_rebateAmount" :disabled="isReadonly" @change="(v:string)=>update('q3f_rebateAmount',v)"><el-radio v-for="opt in REBATE_AMOUNT_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio></el-radio-group></div>
            </template>
            <div class="sub-question"><span class="sub-label">(7) 缁忛攢鍟嗚喘涔扮殑璐х墿鏄惁宸叉渶缁堥攢鍞?/span><el-radio-group :model-value="formData.q3g_finalSold" :disabled="isReadonly" @change="(v:string)=>update('q3g_finalSold',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio><el-radio value="涓嶉€傜敤">涓嶉€傜敤</el-radio></el-radio-group></div>
          </div>
          <!-- Q4 鍏朵粬璧勯噾 -->
          <div class="question-card">
            <div class="q-label">4. 闄ら噰璐鏄惁杩樺瓨鍦ㄥ叾浠栬祫閲戝線鏉ワ紵</div>
            <el-radio-group :model-value="formData.q4_otherFunds" :disabled="isReadonly" @change="(v:string)=>update('q4_otherFunds',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio></el-radio-group>
          </div>
          <!-- Q5 鍏朵粬 -->
          <div class="question-card">
            <div class="q-label">5. 鍏朵粬閲嶈浜嬮」</div>
            <el-input type="textarea" :autosize="{minRows:2,maxRows:6}" :model-value="formData.q5_otherMatters" :disabled="isReadonly" placeholder="璁板綍鍏朵粬闇€鍏虫敞鐨勯噸瑕佷簨椤? @input="(v:string)=>update('q5_otherMatters',v)" />
          </div>
        </div>

        <!-- 鍥涖€佸叧鑱斿叧绯?-->
        <div v-show="activeSection==='ch4'" class="form-section">
          <h4>鍥涖€佸叧鑱斿叧绯绘儏鍐?/h4>
          <p class="field-hint">鍙戣浜虹殑瀹為檯鎺у埗浜恒€佽嚜鐒朵汉鑲′笢銆佽懀浜嬨€佺洃浜嬫垨楂樼浜哄憳鍙婁富瑕佸叧鑱旀柟鏄惁鍦ㄥ鎴锋寔鏈夎偂浠?/p>
          <div class="question-card"><div class="q-label">鏄惁鎸佹湁鑲′唤</div><el-radio-group :model-value="formData.q6_hasShares" :disabled="isReadonly" @change="(v:string)=>update('q6_hasShares',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio></el-radio-group></div>
          <div class="question-card"><div class="q-label">鏄惁鎷呬换鑱屽姟</div><el-radio-group :model-value="formData.q6_hasPosition" :disabled="isReadonly" @change="(v:string)=>update('q6_hasPosition',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio></el-radio-group></div>
          <div class="question-card"><div class="q-label">鏄惁鍜屽鎴锋湁浜ゆ槗</div><el-radio-group :model-value="formData.q6_hasTransaction" :disabled="isReadonly" @change="(v:string)=>update('q6_hasTransaction',v)"><el-radio value="鏄?>鏄?/el-radio><el-radio value="鍚?>鍚?/el-radio></el-radio-group></div>
        </div>

        <!-- 绛惧瓧涓庢壙璇?-->
        <div v-show="activeSection==='sign'" class="form-section">
          <h4>闄勪欢娓呭崟</h4>
          <div class="attachment-list">
            <div class="attachment-item">
              <span class="att-label">1. 渚涘簲鍟嗙洊绔犵‘璁ょ殑宸ュ晢鐧昏璇佹槑鏂囦欢</span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">馃搸 涓婁紶 鈻?/el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('闄勪欢涓婁紶鍔熻兘寮€鍙戜腑')"><span>涓婁紶鏂囦欢</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('鏂囦欢澶逛笂浼犲姛鑳藉紑鍙戜腑')"><span>涓婁紶鏂囦欢澶?/span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
            <div class="attachment-item">
              <span class="att-label">2. 璺熷嚱鍥炲嚱</span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">馃搸 涓婁紶 鈻?/el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('闄勪欢涓婁紶鍔熻兘寮€鍙戜腑')"><span>涓婁紶鏂囦欢</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('鏂囦欢澶逛笂浼犲姛鑳藉紑鍙戜腑')"><span>涓婁紶鏂囦欢澶?/span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
            <div class="attachment-item">
              <span class="att-label">3. XX浜у搧閿€鍞槑缁嗚处銆乆X浜у搧搴撳瓨鍟嗗搧鏄庣粏璐?/span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">馃搸 涓婁紶 鈻?/el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('闄勪欢涓婁紶鍔熻兘寮€鍙戜腑')"><span>涓婁紶鏂囦欢</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('鏂囦欢澶逛笂浼犲姛鑳藉紑鍙戜腑')"><span>涓婁紶鏂囦欢澶?/span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
            <div class="attachment-item">
              <span class="att-label">4. XXX璐︽埛璧勯噾娴佹按</span>
              <el-dropdown trigger="click" size="small">
                <el-button size="small" :disabled="isReadonly">馃搸 涓婁紶 鈻?/el-button>
                <template #dropdown><el-dropdown-menu>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('闄勪欢涓婁紶鍔熻兘寮€鍙戜腑')"><span>涓婁紶鏂囦欢</span></el-upload></el-dropdown-item>
                  <el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="() => ElMessage.info('鏂囦欢澶逛笂浼犲姛鑳藉紑鍙戜腑')"><span>涓婁紶鏂囦欢澶?/span></el-upload></el-dropdown-item>
                </el-dropdown-menu></template>
              </el-dropdown>
            </div>
          </div>

          <h4 style="margin-top:20px;">鍙備笌璁胯皥鐨勫悇鏂逛汉鍛樼瀛?/h4>
          <div class="form-grid">
            <div class="form-item"><label>鎺ュ彈璁胯皥浜哄憳</label><el-input :model-value="formData.signInterviewee" :disabled="isReadonly" @input="(v:string)=>update('signInterviewee',v)" /></div>
            <div class="form-item"><label>瀹¤浜哄憳</label><el-input :model-value="formData.signAuditor" :disabled="isReadonly" @input="(v:string)=>update('signAuditor',v)" /></div>
            <div class="form-item"><label>鍏朵粬浜哄憳</label><el-input :model-value="formData.signOther" :disabled="isReadonly" @input="(v:string)=>update('signOther',v)" /></div>
            <div class="form-item"><label>鏃ユ湡</label><el-input :model-value="formData.signDate" :disabled="isReadonly" placeholder="YYYY-MM-DD" @input="(v:string)=>update('signDate',v)" /></div>
          </div>
          <!-- 鎵胯澹版槑 -->
          <div class="commitment-box">
            <p class="commitment-text">"鏈叕鍙稿悜XX浼氳甯堜簨鍔℃墍鎻愪緵鐨勪俊鎭拰璧勬枡鐪熷疄銆佸畬鏁达紝濡傚瓨鍦ㄨ櫄鍋囦俊鎭垨閲嶅ぇ閬楁紡锛屾湰鍏徃鎰挎剰鎵挎媴涓€鍒囨硶寰嬭矗浠?銆?/p>
            <p class="commitment-hint">濡傝瘑鍒嚭瀹㈡埛瀛樺湪绗笁鏂归厤鍚堝疄鏂借储鍔¤垶寮婄殑椋庨櫓锛屽簲瑕佹眰瀹㈡埛灏卞叾鎻愪緵鐨勮祫鏂欒繘琛屾壙璇哄苟鍔犵洊鍏珷銆?/p>
          </div>
          <!-- CAS18鎻愮ず -->
          <details class="tips-collapse"><summary class="tips-summary">鈿狅笍 CAS18鍙峰疄鍦拌蛋璁挎彁绀?/summary><ol class="tips-list">
            <li>閫夋嫨澶氬悕鎴栦笉鍚屽眰绾т汉鍛樿璋堢浉鍚岄棶棰橈紝杩涜鐩镐簰鍗拌瘉銆?/li>
            <li>鏍稿疄琚闂汉鍛樻槸鍚︿笌琚璁″崟浣嶅瓨鍦ㄧ壒娈婂叧绯汇€?/li>
            <li>瀵瑰鎴风殑浜у搧瀹炴柦瑙傚療銆佹鏌ョ瓑绋嬪簭锛屽叧娉ㄥ瓨璐х殑瀛樻斁鍜岄鐢ㄦ槸鍚︿负鐪熷疄闇€瑕併€?/li>
            <li>瀵圭粡閿€鍟嗗鎴峰叧娉ㄥ簱瀛橀噺鏄惁鏄庢樉涓嶅悎鐞嗭紝鑰冭檻妫€鏌ョ粡閿€鍟嗚繘閿€瀛樿褰曘€?/li>
            <li>閽堝璇嗗埆鍑虹殑椋庨櫓锛岃€冭檻閲囩敤璺熷嚱鏂瑰紡杩涜鍑借瘉锛岃瀵熷嚱璇佸鐞嗚繃绋嬨€?/li>
          </ol></details>
        </div>
      </div>
    </div>
  </template>

  <template v-if="editorMode === '鍦ㄧ嚎缂栬緫'">
    <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="瀹㈡埛璁胯皥璁板綍 D4-31" :readonly="isReadonly" /></div>
  </template>

  <!-- 璁胯皥妗堜緥寮圭獥 -->
  <el-dialog v-model="showExample" title="馃摉 璁胯皥璁板綍涓庢牳瀵圭ず渚? width="800px" destroy-on-close top="5vh">
    <div class="example-content">
      <div class="example-section">
        <h4 class="example-title">涓€銆佽蛋璁跨殑鍏徃鍩烘湰淇℃伅</h4>
        <p class="example-hint">銆愬缓璁噰鍐欍€?/p>
        <div class="example-text">
          <p>銆怷YZ鍏徃鐨勫熀鏈儏鍐碉紝鍖呮嫭锛歑YZ鍏徃娉曞畾浠ｈ〃浜恒€佹敞鍐屽湴銆佹敞鍐岃祫鏈€佽绔嬪強鍙樻洿鍘嗗彶銆佺粡钀ヨ寖鍥淬€佸疄缂磋祫鏈儏鍐靛強鍦ㄥ唽鑲′笢鍑鸿祫姣斾緥绛夈€傚叕鍙歌惀涓氭墽鐓с€佷紒涓氫俊鐢ㄤ俊鎭叕绀烘姤鍛婄瓑銆?/p>
          <p>宸ュ晢淇℃伅鏌ヨ缁撴灉銆佸ぉ鐪兼煡绛夋煡璇㈢粨鏋溿€?/p>
          <p>鐧惧害鍦板浘绛夋煡璇㈣蛋璁垮湴鍧€鐨勭粨鏋溿€?/p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">浜屻€佷氦鏄撳熀鏈俊鎭?/h4>
        <p class="example-hint">銆愬缓璁噰鍐欍€?/p>
        <div class="example-text">
          <p>銆愯闂強XYZ鍏徃涓庡彂琛屼汉鐨勫悎浣滄儏鍐碉紙浜ゆ槗妯″紡銆佷氦鏄撻噾棰濄€佷氦鏄撴柟寮忋€佷粯娆炬柟寮忋€侀€€鎹㈡潯娆俱€佺粨绠楁潯浠剁瓑锛夛紝骞跺叧娉ㄥ疄鐗╂祦涓庡悎鍚屾潯娆惧強璐﹂潰璁板綍鐨勪竴鑷存€э紱闇€鏍稿鐨勯棶棰樺涓嬶紝灏嗘牳瀵规儏鍐佃褰曞湪涓嬭〃锛氥€?/p>
        </div>
        <el-table :data="exampleTradeItems" border size="small" class="example-table">
          <el-table-column prop="seq" label="Q#" width="40" align="center" />
          <el-table-column prop="item" label="椤圭洰" width="100" />
          <el-table-column prop="info" label="璇㈤棶鎵€鑾蜂俊鎭? min-width="200" />
          <el-table-column prop="source" label="鏉ヨ嚜鍙戣浜哄悎鍚屾潯娆? min-width="150" />
        </el-table>
      </div>

      <div class="example-section">
        <h4 class="example-title">涓夈€佷笌鍙戣浜虹殑浜ゆ槗涓庡悎鍚屾潯娆炬牳瀵?/h4>
        <p class="example-hint">銆愬缓璁噰鍐欍€?/p>
        <div class="example-text">
          <p>銆愯闂強鍙栧緱鏈夊叧璇佹槑鏂囦欢鏍稿XYZ鍏徃涓庡彂琛屼汉鍚堜綔鍗忚鐨勬儏鍐点€傚寘鎷悎鍚屾潯娆剧害瀹氥€侀攢鍞噾棰濇瘮瀵广€佺涓夋柟鏀舵/浠樻鎯呭喌銆佽祫閲戜氦鏄撴儏鍐电瓑銆傘€?/p>
          <p>涓庡彂琛屼汉鍚堜綔濮嬩簬2008骞寸璁㈠悎浣滃崗璁€愪笌鍙戣浜篨XX浜у搧閿€鍞瓵AAHH鏉愭枡銆戯紝鎶ュ憡涓夊勾鍚堝悓閲戦鍒嗗埆涓篨XX銆?/p>
          <p>鏈熼棿浜ゆ槗閲戦銆佷笌鍓嶈堪鍙戠エ鍙婂彴璐︽牳瀵逛竴鑷达紝鏃犲紓璁€備氦鏄撻噾棰濇瘮瀵规甯搞€?/p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">鍥涖€佽蛋璁跨粡钀ユ儏鍐?/h4>
        <p class="example-hint">銆愬缓璁噰鍐欍€?/p>
        <div class="example-text">
          <p>銆愯蛋璁縓YZ鐨勭敓浜х粡钀ユ儏鍐碉紙鑻ラ€傜敤锛夛紝鍏虫敞鍏剁敓浜х粡钀ョ幇鐘朵笌璁胯皥鍐呭鍜屽嚟璇佹壂鎻忋€?/p>
          <p>XYZ鍏徃浣嶄簬XXX宸ヤ笟鍥尯锛屽洯鍖洪潰绉?300浜╋紝涓昏鐢熶骇XXXXX锛屼富瑕佸師鏉愭枡AAA锛屽勾浜ц兘XXXX鍚ㄣ€?/p>
          <p>XYZ鍏徃鐩墠鎷ユ湁3涓敓浜ц溅闂达紝鏁翠綋鎴愬搧瀛?鐢熶骇璁稿彲璇?锛屽紑宸ョ巼绾︿负90%銆?/p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">浜斻€佸嚟璇佹牳瀵?/h4>
        <p class="example-hint">銆愬缓璁噰鍐欍€?/p>
        <div class="example-text">
          <p>銆愬XYZ鍏徃杩涜鐜板満鍑借瘉锛堟閮ㄥ垎鍐呭鍖呮嫭浣嗕笉闄愪簬锛氭埅鑷崇洰鐨勬棩鐨勮揣鏉?鏈嶅姟鍚堝悓銆佹垨鏄叏鏈熺殑鍏ㄩ儴浜ゆ槗鍙婂線鏉ヤ綑棰濓級锛涙棤鑱旀柟鍏崇郴纭鍑姐€傘€?/p>
          <p>鐜板満鏀跺彇鐨刋YZ鍏徃瀵瑰嚱璇佷俊鎭繘琛屼竴娆★紙宸紓涓篨XXX鍏冿紝250涓囷級锛孹YZ鍏徃纭鏃犱换浣曠2鏈堝墠瀹為檯鐨勮川妫€鐨勫師鏉愭枡鎸夌収搴旀敹璐︽浣欓锛屽苟鎸夎姹傚鍏惰繘琛岀洊绔犵瀛椼€?/p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">鍏€佸叧鑱旀柟鍏崇郴</h4>
        <p class="example-hint">銆愬缓璁噰鍐欍€?/p>
        <div class="example-text">
          <p>璧拌鍏徃鐨勮偂鏉冪粨鏋勩€佸疄闄呮帶鍒朵汉銆?/p>
          <p>璧拌鍏徃鐨勮懀鐩戦珮銆佸叧閿粡鍔炰汉鍛橈紙濡傛鍚嶃€侀攢鍞憳/闂ㄥ簵搴椾汉銆佸嚭绾崇瓑锛夈€?/p>
        </div>
      </div>

      <div class="example-section">
        <h4 class="example-title">涓冦€佸叾浠?/h4>
        <p class="example-hint">銆愬缓璁噰鍐欍€?/p>
      </div>

      <div class="example-section">
        <h4 class="example-title">璧拌缁撹</h4>
        <div class="example-text">
          <p>锛堢敱瀹¤浜哄憳鏍规嵁璧拌鎯呭喌鎬荤粨寰楀嚭缁撹锛?/p>
        </div>
      </div>
    </div>
  </el-dialog>
</div>
</template>

<style scoped>
.d4-interview-detail { padding: 16px 20px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }

.questionnaire-layout { display: flex; gap: 20px; min-height: 500px; }
.section-nav { width: 140px; flex-shrink: 0; position: sticky; top: 80px; align-self: flex-start; }
.nav-item { padding: 8px 12px; margin-bottom: 4px; border-radius: 6px; font-size: 12px; color: #606266; cursor: pointer; transition: all 0.2s; }
.nav-item:hover { background: #f0f5ff; color: #409eff; }
.nav-item.active { background: #ecf5ff; color: #409eff; font-weight: 600; border-left: 3px solid #409eff; }

.section-content { flex: 1; min-width: 0; }
.form-section { padding: 16px; border: 1px solid #ebeef5; border-radius: 8px; background: #fafbfc; }
.form-section h4 { margin: 0 0 12px; font-size: 14px; color: #303133; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title-row h4 { margin: 0; }

.form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 20px; }
.form-item { display: flex; flex-direction: column; gap: 4px; }
.form-item label { font-size: 12px; color: #909399; }
.form-hint { margin-top: 12px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; font-size: 12px; color: #67c23a; }
.field-hint { font-size: 12px; color: #909399; margin-bottom: 10px; }

.question-card { margin-bottom: 14px; padding: 12px 16px; border: 1px solid #ebeef5; border-radius: 6px; background: #fff; }
.q-label { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #303133; margin-bottom: 8px; }
.sub-question { margin: 8px 0 8px 16px; }
.sub-label { display: block; font-size: 12px; color: #606266; margin-bottom: 4px; }
.condition-expand { margin-left: 32px; padding: 8px 12px; background: #fdf6ec; border-radius: 4px; border-left: 2px solid #e6a23c; }

.commitment-box { margin-top: 16px; padding: 14px 16px; border: 1px solid #e1f3d8; border-radius: 6px; background: #f0f9eb; }
.commitment-text { font-size: var(--wp-font-size, 13px); color: #303133; font-style: italic; margin-bottom: 8px; }
.commitment-hint { font-size: 12px; color: #e6a23c; }

.attachment-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.attachment-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; border: 1px solid #ebeef5; border-radius: 6px; background: #fff; }
.att-label { font-size: 12px; color: #606266; }

.tips-collapse { margin-top: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; background: #fef0f0; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #f56c6c; }
.tips-list { margin: 8px 14px 12px; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }

.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }

/* 妗堜緥寮圭獥 */
.example-content { max-height: 70vh; overflow-y: auto; padding: 0 8px; }
.example-section { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #f0f0f0; }
.example-section:last-child { border-bottom: none; }
.example-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 4px; }
.example-hint { font-size: 12px; color: #e6a23c; margin-bottom: 8px; font-style: italic; }
.example-text { font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.8; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; border-left: 3px solid #409eff; }
.example-text p { margin: 4px 0; }
.example-table { margin-top: 8px; font-size: var(--wp-font-size, 13px); }
.example-table :deep(.el-table__cell) { padding: 6px 8px; font-size: var(--wp-font-size, 13px); }
</style>
