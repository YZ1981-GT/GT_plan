<template>
  <div class="g4-tab-sppi-test">
    <!-- ═══ (一) 债券投资及委托贷款 SPPI分析 ═══ -->
    <div class="section-header">
      <h3 class="section-title">（一）债券投资及委托贷款 — 合同现金流量特征分析（SPPI测试）</h3>
      <div class="section-actions">
        <el-button size="small" type="primary" plain @click="emitAi('sppi-bond-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-6合同现金流量特征分析-债券')">复核</el-button>
      </div>
    </div>

    <!-- Part 1 表格 -->
    <el-table
      :data="bondItems"
      border
      stripe
      size="small"
      :max-height="560"
      highlight-current-row
      class="sppi-bond-table"
      @current-change="() => {}"
    >
      <el-table-column label="投资项目" prop="investProject" min-width="120" fixed>
        <template #default="{ row }">
          <el-input
            v-model="row.investProject"
            size="small"
            :disabled="isReadonly"
            @change="handleBondUpdate(row.id, { investProject: row.investProject })"
          />
        </template>
      </el-table-column>
      <el-table-column label="票面价值" min-width="100">
        <template #default="{ row }">
          <el-input-number
            v-model="row.faceValue"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="handleBondUpdate(row.id, { faceValue: row.faceValue })"
          />
        </template>
      </el-table-column>
      <el-table-column label="票面利率(%)" min-width="100">
        <template #default="{ row }">
          <el-input-number
            v-model="row.couponRate"
            size="small"
            :controls="false"
            :precision="4"
            :disabled="isReadonly"
            @change="handleBondUpdate(row.id, { couponRate: row.couponRate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="提前回售" min-width="80" align="center">
        <template #default="{ row }">
          <el-switch
            v-model="row.hasEarlyRedemption"
            size="small"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="handleBondUpdate(row.id, { hasEarlyRedemption: row.hasEarlyRedemption })"
          />
        </template>
      </el-table-column>
      <el-table-column label="展期" min-width="80" align="center">
        <template #default="{ row }">
          <el-switch
            v-model="row.hasExtension"
            size="small"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="handleBondUpdate(row.id, { hasExtension: row.hasExtension })"
          />
        </template>
      </el-table-column>
      <el-table-column label="权益转换" min-width="80" align="center">
        <template #default="{ row }">
          <el-switch
            v-model="row.hasEquityConversion"
            size="small"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="handleBondUpdate(row.id, { hasEquityConversion: row.hasEquityConversion })"
          />
        </template>
      </el-table-column>
      <el-table-column label="杠杆" min-width="80" align="center">
        <template #default="{ row }">
          <el-switch
            v-model="row.hasLeverage"
            size="small"
            :disabled="isReadonly"
            active-text="是"
            inactive-text="否"
            @change="handleBondUpdate(row.id, { hasLeverage: row.hasLeverage })"
          />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-select
            v-model="row.conclusion"
            size="small"
            :disabled="isReadonly"
            placeholder="自动判定"
            @change="sppiTestLogic.setBondConclusion(row.id, row.conclusion)"
          >
            <el-option
              v-for="opt in SPPI_CONCLUSION_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="分析项目" min-width="140">
        <template #default="{ row }">
          <el-select
            v-model="row.analysisType"
            size="small"
            :disabled="isReadonly"
            placeholder="选择分析类型"
            clearable
            @change="handleBondUpdate(row.id, { analysisType: row.analysisType })"
          >
            <el-option
              v-for="opt in ANALYSIS_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="判断逻辑（方法论上下文）" min-width="280">
        <template #default="{ row }">
          <div
            v-if="row.methodologyText"
            class="methodology-context"
          >
            {{ row.methodologyText }}
          </div>
          <el-text v-else type="info" size="small">选择分析项目后显示</el-text>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            type="danger"
            link
            size="small"
            :disabled="isReadonly || bondItems.length <= 1"
            @click="sppiTestLogic.removeBondItem(row.id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增行 + 导入导出 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="sppiTestLogic.addBondItem()">
        + 新增投资项目
      </el-button>
      <slot name="importExport" />
    </div>

    <!-- 部分(一) 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="bondConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        placeholder="请输入对债券投资SPPI测试的审计结论..."
        :disabled="isReadonly"
        @change="sppiTestLogic.setBondAuditConclusion(bondConclusion)"
      />
    </el-card>

    <!-- ═══ (二) 银行理财产品三步判断 ═══ -->
    <div class="section-header" style="margin-top: 24px;">
      <h3 class="section-title">（二）银行理财产品 — 三步SPPI判断</h3>
      <div class="section-actions">
        <el-button size="small" type="primary" plain @click="emitAi('sppi-financial-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" :icon="ChatDotRound" @click="handleReview('G4-6合同现金流量特征分析-理财')">复核</el-button>
      </div>
    </div>

    <!-- 第一步: 保本保收益 -->
    <h4 class="step-title">第一步：保本保收益判断</h4>
    <el-table :data="step1Items" border stripe size="small" class="step-table">
      <el-table-column label="投资项目" prop="investProject" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="投资总额" min-width="100">
        <template #default="{ row }">
          <el-input-number v-model="row.totalAmount" size="small" :controls="false" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { totalAmount: row.totalAmount })" />
        </template>
      </el-table-column>
      <el-table-column label="保证本金" min-width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.guaranteesPrincipal" size="small" :disabled="isReadonly" active-text="是" inactive-text="否" @change="sppiTestLogic.updateStep1Item(row.id, { guaranteesPrincipal: row.guaranteesPrincipal })" />
        </template>
      </el-table-column>
      <el-table-column label="固定收益" min-width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.hasFixedReturn" size="small" :disabled="isReadonly" active-text="是" inactive-text="否" @change="sppiTestLogic.updateStep1Item(row.id, { hasFixedReturn: row.hasFixedReturn })" />
        </template>
      </el-table-column>
      <el-table-column label="固定收益率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.fixedReturnRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { fixedReturnRate: row.fixedReturnRate })" />
        </template>
      </el-table-column>
      <el-table-column label="约定浮动收益" min-width="100" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.hasFloatingReturn" size="small" :disabled="isReadonly" active-text="是" inactive-text="否" @change="sppiTestLogic.updateStep1Item(row.id, { hasFloatingReturn: row.hasFloatingReturn })" />
        </template>
      </el-table-column>
      <el-table-column label="浮动收益率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.floatingReturnRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="sppiTestLogic.updateStep1Item(row.id, { floatingReturnRate: row.floatingReturnRate })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" placeholder="--" @change="sppiTestLogic.updateStep1Item(row.id, { conclusion: row.conclusion })">
            <el-option label="通过" value="PASS" />
            <el-option label="不通过" value="FAIL" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- 第二步: 浮动收益不现实 -->
    <h4 class="step-title">第二步：浮动收益不现实判断</h4>
    <el-table :data="step2Items" border stripe size="small" class="step-table">
      <el-table-column label="投资项目" prop="investProject" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="固定收益率(%)" min-width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.fixedReturnRate" size="small" :controls="false" :precision="4" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { fixedReturnRate: row.fixedReturnRate })" />
        </template>
      </el-table-column>
      <el-table-column label="浮动收益确定方式" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.floatingMethod" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { floatingMethod: row.floatingMethod })" />
        </template>
      </el-table-column>
      <el-table-column label="基础变量历史变动" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.baseVariableHistory" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep2Item(row.id, { baseVariableHistory: row.baseVariableHistory })" />
        </template>
      </el-table-column>
      <el-table-column label="是否不现实" min-width="90" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.isUnrealistic" size="small" :disabled="isReadonly" active-text="是" inactive-text="否" @change="sppiTestLogic.updateStep2Item(row.id, { isUnrealistic: row.isUnrealistic })" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" placeholder="--" @change="sppiTestLogic.updateStep2Item(row.id, { conclusion: row.conclusion })">
            <el-option label="通过" value="PASS" />
            <el-option label="不通过" value="FAIL" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- 第三步: 穿透底层资产 -->
    <h4 class="step-title">第三步：穿透底层资产分析</h4>
    <el-table :data="step3Items" border stripe size="small" class="step-table">
      <el-table-column label="投资项目" prop="investProject" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.investProject" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep3Item(row.id, { investProject: row.investProject })" />
        </template>
      </el-table-column>
      <el-table-column label="底层资产类型" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.underlyingAssetType" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep3Item(row.id, { underlyingAssetType: row.underlyingAssetType })" />
        </template>
      </el-table-column>
      <el-table-column label="底层资产SPPI特征" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.underlyingSppiFeature" size="small" :disabled="isReadonly" @change="sppiTestLogic.updateStep3Item(row.id, { underlyingSppiFeature: row.underlyingSppiFeature })" />
        </template>
      </el-table-column>
      <el-table-column label="穿透结论" min-width="100">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" :disabled="isReadonly" placeholder="--" @change="sppiTestLogic.updateStep3Item(row.id, { conclusion: row.conclusion })">
            <el-option label="通过" value="PASS" />
            <el-option label="不通过" value="FAIL" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增理财产品 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="sppiTestLogic.addFinancialItem()">
        + 新增理财产品
      </el-button>
    </div>

    <!-- 部分(二) 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="financialConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        placeholder="请输入对银行理财产品SPPI三步分析的审计结论..."
        :disabled="isReadonly"
        @change="sppiTestLogic.setFinancialAuditConclusion(financialConclusion)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 部分(一)：逐项检查债券投资的合同条款，判断现金流量是否仅为本金和利息的支付。</p>
        <p>2. 4个布尔标志（提前回售/展期/权益转换/杠杆）变化时系统自动判定SPPI结论，用户可手动覆盖。</p>
        <p>3. 选择"分析项目"后，右侧"判断逻辑"列自动显示对应方法论参考文本。</p>
        <p>4. 部分(二)：按三步法依次判断银行理财产品（保本保收益→浮动收益不现实→穿透底层资产）。</p>
        <p>5. 权益转换特征或杠杆因素→SPPI必不通过；仅提前回售或展期→需进一步分析。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabSppiTest.vue — G4-6 合同现金流量特征分析（SPPI测试）
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 6.2
 * Requirements: 3.1~3.12, 9.1~9.8
 *
 * 完整实现：
 * - Part 1: 债券投资SPPI分析表格（10列，动态行，方法论上下文列琥珀色）
 * - Part 2: 银行理财产品三步判断（step1/step2/step3 各自表格）
 * - 导入导出 slot + AI辅助 + 复核对话
 */
