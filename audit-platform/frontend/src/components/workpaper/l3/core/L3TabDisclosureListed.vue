<template>
  <div class="l3-tab-disclosure-listed">
    <!-- ═══ 返回目录 + 标题 + AI辅助 ═══ -->
    <div class="disclosure-header">
      <div class="disclosure-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">
          ← 返回目录
        </el-button>
        <h3 class="disclosure-title">附注披露信息核对（上市公司）</h3>
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
        <strong>上市公司长期借款附注披露要求：</strong>
        按借款类型（信用/保证/抵押/质押）分类列示长期借款余额，
        包含期初余额、本期增加、本期减少、期末余额、利率区间、到期日等。
        需单独披露一年内到期的长期借款金额及逾期借款情况。
        披露数据应与审定表L3-1交叉验证一致。
      </div>
    </div>

    <!-- ═══ Section: 长期借款明细 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">一、长期借款明细</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('detail')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.detail"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 12 }"
        placeholder="按借款类型分类列示长期借款余额明细：包括借款银行、币种、年利率、起始日、到期日、期初余额、期末余额、一年内到期金额等..."
        :disabled="isReadonly"
        @input="handleSectionChange('detail')"
      />
    </div>

    <!-- ═══ Section: 利率说明 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">二、利率说明</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('rate')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.rate"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="长期借款利率区间说明：如固定利率X%~Y%、浮动利率LPR+X基点等..."
        :disabled="isReadonly"
        @input="handleSectionChange('rate')"
      />
    </div>

    <!-- ═══ Section: 担保说明 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">三、担保说明</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('guarantee')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.guarantee"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="抵押/质押/保证借款担保情况：担保物名称、账面价值、担保比例、保证人等..."
        :disabled="isReadonly"
        @input="handleSectionChange('guarantee')"
      />
    </div>

    <!-- ═══ Section: 一年内到期说明 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">四、一年内到期说明</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('currentPortion')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.currentPortion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="一年内到期的长期借款明细：已重分类至一年内到期的非流动负债的金额、对应合同及到期安排..."
        :disabled="isReadonly"
        @input="handleSectionChange('currentPortion')"
      />
    </div>

    <!-- ═══ Section: 逾期说明 ═══ -->
    <div class="disclosure-section">
      <div class="section-header">
        <span class="section-title">五、逾期说明</span>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="handleSectionAi('overdue')"
        >
          🤖 AI辅助
        </el-button>
      </div>
      <el-input
        v-model="sections.overdue"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="逾期长期借款情况（如有）：逾期金额、逾期天数、逾期原因及后续安排..."
        :disabled="isReadonly"
        @input="handleSectionChange('overdue')"
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
        <li><strong>披露范围</strong>：上市公司须分类列示长期借款明细，包含利率、担保、到期日等</li>
        <li><strong>一年内到期</strong>：将于资产负债表日起一年内到期的部分单独列示</li>
        <li><strong>逾期披露</strong>：逾期未偿还的长期借款须单独披露金额及原因</li>
        <li><strong>利率区间</strong>：同类借款利率不一致时须披露利率区间</li>
        <li><strong>担保物</strong>：抵押/质押借款须披露担保物及评估价值</li>
        <li><strong>交叉验证</strong>：附注合计应与审定表L3-1期末余额一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L3TabDisclosureListed — 附注披露信息核对（上市公司）
 *
 * 功能：
 * - 上市公司长期借款附注模板
 * - textarea sections: 长期借款明细/利率说明/担保说明/一年内到期说明/逾期说明
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
  detail: '',
  rate: '',
  guarantee: '',
  currentPortion: '',
  overdue: '',
})

const conclusionText = ref('')

// ─── Section Key Map ─────────────────────────────────────────────────────────

const SECTION_KEYS: Record<string, string> = {
  detail: 'L3-disclosure-listed-detail',
  rate: 'L3-disclosure-listed-rate',
  guarantee: 'L3-disclosure-listed-guarantee',
  currentPortion: 'L3-disclosure-listed-current-portion',
  overdue: 'L3-disclosure-listed-overdue',
}

const CONCLUSION_KEY = 'L3-disclosure-listed-conclusion'

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
  // 从 allResponses 中恢复
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
.l3-tab-disclosure-listed {
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

/* ─── 表格统一13px字体 ─── */
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
