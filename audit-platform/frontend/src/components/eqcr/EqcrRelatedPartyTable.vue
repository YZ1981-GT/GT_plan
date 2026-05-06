<template>
  <el-card shadow="never" class="eqcr-tab__section">
    <template #header>
      <div class="eqcr-tab__section-header">
        <div>
          <span class="eqcr-tab__section-title">关联方注册</span>
          <el-tag size="small" type="info" effect="plain">
            共 {{ registries.length }} 家
          </el-tag>
        </div>
        <el-button
          v-if="canWrite"
          type="primary"
          size="small"
          @click="$emit('add')"
        >
          + 新增关联方
        </el-button>
      </div>
    </template>

    <el-empty
      v-if="registries.length === 0"
      description="该项目尚未登记关联方"
      :image-size="60"
    />

    <el-table
      v-else
      :data="registries"
      size="small"
      border
      stripe
      style="width: 100%"
    >
      <el-table-column prop="name" label="关联方名称" min-width="220" />
      <el-table-column prop="relation_type" label="关系类型" width="160">
        <template #default="{ row }">
          {{ RELATION_TYPE_LABELS[row.relation_type] || row.relation_type }}
        </template>
      </el-table-column>
      <el-table-column label="同一控制" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.is_controlled_by_same_party" type="warning" size="small" effect="light">是</el-tag>
          <span v-else class="eqcr-muted">否</span>
        </template>
      </el-table-column>
      <el-table-column label="登记时间" width="180">
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column v-if="canWrite" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="$emit('edit', row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="$emit('delete', row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import type { EqcrRelatedPartyRegistry } from '@/services/eqcrService'

defineProps<{
  registries: EqcrRelatedPartyRegistry[]
  canWrite: boolean
}>()

defineEmits<{
  add: []
  edit: [row: EqcrRelatedPartyRegistry]
  delete: [row: EqcrRelatedPartyRegistry]
}>()

const RELATION_TYPE_LABELS: Record<string, string> = {
  parent: '母公司',
  subsidiary: '子公司',
  associate: '联营企业',
  joint_venture: '合营企业',
  key_management: '关键管理人员',
  family_member: '家庭成员',
  other: '其他',
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString('zh-CN', { hour12: false }) } catch { return iso }
}
</script>

<style scoped>
.eqcr-tab__section { border-radius: var(--gt-radius-md, 6px); }
.eqcr-tab__section-header { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.eqcr-tab__section-title { font-weight: 600; color: var(--gt-color-text, #303133); margin-right: 10px; }
.eqcr-muted { color: var(--gt-color-text-tertiary, #909399); }
</style>
