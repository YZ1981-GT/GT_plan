<template>
  <div class="m1-tab-dividend-check">
    <!-- ═══ 完成率进度条 ═══ -->
    <div class="completion-bar">
      <span class="completion-label">检查完成度</span>
      <el-progress
        :percentage="completionRate"
        :stroke-width="14"
        :format="() => `${passedCount + failedCount + naCount}/${checkItems.length}`"
        :color="completionRate === 100 ? '#67C23A' : '#409EFF'"
        style="flex: 1"
      />
    </div>

    <!-- ═══ 核对清单（8 check items） ═══ -->
    <el-card shadow="never" class="check-section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">核对清单</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleReview('M1-6-checklist')">
              <el-icon><ChatDotSquare /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>

      <div
        v-for="item in checkItems"
        :key="item.id"
        class="check-item"
      >
        <div class="check-item-row">
          <div class="check-item-title">{{ item.title }}</div>
          <div class="check-item-controls">
            <el-select
              :model-value="item.status"
              size="small"
              placeholder="请选择"
              :disabled="isReadonly"
              style="width: 110px"
              @change="(val: string) => updateCheckStatus(item.id, val as any)"
            >
              <el-option
                v-for="opt in CHECK_STATUS_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              >
                <span :style="{ color: opt.color }">{{ opt.label }}</span>
              </el-option>
            </el-select>
          </div>
        </div>
        <div class="check-item-remark">
          <el-input
            :model-value="item.remark"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            size="small"
            placeholder="检查备注..."
            :readonly="isReadonly"
            @input="(val: string) => updateCheckRemark(item.id, val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ AI辅助文本分析区（每个section标题行右侧有AI按钮） ═══ -->
    <el-card
      v-for="section in aiSections"
      :key="section.sectionId"
      shadow="never"
      class="ai-section-card"
    >
      <template #header>
        <div class="card-header">
          <span class="card-title">{{ section.title }}</span>
          <div class="card-header-right">
            <el-button
              size="small"
              :loading="section.isGenerating"
              @click="handleAI(section.sectionId)"
            >
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="handleReview(`M1-6-${section.sectionId}`)">
              <el-icon><ChatDotSquare /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="section.content"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :placeholder="`请输入${section.title}内容...`"
        :readonly="isReadonly"
        @input="(val: string) => updateAiSectionContent(section.sectionId, val)"
      />
    </el-card>

    <!-- ═══ 审计结论区（el-card包裹，findings + conclusion textareas autosize） ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">审计结论</span>
          <div class="card-header-right">
            <el-button size="small" @click="handleAI('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" @click="handleReview('M1-6-conclusion')">
              <el-icon><ChatDotSquare /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>

      <div class="conclusion-fields">
        <div class="field-group">
          <label class="field-label">审计发现</label>
          <el-input
            :model-value="conclusion.findings"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            placeholder="记录应付股利检查中发现的重大事项、异常情况..."
            :readonly="isReadonly"
            @input="(val: string) => updateConclusion('findings', val)"
          />
        </div>
        <div class="field-group">
          <label class="field-label">最终结论</label>
          <el-input
            :model-value="conclusion.conclusion"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            placeholder="综合核对清单结果，对应付股利科目的真实性、完整性、准确性、分类发表结论..."
            :readonly="isReadonly"
            @input="(val: string) => updateConclusion('conclusion', val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐项完成核对清单，选择检查状态（待检查/通过/未通过/不适用）</li>
        <li>完整性重点：股东清册核对，确认所有应付股利均已入账</li>
        <li>准确性重点：宣告分配金额与董事会/股东大会决议核对一致</li>
        <li>外币股利汇率：核对期末即期汇率与M1-4外币测算表一致</li>
        <li>截止性：宣告日与实际入账期间匹配</li>
        <li>审计结论应综合各检查项结果及AI辅助分析内容</li>
        <li>所有未通过项必须填写备注，说明异常及后续处理</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabDividendCheck.vue — M1-6 应付股利（利润）检查表
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 4.5
 * Requirements: 6.1-6.2
 *
 * 功能：
 * - 核对清单（8 check items with status dropdown: 待检查/通过/未通过/不适用）
 * - 审计结论区（el-card wrapped, findings + conclusion textareas autosize）
 * - AI辅助: Each text section title has right-aligned AI button
 * - 完成率进度条
 * - Uses useM1DividendCheck composable
 * - Uses useM1FormData for persistence
 * - Props: wpId, projectId, isReadonly
 * - inject openReviewDialog for 复核按钮
 */
import { computed, inject, onMounted } from 'vue'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useM1FormData } from '../../../composables/useM1FormData'
import {
  useM1DividendCheck,
  CHECK_STATUS_OPTIONS,
} from '../../../composables/useM1DividendCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId?: string) => void) | null>('openReviewDialog', null)

// ─── FormData (persistence layer) ───────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── useM1DividendCheck composable ──────────────────────────────────────────

const {
  checkItems,
  aiSections,
  conclusion,
  completionRate,
  failedCount,
  passedCount,
  updateCheckStatus,
  updateCheckRemark,
  updateAiSectionContent,
  setAiSectionGenerating,
  updateConclusion,
} = useM1DividendCheck(formData)

// ─── 不适用项数（用于进度条分子） ───────────────────────────────────────────

const naCount = computed(() => {
  return checkItems.value.filter(item => item.status === 'na').length
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleAI(sectionId: string) {
  // AI辅助功能占位——后续集成AI生成
  setAiSectionGenerating(sectionId, false)
}

function handleReview(sectionId: string) {
  openReviewDialog?.(sectionId)
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.m1-tab-dividend-check { padding: 12px; font-size: 13px; }

/* 完成度进度条 */
.completion-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding: 10px 16px; background: linear-gradient(135deg, #f8f9fe, #f0f4ff); border-radius: 6px; border: 1px solid #e4e7ed; }
.completion-label { font-size: 13px; font-weight: 500; color: #303133; white-space: nowrap; }

/* Section Cards */
.check-section-card { margin-bottom: 16px; }
.ai-section-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.card-header-right { display: flex; align-items: center; gap: 8px; }

/* 检查项 */
.check-item { padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
.check-item:last-child { border-bottom: none; }
.check-item-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
.check-item-title { font-size: 13px; color: #303133; line-height: 1.5; flex: 1; }
.check-item-controls { flex-shrink: 0; }
.check-item-remark { padding-left: 0; }

/* 结论区 */
.conclusion-card { margin-bottom: 16px; border: 1px solid #d9ecff; }
.conclusion-fields { display: flex; flex-direction: column; gap: 16px; }
.field-group { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 13px; font-weight: 500; color: #606266; }

/* 编制提示 */
.m1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.m1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }

:deep(.el-table) { font-size: 13px; }
</style>
