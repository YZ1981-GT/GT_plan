<template>
  <div class="confirmation-notes">
    <!-- 标题 + AI 预填充按钮 -->
    <div class="confirmation-notes__header">
      <div class="confirmation-notes__header-left">
        <span class="confirmation-notes__title">审计说明</span>
        <span class="confirmation-notes__subtitle">记录函证程序执行情况，供复核人员参阅</span>
      </div>
      <el-button
        v-if="!readonly"
        type="primary"
        size="small"
        :loading="aiLoading"
        :icon="MagicStick"
        @click="handleAiGenerate"
      >
        AI 预填充
      </el-button>
    </div>

    <!-- 说明区块列表 -->
    <div class="confirmation-notes__sections">
      <!-- 1. 函证总体情况 -->
      <div class="confirmation-notes__section">
        <div class="confirmation-notes__section-header">
          <span class="confirmation-notes__section-icon">📋</span>
          <span class="confirmation-notes__section-title">函证总体情况</span>
        </div>
        <p class="confirmation-notes__section-hint">
          概述发函范围（科目、单位数、金额）、发函方式（积极式/消极式）、时间安排等基本情况
        </p>
        <el-input
          :model-value="data.note_general"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="如：本次审计共向XX家单位发出积极式函证，涉及应收账款/合同负债等科目，函证金额合计XX元..."
          @update:model-value="(v) => $emit('update', 'note_general', v)"
        />
      </div>

      <!-- 2. 异常情况说明 -->
      <div class="confirmation-notes__section">
        <div class="confirmation-notes__section-header">
          <span class="confirmation-notes__section-icon">⚠️</span>
          <span class="confirmation-notes__section-title">异常情况说明</span>
        </div>
        <p class="confirmation-notes__section-hint">
          记录差异、退函、地址不详、拒绝回函等异常情况及初步判断原因
        </p>
        <el-input
          :model-value="data.note_exception"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="如：函证过程中发现X笔差异，差异原因为..."
          @update:model-value="(v) => $emit('update', 'note_exception', v)"
        />
      </div>

      <!-- 3. 未回函处理 -->
      <div class="confirmation-notes__section">
        <div class="confirmation-notes__section-header">
          <span class="confirmation-notes__section-icon">📭</span>
          <span class="confirmation-notes__section-title">未回函处理</span>
        </div>
        <p class="confirmation-notes__section-hint">
          记录截至审计报告日的未回函情况、催函措施及对审计结论的影响评估
        </p>
        <el-input
          :model-value="data.note_unreplied"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="如：截至报告日，共有X家未回函。已发送第二次催函，仍未收到回函的执行替代程序..."
          @update:model-value="(v) => $emit('update', 'note_unreplied', v)"
        />
      </div>

      <!-- 4. 替代程序说明 -->
      <div class="confirmation-notes__section">
        <div class="confirmation-notes__section-header">
          <span class="confirmation-notes__section-icon">🔄</span>
          <span class="confirmation-notes__section-title">替代程序说明</span>
        </div>
        <p class="confirmation-notes__section-hint">
          描述替代审计程序的具体内容（检查期后收款、合同、出库单等）及执行结果
        </p>
        <el-input
          :model-value="data.note_alternative"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="如：对未回函单位执行了以下替代程序：1.检查期后收款凭证 2.核对销售合同及出库单..."
          @update:model-value="(v) => $emit('update', 'note_alternative', v)"
        />
      </div>

      <!-- 5. 其他事项 -->
      <div class="confirmation-notes__section">
        <div class="confirmation-notes__section-header">
          <span class="confirmation-notes__section-icon">📝</span>
          <span class="confirmation-notes__section-title">其他事项</span>
        </div>
        <p class="confirmation-notes__section-hint">
          电子函证可靠性评价、关联方函证特殊考虑、舞弊风险评估等
        </p>
        <el-input
          :model-value="data.note_other"
          :disabled="readonly"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="如：本次函证采用纸质函证，回函地址与企业注册地一致，未发现可靠性存疑的回函..."
          @update:model-value="(v) => $emit('update', 'note_other', v)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { NotesData } from './confirmationTypes'

