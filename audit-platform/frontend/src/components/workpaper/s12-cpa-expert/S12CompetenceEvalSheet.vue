<template>
  <div class="s12-competence-eval">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-1 评价胜任能力、专业素质和客观性</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-1-competence', '评价胜任能力')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <!-- 方法论上下文提示 -->
      <div class="methodology-context">
        <p>根据《中国注册会计师审计准则第1421号》，注册会计师应当评价专家是否具备与审计相关事项有关的胜任能力、专业素质和客观性。</p>
      </div>

      <el-table
        :data="evalItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="question" label="评价项目" min-width="400">
          <template #default="{ row }">
            <span>{{ row.question }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="answer" label="评价结论" width="160" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.answer"
              size="small"
              placeholder="请选择"
              style="width: 130px"
            >
              <el-option label="满足要求" value="满足要求" />
              <el-option label="基本满足" value="基本满足" />
              <el-option label="不满足" value="不满足" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <span v-else>{{ row.answer || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写说明"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 评价结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>总体评价结论</span>
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
        placeholder="填写评价结论"
      />
      <div v-else class="conclusion-text">{{ evalConclusion || '—' }}</div>
    </el-card>

    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 胜任能力：考虑专家是否持有相关证书/执照、在相关领域的经验年限。</p>
      <p>2. 专业素质：考虑专家是否受到专业组织的约束、遵守职业道德规范。</p>
      <p>3. 客观性：考虑是否存在利益冲突（详见 S12-1-1）。</p>
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

const evalItems = ref([
  { question: '专家是否持有相关领域的专业资格证书或执照？', answer: '', remark: '' },
  { question: '专家是否具备与审计事项相关的充分经验？', answer: '', remark: '' },
  { question: '专家在相关领域的工作年限是否足够？', answer: '', remark: '' },
  { question: '专家是否了解相关的会计准则和审计准则？', answer: '', remark: '' },
  { question: '专家是否受专业团体/组织的规范约束或遵守职业道德规范？', answer: '', remark: '' },
  { question: '专家是否有良好的执业记录（无重大失误或违规处理）？', answer: '', remark: '' },
  { question: '专家是否具有客观性（参见 S12-1-1 详细评价）？', answer: '', remark: '' },
  { question: '综合评价专家的胜任能力、专业素质和客观性是否满足本次审计需要？', answer: '', remark: '' },
])

const evalConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-competence-eval { padding: 12px; }
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
