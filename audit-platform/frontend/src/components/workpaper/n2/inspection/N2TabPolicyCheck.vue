<template>
  <div class="n2-tab-policy-check">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>税收政策检查 N2-4</span>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 不合规红色摘要（当存在不合规项时显示） ═══ -->
    <div v-if="nonCompliantCount > 0" class="non-compliant-summary">
      <el-icon><WarningFilled /></el-icon>
      <span>
        存在 <strong>{{ nonCompliantCount }}</strong> 项不合规事项，请关注并记录处理意见
      </span>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>税收政策合规检查：</strong>
        逐项检查企业是否正确适用税收优惠政策、税率选择是否恰当、纳税义务发生时点是否合规。
        对每个检查项做出"合规/不合规/不适用"判断，不合规项需填写备注说明。
      </div>
    </div>

    <!-- ═══ Section 1: 税收优惠检查 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>一、税收优惠政策检查</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div
        v-for="(item, idx) in taxIncentiveItems"
        :key="`incentive-${idx}`"
        class="check-item"
        :class="{ 'check-item--non-compliant': item.status === '不合规' }"
      >
        <div class="check-item-header">
          <span class="check-item-seq">{{ idx + 1 }}.</span>
          <span class="check-item-label">{{ item.label }}</span>
        </div>
        <div class="check-item-body">
          <el-radio-group
            :model-value="item.status"
            :disabled="isReadonly"
            @change="(val: string) => handleStatusChange('incentive', idx, val)"
          >
            <el-radio value="合规">合规</el-radio>
            <el-radio value="不合规">不合规</el-radio>
            <el-radio value="不适用">不适用</el-radio>
          </el-radio-group>
          <el-input
            v-if="item.status === '不合规'"
            :model-value="item.remark"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="请说明不合规情况及处理意见..."
            :disabled="isReadonly"
            class="check-remark"
            @input="(val: string) => handleRemarkChange('incentive', idx, val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ Section 2: 税率适用检查 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>二、税率适用检查</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div
        v-for="(item, idx) in taxRateItems"
        :key="`rate-${idx}`"
        class="check-item"
        :class="{ 'check-item--non-compliant': item.status === '不合规' }"
      >
        <div class="check-item-header">
          <span class="check-item-seq">{{ idx + 1 }}.</span>
          <span class="check-item-label">{{ item.label }}</span>
        </div>
        <div class="check-item-body">
          <el-radio-group
            :model-value="item.status"
            :disabled="isReadonly"
            @change="(val: string) => handleStatusChange('rate', idx, val)"
          >
            <el-radio value="合规">合规</el-radio>
            <el-radio value="不合规">不合规</el-radio>
            <el-radio value="不适用">不适用</el-radio>
          </el-radio-group>
          <el-input
            v-if="item.status === '不合规'"
            :model-value="item.remark"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="请说明税率适用不合规情况..."
            :disabled="isReadonly"
            class="check-remark"
            @input="(val: string) => handleRemarkChange('rate', idx, val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ Section 3: 纳税义务时点检查 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>三、纳税义务时点合规检查</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div
        v-for="(item, idx) in obligationItems"
        :key="`obligation-${idx}`"
        class="check-item"
        :class="{ 'check-item--non-compliant': item.status === '不合规' }"
      >
        <div class="check-item-header">
          <span class="check-item-seq">{{ idx + 1 }}.</span>
          <span class="check-item-label">{{ item.label }}</span>
        </div>
        <div class="check-item-body">
          <el-radio-group
            :model-value="item.status"
            :disabled="isReadonly"
            @change="(val: string) => handleStatusChange('obligation', idx, val)"
          >
            <el-radio value="合规">合规</el-radio>
            <el-radio value="不合规">不合规</el-radio>
            <el-radio value="不适用">不适用</el-radio>
          </el-radio-group>
          <el-input
            v-if="item.status === '不合规'"
            :model-value="item.remark"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="请说明纳税义务时点不合规情况..."
            :disabled="isReadonly"
            class="check-remark"
            @input="(val: string) => handleRemarkChange('obligation', idx, val)"
          />
        </div>
      </div>
    </el-card>

    <!-- ═══ 综合结论 ═══ -->
    <el-card shadow="never" class="check-card">
      <template #header>
        <div class="card-header">
          <span>综合结论</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overallConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="请输入税收政策检查综合结论..."
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐项检查三大类：税收优惠/税率适用/纳税义务时点</li>
        <li>每项做出"合规/不合规/不适用"判断</li>
        <li>不合规项需填写备注说明（红色高亮提醒）</li>
        <li>税收优惠：高新技术企业15%、小微企业优惠、研发加计扣除等</li>
        <li>税率适用：增值税13%/9%/6%、城建税7%/5%/1%等</li>
        <li>纳税义务时点：收入确认时点与纳税义务发生时点一致性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabPolicyCheck — N2-4 税收政策检查
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.6
 * Requirements: 9.3-9.5
 *
 * 核心职责：
 * - 三大类检查：税收优惠/税率适用/纳税义务时点
 * - 每项：el-radio-group（合规/不合规/不适用）+ remark textarea
 * - 不合规红色摘要显示（顶部，存在不合规项时）
 * - 综合结论 textarea
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare, WarningFilled } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Types ───────────────────────────────────────────────────────────────────

