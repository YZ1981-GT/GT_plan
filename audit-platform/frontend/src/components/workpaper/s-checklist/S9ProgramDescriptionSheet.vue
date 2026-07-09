<template>
  <div class="s9-program-desc">
    <!-- ═══ 程序说明 — 电子商务考虑方法论 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>程序说明 — 对电子商务的考虑</span>
          <div class="header-actions">
            <el-tag size="small" type="info" effect="plain">参考文档</el-tag>
          </div>
        </div>
      </template>

      <!-- 方法论上下文描述 -->
      <div class="methodology-context">
        <h4>一、审计目标</h4>
        <p>在了解被审计单位及其环境时，考虑电子商务对业务流程、内部控制及财务报表的影响。</p>

        <h4>二、适用准则</h4>
        <p>《中国注册会计师审计准则第1211号——通过了解被审计单位及其环境识别和评估重大错报风险》</p>
        <p>《中国注册会计师审计准则第1231号——针对评估的重大错报风险采取的应对措施》</p>

        <h4>三、程序要点</h4>
        <p>1. 了解被审计单位电子商务业务模式（B2B/B2C/C2C/O2O 等）。</p>
        <p>2. 评估电子商务对收入确认的影响（时点/时段、退货退款、促销折扣）。</p>
        <p>3. 了解电子支付渠道及资金结算流程。</p>
        <p>4. 评估电子商务相关的内部控制（信息系统一般控制 + 应用控制）。</p>
        <p>5. 关注电子商务数据安全和个人信息保护合规性。</p>
        <p>6. 评估电子商务对存货管理、物流和仓储的影响。</p>
        <p>7. 考虑跨境电子商务（如有）的外汇和税务风险。</p>

        <h4>四、与其他程序的关系</h4>
        <p>• 本程序的结论将影响 B50 风险评估中电子商务相关的重大错报风险识别。</p>
        <p>• 内控调查表（S9-2）结果直接影响控制测试程序的设计。</p>
        <p>• 审定表（S9-1）回写试算表相关科目。</p>

        <h4>五、索引参考</h4>
        <p>• B50 — 重大错报风险评估</p>
        <p>• C22 — IT一般控制测试</p>
        <p>• D4/D7 — 营业收入/合同负债实质性程序</p>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * S9ProgramDescriptionSheet.vue — S9 程序说明（方法论参考）
 *
 * 功能：
 * - 展示"在了解被审计单位及其环境时对电子商务的考虑"的方法论说明
 * - 61×9 结构，以方法论上下文样式呈现
 * - 纯参考性只读文档
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.1
 * Requirements: 7.1
 */

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()
</script>

<style scoped>
.s9-program-desc {
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
  padding: 16px 20px;
  border-left: 4px solid #e6a23c;
  background-color: #fdf6ec;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}

.methodology-context h4 {
  margin: 14px 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.methodology-context h4:first-child {
  margin-top: 0;
}

.methodology-context p {
  margin: 4px 0;
}
</style>
