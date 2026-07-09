<template>
  <div class="h3-tab-disclosure-soe">
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
.h3-tab-disclosure-soe { padding: 16px; font-size: 13px; }
.method-context { margin-bottom: 16px; }
.context-bar { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 8px 12px; border-radius: 4px; font-size: 12px; }
.note-section { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.note-table { font-size: 13px; margin-bottom: 12px; }
.note-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
