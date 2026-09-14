<template>
  <div class="s12-specialty">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-2 了解专家的专长领域</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-2-specialty', '了解专家专长领域')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-context">
        <p>注册会计师应充分了解专家的专长领域，以能够确定专家的工作用于审计目的、评价其工作的恰当性以及评估其发现和结论的合理性。</p>
      </div>

      <el-table
        :data="specialtyItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="question" label="了解事项" min-width="400">
          <template #default="{ row }">
            <span>{{ row.question }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="answer" label="了解情况" min-width="280">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.answer"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写了解情况"
            />
            <span v-else>{{ row.answer || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>了解结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="evalConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写了解结论"
      />
      <div v-else class="conclusion-text">{{ evalConclusion || '—' }}</div>
    </el-card>

    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 了解专家的专长领域是否涵盖与审计事项相关的所有方面。</p>
      <p>2. 了解该领域是否存在替代性的方法或假设。</p>
      <p>3. 考虑专家对审计相关情况的了解程度（如行业特点、监管环境）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

const specialtyItems = ref([
  { question: '专家的专长领域及具体方向是什么？', answer: '' },
  { question: '该专长领域与被审计单位审计事项的相关性如何？', answer: '' },
  { question: '专家在该领域是否存在替代性的方法或假设？', answer: '' },
  { question: '专家使用的数据来源和方法的性质是什么？', answer: '' },
  { question: '专家对审计相关情况（行业特点、监管环境等）的了解程度如何？', answer: '' },
  { question: '专家的工作成果将以何种形式呈现（报告、备忘录等）？', answer: '' },
])

const evalConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-specialty { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; }
.methodology-context {
  margin-bottom: 12px; padding: 8px 12px;
  border-left: 3px solid #e6a23c; background: #fdf6ec;
  font-size: 12px; color: #8a6914; line-height: 1.5;
}
.conclusion-card { margin-top: 16px; }
.conclusion-text { white-space: pre-wrap; font-size: var(--wp-font-size, 13px); line-height: 1.6; color: #303133; }
.edit-hints { margin-top: 16px; font-size: 12px; color: #909399; }
.edit-hints summary { cursor: pointer; user-select: none; }
.edit-hints p { margin: 4px 0; line-height: 1.5; }
</style>
