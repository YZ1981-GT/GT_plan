<template>
  <div class="qc-rule-list">
    <GtPageHeader title="质控规则" :show-back="false">
      <template #actions>
        <el-button size="small" @click="loadRules" :loading="loading">刷新</el-button>
      </template>
    </GtPageHeader>

    <!-- 规则表格 -->
    <el-table
      :data="rules"
      v-loading="loading"
      stripe
      style="width: 100%"
      row-key="id"
    >
      <el-table-column label="规则编号" prop="rule_code" width="120">
        <template #default="{ row }">
          <span class="rule-code">{{ row.rule_code }}</span>
        </template>
      </el-table-column>

      <el-table-column label="标题" prop="title" min-width="240" />

      <el-table-column label="严重级别" prop="severity" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity)" size="small" effect="dark">
            {{ severityLabel(row.severity) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="适用范围" prop="scope" width="160" align="center">
        <template #default="{ row }">
          <span>{{ scopeLabel(row.scope) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="准则引用" prop="standard_ref" min-width="220">
        <template #default="{ row }">
          <span v-if="row.standard_ref && row.standard_ref.length">
            {{ row.standard_ref.join(', ') }}
          </span>
          <span v-else class="no-ref">—</span>
        </template>
      </el-table-column>

      <el-table-column label="启用状态" prop="enabled" width="120" align="center">
        <template #default="{ row }">
          <span :class="['enabled-dot', row.enabled ? 'enabled-dot--on' : 'enabled-dot--off']" />
          <span>{{ row.enabled ? '已启用' : '已停用' }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getQcRules } from '@/services/qcRuleApi'

// ─── Types ──────────────────────────────────────────────────────────────────

interface QcRule {
  id: string
  rule_code: string
  title: string
  severity: string
  scope: string
  standard_ref: string[] | null
  enabled: boolean
}

// ─── State ──────────────────────────────────────────────────────────────────

const rules = ref<QcRule[]>([])
const loading = ref(false)

const enabledCount = computed(() => rules.value.filter((r) => r.enabled).length)

// ─── Helpers ────────────────────────────────────────────────────────────────

function severityTagType(severity: string): 'danger' | 'warning' | 'info' {
  switch (severity) {
    case 'blocking': return 'danger'
    case 'warning': return 'warning'
    default: return 'info'
  }
}

function severityLabel(severity: string): string {
  switch (severity) {
    case 'blocking': return '阻断'
    case 'warning': return '警告'
    case 'info': return '提示'
    default: return severity
  }
}

function scopeLabel(scope: string): string {
  const map: Record<string, string> = {
    workpaper: '底稿',
    project: '项目',
    submit_review: '提交复核',
    sign_off: '签字',
    export_package: '导出归档',
    eqcr_approval: 'EQCR审批',
  }
  return map[scope] || scope
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadRules() {
  loading.value = true
  try {
    const data = await getQcRules()
    rules.value = (data.items || []) as any
  } catch {
    rules.value = []
  } finally {
    loading.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  loadRules()
})
</script>

<style scoped>
.qc-rule-list {
  padding: 0;
}

.rule-code {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  color: var(--gt-color-teal);
}

.no-ref {
  color: var(--gt-color-text-placeholder);
}

.enabled-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

.enabled-dot--on {
  background-color: var(--gt-color-success);
}

.enabled-dot--off {
  background-color: var(--gt-color-text-placeholder);
}
</style>
