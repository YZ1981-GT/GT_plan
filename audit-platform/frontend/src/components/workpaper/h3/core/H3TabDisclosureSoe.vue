<template>
  <div class="h3-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产附注披露（国企口径）的完整与准确，含用途分类、产权完整性、抵押担保及计量政策披露，确保与审定表、报表一致；成本模式与公允价值模式披露口径不同。"
    />

    <!-- 计量模式说明 -->
    <div class="method-context">
      <div class="context-bar">
        计量模式：{{ measurementModel === 'cost' ? '成本模式（国企格式：原值+折旧+净值+用途）' : '公允价值模式（国企格式：公允+变动+评估依据）' }}
      </div>
    </div>

    <!-- 子节卡片 -->
    <el-card v-for="section in sections" :key="section.key" shadow="never" class="note-section">
      <template #header>
        <div class="section-title">
          <span>{{ section.title }}</span>
          <el-button size="small" @click="generateAI(section.key)">AI</el-button>
        </div>
      </template>

      <!-- 动态行表格 -->
      <el-table v-if="section.hasTable" :data="getSectionRows(section.key)" border size="small" class="note-table" show-summary :summary-method="getNoteSummary">
        <el-table-column prop="category" label="项目" min-width="140" />
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginBalance" size="small" :disabled="isReadonly" @change="onRowChange(section.key, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.increase" size="small" :disabled="isReadonly" @change="onRowChange(section.key, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" @change="onRowChange(section.key, row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.beginBalance + row.increase - row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usage" label="用途" min-width="100">
          <template #default="{ row }">
            <el-input v-model="row.usage" size="small" :disabled="isReadonly" @change="onRowChange(section.key, row)" />
          </template>
        </el-table-column>
      </el-table>

      <!-- 文本区 -->
      <el-input
        v-model="sectionTexts[section.key]"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :placeholder="section.placeholder"
        :disabled="isReadonly"
        @change="onTextChange(section.key)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注格式需额外披露用途分类（出租/增值持有）</li>
        <li>关注产权完整性说明、抵押担保情况</li>
        <li>成本模式需详细列示折旧政策及各类变动明细</li>
        <li>公允价值模式需披露评估机构、评估方法、关键假设</li>
      </ul>
    </details>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：各披露子项的取数来源、用途/产权/抵押披露核对、与审定表及报表的勾稽情况。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、披露完整准确，与审定表/报表一致。B、除下列事项外未见异常。C、披露存在重大遗漏或错误，需更正。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDisclosureSoe.vue — 附注披露（国企版）
 * 多子节卡片+计量模式说明+动态行+合计+用途列
 * EventBus: subscribe 'substantive:adjudicated' 刷新 / publish 'disclosure:note-text-updated'
 */
import { ref, computed, inject, toRef, onMounted, onUnmounted } from 'vue'
import { useH3Disclosure } from '../../composables/useH3Disclosure'
import { useH3FormData } from '../../composables/useH3FormData'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel: 'cost' | 'fair_value'
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: toRef(props, 'measurementModel') as any,
})

const {
  sectionRows, sectionTexts, updateRow, updateText, getSectionRows,
} = useH3Disclosure({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
  measurementModel: toRef(props, 'measurementModel') as any,
  variant: ref('soe') as any,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-disc-soe-audit-note'
const CONCLUSION_KEY = 'H3-disc-soe-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

// ─── EventBus: subscribe 'substantive:adjudicated' → 刷新附注数据 ──────────
let eventSource: EventSource | null = null

function setupEventBusSubscription() {
  try {
    eventSource = new EventSource(`/api/projects/${props.projectId}/events/stream`)
    eventSource.addEventListener('substantive:adjudicated', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data)
        if (data.wp_code?.startsWith('H3')) {
          // 审定完成 → 刷新附注（响应式链自动处理）
        }
      } catch { /* ignore parse errors */ }
    })
  } catch { /* SSE not available, silent */ }
}

onMounted(() => { setupEventBusSubscription() })
onUnmounted(() => { eventSource?.close(); eventSource = null })

// ─── EventBus: publish 'disclosure:note-text-updated' ────────────────────────
function publishNoteTextUpdated(sectionKey: string, text: string) {
  http.post(`/api/projects/${props.projectId}/events/publish`, {
    event_type: 'disclosure:note-text-updated',
    payload: { wp_id: props.wpId, section: sectionKey, text, variant: 'soe' },
  }).catch(() => { /* best effort */ })
}

interface NoteSection {
  key: string
  title: string
  hasTable: boolean
  placeholder: string
}

const sections: NoteSection[] = [
  { key: 'soe-original', title: '一、投资性房地产账面原值', hasTable: true, placeholder: '按用途分类列示原值变动...' },
  { key: 'soe-dep', title: '二、累计折旧/摊销', hasTable: true, placeholder: '列示折旧/摊销变动...' },
  { key: 'soe-net', title: '三、投资性房地产净值', hasTable: true, placeholder: '列示净值明细...' },
  { key: 'soe-fair', title: '四、公允价值变动（如适用）', hasTable: true, placeholder: '列示公允价值变动...' },
  { key: 'soe-policy', title: '五、计量政策及折旧方法', hasTable: false, placeholder: '描述计量模式选择依据、折旧方法、使用年限...' },
  { key: 'soe-restriction', title: '六、产权及限制情况', hasTable: false, placeholder: '说明产权归属、抵押担保、使用限制...' },
  { key: 'soe-rental', title: '七、租赁情况', hasTable: false, placeholder: '说明出租对象、租期、租金收入...' },
]

function onRowChange(sectionKey: string, row: any) {
  updateRow(sectionKey, row)
}
function onTextChange(sectionKey: string) {
  updateText(sectionKey, sectionTexts[sectionKey])
  publishNoteTextUpdated(sectionKey, sectionTexts[sectionKey])
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function getNoteSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => idx === 0 ? '合计' : '')
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section: `H3-disc-S-${section}`, wpId: props.wpId } }))
}
</script>

<style scoped>
.h3-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.method-context { margin-bottom: 16px; }
.context-bar { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 8px 12px; border-radius: 4px; font-size: 12px; }
.note-section { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.note-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.note-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
