<!--
  GtIndexChip.vue — 跨底稿索引跳转 Chip 组件

  按 design §3.8 实现：
  - 解析 value → parseIndexRef()
  - validate=true 时调 GET /api/wp-index-resolve 校验存在性
  - 4 种显示状态：valid+exists(蓝) / valid+not_exists(灰) / valid+trimmed(灰) / invalid(纯文本)
  - 11 命名空间路由 + 4 层级跳转 + 9 种边缘 case

  锚定 spec workpaper-html-renderer Task 3.7
  Validates: Requirements 3.11.8（4 层级跳转）+ 3.11.10（9 边缘 case）
-->
<template>
  <!-- Invalid ref: render as plain text, no chip styling -->
  <span v-if="!parsed" class="gt-index-chip--plain">{{ value }}</span>

  <!-- Multi-target (value contains /): show dropdown menu on hover -->
  <el-dropdown
    v-else-if="isMultiTarget"
    trigger="hover"
    @command="handleMultiTargetSelect"
  >
    <el-tooltip
      :content="tooltipContent"
      :disabled="!tooltipContent"
      placement="top"
    >
      <el-tag
        :type="chipType"
        :effect="chipEffect"
        :class="chipClass"
        size="small"
        @click.stop="handleClick"
      >
        {{ displayText }}
      </el-tag>
    </el-tooltip>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="(target, idx) in multiTargets"
          :key="idx"
          :command="target"
        >
          {{ target }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <!-- Single target: normal chip with tooltip -->
  <el-tooltip
    v-else
    :content="tooltipContent"
    :disabled="!tooltipContent"
    placement="top"
  >
    <el-tag
      :type="chipType"
      :effect="chipEffect"
      :class="chipClass"
      size="small"
      @click.stop="handleClick"
    >
      {{ displayText }}
    </el-tag>
  </el-tooltip>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/services/apiProxy'
import { parseIndexRef, type ResolvedIndexRef } from '@/utils/parseIndexRef'
import { useWpNavigationHistory } from '@/composables/useWpNavigationHistory'

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  value: string
  validate?: boolean
  contextProjectId?: string
}>(), {
  validate: true,
})

const emit = defineEmits<{
  click: [resolved: ResolvedIndexRef]
}>()

// ─── Router ───
const route = useRoute()
const router = useRouter()
const { push: pushNavHistory } = useWpNavigationHistory()

// ─── State ───
const parsed = ref<ResolvedIndexRef | null>(null)
const resolveStatus = ref<'pending' | 'exists' | 'not_exists' | 'trimmed' | 'error'>('pending')
const trimReason = ref('')
const resolving = ref(false)

// ─── Computed ───
const projectId = computed(() => {
  return props.contextProjectId || (route.params.projectId as string) || ''
})

const isCrossProject = computed(() => {
  // If contextProjectId is provided and differs from current route project, it's cross-project
  if (!props.contextProjectId) return false
  const routeProjectId = route.params.projectId as string
  return routeProjectId && props.contextProjectId !== routeProjectId
})

const isMultiTarget = computed(() => {
  return props.value.includes('/')
})

const multiTargets = computed(() => {
  if (!isMultiTarget.value) return []
  return props.value.split('/').map(t => t.trim()).filter(Boolean)
})

const displayText = computed(() => {
  if (!parsed.value) return props.value
  // For multi-target, show original value
  if (isMultiTarget.value) return props.value
  const { ns, target } = parsed.value
  // For strict mode refs, show namespace:target
  if (ns === 'Note' || ns === 'TB' || ns === 'Adj' || ns === 'Att' ||
      ns === 'EQCR' || ns === 'Calc' || ns === 'Sample' || ns === 'Confirm') {
    return `${ns}:${target}`
  }
  // For wp/sheet/cell loose mode, show target directly
  return target
})

const chipType = computed<'' | 'info' | 'success' | 'warning' | 'danger'>(() => {
  if (resolveStatus.value === 'exists') return ''  // primary/default
  if (resolveStatus.value === 'not_exists' || resolveStatus.value === 'trimmed') return 'info'
  if (resolveStatus.value === 'error') return 'danger'
  return ''  // pending
})

const chipEffect = computed(() => {
  if (resolveStatus.value === 'exists') return 'light'
  return 'plain'
})

const chipClass = computed(() => {
  const classes = ['gt-index-chip']
  if (resolveStatus.value === 'exists' && !isCrossProject.value) {
    classes.push('gt-index-chip--clickable')
  }
  if (resolveStatus.value === 'not_exists' || resolveStatus.value === 'trimmed') {
    classes.push('gt-index-chip--disabled')
  }
  if (resolving.value) {
    classes.push('gt-index-chip--loading')
  }
  return classes
})

const tooltipContent = computed(() => {
  if (!parsed.value) return ''

  if (isCrossProject.value) {
    return '跨项目引用，不可跳转'
  }

  if (resolveStatus.value === 'not_exists') {
    return '底稿不存在或被裁剪'
  }

  if (resolveStatus.value === 'trimmed') {
    return trimReason.value ? `已裁剪：${trimReason.value}` : '已裁剪'
  }

  if (resolveStatus.value === 'exists') {
    const { ns, layer, target } = parsed.value
    const layerLabel = ['', '单元格', 'Sheet', '底稿', '模块'][layer] || ''
    return `${layerLabel}跳转 → ${ns}:${target}`
  }

  if (resolveStatus.value === 'pending' && resolving.value) {
    return '正在校验...'
  }

  return ''
})

