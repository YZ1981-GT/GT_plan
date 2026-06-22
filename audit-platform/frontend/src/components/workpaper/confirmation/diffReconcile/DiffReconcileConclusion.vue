<template>
  <div class="diff-reconcile-conclusion">
    <!-- 审计说明 -->
    <div class="diff-reconcile-conclusion__section">
      <div class="diff-reconcile-conclusion__title-row">
        <h4 class="diff-reconcile-conclusion__title">审计说明</h4>
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
        <el-form-item>
          <template #label>
            <span>差异总体情况说明</span>
            <span class="diff-reconcile-conclusion__hint">概述差异笔数、金额、查明程度和主要原因分布</span>
          </template>
          <el-input
            :model-value="auditNote.note_general"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="readonly"
            placeholder="如：本次函证共发现X笔差异，差异净额合计XX元。其中时间性差异X笔（占比XX%），记账差异X笔，未达账项X笔。所有差异已查明原因。"
            @input="(val: string) => $emit('update-note', 'note_general', val)"
          />
        </el-form-item>
        <el-form-item>
          <template #label>
            <span>调整处理说明</span>
            <span class="diff-reconcile-conclusion__hint">说明哪些差异已做调整、哪些无需调整及理由</span>
          </template>
          <el-input
            :model-value="auditNote.note_adjustment"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="readonly"
            placeholder="如：X笔记账差异已建议被审计单位调整（AJE编号XXX）；X笔时间性差异为在途款项，无需调整。"
            @input="(val: string) => $emit('update-note', 'note_adjustment', val)"
          />
        </el-form-item>
        <el-form-item>
          <template #label>
            <span>其他事项</span>
            <span class="diff-reconcile-conclusion__hint">如有超重要性差异、管理层解释、后续跟踪计划等</span>
          </template>
          <el-input
            :model-value="auditNote.note_other"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="readonly"
            placeholder="如：X笔差异超过实际执行重要性，已扩大替代程序范围（详见D0-5）。"
            @input="(val: string) => $emit('update-note', 'note_other', val)"
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- 审计结论 -->
    <div class="diff-reconcile-conclusion__section">
      <h4 class="diff-reconcile-conclusion__title">审计结论</h4>
      <div class="diff-reconcile-conclusion__options">
        <el-radio-group
          :model-value="conclusion.conclusion_type"
          :disabled="readonly"
          @change="(val: string) => $emit('update-conclusion', 'conclusion_type', val)"
        >
          <div class="diff-reconcile-conclusion__option" :class="{ 'is-active': conclusion.conclusion_type === 'A' }">
            <el-radio value="A">
              <span class="diff-reconcile-conclusion__tag diff-reconcile-conclusion__tag--success">A</span>
              差异已全部查明并调整
            </el-radio>
            <p class="diff-reconcile-conclusion__option-desc">所有差异原因已查明，需调整项已编制 AJE，不影响审计意见</p>
          </div>
          <div class="diff-reconcile-conclusion__option" :class="{ 'is-active': conclusion.conclusion_type === 'B' }">
            <el-radio value="B">
              <span class="diff-reconcile-conclusion__tag diff-reconcile-conclusion__tag--warn">B</span>
              部分差异待确认
            </el-radio>
            <p class="diff-reconcile-conclusion__option-desc">部分差异原因待进一步核实或等待对方补充资料</p>
          </div>
          <div class="diff-reconcile-conclusion__option" :class="{ 'is-active': conclusion.conclusion_type === 'C' }">
            <el-radio value="C">
              <span class="diff-reconcile-conclusion__tag diff-reconcile-conclusion__tag--danger">C</span>
              存在重大未调差异
            </el-radio>
            <p class="diff-reconcile-conclusion__option-desc">差异金额超过重要性水平，需扩大审计范围或考虑对意见的影响</p>
          </div>
        </el-radio-group>
      </div>

      <el-input
        v-if="conclusion.conclusion_type === 'B' || conclusion.conclusion_type === 'C'"
        :model-value="conclusion.conclusion_text"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="readonly"
        :placeholder="conclusion.conclusion_type === 'B' ? '说明待确认差异的金额、涉及科目及预计确认时间' : '说明差异金额、影响范围及后续审计措施'"
        style="margin-top: 8px"
        @input="(val: string) => $emit('update-conclusion', 'conclusion_text', val)"
      />

      <!-- 未决事项提示 -->
      <el-alert
        v-if="hasUnresolved"
        title="存在未决事项：部分差异未分类或未填写应对措施，请确认后再出具最终结论"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top: 8px"
      />
    </div>

    <!-- 重要性配置 -->
    <div class="diff-reconcile-conclusion__section">
      <h4 class="diff-reconcile-conclusion__title">
        重要性配置
        <el-tooltip content="用于判断差异是否超过实际执行重要性（PM），超标差异将标红预警" placement="top">
          <el-icon :size="14" style="margin-left:4px;cursor:help"><InfoFilled /></el-icon>
        </el-tooltip>
      </h4>
      <p class="diff-reconcile-conclusion__hint" style="margin:0 0 8px">
        默认从 B15 重要性水平底稿自动获取，也可手动覆盖。差异金额超过此值的行将标红提示。
      </p>
      <el-form :inline="true" size="small">
        <el-form-item label="实际执行重要性">
          <el-input-number
            :model-value="materialityConfig.performance_materiality"
            :disabled="readonly"
            :controls="false"
            :precision="2"
            :min="0"
            placeholder="从 B15 自动获取"
            style="width: 180px"
            @change="(val: number) => $emit('update-materiality', val)"
          />
          <span style="margin-left:6px;font-size:12px;color:#909399">元</span>
        </el-form-item>
        <el-form-item>
          <el-tag v-if="materialityConfig.source === 'auto'" type="primary" size="small">自动取值</el-tag>
          <el-tag v-else-if="materialityConfig.is_overridden" type="warning" size="small">手动覆盖</el-tag>
          <el-tag v-else type="info" size="small">未配置</el-tag>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { DiffAuditNote, DiffConclusion, MaterialityConfig } from './diffReconcileTypes'

