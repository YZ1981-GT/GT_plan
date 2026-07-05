<template>
  <div class="gt-c23-journal-control">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 顶部操作引导区 -->
      <div class="guidance-area">
        <div class="guidance-header">
          <el-icon><InfoFilled /></el-icon>
          <span>操作流程引导</span>
        </div>
        <div class="guidance-steps">
          <div class="step-item">
            <span class="step-num">①</span>
            <span class="step-text">维护授权清单</span>
          </div>
          <div class="step-item">
            <span class="step-num">②</span>
            <span class="step-text">抽样核对</span>
          </div>
          <div class="step-item">
            <span class="step-num">③</span>
            <span class="step-text">判断偏差</span>
          </div>
          <div class="step-item">
            <span class="step-num">④</span>
            <span class="step-text">得出结论</span>
          </div>
        </div>
      </div>

      <!-- C23A 程序表 -->
      <div v-if="currentSheet === 'C23A'" class="c23-program-console">
        <GtAProgramConsole
          :wp-id="props.wpId"
          sheet-name="C23A"
          :schema="{ columns: [], rows: [] }"
          :html-data="{ programs: [], schema: { columns: [], rows: [] } }"
          :readonly="isReadonly"
        />
      </div>

      <!-- C23-1 会计人员清单完整性测试表 -->
      <div v-else-if="currentSheet === 'C23-1'" class="c23-personnel-list">
        <C23PersonnelSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :persons="persons"
          :source-desc="sourceDesc"
          :conclusion1="conclusion1"
          :is-readonly="isReadonly"
          @update:source-desc="onSourceDescChange"
          @update:conclusion1="onConclusion1Change"
          @add-person="onAddPerson"
          @remove-person="onRemovePerson"
          @update-person="onUpdatePerson"
          @ai-suggest="onAiSuggest('C23-1-conclusion')"
        />
      </div>

      <!-- C23-2 会计分录控制测试样本表 -->
      <div v-else-if="currentSheet === 'C23-2'" class="c23-control-test">
        <C23SampleSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :samples="samples"
          :persons="persons"
          :deviation-count="deviationCount"
          :deviation-total="deviationTotal"
          :conclusion2="conclusion2"
          :is-readonly="isReadonly"
          @update-sample="onUpdateSample"
          @update:conclusion2="onConclusion2Change"
          @ai-suggest="onAiSuggest('C23-2-conclusion')"
        />
      </div>

      <!-- 示例 sheets (只读) -->
      <div v-else class="c23-example">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>{{ currentSheet === '示例1' ? '示例 — 会计人员清单测试' : '示例 — 会计分录控制测试' }}</template>
          <p style="margin-top: 8px; color: #606266;">此为只读参考示例，请在 C23-1 / C23-2 中进行实际操作。</p>
        </el-alert>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC23JournalControl — C23 会计分录控制测试专属组件
 *
 * componentType: c23-journal-entry-control
 * 对齐 D4 标准：sheetName v-if 分发，无内部 el-tabs
 *
 * Sheets: C23A / C23-1 人员清单 / C23-2 控制测试 / 示例1 / 示例2
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 4.1
 * Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5
 */
