<template>
  <div class="s12-objectivity-eval">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-1-1 评价专家的客观性</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-1-1-objectivity', '评价专家客观性')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-context">
        <p>客观性是指专家在执业过程中不受利益冲突或不当影响的能力。注册会计师应了解可能影响专家客观性的利益和关系。</p>
      </div>

      <el-table
        :data="objectivityItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="question" label="评价项目" min-width="400">
          <template #default="{ row }">
            <span>{{ row.question }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="answer" label="是/否" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.answer"
              size="small"
              placeholder="—"
              style="width: 80px"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="N/A" value="N/A" />
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
          <span>客观性评价结论</span>
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
        placeholder="填写客观性评价结论"
      />
      <div v-else class="conclusion-text">{{ evalConclusion || '—' }}</div>
    </el-card>

    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 了解专家与被审计单位之间是否存在经济利益、雇佣关系或业务关系。</p>
      <p>2. 考虑专家的工作成果是否与某种特定结果挂钩（如或有收费）。</p>
      <p>3. 如存在可能影响客观性的因素，评估防范措施是否有效。</p>
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

const objectivityItems = ref([
  { question: '专家是否为被审计单位的员工？', answer: '', remark: '' },
  { question: '专家是否与被审计单位存在经济利益关系？', answer: '', remark: '' },
  { question: '专家的收费是否取决于审计结果或被审计单位的某种特定结果？', answer: '', remark: '' },
  { question: '专家与被审计单位管理层是否存在密切的个人关系？', answer: '', remark: '' },
  { question: '专家过去是否曾为被审计单位提供与审计事项相关的其他服务？', answer: '', remark: '' },
  { question: '是否存在其他可能影响专家客观性的利益或关系？', answer: '', remark: '' },
  { question: '若存在威胁客观性的因素，是否采取了防范措施使其降至可接受水平？', answer: '', remark: '' },
  { question: '综合考虑上述因素，专家的客观性是否满足审计需要？', answer: '', remark: '' },
])

const evalConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-objectivity-eval { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; }
.methodology-context {
  margin-bottom: 12px; padding: 8px 12px;
  border-left: 3px solid #e6a23c; background: #fdf6ec;
  font-size: 12px; color: #8a6914; line-height: 1.5;
}
.conclusion-card { margin-top: 16px; }
.conclusion-text { white-space: pre-wrap; font-size: 13px; line-height: 1.6; color: #303133; }
.edit-hints { margin-top: 16px; font-size: 12px; color: #909399; }
.edit-hints summary { cursor: pointer; user-select: none; }
.edit-hints p { margin: 4px 0; line-height: 1.5; }
</style>
