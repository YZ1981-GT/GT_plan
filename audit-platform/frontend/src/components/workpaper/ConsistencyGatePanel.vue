<script setup lang="ts">
/**
 * ConsistencyGatePanel — D4 营业收入勾稽 4 条 VR 结果展示
 *
 * D spec F7 Task 2.17: 显示 VR-D4-01~04 校验结果
 * - blocking 规则失败显示红色 ❌
 * - warning 规则触发显示黄色 ⚠️
 * - 通过显示绿色 ✅
 */
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { chainWorkflow } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { checkReasonOf, checkStatusLabel, checkStatusOf, type GateCheckStatus } from '@/utils/consistencyCheckStatus'

export interface D4ValidationResult {
  rule_id: string
  description: string
  passed: boolean
  /** 五态；接口没给出时按「检查异常」显示（不按 passed 推断成通过） */
  status?: GateCheckStatus
  /** 非通过原因（未执行 / 不适用 / 异常时由后端给出） */
  reason?: string
  severity: 'blocking' | 'warning'
  details: string
  check_name: string
}

function statusOf(item: D4ValidationResult): GateCheckStatus {
  return checkStatusOf(item)
}

const props = defineProps<{
  projectId: string
  year: number
  wpCode?: string
}>()

const loading = ref(false)
const results = ref<D4ValidationResult[]>([])
const lastCheckedAt = ref<string | null>(null)

// 只有「失败」才是阻断级差异；未执行 / 不适用 / 异常各自显示，不算通过也不算差异
const hasBlockingFailures = computed(() =>
  results.value.some(r => statusOf(r) === 'failed' && r.severity === 'blocking')
)

const summaryText = computed(() => {
  if (results.value.length === 0) return '未执行'
  const count = (s: GateCheckStatus) => results.value.filter(r => statusOf(r) === s).length
  const passed = count('passed')
  const total = results.value.length
  if (passed === total) return `${total}/${total} 通过`
  const parts: string[] = [`${passed} 通过`]
  if (count('failed') > 0) parts.push(`${count('failed')} 失败`)
  if (count('not_executed') > 0) parts.push(`${count('not_executed')} 未执行`)
  if (count('not_applicable') > 0) parts.push(`${count('not_applicable')} 不适用`)
  if (count('error') > 0) parts.push(`${count('error')} 检查异常`)
  return parts.join('、')
})

const overallStatus = computed(() => {
  if (results.value.length === 0) return 'pending'
  if (hasBlockingFailures.value) return 'blocked'
  if (results.value.some(r => statusOf(r) !== 'passed' && statusOf(r) !== 'not_applicable')) return 'warning'
  return 'pass'
})

// D4 VR 规则定义（前端静态，与 d_cycle_validation_rules.json 对应）
const D4_VR_RULES = [
  { rule_id: 'VR-D4-01', description: '营业收入合计 = 主营业务收入 + 其他业务收入', severity: 'blocking' as const },
  { rule_id: 'VR-D4-02', description: '应收账款增长率 vs 营业收入增长率合理性', severity: 'warning' as const },
  { rule_id: 'VR-D4-03', description: '毛利率波动 < 5%', severity: 'warning' as const },
  { rule_id: 'VR-D4-04', description: '合同负债期末 vs D7-1 审定数一致', severity: 'blocking' as const },
]

function getStatusIcon(item: D4ValidationResult): string {
  const st = statusOf(item)
  if (st === 'passed') return '✅'
  if (st === 'failed') return item.severity === 'blocking' ? '❌' : '⚠️'
  if (st === 'not_executed') return '⏭️'
  if (st === 'not_applicable') return '➖'
  return '⚠️'
}

function getStatusClass(item: D4ValidationResult): string {
  const st = statusOf(item)
  if (st === 'passed') return 'status-pass'
  if (st === 'failed') return item.severity === 'blocking' ? 'status-blocking' : 'status-warning'
  if (st === 'not_executed') return 'status-not-executed'
  if (st === 'not_applicable') return 'status-not-applicable'
  return 'status-warning'
}

/** 五态标签（需求 16.5：未执行 / 不适用 / 检查异常各有标签，不显示「通过」） */
function getStatusLabel(item: D4ValidationResult): string {
  return checkStatusLabel(item)
}

/** 非通过项显示的原因：后端 reason 优先，没有再用 details；状态缺失时写明接口没给状态 */
function getReasonText(item: D4ValidationResult): string {
  return checkReasonOf(item)
}

function getSeverityLabel(severity: string): string {
  return severity === 'blocking' ? '阻断' : '警告'
}

