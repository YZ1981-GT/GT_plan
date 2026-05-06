<template>
  <div class="qc-rule-list">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner gt-page-banner--teal">
      <div class="gt-banner-content">
        <h2>📋 质控规则管理</h2>
        <span class="gt-banner-sub">
          共 {{ total }} 条规则，已启用 {{ enabledCount }} 条
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-button size="small" @click="loadRules" :loading="loading">刷新</el-button>
        <el-button size="small" type="primary" @click="handleCreate">+ 新建规则</el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select
        v-model="filters.severity"
        placeholder="严重级别"
        clearable
        size="default"
        style="width: 140px"
        @change="loadRules"
      >
        <el-option label="阻断 (blocking)" value="blocking" />
        <el-option label="警告 (warning)" value="warning" />
        <el-option label="提示 (info)" value="info" />
      </el-select>

      <el-select
        v-model="filters.scope"
        placeholder="适用范围"
        clearable
        size="default"
        style="width: 160px"
        @change="loadRules"
      >
        <el-option label="底稿 (workpaper)" value="workpaper" />
        <el-option label="项目 (project)" value="project" />
        <el-option label="合并 (consolidation)" value="consolidation" />
        <el-option label="审计日志 (audit_log)" value="audit_log" />
      </el-select>

      <el-switch
        v-model="filters.enabledOnly"
        active-text="仅启用"
        inactive-text=""
        size="default"
        @change="loadRules"
      />
    </div>

    <!-- 规则表格 -->
    <el-table
      :data="rules"
      v-loading="loading"
      stripe
      style="width: 100%"
      row-key="id"
    >
      <el-table-column label="规则编号" prop="rule_code" width="130" fixed>
        <template #default="{ row }">
          <span class="rule-code">{{ row.rule_code }}</span>
        </template>
      </el-table-column>

      <el-table-column label="标题" prop="title" min-width="200" show-overflow-tooltip />

      <el-table-column label="严重级别" prop="severity" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity)" size="small" effect="dark">
            {{ severityLabel(row.severity) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="适用范围" prop="scope" width="120" align="center">
        <template #default="{ row }">
          <span>{{ scopeLabel(row.scope) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="启用" prop="enabled" width="80" align="center">
        <template #default="{ row }">
          <el-switch
            :model-value="row.enabled"
            size="small"
            @change="(val: string | number | boolean) => handleToggle(row, !!val)"
          />
        </template>
      </el-table-column>

      <el-table-column label="准则引用" min-width="200">
        <template #default="{ row }">
          <template v-if="row.standard_ref && row.standard_ref.length">
            <el-tag
              v-for="ref in row.standard_ref"
              :key="ref.code + (ref.section || '')"
              size="small"
              type="info"
              class="standard-tag"
              :title="ref.name || ''"
            >
              {{ ref.code }}{{ ref.section ? ' §' + ref.section : '' }}
            </el-tag>
          </template>
          <span v-else class="no-ref">—</span>
        </template>
      </el-table-column>

      <el-table-column label="版本" prop="version" width="70" align="center" />

      <el-table-column label="操作" width="140" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="handleEdit(row)">
            编辑
          </el-button>
          <el-button link type="danger" size="small" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrap" v-if="total > pageSize">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadRules"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getQcRules,
  deleteQcRule,
  toggleQcRule,
  type QcRuleDefinition,
} from '@/services/qcRuleApi'

const router = useRouter()

// ─── State ──────────────────────────────────────────────────────────────────

const rules = ref<QcRuleDefinition[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20

const filters = reactive({
  severity: '' as string,
  scope: '' as string,
  enabledOnly: false,
})

const enabledCount = computed(() => rules.value.filter((r) => r.enabled).length)

// ─── Helpers ────────────────────────────────────────────────────────────────

function severityTagType(severity: string): 'success' | 'warning' | 'danger' | 'info' {
  switch (severity) {
    case 'blocking': return 'danger'
    case 'warning': return 'warning'
    case 'info': return 'info'
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
  switch (scope) {
    case 'workpaper': return '底稿'
    case 'project': return '项目'
    case 'consolidation': return '合并'
    case 'audit_log': return '审计日志'
    default: return scope
  }
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadRules() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: currentPage.value,
      page_size: pageSize,
    }
    if (filters.severity) params.severity = filters.severity
    if (filters.scope) params.scope = filters.scope
    if (filters.enabledOnly) params.enabled = true

    const res = await getQcRules(params)
    rules.value = res.items
    total.value = res.total
  } catch (e: any) {
    ElMessage.error('加载规则列表失败')
  } finally {
    loading.value = false
  }
}

// ─── Actions ────────────────────────────────────────────────────────────────

function handleCreate() {
  router.push('/qc/rules/new')
}

function handleEdit(row: QcRuleDefinition) {
  router.push(`/qc/rules/${row.id}/edit`)
}

async function handleToggle(row: QcRuleDefinition, val: boolean) {
  try {
    await toggleQcRule(row.id, val)
    row.enabled = val
    ElMessage.success(val ? '规则已启用' : '规则已停用')
  } catch {
    ElMessage.error('操作失败')
  }
}

async function handleDelete(row: QcRuleDefinition) {
  try {
    await ElMessageBox.confirm(
      `确定删除规则「${row.rule_code} - ${row.title}」？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await deleteQcRule(row.id)
    ElMessage.success('规则已删除')
    await loadRules()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
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

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}

.rule-code {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  color: #409eff;
}

.standard-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.no-ref {
  color: #c0c4cc;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
}
</style>
