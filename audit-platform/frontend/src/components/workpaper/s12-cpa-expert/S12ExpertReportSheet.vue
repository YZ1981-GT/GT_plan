<template>
  <div class="s12-expert-report">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-3-1 注册会计师的专家的报告</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-3-1-report', '专家报告')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-context">
        <p>记录注册会计师的专家所出具的报告的主要内容，以及注册会计师对该报告的审阅结论。</p>
      </div>

      <el-table
        :data="reportItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="item" label="审阅项目" min-width="300">
          <template #default="{ row }">
            <span>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="报告内容/审阅情况" min-width="360">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.content"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写报告内容或审阅情况"
            />
            <span v-else>{{ row.content || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审阅结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>报告审阅结论</span>
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
        v-model="reportConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写报告审阅结论"
      />
      <div v-else class="conclusion-text">{{ reportConclusion || '—' }}</div>
    </el-card>

    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 审阅报告是否包含专家对工作范围、方法、假设的描述。</p>
      <p>2. 审阅报告的结论是否明确清晰、易于理解。</p>
      <p>3. 确认报告中使用的数据来源。</p>
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

const reportItems = ref([
  { item: '报告标题及日期', content: '' },
  { item: '专家的姓名、资质和所属机构', content: '' },
  { item: '工作范围及目标描述', content: '' },
  { item: '使用的方法和假设', content: '' },
  { item: '使用的源数据及其来源', content: '' },
  { item: '重要发现和结论', content: '' },
  { item: '与管理层估计/假设的一致性', content: '' },
  { item: '对使用限制条件的说明', content: '' },
])

const reportConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-expert-report { padding: 12px; }
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
