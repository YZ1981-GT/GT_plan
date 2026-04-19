<template>
  <div class="validation-list">
    <el-table :data="findings" stripe size="small" max-height="500">
      <el-table-column prop="severity" label="严重度" width="80">
        <template #default="{ row }">
          <el-tag :type="severityType(row.severity)" size="small">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="check_type" label="类型" width="160" />
      <el-table-column prop="message" label="描述" min-width="300" show-overflow-tooltip />
      <el-table-column prop="fix_suggestion" label="建议" width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button v-if="row.fix_suggestion" size="small" text type="primary" @click="$emit('fix', [row.id])">修复</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!findings.length" description="暂无校验结果" />
  </div>
</template>

<script setup lang="ts">
defineProps<{ findings: any[] }>()
defineEmits<{ fix: [ids: string[]] }>()

function severityType(s: string) {
  return s === 'high' ? 'danger' : s === 'medium' ? 'warning' : s === 'low' ? 'info' : ''
}
</script>
