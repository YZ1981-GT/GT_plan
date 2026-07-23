<script setup lang="ts">
/**
 * GtB2Bundle — B2 前任-后任注册会计师沟通聚合组件
 *
 * Tabs：基础信息 / 程序表 / 流程总览 / B2-5 尽调评价。
 * 基础信息：录入前任所名称 + 项目组联系方式（供信函占位符自动填充）。
 * 流程总览：三场景泳道 + 适用性裁剪 + 跳转子底稿。
 * 独立信函（B2-1/3/6/8/11/12）经 router 跳转对应 WorkpaperEditor 打开。
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import { api } from '@/services/apiProxy'
import GtAProgramConsole from './GtAProgramConsole.vue'
import GtB2PredecessorInfo from './GtB2PredecessorInfo.vue'
import GtB2FlowOverview from './GtB2FlowOverview.vue'

const GtB25Evaluation = defineAsyncComponent(() => import('./GtB25Evaluation.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
}>()

// ─── Tab 配置（静态） ───
const TABS = [
  { id: 'info', label: '基础信息', wpCode: null },
  { id: 'program', label: '程序表', wpCode: null },
  { id: 'flow', label: '流程总览', wpCode: null },
  { id: 'B2-5', label: 'B2-5 沟通后评价', wpCode: 'B2-5' },
]

// ─── State ───
const route = useRoute()
const router = useRouter()
const active = ref('')
const wpIndex = ref<WpIndexItem[]>([])
const loading = ref(false)

// ─── 适用性（Task 5） ───
interface Applicability {
  firstEngagement: boolean
  reviewPredecessorWp: boolean
  ipoReaudit: boolean
}
const APPLICABILITY_ITEM = 'B2-applicability'
const applicability = ref<Applicability>({
  firstEngagement: true,
  reviewPredecessorWp: true,
  ipoReaudit: true,
})
const applicabilitySaving = ref(false)

// ─── 函件往来状态台账（Task 13 / D+E） ───
const LETTER_STATUS_ITEM = 'B2-letter-status'
interface LetterStatus { status?: string; sentDate?: string; replyDate?: string; followUpDate?: string }
const letterStatus = ref<Record<string, LetterStatus>>({})
let _letterStatusTimer: ReturnType<typeof setTimeout> | null = null

// ─── wp_id 解析 ───
const wpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of wpIndex.value) {
    if (item.wp_code?.startsWith('B2-')) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

// ─── 可见 Tab：程序表/基础信息/流程总览恒显；B2-5 需存在 ───
const visibleTabs = computed(() =>
  TABS.filter(t => t.wpCode === null || !!wpIdMap.value[t.wpCode])
)

// ─── sheetName 路由 ───
watch(() => props.sheetName, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) active.value = v
})
watch(() => route.query.sheet as string | undefined, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) active.value = v
})

// ─── 适用性 加载/保存 ───
async function loadApplicability() {
  if (!props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const row = list.find((r) => r.item_id === APPLICABILITY_ITEM)
    if (row?.remark) {
      try {
        const parsed = JSON.parse(row.remark)
        if (parsed && typeof parsed === 'object') {
          applicability.value = { ...applicability.value, ...parsed }
        }
      } catch { /* ignore */ }
    }
  } catch { /* 缺省全 true */ }
}

async function saveApplicability() {
  if (props.readonly || !props.wpId) return
  applicabilitySaving.value = true
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: APPLICABILITY_ITEM, conclusion: null, remark: JSON.stringify(applicability.value) }],
    })
  } catch { /* silent */ } finally {
    applicabilitySaving.value = false
  }
}

async function loadLetterStatus() {
  if (!props.wpId) return
  try {
    const res = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    const row = list.find((r) => r.item_id === LETTER_STATUS_ITEM)
    if (row?.remark) {
      try {
        const parsed = JSON.parse(row.remark)
        if (parsed && typeof parsed === 'object') letterStatus.value = parsed
      } catch { /* ignore */ }
    }
  } catch { /* empty */ }
}

