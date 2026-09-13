<script setup lang="ts">
/**
 * D4TabCustomerDetail 鈥?D4-29 瀹㈡埛淇℃伅妫€鏌ヨ〃
 *
 * 涓夋ā寮忥細鍗＄墖瑙嗗浘(閫愬鎴峰～鍐? / 鐭╅樀瑙嗗浘(琛?瀛楁,鍒?瀹㈡埛鍙瀵规瘮) / 鍦ㄧ嚎缂栬緫
 * 31涓鏌ュ瓧娈?脳 N涓鎴凤紝搴曢儴CAS18鍙疯垶寮婇闄╂彁绀烘姌鍙?
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4CustomerDetail, CUSTOMER_FIELDS, FIELD_GROUPS } from '../../composables/useD4CustomerDetail'
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

const {
  customers, auditNote, auditConclusion,
  customerCount, relatedCount, completionRate,
  addCustomer, removeCustomer, updateField, updateCustomerName,
  updateAuditNote, updateAuditConclusion,
} = useD4CustomerDetail({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  isReadonly: computed(() => props.isReadonly),
})

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

// 鈹€鈹€鈹€ Mode 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const editorMode = ref<string>('鍗＄墖瑙嗗浘')
const modeOptions = ['鍗＄墖瑙嗗浘', '鐭╅樀瑙嗗浘', '鍦ㄧ嚎缂栬緫']
const activeCustomerIdx = ref(0)

// 鈹€鈹€鈹€ AI 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 杈呭姪鐢熸垚' : 'AI 鏈嶅姟鏆備笉鍙敤')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)

async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '鍩轰簬瀹㈡埛淇℃伅妫€鏌?D4-29)缁撴灉鐢熸垚瀹¤璇存槑', customerCount: customerCount.value, relatedCount: relatedCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 鏈敓鎴愬唴瀹?); return }; await ElMessageBox.confirm(t, 'AI 鐢熸垚 路 瀹¤璇存槑', { confirmButtonText: '濉叆', cancelButtonText: '鍙栨秷', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 鐢熸垚澶辫触') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '鍩轰簬瀹㈡埛淇℃伅妫€鏌ョ粨鏋滅敓鎴愬璁＄粨璁?, noteText: auditNote.value, customerCount: customerCount.value, relatedCount: relatedCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 鏈敓鎴愬唴瀹?); return }; await ElMessageBox.confirm(t, 'AI 鐢熸垚 路 瀹¤缁撹', { confirmButtonText: '濉叆', cancelButtonText: '鍙栨秷', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 鐢熸垚澶辫触') } finally { aiConclusionLoading.value = false } }

async function handleAddCustomer() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('璇疯緭鍏ュ鎴峰悕绉?, '娣诲姞瀹㈡埛', { confirmButtonText: '纭', cancelButtonText: '鍙栨秷', inputPattern: /\S+/, inputErrorMessage: '涓嶈兘涓虹┖' }); if (value?.trim()) { addCustomer(value.trim()); activeCustomerIdx.value = customers.value.length - 1 } } catch {} }

function handleExportTemplate() { exportTemplate('D4-29') }
function handleExportData() { exportData('D4-29') }
async function handleImportFile(f: any) { const r = await importData('D4-29', f.raw || f); if (r) await reloadWorkpaperData?.() }

// 褰撳墠鍗＄墖瀹㈡埛
const activeCustomer = computed(() => customers.value[activeCustomerIdx.value] || null)

// 鈹€鈹€鈹€ 椋庨櫓鍙戠幇锛堜粎鐢辨樉寮忛闄╂寚鏍?鏄?鏍囪锛屼笉鐢?鍚?/绌?reason 鍗曠嫭鍒ゅ畾锛夆攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
const riskFindings = computed<D4IpoFinding[]>(() => {
  const out: D4IpoFinding[] = []
  for (const c of customers.value) {
    const f = c.fields || {}
    const flags: string[] = []
    if (f.isRelated === '鏄?) flags.push('鍏宠仈鏂?)
    if (f.isBlacklisted === '鏄?) flags.push('鍒楀叆澶变俊浜?)
    if (f.hasOverdue === '鏄?) flags.push('闀挎湡鎷栨瑺娆鹃」')
    if (flags.length) {
      out.push({ key: `d4-29-${c.id}`, label: `${c.name || '瀹㈡埛'}锛?{flags.join('銆?)}`, indexRef: 'D4-29' })
    }
  }
  return out
})

// 瀛楁鎸夌粍鍒嗙粍
const fieldsByGroup = computed(() => FIELD_GROUPS.map(g => ({ ...g, fields: CUSTOMER_FIELDS.filter(f => f.group === g.key) })))
</script>

<template>
<div class="d4-customer-detail">
  <!-- 宸ュ叿鏉?-->
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">瀵煎叆瀵煎嚭 鈻?/el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">瀵煎嚭妯℃澘</el-dropdown-item><el-dropdown-item @click="handleExportData">瀵煎嚭鏁版嵁</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>瀵煎叆鏁版嵁</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><D4IpoFindingWriteback wp-code="D4-29" :all-responses="allResponses" :is-readonly="isReadonly" :findings="riskFindings" /><GtIndexChip value="wp:D4-28" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-29-detail')">馃挰 澶嶆牳</el-button></div></div>

  <!-- 浠〃鏉?-->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ customerCount }}<span class="stat-unit">瀹?/span></div><div class="stat-label">妫€鏌ュ鎴?/div></div>
    <div class="stat-card" :class="relatedCount > 0 ? 'stat-warn' : 'stat-ok'"><div class="stat-value">{{ relatedCount }}<span class="stat-unit">瀹?/span></div><div class="stat-label">鍏宠仈鏂?/div></div>
    <div class="stat-card stat-progress"><div class="stat-value">{{ completionRate }}%</div><div class="stat-label">瀛楁瀹屾垚搴?/div></div>
  </div>

  <!-- 鈺愨晲鈺?鍗＄墖瑙嗗浘 鈺愨晲鈺?-->
  <template v-if="editorMode === '鍗＄墖瑙嗗浘'">
    <!-- 浣跨敤璇存槑 -->
    <div class="usage-guide">
      <span class="usage-icon">馃挕</span>
      <span class="usage-text">鐐瑰嚮涓嬫柟"娣诲姞瀹㈡埛"鎸夐挳鍒涘缓瀹㈡埛鍗＄墖锛岄€愰」濉啓宸ュ晢淇℃伅銆佽偂涓溿€佺鐞嗗眰鍙婇闄╁垽鏂€傚垏鎹?鐭╅樀瑙嗗浘"鍙í鍚戝姣斿涓鎴蜂俊鎭€?/span>
    </div>
    <!-- 瀹㈡埛鏍囩椤?-->
    <div class="customer-tabs">
      <el-tabs v-model="activeCustomerIdx" type="card" @tab-remove="(name: any) => removeCustomer(customers[Number(name)]?.id)">
        <el-tab-pane v-for="(cust, idx) in customers" :key="cust.id" :label="cust.name || `瀹㈡埛${idx+1}`" :name="idx" :closable="!isReadonly" />
      </el-tabs>
    </div>

    <!-- 鍗＄墖鍐呭 -->
    <div v-if="activeCustomer" class="card-content">
      <div class="card-header">
        <el-input v-model="activeCustomer.name" size="default" :disabled="isReadonly" class="customer-name-input" @change="updateCustomerName(activeCustomer.id, activeCustomer.name)" />
      </div>
      <div v-for="group in fieldsByGroup" :key="group.key" class="field-group" :style="{ borderLeftColor: group.color }">
        <div class="group-title">{{ group.label }}</div>
        <div class="fields-grid">
          <div v-for="field in group.fields" :key="field.key" class="field-item">
            <label>{{ field.label }}</label>
            <el-select v-if="field.type === 'select'" :model-value="activeCustomer.fields[field.key] || ''" size="small" :disabled="isReadonly" placeholder="璇烽€夋嫨" @change="(v: string) => updateField(activeCustomer.id, field.key, v)">
              <el-option v-for="opt in field.options" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-input v-else-if="field.type === 'textarea'" :model-value="activeCustomer.fields[field.key] || ''" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" size="small" :disabled="isReadonly" @input="(v: string) => updateField(activeCustomer.id, field.key, v)" />
            <el-input v-else :model-value="activeCustomer.fields[field.key] || ''" size="small" :disabled="isReadonly" @input="(v: string) => updateField(activeCustomer.id, field.key, v)" />
          </div>
        </div>
      </div>
    </div>
    <el-empty v-else description="璇锋坊鍔犲鎴峰紑濮嬫鏌? :image-size="80">
      <el-button type="primary" :disabled="isReadonly" @click="handleAddCustomer"><el-icon :size="14"><Plus /></el-icon> 娣诲姞瀹㈡埛</el-button>
    </el-empty>
  </template>

  <!-- 鈺愨晲鈺?鐭╅樀瑙嗗浘 鈺愨晲鈺?-->
  <template v-else-if="editorMode === '鐭╅樀瑙嗗浘'">
    <el-table :data="CUSTOMER_FIELDS" border class="matrix-table" max-height="600">
      <el-table-column label="妫€鏌ラ」鐩? min-width="150" fixed>
        <template #default="{ row }">{{ row.label }}</template>
      </el-table-column>
      <el-table-column v-for="cust in customers" :key="cust.id" :label="cust.name" min-width="130" align="center">
        <template #default="{ row }">
          <span :class="{ 'risk-yes': row.key === 'isRelated' && cust.fields[row.key] === '鏄? }">{{ cust.fields[row.key] || '鈥? }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!customers.length" class="empty-matrix"><el-empty description="鏆傛棤瀹㈡埛鏁版嵁" /></div>
  </template>

  <!-- 鈺愨晲鈺?鍦ㄧ嚎缂栬緫 鈺愨晲鈺?-->
  <template v-else-if="editorMode === '鍦ㄧ嚎缂栬緫'">
    <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="瀹㈡埛淇℃伅妫€鏌ヨ〃D4-29" :readonly="isReadonly" /></div>
  </template>

  <!-- 闈濷O妯″紡鍏变韩鍖哄煙 -->
  <template v-if="editorMode !== '鍦ㄧ嚎缂栬緫'">
    <!-- 瀹¤鎰忚鍖?-->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">瀹¤鎰忚鍖?/span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">馃 AI杈呭姪璇存槑</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">馃 AI杈呭姪缁撹</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>涓夈€佸璁¤鏄?/label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="璁板綍瀹㈡埛淇℃伅鏍告煡鍙戠幇鐨勫紓甯告儏鍐? @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>鍥涖€佸璁＄粨璁?/label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="缁煎悎鍒ゆ柇瀹㈡埛淇℃伅鏄惁鐪熷疄銆佹槸鍚﹀瓨鍦ㄧ涓夋柟閰嶅悎鑸炲紛杩硅薄" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>

    <!-- CAS18鍙疯垶寮婇闄╂彁绀猴紙绾㈠瓧鎶樺彔锛?-->
    <details class="fraud-tips-collapse">
      <summary class="fraud-tips-summary">鈿狅笍 CAS18鍙封€斺€旂涓夋柟閰嶅悎鑸炲紛鐗瑰緛鎻愮ず锛堢偣鍑诲睍寮€锛?/summary>
      <div class="fraud-tips-body">
        <p class="fraud-tips-intro">鏍规嵁銆婁腑鍥芥敞鍐屼細璁″笀瀹¤鍑嗗垯闂瑙ｇ瓟绗?8鍙封€斺€旇瘑鍒拰搴斿绗笁鏂归厤鍚堝疄鏂借储鍔¤垶寮娿€嬶紝閰嶅悎瀹炴柦璐㈠姟鑸炲紛鐨勭涓夋柟鍙兘鍏锋湁浠ヤ笅鐗瑰緛锛?/p>
        <ol class="fraud-tips-list">
          <li>缁忚惀鏃堕棿杈冪煭銆?/li>
          <li>缂寸撼绀句繚浜烘暟杈冨皯銆?/li>
          <li>涓轰釜浜烘垨涓綋宸ュ晢鎴枫€?/li>
          <li>娉ㄥ唽璧勬湰涓庝氦鏄撹妯′笉鍖归厤銆?/li>
          <li>浜ゆ槗瑙勬ā涓庣涓夋柟鎵€澶勮涓氱姸鍐典笉鍖归厤銆?/li>
          <li>缁忚惀鑼冨洿涓庝氦鏄撴€ц川涓嶅尮閰嶃€?/li>
          <li>娉ㄥ唽鍦板潃涓庤瀹¤鍗曚綅鍦板潃杈冧负鎺ヨ繎銆?/li>
          <li>涓嶅悓绗笁鏂圭殑宸ュ晢鐧昏淇℃伅鐩稿悓鎴栫浉杩戯紙鑲′笢銆佽懀鐩戦珮銆佹敞鍐屽湴鍧€銆佽仈绯绘柟寮忕瓑锛夈€?/li>
          <li>鏃㈡槸瀹㈡埛鍙堟槸渚涘簲鍟嗭紝鎴栧彈鍚屼竴瀹為檯鎺у埗浜烘帶鍒躲€?/li>
          <li>瀵硅瀹¤鍗曚綅瀛樺湪閲嶅ぇ渚濊禆锛堝琚璁″崟浣嶆槸鍏朵富瑕佸鎴凤級銆?/li>
          <li>琚璁″崟浣嶅悜鍏堕攢鍞殑瑙勬ā涓庡叾闇€姹備笉鍖归厤銆?/li>
          <li>杩炵画瀹¤鏈熼棿瀵瑰璁＄▼搴忛厤鍚堝害鎸佺画杈冮珮锛屽潎鑳芥彁渚涙闈㈠璁¤瘉鎹€?/li>
          <li>鏇剧粡閰嶅悎鍏朵粬鏂瑰疄鏂借储鍔¤垶寮娿€?/li>
          <li>娉曞緥鎰忚瘑娣¤杽锛屽悎瑙勬€ц緝宸紙杩戜笁骞村彈杩囪鏀垮缃氾級銆?/li>
          <li>鑲′笢鎴栧叧閿鐞嗕汉鍛樹笌琚璁″崟浣嶆垨鍏剁浉鍏充汉鍛樺瓨鍦ㄧ壒娈婂叧绯汇€?/li>
          <li>瀛樺湪瀹炵幇鐗瑰畾鐩殑鐨勯渶姹傦紙濡傝€冩牳銆佽涓氭帓鍚嶇瓑鍋氬ぇ鏀跺叆鐨勯渶姹傦級銆?/li>
        </ol>
      </div>
    </details>
  </template>
</div>
</template>

<style scoped>
.d4-customer-detail { padding: 16px 20px; font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 100px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-warn { border-left: 3px solid #f56c6c; }
.stat-card.stat-ok { border-left: 3px solid #67c23a; }
.stat-card.stat-progress { border-left: 3px solid #e6a23c; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }

/* 鍗＄墖瑙嗗浘 */
.usage-guide { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 14px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.usage-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.usage-text { font-size: 12px; color: #529b2e; line-height: 1.6; }
.customer-tabs { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.customer-tabs :deep(.el-tabs) { flex: 1; }
.customer-tabs :deep(.el-tabs__header) { margin-bottom: 0; }
.add-btn { flex-shrink: 0; }
.card-content { border: 1px solid #ebeef5; border-radius: 8px; padding: 16px; background: #fafbfc; }
.card-header { margin-bottom: 16px; }
.customer-name-input { max-width: 300px; }
.customer-name-input :deep(.el-input__inner) { font-size: 15px; font-weight: 600; }
.field-group { border-left: 3px solid #e4e7ed; padding: 12px 16px; margin-bottom: 12px; border-radius: 0 6px 6px 0; background: #fff; }
.group-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; margin-bottom: 10px; }
.fields-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 20px; }
.field-item { display: flex; flex-direction: column; gap: 3px; }
.field-item label { font-size: 12px; color: #909399; }
:deep(.el-empty) { padding: 32px 0; }
:deep(.el-empty__description) { margin-top: 8px; }

/* 鐭╅樀瑙嗗浘 */
.matrix-table { font-size: var(--wp-font-size, 13px); margin-bottom: 24px; }
.matrix-table :deep(.el-table__cell) { padding: 4px 6px; font-size: var(--wp-font-size, 13px); }
.risk-yes { color: #f56c6c; font-weight: 600; }
.empty-matrix { padding: 40px 0; }

/* 瀹¤鎰忚鍖?*/
.audit-opinion-card { margin-top: 24px; margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { margin-left: auto; display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500; }

/* CAS18鑸炲紛鎻愮ず鎶樺彔 */
.fraud-tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; background: #fef0f0; }
.fraud-tips-summary { cursor: pointer; padding: 10px 14px; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #f56c6c; }
.fraud-tips-body { padding: 8px 14px 14px; font-size: 12px; color: #606266; line-height: 1.9; }
.fraud-tips-intro { margin-bottom: 8px; font-weight: 500; }
.fraud-tips-list { margin: 0; padding-left: 18px; }
.fraud-tips-list li { margin-bottom: 2px; }

.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
</style>
