<script setup lang="ts">
/**
 * GtA16Bundle — A16 管理层声明书聚合组件
 *
 * 将 A16 的 7 个 word-template 子底稿聚合为单一 Bundle 组件，
 * 内部通过 el-tabs 分发渲染各子底稿的 WorkpaperWordEditor。
 *
 * 模式参考：GtA11Bundle（极简模式，无 composable / 无联动 / 无完成追踪）
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import { api } from '@/services/apiProxy'

const WorkpaperWordEditor = defineAsyncComponent(() => import('./WorkpaperWordEditor.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  readonly?: boolean
}>()

// ─── Tab 配置（静态） ───
const TABS = [
  { id: 'A16-1', label: '会计审核版', wpCode: 'A16-1' },
  { id: 'A16-2', label: '整合审核版', wpCode: 'A16-2' },
  { id: 'A16-3', label: 'IPO补贴', wpCode: 'A16-3' },
  { id: 'A16-4', label: 'IPO券商审阅', wpCode: 'A16-4' },
  { id: 'A16-5', label: '新三板申报', wpCode: 'A16-5' },
  { id: 'A16-6', label: '合营协议', wpCode: 'A16-6' },
  { id: 'A16-7', label: '关联交易合规说明', wpCode: 'A16-7' },
]

// ─── State ───
const route = useRoute()
const router = useRouter()
const active = ref('')
const wpIndex = ref<WpIndexItem[]>([])
const loading = ref(false)

/**
 * wp_index 是否已加载结束（成功或失败都算结束）。
 *
 * 🔴 空态判据必须用它，不能只看 `visibleTabs.length === 0`：首次渲染发生在 onMounted
 * 发请求之前，那一刻 `visibleTabs` 同样是 0 —— 单看它会在加载前闪一下空态
 * （spec api-prefix-fix-recovery 任务 5 明确要求「加载中不误显空态」）。
 */
const loaded = ref(false)

/** 取 wp_index 失败的原因；空串 = 没失败 */
const loadError = ref('')

// ─── wp_id 解析 ───
const wpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of wpIndex.value) {
    if (item.wp_code?.startsWith('A16-')) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

// ─── 仅显示 wp_index 中存在的 Tab ───
const visibleTabs = computed(() =>
  TABS.filter(t => !!wpIdMap.value[t.wpCode])
)

/**
 * 还没生成的子底稿。TABS 是前端静态配置 ⇒ 期望清单已知，缺哪几张可以直接列出来，
 * 不必只说「一张都没有」。
 */
const missingTabs = computed(() =>
  TABS.filter(t => !wpIdMap.value[t.wpCode])
)

/**
 * 空态文案里的「缺哪几张」。
 *
 * 🔴 拼装放在 script 里而不是模板表达式：模板里的 `missingTabs.map(t => t.id)` 拿不到
 * 上下文类型（vue-tsc 报 TS7006『Parameter t implicitly has an any type』），
 * 而这类隐式 any 在本仓的区域类型检查里算新增错误。
 */
const missingCodesText = computed(() =>
  missingTabs.value.map(t => t.id).join('、')
)

// ─── sheetName 路由 ───
watch(() => props.sheetName, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) {
    active.value = v
  }
})

watch(() => route.query.sheet as string | undefined, (v) => {
  if (v && visibleTabs.value.some(t => t.id === v)) {
    active.value = v
  }
})

// ─── 加载 ───
function describeError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e ?? '')
  return msg.trim() || '未知错误'
}

async function loadIndex() {
  loading.value = true
  loaded.value = false
  loadError.value = ''
  try {
    wpIndex.value = props.projectId ? await getWpIndex(props.projectId) : []
  } catch (e) {
    // 取索引失败 ≠「一张都没生成」，两者提示必须分开，否则等于告诉用户一个假结论
    wpIndex.value = []
    loadError.value = describeError(e)
  } finally {
    loading.value = false
    loaded.value = true
  }
  initActive()
}

/** 初始化 active tab：props.sheetName > route.query.sheet > 第一个可见 Tab */
function initActive() {
  const sheet = props.sheetName || (route.query.sheet as string | undefined)
  if (sheet && visibleTabs.value.some(t => t.id === sheet)) {
    active.value = sheet
  } else {
    active.value = visibleTabs.value[0]?.id || ''
  }
}

/** 去底稿列表生成子底稿（与 useWorkpaperNavigation 的 A16 兜底同一写法） */
function goWorkpaperList() {
  if (!props.projectId) return
  router.push({
    name: 'WorkpaperList',
    params: { projectId: props.projectId },
    query: { highlight: 'A16' },
  })
}

// ─── A16 推荐版本（R8 / 缺陷修复 2026-11-16）────────────────────────────────
//
// 这套信息原先只挂在 `GtAProgramConsole` 的 A16 seq2 行（要求 `sheetCode === 'A16'`
// 且走 `a-program-console`），而 A16 底稿的 componentType 已是 `a16-bundle`
// ⇒ `isA16Table` 恒假 ⇒ 推荐标记在界面上永远不出现（预存接线错位）。
//
// 这里在 Bundle 层重新接上：进页面就取推荐版本，若推荐的那张子底稿本项目还没生成，
// 给一条提示 + 「一键创建」。已生成时不打扰（页签本身已经列出全部可用版本）。
const recommendedCode = ref('')
const recommendedLabel = ref('')
const creatingRecommended = ref(false)

