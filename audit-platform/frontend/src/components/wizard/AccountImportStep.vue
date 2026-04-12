<template>
  <div class="account-import-step">
    <h2 class="step-title">科目导入</h2>
    <p class="step-desc">上传客户科目表文件（Excel/CSV），系统将自动解析并导入</p>

    <!-- Upload Area -->
    <div class="upload-section">
      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx,.xls,.csv"
        :on-change="onFileChange"
        :on-exceed="onExceed"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          将文件拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 .xlsx / .xls / .csv 格式，文件需包含「科目编码」和「科目名称」列
          </div>
        </template>
      </el-upload>

      <el-button
        type="primary"
        :loading="importing"
        :disabled="!selectedFile"
        style="margin-top: 16px"
        @click="handleImport"
      >
        开始导入
      </el-button>
    </div>

    <!-- Import Result -->
    <div v-if="importResult" class="result-section">
      <el-alert
        :title="`成功导入 ${importResult.total_imported} 个科目`"
        type="success"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />

      <!-- Category Summary -->
      <div class="category-summary">
        <el-tag
          v-for="(count, cat) in importResult.by_category"
          :key="cat"
          :type="categoryTagType(cat as string)"
          size="large"
          style="margin-right: 8px; margin-bottom: 8px"
        >
          {{ categoryLabel(cat as string) }}: {{ count }}
        </el-tag>
      </div>

      <!-- Errors -->
      <el-alert
        v-if="importResult.errors.length > 0"
        title="导入警告"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #default>
          <ul class="error-list">
            <li v-for="(err, idx) in importResult.errors" :key="idx">{{ err }}</li>
          </ul>
        </template>
      </el-alert>
    </div>

    <!-- Client Chart Tree -->
    <div v-if="clientTree && Object.keys(clientTree).length > 0" class="tree-section">
      <h3 class="section-title">客户科目表</h3>
      <div v-for="(nodes, cat) in clientTree" :key="cat" class="category-group">
        <div class="category-header">
          <el-tag :type="categoryTagType(cat)" size="small">{{ categoryLabel(cat) }}</el-tag>
          <span class="category-count">{{ countNodes(nodes) }} 个科目</span>
        </div>
        <el-tree
          :data="toElTreeData(nodes)"
          :props="treeProps"
          default-expand-all
          :expand-on-click-node="false"
          class="account-tree"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span class="node-code">{{ data.account_code }}</span>
              <span class="node-name">{{ data.account_name }}</span>
              <el-tag size="small" :type="data.direction === 'debit' ? 'primary' : 'warning'">
                {{ data.direction === 'debit' ? '借' : '贷' }}
              </el-tag>
            </span>
          </template>
        </el-tree>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'
import http from '@/utils/http'
import { useWizardStore } from '@/stores/wizard'

const wizardStore = useWizardStore()
const uploadRef = ref<UploadInstance>()
const selectedFile = ref<File | null>(null)
const importing = ref(false)

interface AccountImportResult {
  total_imported: number
  by_category: Record<string, number>
  errors: string[]
}

interface AccountTreeNode {
  account_code: string
  account_name: string
  direction: string
  level: number
  category: string
  parent_code: string | null
  children: AccountTreeNode[]
}

const importResult = ref<AccountImportResult | null>(null)
const clientTree = ref<Record<string, AccountTreeNode[]> | null>(null)

const treeProps = {
  children: 'children',
  label: 'account_name',
}

const CATEGORY_LABELS: Record<string, string> = {
  asset: '资产类',
  liability: '负债类',
  equity: '权益类',
  revenue: '收入类',
  expense: '费用类',
}

const CATEGORY_TAG_TYPES: Record<string, string> = {
  asset: '',
  liability: 'warning',
  equity: 'success',
  revenue: 'primary',
  expense: 'danger',
}

function categoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] || cat
}

function categoryTagType(cat: string): string {
  return CATEGORY_TAG_TYPES[cat] || ''
}

function countNodes(nodes: AccountTreeNode[]): number {
  let count = 0
  for (const n of nodes) {
    count += 1
    if (n.children) count += countNodes(n.children)
  }
  return count
}

function toElTreeData(nodes: AccountTreeNode[]): Record<string, unknown>[] {
  return nodes.map((n) => ({
    account_code: n.account_code,
    account_name: n.account_name,
    direction: n.direction,
    level: n.level,
    children: n.children ? toElTreeData(n.children) : [],
  }))
}

function onFileChange(file: UploadFile) {
  selectedFile.value = file.raw || null
}

function onExceed() {
  ElMessage.warning('只能上传一个文件，请先移除已选文件')
}

async function handleImport() {
  if (!selectedFile.value || !wizardStore.projectId) return

  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/account-chart/import`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    const result: AccountImportResult = data.data ?? data
    importResult.value = result
    ElMessage.success(`成功导入 ${result.total_imported} 个科目`)

    // Save step data
    await wizardStore.saveStep('account_import', {
      total_imported: result.total_imported,
      by_category: result.by_category,
    })

    // Load client tree
    await loadClientTree()
  } catch {
    // Error handled by http interceptor
  } finally {
    importing.value = false
  }
}

async function loadClientTree() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/account-chart/client`,
    )
    clientTree.value = data.data ?? data
  } catch {
    // Silently fail
  }
}

onMounted(async () => {
  // If step already completed, load existing data
  if (wizardStore.projectId && wizardStore.isStepCompleted('account_import')) {
    const saved = wizardStore.stepData.account_import as Record<string, unknown> | undefined
    if (saved) {
      importResult.value = {
        total_imported: (saved.total_imported as number) || 0,
        by_category: (saved.by_category as Record<string, number>) || {},
        errors: [],
      }
    }
    await loadClientTree()
  }
})
</script>

<style scoped>
.account-import-step {
  max-width: 800px;
  margin: 0 auto;
}

.step-title {
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-1);
  font-size: 20px;
}

.step-desc {
  color: #999;
  margin-bottom: var(--gt-space-6);
  font-size: 14px;
}

.upload-section {
  margin-bottom: var(--gt-space-6);
}

.upload-area {
  width: 100%;
}

.result-section {
  margin-bottom: var(--gt-space-6);
}

.category-summary {
  margin-bottom: var(--gt-space-4);
}

.error-list {
  margin: 0;
  padding-left: 20px;
}

.tree-section {
  margin-top: var(--gt-space-4);
}

.section-title {
  font-size: 16px;
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-4);
}

.category-group {
  margin-bottom: var(--gt-space-4);
  border: 1px solid #eee;
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-3);
}

.category-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--gt-space-2);
  padding-bottom: var(--gt-space-2);
  border-bottom: 1px solid #f0f0f0;
}

.category-count {
  color: #999;
  font-size: 13px;
}

.account-tree {
  background: transparent;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.node-code {
  color: var(--gt-color-primary);
  font-family: monospace;
  min-width: 60px;
}

.node-name {
  color: #333;
}
</style>
