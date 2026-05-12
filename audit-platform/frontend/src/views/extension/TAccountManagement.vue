<template>
  <div class="gt-t-mgmt">
    <GtPageHeader title="T型账户" :show-back="false">
      <template #actions>
        <el-button type="primary" size="small" @click="showCreate = true">
          <el-icon><Plus /></el-icon> 新建T型账户
        </el-button>
        <el-button size="small" @click="loadAccounts" :loading="loading">刷新</el-button>
      </template>
    </GtPageHeader>

    <!-- T型账户列表 -->
    <el-table :data="accounts" v-loading="loading" stripe size="small" style="width: 100%"
      @row-click="selectAccount">
      <el-table-column prop="account_code" label="科目编号" width="120" />
      <el-table-column prop="account_name" label="科目名称" min-width="180" />
      <el-table-column prop="opening_balance" label="期初余额" width="140" align="right">
        <template #default="{ row }">{{ fmtAmt(row.opening_balance) }}</template>
      </el-table-column>
      <el-table-column prop="entry_count" label="分录数" width="80" align="center" />
      <el-table-column prop="net_change" label="净变动" width="140" align="right">
        <template #default="{ row }">{{ fmtAmt(row.net_change) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click.stop="openEditor(row)">编辑</el-button>
          <el-button link type="primary" size="small" @click.stop="calculate(row)">计算</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑器弹窗 -->
    <el-dialog append-to-body v-model="showEditor" :title="`T型账户 - ${currentAccount?.account_name || ''}`" width="800px" destroy-on-close>
      <div class="gt-editor-layout" v-if="currentAccount">
        <TAccountEditor
          :account-name="currentAccount.account_name"
          :account-code="currentAccount.account_code"
          :opening-balance="currentAccount.opening_balance"
          :entries="currentEntries"
        />
        <el-divider />
        <h4>添加分录</h4>
        <TAccountEntryForm @submit="addEntry" />
        <TAccountResult v-if="calcResult" :result="calcResult" />
      </div>
    </el-dialog>

    <!-- 新建弹窗 -->
    <el-dialog append-to-body v-model="showCreate" title="新建T型账户" width="500px">
      <el-form label-width="100px" size="small">
        <el-form-item label="科目编号">
          <el-input v-model="newAccount.account_code" placeholder="如 1601" />
        </el-form-item>
        <el-form-item label="科目名称">
          <el-input v-model="newAccount.account_name" placeholder="如 固定资产" />
        </el-form-item>
        <el-form-item label="期初余额">
          <el-input-number v-model="newAccount.opening_balance" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="newAccount.source" style="width: 100%">
            <el-option label="自定义" value="custom" />
            <el-option label="从模板创建" value="template" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createAccount" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import TAccountEditor from '@/components/extension/TAccountEditor.vue'
import TAccountEntryForm from '@/components/extension/TAccountEntryForm.vue'
import TAccountResult from '@/components/extension/TAccountResult.vue'
import {
  listTAccounts, getTAccount, createTAccount,
  addTAccountEntry, calculateTAccount,
} from '@/services/commonApi'
import { fmtAmount } from '@/utils/formatters'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')

const loading = ref(false)
const creating = ref(false)
const accounts = ref<any[]>([])
const showEditor = ref(false)
const showCreate = ref(false)
const currentAccount = ref<any>(null)
const currentEntries = ref<any[]>([])
const calcResult = ref<any>(null)

const newAccount = ref({
  account_code: '',
  account_name: '',
  opening_balance: 0,
  source: 'custom',
})

async function loadAccounts() {
  if (!projectId.value) return
  loading.value = true
  try {
    accounts.value = await listTAccounts(projectId.value)
  } catch { accounts.value = [] }
  finally { loading.value = false }
}

function selectAccount(row: any) {
  currentAccount.value = row
}

async function openEditor(row: any) {
  currentAccount.value = row
  calcResult.value = null
  try {
    const detail = await getTAccount(projectId.value, row.id)
    currentEntries.value = detail.entries ?? []
  } catch { currentEntries.value = [] }
  showEditor.value = true
}

async function addEntry(entry: any) {
  if (!currentAccount.value) return
  try {
    await addTAccountEntry(projectId.value, currentAccount.value.id, entry)
    ElMessage.success('分录已添加')
    const detail = await getTAccount(projectId.value, currentAccount.value.id)
    currentEntries.value = detail.entries ?? []
  } catch (e: any) { handleApiError(e, '添加') }
}

async function calculate(row: any) {
  try {
    calcResult.value = await calculateTAccount(projectId.value, row.id)
    ElMessage.success('计算完成')
  } catch (e: any) { handleApiError(e, '计算') }
}

async function createAccount() {
  if (!projectId.value) return
  creating.value = true
  try {
    await createTAccount(projectId.value, newAccount.value)
    ElMessage.success('T型账户已创建')
    showCreate.value = false
    loadAccounts()
  } catch (e: any) { handleApiError(e, '创建') }
  finally { creating.value = false }
}

const fmtAmt = fmtAmount

onMounted(loadAccounts)
</script>

<style scoped>
.gt-t-mgmt { padding: var(--gt-space-4); }
.gt-page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
.gt-header-actions { display: flex; gap: var(--gt-space-2); }
.gt-editor-layout { padding: var(--gt-space-2); }
</style>
