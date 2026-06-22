<template>
  <div class="reliability-conclusion">
    <el-divider content-position="left">审计说明与结论</el-divider>

    <!-- 审计说明 -->
    <div class="reliability-conclusion__section">
      <div class="reliability-conclusion__title-row">
        <h4 class="reliability-conclusion__title">审计说明</h4>
        <el-button
          v-if="!readonly"
          type="primary"
          size="small"
          plain
          :loading="aiLoading"
          @click="handleAiFill"
        >
          AI 智能填充
        </el-button>
      </div>
      <el-form label-position="top" size="small">
        <el-form-item label="验证总体情况说明">
          <el-input
            :model-value="auditNote.note_general"
            type="textarea"
            :rows="3"
            :disabled="readonly"
            placeholder="简要描述电子回函可靠性验证的整体执行情况（已验证数量、方法、结果概述）"
            @input="(val: string) => $emit('update-note', 'note_general', val)"
          />
        </el-form-item>
        <el-form-item label="不可靠情况说明">
          <el-input
            :model-value="auditNote.note_unreliable"
            type="textarea"
            :rows="3"
            :disabled="readonly"
            placeholder="对被评定为不可靠的回函，说明原因及后续处理（替代程序/追加证据/调整建议）"
            @input="(val: string) => $emit('update-note', 'note_unreliable', val)"
          />
        </el-form-item>
        <el-form-item label="其他事项">
          <el-input
            :model-value="auditNote.note_other"
            type="textarea"
            :rows="2"
            :disabled="readonly"
            placeholder="如有其他需说明的验证事项"
            @input="(val: string) => $emit('update-note', 'note_other', val)"
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- 审计结论 -->
    <div class="reliability-conclusion__section">
      <h4 class="reliability-conclusion__title">审计结论</h4>
      <el-form label-position="top" size="small">
        <el-form-item label="结论类型">
          <el-radio-group
            :model-value="conclusion.conclusion_type"
            :disabled="readonly"
            @change="(val: string) => $emit('update-conclusion', 'conclusion_type', val)"
          >
            <el-radio value="可靠">可靠——电子回函经验证均可靠，可作为审计证据</el-radio>
            <el-radio value="部分可靠需补充">部分可靠需补充——部分回函需补充程序确认可靠性</el-radio>
            <el-radio value="不可靠">不可靠——电子回函存在不可靠情形，需执行替代程序</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="结论说明">
          <el-input
            :model-value="conclusion.conclusion_text"
            type="textarea"
            :rows="3"
            :disabled="readonly"
            placeholder="对可靠性验证的整体结论进行说明，包括对审计证据充分性和适当性的影响判断"
            @input="(val: string) => $emit('update-conclusion', 'conclusion_text', val)"
          />
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ReliabilityAuditNote, ReliabilityConclusion } from './reliabilityTypes'

const props = defineProps<{
  auditNote: ReliabilityAuditNote
  conclusion: ReliabilityConclusion
  readonly: boolean
  /** 从父组件传入的统计数据，用于 AI 填充 */
  totalCount?: number
  verifiedCount?: number
  reliableCount?: number
  partialCount?: number
  unreliableCount?: number
  originalReturnedCount?: number
}>()

const emit = defineEmits<{
  (e: 'update-note', field: string, value: string): void
  (e: 'update-conclusion', field: string, value: any): void
}>()

const aiLoading = ref(false)

function handleAiFill() {
  aiLoading.value = true
  try {
    const total = props.totalCount ?? 0
    const verified = props.verifiedCount ?? 0
    const reliable = props.reliableCount ?? 0
    const partial = props.partialCount ?? 0
    const unreliable = props.unreliableCount ?? 0
    const originalReturned = props.originalReturnedCount ?? 0

    // 生成验证总体情况说明
    let general = ''
    if (total > 0) {
      general = `本次对 ${total} 份电子回函（传真/电子邮件方式）执行了可靠性验证。`
      if (originalReturned > 0) {
        general += `其中 ${originalReturned} 份已寄回原件，免于验证。`
      }
      const needVerify = total - originalReturned
      if (needVerify > 0) {
        general += `需验证 ${needVerify} 份，已完成验证 ${verified} 份（验证率 ${total > 0 ? Math.round((verified / total) * 100) : 0}%）。`
      }
      if (reliable > 0) general += `判定可靠 ${reliable} 份。`
      if (partial > 0) general += `部分可靠需补充 ${partial} 份。`
      if (unreliable > 0) general += `判定不可靠 ${unreliable} 份。`
    } else {
      general = '本次函证未涉及电子回函（传真/电子邮件），无需执行可靠性验证。'
    }

    // 生成不可靠情况说明
    let noteUnreliable = ''
    if (unreliable > 0) {
      noteUnreliable = `共 ${unreliable} 份电子回函被评定为不可靠。主要原因包括：发件人身份无法确认、使用私人邮箱（无法证实发件人授权）、邮箱域名与被函证单位不一致等。`
      noteUnreliable += '对不可靠的回函已建议执行替代程序（D0-5/D0-6），并将相关信息收集至 D0-8 舞弊风险评价（第7条）。'
    } else if (total > 0) {
      noteUnreliable = '本次验证未发现不可靠的电子回函。'
    }

    // 仅填充空白字段
    if (!props.auditNote.note_general) emit('update-note', 'note_general', general)
    if (!props.auditNote.note_unreliable) emit('update-note', 'note_unreliable', noteUnreliable)

    // 自动推荐结论类型
    if (!props.conclusion.conclusion_type) {
      if (unreliable > 0) {
        emit('update-conclusion', 'conclusion_type', '不可靠')
      } else if (partial > 0) {
        emit('update-conclusion', 'conclusion_type', '部分可靠需补充')
      } else if (total > 0) {
        emit('update-conclusion', 'conclusion_type', '可靠')
      }
    }

    ElMessage.success('已根据验证数据生成审计说明（仅供参考，请根据实际情况修改）')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.reliability-conclusion__section {
  margin-bottom: 16px;
}

.reliability-conclusion__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.reliability-conclusion__title {
  font-size: 14px;
  font-weight: 500;
  margin: 8px 0;
  color: var(--el-text-color-primary);
}

:deep(.el-radio) {
  display: block;
  margin-bottom: 8px;
  line-height: 1.5;
}
</style>
