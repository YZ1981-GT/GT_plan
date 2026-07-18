<!--
  GtIndexChip.vue — 跨底稿索引跳转 Chip 组件

  按 ACNR design §四大消费库关联统一 — 索引库 GtIndexChip 实现：
  - 解析 value → parseIndexRef()（本地语法解析，仅用于显示）
  - validate=true 时调 ACNR resolve(ns:target) 获取 addr_id + jump_route（R13.3）
  - 4 种显示状态：valid+exists(蓝) / valid+not_exists(灰) / valid+trimmed(灰) / invalid(纯文本)
  - 跳转使用 ACNR 返回的 jump_route，不自行 parse 路由（R7.3 铁律）

  锚定 spec acnr Task 17.2
  Validates: Requirements 11.2, 11.3, 13.3
-->
<template>
  <!-- Invalid ref: render as plain text, no chip styling -->
  <span v-if="!parsed" class="gt-index-chip--plain">{{ refValue }}</span>

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
import { ElMessage } from 'element-plus'
import { parseIndexRef, type ResolvedIndexRef } from '@/utils/parseIndexRef'
import { useWpNavigationHistory } from '@/composables/useWpNavigationHistory'
import { useAcnr, type AcnrResolveResult } from '@/services/acnr'
import { BUNDLE_SHEET_ALIASES } from './bundleSheetAliases'

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  value?: string
  /** @deprecated 历史误用；解析优先级低于 value / wpCode / target */
  label?: string
  /** 简写：等价于 value（部分 Tab 误传 wp-code） */
  wpCode?: string
  /** 简写：等价于 value（部分 Tab 误传 target） */
  target?: string
  validate?: boolean
  contextProjectId?: string
  /** 为 true 时 click 仅 emit 不自动导航（供弹窗模式使用） */
  preventNavigate?: boolean
  /** 为 true 时 chip 灰显不可点击（程序步骤不适用时） */
  disabled?: boolean
  /** 附带上下文摘要（如缺陷描述），显示在 tooltip 中 */
  context?: string
}>(), {
  validate: true,
  preventNavigate: false,
  disabled: false,
})

/** 归一化索引文本，避免 value 未传时 .includes 抛错 */
const refValue = computed(() => {
  const raw = props.value ?? props.wpCode ?? props.target ?? props.label ?? ''
  return typeof raw === 'string' ? raw : ''
})

const emit = defineEmits<{
  click: [resolved: ResolvedIndexRef]
}>()

// ─── Router ───
const route = useRoute()
const router = useRouter()
const { push: pushNavHistory } = useWpNavigationHistory()

// ─── ACNR SDK (R13.3: 不自行 parse，委托 ACNR resolve) ───
const { resolve: acnrResolve, resolveInstance: acnrResolveInstance } = useAcnr()

// ─── State ───
const parsed = ref<ResolvedIndexRef | null>(null)
const resolveStatus = ref<'pending' | 'exists' | 'not_exists' | 'trimmed' | 'error'>('pending')
const trimReason = ref('')
const resolving = ref(false)
/** ACNR resolve 结果缓存，用于跳转时直接取 jump_route */
const acnrResult = ref<AcnrResolveResult | null>(null)

// ─── Computed ───
const projectId = computed(() => {
  return props.contextProjectId || (route?.params?.projectId as string) || ''
})

const isCrossProject = computed(() => {
  // If contextProjectId is provided and differs from current route project, it's cross-project
  if (!props.contextProjectId) return false
  const routeProjectId = route?.params?.projectId as string
  return !!routeProjectId && props.contextProjectId !== routeProjectId
})

const isMultiTarget = computed(() => {
  return refValue.value.includes('/')
})

const multiTargets = computed(() => {
  if (!isMultiTarget.value) return []
  return refValue.value.split('/').map(t => t.trim()).filter(Boolean)
})

const displayText = computed(() => {
  if (!parsed.value) return refValue.value
  // For multi-target, show original value
  if (isMultiTarget.value) return refValue.value
  const { ns, target } = parsed.value
  // For strict mode refs, show namespace:target
  if (ns === 'Note' || ns === 'TB' || ns === 'Adj' || ns === 'Att' ||
      ns === 'EQCR' || ns === 'Calc' || ns === 'Sample' || ns === 'Confirm') {
    return `${ns}:${target}`
  }
  // For wp/sheet/cell loose mode, show target directly
  return target
})

