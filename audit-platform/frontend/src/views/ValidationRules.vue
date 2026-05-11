<template>
  <div class="validation-rules-page">
    <div class="page-header">
      <h2>数据校验规则说明</h2>
      <p class="page-desc">以下规则用于账表导入后的数据质量校验，分为 L1（基础格式）、L2（逻辑一致性）、L3（跨表核对）三个层级。</p>
    </div>

    <el-skeleton :loading="loading" :rows="8" animated>
      <template #default>
        <el-collapse v-model="expandedLevels">
          <el-collapse-item
            v-for="level in levels"
            :key="level.key"
            :name="level.key"
          >
            <template #title>
              <div class="level-title">
                <el-tag :type="level.tagType" size="small" effect="dark">{{ level.label }}</el-tag>
                <span>{{ level.description }}</span>
                <el-badge :value="getRulesByLevel(level.key).length" type="info" />
              </div>
            </template>

            <el-table
              :data="getRulesByLevel(level.key)"
              stripe
              size="small"
              style="width: 100%"
            >
              <el-table-column prop="code" label="规则编码" width="180" />
              <el-table-column prop="title_cn" label="规则名称" min-width="200" />
              <el-table-column prop="formula_cn" label="校验公式" min-width="250">
                <template #default="{ row }">
                  <code class="formula-text">{{ row.formula_cn || '-' }}</code>
                </template>
              </el-table-column>
              <el-table-column prop="tolerance_cn" label="容差" width="160">
                <template #default="{ row }">
                  <span>{{ row.tolerance_cn || '无' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="scope_cn" label="适用范围" width="120" />
              <el-table-column prop="why_cn" label="校验目的" min-width="200" />
              <el-table-column label="可强制跳过" width="100" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.can_force" type="warning" size="small">可跳过</el-tag>
                  <el-tag v-else type="danger" size="small" effect="plain">不可跳过</el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </template>
    </el-skeleton>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

// ─── Types ──────────────────────────────────────────────────────────────────

interface ValidationRule {
  code: string
  level: string
  title_cn: string
  formula_cn?: string
  tolerance_cn?: string
  scope_cn?: string
  why_cn?: string
  can_force: boolean
}

// ─── State ──────────────────────────────────────────────────────────────────

const rules = ref<ValidationRule[]>([])
const loading = ref(false)
const expandedLevels = ref<string[]>(['L1', 'L2', 'L3'])

const levels = [
  { key: 'L1', label: 'L1', tagType: 'info' as const, description: '基础格式校验（字段类型、必填、空值）' },
  { key: 'L2', label: 'L2', tagType: 'warning' as const, description: '逻辑一致性校验（借贷平衡、年度范围）' },
  { key: 'L3', label: 'L3', tagType: 'danger' as const, description: '跨表核对校验（余额=序时累计）' },
]

// ─── Computed ───────────────────────────────────────────────────────────────

function getRulesByLevel(level: string): ValidationRule[] {
  return rules.value.filter(r => r.level === level)
}

// ─── Fetch ──────────────────────────────────────────────────────────────────

async function fetchRules() {
  loading.value = true
  try {
    const res = await api.get<ValidationRule[]>('/api/ledger-import/validation-rules')
    rules.value = Array.isArray(res) ? res : []
  } catch (e) {
    console.error('获取校验规则失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchRules()
})
</script>

<style scoped>
.validation-rules-page {
  padding: 20px 24px;
  max-width: 1400px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0 0 8px;
  font-size: 18px;
}

.page-desc {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.level-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
}

.formula-text {
  font-size: 12px;
  background: var(--el-fill-color-lighter);
  padding: 2px 6px;
  border-radius: 3px;
  word-break: break-all;
}
</style>