function handleUpdateStatus(wpCode: string, patch: LetterStatus) {
  if (props.readonly) return
  letterStatus.value = { ...letterStatus.value, [wpCode]: patch }
  if (_letterStatusTimer) clearTimeout(_letterStatusTimer)
  _letterStatusTimer = setTimeout(async () => {
    try {
      await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
        project_id: props.projectId || undefined,
        items: [{ item_id: LETTER_STATUS_ITEM, conclusion: null, remark: JSON.stringify(letterStatus.value) }],
      })
    } catch { /* silent */ }
  }, 600)
}

// ─── 流程总览：打开子底稿 ───
function handleOpen(wpCode: string) {
  if (wpCode === 'B2-5') {
    if (visibleTabs.value.some(t => t.id === 'B2-5')) active.value = 'B2-5'
    return
  }
  const targetId = wpIdMap.value[wpCode]
  if (targetId && props.projectId) {
    router.push({ path: `/projects/${props.projectId}/workpapers/${targetId}/edit` })
  }
}

// ─── Lifecycle ───
onMounted(async () => {
  loading.value = true
  try {
    if (props.projectId) {
      wpIndex.value = await getWpIndex(props.projectId)
    }
  } catch {
    wpIndex.value = []
  } finally {
    loading.value = false
  }

  await loadApplicability()
  await loadLetterStatus()

  const sheet = props.sheetName || (route.query.sheet as string)
  if (sheet && visibleTabs.value.some(t => t.id === sheet)) {
    active.value = sheet
  } else {
    active.value = visibleTabs.value[0]?.id || ''
  }
})
</script>

<template>
  <div class="gt-b2-bundle" v-loading="loading">
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="t in visibleTabs"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <!-- 基础信息 -->
        <GtB2PredecessorInfo
          v-if="t.id === 'info'"
          :wp-id="wpId"
          :project-id="projectId"
          :readonly="readonly"
        />

        <!-- 程序表 -->
        <GtAProgramConsole
          v-else-if="t.id === 'program'"
          :wp-id="wpId"
          :embedded="true"
          :readonly="readonly"
        />

        <!-- 流程总览 + 适用性 -->
        <div v-else-if="t.id === 'flow'" class="gt-b2-bundle__flow">
          <el-card shadow="never" class="gt-b2-bundle__applic">
            <template #header>
              <span class="gt-b2-bundle__applic-title">适用性判断（勾选不适用的场景以裁剪）</span>
            </template>
            <div class="gt-b2-bundle__switches">
              <el-switch
                v-model="applicability.firstEngagement"
                :disabled="readonly"
                active-text="① 首次承接（委托前沟通）"
                @change="saveApplicability"
              />
              <el-switch
                v-model="applicability.reviewPredecessorWp"
                :disabled="readonly"
                active-text="② 查阅前任底稿（期初余额）"
                @change="saveApplicability"
              />
              <el-switch
                v-model="applicability.ipoReaudit"
                :disabled="readonly"
                active-text="③ 重新审计 / IPO 前任评价"
                @change="saveApplicability"
              />
            </div>
          </el-card>
          <GtB2FlowOverview
            :wp-id-map="wpIdMap"
            :applicability="applicability"
            :letter-status="letterStatus"
            :readonly="readonly"
            @open="handleOpen"
            @update-status="handleUpdateStatus"
          />
        </div>

        <!-- B2-5 沟通后评价（决策向导） -->
        <GtB25Evaluation
          v-else-if="t.wpCode === 'B2-5'"
          :wp-id="wpIdMap[t.wpCode]"
          :project-id="projectId"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.gt-b2-bundle__flow { padding: 4px; }
.gt-b2-bundle__applic { margin-bottom: 14px; max-width: 720px; }
.gt-b2-bundle__applic-title { font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
.gt-b2-bundle__switches { display: flex; flex-direction: column; gap: 12px; }
</style>
