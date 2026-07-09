<template>
  <div class="l3-tab-disclosure-soe">
    <!-- ═══ 返回目录 + 标题 + AI辅助 ═══ -->
    <div class="disclosure-header">
      <div class="disclosure-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="disclosure-title">附注披露信息核对（国有企业）</h3>
      </div>
      <div class="disclosure-header-right">
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleAiAssist"
        >
          🤖 AI辅助
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业长期借款附注披露要求：</strong>
        国有企业按借款构成分类列示长期借款余额，
        包含利率区间、担保情况、到期分布等信息。
        国企版本侧重资金来源合规性和还款计划安排。
        披露数据应与审定表L3-1交叉验证一致。
      </div>
    </div>

    <!-- ═══ 企业类型标识 ═══ -->
    <div class="entity-type-badge">
      <el-tag type="info" effect="dark" size="small">
        国有企业版
      </el-tag>
      <span class="entity-type-hint">（系统根据企业类型自动切换模板）</span>
    </div>

    <!-- ═══ Section: 长期借款构成 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">一、长期借款构成</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('composition')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.composition"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        placeholder="按借款构成分类列示：信用借款/保证借款/抵押借款/质押借款各期初期末余额、增减变动，按银行及合同号列示..."
        :disabled="isReadonly"
        @input="handleSectionChange('composition')"
      />
    </div>

    <!-- ═══ Section: 利率区间 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">二、利率区间</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('rateRange')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.rateRange"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="长期借款利率区间：固定利率X%~Y%、浮动利率LPR+X基点~LPR+Y基点，按类型列示..."
        :disabled="isReadonly"
        @input="handleSectionChange('rateRange')"
      />
    </div>

    <!-- ═══ Section: 担保情况 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">三、担保情况</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('guaranteeStatus')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.guaranteeStatus"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="担保情况说明：抵押物/质押物名称及账面价值、保证人资质及担保额度、信用借款额度等..."
        :disabled="isReadonly"
        @input="handleSectionChange('guaranteeStatus')"
      />
    </div>

    <!-- ═══ Section: 到期分布 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">四、到期分布</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('maturityDistribution')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.maturityDistribution"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="到期分布情况：1年内到期/1-2年/2-3年/3-5年/5年以上各期金额分布，还款计划安排..."
        :disabled="isReadonly"
        @input="handleSectionChange('maturityDistribution')"
      />
    </div>

    <!-- ═══ 审计结论 ═══ -->
    <div class="conclusion-section">
      <el-card shadow="never">
        <template #header>
          <div class="conclusion-header">
            <span>审计结论</span>
            <el-button
              size="small"
              :disabled="isReadonly"
              @click="handleAiConclusion"
            >
              🤖 AI生成结论
            </el-button>
          </div>
        </template>
        <el-input
          v-model="conclusionText"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入附注披露核对结论..."
          :disabled="isReadonly"
          @input="handleConclusionChange"
        />
      </el-card>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>国企特点</strong>：国有企业附注侧重借款构成、利率区间、担保情况和到期分布</li>
        <li><strong>到期分布</strong>：按1年内/1-2年/2-3年/3-5年/5年以上分段列示</li>
        <li><strong>资金合规</strong>：关注借款用途是否符合国有资产管理相关规定</li>
        <li><strong>交叉验证</strong>：附注合计应与审定表L3-1期末余额一致</li>
        <li><strong>企业类型</strong>：系统根据项目企业类型自动选择上市/国企版本</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabDisclosureSoe — 附注披露信息核对（国有企业）
 *
 * 功能：
 * - 国企长期借款附注模板
 * - textarea sections: 长期借款构成/利率区间/担保情况/到期分布
 * - 每个section标题行右侧AI辅助按钮
 * - subscribe 'substantive:adjudicated' 事件刷新
 * - inject l3FormData
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 4.7
 * Requirements: 9.2
 */
import { inject, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'
import { eventBus } from '@/utils/eventBus'

// ─── Props / Emits ───────────────────────────────────────────────────────────

defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject formData ─────────────────────────────────────────────────────────

const formData = inject<ReturnType<typeof useL3FormData>>('l3FormData')!

// ─── State ───────────────────────────────────────────────────────────────────

const sections = reactive({
  composition: '',
  rateRange: '',
  guaranteeStatus: '',
  maturityDistribution: '',
})

const conclusionText = ref('')

// ─── Section Key Map ─────────────────────────────────────────────────────────

const SECTION_KEYS: Record<string, string> = {
  composition: 'L3-disclosure-soe-composition',
  rateRange: 'L3-disclosure-soe-rate-range',
  guaranteeStatus: 'L3-disclosure-soe-guarantee-status',
  maturityDistribution: 'L3-disclosure-soe-maturity-distribution',
}

const CONCLUSION_KEY = 'L3-disclosure-soe-conclusion'

// ─── 字段变更保存 ────────────────────────────────────────────────────────────

function handleSectionChange(key: keyof typeof sections) {
  const itemId = SECTION_KEYS[key]
  if (!itemId) return
  formData.debouncedSave(itemId, { remark: sections[key] || null })
}

function handleConclusionChange() {
  formData.debouncedSave(CONCLUSION_KEY, { remark: conclusionText.value || null })
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中...')
}

function handleSectionAi(section: string) {
  ElMessage.info(`AI辅助（${section}）功能开发中...`)
}

function handleAiConclusion() {
  ElMessage.info('AI生成结论功能开发中...')
}

// ─── EventBus 订阅：审定变更后刷新 ──────────────────────────────────────────

function handleAdjudicatedRefresh() {
  loadDisclosureData()
}

onMounted(() => {
  eventBus.on('substantive:adjudicated', handleAdjudicatedRefresh)
  loadDisclosureData()
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicatedRefresh)
})

// ─── 加载数据 ────────────────────────────────────────────────────────────────

function loadDisclosureData() {
  const responses = formData.allResponses.value

  for (const [key, itemId] of Object.entries(SECTION_KEYS)) {
    const resp = responses.get(itemId)
    if (resp?.remark) {
      ;(sections as any)[key] = resp.remark
    }
  }

  const conclusionResp = responses.get(CONCLUSION_KEY)
  if (conclusionResp?.remark) {
    conclusionText.value = conclusionResp.remark
  }
}
</script>

<style scoped>
.l3-tab-disclosure-soe {
  padding: 12px;
  font-size: 13px;
}

/* ─── 头部 ─── */
.disclosure-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.disclosure-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.disclosure-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.disclosure-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 企业类型标识 ─── */
.entity-type-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.entity-type-hint {
  font-size: 12px;
  color: #909399;
}

/* ─── Section 区块 ─── */
.disclosure-section {
  margin-bottom: 18px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: #f5f7fa;
  border-radius: 4px;
}

.section-title {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
}

/* ─── 结论区 ─── */
.conclusion-section {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
}

/* ─── textarea统一13px字体 ─── */
:deep(.el-textarea__inner) {
  font-size: 13px;
  line-height: 1.6;
}

/* ─── 编制提示折叠 ─── */
.l3-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.l3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