const props = defineProps<{
  auditNote: DiffAuditNote
  conclusion: DiffConclusion
  materialityConfig: MaterialityConfig
  readonly: boolean
  hasUnresolved: boolean
  /** 从父组件传入的统计数据，用于 AI 填充 */
  totalCount?: number
  differenceNet?: number
  differenceAbs?: number
  adjustmentCount?: number
  analyzedRate?: number
}>()

const emit = defineEmits<{
  (e: 'update-note', field: string, value: string): void
  (e: 'update-conclusion', field: string, value: any): void
  (e: 'update-materiality', value: number): void
}>()

const aiLoading = ref(false)

function handleAiFill() {
  aiLoading.value = true
  try {
    const total = props.totalCount ?? 0
    const netAmt = props.differenceNet ?? 0
    const absAmt = props.differenceAbs ?? 0
    const adjCount = props.adjustmentCount ?? 0
    const rate = props.analyzedRate ?? 0

    // 规则生成审计说明（基于当前数据）
    const general = total > 0
      ? `本次函证差异调节共涉及 ${total} 笔差异，差异净额合计 ${netAmt.toLocaleString()} 元（绝对值合计 ${absAmt.toLocaleString()} 元）。已分析率 ${rate}%。${rate >= 100 ? '所有差异原因已查明。' : '部分差异尚待分类确认。'}`
      : '本次函证未发现差异，账面记录与回函金额一致。'

    const adjustment = adjCount > 0
      ? `共 ${adjCount} 笔差异标记为需调整，已建议被审计单位进行账务调整。未标记调整的差异为时间性差异或金额低于重要性水平，经评估无需调整。`
      : '所有差异均为时间性差异或金额不重大，无需进行审计调整。'

    const other = props.hasUnresolved
      ? '注意：尚有未分类差异待处理，请在差异明细表中完善差异类型后再出具最终结论。'
      : '无其他需要关注事项。'

    // 仅填充空白字段
    if (!props.auditNote.note_general) emit('update-note', 'note_general', general)
    if (!props.auditNote.note_adjustment) emit('update-note', 'note_adjustment', adjustment)
    if (!props.auditNote.note_other) emit('update-note', 'note_other', other)

    ElMessage.success('已根据差异数据生成审计说明（仅供参考，请根据实际情况修改）')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.diff-reconcile-conclusion__section {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.diff-reconcile-conclusion__title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.diff-reconcile-conclusion__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
}

.diff-reconcile-conclusion__hint {
  font-size: 11px;
  color: #909399;
  font-weight: 400;
  margin-left: 8px;
}

/* 审计结论卡片式选项 */
.diff-reconcile-conclusion__options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diff-reconcile-conclusion__option {
  padding: 8px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
  transition: all 0.2s;
}

.diff-reconcile-conclusion__option.is-active {
  border-color: #7b61ff;
  background: #f8f5ff;
}

.diff-reconcile-conclusion__option .el-radio {
  font-weight: 500;
}

.diff-reconcile-conclusion__tag {
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

.diff-reconcile-conclusion__tag--success { background: #67c23a; }
.diff-reconcile-conclusion__tag--warn { background: #e6a23c; }
.diff-reconcile-conclusion__tag--danger { background: #f56c6c; }

.diff-reconcile-conclusion__option-desc {
  font-size: 11px;
  color: #909399;
  margin: 2px 0 0 24px;
  line-height: 1.4;
}
</style>
