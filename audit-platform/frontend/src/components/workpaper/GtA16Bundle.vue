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
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'

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

// ─── Lifecycle ───
onMounted(loadIndex)
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
