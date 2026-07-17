<template>
  <div class="h3-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产附注披露（上市公司口径，CAS33）的完整与准确，确保原值/累计折旧/减值/公允价值变动等披露与审定表、报表一致；成本模式与公允价值模式披露口径不同。"
    />

    <!-- 计量模式说明 -->
    <div class="method-context">
      <div class="context-bar">
        计量模式：{{ measurementModel === 'cost' ? '成本模式（报告原值+累计折旧+净值）' : '公允价值模式（报告公允价值+变动损益）' }}
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

      <!-- 动态行表格（如适用） -->
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
        <li>上市公司附注按CAS33格式披露投资性房地产变动</li>
        <li>成本模式需披露原值、累计折旧、减值准备、净值变动</li>
        <li>公允价值模式需披露公允价值变动金额及确定依据</li>
        <li>表格数据优先从H3-1审定表自动取数</li>
      </ul>
    </details>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：各披露子项的取数来源、与审定表/报表的勾稽、计量模式披露口径的核对情况。" :disabled="isReadonly" @change="saveAuditNote" />
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
 * H3TabDisclosureListed.vue — 附注披露（上市公司版）
 * 多子节卡片+计量模式说明+动态行+合计
 * EventBus: subscribe 'substantive:adjudicated' 刷新 / publish 'disclosure:note-text-updated'
 */
import { ref, reactive, computed, inject, toRef, onMounted } from 'vue'
import { useH3Disclosure } from '../../composables/useH3Disclosure'
import { useH3FormData } from '../../composables/useH3FormData'
import { eventBus } from '@/utils/eventBus'

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
  variant: ref('listed') as any,
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-disc-listed-audit-note'
const CONCLUSION_KEY = 'H3-disc-listed-audit-conclusion'
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

// ─── 附注取数刷新 ────────────────────────────────────────────────────────────
// 跨 sheet 数据刷新由主入口 GtH3InvestmentProperty 订阅 substantive:adjudicated 统一处理
// （刷新 allResponses → 本 tab computed 自动重算）。此处不再自建失效的 SSE 订阅
// （原 EventSource 订阅客户端事件 + refreshDisclosureData 空操作 = 双重空转）。

// ─── EventBus: publish 'disclosure:note-text-updated'（走客户端总线，经桥同步到 window）──
function publishNoteTextUpdated(sectionKey: string, _text: string) {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'H3',
    section: sectionKey,
    timestamp: Date.now(),
  })
}

interface NoteSection {
  key: string
  title: string
  hasTable: boolean
  placeholder: string
}

const sections: NoteSection[] = [
  { key: 'cost-original', title: '一、投资性房地产—原值变动', hasTable: true, placeholder: '披露原值期初/增减/期末...' },
  { key: 'cost-dep', title: '二、累计折旧变动', hasTable: true, placeholder: '披露累计折旧期初/计提/期末...' },
  { key: 'cost-impair', title: '三、减值准备', hasTable: true, placeholder: '披露减值准备变动...' },
  { key: 'fair-change', title: '四、公允价值变动', hasTable: true, placeholder: '披露公允价值变动金额...' },
  { key: 'measurement-basis', title: '五、计量模式及公允价值确定依据', hasTable: false, placeholder: '描述企业采用的计量模式、公允价值确定方法...' },
  { key: 'restriction', title: '六、限制及担保', hasTable: false, placeholder: '描述抵押/担保/使用限制情况...' },
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
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section: `H3-disc-L-${section}`, wpId: props.wpId } }))
}
</script>

<style scoped>
.h3-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