const chipType = computed<'primary' | 'info' | 'success' | 'warning' | 'danger'>(() => {
  if (props.disabled) return 'info'
  if (resolveStatus.value === 'exists') return 'primary'  // 默认色（element-plus v2 起 '' 已废弃）
  if (resolveStatus.value === 'not_exists' || resolveStatus.value === 'trimmed') return 'info'
  if (resolveStatus.value === 'error') return 'danger'
  return 'primary'  // pending
})

const chipEffect = computed(() => {
  if (resolveStatus.value === 'exists') return 'light'
  return 'plain'
})

const chipClass = computed(() => {
  const classes = ['gt-index-chip']
  if (props.disabled) {
    classes.push('gt-index-chip--disabled')
    return classes
  }
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

  if (props.disabled) {
    return '当前步骤不适用，chip 不可点击'
  }

  if (isCrossProject.value) {
    return '跨项目引用，不可跳转'
  }

  if (resolveStatus.value === 'not_exists') {
    return '底稿不存在'
  }

  if (resolveStatus.value === 'trimmed') {
    return trimReason.value ? `已裁剪：${trimReason.value}` : '已裁剪'
  }

  if (resolveStatus.value === 'exists') {
    const { ns, layer, target } = parsed.value
    const layerLabel = ['', '单元格', 'Sheet', '底稿', '模块'][layer] || ''
    const base = `${layerLabel}跳转 → ${ns}:${target}`
    // 附带上下文摘要
    if (props.context) {
      return `${base}\n${props.context}`
    }
    return base
  }

  if (resolveStatus.value === 'pending' && resolving.value) {
    return '正在校验...'
  }

  return ''
})

// ─── Methods ───

/**
 * 调用 ACNR resolve(ns:target) 校验存在性并获取 addr_id + jump_route (R13.3)
 * 不自行 parse 路由，委托 ACNR 统一解析。
 */
async function resolveRef() {
  if (!parsed.value || !props.validate) {
    if (parsed.value) resolveStatus.value = 'exists'  // skip validation, assume exists
    return
  }

  resolving.value = true
  try {
    // R13.3: 调 resolve(ns:target) 获取 addr_id + jump_route，不自行 parse
    const indexRef = buildIndexRef(parsed.value)
    const result = await acnrResolve({
      index_ref: indexRef,
      project_id: projectId.value || undefined,
    })

    acnrResult.value = result

    if (!result.found) {
      // ACNR miss — 可能是 trimmed 或 not_exists
      if (result.trimmed) {
        resolveStatus.value = 'trimmed'
        trimReason.value = result.reason || ''
      } else {
        resolveStatus.value = 'not_exists'
      }
    } else {
      // ACNR 命中
      resolveStatus.value = 'exists'
    }
  } catch {
    // ACNR 不可用时返回错误（R13.5: 不回退旧逻辑）
    resolveStatus.value = 'error'
    acnrResult.value = null
  } finally {
    resolving.value = false
  }
}

/**
 * 从 parsed ResolvedIndexRef 构建 index_ref 字符串给 ACNR
 * 格式: `ns:target`
 */
function buildIndexRef(resolved: ResolvedIndexRef): string {
  return `${resolved.ns}:${resolved.target}`
}

