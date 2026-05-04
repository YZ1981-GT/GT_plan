<template>
  <div class="gt-mobile-penetration">
    <div class="gt-mp-header">
      <h3>穿透查询</h3>
      <el-tag size="small" type="info">{{ year }}年</el-tag>
    </div>

    <!-- 搜索 -->
    <el-input
      v-model="keyword"
      placeholder="搜索科目编号或名称"
      clearable
      size="large"
      style="margin-bottom: 12px"
    />

    <!-- 科目列表（单列，点击穿透） -->
    <div class="gt-mp-list">
      <div
        v-for="item in filteredItems"
        :key="item.account_code"
        class="gt-mp-item"
        @click="onDrill(item)"
      >
        <div class="gt-mp-item-top">
          <span class="gt-mp-code">{{ item.account_code }}</span>
          <span class="gt-mp-name">{{ item.account_name }}</span>
        </div>
        <div class="gt-mp-item-bottom">
          <span>期初: {{ fmtAmt(item.opening_balance) }}</span>
          <span>期末: {{ fmtAmt(item.closing_balance) }}</span>
          <el-icon :size="16" style="color: var(--gt-color-primary)"><ArrowRight /></el-icon>
        </div>
      </div>
      <div v-if="filteredItems.length === 0 && !loading" class="gt-mp-empty">
        暂无数据
      </div>
    </div>

    <!-- 明细弹窗 -->
    <el-drawer v-model="showDetail" direction="btt" size="70%" :title="`${detailCode} 序时账`">
      <div v-if="detailItems.length === 0" class="gt-mp-empty">暂无明细</div>
      <div v-for="(d, i) in detailItems" :key="i" class="gt-mp-detail-row">
        <div class="gt-mp-detail-top">
          <span>{{ d.voucher_date }}</span>
          <span>{{ d.voucher_no }}</span>
        </div>
        <div class="gt-mp-detail-mid">{{ d.summary || '—' }}</div>
        <div class="gt-mp-detail-bottom">
          <span v-if="d.debit_amount" style="color: #e6a23c">借 {{ fmtAmt(d.debit_amount) }}</span>
          <span v-if="d.credit_amount" style="color: #409eff">贷 {{ fmtAmt(d.credit_amount) }}</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { getLedgerBalance, getLedgerEntries } from '@/services/commonApi'
import { fmtAmount } from '@/utils/formatters'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear() - 1)

const loading = ref(false)
const keyword = ref('')
const items = ref<any[]>([])
const showDetail = ref(false)
const detailCode = ref('')
const detailItems = ref<any[]>([])

const filteredItems = computed(() => {
  if (!keyword.value) return items.value
  const kw = keyword.value.toLowerCase()
  return items.value.filter(r =>
    (r.account_code || '').toLowerCase().includes(kw) ||
    (r.account_name || '').toLowerCase().includes(kw)
  )
})

const fmtAmt = fmtAmount

async function loadBalance() {
  if (!projectId.value) return
  loading.value = true
  try {
    items.value = await getLedgerBalance(projectId.value, year.value)
  } catch { items.value = [] }
  finally { loading.value = false }
}

async function onDrill(item: any) {
  detailCode.value = item.account_code
  showDetail.value = true
  try {
    const result = await getLedgerEntries(projectId.value, item.account_code, year.value)
    detailItems.value = result.items ?? result ?? []
  } catch { detailItems.value = [] }
}

onMounted(loadBalance)
</script>

<style scoped>
.gt-mobile-penetration { padding: 12px; }
.gt-mp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-mp-header h3 { margin: 0; font-size: 18px; }
.gt-mp-list { display: flex; flex-direction: column; gap: 8px; }
.gt-mp-item {
  padding: 12px; border: 1px solid #eee; border-radius: 8px;
  background: #fff; cursor: pointer; transition: box-shadow 0.2s;
}
.gt-mp-item:active { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.gt-mp-item-top { display: flex; gap: 8px; margin-bottom: 6px; }
.gt-mp-code { font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
.gt-mp-name { color: #666; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-mp-item-bottom { display: flex; gap: 12px; font-size: 13px; color: #999; align-items: center; }
.gt-mp-empty { text-align: center; padding: 40px; color: #ccc; }
.gt-mp-detail-row { padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
.gt-mp-detail-top { display: flex; justify-content: space-between; font-size: 13px; color: #999; }
.gt-mp-detail-mid { margin: 4px 0; font-size: 14px; }
.gt-mp-detail-bottom { display: flex; gap: 16px; font-size: 14px; font-weight: 500; }
</style>
