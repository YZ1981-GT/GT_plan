<template>
  <div class="checklist-audit-note">
    <el-divider content-position="left">总体审计结论</el-divider>

    <!-- 总体说明 + AI -->
    <div class="checklist-audit-note__field">
      <div class="checklist-audit-note__field-header">
        <label class="checklist-audit-note__label">
          总体情况说明
          <span class="checklist-audit-note__hint">汇总所有公司的调节结果</span>
        </label>
        <el-button v-if="!readonly" size="small" type="primary" plain @click="handleAiFill">
          AI 生成
        </el-button>
      </div>
      <el-input
        v-if="!readonly"
        :model-value="globalNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="如：本次对X家单位逐户编制差异检查表，经双向调节后X家已平衡，X家仍有差异..."
        @input="(val: string) => $emit('update-global-note', val)"
      />
      <div v-else class="checklist-audit-note__text">{{ globalNote || '—' }}</div>
    </div>

    <!-- 审计结论 -->
    <div class="checklist-audit-note__field">
      <label class="checklist-audit-note__label">审计结论</label>
      <div class="checklist-audit-note__options">
        <el-radio-group
          :model-value="conclusion?.conclusion_type"
          :disabled="readonly"
          @change="(val: string) => $emit('update-conclusion', 'conclusion_type', val)"
        >
          <div class="checklist-audit-note__option" :class="{ 'is-active': conclusion?.conclusion_type === 'A' }">
            <el-radio label="A">
              <span class="checklist-audit-note__tag checklist-audit-note__tag--success">A</span>
              所有差异均已查明并调节相符
            </el-radio>
          </div>
          <div class="checklist-audit-note__option" :class="{ 'is-active': conclusion?.conclusion_type === 'B' }">
            <el-radio label="B">
              <span class="checklist-audit-note__tag checklist-audit-note__tag--warn">B</span>
              部分差异已调节，剩余差异不重大
            </el-radio>
          </div>
          <div class="checklist-audit-note__option" :class="{ 'is-active': conclusion?.conclusion_type === 'C' }">
            <el-radio label="C">
              <span class="checklist-audit-note__tag checklist-audit-note__tag--danger">C</span>
              存在无法调节的重大差异
            </el-radio>
          </div>
        </el-radio-group>
      </div>
      <el-input
        v-if="!readonly && (conclusion?.conclusion_type === 'B' || conclusion?.conclusion_type === 'C')"
        :model-value="conclusion?.conclusion_text"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
        :placeholder="conclusion?.conclusion_type === 'B' ? '说明剩余差异金额及不重大的判断依据' : '说明无法调节差异的金额、涉及公司及后续措施'"
        style="margin-top:8px"
        @input="(val: string) => $emit('update-conclusion', 'conclusion_text', val)"
      />
    </div>

    <!-- 重要性配置（与结论联动） -->
    <div class="checklist-audit-note__field">
      <label class="checklist-audit-note__label">
        实际执行重要性
        <el-tooltip content="差异绝对值超过此金额的项目标记为超重要性。用于判断结论B中剩余差异是否重大。" placement="top">
          <el-icon :size="12" style="cursor:help"><InfoFilled /></el-icon>
        </el-tooltip>
      </label>
      <div style="display:flex;align-items:center;gap:8px">
        <el-input-number
          v-if="!readonly"
          :model-value="materialityConfig?.performance_materiality"
          :controls="false"
          :precision="2"
          :min="0"
          size="small"
          placeholder="输入重要性金额"
          style="width:180px"
          @change="(val: number) => $emit('update-materiality', val)"
        />
        <span v-else class="checklist-audit-note__amount">
          {{ materialityConfig?.performance_materiality != null ? formatAmount(materialityConfig.performance_materiality) : '未配置' }}
        </span>
        <span style="font-size:12px;color:#909399">元（超过此金额的差异将标红）</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { ChecklistConclusion, ChecklistMaterialityConfig } from './diffChecklistTypes'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  globalNote: string
  conclusion: ChecklistConclusion
  materialityConfig: ChecklistMaterialityConfig
  readonly: boolean
  /** 从父组件传入的汇总统计 */
  totalCompanies?: number
  balancedCount?: number
  diffCount?: number
  overMaterialityCount?: number
}>()

const emit = defineEmits<{
  (e: 'update-global-note', value: string): void
  (e: 'update-conclusion', field: string, value: any): void
  (e: 'update-materiality', value: number): void
}>()

function handleAiFill() {
  const total = props.totalCompanies ?? 0
  const balanced = props.balancedCount ?? 0
  const diff = props.diffCount ?? 0
  const over = props.overMaterialityCount ?? 0

  let note = ''
  if (total === 0) {
    note = '本次函证差异检查表尚未录入数据。'
  } else if (diff === 0) {
    note = `本次共对 ${total} 家被询证单位逐户编制差异检查表，经双向调节后全部平衡，不存在未解释差异。函证结果有效支持账面记录。`
  } else {
    note = `本次共对 ${total} 家被询证单位逐户编制差异检查表。其中 ${balanced} 家经调节后已平衡，${diff} 家仍存在差异。`
    if (over > 0) {
      note += `${over} 家差异超过实际执行重要性，需重点关注并考虑扩大审计范围。`
    } else {
      note += `剩余差异金额均低于实际执行重要性，不影响审计结论。`
    }
  }

  emit('update-global-note', note)
  // 自动推荐结论
  if (!props.conclusion?.conclusion_type) {
    if (diff === 0) emit('update-conclusion', 'conclusion_type', 'A')
    else if (over === 0) emit('update-conclusion', 'conclusion_type', 'B')
    else emit('update-conclusion', 'conclusion_type', 'C')
  }
  ElMessage.success('已根据调节汇总数据生成说明及结论建议')
}

const prefs = useDisplayPrefsStore()

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}
</script>

<style scoped>
.checklist-audit-note {
  margin-top: 12px;
}

.checklist-audit-note__field {
  margin-bottom: 14px;
}

.checklist-audit-note__field-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.checklist-audit-note__label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.checklist-audit-note__hint {
  font-size: 11px;
  color: #909399;
  font-weight: 400;
  margin-left: 6px;
}

.checklist-audit-note__text {
  font-size: var(--wp-font-size, 13px);
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}

.checklist-audit-note__amount {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

/* 结论卡片 */
.checklist-audit-note__options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}

.checklist-audit-note__option {
  padding: 8px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafbfc;
  transition: all 0.2s;
}

.checklist-audit-note__option.is-active {
  border-color: #7b61ff;
  background: #f8f5ff;
}

.checklist-audit-note__option .el-radio {
  font-weight: 500;
}

.checklist-audit-note__tag {
  display: inline-block;
  width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  margin-right: 4px;
}

.checklist-audit-note__tag--success { background: #67c23a; }
.checklist-audit-note__tag--warn { background: #e6a23c; }
.checklist-audit-note__tag--danger { background: #f56c6c; }
</style>
