<script setup lang="ts">
/**
 * GtB23ProcessControl — B23 业务流程与控制了解表
 * Spec: .kiro/specs/b23-process-control/ | Tasks: 3.1~3.15, 4.1
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, watch, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import { useB23FormData } from './composables/useB23FormData'
import {
  useB23ProcessControl, STANDARD_PROCESSES, PROCESS_CONCLUSION_COLOR_MAP, CONCLUSION_TO_B50_IMPACT,
  type ProcessConclusion, type WalkthroughConclusion, type UnderstandingMethod,
  type ControlFrequency, type ControlPoint, type ControlConclusionPayload,
} from './composables/useB23ProcessControl'
import { useB23Review } from './composables/useB23Review'
import { eventBus } from '@/utils/eventBus'

interface Props { wpId: string; projectId: string; wpCode: string; year: number; readonly?: boolean }
const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void }>()
const wpIdRef = toRef(props, 'wpId')
const externalReadonly = toRef(props, 'readonly')
const { allResponses, loading, saving, loadAll, saveImmediate, saveDebouncedText, flushPendingSave } = useB23FormData(wpIdRef)
const { processes, expandedProcesses, toggleProcess, expandAll, collapseAll, setApplicability, getControlPoints, addControlPoint, removeControlPoint, setControlPointField, getWalkthroughRecords, addWalkthroughSample, setWalkthroughField, isWalkthroughComplete, walkthroughSummary, suggestConclusion, getConclusion, setConclusion, isConclusionOverridden, getOverrideReason, dashboardStats, entityLevelContext, onControlConclusionChanged, linkageInfo, publishWalkthroughCompleted } = useB23ProcessControl(allResponses, saveImmediate)
const { isReviewed, isReadonly, canReview, pendingItems, reviewInfo, doReview, startAmendment } = useB23Review(wpIdRef, allResponses, processes, externalReadonly, saveImmediate)
const overrideDialogVisible = ref(false)
const overrideProcessNum = ref<number>(0)
const overrideConclusion = ref<ProcessConclusion | null>(null)
const overrideReason = ref('')
const amendmentDialogVisible = ref(false)
const amendmentReason = ref('')
const deleteConfirmVisible = ref(false)
const deleteTarget = ref<{ num: number; index: number } | null>(null)
const importConflictVisible = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)
const flowDiagramCollapsed = ref(false)
const entityContextCollapsed = ref(false)
const walkthroughExpanded = ref<Set<number>>(new Set())
const CONCLUSION_OPTIONS: ProcessConclusion[] = ['设计有效且已实施', '设计有效但未有效实施', '设计无效', '不适用']
const WT_CONCLUSION_OPTIONS: WalkthroughConclusion[] = ['控制有效运行', '控制未有效运行', '未执行穿行', '不适用']
const FREQUENCY_OPTIONS: ControlFrequency[] = ['每笔', '每日', '每周', '每月', '每季', '每年', '不定期']
const METHOD_OPTIONS: UnderstandingMethod[] = ['询问', '观察', '检查文件', '穿行测试', '重新执行']
const CYCLE_MAP: Record<number, { code: string; name: string }> = { 1: { code: 'DA', name: '采购与付款循环程序表' }, 2: { code: 'EA', name: '销售与收款循环程序表' }, 3: { code: 'FA', name: '资金管理循环程序表' }, 4: { code: 'GA', name: '生产与存货循环程序表' }, 5: { code: 'HA', name: '薪酬与人力循环程序表' }, 6: { code: 'IA', name: '固定资产循环程序表' }, 7: { code: 'JA', name: '投资循环程序表' }, 8: { code: 'KA', name: '其他流程循环程序表' } }
const ADVICE_MAP: Record<string, string> = { '设计有效且已实施': '控制可依赖——可适当缩小实质性程序范围', '设计有效但未有效实施': '控制不可依赖——建议扩大实质性程序范围和样本量', '设计无效': '控制不可依赖——建议扩大实质性程序范围和样本量' }
const EXPORT_COLS = ['序号', '控制目标', '控制活动描述', '控制频率', '执行人/部门', '了解方法', '穿行测试结论', '备注/索引']
function getColor(c: ProcessConclusion | null): string { return c ? (PROCESS_CONCLUSION_COLOR_MAP[c]?.color || '#1890ff') : '#1890ff' }
function getBg(c: ProcessConclusion | null): string { return c ? (PROCESS_CONCLUSION_COLOR_MAP[c]?.bg || '#e6f7ff') : '#e6f7ff' }
function getLabel(c: ProcessConclusion | null): string { return c ? (PROCESS_CONCLUSION_COLOR_MAP[c]?.label || '待测试') : '待测试' }

// ─── 附件底稿 Tab 区域 ───────────────────────────────────────────────────────
const GtWpRendererLazy = defineAsyncComponent(() => import('./GtWpRenderer.vue'))

const attachmentWpIndex = ref<WpIndexItem[]>([])
const attachmentExpanded = ref(true)
const attachmentActive = ref('')

const B23_ATTACHMENT_CODES: { code: string; label: string }[] = [
  { code: 'B23-9', label: '穿行测试-采购付款' },
  { code: 'B23-10', label: '穿行测试-销售收款' },
  { code: 'B23-11', label: '穿行测试-资金管理' },
  { code: 'B23-12', label: '穿行测试-生产存货' },
  { code: 'B23-13', label: '穿行测试-薪酬人力' },
  { code: 'B23-14', label: '穿行测试-固定资产' },
  { code: 'B23-15', label: '穿行测试-投资' },
  { code: 'B23-XX-5', label: '穿行测试-其他' },
]

const attachmentWpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of attachmentWpIndex.value) {
    if (item.wp_code && /^B23-(9|1[0-5]|XX-5)$/.test(item.wp_code)) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

const attachmentTabs = computed(() =>
  B23_ATTACHMENT_CODES
    .filter(c => !!attachmentWpIdMap.value[c.code])
    .map(c => ({ id: c.code, label: c.label, wpId: attachmentWpIdMap.value[c.code] }))
)

// Load attachment wpIndex in onMounted
onMounted(async () => {
  await loadAll()
  try {
    if (props.projectId) {
      attachmentWpIndex.value = await getWpIndex(props.projectId)
      if (attachmentTabs.value.length > 0 && !attachmentActive.value) {
        attachmentActive.value = attachmentTabs.value[0].id
      }
    }
  } catch { attachmentWpIndex.value = [] }
})

onBeforeUnmount(() => { flushPendingSave() })
</script>

<template>
  <div class="gt-b23-process-control" :class="{ 'is-readonly': isReadonly }">
    <!-- 主体内容占位（已有逻辑在上方 script setup 中，template 由后续 spec 任务完善） -->
    <div v-if="loading" class="loading-mask">加载中...</div>

    <!-- 附件底稿 Tab 区域 -->
    <section v-if="attachmentTabs.length > 0" class="b23-attachment-section">
      <div class="attachment-header" @click="attachmentExpanded = !attachmentExpanded">
        <span>📎 附件底稿（{{ attachmentTabs.length }}）</span>
        <span>{{ attachmentExpanded ? '−' : '+' }}</span>
      </div>
      <div v-show="attachmentExpanded">
        <el-tabs v-model="attachmentActive" type="border-card">
          <el-tab-pane v-for="t in attachmentTabs" :key="t.id" :label="t.label" :name="t.id" lazy>
            <GtWpRendererLazy :wp-id="t.wpId" :readonly="isReadonly" />
          </el-tab-pane>
        </el-tabs>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.gt-b23-process-control {
  padding: 16px;
  font-size: 14px;

  &.is-readonly {
    .el-input, .el-select, .el-input-number { pointer-events: none; opacity: 0.75; }
  }

  .loading-mask { text-align: center; padding: 40px; color: #999; }
}

/* ═══ 附件底稿 Tab 区域 ═══ */
.b23-attachment-section {
  margin-top: 24px;
  border: 1px solid #d8b8ee;
  border-radius: 12px;
  overflow: hidden;

  .attachment-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: linear-gradient(135deg, #f9f0ff 0%, #efdbff 100%);
    cursor: pointer;
    user-select: none;
    font-weight: 500;
    font-size: 14px;
    color: #531dab;
  }

  :deep(.el-tabs--border-card) {
    border: none;
    border-top: 1px solid #d8b8ee;
    border-radius: 0;
  }
}
</style>
