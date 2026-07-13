<template>
  <div class="k6-tab-initial-recognition">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在 / 权利义务：</b>资产负债表中记录的持有待售资产和负债是存在的、已记录于恰当账户；记录的持有待售资产由被审计单位拥有或控制，负债为应履行的偿还义务；</li>
        <li><b>计价和分摊：</b>持有待售资产和负债以恰当金额包括在财务报表中，相关计价或分摊调整已恰当记录；</li>
        <li><b>列报与披露（分类恰当）：</b>初始分类满足 CAS42 五条件（决议 / 不可撤销转让协议 / 一年内完成出售等），相关披露已恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step">
          <span class="step-num">①</span>
          <span>录入各持有待售资产/负债的账面价值（可与 K6-2 明细表核对）</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">②</span>
          <span>三方法确定公允价值：销售协议价 &gt; 活跃市场价 &gt; 估计价（自动取优先级）</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">③</span>
          <span>公允净额 = 公允价值 − 出售费用；填写预计出售时间、决议/协议索引</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">④</span>
          <span>下方 CAS42 五条件辅助判断 → AI 生成分类判断结论</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块，源模板审计过程） ═══ -->
    <div class="methodology-context">
      <p><strong>CAS42 初始确认审计过程：</strong>①获取处置决议、不可撤销转让协议等文件，分析是否在当前状况下即可立即出售、是否一年内完成，确认是否满足持有待售条件；②检查划分为持有待售的资产是否停止计提折旧/折耗/摊销，是否按<strong>账面价值与公允价值减去出售费用后的净额孰低</strong>计量，公允价值确定是否合理；③与相关损益项目勾稽，复核计入金额是否准确；④如聘请专家确定公允价值和出售费用，应考虑利用专家工作；⑤结合关联方审计程序，关注与关联方签订的处置协议的会计处理与披露。</p>
    </div>

    <!-- ═══ 初始确认估值表（源模板主体） ═══ -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">K6-4 持有待售资产和负债初始确认估值表</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('K6-4-valuation')">💬</el-button>
          </div>
        </div>
      </template>

      <el-empty
        v-if="valuationRows.length === 0"
        description="暂无估值行，点击下方按钮按分类新增（持有待售非流动资产 / 处置组资产 / 处置组负债）"
        :image-size="70"
      />

      <el-table
        v-else
        :data="valuationRows"
        border
        size="small"
        class="valuation-table"
        row-key="rowId"
        :row-class-name="valuationRowClass"
        max-height="560"
      >
        <el-table-column type="index" label="序" width="44" align="center" fixed="left" />
        <el-table-column label="分类" width="120" fixed="left">
          <template #default="{ row }">
            <el-select
              :model-value="row.category"
              :disabled="isReadonly"
              size="small"
              @change="(v: any) => updateValuationCell(row.rowId, 'category', v)"
            >
              <el-option label="非流动资产" value="asset_noncurrent" />
              <el-option label="处置组资产" value="asset_group" />
              <el-option label="处置组负债" value="liability_group" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="处置组/主体" width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.groupName"
              :disabled="isReadonly"
              size="small"
              placeholder="如子公司A"
              @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'groupName', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="项目" min-width="150" fixed="left">
          <template #default="{ row }">
            <el-input
              :model-value="row.itemName"
              :disabled="isReadonly"
              size="small"
              @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'itemName', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.bookValue"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              @change="(v: number | undefined) => updateValuationCell(row.rowId, 'bookValue', v ?? 0)"
            />
          </template>
        </el-table-column>

        <!-- 公允价值确定（三方法，分组表头，对照源模板 R16） -->
        <el-table-column label="公允价值确定">
          <el-table-column label="销售协议价格" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.salesPrice"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateValuationCell(row.rowId, 'salesPrice', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="依据" width="100">
            <template #default="{ row }">
              <el-input
                :model-value="row.salesBasis"
                :disabled="isReadonly"
                size="small"
                @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'salesBasis', (e.target as HTMLInputElement)?.value ?? '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="资产活跃市场价格" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.marketPrice"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateValuationCell(row.rowId, 'marketPrice', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="依据" width="100">
            <template #default="{ row }">
              <el-input
                :model-value="row.marketBasis"
                :disabled="isReadonly"
                size="small"
                @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'marketBasis', (e.target as HTMLInputElement)?.value ?? '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="估计价格" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.estimatePrice"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateValuationCell(row.rowId, 'estimatePrice', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="依据" width="100">
            <template #default="{ row }">
              <el-input
                :model-value="row.estimateBasis"
                :disabled="isReadonly"
                size="small"
                @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'estimateBasis', (e.target as HTMLInputElement)?.value ?? '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="120" align="right">
            <template #header>
              <span class="formula-header" title="= IF(销售协议价>0, 销售协议价, IF(活跃市场价>0, 活跃市场价, 估计价))">公允价值</span>
            </template>
            <template #default="{ row }">
              <el-tooltip content="优先级：销售协议价 > 活跃市场价 > 估计价" placement="top">
                <span class="formula-cell">{{ fmtAmt(row.fairValue) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="出售费用" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.sellingCost"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              @change="(v: number | undefined) => updateValuationCell(row.rowId, 'sellingCost', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="公允净额" width="120" align="right">
          <template #header>
            <span class="formula-header" title="= 公允价值 - 出售费用（孰低计量基础）">公允净额</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 公允价值 - 出售费用" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.fairValueNet) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="预计出售时间" width="130">
          <template #default="{ row }">
            <el-input
              :model-value="row.expectedSaleTime"
              :disabled="isReadonly"
              size="small"
              placeholder="预计一年内完成"
              @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'expectedSaleTime', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="即可立即出售" width="120" align="center">
          <template #header>
            <el-tooltip content="根据类似交易惯例，在当前状况下即可立即出售" placement="top">
              <span class="hint-header">即可立即出售</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              :model-value="row.immediatelySellable"
              :disabled="isReadonly"
              size="small"
              placeholder="请选择"
              @change="(v: any) => updateValuationCell(row.rowId, 'immediatelySellable', v)"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待定" value="待定" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="决议索引" width="110">
          <template #header>
            <el-tooltip content="被审计单位就出售计划作出决议（索引）" placement="top">
              <span class="hint-header">决议索引</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input
              :model-value="row.decisionRef"
              :disabled="isReadonly"
              size="small"
              @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'decisionRef', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="协议索引" width="110">
          <template #header>
            <el-tooltip content="与受让方签订的不可撤销的具有法律约束力的购买协议（索引）" placement="top">
              <span class="hint-header">协议索引</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input
              :model-value="row.agreementRef"
              :disabled="isReadonly"
              size="small"
              @blur="(e: FocusEvent) => updateValuationCell(row.rowId, 'agreementRef', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeValuationRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分区小计 -->
      <div class="valuation-summary">
        <span class="summary-item">资产合计（{{ valuationSubtotals.assetCount }} 项）— 账面: <strong>{{ fmtAmt(valuationSubtotals.assetBook) }}</strong> ｜ 公允净额: <strong>{{ fmtAmt(valuationSubtotals.assetFairNet) }}</strong></span>
        <span class="summary-item">负债合计（{{ valuationSubtotals.liabilityCount }} 项）— 账面: <strong>{{ fmtAmt(valuationSubtotals.liabilityBook) }}</strong> ｜ 公允净额: <strong>{{ fmtAmt(valuationSubtotals.liabilityFairNet) }}</strong></span>
      </div>

      <!-- 分类新增按钮 -->
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="addValuationRow('asset_noncurrent')">+ 持有待售非流动资产</el-button>
        <el-button size="small" @click="addValuationRow('asset_group')">+ 处置组资产</el-button>
        <el-button size="small" @click="addValuationRow('liability_group')">+ 处置组负债</el-button>
      </div>
    </el-card>

    <!-- ═══ CAS42 五条件辅助判断区 ═══ -->
    <el-card shadow="never" class="block-card aux-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">CAS42 五条件核对（辅助判断）</span>
          <div class="section-header-actions">
            <el-tag v-if="isFullyEvaluated" :type="classificationResult === 'classified' ? 'success' : 'danger'" size="small">
              {{ classificationResult === 'classified' ? '可分类为持有待售' : '不满足分类条件' }}
            </el-tag>
            <el-tag v-else type="info" size="small">评估进行中</el-tag>
            <el-button size="small" circle @click="openReview('K6-4')">💬</el-button>
          </div>
        </div>
      </template>

      <!-- 不满足条件红色列表 -->
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
            :autosize="{ minRows: 1, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="审计证据/说明（如：已查阅董事会决议第XX号、已核对转让协议…）"
            @blur="(e: FocusEvent) => updateConditionEvidence(cond.index, (e.target as HTMLTextAreaElement)?.value ?? '')"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="如：与资产减值损失科目勾稽核对一致，详见底稿 JXXXX…"
        @blur="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 分类判断结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计结论（分类判断）</span>
          <el-button size="small" type="primary" link :loading="aiLoading" @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="classificationConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写持有待售分类判断结论（如：经逐条核对 CAS42 第六条规定的五项分类条件，并按孰低法复核估值，该资产/处置组满足/不满足持有待售分类条件…）"
        @blur="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>估值表账面价值应与 K6-2 明细表核对一致；公允价值三方法取优先级：销售协议价 &gt; 活跃市场价 &gt; 估计价</li>
        <li>公允净额 = 公允价值 − 出售费用，是后续孰低计量（K6-5/K6-6）的计量基础</li>
        <li>持有待售的处置组按"处置组资产/处置组负债"分类录入，可用"处置组/主体"列标注子公司A、分公司B</li>
        <li>CAS42 第六条五个条件必须<strong>同时满足</strong>才能分类为持有待售，"不适用"视同满足</li>
        <li>条件④"一年内完成"有例外情形：非企业自身原因导致延期且企业已取得足够证据表明仍承诺出售</li>
        <li>划分为持有待售后应停止计提折旧/折耗/摊销，并跳转 K6-5 减值测试按孰低计量</li>
        <li>决议索引/协议索引应指向董事会决议、不可撤销转让协议等支持性证据底稿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabInitialRecognition.vue — K6-4 持有待售资产和负债初始确认检查表
 *
 * 对照源模板重建：
 * - 主体 = 初始确认估值表（19列）：分类/处置组/项目/账面价值 + 公允价值三方法确定（销售协议价/依据/活跃市场价/依据/估计价/依据/公允价值公式）+ 出售费用/公允净额(公式) + CAS42判断列（预计出售时间/即可立即出售/决议索引/协议索引）
 * - 辅助 = CAS42 五条件核对清单（满足/不满足/不适用 + 证据）
 * - AI 分类判断结论 + 审计说明 + 编制提示
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.4 · Requirements 4.1-4.5
 */
import { ref, computed, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
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
  valuationRows,
  valuationSubtotals,
  updateValuationCell,
  addValuationRow,
  removeValuationRow,
  auditNote,
  saveAuditNote,
} = useK6InitialRecognition({
  allResponses: allResponsesRef,
  saveResponse,
})

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

const aiLoading = ref(false)

async function handleAiGenerate() {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const condContext = conditions.value.map(c =>
      `${c.label}: ${c.status === 'met' ? '满足' : c.status === 'not_met' ? '不满足' : c.status === 'na' ? '不适用' : '未评估'}${c.evidence ? ` (证据: ${c.evidence})` : ''}`
    ).join('\n')
    const valContext = `估值表：资产 ${valuationSubtotals.value.assetCount} 项(账面 ${valuationSubtotals.value.assetBook}，公允净额 ${valuationSubtotals.value.assetFairNet})，负债 ${valuationSubtotals.value.liabilityCount} 项(账面 ${valuationSubtotals.value.liabilityBook}，公允净额 ${valuationSubtotals.value.liabilityFairNet})`
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'classification-conclusion',
      context: `${valContext}\n\nCAS42五条件核对：\n${condContext}`,
      prompt: '根据初始确认估值表与CAS42五条件核对结果，生成持有待售分类判断结论',
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

// ─── Review ──────────────────────────────────────────────────────────────────

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── Table row class ─────────────────────────────────────────────────────────

function valuationRowClass({ row }: { row: any }): string {
  if (row.category === 'liability_group') return 'liability-row'
  if (row.category === 'asset_group') return 'group-asset-row'
  return ''
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-initial-recognition {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

.audit-objective { margin-bottom: 14px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-list { padding-left: 18px; line-height: 1.55; font-size: 12px; margin: 4px 0 0; }

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
  font-size: var(--wp-font-size, 13px);
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

/* 块卡片 */
.block-card { margin-bottom: 16px; }
.block-card :deep(.el-card__header) { padding: 8px 14px; }
.block-card :deep(.el-card__body) { padding: 12px; }
.aux-card :deep(.el-card__body) { padding: 12px; }

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

/* 估值表 */
.valuation-table {
  font-size: var(--wp-font-size, 13px);
}
.valuation-table :deep(.el-table__cell) {
  padding: 4px 0;
}
.valuation-table :deep(.liability-row) {
  background: #fef6f6;
}
.valuation-table :deep(.group-asset-row) {
  background: #f6faf6;
}
.amt-input {
  width: 100%;
}
.amt-input :deep(.el-input__inner) {
  text-align: right;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 2px;
}
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
.hint-header {
  border-bottom: 1px dotted #c0c4cc;
  cursor: help;
}

/* 分区小计 */
.valuation-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 10px 12px;
  margin-top: 10px;
  background: #f9fafb;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
  font-size: var(--wp-font-size, 13px);
  color: #4b5563;
}

/* 新增按钮 */
.add-row-bar {
  padding-top: 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 不满足条件提示 */
.unmet-alert { margin-bottom: 12px; }

/* 条件清单 */
.conditions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.condition-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 14px;
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
  margin-bottom: 6px;
}
.condition-label {
  font-weight: 600;
  font-size: 13px;
  color: #1f2937;
}
.condition-desc {
  font-size: 12px;
  color: #6b7280;
  margin: 4px 0 8px 0;
  line-height: 1.5;
}

/* 审计结论卡 */
.audit-note-card { margin-bottom: 16px; }

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
