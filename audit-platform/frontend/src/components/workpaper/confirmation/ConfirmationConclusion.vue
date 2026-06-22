<template>
  <div class="confirmation-conclusion">
    <!-- 标题区 -->
    <div class="confirmation-conclusion__header">
      <span class="confirmation-conclusion__title">审计结论</span>
      <span class="confirmation-conclusion__subtitle">基于函证结果，对账面记录的审计判断</span>
    </div>

    <!-- 结论选项 -->
    <div class="confirmation-conclusion__options">
      <el-radio-group
        :model-value="data.conclusion_type"
        :disabled="readonly"
        @update:model-value="(v) => $emit('update', 'conclusion_type', v)"
      >
        <div class="confirmation-conclusion__option" :class="{ 'is-active': data.conclusion_type === 'A' }">
          <el-radio value="A">
            <span class="confirmation-conclusion__option-tag confirmation-conclusion__option-tag--success">A</span>
            函证结果支持账面记录
          </el-radio>
          <p class="confirmation-conclusion__option-desc">回函与账面一致，覆盖率满足要求，审计证据充分</p>
        </div>
        <div class="confirmation-conclusion__option" :class="{ 'is-active': data.conclusion_type === 'B' }">
          <el-radio value="B">
            <span class="confirmation-conclusion__option-tag confirmation-conclusion__option-tag--warn">B</span>
            函证结果发现差异但经调查可接受
          </el-radio>
          <p class="confirmation-conclusion__option-desc">存在差异但原因合理（如在途款项、截止日差异），不影响审计结论</p>
        </div>
        <div class="confirmation-conclusion__option" :class="{ 'is-active': data.conclusion_type === 'C' }">
          <el-radio value="C">
            <span class="confirmation-conclusion__option-tag confirmation-conclusion__option-tag--danger">C</span>
            函证结果存在重大差异需进一步审计
          </el-radio>
          <p class="confirmation-conclusion__option-desc">差异金额重大或原因不明，需扩大审计范围或实施追加程序</p>
        </div>
      </el-radio-group>
    </div>

    <!-- 结论说明（B/C 时展开） -->
    <div v-if="data.conclusion_type === 'B' || data.conclusion_type === 'C'" class="confirmation-conclusion__detail">
      <div class="confirmation-conclusion__detail-label">
        <span>{{ data.conclusion_type === 'B' ? '差异原因及处理说明' : '重大差异说明及后续措施' }}</span>
      </div>
      <el-input
        :model-value="data.conclusion_text"
        :disabled="readonly"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :placeholder="conclusionPlaceholder"
        @update:model-value="(v) => $emit('update', 'conclusion_text', v)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ConclusionData } from './confirmationTypes'

const props = defineProps<{
  data: ConclusionData
  readonly: boolean
}>()

defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

const conclusionPlaceholder = computed(() => {
  if (props.data.conclusion_type === 'B') {
    return '说明差异性质（如：在途款项、截止日差异、汇率折算）及调查结论，确认不影响审计意见'
  }
  return '说明差异金额、涉及科目、初步原因判断、已采取的追加措施及下一步计划'
})
</script>

<style scoped>
.confirmation-conclusion {
  padding: 4px 0;
}

.confirmation-conclusion__header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.confirmation-conclusion__title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.confirmation-conclusion__subtitle {
  font-size: 12px;
  color: #909399;
}

.confirmation-conclusion__options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.confirmation-conclusion__option {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafbfc;
  transition: all 0.2s;
}

.confirmation-conclusion__option.is-active {
  border-color: #7b61ff;
  background: #f8f5ff;
}

.confirmation-conclusion__option .el-radio {
  display: flex;
  align-items: center;
  font-weight: 500;
}

.confirmation-conclusion__option-tag {
  display: inline-block;
  width: 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  margin-right: 6px;
}

.confirmation-conclusion__option-tag--success { background: #67c23a; }
.confirmation-conclusion__option-tag--warn { background: #e6a23c; }
.confirmation-conclusion__option-tag--danger { background: #f56c6c; }

.confirmation-conclusion__option-desc {
  font-size: 11px;
  color: #909399;
  margin: 4px 0 0 24px;
  line-height: 1.5;
}

.confirmation-conclusion__detail {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fffbf0;
}

.confirmation-conclusion__detail-label {
  font-size: 12px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}

.confirmation-conclusion__detail :deep(.el-textarea__inner) {
  font-size: 13px;
}
</style>
