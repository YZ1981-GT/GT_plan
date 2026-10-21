<!--
  公式模板列表（全局设置页「公式模板」页签；spec formula-global-settings-sync，design §16.6，R13）。
  只列当前用户可见的模板（个人 / 项目组 / 集团 / 事务所，服务端判定），按共享范围筛选；
  新建（从全局设置副本保存）、详情（定义 / 与全局不一致 / 版本 / 订阅项目 / 发布 / 设为全局 / 删除）。
  在项目里「保存为模板 / 订阅模板」请到公式管理中心。
-->
<template>
  <div class="gt-ftm" data-testid="formula-template-manager">
    <div class="gt-ftm-bar">
      <el-radio-group v-model="shareFilter" size="small">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button v-for="o in SHARE_SCOPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</el-radio-button>
      </el-radio-group>
      <el-select v-model="domainFilter" size="small" clearable placeholder="全部公式域" style="width: 180px" @change="load">
        <el-option v-for="d in domains" :key="d.key" :value="d.key" :label="d.label" />
      </el-select>
      <el-input v-model="keyword" size="small" clearable placeholder="搜索模板名称" style="width: 200px" />
      <span class="gt-ftm-spacer" />
      <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      <el-button size="small" type="primary" data-testid="ftm-create" @click="showSave = true">+ 新建模板</el-button>
    </div>
    <el-table v-loading="loading" :data="filtered" size="small" border max-height="calc(100vh - 320px)" row-key="id"
      empty-text="暂无可见的公式模板" @row-dblclick="openDetail">
      <el-table-column prop="name" label="模板" min-width="220" show-overflow-tooltip>
        <!-- formula-management-ux-improvements C2：推荐标签 -->
        <template #default="{ row }">
          <span>{{ row.name }}</span>
          <el-tag v-if="row._recommended" size="small" type="success" effect="plain" style="margin-left: 4px;">推荐</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="share_scope_label" label="共享范围" width="90" />
      <el-table-column label="适用范围" width="140">
        <template #default="{ row }">{{ scopeLabel(row.applicable_scope) }}</template>
      </el-table-column>
      <el-table-column label="公式域" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">{{ row.domains.map(domainLabel).join('、') }}</template>
      </el-table-column>
      <el-table-column label="版本" width="70" align="center">
        <template #default="{ row }">v{{ row.version }}</template>
      </el-table-column>
      <el-table-column label="可管理" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.can_manage" size="small" type="success">是</el-tag>
          <span v-else class="gt-ftm-muted">只读</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :data-testid="`ftm-detail-${row.id}`" @click="openDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>
    <FormulaTemplateSaveDialog v-model="showSave" @saved="load" />
    <FormulaTemplateDetailDrawer v-model="detailVisible" :template-id="detailId" :domains="domains" :is-admin="isAdmin"
      @changed="load" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import FormulaTemplateSaveDialog from './FormulaTemplateSaveDialog.vue'
import FormulaTemplateDetailDrawer from './FormulaTemplateDetailDrawer.vue'
import {
  SHARE_SCOPE_OPTIONS, formulaErrorText, formulaSettingsApi, scopeLabel,
  type FormulaDomainInfo, type FormulaTemplateInfo,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaTemplateManager' })

const props = withDefaults(defineProps<{ domains: FormulaDomainInfo[]; isAdmin?: boolean }>(), { isAdmin: false })

const items = ref<FormulaTemplateInfo[]>([])
const loading = ref(false)
const shareFilter = ref('')
const domainFilter = ref('')
const keyword = ref('')
const showSave = ref(false)
const detailVisible = ref(false)
const detailId = ref('')

const filtered = computed(() => {
  const kw = keyword.value.trim()
  return items.value
    .map((t) => ({
      ...t,
      // formula-management-ux-improvements C2：推荐标签（事务所级 + 适用范围匹配常用准则）
      _recommended: t.share_scope === 'firm' && !!t.applicable_scope
        && ['soe_standalone', 'listed_standalone', 'soe_consolidated', 'listed_consolidated'].includes(t.applicable_scope),
    }))
    .filter((t) => (!shareFilter.value || t.share_scope === shareFilter.value)
      && (!kw || t.name.includes(kw)))
    .sort((a, b) => (b._recommended ? 1 : 0) - (a._recommended ? 1 : 0))  // 推荐排在前面
})

function domainLabel(key: string): string {
  return props.domains.find((d) => d.key === key)?.label || key
}

async function load() {
  loading.value = true
  try {
    items.value = (await formulaSettingsApi.templates({ domain: domainFilter.value || undefined }))?.items || []
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '加载公式模板失败'))
  } finally {
    loading.value = false
  }
}

function openDetail(row: FormulaTemplateInfo) {
  detailId.value = row.id
  detailVisible.value = true
}

onMounted(load)
defineExpose({ load })
</script>

<style scoped>
.gt-ftm-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.gt-ftm-spacer { flex: 1; }
.gt-ftm-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
