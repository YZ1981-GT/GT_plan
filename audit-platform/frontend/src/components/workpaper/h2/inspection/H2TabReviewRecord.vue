<template>
  <div class="h2-tab-review-record">
    <!-- 工程筛选 -->
    <div class="filter-bar">
      <el-select v-model="selectedProject" placeholder="选择工程项目" size="small" clearable style="width:240px"
        @change="handleProjectFilter">
        <el-option v-for="p in state.projectOptions.value" :key="p" :label="p" :value="p" />
      </el-select>
    </div>

    <!-- 签章式审核卡片 -->
    <el-card v-for="record in state.filteredRecords.value" :key="record.id"
      shadow="never" class="review-card">
      <template #header>
        <div class="section-header">
          <span>{{ record.title }}</span>
          <div class="section-header-actions">
            <el-tag :type="record.status === '已审核' ? 'success' : 'warning'" size="small">
              {{ record.status }}
            </el-tag>
            <el-button size="small" type="primary" link @click="handleAiGenerate(record.id)">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview(`H2-6-${record.id}`)">💬</el-button>
          </div>
        </div>
      </template>

      <!-- 基本信息区 -->
      <div class="record-meta">
        <div class="meta-row">
          <span class="meta-label">工程项目：</span>
          <span>{{ record.projectName || '-' }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">审核日期：</span>
          <el-date-picker v-if="!isReadonly" v-model="record.reviewDate" type="date" size="small"
            value-format="YYYY-MM-DD" style="width:160px"
            @change="onFieldChange(record.id, 'reviewDate', $event)" />
          <span v-else>{{ record.reviewDate || '-' }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">审核人员：</span>
          <el-input v-if="!isReadonly" v-model="record.reviewer" size="small" style="width:160px"
            @change="onFieldChange(record.id, 'reviewer', $event)" />
          <span v-else>{{ record.reviewer || '-' }}</span>
        </div>
      </div>

      <!-- 审核事项 -->
      <div class="review-items">
        <div v-for="(item, idx) in record.items" :key="idx" class="review-item">
          <div class="item-header">
            <span class="item-seq">{{ idx + 1 }}.</span>
            <span class="item-title">{{ item.title }}</span>
            <el-select v-if="!isReadonly" v-model="item.result" size="small" style="width:100px"
              @change="onItemChange(record.id, idx, 'result', $event)">
              <el-option label="合规" value="合规" />
              <el-option label="存疑" value="存疑" />
              <el-option label="不合规" value="不合规" />
            </el-select>
            <el-tag v-else :type="item.result === '合规' ? 'success' : item.result === '不合规' ? 'danger' : 'warning'" size="small">
              {{ item.result || '待审' }}
            </el-tag>
          </div>
          <el-input v-if="!isReadonly" v-model="item.comment" type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }" size="small" placeholder="审核意见..."
            @blur="onItemChange(record.id, idx, 'comment', item.comment)" />
          <p v-else class="item-comment">{{ item.comment || '' }}</p>
        </div>
      </div>

      <!-- 签章结论 -->
      <div class="sign-section">
        <el-divider />
        <div class="meta-row">
          <span class="meta-label">审核结论：</span>
          <el-input v-if="!isReadonly" v-model="record.conclusion" type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }" style="flex:1"
            @blur="onFieldChange(record.id, 'conclusion', record.conclusion)" />
          <span v-else>{{ record.conclusion || '-' }}</span>
        </div>
        <div class="meta-row sign-row">
          <span class="meta-label">签章：</span>
          <span class="sign-placeholder">{{ record.reviewer || '________' }}</span>
          <span style="margin-left:24px">日期：{{ record.reviewDate || '____年__月__日' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 新增审核记录 -->
    <div class="add-row-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRecord">+ 新增审核记录</el-button>
    </div>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>每个转固工程项目对应一条审核记录</li>
        <li>审核事项包括：竣工验收、费用完整性、条件判定等</li>
        <li>筛选器可按工程项目过滤显示</li>
        <li>签章结论需审核人手动确认</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabReviewRecord.vue — H2-6 审核记录
 * 签章式卡片 + 工程筛选el-select + AI + 💬复核
 * Spec: Task 4.8 | Requirements: 7.1-7.5
 */
import { ref, inject, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2ReviewRecord } from '../../composables/useH2ReviewRecord'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const selectedProject = ref('')

const state = useH2ReviewRecord({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  filterProject: selectedProject,
})

function handleProjectFilter() {
  // reactivity handles it via filterProject ref
}

function onFieldChange(recordId: string, field: string, value: any) {
  state.updateField(recordId, field, value)
}

function onItemChange(recordId: string, idx: number, field: string, value: any) {
  state.updateItem(recordId, idx, field, value)
}

async function handleAddRecord() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增审核记录', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRecord(value)
  } catch { /* cancelled */ }
}

function handleAiGenerate(recordId: string) {
  console.log('AI generate review:', recordId)
}

function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.h2-tab-review-record { padding: 16px; font-size: 13px; }
.filter-bar { margin-bottom: 16px; }
.review-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.record-meta { margin-bottom: 16px; }
.meta-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.meta-label { font-weight: 500; min-width: 80px; color: var(--el-text-color-secondary); }
.review-items { margin: 12px 0; }
.review-item { margin-bottom: 12px; padding: 8px; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.item-seq { font-weight: 600; }
.item-title { flex: 1; }
.item-comment { margin: 4px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.sign-section { margin-top: 12px; }
.sign-row { margin-top: 8px; }
.sign-placeholder { font-weight: 600; text-decoration: underline; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
