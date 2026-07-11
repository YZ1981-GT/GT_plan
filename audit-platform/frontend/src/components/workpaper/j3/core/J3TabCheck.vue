<template>
  <div class="j3-tab-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：依据 CAS 11《股份支付》逐项核验授予条件、验证 Black-Scholes 定价参数（波动率、无风险利率、期限等）的合理性，形成股份支付会计处理的检查结论。
      </template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="check-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:J3-1" :context-project-id="props.projectId" /></span>
      <el-tag size="small" type="info">共 {{ checkData.sections.value.length }} 检查区</el-tag>
    </div>

    <!-- 顶部引导 -->
    <div class="guide-banner">
      <div class="guide-step"><span class="step-num">①</span> 逐项核验授予条件</div>
      <div class="guide-step"><span class="step-num">②</span> 验证BS参数合理性</div>
      <div class="guide-step"><span class="step-num">③</span> 形成检查结论</div>
    </div>

    <!-- BS参数验证面板 -->
    <el-card shadow="never" class="bs-panel">
      <template #header>
        <div class="section-header">
          <span style="font-weight: 600">Black-Scholes 参数验证</span>
          <el-button size="small" type="primary" plain @click="handleAIAnalysis">
            🤖 AI 合理性分析
          </el-button>
        </div>
      </template>
      <div class="bs-params-grid">
        <div v-for="check in checkData.bsParamChecks.value" :key="check.param" class="bs-param-item">
          <div class="param-label">{{ check.label }}</div>
          <el-input-number
            v-model="checkData.bsParams.value[check.param as keyof typeof checkData.bsParams.value]"
            :precision="4"
            :step="0.01"
            size="small"
            :disabled="isReadonly"
          />
          <el-tag
            v-if="check.warning"
            type="warning"
            size="small"
            style="margin-left: 8px"
          >
            {{ check.warning }}
          </el-tag>
          <el-tag
            v-else-if="check.isReasonable"
            type="success"
            size="small"
            style="margin-left: 8px"
          >
            合理
          </el-tag>
        </div>
      </div>
      <div v-if="bsResult !== null" class="bs-result">
        <span class="bs-result-label">BS定价结果：</span>
        <span class="bs-result-value">{{ bsResult.toFixed(4) }} 元/份</span>
      </div>
    </el-card>

    <!-- 段落型检查区 -->
    <div v-for="section in checkData.sections.value" :key="section.id" class="check-section">
      <el-card shadow="never">
        <template #header>
          <div class="section-header">
            <span style="font-weight: 600; font-size: 13px">{{ section.title }}</span>
            <el-button size="small" plain @click="handleSectionAI(section.id)">
              🤖 AI辅助
            </el-button>
          </div>
        </template>

        <!-- 方法论上下文 -->
        <div class="methodology-context">
          <span>{{ section.description }}</span>
        </div>

        <!-- 逐项检查 -->
        <div v-for="item in section.items" :key="item.id" class="check-item">
          <div class="item-label">{{ item.label }}</div>
          <div class="item-controls">
            <el-input
              v-model="item.value"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="检查情况..."
              size="small"
              :disabled="isReadonly"
            />
            <el-select
              v-model="item.conclusion"
              placeholder="结论"
              size="small"
              style="width: 100px; margin-top: 4px"
              :disabled="isReadonly"
            >
              <el-option label="符合" value="符合" />
              <el-option label="不符合" value="不符合" />
              <el-option label="不适用" value="不适用" />
            </el-select>
          </div>
        </div>
      </el-card>
    </div>

    <!-- IPO面板（条件显示） -->
    <el-card v-if="showIPOPanel" shadow="never" class="ipo-panel">
      <template #header>
        <span style="font-weight: 600; color: #e6a23c">⚠️ IPO审计重点提示</span>
      </template>
      <ul class="ipo-highlights">
        <li v-for="(h, idx) in ipoHighlights" :key="idx">{{ h }}</li>
      </ul>
    </el-card>

    <!-- 整体结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span style="font-weight: 600">检查结论</span></template>
      <el-tag :type="conclusionType" size="default">{{ checkData.overallConclusion.value }}</el-tag>
      <el-input
        v-model="conclusionNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="审计结论说明..."
        style="margin-top: 12px"
        :disabled="isReadonly"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 11《股份支付》，须核验授予日、行权价、等待期、可行权条件（服务/业绩条件）等关键要素。</p>
        <p>2. Black-Scholes 参数中，波动率应参考同行业可比公司历史波动率，无风险利率取等待期匹配的国债收益率。</p>
        <p>3. 上市公司/拟 IPO 企业须重点关注股份支付费用对净利润的影响及信息披露充分性。</p>
        <p>4. 检查结论"存在不符合事项"的须在说明栏列明并评估对财务报表的影响。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * J3TabCheck — J3-2 股份支付检查表（19列段落型 + CAS11 + BS参数逐项验证）
 */
