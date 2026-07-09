<template>
  <div class="s12-branch-general">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>S12-3-2 利用专家评价管理层的工作的适当性</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview('s12-3-2-branch-general', '通用评价')"
            >复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-context">
        <p>本表用于评价利用注册会计师的专家评价管理层工作的适当性（通用领域）。评价内容包括管理层使用的方法、假设、数据及其结论是否恰当。</p>
      </div>

      <!-- 评价对象基本信息 -->
      <el-descriptions :column="2" border class="eval-info" size="small">
        <el-descriptions-item label="评价领域">
          <el-tag type="info">通用</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="管理层专家">
          <el-input
            v-if="!isReadonly"
            v-model="expertInfo.name"
            size="small"
            placeholder="管理层专家姓名/机构"
          />
          <span v-else>{{ expertInfo.name || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="评价事项">
          <el-input
            v-if="!isReadonly"
            v-model="expertInfo.matter"
            size="small"
            placeholder="所评价的审计事项"
          />
          <span v-else>{{ expertInfo.matter || '—' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="评价日期">
          <el-date-picker
            v-if="!isReadonly"
            v-model="expertInfo.date"
            type="date"
            size="small"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
          />
          <span v-else>{{ expertInfo.date || '—' }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 评价检查表 -->
      <el-table
        :data="evalItems"
        border
        style="width: 100%; font-size: 13px; margin-top: 16px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="评价类别" width="120">
          <template #default="{ row }">
            <span>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="question" label="评价项目" min-width="360">
          <template #default="{ row }">
            <span>{{ row.question }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="answer" label="评价结论" width="140" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.answer"
              size="small"
              placeholder="—"
              style="width: 110px"
            >
              <el-option label="恰当" value="恰当" />
              <el-option label="基本恰当" value="基本恰当" />
              <el-option label="不恰当" value="不恰当" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <span v-else>{{ row.answer || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明/证据" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="说明"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 总体评价结论 -->
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
        placeholder="填写总体评价结论"
      />
      <div v-else class="conclusion-text">{{ evalConclusion || '—' }}</div>
    </el-card>

    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>1. 评价管理层使用的方法和假设是否恰当。</p>
      <p>2. 评价数据的完整性、准确性和相关性。</p>
      <p>3. 将专家结论与管理层结论进行比较分析。</p>
      <p>4. 如有差异，分析原因并确定进一步审计程序。</p>
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
  domain?: string
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

const expertInfo = ref({
  name: '',
  matter: '',
  date: '',
})

const evalItems = ref([
  { category: '方法', question: '管理层使用的方法是否为该领域通常接受的方法？', answer: '', remark: '' },
  { category: '方法', question: '管理层使用的方法是否适用于被审计事项的具体情况？', answer: '', remark: '' },
  { category: '方法', question: '管理层使用的方法是否与以前年度一致（如不一致，变更是否合理）？', answer: '', remark: '' },
  { category: '假设', question: '管理层使用的重大假设是否合理？', answer: '', remark: '' },
  { category: '假设', question: '假设是否在合理范围内且相互一致？', answer: '', remark: '' },
  { category: '假设', question: '假设是否得到充分的客观数据支持？', answer: '', remark: '' },
  { category: '数据', question: '管理层使用的源数据是否完整和准确？', answer: '', remark: '' },
  { category: '数据', question: '源数据是否来源可靠、来源可追溯？', answer: '', remark: '' },
  { category: '数据', question: '源数据是否经过适当的审核或验证？', answer: '', remark: '' },
  { category: '结论', question: '管理层的结论是否逻辑一致且得到充分支持？', answer: '', remark: '' },
  { category: '结论', question: '管理层的结论与注册会计师专家的结论是否一致？', answer: '', remark: '' },
  { category: '结论', question: '如有差异，差异是否得到合理解释？', answer: '', remark: '' },
  { category: '披露', question: '相关会计估计和关键假设是否在财务报表中恰当披露？', answer: '', remark: '' },
  { category: '披露', question: '披露内容是否充分反映估计的不确定性程度？', answer: '', remark: '' },
])

const evalConclusion = ref('')

function handleAiAssist() { /* TODO */ }
function handleAiConclusion() { /* TODO */ }
</script>

<style scoped>
.s12-branch-general { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; }
.methodology-context {
  margin-bottom: 12px; padding: 8px 12px;
  border-left: 3px solid #e6a23c; background: #fdf6ec;
  font-size: 12px; color: #8a6914; line-height: 1.5;
}
.eval-info { margin-top: 12px; }
.conclusion-card { margin-top: 16px; }
.conclusion-text { white-space: pre-wrap; font-size: 13px; line-height: 1.6; color: #303133; }
.edit-hints { margin-top: 16px; font-size: 12px; color: #909399; }
.edit-hints summary { cursor: pointer; user-select: none; }
.edit-hints p { margin: 4px 0; line-height: 1.5; }
</style>
