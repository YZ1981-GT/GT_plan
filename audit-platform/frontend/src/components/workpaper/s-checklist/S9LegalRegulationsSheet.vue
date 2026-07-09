<template>
  <div class="s9-legal-regulations">
    <!-- ═══ 电子商务法律法规 — 方法论上下文（可折叠） ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>方法论上下文 — 电子商务法律法规</span>
          <div class="header-actions">
            <el-button size="small" @click="toggleExpanded">
              {{ isExpanded ? '收起全文' : '展开全文' }}
            </el-button>
          </div>
        </div>
      </template>

      <!-- 摘要区（始终显示） -->
      <div class="methodology-context regulatory-summary">
        <p><strong>适用法律法规概要：</strong></p>
        <p>1. 《中华人民共和国电子商务法》（2019年1月1日起施行）——电子商务经营者资质、消费者权益保护、电子合同效力。</p>
        <p>2. 《中华人民共和国网络安全法》——网络运营者安全义务、个人信息保护、数据跨境传输。</p>
        <p>3. 《中华人民共和国个人信息保护法》——个人信息处理规则、数据出境安全评估。</p>
        <p>4. 《中华人民共和国数据安全法》——数据分级分类保护、数据安全审查。</p>
        <p>5. 相关行业监管规定——支付结算管理、电子发票管理、跨境电商监管等。</p>
      </div>

      <!-- 全文内容（可折叠/滚动） -->
      <div v-if="isExpanded" class="regulatory-full-text">
        <div class="methodology-context regulatory-body" ref="bodyRef">
          <!-- ─── 电子商务法 ─── -->
          <h4>一、《中华人民共和国电子商务法》要点</h4>
          <p><strong>第一章 总则</strong></p>
          <p>电子商务是指通过互联网等信息网络销售商品或者提供服务的经营活动。</p>
          <p>电子商务经营者应当依法办理市场主体登记，依法纳税，并如实申报纳税。</p>

          <p><strong>第二章 电子商务经营者</strong></p>
          <p>（一）电子商务经营者从事经营活动，应当遵循自愿、平等、公平、诚信的原则。</p>
          <p>（二）电子商务经营者应当在其首页显著位置公示营业执照信息。</p>
          <p>（三）电子商务经营者应当保障用户知情权和选择权，不得以虚构交易等方式进行虚假宣传。</p>
          <p>（四）电子商务经营者发布的商品或者服务信息符合要约条件的，用户选择该商品或者服务并提交订单成功，合同成立。</p>

          <p><strong>第三章 电子合同</strong></p>
          <p>（一）电子商务当事人通过数据电文形式订立的合同，具有法律效力。</p>
          <p>（二）合同标的为交付商品并采用快递物流方式交付的，收货人签收时间为交付时间。</p>

          <p><strong>第四章 争议解决</strong></p>
          <p>电子商务经营者应当建立便捷、有效的投诉、举报机制，公开投诉、举报方式等信息。</p>

          <!-- ─── 网络安全法 ─── -->
          <h4>二、《中华人民共和国网络安全法》要点</h4>
          <p>（一）网络运营者应当按照网络安全等级保护制度的要求，采取安全保护措施。</p>
          <p>（二）网络运营者收集、使用个人信息，应当遵循合法、正当、必要的原则。</p>
          <p>（三）关键信息基础设施运营者应当在境内存储重要数据和个人信息。</p>
          <p>（四）任何个人和组织不得从事侵入他人网络、干扰网络正常功能等危害网络安全的活动。</p>

          <!-- ─── 个人信息保护法 ─── -->
          <h4>三、《中华人民共和国个人信息保护法》要点</h4>
          <p>（一）处理个人信息应当取得个人同意（七种合法事由之一）。</p>
          <p>（二）个人信息的处理目的、处理方式和处理的个人信息种类应当明确告知。</p>
          <p>（三）个人信息处理者应当对其个人信息处理活动负责，采取必要措施保障安全。</p>
          <p>（四）向境外提供个人信息应当通过安全评估或取得个人信息保护认证。</p>

          <!-- ─── 数据安全法 ─── -->
          <h4>四、《中华人民共和国数据安全法》要点</h4>
          <p>（一）国家建立数据分类分级保护制度，根据数据在经济社会发展中的重要程度实行分类分级保护。</p>
          <p>（二）开展数据处理活动应当加强风险监测，发现数据安全缺陷、漏洞等风险时，应当立即采取补救措施。</p>
          <p>（三）重要数据的处理者应当按照规定对其数据处理活动定期开展风险评估。</p>

          <!-- ─── 支付与税务 ─── -->
          <h4>五、电子支付与税务管理</h4>
          <p>（一）《非银行支付机构网络支付业务管理办法》——第三方支付账户实名制、支付限额管理。</p>
          <p>（二）《增值税电子普通发票开具与管理规定》——电子发票的开具、传递、查验与入账。</p>
          <p>（三）《跨境电子商务零售进出口商品监管规定》——跨境电商税收政策、海关监管要求。</p>

          <!-- ─── 审计关注 ─── -->
          <h4>六、审计关注要点</h4>
          <p>（一）被审计单位的电子商务经营资质是否合法合规。</p>
          <p>（二）电子商务收入确认时点是否符合会计准则和相关法律规定。</p>
          <p>（三）用户数据保护措施是否符合个人信息保护法的要求。</p>
          <p>（四）跨境电子商务（如有）是否符合外汇管理和海关监管要求。</p>
          <p>（五）电子支付资金的结算和对账是否完整、及时。</p>
          <p>（六）电子发票管理是否合规，是否存在虚开发票风险。</p>
          <p>（七）平台经营者与入驻商户的权责划分和收入分成是否清晰。</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * S9LegalRegulationsSheet.vue — 电子商务法律法规 方法论上下文
 *
 * 功能：
 * - 展示电子商务相关法律法规参考内容（98×5 结构）
 * - 以"方法论上下文"样式呈现（琥珀色左边线 + 浅黄背景）
 * - 默认折叠仅显示摘要，点击"展开全文"显示完整内容
 * - 长文本可滚动展示，不占主视图
 * - 纯参考性内容，无编辑功能
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.1
 * Requirements: 7.3
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
.s9-legal-regulations {
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

.methodology-context {
  padding: 12px 16px;
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
  font-size: 13px;
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
</style>
