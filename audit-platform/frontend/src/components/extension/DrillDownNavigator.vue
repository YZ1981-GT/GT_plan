<template>
  <div class="gt-drilldown-nav gt-fade-in">
    <!-- 面包屑导航 -->
    <div class="gt-dn-breadcrumb">
      <el-breadcrumb separator="/">
        <el-breadcrumb-item
          v-for="(crumb, i) in breadcrumbs"
          :key="i"
          @click="navigateTo(i)"
        >
          <span :class="{ 'gt-crumb-link': i < breadcrumbs.length - 1 }">{{ crumb.label }}</span>
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <!-- 下钻路径提示 -->
    <div class="gt-dn-paths" v-if="showPaths && drilldownPaths.length">
      <el-tag
        v-for="path in drilldownPaths"
        :key="path.id"
        size="small"
        type="info"
        effect="plain"
        class="gt-dn-path-tag"
      >
        <el-icon><Right /></el-icon>
        {{ path.name }}
      </el-tag>
    </div>

    <!-- 下钻操作按钮 -->
    <div class="gt-dn-actions" v-if="currentLevel !== 'voucher'">
      <el-button
        v-if="canDrillToLedger"
        size="small"
        type="primary"
        plain
        @click="drillTo('ledger')"
      >
        <el-icon><List /></el-icon>
        查看明细账
      </el-button>
      <el-button
        v-if="canDrillToVoucher"
        size="small"
        type="primary"
        plain
        @click="drillTo('voucher')"
      >
        <el-icon><Document /></el-icon>
        查看凭证
      </el-button>
      <el-button
        v-if="canDrillToAux"
        size="small"
        plain
        @click="drillTo('aux_balance')"
      >
        <el-icon><DataAnalysis /></el-icon>
        查看辅助账
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Right, List, Document, DataAnalysis } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

interface Crumb {
  label: string
  level: string
  params?: Record<string, any>
}

interface DrilldownPath {
  id: string
  name: string
  source: string
  target_level: string
}

const props = withDefaults(defineProps<{
  breadcrumbs: Crumb[]
  projectId?: string
  year?: number
  currentLevel?: string
  accountCode?: string
  voucherNo?: string
  showPaths?: boolean
}>(), {
  currentLevel: 'balance',
  showPaths: false,
})

const emit = defineEmits<{
  (e: 'navigate', index: number, crumb: Crumb): void
  (e: 'drilldown', level: string, url: string): void
}>()

const router = useRouter()
const drilldownPaths = ref<DrilldownPath[]>([])

const canDrillToLedger = computed(() =>
  ['balance', 'aux_balance'].includes(props.currentLevel) && !!props.accountCode
)
const canDrillToVoucher = computed(() =>
  props.currentLevel === 'ledger' && !!props.voucherNo
)
const canDrillToAux = computed(() =>
  props.currentLevel === 'balance' && !!props.accountCode
)

function navigateTo(index: number) {
  emit('navigate', index, props.breadcrumbs[index])
}

async function drillTo(targetLevel: string) {
  if (!props.projectId || !props.year) return
  try {
    const params: any = {
      project_id: props.projectId,
      year: props.year,
      target_level: targetLevel,
    }
    if (props.accountCode) params.account_code = props.accountCode
    if (props.voucherNo) params.voucher_no = props.voucherNo

    const data = await api.get('/api/metabase/drilldown-url', { params })
    const result = data
    emit('drilldown', targetLevel, result.drilldown_url)
    router.push(result.drilldown_url)
  } catch { /* ignore */ }
}

async function loadDrilldownPaths() {
  try {
    const data = await api.get('/api/metabase/drilldown-config')
    drilldownPaths.value = data ?? []
  } catch { drilldownPaths.value = [] }
}

onMounted(() => {
  if (props.showPaths) loadDrilldownPaths()
})
</script>

<style scoped>
.gt-drilldown-nav {
  display: flex;
  align-items: center;
  gap: var(--gt-space-4);
  padding: var(--gt-space-2) var(--gt-space-3);
  background: var(--gt-color-bg-white);
  border-bottom: 1px solid var(--gt-color-border-light);
  flex-wrap: wrap;
}
.gt-dn-breadcrumb { flex-shrink: 0; }
.gt-crumb-link { cursor: pointer; color: var(--gt-color-primary); }
.gt-crumb-link:hover { text-decoration: underline; }
.gt-dn-paths { display: flex; gap: var(--gt-space-1); flex-wrap: wrap; }
.gt-dn-path-tag { font-size: var(--gt-font-size-xs); }
.gt-dn-actions { display: flex; gap: var(--gt-space-2); margin-left: auto; }
</style>
