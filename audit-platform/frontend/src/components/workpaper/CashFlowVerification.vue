<template>
  <div class="cf-verification">
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="现金等价物" name="cash">
        <CfCashEquivalents :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="勾稽核对" name="reconcile">
        <CfReconciliation :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="主表逆算" name="main">
        <el-alert type="info" :closable="false" style="margin-bottom: 8px" show-icon>
          逆算公式中涉及增值税影响（如销售收到现金）暂未扣除增值税销项税额，差异可能包含税金影响。
        </el-alert>
        <CfMainTable :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="附表间接法" name="supplementary">
        <CfSupplementary :project-id="projectId" :year="year" />
      </el-tab-pane>
      <el-tab-pane label="CF调整" name="adjustment">
        <CfAdjustment :project-id="projectId" :year="year" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CfCashEquivalents from './cf/CfCashEquivalents.vue'
import CfReconciliation from './cf/CfReconciliation.vue'
import CfMainTable from './cf/CfMainTable.vue'
import CfSupplementary from './cf/CfSupplementary.vue'
import CfAdjustment from './cf/CfAdjustment.vue'

const props = defineProps<{
  projectId: string
  year: number
  wpId?: string
}>()

const activeTab = ref('cash')
</script>

<style scoped>
.cf-verification {
  padding: 16px;
}
</style>