const props = defineProps<{
  data: NotesData
  readonly: boolean
  /** 用于 AI 生成的上下文 */
  wpId?: string
  projectId?: string
  wpCode?: string
  /** 函证统计数据（从父组件传入） */
  stats?: {
    totalCount: number
    totalAmount: number
    repliedCount: number
    matchedCount: number
    unrepliedCount: number
    coveragePct: number
    accountTypes: string[]
  }
}>()

const emit = defineEmits<{
  (e: 'update', field: string, value: any): void
}>()

const aiLoading = ref(false)

async function handleAiGenerate() {
  // 检查是否已有内容
  const hasContent = props.data.note_general || props.data.note_exception
    || props.data.note_unreplied || props.data.note_alternative || props.data.note_other
  if (hasContent) {
    try {
      await ElMessageBox.confirm(
        '当前已有部分内容，AI 预填充将覆盖所有空白字段（已填字段不覆盖）。是否继续？',
        '确认',
        { confirmButtonText: '继续', cancelButtonText: '取消', type: 'info' }
      )
    } catch {
      return
    }
  }

  aiLoading.value = true
  try {
    const payload = {
      project_id: props.projectId || '',
      wp_code: props.wpCode || 'D0-1',
      total_count: props.stats?.totalCount ?? 0,
      total_amount: props.stats?.totalAmount ?? 0,
      replied_count: props.stats?.repliedCount ?? 0,
      matched_count: props.stats?.matchedCount ?? 0,
      unreplied_count: props.stats?.unrepliedCount ?? 0,
      coverage_pct: props.stats?.coveragePct ?? 0,
      account_types: props.stats?.accountTypes ?? [],
      existing_notes: props.data,
    }

    const wpId = props.wpId || 'current'
    const { data } = await http.post(`/api/workpapers/${wpId}/ai-generate-notes`, payload)
    const notes = data?.notes || data?.data?.notes

    if (notes) {
      // 仅填充空白字段（不覆盖已有内容）
      const fields: (keyof NotesData)[] = ['note_general', 'note_exception', 'note_unreplied', 'note_alternative', 'note_other']
      let filled = 0
      for (const field of fields) {
        if (!props.data[field] && notes[field]) {
          emit('update', field, notes[field])
          filled++
        }
      }
      const source = data?.source || data?.data?.source
      const sourceLabel = source === 'llm' ? 'AI 生成' : '规则生成'
      ElMessage.success(`已${sourceLabel} ${filled} 项审计说明（${sourceLabel}仅供参考，请根据实际情况修改）`)
    } else {
      ElMessage.warning('未获取到生成内容，请稍后重试')
    }
  } catch (e: any) {
    console.error('[ConfirmationNotes] AI generate error:', e)
    ElMessage.error('生成失败：' + (e?.message || '服务暂不可用'))
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.confirmation-notes {
  padding: 4px 0;
}

.confirmation-notes__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}

.confirmation-notes__header-left {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.confirmation-notes__title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.confirmation-notes__subtitle {
  font-size: 12px;
  color: #909399;
}

.confirmation-notes__sections {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.confirmation-notes__section {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafbfc;
  transition: border-color 0.2s;
}

.confirmation-notes__section:focus-within {
  border-color: #7b61ff;
  background: #fff;
}

.confirmation-notes__section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.confirmation-notes__section-icon {
  font-size: 14px;
}

.confirmation-notes__section-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
}

.confirmation-notes__section-hint {
  font-size: 11px;
  color: #909399;
  margin: 0 0 6px 0;
  line-height: 1.5;
}

.confirmation-notes__section :deep(.el-textarea__inner) {
  border: none;
  background: transparent;
  padding: 4px 0;
  font-size: var(--wp-font-size, 13px);
  box-shadow: none;
}

.confirmation-notes__section :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}
</style>
