<template>
  <div class="s6-regulatory">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>方法论上下文 — 会计监管风险提示第9号</span>
          <div class="header-actions">
            <el-button size="small" @click="toggleExpanded">
              {{ isExpanded ? '收起全文' : '展开全文' }}
            </el-button>
          </div>
        </div>
      </template>

      <!-- 监管文件标题 -->
      <div class="regulatory-title">
        会计监管风险提示第9号——上市公司控股股东资金占用及其审计
      </div>

      <!-- 摘要区（始终显示） -->
      <div class="methodology-context regulatory-summary">
        <p><strong>核心要点：</strong></p>
        <p>1. 控股股东资金占用是指上市公司的控股股东及其附属企业直接或间接无偿占用上市公司资金的行为。</p>
        <p>2. 注册会计师在审计上市公司年度财务报表时，应关注控股股东及关联方是否存在资金占用情况。</p>
        <p>3. 注册会计师应核实资金往来的商业实质，判断是否属于非经营性资金占用。</p>
        <p>4. 对于已发现的资金占用问题，注册会计师应评估对财务报表整体影响和审计意见类型的选择。</p>
      </div>

      <!-- 全文内容（可折叠/滚动） -->
      <div v-if="isExpanded" class="regulatory-full-text">
        <div class="methodology-context regulatory-body" ref="bodyRef">
          <h4>一、资金占用的定义和表现形式</h4>
          <p>控股股东资金占用是指上市公司的控股股东、实际控制人及其附属企业以各种方式直接或间接无偿占用上市公司资金的行为，主要表现形式包括：</p>
          <p>（一）控股股东及关联方直接借用上市公司资金而未按约定归还或支付利息；</p>
          <p>（二）通过预付账款、其他应收款等科目以经营性名义占用资金，但实质无真实交易支撑；</p>
          <p>（三）通过第三方（包括关联方的关联方）中转，形成隐性资金占用链条；</p>
          <p>（四）上市公司为控股股东提供资金担保，且控股股东未按期偿还导致上市公司承担代偿责任；</p>
          <p>（五）其他损害上市公司及中小股东利益的资金占用行为。</p>

          <h4>二、注册会计师的审计责任</h4>
          <p>注册会计师在审计上市公司年度财务报表时，应当：</p>
          <p>（一）了解和评估与关联方交易和资金往来相关的重大错报风险；</p>
          <p>（二）设计和实施审计程序以识别控股股东及关联方是否存在资金占用行为；</p>
          <p>（三）对已识别的资金占用事项获取充分、适当的审计证据；</p>
          <p>（四）评价资金占用事项对财务报表的影响以及对审计意见的影响。</p>

          <h4>三、审计程序要求</h4>
          <p>注册会计师应当实施以下审计程序：</p>
          <p>（一）获取并核实关联方清单的完整性，关注是否存在未披露的关联关系；</p>
          <p>（二）分析大额资金往来的商业实质，关注预付账款长期挂账、其他应收款异常增长等情形；</p>
          <p>（三）检查资金流向，对大额款项进行穿透核查，识别最终资金使用方；</p>
          <p>（四）向相关方函证资金往来余额及交易发生额；</p>
          <p>（五）检查相关合同、协议、审批文件，判断交易的合规性；</p>
          <p>（六）检查银行流水、资金收付记录，核实资金流转路径；</p>
          <p>（七）对本期发生的关联方资金往来逐笔核实其商业目的和经济实质。</p>

          <h4>四、审计报告影响评估</h4>
          <p>当发现控股股东资金占用时，注册会计师应当：</p>
          <p>（一）评估资金占用金额的重大性水平和影响范围；</p>
          <p>（二）评估资金能否按时收回及回收的可能性（减值风险）；</p>
          <p>（三）评估资金占用对上市公司持续经营能力的影响；</p>
          <p>（四）根据资金占用的严重程度选择适当的审计意见类型：</p>
          <p class="indent">- 如果资金占用导致重大且广泛的错报：考虑出具否定意见或无法表示意见；</p>
          <p class="indent">- 如果资金占用导致重大但不广泛的错报：考虑出具保留意见；</p>
          <p class="indent">- 如果资金占用信息未在附注中充分披露：在审计报告强调事项段中提请关注。</p>

          <h4>五、违规担保的审计关注</h4>
          <p>注册会计师还应关注上市公司为控股股东及关联方提供担保的情况：</p>
          <p>（一）获取担保清单并核实完整性（包括查询人民银行征信系统/中国裁判文书网等）；</p>
          <p>（二）检查担保是否经过合法合规的审批程序（股东大会/董事会决议）；</p>
          <p>（三）评估被担保方的偿债能力和担保风险敞口；</p>
          <p>（四）评价或有负债（预计负债）的计量和披露是否充分。</p>

          <h4>六、其他要求</h4>
          <p>（一）注册会计师应当关注资金占用/违规担保是否涉及舞弊（管理层凌驾于内部控制之上）；</p>
          <p>（二）对于本期已归还的资金占用，应关注是否属于"先还后借"的短期行为；</p>
          <p>（三）关注是否存在通过"体外循环"规避监管的行为（如通过供应商/客户中转资金）；</p>
          <p>（四）在出具审计报告前，应向上市公司管理层和治理层沟通已发现的资金占用事项。</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * S6RegulatoryReferenceSheet.vue — 会计监管风险提示第9号 方法论上下文
 *
 * 功能：
 * - 展示会计监管风险提示第9号——上市公司控股股东资金占用及其审计
 * - 以"方法论上下文"样式呈现（琥珀色左边线 + 浅黄背景）
 * - 150 rows 长文本，默认折叠仅显示摘要，点击"展开全文"显示完整内容
 * - 可滚动长文本展示
 * - 纯参考性内容，无编辑功能
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 4.4
 * Requirements: 6.2
 */
import { ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 展开/折叠状态 ──────────────────────────────────────────────────────────

const isExpanded = ref(false)
const bodyRef = ref<HTMLElement | null>(null)

function toggleExpanded() {
  isExpanded.value = !isExpanded.value
}
</script>

<style scoped>
.s6-regulatory {
  padding: 12px;
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

.regulatory-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
  text-align: center;
}

.methodology-context {
  padding: 12px 16px;
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.8;
  color: #606266;
}

.regulatory-summary {
  margin-bottom: 12px;
}

.regulatory-summary p {
  margin: 4px 0;
}

.regulatory-full-text {
  margin-top: 12px;
}

.regulatory-body {
  max-height: 500px;
  overflow-y: auto;
}

.regulatory-body h4 {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.regulatory-body p {
  margin: 4px 0;
}

.regulatory-body .indent {
  padding-left: 16px;
}
</style>
