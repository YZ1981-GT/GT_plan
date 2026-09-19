<template>
  <el-tooltip
    placement="top"
    :show-after="120"
    :hide-after="0"
    popper-class="gt-formula-source-tooltip__popper"
    @before-show="handleBeforeShow"
  >
    <template #content>
      <div class="gt-formula-source">
        <div class="gt-formula-source__row">
          <span class="gt-formula-source__label">公式表达式</span>
          <span class="gt-formula-source__value gt-formula-source__expr">{{ displayExpression }}</span>
        </div>
        <div class="gt-formula-source__row">
          <span class="gt-formula-source__label">来源地址</span>
          <span class="gt-formula-source__value">
            <el-icon v-if="resolving" class="gt-formula-source__spin"><Loading /></el-icon>
            <span v-else>{{ displaySource }}</span>
          </span>
        </div>
        <div class="gt-formula-source__row">
          <span class="gt-formula-source__label">最近计算</span>
          <span
            class="gt-formula-source__value"
            :class="{ 'gt-formula-source__pending': !hasComputed }"
          >{{ displayComputedAt }}</span>
        </div>
      </div>
    </template>

    <span class="formula-cell" :class="{ 'formula-cell--plain': plain }">
      <slot />
    </span>
  </el-tooltip>
</template>

<script setup lang="ts">
/**
 * GtFormulaSourceTooltip — 统一公式来源悬停提示（底稿 / 报表 / 附注三处通用）
 *
 * 视觉：虚线下划线 + cursor:help（Req 10.1）
 * 悬停内容：公式表达式 + 来源地址 + 最近计算时间（Req 10.2）
 * 来源地址：使用 ACNR full_resolve 返回的 canonical semantic_label（Req 10.5），
 *          绝不在前端拼接 wp_code+sheet+cell 坐标字符串。
 * 未计算过（无 last_computed_at）：显示"尚未计算"占位（Req 10.4）
 * 统一挂载：底稿表格 / 报表 / 附注（Req 10.3）
 *
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
 */
import { computed, ref } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { fmtDateTime } from '@/utils/formatters'
import { useAcnr } from '@/services/acnr/useAcnr'

const props = withDefaults(
  defineProps<{
    /** 公式表达式（如 "= 期初 + 增加 - 减少" 或 "SUM(...)"），无则显示占位 */
    expression?: string | null
    /** ACNR addr_id，用于 full_resolve 取 canonical semantic_label（来源地址） */
    addrId?: string | null
    /** ACNR formula_ref，addr_id 缺失时的备选解析入口 */
    formulaRef?: string | null
    /** 已由父级解析好的来源地址（semantic_label），提供则跳过前端 resolve */
    sourceLabel?: string | null
    /** 最近计算时间（后端 naive UTC 时间戳或 ISO 串）；空 → "尚未计算" */
    lastComputedAt?: string | Date | null
    /** true 时不显示虚线下划线（仅悬停提示），用于已有样式的容器 */
    plain?: boolean
  }>(),
  {
    expression: null,
    addrId: null,
    formulaRef: null,
    sourceLabel: null,
    lastComputedAt: null,
    plain: false,
  },
)

const { resolveAddr, resolveFormula } = useAcnr()

const resolving = ref(false)
const resolved = ref(false)
/** 前端 resolve 得到的 canonical semantic_label */
const resolvedLabel = ref<string | null>(null)

const displayExpression = computed(() => {
  const e = (props.expression ?? '').trim()
  return e || '（未定义表达式）'
})

const hasComputed = computed(() => !!props.lastComputedAt)

/**
 * 来源地址显示：优先父级传入的 sourceLabel（已 resolve），
 * 否则用前端 resolve 得到的 canonical semantic_label。
 * 两者皆无 → 占位（不拼接坐标）。
 */
const displaySource = computed(() => {
  const label = (props.sourceLabel ?? resolvedLabel.value ?? '').trim()
  return label || '（未知来源）'
})

const displayComputedAt = computed(() => {
  if (!props.lastComputedAt) return '尚未计算'
  return fmtDateTime(normalizeTimestamp(props.lastComputedAt))
})

/**
 * 后端时间戳多为 naive UTC（func.now()/utcnow 无时区标记），
 * 浏览器会误当本地时间。补 'Z' 标记为 UTC，再交统一格式化器转本地时区。
 */
function normalizeTimestamp(v: string | Date): string | Date {
  if (v instanceof Date) return v
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(v)
  return hasTz ? v : `${v}Z`
}

/**
 * 悬停展开前懒解析来源地址（Req 10.5）。
 * 仅在父级未提供 sourceLabel 且给了 addrId/formulaRef 时触发，
 * 避免表格大量单元一次性发起 resolve 请求。
 */
async function handleBeforeShow() {
  if (resolved.value || resolving.value) return
  if (props.sourceLabel) return
  if (!props.addrId && !props.formulaRef) return

  resolving.value = true
  try {
    const result = props.addrId
      ? await resolveAddr(props.addrId)
      : await resolveFormula(props.formulaRef as string)
    if (result.found && result.semantic_label) {
      resolvedLabel.value = result.semantic_label
    }
    resolved.value = true
  } finally {
    resolving.value = false
  }
}
</script>

<style scoped>
.formula-cell {
  border-bottom: 1px dashed #409eff;
  cursor: help;
}
.formula-cell--plain {
  border-bottom: none;
  cursor: help;
}
.gt-formula-source {
  font-size: 12px;
  line-height: 1.7;
  max-width: 320px;
}
.gt-formula-source__row {
  display: flex;
  gap: 8px;
}
.gt-formula-source__label {
  flex: 0 0 60px;
  color: #a3c8ff;
  white-space: nowrap;
}
.gt-formula-source__value {
  flex: 1;
  word-break: break-all;
}
.gt-formula-source__expr {
  font-family: 'Consolas', 'Courier New', monospace;
}
.gt-formula-source__pending {
  color: #e6a23c;
  font-style: italic;
}
.gt-formula-source__spin {
  animation: gt-formula-spin 1s linear infinite;
}
@keyframes gt-formula-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
