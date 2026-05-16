<template>
  <div class="gate-block-panel" v-if="state !== 'normal' || hitRules.length > 0">
    <!-- 评估中 -->
    <div v-if="state === 'evaluating'" class="gate-evaluating">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>门禁评估中...</span>
    </div>

    <!-- 阻断态 -->
    <el-alert
      v-else-if="state === 'blocked'"
      type="error"
      :closable="false"
      show-icon
      class="gate-blocked-alert"
    >
      <template #title>
        <span>提交被阻断（{{ blockingCount }} 项需修复）</span>
      </template>
      <template #default>
        <div class="gate-rules-list">
          <div
            v-for="(group, idx) in groupedRules"
            :key="idx"
            class="gate-rule-item"
            :class="group.severity"
          >
            <div class="rule-header" @click="handleJump(group)">
              <el-tag :type="severityTagType(group.severity)" size="small">
                {{ group.ruleCode }}
              </el-tag>
              <span class="rule-message">{{ group.message }}</span>
              <el-badge v-if="group.count > 1" :value="group.count" class="rule-count" />
            </div>
            <div class="rule-action" v-if="group.suggestedAction">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ group.suggestedAction }}</span>
            </div>
          </div>
        </div>
        <div class="gate-trace" v-if="traceId">
          <span class="trace-label">trace_id:</span>
          <el-button type="primary" link size="small" @click="copyTrace">
            {{ traceId }}
            <el-icon><CopyDocument /></el-icon>
          </el-button>
        </div>
      </template>
    </el-alert>

    <!-- 警告态 -->
    <el-alert
      v-else-if="state === 'warned'"
      type="warning"
      :closable="false"
      show-icon
      class="gate-warned-alert"
    >
      <template #title>
        <span>存在 {{ warningCount }} 项警告（可确认后继续）</span>
      </template>
      <template #default>
        <div class="gate-rules-list">
          <div
            v-for="(group, idx) in groupedRules"
            :key="idx"
            class="gate-rule-item warning"
          >
            <el-tag type="warning" size="small">{{ group.ruleCode }}</el-tag>
            <span class="rule-message">{{ group.message }}</span>
          </div>
        </div>
      </template>
    </el-alert>

    <!-- 错误态 -->
    <el-alert
      v-else-if="state === 'error'"
      type="info"
      :closable="false"
      show-icon
    >
      <template #title>门禁评估异常</template>
      <template #default>
        <span>系统繁忙，请稍后重试。</span>
        <span v-if="traceId" class="gate-trace">trace_id: {{ traceId }}</span>
      </template>
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, InfoFilled, CopyDocument } from '@element-plus/icons-vue'

interface GateRuleHit {
  rule_code: string
  error_code: string
  severity: string
  message: string
  location: Record<string, any>
  suggested_action: string
}

interface GroupedRule {
  ruleCode: string
  severity: string
  message: string
  suggestedAction: string
  count: number
  location: Record<string, any>
}

const props = defineProps<{
  state: 'normal' | 'evaluating' | 'blocked' | 'warned' | 'error'
  hitRules: GateRuleHit[]
  traceId: string
}>()

const emit = defineEmits<{
  (e: 'jump', location: Record<string, any>): void
}>()

// 按 rule_code 聚合，同规则多次触发显示计数
const groupedRules = computed<GroupedRule[]>(() => {
  const map = new Map<string, GroupedRule>()
  // 排序：blocking 优先（可自动修复 → 需人工处理）
  const sorted = [...props.hitRules].sort((a, b) => {
    const order: Record<string, number> = { blocking: 0, warning: 1, info: 2 }
    return (order[a.severity] ?? 9) - (order[b.severity] ?? 9)
  })
  for (const rule of sorted) {
    const existing = map.get(rule.rule_code)
    if (existing) {
      existing.count++
    } else {
      map.set(rule.rule_code, {
        ruleCode: rule.rule_code,
        severity: rule.severity,
        message: rule.message,
        suggestedAction: rule.suggested_action,
        count: 1,
        location: rule.location,
      })
    }
  }
  return Array.from(map.values())
})

const blockingCount = computed(() =>
  props.hitRules.filter(r => r.severity === 'blocking').length
)

const warningCount = computed(() =>
  props.hitRules.filter(r => r.severity === 'warning').length
)

function severityTagType(severity: string) {
  if (severity === 'blocking') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'info'
}

function handleJump(group: GroupedRule) {
  if (group.location) {
    emit('jump', group.location)
  }
}

async function copyTrace() {
  try {
    await navigator.clipboard.writeText(props.traceId)
    ElMessage.success('trace_id 已复制')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}
</script>

<style scoped>
.gate-block-panel {
  margin-bottom: 12px;
}
.gate-evaluating {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  color: var(--gt-color-text-secondary, #666);
}
.gate-rules-list {
  margin-top: 8px;
}
.gate-rule-item {
  padding: 6px 0;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  cursor: pointer;
}
.gate-rule-item:hover {
  background: rgba(0,0,0,0.02);
}
.rule-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.rule-message {
  flex: 1;
  font-size: var(--gt-font-size-sm);
}
.rule-action {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  padding-left: 60px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary, #999);
}
.gate-trace {
  margin-top: 8px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary, #999);
}
.trace-label {
  margin-right: 4px;
}
</style>