/** 解析 wp_code → wp_id 再跳转到底稿编辑页 (经 ACNR resolve_instance，R13.1) */
async function resolveAndNavigateToWp(wpCode: string, pid: string) {
  // ─── 虚拟子码重定向：A16-1~7 → A16 + ?version= ───
  if (/^A16-[1-7]$/.test(wpCode)) {
    try {
      const res = await acnrResolveInstance({
        project_id: pid,
        parent: 'A16',
        sheet_code: 'A16',
      })
      if (res?.found && res.wp_id) {
        router.push({
          path: `/projects/${pid}/workpapers/${res.wp_id}/edit`,
          query: { version: wpCode },
        })
      } else {
        ElMessage.warning('A16 底稿尚未生成')
      }
    } catch {
      ElMessage.warning(`跳转 ${wpCode} 失败，请手动查找`)
    }
    return
  }

  // ─── Bundle sheet alias（design §Sheet/Tab 路由契约）───
  const alias = BUNDLE_SHEET_ALIASES[wpCode]

  try {
    // R13.1: resolve_instance 是唯一 wp_id 出口
    const res = await acnrResolveInstance({
      project_id: pid,
      parent: wpCode,
      sheet_code: wpCode,
    })

    if (res?.found && res.wp_id) {
      // 使用 ACNR 返回的 jump_route（R7.3 铁律：不自行拼路由）
      if (res.jump_route) {
        router.push(res.jump_route)
      } else {
        router.push({ path: `/projects/${pid}/workpapers/${res.wp_id}/edit` })
      }
    } else if (alias) {
      // 独立底稿不存在但有 bundle alias → 路由到父 bundle 的指定 sheet
      const parentRes = await acnrResolveInstance({
        project_id: pid,
        parent: alias.parent,
        sheet_code: alias.parent,
      })
      if (parentRes?.found && parentRes.wp_id) {
        router.push({
          path: `/projects/${pid}/workpapers/${parentRes.wp_id}/edit`,
          query: { sheet: alias.sheet },
        })
      } else {
        ElMessage.warning(`底稿 ${wpCode} 尚未生成`)
      }
    } else if (res?.error === 'not_found') {
      ElMessage.warning(`底稿 ${wpCode} 尚未生成`)
    } else {
      // 降级：用 wp_code 作为 query 跳转到工作台筛选
      router.push({ path: `/projects/${pid}/workpapers`, query: { search: wpCode } })
    }
  } catch {
    // R13.5: 转发失败返回错误，不回退旧逻辑
    ElMessage.warning(`跳转 ${wpCode} 失败，请手动查找`)
  }
}

function handleClick() {
  if (!parsed.value) return
  if (props.disabled) return
  if (isCrossProject.value) return
  // preventNavigate 模式下跳过存在性检查（弹窗子底稿可能未生成实例）
  if (!props.preventNavigate) {
    if (resolveStatus.value === 'not_exists' || resolveStatus.value === 'trimmed') return
  }

  emit('click', parsed.value)
  if (!props.preventNavigate) {
    navigateToTarget(parsed.value)
  }
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
  const currentWpId = (route?.params?.id as string) || (route?.params?.wpId as string) || ''
  if (currentWpId && ns === 'wp') {
    pushNavHistory({
      wpId: currentWpId,
      wpCode: (route?.query?.wp_code as string) || '',
      sheetName: (route?.query?.sheet as string) || '',
    })
  }

  // R13.3 / R7.3: 优先使用 ACNR 返回的 jump_route（不自行拼路由）
  if (acnrResult.value?.found && acnrResult.value.jump_route) {
    const jumpRoute = acnrResult.value.jump_route
    // jump_route 模板中的 {wp_id} 已由后端 resolve_instance 填充
    // 如果包含 {project_id} 占位符则替换
    const finalRoute = jumpRoute.replace('{project_id}', pid)
    router.push(finalRoute)
    return
  }

  // Fallback: ACNR 未返回 jump_route 时（如 validate=false 或 ACNR 不可用），
  // 使用 ACNR resolveInstance 获取 wp_id 跳转（仍经 ACNR 统一出口）
  switch (ns) {
    case 'wp':
      // Layer 3: cross-workpaper jump → ACNR resolve_instance
      resolveAndNavigateToWp(target, pid)
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
    parsed.value = parseIndexRef(refValue.value)
  }
  if (parsed.value) {
    resolveRef()
  }
}

onMounted(init)

// Re-parse and re-validate when value changes
watch(refValue, () => {
  resolveStatus.value = 'pending'
  trimReason.value = ''
  acnrResult.value = null
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

/* GT 紫令牌覆盖 Element 默认蓝（铁律：禁用 #409eff fallback）。
   el-tag--primary 默认渲染蓝色，索引跳转 chip 统一用 GT 核心紫。
   用 GT token 变量，自动适配暗色模式。 */
.gt-index-chip.el-tag--primary {
  --el-tag-bg-color: var(--gt-color-primary-bg);
  --el-tag-border-color: var(--gt-color-border-purple-light);
  --el-tag-text-color: var(--gt-color-primary);
  background-color: var(--gt-color-primary-bg);
  border-color: var(--gt-color-border-purple-light);
  color: var(--gt-color-primary);
}

.gt-index-chip.el-tag--primary.is-light {
  background-color: var(--gt-color-primary-bg);
  border-color: var(--gt-color-border-purple-light);
  color: var(--gt-color-primary);
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
