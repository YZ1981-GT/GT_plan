<template>
<div class="d7-tab-procedure">
  <!-- 加载状态 -->
  <el-skeleton v-if="isLoading" :rows="6" animated />

  <template v-else>
    <!-- 编制提示 -->
    <details class="editing-hints">
      <summary>📋 编制提示</summary>
      <div class="hints-content">
        <p>本程序表列示D7合同负债底稿全部实质性程序步骤。</p>
        <p>请逐项执行审计程序，完成后标记状态并填写执行情况说明。</p>
        <p>CAS14收入准则相关：需区分合同负债与预收账款（D3），判断是否存在向客户转让商品的履约义务。</p>
        <p>凭证抽查（D7-7）需重点关注期后结转与D4营业收入的联动关系。</p>
      </div>
    </details>

    <!-- 索引跳转区 -->
    <div class="index-chips-bar">
      <span class="chip-label">相关底稿：</span>
      <GtIndexChip wp-code="D7-1" label="D7-1 审定表" />
      <GtIndexChip wp-code="D7-2" label="D7-2 明细表" />
      <GtIndexChip wp-code="D7-4" label="D7-4 分析表" />
      <GtIndexChip wp-code="D7-5" label="D7-5 账龄1年以上" />
      <GtIndexChip wp-code="D7-6" label="D7-6 关联方" />
      <GtIndexChip wp-code="D7-7" label="D7-7 凭证检查" />
      <GtIndexChip wp-code="D0" label="D0 函证" />
      <GtIndexChip wp-code="D3" label="D3 预收账款" />
      <GtIndexChip wp-code="D4" label="D4 营业收入" />
      <GtIndexChip wp-code="A1-1" label="A1-1" />
      <GtIndexChip wp-code="A1-15" label="A1-15" />
      <GtIndexChip wp-code="A1-16" label="A1-16" />
    </div>

    <!-- CAS14准则提示 -->
    <details class="cas14-hints">
      <summary>📖 CAS14 合同负债与预收账款区分</summary>
      <div class="hints-content">
        <p><strong>合同负债</strong>：企业已收或应收客户对价而应向客户转让商品的义务（适用CAS14收入准则）。</p>
        <p><strong>预收账款</strong>：不适用CAS14的预收款项（如预收租金、押金等）。</p>
        <p>判断标准：是否存在"向客户转让商品"的履约义务。</p>
        <p>相关底稿：<GtIndexChip wp-code="D3" label="→D3 预收账款" />（CAS14不适用的预收款项归入D3）</p>
      </div>
    </details>

    <!-- 程序表主体：复用 GtAProgramConsole -->
    <component
      :is="programConsole"
      v-if="programData"
      :wp-id="wpId"
      :project-id="projectId"
      :html-data="programData"
      :readonly="isReadonly"
    />

    <el-empty v-else description="暂无程序表数据，请刷新或检查底稿配置" />
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D7TabProcedure.vue — 实质性程序表 D7A (~200行)
 *
 * 复用 GtAProgramConsole componentType（selfLoad: force_component_type=a-program-console）
 * GtIndexChip跳转：D7-1/D7-2/D7-4/D7-5/D7-6/D7-7/D0/D3/D4/A1-1/A1-15/A1-16
 * CAS14准则相关程序步骤提供GtIndexChip跳转D3预收账款底稿
 * EventBus监听risk:updated更新程序步骤状态
 *
 * Task: 15.1
 * Requirements: 16.1-16.5, 17.4, 18.6, 19.6
 */
import { ref, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import http from '@/utils/http'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'

const programConsole = defineAsyncComponent(() => import('../GtAProgramConsole.vue'))

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(false)
const programData = ref<any>(null)

// ─── Self Load ───────────────────────────────────────────────────────────────

async function loadProgramData() {
  isLoading.value = true
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { force_component_type: 'a-program-console' },
    })
    const data = res.data?.data || res.data
    programData.value = data?.sheets?.[0]?.html_data || data
  } catch (err) {
    console.error('[D7TabProcedure] loadProgramData failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── EventBus: risk:updated ──────────────────────────────────────────────────

function onRiskUpdated(event: Event) {
  const detail = (event as CustomEvent).detail
  if (!detail?.affectedAccounts) return
  const accounts: string[] = detail.affectedAccounts
  if (accounts.includes('2205') || accounts.includes('合同负债')) {
    loadProgramData()
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadProgramData()
  window.addEventListener('risk:updated', onRiskUpdated)
})

onUnmounted(() => {
  window.removeEventListener('risk:updated', onRiskUpdated)
})
</script>

<style scoped>
.d7-tab-procedure {
  padding: 16px;
}

.editing-hints,
.cas14-hints {
  margin-bottom: 16px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
}

.editing-hints summary,
.cas14-hints summary {
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #409eff;
}

.hints-content {
  padding: 0 14px 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
  white-space: pre-wrap;
}

.hints-content p {
  margin: 0 0 4px;
}

.index-chips-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  margin-bottom: 16px;
}

.chip-label {
  font-size: 13px;
  color: #909399;
  margin-right: 4px;
}
</style>