import { ref, computed, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { ElMessage, ElMessageBox } from 'element-plus'
import { checkPersonnel, type AuthorizedPerson, type JeControlSample } from '@/composables/useC23ControlData'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'

defineOptions({ name: 'GtC23JournalControl' })

// ─── Lazy child components ───
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const C23PersonnelSheet = defineAsyncComponent(() => import('./c23/C23PersonnelSheet.vue'))
const C23SampleSheet = defineAsyncComponent(() => import('./c23/C23SampleSheet.vue'))

// ─── Props / Emits ───
const props = defineProps<{
  wpId: string
  projectId?: string
  wpCode?: string
  year?: string
  sheetName?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───
const isLoading = ref(true)
const isReadonly = computed(() => !!props.readonly)

const currentSheet = computed(() => {
  const name = props.sheetName || 'C23A'
  if (name.includes('C23A') || name.includes('程序表')) return 'C23A'
  if (name.includes('C23-1') || name.includes('人员清单')) return 'C23-1'
  if (name.includes('C23-2') || name.includes('控制测试')) return 'C23-2'
  if (name.includes('示例1') || name.includes('人员清单测试')) return '示例1'
  if (name.includes('示例2') || name.includes('分录控制测试')) return '示例2'
  return name
})

// ─── C23-1 数据来源 + 授权人员清单 ───
const sourceDesc = ref('')
const conclusion1 = ref('')
const persons = ref<Array<{ seq: number; name: string; role: string; note: string }>>([])

// ─── C23-2 样本数据 ───
const SAMPLE_COUNT = 25
interface SampleRow {
  seq: number
  date: string
  voucherNo: string
  preparer: string
  poster: string
  reviewer: string
  supportDoc: string
  approval: string
  deviation: string   // '是' | '否' | ''
  deviationNote: string
  indexRef: string
}
const samples = ref<SampleRow[]>([])
const conclusion2 = ref('')

// ─── 偏差统计 (formula) ───
const deviationCount = computed(() => samples.value.filter(s => s.deviation.startsWith('是')).length)
const deviationTotal = computed(() => samples.value.filter(s => s.date || s.voucherNo || s.preparer).length || SAMPLE_COUNT)

// ─── AI ───
const ai = useWpAiSuggest({ wpId: props.wpId, sheetName: 'C23' })

// ─── Debounce save ───
let saveTimer: ReturnType<typeof setTimeout> | null = null

function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { persistAll() }, 2000)
}

function flushPendingSaves() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistAll()
  }
}

// ─── Persist functions ───
async function persistAll() {
  if (!props.wpId || isReadonly.value) return
  const items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }> = []

  // C23-1 source & conclusion
  items.push({ item_id: 'C23-1-source', conclusion: null, remark: sourceDesc.value || null })
  items.push({ item_id: 'C23-1-conclusion', conclusion: conclusion1.value || null, remark: null })

  // C23-1 persons
  persons.value.forEach((p, i) => {
    const n = i + 1
    items.push({ item_id: `C23-person-${n}-name`, conclusion: null, remark: p.name || null })
    items.push({ item_id: `C23-person-${n}-role`, conclusion: p.role || null, remark: null })
    items.push({ item_id: `C23-person-${n}-note`, conclusion: null, remark: p.note || null })
  })

  // C23-2 samples
  samples.value.forEach((s) => {
    const prefix = `C23-sample-${s.seq}`
    items.push({ item_id: `${prefix}-date`, conclusion: null, remark: s.date || null })
    items.push({ item_id: `${prefix}-voucherNo`, conclusion: null, remark: s.voucherNo || null })
    items.push({ item_id: `${prefix}-preparer`, conclusion: null, remark: s.preparer || null })
    items.push({ item_id: `${prefix}-poster`, conclusion: null, remark: s.poster || null })
    items.push({ item_id: `${prefix}-reviewer`, conclusion: null, remark: s.reviewer || null })
    items.push({ item_id: `${prefix}-supportDoc`, conclusion: null, remark: s.supportDoc || null })
    items.push({ item_id: `${prefix}-approval`, conclusion: null, remark: s.approval || null })
    items.push({ item_id: `${prefix}-deviation`, conclusion: s.deviation || null, remark: null })
    items.push({ item_id: `${prefix}-deviationNote`, conclusion: null, remark: s.deviationNote || null })
    items.push({ item_id: `${prefix}-indexRef`, conclusion: null, remark: s.indexRef || null })
  })

  // C23-2 conclusion & deviation count
  items.push({ item_id: 'C23-2-conclusion', conclusion: conclusion2.value || null, remark: null })
  items.push({ item_id: 'C23-2-deviationCount', conclusion: null, remark: `${deviationCount.value}/${deviationTotal.value}` })

  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items,
    })
    emit('save')
  } catch (err: any) {
    ElMessage.error('保存失败，数据已保留在本地')
    console.warn('[C23] persist failed:', err)
  }
}

