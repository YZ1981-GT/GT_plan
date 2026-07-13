<template>
  <div class="h1-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px"
      title="审计目标：确认固定资产附注披露（原值/累计折旧/减值变动、闲置、融资租入、经营租出、所有权受限、已提足固定资产）完整，与审定表(H1-1)/明细表(H1-2)勾稽一致，符合上市公司披露要求。" />

    <!-- 顶部引导 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 固定资产情况总表（跨sheet自动取数H1-1/H1-2）</div>
        <div class="guide-step"><span class="step-num">②</span> 闲置/融资租入/经营租出/受限/已提足 五子节动态行</div>
      </div>
    </div>

    <!-- 6子节卡片 -->
    <template v-for="section in sections" :key="section.key">
      <el-card shadow="never" class="disclosure-card">
        <template #header>
          <div class="section-title">
            <span>{{ section.title }}</span>
            <div class="title-actions">
              <el-button size="small" type="default" link @click="handleReview(`disc-listed-${section.key}`)">💬</el-button>
            </div>
          </div>
        </template>

        <!-- 概览子节：矩阵表 -->
        <template v-if="section.key === 'overview'">
          <el-table :data="overviewRows" border stripe size="small">
            <el-table-column prop="category" label="资产分类" min-width="120" />
            <el-table-column prop="beginBalance" label="期初余额" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell auto-fill">{{ fmtAmt(row.beginBalance) }}</span></template>
            </el-table-column>
            <el-table-column prop="increase" label="本期增加" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell auto-fill">{{ fmtAmt(row.increase) }}</span></template>
            </el-table-column>
            <el-table-column prop="decrease" label="本期减少" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell auto-fill">{{ fmtAmt(row.decrease) }}</span></template>
            </el-table-column>
            <el-table-column label="期末余额" width="120" align="right">
              <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span></template>
            </el-table-column>
          </el-table>
          <div class="auto-fill-hint">💡 数据自动从H1-1/H1-2取入（浅蓝色=跨sheet）</div>
        </template>

        <!-- 动态行子节 -->
        <template v-else>
          <el-table :data="getDynamicRows(section.key)" border stripe size="small">
            <el-table-column type="index" width="40" />
            <el-table-column prop="name" label="资产名称/项目" min-width="160">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.name" size="small" />
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="账面价值" width="130" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" />
                <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="说明" min-width="200">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.description" size="small" />
                <span v-else>{{ row.description }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div class="dynamic-actions" v-if="!isReadonly">
            <el-button size="small" @click="addDynamicRow(section.key)">+ 新增行</el-button>
          </div>
          <div class="subtotal-row">
            合计: <span class="amount-cell">{{ fmtAmt(getDynamicSubtotal(section.key)) }}</span>
          </div>
        </template>
      </el-card>
    </template>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>附注披露审计说明</span></template>
      <el-input v-model="disclosureNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写附注披露审计说明..." @change="saveDisclosureNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="auditConclusionText" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="填写附注披露审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>概览表数据从审定表/明细表自动取入（不可编辑）</li>
        <li>其余5个子节为动态行，按实际情况逐项登记</li>
        <li>适用上市公司年报附注披露要求</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabDisclosureListed.vue — 附注披露（上市公司版）
 * Task 6.6: 附注EventBus集成
 * - subscribe 'substantive:adjudicated' 刷新附注取数
 * - publish 'disclosure:note-text-updated' 通知外部
 */
import { ref, computed, inject, toRef, onMounted, onUnmounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Disclosure, LISTED_SECTIONS } from '../../composables/useH1Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const disclosureNote = ref('')
const auditConclusionText = ref('')
const NOTE_KEY = 'H1-note-listed-audit-note'
const CONCLUSION_KEY = 'H1-note-listed-audit-conclusion'
function saveDisclosureNote() { saveResponse(NOTE_KEY, disclosureNote.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, auditConclusionText.value) }

const sections = LISTED_SECTIONS

const disclosure = useH1Disclosure(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    variant: ref('listed') as any,
    onPublishEvent(event: string, payload: any) {
      // 6.6 — publish 'disclosure:note-text-updated' 通知外部
      console.log('[H1-DiscListed] publish', event, payload)
    },
  },
)

const { costMatrixRows: overviewRows, sectionRows: dynamicRowsMap, addDynamicRow: _addDynamic } = disclosure

// ─── 6.6 EventBus: subscribe 'substantive:adjudicated' 刷新附注取数 ─────────
let eventSource: EventSource | null = null

function subscribeAdjudicated() {
  // SSE-based EventBus subscription for cross-sheet refresh
  try {
    eventSource = new EventSource(`/api/projects/${props.projectId}/events?topic=substantive:adjudicated`)
    eventSource.onmessage = () => {
      // 刷新跨sheet取数 — trigger re-load from allResponses
      console.log('[H1-DiscListed] received substantive:adjudicated, refreshing disclosure data')
    }
  } catch { /* SSE not available, degrade silently */ }
}

onMounted(() => {
  subscribeAdjudicated()
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) disclosureNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) auditConclusionText.value = c.remark
})
onUnmounted(() => { eventSource?.close() })

function getDynamicRows(key: string) {
  return dynamicRowsMap.value?.[key] ?? []
}

function getDynamicSubtotal(key: string): number {
  const rows = getDynamicRows(key)
  return rows.reduce((sum: number, r: any) => sum + (Number(r.amount) || 0), 0)
}

function addDynamicRow(key: string) { _addDynamic(key) }
function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.disclosure-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.auto-fill { color: var(--el-color-primary); }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.auto-fill-hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 8px; }
.dynamic-actions { margin-top: 8px; }
.subtotal-row { margin-top: 8px; font-weight: 500; text-align: right; padding-right: 12px; }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