type ComplianceStatus = '合规' | '不合规' | '不适用' | ''

interface CheckItem {
  label: string
  status: ComplianceStatus
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)
const overallConclusion = ref('')

// 税收优惠检查项
const taxIncentiveItems = ref<CheckItem[]>([
  { label: '高新技术企业优惠税率（15%）适用资格是否有效', status: '', remark: '' },
  { label: '小型微利企业优惠是否符合条件（年应纳税所得额/从业人数/资产总额）', status: '', remark: '' },
  { label: '研发费用加计扣除是否规范（项目立项/费用归集/台账管理）', status: '', remark: '' },
  { label: '增值税即征即退/先征后返是否有有效批文', status: '', remark: '' },
  { label: '免税收入/不征税收入分类是否正确', status: '', remark: '' },
  { label: '税收优惠期限是否到期、续期手续是否完备', status: '', remark: '' },
])

// 税率适用检查项
const taxRateItems = ref<CheckItem[]>([
  { label: '增值税税率选用是否正确（13%/9%/6%/免税）', status: '', remark: '' },
  { label: '城建税率是否与实际注册地匹配（市区7%/县城5%/其他1%）', status: '', remark: '' },
  { label: '房产税从价/从租计税方式选择是否正确', status: '', remark: '' },
  { label: '土地增值税适用税率档次是否与增值率匹配', status: '', remark: '' },
  { label: '企业所得税税率适用是否正确（25%/15%/20%/10%）', status: '', remark: '' },
  { label: '印花税税率/计税依据是否按合同类型正确适用', status: '', remark: '' },
])

// 纳税义务时点检查项
const obligationItems = ref<CheckItem[]>([
  { label: '增值税纳税义务发生时间是否与收入确认时点一致', status: '', remark: '' },
  { label: '企业所得税收入确认时点是否符合税法规定', status: '', remark: '' },
  { label: '土地增值税清算时点判断是否正确', status: '', remark: '' },
  { label: '预缴税款是否按规定时间申报缴纳', status: '', remark: '' },
  { label: '跨期费用的税前扣除时点是否正确', status: '', remark: '' },
])

// ─── 不合规计数 ──────────────────────────────────────────────────────────────

const nonCompliantCount = computed(() => {
  const allItems = [...taxIncentiveItems.value, ...taxRateItems.value, ...obligationItems.value]
  return allItems.filter(item => item.status === '不合规').length
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

type CheckSection = 'incentive' | 'rate' | 'obligation'

function getItemsRef(section: CheckSection) {
  switch (section) {
    case 'incentive': return taxIncentiveItems
    case 'rate': return taxRateItems
    case 'obligation': return obligationItems
  }
}

function handleStatusChange(section: CheckSection, index: number, val: string) {
  const items = getItemsRef(section)
  items.value[index].status = val as ComplianceStatus
  persistSection(section)
}

function handleRemarkChange(section: CheckSection, index: number, val: string) {
  const items = getItemsRef(section)
  items.value[index].remark = val
  persistSection(section)
}

function persistSection(section: CheckSection) {
  const items = getItemsRef(section)
  formData.debouncedSave(`N2-4-${section}`, {
    conclusion: JSON.stringify(items.value.map(i => ({ status: i.status, remark: i.remark }))),
  })
}

function handleConclusionChange() {
  formData.debouncedSave('N2-4-conclusion', { remark: overallConclusion.value || null })
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-policy-check',
      prompt: '请基于应交税费底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('N2-4-税收政策检查')
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  for (const section of ['incentive', 'rate', 'obligation'] as CheckSection[]) {
    const resp = formData.allResponses.value.get(`N2-4-${section}`)
    if (resp?.conclusion) {
      try {
        const saved: Array<{ status: string; remark: string }> = JSON.parse(resp.conclusion)
        const items = getItemsRef(section)
        saved.forEach((s, i) => {
          if (i < items.value.length) {
            items.value[i].status = (s.status as ComplianceStatus) || ''
            items.value[i].remark = s.remark || ''
          }
        })
      } catch { /* ignore */ }
    }
  }
  const conclusionResp = formData.allResponses.value.get('N2-4-conclusion')
  if (conclusionResp?.remark) overallConclusion.value = conclusionResp.remark
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-policy-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 不合规红色摘要 ─── */
.non-compliant-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  background: linear-gradient(135deg, #fef0f0 0%, #fde2e2 100%);
  border: 1px solid #fab6b6;
  border-left: 4px solid #f56c6c;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #c45656;
  font-weight: 500;
}

.non-compliant-summary .el-icon {
  font-size: 16px;
  color: #f56c6c;
  flex-shrink: 0;
}

.non-compliant-summary strong {
  color: #c45656;
  font-size: 15px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 检查卡片 ─── */
.check-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

/* ─── 检查项 ─── */
.check-item {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.check-item:last-child {
  border-bottom: none;
}

.check-item--non-compliant {
  background: #fef0f0;
  border-left: 3px solid #f56c6c;
  border-radius: 0 4px 4px 0;
}

.check-item-header {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 8px;
}

.check-item-seq {
  font-weight: 600;
  color: #606266;
  flex-shrink: 0;
}

.check-item-label {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
  line-height: 1.5;
}

.check-item-body {
  padding-left: 18px;
}

.check-remark {
  margin-top: 8px;
}

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