import { inject, toRef } from 'vue'
import { ChatDotRound, MagicStick } from '@element-plus/icons-vue'
import { useG4SppiTest, ANALYSIS_TYPE_OPTIONS, SPPI_CONCLUSION_OPTIONS } from '@/composables/useG4SppiTest'
import type { BondSppiItem } from '@/composables/useG4SppiTest'
import type { UseG4SppiFormDataOptions } from '@/composables/useG4SppiFormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: any
  debouncedSave: (itemId: string, data: any) => void
}>()

const emit = defineEmits<{
  (e: 'aiGenerate', section: string): void
}>()

// ─── 复核对话 inject ────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog')
function handleReview(sectionId: string): void {
  openReviewDialog?.(sectionId)
}

// ─── AI辅助 ────────────────────────────────────────────────────────────────
function emitAi(section: string): void {
  emit('aiGenerate', section)
}

// ─── useG4SppiTest composable ──────────────────────────────────────────────
const sppiTestLogic = useG4SppiTest({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const {
  bondItems,
  bondConclusion,
  step1Items,
  step2Items,
  step3Items,
  financialConclusion,
} = sppiTestLogic

function handleBondUpdate(id: string, patch: Partial<BondSppiItem>): void {
  sppiTestLogic.updateBondItem(id, patch)
}
</script>

<style scoped>
.g4-tab-sppi-test { font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.section-actions { display: flex; gap: 6px; align-items: center; }

.sppi-bond-table { margin-bottom: 12px; }

.methodology-context {
  background: #fffbe6;
  border-left: 3px solid #e6a23c;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #8b6914;
  border-radius: 2px;
}

.step-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.step-table { margin-bottom: 8px; }

.table-actions {
  display: flex;
  gap: 8px;
  margin: 8px 0 16px;
}

.conclusion-card { margin: 12px 0; }
.conclusion-card :deep(.el-card__header) {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
}

.guidance-details {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.guidance-content {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.8;
}
.guidance-content p { margin: 0; }
</style>
