<template>
  <div class="deliverable-toolbar">
    <div class="deliverable-toolbar__filters">
      <el-select v-model="docType" placeholder="文档类型" clearable style="width: 160px" @change="emit('refresh')">
        <el-option label="审计报告正文" value="audit_report" />
        <el-option label="财务报表（审定）" value="financial_report" />
        <el-option label="财务报表（未审）" value="financial_report_unadjusted" />
        <el-option label="附注" value="disclosure_notes" />
        <el-option label="全套包" value="full_package" />
      </el-select>
      <el-select v-model="status" placeholder="状态" clearable style="width: 140px" @change="emit('refresh')">
        <el-option label="草稿" value="draft" />
        <el-option label="编辑中" value="editing" />
        <el-option label="已确认" value="confirmed" />
        <el-option label="已签章" value="signed" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-input
        v-model="keyword"
        placeholder="搜索文件名或导出者"
        clearable
        style="width: 220px"
        @keyup.enter="emit('refresh')"
        @clear="emit('refresh')"
      />
      <el-button @click="emit('refresh')">刷新</el-button>
    </div>
    <div class="deliverable-toolbar__actions">
      <el-button type="primary" :loading="generating" @click="emit('generate-reports')">生成报表</el-button>
      <el-button type="primary" :loading="generating" @click="emit('generate-notes')">生成附注</el-button>
      <el-button type="primary" :loading="generating" @click="emit('generate-report')">生成报告</el-button>
      <el-button type="primary" :loading="fullGenerating" @click="emit('generate-full')">一键生成全套</el-button>
      <el-button :loading="packaging" @click="emit('package-download')">打包下载</el-button>
      <el-button @click="emit('archive')">项目归档</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
const docType = defineModel<string>('docType', { default: '' })
const status = defineModel<string>('status', { default: '' })
const keyword = defineModel<string>('keyword', { default: '' })

defineProps<{ generating?: boolean; packaging?: boolean; fullGenerating?: boolean }>()
const emit = defineEmits<{
  refresh: []
  'generate-report': []
  'generate-reports': []
  'generate-notes': []
  'generate-full': []
  'package-download': []
  archive: []
}>()
</script>

<style scoped>
.deliverable-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 16px;
}
.deliverable-toolbar__filters,
.deliverable-toolbar__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