/** 即时保存结论字段 */
async function saveConclusion(itemId: string, value: string) {
  if (!props.wpId || isReadonly.value) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: itemId, conclusion: value || null, remark: null }],
    })
  } catch { /* silent */ }
}

// ─── Event handlers ───

function onSourceDescChange(val: string) {
  sourceDesc.value = val
  debounceSave()
}

function onConclusion1Change(val: string) {
  conclusion1.value = val
  saveConclusion('C23-1-conclusion', val)
}

function onConclusion2Change(val: string) {
  conclusion2.value = val
  saveConclusion('C23-2-conclusion', val)
}

async function onAddPerson() {
  if (isReadonly.value) return
  try {
    const { value: name } = await ElMessageBox.prompt('请输入人员姓名', '新增授权人员', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '请输入姓名',
      inputValidator: (v) => (v?.trim() ? true : '姓名不能为空'),
    })
    if (!name?.trim()) return
    const seq = persons.value.length + 1
    persons.value.push({ seq, name: name.trim(), role: '', note: '' })
    debounceSave()
    runPersonnelCheck()
  } catch { /* cancelled */ }
}

function onRemovePerson(index: number) {
  if (isReadonly.value) return
  persons.value.splice(index, 1)
  // Re-sequence
  persons.value.forEach((p, i) => { p.seq = i + 1 })
  debounceSave()
  runPersonnelCheck()
}

function onUpdatePerson(index: number, field: 'name' | 'role' | 'note', value: string) {
  if (isReadonly.value) return
  persons.value[index][field] = value
  debounceSave()
  if (field === 'name') runPersonnelCheck()
}

function onUpdateSample(index: number, field: keyof SampleRow, value: string) {
  if (isReadonly.value) return
  ;(samples.value[index] as any)[field] = value
  debounceSave()
  // Auto check personnel after preparer/poster/reviewer change
  if (['preparer', 'poster', 'reviewer'].includes(field)) {
    runPersonnelCheck()
  }
}

/** 人员核对：调用 checkPersonnel 自动标记偏差 */
function runPersonnelCheck() {
  const authorized: AuthorizedPerson[] = persons.value
    .filter(p => p.name.trim())
    .map(p => ({ name: p.name, role: p.role }))

  const sampleData: JeControlSample[] = samples.value
    .filter(s => s.preparer || s.poster || s.reviewer)
    .map(s => ({
      seq: s.seq,
      voucherDate: s.date,
      voucherNo: s.voucherNo,
      preparer: s.preparer,
      poster: s.poster,
      reviewer: s.reviewer,
      supportDoc: s.supportDoc,
      approval: s.approval,
    }))

  if (!authorized.length || !sampleData.length) return

  const results = checkPersonnel(sampleData, authorized)
  results.forEach(r => {
    const row = samples.value.find(s => s.seq === r.sample.seq)
    if (row) {
      // 自动标记：偏差为 "是-需跟进"，无偏差为 "否"
      if (r.deviation && !row.deviation) {
        row.deviation = '是-需跟进'
      } else if (!r.deviation && !row.deviation) {
        row.deviation = '否'
      }
      if (r.deviation && r.deviationDetails) {
        row.deviationNote = r.deviationDetails
      }
    }
  })
}

async function onAiSuggest(fieldId: string) {
  if (isReadonly.value || !ai.aiEnabled.value) return
  const fieldName = fieldId === 'C23-1-conclusion' ? '人员清单完整性测试结论' : '控制测试结论'
  const currentVal = fieldId === 'C23-1-conclusion' ? conclusion1.value : conclusion2.value
  await ai.requestSuggestion(fieldName, currentVal)
  const text = ai.adoptSuggestion()
  if (text) {
    if (fieldId === 'C23-1-conclusion') {
      conclusion1.value = text
      saveConclusion('C23-1-conclusion', text)
    } else {
      conclusion2.value = text
      saveConclusion('C23-2-conclusion', text)
    }
  }
}

