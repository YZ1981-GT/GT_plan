<script setup lang="ts">
/**
 * GtReviewBundle — A21~A25 角色复核聚合组件
 *
 * 将主复核清单 + 2 个子复核清单聚合为单一 Bundle，
 * 内部通过 el-tabs 分发渲染 GtReviewChecklist。
 *
 * 复用模式：wpCode prop 决定子底稿编码前缀（A21/A22/A23/A24/A25）
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'

const GtReviewChecklist = defineAsyncComponent(() => import('./GtReviewChecklist.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode: string       // 'A21' | 'A22' | 'A23' | 'A24' | 'A25'
  sheetName?: string
  readonly?: boolean
}>()

const emit = defineEmits<{ (e: 'save'): void }>()

// ─── Tab 标签 ───
const SUFFIX_LABELS: Record<string, string> = {
  '': '复核清单（主表）',
  '-1': '复核清单（第一部分）',
  '-2': '复核清单（第二部分）',
}

// ─── State ───
const route = useRoute()
const active = ref('')
const wpIndex = ref<WpIndexItem[]>([])
const loading = ref(false)

// ─── wp_id 解析：查找子底稿 ───
const wpIdMap = computed<Record<string, string>>(() => {
  const prefix = props.wpCode + '-'
  const map: Record<string, string> = {}
  for (const item of wpIndex.value) {
    if (item.wp_code?.startsWith(prefix)) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

// ─── 动态 Tab 列表 ───
const tabs = computed(() => {
  const list: { id: string; label: string; wpCode: string; wpId: string }[] = []
  // 主表始终显示
  list.push({
    id: props.wpCode,
    label: SUFFIX_LABELS[''],
    wpCode: props.wpCode,
    wpId: props.wpId,
  })
  // 子表按后缀 -1, -2 显示（如存在于 wpIdMap）
  for (const suffix of ['-1', '-2']) {
    const code = props.wpCode + suffix
    const id = wpIdMap.value[code]
    if (id) {
      list.push({
        id: code,
        label: SUFFIX_LABELS[suffix],
        wpCode: code,
        wpId: id,
      })
    }
  }
  return list
})

// ─── sheetName / route query 路由 ───
watch(() => props.sheetName, (v) => {
  if (v && tabs.value.some(t => t.id === v)) {
    active.value = v
  }
})

watch(() => route.query.sheet as string | undefined, (v) => {
  if (v && tabs.value.some(t => t.id === v)) {
    active.value = v
  }
})

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

  // 初始化 active tab
  const sheet = props.sheetName || (route.query.sheet as string)
  if (sheet && tabs.value.some(t => t.id === sheet)) {
    active.value = sheet
  } else {
    active.value = tabs.value[0]?.id || ''
  }
})
</script>

<template>
  <div class="gt-review-bundle" v-loading="loading">
    <el-tabs v-model="active">
      <el-tab-pane
        v-for="t in tabs"
        :key="t.id"
        :label="t.label"
        :name="t.id"
        lazy
      >
        <GtReviewChecklist
          :wp-id="t.wpId"
          :project-id="props.projectId"
          :wp-code="t.wpCode"
          :readonly="props.readonly"
          @save="emit('save')"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