import { ref, computed } from 'vue'
import { useJ3Check } from '@/composables/workpaper/j3/useJ3Check'
import { useJ3Disclosure } from '@/composables/workpaper/j3/useJ3Disclosure'
import { calcBlackScholes } from '@/composables/workpaper/j3/useJ3OptionPricingEngine'
import { useJ3FormData } from '@/composables/workpaper/j3/useJ3FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  year?: string | number
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
  projectType?: string
}>()

const formData = useJ3FormData({ wpId: props.wpId, projectId: props.projectId, htmlData: props.htmlData })
const checkData = useJ3Check(formData.plans)
const { showIPOPanel, ipoHighlights } = useJ3Disclosure(props.projectType || '')
const conclusionNote = ref('')

// BS计算结果
const bsResult = computed(() => {
  const p = checkData.bsParams.value
  if (p.S > 0 && p.K > 0 && p.T > 0 && p.sigma > 0) {
    return calcBlackScholes(p.S, p.K, p.T, p.r, p.sigma)
  }
  return null
})

const conclusionType = computed(() => {
  const c = checkData.overallConclusion.value
  if (c === '全部符合') return 'success'
  if (c === '存在不符合事项') return 'danger'
  return 'info'
})

function handleAIAnalysis() {
  // 调用通用AI端点分析BS参数合理性
  console.log('[J3 Check] AI analysis triggered for BS params')
}

function handleSectionAI(sectionId: string) {
  console.log('[J3 Check] AI assist for section:', sectionId)
}

formData.loadData()
</script>

<style scoped>
.j3-tab-check { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.check-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.guide-banner {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecf7 100%);
  border-radius: 8px;
}
.guide-step { font-size: 13px; color: #303133; }
.step-num { font-weight: 700; color: #409eff; margin-right: 4px; }
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.bs-panel { margin-bottom: 16px; }
.bs-params-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.bs-param-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.param-label { font-size: 13px; min-width: 80px; color: #606266; }
.bs-result {
  margin-top: 12px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
}
.bs-result-label { font-size: 13px; color: #606266; }
.bs-result-value { font-weight: 700; color: #67c23a; font-size: 15px; }
.methodology-context {
  padding: 8px 12px;
  margin-bottom: 12px;
  background: #fffbeb;
  border-left: 3px solid #e6a23c;
  font-size: 12px;
  color: #909399;
}
.check-section { margin-bottom: 16px; }
.check-item {
  padding: 8px 0;
  border-bottom: 1px solid #ebeef5;
}
.item-label { font-size: 13px; font-weight: 500; margin-bottom: 4px; }
.item-controls { display: flex; align-items: flex-start; gap: 8px; }
.ipo-panel { margin-top: 16px; }
.ipo-highlights {
  padding-left: 20px;
  font-size: 13px;
  line-height: 2;
}
.conclusion-card { margin-top: 16px; }
</style>
