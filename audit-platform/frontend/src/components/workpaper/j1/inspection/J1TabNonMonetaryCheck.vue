<template>
  <div class="j1-tab-nonmonetary">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：检查以自产产品、外购商品、房屋等非货币性资产提供的职工福利，验证其计量方式（公允价值）、金额及税务处理的合规性。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">非货币性福利检查表（J1-9）</span>
          <el-tag v-if="hasNonCompliant" type="warning" size="small">存在不合规项</el-tag>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
        </div>
      </template>

      <el-table :data="rows" border size="small" style="font-size: 13px">
        <el-table-column prop="benefitType" label="福利形式" min-width="120" />
        <el-table-column prop="source" label="实物来源" min-width="120" />
        <el-table-column prop="measureMethod" label="计量方式" width="100" />
        <el-table-column prop="amount" label="金额" width="110" align="right">
          <template #default="{ row }">{{ row.amount?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100" />
        <el-table-column prop="employeeCount" label="受益人数" width="80" align="right" />
        <el-table-column prop="checkResult" label="检查结论" min-width="100" />
        <el-table-column label="合规" width="60" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isCompliant ? 'success' : 'danger'" size="small">
              {{ row.isCompliant ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="total-summary">非货币性福利合计: {{ totalAmount?.toLocaleString() }} 元</div>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，以自产产品发放的非货币性福利按产品公允价值计量并计入成本费用。</p>
        <p>2. 外购商品、房屋等提供职工使用的，按实际成本或折旧/租金公允价值确认福利费。</p>
        <p>3. 非货币性福利涉及增值税视同销售、个人所得税代扣代缴，须核验税务处理合规性。</p>
        <p>4. 合规列 ✗ 项须在检查结论栏说明整改建议。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1NonMonetaryCheck } from '@/composables/workpaper/j1/useJ1NonMonetaryCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, totalAmount, hasNonCompliant, initFromHtmlData } = useJ1NonMonetaryCheck(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-nonmonetary { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.total-summary { margin-top: 12px; font-size: var(--wp-font-size, 13px); color: #606266; padding: 8px; background: #f5f7fa; border-radius: 4px; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
