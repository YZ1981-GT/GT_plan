<template>
  <div class="s12-appropriateness">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-3 评价专家工作的恰当性</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-3-appropriateness', '评价专家工作恰当性')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-context">
        <p>注册会计师应评价专家工作与审计目的的相关性和合理性，包括所用方法和假设的恰当性、源数据的完整性与准确性、以及发现和结论与其他审计证据的一致性。</p>
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
              <el-option label="恰当" value="恰当" />
              <el-option label="基本恰当" value="基本恰当" />
              <el-option label="不恰当" value="不恰当" />
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
          <span>恰当性评价结论</span>
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
        placeholder="填写恰当性评价结论"
      />
      <div v-else class="conclusion-text">{{ evalConclusion || '—' }}</div>
    </el-card>

    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 评价专家使用的方法是否为该领域通常接受的方法。</p>
      <p>2. 评价假设和模型是否恰当、完整。</p>
      <p>3. 评价源数据的完整性和准确性。</p>
      <p>4. 评价专家的发现与结论是否与其他审计证据一致。</p>
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
  { question: '专家使用的方法是否为该专长领域通常接受或使用的方法？', answer: '', remark: '' },
  { question: '专家使用的方法对审计目的而言是否恰当？', answer: '', remark: '' },
  { question: '专家使用的假设和模型是否合理？', answer: '', remark: '' },
  { question: '专家使用的源数据是否完整和准确？', answer: '', remark: '' },
  { question: '专家的发现和结论是否与其他审计证据一致？', answer: '', remark: '' },
  { question: '专家的发现和结论是否以专家的专长领域中的原则和方法为基础恰当表述？', answer: '', remark: '' },
  { question: '如果专家的工作涉及使用重要的假设和方法，这些假设和方法在被审计情况下是否合理？', answer: '', remark: '' },
  { question: '如果专家的工作涉及使用源数据，这些数据对专家的工作是否相关和合理？', answer: '', remark: '' },
])

const evalConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-appropriateness { padding: 12px; }
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
