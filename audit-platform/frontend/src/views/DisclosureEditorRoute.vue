<template>
  <DisclosureEditor v-if="auditYear != null" :audit-year="auditYear" />
  <el-empty v-else class="gt-de-missing-year" :description="MISSING_AUDIT_YEAR_MESSAGE">
    <el-button @click="router.back()">返回</el-button>
  </el-empty>
</template>

<script setup lang="ts">
/**
 * 附注编辑路由壳（spec post-push-residual-defect-closure 6.5）。
 *
 * 附注编辑页全程按年度取数（目录、章节、校验、导出……）。年度 = 路由 → 项目 store（项目审计年度）；
 * 项目没填审计年度时不挂附注编辑页、提示先填 —— 原先页内读 store，store 初值去年，没填年度的项目也按去年取附注
 * （浏览器实测 `/disclosure-notes/{pid}/2025` 回 404）。页内切年度（信息栏）照旧改 store，壳把新年度传下去。
 * 年度变成 null（离开项目）时壳直接卸载编辑页，编辑页里按年度的监听不会拿到 null 去请求。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import DisclosureEditor from './DisclosureEditor.vue'
import { useProjectStore } from '@/stores/project'
import { parseAuditYear } from '@/utils/resolveAuditYear'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
// 与编辑页原先的口径相同：路由显式年度优先，其次项目 store
const auditYear = computed(() => parseAuditYear(route.query.year) ?? projectStore.year)
</script>

<style scoped>
.gt-de-missing-year {
  padding: var(--gt-space-8, 48px) 0;
}
</style>
