<template>
  <div class="h2-tab-review-record">
    <!-- 工程筛选 -->
    <div class="filter-bar">
      <el-select v-model="selectedProject" placeholder="按工程项目筛选审核事项" size="small" clearable
        style="width:260px" @change="handleProjectFilter">
        <el-option v-for="p in state.projectList.value" :key="p" :label="p" :value="p" />
      </el-select>
    </div>

    <!-- 基本信息 -->
    <el-card shadow="never" class="review-card">
      <template #header>
        <div class="section-header">
          <span>审核基本信息</span>
        </div>
      </template>
      <div class="record-meta">
        <div class="meta-row">
          <span class="meta-label">工程项目：</span>
          <el-input v-if="!isReadonly" v-model="state.basicInfo.value.projectName" size="small" style="width:220px"
            @change="onBasicChange('projectName', state.basicInfo.value.projectName)" />
          <span v-else>{{ state.basicInfo.value.projectName || '-' }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">施工单位：</span>
          <el-input v-if="!isReadonly" v-model="state.basicInfo.value.constructionUnit" size="small" style="width:220px"
            @change="onBasicChange('constructionUnit', state.basicInfo.value.constructionUnit)" />
          <span v-else>{{ state.basicInfo.value.constructionUnit || '-' }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">监理单位：</span>
          <el-input v-if="!isReadonly" v-model="state.basicInfo.value.supervisorUnit" size="small" style="width:220px"
            @change="onBasicChange('supervisorUnit', state.basicInfo.value.supervisorUnit)" />
          <span v-else>{{ state.basicInfo.value.supervisorUnit || '-' }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">合同金额：</span>
          <el-input-number v-if="!isReadonly" v-model="state.basicInfo.value.contractAmount" :controls="false"
            size="small" style="width:220px"
            @change="onBasicChange('contractAmount', state.basicInfo.value.contractAmount)" />
          <span v-else class="amt-cell">{{ fmtAmt(state.basicInfo.value.contractAmount) }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">审核日期：</span>
          <el-date-picker v-if="!isReadonly" v-model="state.basicInfo.value.reviewDate" type="date" size="small"
            value-format="YYYY-MM-DD" style="width:220px"
            @change="onBasicChange('reviewDate', state.basicInfo.value.reviewDate)" />
          <span v-else>{{ state.basicInfo.value.reviewDate || '-' }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">审核人员：</span>
          <el-input v-if="!isReadonly" v-model="state.basicInfo.value.reviewer" size="small" style="width:220px"
            @change="onBasicChange('reviewer', state.basicInfo.value.reviewer)" />
          <span v-else>{{ state.basicInfo.value.reviewer || '-' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 审核事项 -->
    <el-card shadow="never" class="review-card">
      <template #header>
        <div class="section-header">
          <span>审核事项（共 {{ state.reviewItems.value.length }} 项 / 异常 {{ state.abnormalCount.value }} 项）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('items')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-6-items')">💬</el-button>
          </div>
        </div>
      </template>

      <div class="review-items">
        <div v-for="item in state.filteredItems.value" :key="item.rowId" class="review-item">
          <div class="item-header">
            <el-input v-if="!isReadonly" v-model="item.subject" size="small" placeholder="审核事项"
              style="flex:1" @change="onItemChange(item.rowId, 'subject', item.subject)" />
            <span v-else class="item-title">{{ item.subject || '（未命名事项）' }}</span>
            <el-checkbox v-if="!isReadonly" v-model="item.isAbnormal" label="异常"
              @change="onItemChange(item.rowId, 'isAbnormal', item.isAbnormal)" />
            <el-tag v-else :type="item.isAbnormal ? 'danger' : 'success'" size="small">
              {{ item.isAbnormal ? '异常' : '正常' }}
            </el-tag>
            <el-button v-if="!isReadonly" size="small" type="danger" link
              @click="handleRemoveItem(item.rowId)">✕</el-button>
          </div>
          <div class="item-grid">
            <div class="item-field">
              <span class="field-label">审核内容</span>
              <el-input v-if="!isReadonly" v-model="item.content" size="small"
                @change="onItemChange(item.rowId, 'content', item.content)" />
              <span v-else>{{ item.content || '-' }}</span>
            </div>
            <div class="item-field">
              <span class="field-label">合同约定</span>
              <el-input v-if="!isReadonly" v-model="item.contractTerms" size="small"
                @change="onItemChange(item.rowId, 'contractTerms', item.contractTerms)" />
              <span v-else>{{ item.contractTerms || '-' }}</span>
            </div>
            <div class="item-field">
              <span class="field-label">实际情况</span>
              <el-input v-if="!isReadonly" v-model="item.actualStatus" size="small"
                @change="onItemChange(item.rowId, 'actualStatus', item.actualStatus)" />
              <span v-else>{{ item.actualStatus || '-' }}</span>
            </div>
            <div class="item-field">
              <span class="field-label">差异</span>
              <el-input v-if="!isReadonly" v-model="item.difference" size="small"
                @change="onItemChange(item.rowId, 'difference', item.difference)" />
              <span v-else>{{ item.difference || '-' }}</span>
            </div>
            <div class="item-field">
              <span class="field-label">进一步程序</span>
              <el-input v-if="!isReadonly" v-model="item.furtherProcedure" size="small"
                @change="onItemChange(item.rowId, 'furtherProcedure', item.furtherProcedure)" />
              <span v-else>{{ item.furtherProcedure || '-' }}</span>
            </div>
            <div class="item-field">
              <span class="field-label">证据索引</span>
              <el-input v-if="!isReadonly" v-model="item.evidenceIndex" size="small"
                @change="onItemChange(item.rowId, 'evidenceIndex', item.evidenceIndex)" />
              <span v-else>{{ item.evidenceIndex || '-' }}</span>
            </div>
          </div>
          <div class="item-opinion">
            <span class="field-label">审核意见</span>
            <el-input v-if="!isReadonly" v-model="item.opinion" type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }" size="small" placeholder="审核意见..."
              @blur="onItemChange(item.rowId, 'opinion', item.opinion)" />
            <p v-else class="item-comment">{{ item.opinion || '' }}</p>
          </div>
        </div>
      </div>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddItem">+ 新增审核事项</el-button>
      </div>
    </el-card>

    <!-- 结论 + 签章 -->
    <el-card shadow="never" class="review-card">
      <template #header>
        <div class="section-header">
          <span>审核结论与签章</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="state.conclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审核结论..." :disabled="isReadonly"
        @blur="state.saveConclusion(state.conclusion.value)" />
      <div class="sign-section">
        <div class="meta-row sign-row">
          <span class="meta-label">编制：</span>
          <el-input v-if="!isReadonly" v-model="state.signature.value.preparedBy" size="small" style="width:140px"
            placeholder="编制人" @change="onSignChange" />
          <span v-else class="sign-placeholder">{{ state.signature.value.preparedBy || '________' }}</span>
          <span style="margin-left:16px">复核：</span>
          <el-input v-if="!isReadonly" v-model="state.signature.value.reviewedBy" size="small" style="width:140px"
            placeholder="复核人" @change="onSignChange" />
          <span v-else class="sign-placeholder">{{ state.signature.value.reviewedBy || '________' }}</span>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>基本信息记录被审核工程的施工/监理单位与合同金额</li>
        <li>逐条录入审核事项，勾选"异常"标记需进一步处理的事项</li>
        <li>筛选器按工程名称过滤审核事项（匹配事项/内容）</li>
        <li>签章结论需编制人、复核人手动确认</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabReviewRecord.vue — H2-6 审核记录
 * 签章式（基本信息+审核事项逐条+结论签名）+ 工程筛选el-select + AI + 💬复核
 * Spec: Task 4.8 | Requirements: 7.1-7.5
 */
import { ref, inject, toRef, computed } from 'vue'
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
})

function handleProjectFilter() {
  state.setFilterProject(selectedProject.value)
}

function onBasicChange(field: string, value: any) {
  state.updateBasicInfo(field as any, value)
}

function onItemChange(rowId: string, field: string, value: any) {
  state.updateReviewItem(rowId, field, value)
}

function handleAddItem() {
  state.addReviewItem()
}

function handleRemoveItem(rowId: string) {
  state.removeReviewItem(rowId)
}

function onSignChange() {
  state.saveSignature(state.signature.value)
}

function handleAiGenerate(section: string) {
  console.log('AI generate review:', section)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-review-record { padding: 16px; font-size: var(--wp-font-size, 13px); }
.filter-bar { margin-bottom: 16px; }
.review-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.record-meta { display: flex; flex-wrap: wrap; gap: 12px 24px; }
.meta-row { display: flex; align-items: center; gap: 8px; }
.meta-label { font-weight: 500; color: var(--el-text-color-secondary); }
.amt-cell { font-variant-numeric: tabular-nums; }
.review-items { margin: 4px 0; }
.review-item { margin-bottom: 12px; padding: 10px; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; }
.item-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.item-title { flex: 1; font-weight: 600; }
.item-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; margin-bottom: 8px; }
.item-field { display: flex; align-items: center; gap: 6px; }
.field-label { color: var(--el-text-color-secondary); min-width: 68px; }
.item-opinion { display: flex; flex-direction: column; gap: 4px; }
.item-comment { margin: 4px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.sign-section { margin-top: 12px; }
.sign-row { margin-top: 8px; }
.sign-placeholder { font-weight: 600; text-decoration: underline; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
