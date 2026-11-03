<!--
  WpAccountAbsenceHint — 试算表里找不到本底稿科目时的不阻断提示（spec trim-followup-residual-findings-closure R1.2）。

  H5 油气资产 / H7 生产性生物资产 / M8 一般风险准备只在特定业务里核算。平台没有项目级行业来源，
  原先按「行业」整页拦截或跳过取数，判定永远不命中。现按渲染返回的 accounts_found（本底稿语义科目
  在本项目试算表里是否找到）提示：只在明确为 false 时出现，不挡编制；不适用的底稿走程序裁剪（有理由、留痕）。
-->
<template>
  <el-alert
    v-if="accountsFound === false"
    type="info"
    show-icon
    :closable="true"
    class="wp-account-absence-hint"
    :title="`试算表中未找到「${accountName}」科目`"
  >
    <template #default>
      <span>{{ usualScope }}。如本项目不涉及，可在程序裁剪中把本底稿标为不执行；若还没有导入试算表，可忽略此提示。</span>
      <el-button link type="primary" class="wp-account-absence-hint__trim" @click="goTrim">去程序裁剪</el-button>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

// 🔴 默认值必须显式给 null：含 Boolean 的 prop 父组件不传时 Vue 会转成 false，提示就会无条件出现
const props = withDefaults(defineProps<{
  projectId: string
  /** 审计循环字母（裁剪页按循环深链） */
  cycle: string
  /** 本底稿核算的科目名，如「油气资产」 */
  accountName: string
  /** 该科目通常适用的业务说明，如「通常只在石油天然气开采企业核算」 */
  usualScope: string
  /** 渲染返回的 accounts_found；null = 尚未知道，不提示 */
  accountsFound?: boolean | null
}>(), { accountsFound: null })

const router = useRouter()

function goTrim(): void {
  void router.push({ name: 'ProcedureTrimming', params: { projectId: props.projectId }, query: { cycle: props.cycle } })
}
</script>

<style scoped>
.wp-account-absence-hint {
  margin: 8px 16px;
}

.wp-account-absence-hint__trim {
  margin-left: 8px;
  vertical-align: baseline;
}
</style>
