<template>
  <!-- C.1.4: AI 建议侧栏 -->
  <el-drawer
    v-model="visible"
    title="AI 建议"
    direction="rtl"
    size="360px"
  >
    <div class="ai-panel">
      <el-button type="primary" size="small" :loading="loading" @click="fetchSuggestions" style="width: 100%; margin-bottom: 12px">
        🤖 分析当前章节
      </el-button>

      <!-- 动态行建议 -->
      <div v-if="dynamicRowSuggestions.length" class="ai-section">
        <h4>动态行建议</h4>
        <el-card v-for="(s, idx) in dynamicRowSuggestions" :key="idx" shadow="hover" style="margin-bottom: 8px">
          <div style="font-weight: 500">{{ s.region_name }}</div>
          <div style="color: #909399; font-size: 12px; margin-top: 4px">{{ s.rationale }}</div>
          <div style="margin-top: 6px">
            <el-tag size="small">置信度: {{ (s.confidence * 100).toFixed(0) }}%</el-tag>
            <el-tag size="small" type="info" style="margin-left: 4px">{{ s.aux_count }} 条辅助账</el-tag>
          </div>
        </el-card>
      </div>

      <!-- 一致性问题 -->
      <div v-if="consistencyIssues.length" class="ai-section">
        <h4>数据一致性</h4>
        <el-alert
          v-for="(issue, idx) in consistencyIssues"
          :key="idx"
          :type="issue.severity === 'high' ? 'error' : issue.severity === 'medium' ? 'warning' : 'info'"
          :title="`${issue.wp_code}: 差异 ${issue.diff.toLocaleString()}`"
          :description="`底稿值 ${issue.wp_value.toLocaleString()} vs 试算表 ${issue.tb_value.toLocaleString()}`"
          show-icon
          :closable="false"
          style="margin-bottom: 8px"
        />
      </div>

      <el-empty v-if="!loading && !dynamicRowSuggestions.length && !consistencyIssues.length" description="暂无建议，点击上方按钮分析" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
interface Props {
  modelValue: boolean
  projectId: string
  year: number
  currentSectionId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const dynamicRowSuggestions = ref<any[]>([])
const consistencyIssues = ref<any[]>([])

async function fetchSuggestions() {
  loading.value = true
  dynamicRowSuggestions.value = []
  consistencyIssues.value = []

  try {
    // Fetch dynamic row suggestions
    const suggestResp: any = await api.post(
      `/api/disclosure-notes/${props.currentSectionId}/ai/suggest-dynamic-rows`,
      { project_id: props.projectId, year: props.year }
    )
    dynamicRowSuggestions.value = suggestResp || []

    // Fetch consistency check
    const consistResp: any = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/ai/check-consistency`
    )
    consistencyIssues.value = (consistResp || []).filter(
      (i: any) => i.section_id === props.currentSectionId
    )
  } catch (e: any) {
    handleApiError(e, 'AI 分析')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.ai-panel {
  padding: 0 4px;
}
.ai-section {
  margin-bottom: 16px;
}
.ai-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}
</style>
