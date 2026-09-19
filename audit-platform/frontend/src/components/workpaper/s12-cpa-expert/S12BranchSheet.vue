<template>
  <div class="s12-branch">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        针对具体评价领域（通用评估 / 股份支付公允价值 / 金融工具公允价值），评价所利用专家工作在假设、方法、源数据和结论方面的适当性，确认其结论可作为相关审计事项的审计证据。
      </div>
    </el-alert>

    <!-- 域选择器（el-segmented） -->
    <div class="domain-selector">
      <span class="domain-label">评价对象领域：</span>
      <el-segmented
        v-model="selectedDomain"
        :options="domainOptions"
        size="default"
      />
    </div>

    <!-- 当前域标题 + 方法论上下文 -->
    <div class="methodology-context">
      <p>{{ domainDescription }}</p>
    </div>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>{{ resolvedSheetName }}</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiAssist"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview(`s12-branch-${selectedDomain}`, resolvedSheetName)"
            >复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="branchRows"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="category" label="评价维度" width="140">
          <template #default="{ row }">
            <span>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="criterion" label="评价内容/核查事项" min-width="360">
          <template #default="{ row }">
            <span>{{ row.criterion }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="result" label="评价结果" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.result"
              size="small"
              placeholder="—"
              style="width: 100px"
              @change="saveRows"
            >
              <el-option label="满意" value="满意" />
              <el-option label="基本满意" value="基本满意" />
              <el-option label="不满意" value="不满意" />
              <el-option label="N/A" value="N/A" />
            </el-select>
            <span v-else>{{ row.result || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明/工作记录" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              placeholder="填写评价说明"
              @change="saveRows"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ref" label="索引号" width="90" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.ref" :value="row.ref" />
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-section conclusion-card">
      <template #header>
        <div class="section-header">
          <span>评价结论</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              :icon="MagicStick"
              @click="handleAiConclusion"
            >AI辅助</el-button>
            <el-button
              size="small"
              @click="handleOpenReview(`s12-branch-${selectedDomain}-conclusion`, '评价结论')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-if="!isReadonly"
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写评价结论"
        @change="saveConclusion"
      />
      <div v-else class="conclusion-text">{{ conclusion || '—' }}</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p v-for="(hint, idx) in currentHints" :key="idx">{{ idx + 1 }}. {{ hint }}</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * S12BranchSheet.vue — S12/S13 多分支子表（通用/股份支付/金融工具公允价值）
 *
 * 根据 ExpertDomain 选择显示 S12-3-2/S12-3-3/S12-3-4（或 S13-3-2/S13-3-3/S13-3-4）。
 * 使用 resolveExpertSubSheet 从 useS12S13ExpertBranch.ts 解析确定性 sheetName。
 *
 * 功能：
 * - el-segmented 域选择器（通用/股份支付/金融工具公允价值）
 * - 根据选择的 domain 动态展示对应评价表
 * - 方法论上下文（琥珀色块）
 * - 结论区 el-card + AI 按钮
 * - GtIndexChip 跨底稿引用
 * - readonly 禁编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.3
 * Requirements: 4.1, 4.2, 4.3, 4.4
 */
import { ref, computed, watch, inject, onMounted } from 'vue'
import { defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import {
  resolveExpertSubSheet,
  EXPERT_DOMAIN_LABELS,
  type ExpertDomain,
  type ExpertPrefix,
} from '../composables/useS12S13ExpertBranch'
import { useSExpertPersist } from '../composables/useSExpertPersist'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  prefix: ExpertPrefix
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// ─── 复核对话 ────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog')

function handleOpenReview(sectionId: string, label: string) {
  openReviewDialog?.(sectionId, label)
}

// ─── 域选择 ──────────────────────────────────────────────────────────────────

const selectedDomain = ref<ExpertDomain>('general')

const domainOptions = [
  { label: EXPERT_DOMAIN_LABELS['general'], value: 'general' },
  { label: EXPERT_DOMAIN_LABELS['share-based-payment'], value: 'share-based-payment' },
  { label: EXPERT_DOMAIN_LABELS['financial-instrument-fair-value'], value: 'financial-instrument-fair-value' },
]

/** 使用 resolveExpertSubSheet 确定性解析当前 sheetName */
const resolvedSheetName = computed(() => {
  return resolveExpertSubSheet(props.prefix, selectedDomain.value)
})

const domainDescription = computed(() => {
  const descMap: Record<ExpertDomain, string> = {
    'general': '通用评价——适用于评估师（资产评估/房产评估/矿权评估）、精算师、工程造价师、法律顾问等一般性专家工作的评价。',
    'share-based-payment': '股份支付专用评价——适用于对股份支付公允价值计量（Black-Scholes 模型、二叉树模型等）所利用专家工作的评价。',
    'financial-instrument-fair-value': '金融工具公允价值专用评价——适用于对金融工具（结构化产品、衍生品、可转换债券等）公允价值计量所利用专家工作的评价。',
  }
  return descMap[selectedDomain.value]
})

// ─── 分支数据 ────────────────────────────────────────────────────────────────

const branchRows = ref<Array<{ category: string; criterion: string; result: string; remark: string; ref: string }>>([])

function loadBranchRows(domain: ExpertDomain) {
  const prefix = props.prefix
  if (domain === 'general') {
    branchRows.value = getGeneralRows(prefix)
  } else if (domain === 'share-based-payment') {
    branchRows.value = getShareBasedPaymentRows(prefix)
  } else {
    branchRows.value = getFinancialInstrumentRows(prefix)
  }
}

function getGeneralRows(prefix: ExpertPrefix) {
  return [
    { category: '评估目的', criterion: '专家的估值目的是否与财务报告要求一致（如公允价值计量、减值测试等）', result: '', remark: '', ref: '' },
    { category: '评估目的', criterion: '评估报告的价值类型是否恰当（市场价值/投资价值/清算价值）', result: '', remark: '', ref: '' },
    { category: '假设合理性', criterion: '关键假设（如折现率、增长率、预期寿命等）是否有充分依据', result: '', remark: '', ref: '' },
    { category: '假设合理性', criterion: '假设是否与行业数据和历史趋势一致', result: '', remark: '', ref: '' },
    { category: '方法选择', criterion: '所选评估方法（收益法/市场法/成本法）是否适合标的资产特征', result: '', remark: '', ref: '' },
    { category: '方法选择', criterion: '如使用多种方法，各方法的权重分配是否合理', result: '', remark: '', ref: '' },
    { category: '数据完整性', criterion: '专家使用的基础数据（财务数据/市场数据/合同条款）是否完整准确', result: '', remark: '', ref: '' },
    { category: '数据完整性', criterion: '数据是否与被审计单位会计记录一致', result: '', remark: '', ref: '' },
    { category: '结论合理性', criterion: '评估结论是否在合理范围内', result: '', remark: '', ref: '' },
    { category: '结论合理性', criterion: '如与管理层估计差异较大，是否已获取合理解释', result: '', remark: '', ref: '' },
    { category: '敏感性分析', criterion: '关键变量的敏感性分析结果是否合理', result: '', remark: '', ref: '' },
    { category: '报告局限', criterion: '报告中的限制条件和保留意见是否影响审计结论', result: '', remark: '', ref: '' },
  ]
}

function getShareBasedPaymentRows(prefix: ExpertPrefix) {
  return [
    { category: '计量模型', criterion: '所用定价模型（Black-Scholes/二叉树/蒙特卡罗）是否适合对应股份支付工具', result: '', remark: '', ref: '' },
    { category: '计量模型', criterion: '模型选择理由是否充分（是否考虑了行权条件、限售安排等）', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '标的股票/股权的公允价值或价格是否可靠', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '行权价格（Exercise Price）是否与授权协议一致', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '预期波动率的计算依据和方法是否合理（历史波动率/隐含波动率）', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '预期有效期（Expected Life）与实际行权行为是否匹配', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '无风险利率选取是否恰当（期限匹配的国债收益率）', result: '', remark: '', ref: '' },
    { category: '关键参数', criterion: '预期股利率是否与公司股利政策一致', result: '', remark: '', ref: '' },
    { category: '业绩条件', criterion: '如含有市场条件，是否已在模型中反映', result: '', remark: '', ref: '' },
    { category: '业绩条件', criterion: '非市场条件（如业绩指标）是否未在公允价值中调整而在可行权数量中反映', result: '', remark: '', ref: '' },
    { category: '结论检验', criterion: '计量结果是否与可比交易或同行数据合理一致', result: '', remark: '', ref: '' },
  ]
}

function getFinancialInstrumentRows(prefix: ExpertPrefix) {
  return [
    { category: '估值层级', criterion: '金融工具的公允价值层级划分（Level 1/2/3）是否恰当', result: '', remark: '', ref: '' },
    { category: '估值层级', criterion: '是否优先使用活跃市场报价（Level 1）', result: '', remark: '', ref: '' },
    { category: '估值模型', criterion: '所用估值模型（现金流量折现/期权定价/信用风险模型）是否适合该金融工具', result: '', remark: '', ref: '' },
    { category: '估值模型', criterion: '模型是否经过独立验证或回溯测试', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '折现率/收益率曲线选取是否合理', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '信用利差（Credit Spread）是否反映发行人/交易对手信用风险', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '波动率曲面数据是否来源可靠', result: '', remark: '', ref: '' },
    { category: '关键输入', criterion: '违约概率/回收率等参数是否有合理依据', result: '', remark: '', ref: '' },
    { category: '合同条款', criterion: '是否充分考虑了嵌入衍生品或结构化条款', result: '', remark: '', ref: '' },
    { category: '合同条款', criterion: '提前赎回/转换等条款是否已在估值中反映', result: '', remark: '', ref: '' },
    { category: '市场数据', criterion: '使用的市场数据（利率/汇率/商品价格）是否为估值日数据', result: '', remark: '', ref: '' },
    { category: '日期差异', criterion: '如市场数据与报告日有时滞，是否已做适当调整', result: '', remark: '', ref: '' },
    { category: '结论合理性', criterion: '估值结果是否与市场可比数据或经纪商报价合理一致', result: '', remark: '', ref: '' },
    { category: '结论合理性', criterion: '估值不确定性区间是否合理', result: '', remark: '', ref: '' },
  ]
}

// 初始加载 + watch domain 变更（切换域时重载骨架并 seed 该域已存数据）
loadBranchRows(selectedDomain.value)
watch(selectedDomain, (newDomain) => {
  loadBranchRows(newDomain)
  conclusion.value = ''
  seedDomain(newDomain)
})

// ─── 结论 ────────────────────────────────────────────────────────────────────

const conclusion = ref('')

// ─── 持久化接线（load + save，item_id 按 prefix + domain） ────────────────────

const { seed, save } = useSExpertPersist(() => props.allResponses)

function domainRowsId(d: ExpertDomain): string {
  return `${props.prefix}-branch-${d}-rows`
}
function domainConclusionId(d: ExpertDomain): string {
  return `${props.prefix}-branch-${d}-conclusion`
}
function seedDomain(d: ExpertDomain): void {
  seed([
    { itemId: domainRowsId(d), ref: branchRows },
    { itemId: domainConclusionId(d), ref: conclusion },
  ])
}
function saveRows(): void {
  save(domainRowsId(selectedDomain.value), branchRows.value)
}
function saveConclusion(): void {
  save(domainConclusionId(selectedDomain.value), conclusion.value)
}

onMounted(() => seedDomain(selectedDomain.value))

// ─── 编制提示 ────────────────────────────────────────────────────────────────

const currentHints = computed(() => {
  const hintsMap: Record<ExpertDomain, string[]> = {
    'general': [
      '逐项核查专家的评估报告中的假设、方法和数据。',
      '关注评估结论与其他审计证据的一致性。',
      '如有重大差异，需追加程序或获取解释。',
    ],
    'share-based-payment': [
      '核查定价模型输入参数（波动率/无风险利率/预期有效期/股利率）的依据。',
      '区分市场条件和非市场条件的会计处理方式。',
      '与授权协议核对行权价格和行权条件。',
    ],
    'financial-instrument-fair-value': [
      '核查公允价值层级划分的合理性。',
      '关注 Level 3 估值中的不可观察输入和模型风险。',
      '验证市场数据来源的可靠性和时效性。',
      '核查嵌入衍生品是否需要拆分计量。',
    ],
  }
  return hintsMap[selectedDomain.value]
})

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

function handleAiAssist() {
  // TODO: 调用 AI 辅助
}

function handleAiConclusion() {
  // TODO: 调用 AI 辅助生成结论
}
</script>

<style scoped>
.s12-branch {
  padding: 12px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.domain-selector {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.domain-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #303133;
  white-space: nowrap;
}

.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}

.audit-section {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.conclusion-card {
  margin-top: 16px;
}

.conclusion-text {
  white-space: pre-wrap;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
  color: #303133;
}

.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}

.edit-hints summary {
  cursor: pointer;
  user-select: none;
}

.edit-hints p {
  margin: 4px 0;
  line-height: 1.5;
}
</style>
