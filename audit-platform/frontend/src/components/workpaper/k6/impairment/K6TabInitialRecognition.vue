<template>
  <div class="k6-tab-initial-recognition">
    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step">
          <span class="step-num">①</span>
          <span>逐条核对CAS42五条件（满足/不满足/不适用）</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">②</span>
          <span>全部满足 → 可分类为持有待售；任一不满足 → 不得分类</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">③</span>
          <span>AI辅助生成分类判断结论，填写审计证据</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p><strong>CAS42 持有待售分类条件：</strong>企业主要通过出售而非持续使用一项非流动资产或处置组收回其账面价值的，应当将其划分为持有待售类别。划分为持有待售类别应当<strong>同时满足</strong>以下五个条件。企业对于划分为持有待售类别的非流动资产，应当调整预计净残值，使其反映公允价值减去出售费用后的净额。</p>
    </div>

    <!-- ═══ 分类判断结果 Banner ═══ -->
    <div v-if="isFullyEvaluated" class="classification-banner" :class="classificationResult === 'classified' ? 'banner-success' : 'banner-danger'">
      <el-icon v-if="classificationResult === 'classified'" :size="20"><CircleCheckFilled /></el-icon>
      <el-icon v-else :size="20"><CircleCloseFilled /></el-icon>
      <span class="banner-text">
        {{ classificationResult === 'classified' ? '可分类为持有待售' : '不满足分类条件' }}
      </span>
    </div>

    <!-- ═══ 不满足条件红色列表 ═══ -->
    <el-alert
      v-if="unmetConditions.length > 0"
      type="error"
      :closable="false"
      show-icon
      class="unmet-alert"
    >
      <template #title>
        {{ unmetConditions.length }} 项条件不满足：
        <span v-for="(c, idx) in unmetConditions" :key="c.index">
          {{ c.label }}{{ idx < unmetConditions.length - 1 ? '、' : '' }}
        </span>
      </template>
    </el-alert>

    <!-- ═══ CAS42五条件核对清单 ═══ -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">K6-4 CAS42五条件核对清单</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" circle @click="openReview('K6-4')">💬</el-button>
          </div>
        </div>
      </template>

      <div class="conditions-list">
        <div
          v-for="cond in conditions"
          :key="cond.index"
          class="condition-card"
          :class="{
            'card-met': cond.status === 'met',
            'card-not-met': cond.status === 'not_met',
            'card-na': cond.status === 'na',
          }"
        >
          <div class="condition-header">
            <span class="condition-label">{{ cond.label }}</span>
            <el-radio-group
              :model-value="cond.status"
              :disabled="isReadonly"
              size="small"
              @change="(v: any) => updateConditionStatus(cond.index, v)"
            >
              <el-radio-button value="met">满足</el-radio-button>
              <el-radio-button value="not_met">不满足</el-radio-button>
              <el-radio-button value="na">不适用</el-radio-button>
            </el-radio-group>
          </div>
          <p class="condition-desc">{{ cond.description }}</p>
          <el-input
            :model-value="cond.evidence"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="isReadonly"
            placeholder="审计证据/说明（如：已查阅董事会决议第XX号、已核对转让协议…）"
            @blur="(e: FocusEvent) => updateConditionEvidence(cond.index, (e.target as HTMLTextAreaElement)?.value ?? '')"
          />
        </div>
      </div>

      <!-- 完成度统计 -->
      <div class="progress-bar">
        <span>评估进度: {{ evaluatedCount }} / 5</span>
        <el-tag v-if="isFullyEvaluated" type="success" size="small">全部完成</el-tag>
        <el-tag v-else type="info" size="small">进行中</el-tag>
      </div>
    </el-card>

    <!-- ═══ 审计结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>分类判断结论</span>
          <el-button size="small" type="primary" link :loading="aiLoading" @click="handleAiConclusion">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="classificationConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写持有待售分类判断结论（如：经逐条核对CAS42第六条规定的五项分类条件，该资产/处置组满足/不满足持有待售分类条件…）"
        @blur="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>CAS42第六条：企业主要通过出售而非持续使用一项非流动资产或处置组收回其账面价值的，应当将其划分为持有待售类别</li>
        <li>五个条件必须<strong>同时满足</strong>才能分类为持有待售</li>
        <li>"不适用"视同满足（不影响分类判断）</li>
        <li>条件④"一年内完成"有例外情形：非企业自身原因导致延期且企业已取得足够证据表明仍承诺出售</li>
        <li>分类后应按公允价值减去出售费用后的净额与账面价值孰低计量（跳转K6-5减值测试）</li>
        <li>AI辅助可根据已填写的条件状态自动生成结论段落</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabInitialRecognition.vue — K6-4 初始确认（CAS42五条件清单）
 *
 * CAS42五条件核对清单 + 分类判断结果Banner + AI辅助
 * 全部满足 → 绿色"可分类为持有待售"
 * 任一不满足 → 红色"不满足分类条件"
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.4
 * Requirements: 4.1-4.5
 */