// ─── Methods ───
async function resolveRef() {
  if (!parsed.value || !props.validate) {
    if (parsed.value) resolveStatus.value = 'exists'  // skip validation, assume exists
    return
  }

  resolving.value = true
  try {
    const result = await api.get<{
      exists: boolean
      trimmed?: boolean
      reason?: string
      empty?: boolean
    }>('/api/wp-index-resolve', {
      params: {
        ref: props.value,
        project_id: projectId.value || undefined,
      },
    })

    if (result.trimmed) {
      resolveStatus.value = 'trimmed'
      trimReason.value = result.reason || ''
    } else if (result.exists) {
      resolveStatus.value = 'exists'
      if (result.empty && parsed.value) {
        parsed.value.empty = true
      }
    } else {
      resolveStatus.value = 'not_exists'
    }
  } catch {
    // On error, default to exists to avoid blocking user
    resolveStatus.value = 'exists'
  } finally {
    resolving.value = false
  }
}

function handleClick() {
  if (!parsed.value) return
  if (isCrossProject.value) return
  if (resolveStatus.value === 'not_exists' || resolveStatus.value === 'trimmed') return

  emit('click', parsed.value)
  navigateToTarget(parsed.value)
}

function handleMultiTargetSelect(target: string) {
  const ref = parseIndexRef(target)
  if (!ref) return
  if (isCrossProject.value) return

  emit('click', ref)
  navigateToTarget(ref)
}

function navigateToTarget(resolved: ResolvedIndexRef) {
  const pid = projectId.value
  if (!pid) return

  const { ns, target } = resolved

  // Task 11.2: push current location to navigation history before jumping
  const currentWpId = route.params.id as string || route.params.wpId as string || ''
  if (currentWpId && ns === 'wp') {
    pushNavHistory({
      wpId: currentWpId,
      wpCode: route.query.wp_code as string || '',
      sheetName: route.query.sheet as string || '',
    })
  }

  switch (ns) {
    case 'wp':
      // Layer 3: cross-workpaper jump → workpaper editor
      router.push({
        path: `/projects/${pid}/workpapers/${target}/edit`,
      })
      break

    case 'sheet':
      // Layer 2: same workpaper sheet switch → query param
      router.push({
        path: route.path,
        query: { ...route.query, sheet: target },
      })
      break

    case 'cell': {
      // Layer 1: sheet + cell highlight
      const [sheetPart, cellPart] = target.split('!')
      router.push({
        path: route.path,
        query: { ...route.query, sheet: sheetPart, cell: cellPart },
      })
      break
    }

    case 'Note':
      // Layer 4: disclosure notes module
      router.push({
        path: `/projects/${pid}/disclosure-notes`,
        query: { section: target },
      })
      break

    case 'TB':
      // Layer 4: trial balance
      router.push({
        path: `/projects/${pid}/trial-balance`,
        query: { account: target },
      })
      break

    case 'Adj':
      // Layer 4: adjustments
      router.push({
        path: `/projects/${pid}/adjustments`,
        query: { id: target },
      })
      break

    case 'Att':
      // Layer 4: attachments
      router.push({
        path: `/projects/${pid}/attachments`,
        query: { id: target },
      })
      break

    case 'EQCR':
      // Layer 4: EQCR workbench
      router.push({
        path: '/eqcr/workbench',
        query: { id: target },
      })
      break

    case 'Calc':
      // Layer 4: calculation dialog (emit event, handled by parent)
      // No route navigation, parent handles dialog trigger
      break

    case 'Sample':
      // Layer 4: sampling tool
      router.push({
        path: `/projects/${pid}/sampling-enhanced`,
        query: { id: target },
      })
      break

    case 'Confirm':
      // Layer 4: confirmation management
      router.push({
        path: '/confirmation',
        query: { id: target },
      })
      break
  }
}

// ─── Lifecycle ───
function init() {
  if (isMultiTarget.value) {
    // For multi-target values (containing /), parse the first target
    const firstTarget = multiTargets.value[0]
    parsed.value = firstTarget ? parseIndexRef(firstTarget) : null
  } else {
    parsed.value = parseIndexRef(props.value)
  }
  if (parsed.value) {
    resolveRef()
  }
}

onMounted(init)

// Re-parse and re-validate when value changes
watch(() => props.value, () => {
  resolveStatus.value = 'pending'
  trimReason.value = ''
  init()
})
</script>

<style scoped>
.gt-index-chip--plain {
  font-size: inherit;
  color: inherit;
}

.gt-index-chip {
  cursor: default;
  font-size: 12px;
  vertical-align: middle;
}

.gt-index-chip--clickable {
  cursor: pointer;
  transition: opacity 0.2s;
}

.gt-index-chip--clickable:hover {
  opacity: 0.8;
}

.gt-index-chip--disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.gt-index-chip--loading {
  opacity: 0.7;
}
</style>