// ─── selfLoad ───
async function selfLoad() {
  try {
    const res = await api.get<any[]>(`/api/workpapers/${props.wpId}/checklist-responses`, { _silent: true } as any)
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> = Array.isArray(res) ? res : (res as any)?.data || []

    // Build lookup map
    const map = new Map<string, { conclusion?: string; remark?: string }>()
    for (const item of items) {
      if (item.item_id?.startsWith('C23-')) {
        map.set(item.item_id, { conclusion: item.conclusion, remark: item.remark })
      }
    }

    // C23-1 source & conclusion
    sourceDesc.value = map.get('C23-1-source')?.remark || ''
    conclusion1.value = map.get('C23-1-conclusion')?.conclusion || ''

    // C23-1 persons (find max n)
    const personKeys = [...map.keys()].filter(k => k.startsWith('C23-person-'))
    const maxPersonN = personKeys.reduce((max, k) => {
      const m = k.match(/^C23-person-(\d+)-/)
      return m ? Math.max(max, parseInt(m[1])) : max
    }, 0)
    const loadedPersons: Array<{ seq: number; name: string; role: string; note: string }> = []
    for (let n = 1; n <= maxPersonN; n++) {
      const name = map.get(`C23-person-${n}-name`)?.remark || ''
      const role = map.get(`C23-person-${n}-role`)?.conclusion || ''
      const note = map.get(`C23-person-${n}-note`)?.remark || ''
      if (name || role || note) {
        loadedPersons.push({ seq: n, name, role, note })
      }
    }
    persons.value = loadedPersons

    // C23-2 samples
    const loadedSamples: SampleRow[] = []
    for (let s = 1; s <= SAMPLE_COUNT; s++) {
      const prefix = `C23-sample-${s}`
      loadedSamples.push({
        seq: s,
        date: map.get(`${prefix}-date`)?.remark || '',
        voucherNo: map.get(`${prefix}-voucherNo`)?.remark || '',
        preparer: map.get(`${prefix}-preparer`)?.remark || '',
        poster: map.get(`${prefix}-poster`)?.remark || '',
        reviewer: map.get(`${prefix}-reviewer`)?.remark || '',
        supportDoc: map.get(`${prefix}-supportDoc`)?.remark || '',
        approval: map.get(`${prefix}-approval`)?.remark || '',
        deviation: map.get(`${prefix}-deviation`)?.conclusion || '',
        deviationNote: map.get(`${prefix}-deviationNote`)?.remark || '',
        indexRef: map.get(`${prefix}-indexRef`)?.remark || '',
      })
    }
    samples.value = loadedSamples

    // C23-2 conclusion
    conclusion2.value = map.get('C23-2-conclusion')?.conclusion || ''
  } catch (err) {
    console.warn('[GtC23JournalControl] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── Lifecycle ───
onMounted(() => { selfLoad() })
onBeforeUnmount(() => { flushPendingSaves() })
defineExpose({ reload: selfLoad })
</script>

<style scoped>
.gt-c23-journal-control {
  padding: 12px;
  font-size: 13px;
}
.loading-container {
  padding: 24px;
}
.guidance-area {
  background: linear-gradient(135deg, #ecf5ff 0%, #d9ecff 100%);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.guidance-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
  margin-bottom: 12px;
}
.guidance-header .el-icon {
  color: #409eff;
  font-size: 16px;
}
.guidance-steps {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 6px;
}
.step-num {
  font-weight: 700;
  color: #409eff;
  font-size: 14px;
}
.step-text {
  font-size: 13px;
  color: #303133;
}
</style>