import { ref, computed, inject } from 'vue'
import { MagicStick, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK6InitialRecognition } from '../../composables/useK6InitialRecognition'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

function saveResponse(field: string, value: any): Promise<void> {
  emit('save', field, value)
  return Promise.resolve()
}

const {
  conditions,
  classificationResult,
  classificationConclusion,
  isFullyEvaluated,
  unmetConditions,
  updateConditionStatus,
  updateConditionEvidence,
  saveConclusion,
  setAiConclusion,
} = useK6InitialRecognition({
  allResponses: allResponsesRef,
  saveResponse,
})

// ─── Local State ─────────────────────────────────────────────────────────────

const aiLoading = ref(false)

const evaluatedCount = computed(() => conditions.value.filter(c => c.status !== '').length)

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

async function handleAiGenerate() {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const context = conditions.value.map(c =>
      `${c.label}: ${c.status === 'met' ? '满足' : c.status === 'not_met' ? '不满足' : c.status === 'na' ? '不适用' : '未评估'}${c.evidence ? ` (证据: ${c.evidence})` : ''}`
    ).join('\n')
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'classification-conclusion',
      context,
      prompt: '根据CAS42五条件核对结果，生成持有待售分类判断结论',
      existingContent: classificationConclusion.value,
    })
    const text = resp?.data?.content || resp?.data?.text || resp?.content || ''
    if (text) {
      setAiConclusion(text)
      ElMessage.success('AI结论已生成')
    }
  } catch (e: any) {
    ElMessage.error('AI生成失败: ' + (e?.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

async function handleAiConclusion() {
  await handleAiGenerate()
}

// ─── Review ──────────────────────────────────────────────────────────────────

function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.k6-tab-initial-recognition {
  padding: 16px;
  font-size: 13px;
}

/* 蓝色渐变引导区 */
.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border: 1px solid #b3d8fd;
}
.guidance-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}
.guidance-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #1d3557;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

/* 琥珀色方法论上下文 */
.methodology-context {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12.5px;
  color: #78350f;
  line-height: 1.6;
}

/* 分类判断结果 Banner */
.classification-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 15px;
  font-weight: 600;
}
.banner-success {
  background: #ecfdf5;
  border: 1px solid #6ee7b7;
  color: #065f46;
}
.banner-danger {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
}
.banner-text {
  letter-spacing: 0.5px;
}

/* 不满足条件提示 */
.unmet-alert {
  margin-bottom: 16px;
}

/* 条件清单 */
.conditions-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.condition-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px 16px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.condition-card.card-met {
  border-color: #6ee7b7;
  background: #f0fdf4;
}
.condition-card.card-not-met {
  border-color: #fca5a5;
  background: #fef2f2;
}
.condition-card.card-na {
  border-color: #d1d5db;
  background: #f9fafb;
}
.condition-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.condition-label {
  font-weight: 600;
  font-size: 13.5px;
  color: #1f2937;
}
.condition-desc {
  font-size: 12.5px;
  color: #6b7280;
  margin: 4px 0 10px 0;
  line-height: 1.5;
}

/* 进度统计 */
.progress-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid #f0f0f0;
  font-size: 13px;
  color: #6b7280;
}

/* 块卡片 */
.block-card {
  margin-bottom: 16px;
}

/* Section标题 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
}
.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 审计结论卡 */
.audit-note-card {
  margin-bottom: 16px;
}

/* 编制提示 */
.edit-tips {
  margin-top: 16px;
  font-size: 12px;
  color: #6b7280;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 14px;
}
.edit-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #374151;
}
.edit-tips ul {
  margin: 8px 0 0 0;
  padding-left: 18px;
  line-height: 1.8;
}
</style>