/** 推荐版本未在项目中创建时才有值（= 需要在 Bundle 顶部提示） */
const recommendedMissing = computed(() => {
  if (!recommendedCode.value) return ''
  return wpIdMap.value[recommendedCode.value] ? '' : recommendedCode.value
})

async function loadRecommendedVersion() {
  if (!props.projectId) return
  try {
    const data = await api.get<any>(
      `/api/projects/${props.projectId}/a16/recommended-version`,
      { _silent: true } as any,
    )
    const payload = data?.data ?? data
    if (typeof payload?.recommended_code === 'string') {
      recommendedCode.value = payload.recommended_code
      recommendedLabel.value =
        typeof payload.recommended_label === 'string' ? payload.recommended_label : payload.recommended_code
    }
  } catch {
    // 推荐版本是增强信息：取不到就不显示，不影响页签与编辑器
  }
}

/** 一键创建推荐的子底稿，成功后刷新 wp_index 让页签出现 */
async function createRecommendedVersion() {
  const code = recommendedMissing.value
  if (!code || !props.projectId || creatingRecommended.value) return
  creatingRecommended.value = true
  try {
    const res = await api.post<any>(
      `/api/projects/${props.projectId}/working-papers/generate-from-codes`,
      { wp_codes: [code] },
    )
    const receipt = res?.data ?? res ?? {}
    const created: string[] = Array.isArray(receipt.created_codes) ? receipt.created_codes : []
    const inRecycle: string[] = Array.isArray(receipt.in_recycle_codes) ? receipt.in_recycle_codes : []
    const failures: any[] = Array.isArray(receipt.failures) ? receipt.failures : []

    if (created.includes(code)) {
      ElMessage.success(`已创建 ${code}${recommendedLabel.value ? ` ${recommendedLabel.value}` : ''}`)
    } else if (inRecycle.includes(code)) {
      // 在回收站里：generate-from-codes 不会重建（平台语义，见 wp_generation_receipt）
      ElMessage.warning(`${code} 在回收站中，请先到回收站恢复后再编辑`)
    } else if (failures.length) {
      ElMessage.error(`创建 ${code} 失败：${failures[0]?.reason || failures[0]?.message || '请重试'}`)
    } else {
      ElMessage.warning(`${code} 未创建（已有底稿或已被裁剪），请到底稿列表确认`)
    }
    // 无论哪种结果都刷新：创建成功要让页签出现，回收站场景要让提示文案与实际一致
    await loadIndex()
    await loadRecommendedVersion()
  } catch (e: any) {
    ElMessage.error('创建失败：' + (e?.response?.data?.detail?.message || e?.message || '请重试'))
  } finally {
    creatingRecommended.value = false
  }
}

// ─── Lifecycle ───
onMounted(async () => {
  await loadIndex()
  await loadRecommendedVersion()
})
</script>

<template>
  <div class="gt-a16-bundle" v-loading="loading">
    <!-- 取索引失败：不能说成「未生成」（那是假信息），给原因 + 重试 -->
    <el-empty
      v-if="loaded && loadError"
      class="gt-a16-bundle__empty"
      :description="`底稿索引加载失败：${loadError}`"
    >
      <el-button type="primary" @click="loadIndex">重试</el-button>
    </el-empty>

    <!-- 本项目一张 A16 子底稿都没生成时，原先只剩空白页签区、看不出原因（residual 任务 28 实测） -->
    <el-empty
      v-else-if="loaded && visibleTabs.length === 0"
      class="gt-a16-bundle__empty"
      :description="`本项目还没有生成 A16 管理层声明书的子底稿：${missingCodesText} 均未生成。请到底稿列表按需生成后再编辑。`"
    >
      <el-button type="primary" @click="goWorkpaperList">去底稿列表生成</el-button>
    </el-empty>

    <el-tabs v-else-if="visibleTabs.length" v-model="active">
      <!-- A16 推荐版本：推荐的那张子底稿本项目还没生成时给提示 + 一键创建。
           原先这套信息只在 a-program-console 的 A16 seq2 行，而 A16 已是 a16-bundle
           ⇒ 界面上永远看不到（缺陷修复 2026-11-16）。 -->
      <el-alert
        v-if="recommendedMissing"
        class="gt-a16-bundle__recommend"
        type="info"
        show-icon
        :closable="false"
      >
        <template #title>
          推荐使用「{{ recommendedMissing }} {{ recommendedLabel }}」，该版本尚未在本项目中生成。
        </template>
        <el-button
          size="small"
          type="primary"
          :loading="creatingRecommended"
          @click="createRecommendedVersion"
        >
          一键创建
        </el-button>
      </el-alert>
      <el-tab-pane
        v-for="t in visibleTabs"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <WorkpaperWordEditor
          :wp-id="wpIdMap[t.wpCode]"
          :readonly="readonly"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.gt-a16-bundle__empty {
  padding: 24px 0;
}
.gt-a16-bundle__recommend {
  margin-bottom: 12px;
}
</style>