async function fetchD4Results() {
  // 仅 D4 底稿时显示，或者不限制 wpCode 时也显示
  if (props.wpCode && props.wpCode !== 'D4') {
    results.value = []
    return
  }

  loading.value = true
  try {
    // 展示端点 = 一致性检查（五态，需求 16.5）；原先请求的 /consistency-gate/check 后端不存在（恒 404）
    const data = await api.get(chainWorkflow.consistencyCheck(props.projectId), {
      params: { year: props.year },
    })
    // 从一致性检查结果中提取 D4 勾稽相关的 checks
    const allChecks: Array<{
      check_name: string; passed: boolean; status?: GateCheckStatus; reason?: string
      severity: string; details: unknown
    }> = data?.checks || []
    const d4Checks = allChecks.filter(c => (c.check_name || '').startsWith('D4勾稽'))

    if (d4Checks.length > 0) {
      results.value = d4Checks.map((c, idx) => ({
        rule_id: D4_VR_RULES[idx]?.rule_id || `VR-D4-0${idx + 1}`,
        description: D4_VR_RULES[idx]?.description || c.check_name,
        passed: c.passed,
        status: c.status,
        reason: c.reason || '',
        severity: (c.severity as 'blocking' | 'warning') || D4_VR_RULES[idx]?.severity || 'warning',
        details: typeof c.details === 'string' ? c.details : '',
        check_name: c.check_name,
      }))
    } else {
      // 接口没有返回 D4 勾稽结果：显示「未执行」并写明原因，不自补「通过」（需求 16.5）
      results.value = D4_VR_RULES.map(rule => ({
        rule_id: rule.rule_id,
        description: rule.description,
        passed: false,
        status: 'not_executed' as const,
        reason: '一致性检查未返回该项结果，未执行',
        severity: rule.severity,
        details: '',
        check_name: '',
      }))
    }
    lastCheckedAt.value = new Date().toLocaleString('zh-CN')
  } catch (e: unknown) {
    handleApiError(e, 'D4 勾稽校验')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchD4Results()
})

watch(() => [props.projectId, props.year], () => {
  fetchD4Results()
})
</script>

<template>
  <div class="gt-d4-gate-panel">
    <!-- 标题栏 -->
    <div class="panel-header">
      <div class="header-left">
        <span class="panel-title">D4 营业收入勾稽</span>
        <el-tag
          :type="overallStatus === 'pass' ? 'success' : overallStatus === 'blocked' ? 'danger' : overallStatus === 'warning' ? 'warning' : 'info'"
          size="small"
          effect="dark"
        >
          {{ summaryText }}
        </el-tag>
      </div>
      <el-button size="small" :loading="loading" @click="fetchD4Results">
        刷新
      </el-button>
    </div>

    <!-- 阻断提示 -->
    <el-alert
      v-if="hasBlockingFailures"
      type="error"
      :closable="false"
      show-icon
      class="blocking-alert"
    >
      <template #title>存在阻断级差异，无法签字确认</template>
    </el-alert>

    <!-- 规则列表 -->
    <div v-loading="loading" class="rules-list">
      <div
        v-for="item in results"
        :key="item.rule_id"
        class="rule-item"
        :class="getStatusClass(item)"
      >
        <div class="rule-row">
          <span class="rule-icon">{{ getStatusIcon(item) }}</span>
          <div class="rule-content">
            <div class="rule-header">
              <span class="rule-id">{{ item.rule_id }}</span>
              <el-tag
                :type="item.severity === 'blocking' ? 'danger' : 'warning'"
                size="small"
                effect="plain"
              >
                {{ getSeverityLabel(item.severity) }}
              </el-tag>
              <span class="rule-status" data-testid="gate-status-label">{{ getStatusLabel(item) }}</span>
            </div>
            <div class="rule-desc">{{ item.description }}</div>
            <div v-if="getReasonText(item)" class="rule-details" data-testid="gate-status-reason">
              {{ getReasonText(item) }}
            </div>
          </div>
        </div>
      </div>

      <el-empty
        v-if="results.length === 0 && !loading"
        description="暂无 D4 勾稽数据"
        :image-size="48"
      />
    </div>

    <!-- 底部信息 -->
    <div v-if="lastCheckedAt" class="panel-footer">
      <span class="footer-text">最后检查: {{ lastCheckedAt }}</span>
    </div>
  </div>
</template>

<style scoped>
.gt-d4-gate-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}

.blocking-alert {
  margin: 0;
}

.rules-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-item {
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  transition: border-color 0.2s, background-color 0.2s;
}

.rule-item.status-pass {
  border-left: 3px solid var(--el-color-success);
}

.rule-item.status-blocking {
  border-left: 3px solid var(--el-color-danger);
  background: var(--el-color-danger-light-9, #fef0f0);
}

.rule-item.status-warning {
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9, #fdf6ec);
}

.rule-item.status-not-executed {
  border-left: 3px solid var(--el-color-info);
  background: var(--el-color-info-light-9, #f4f4f5);
}

.rule-item.status-not-applicable {
  border-left: 3px solid #c0c4cc;
  background: #fafafa;
  opacity: 0.75;
}

.rule-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.rule-icon {
  font-size: 16px;
  line-height: 1.4;
  flex-shrink: 0;
}

.rule-content {
  flex: 1;
  min-width: 0;
}

.rule-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.rule-id {
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text-secondary);
  font-family: 'Arial Narrow', Arial, sans-serif;
}

.rule-status {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}

.rule-desc {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
  line-height: 1.4;
}

.rule-details {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  margin-top: 4px;
  padding: 4px 8px;
  background: var(--gt-bg-subtle, #f5f7fa);
  border-radius: 4px;
  word-break: break-all;
}

.panel-footer {
  padding-top: 8px;
  border-top: 1px solid var(--gt-color-border-lighter);
}

.footer-text {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-placeholder);
}
</style>
