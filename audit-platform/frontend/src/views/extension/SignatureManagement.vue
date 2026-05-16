<template>
  <div class="gt-sig-mgmt">
    <GtPageHeader title="签字管理" :show-back="false" />

    <!-- 对象选择 -->
    <el-card shadow="never" class="gt-sig-selector">
      <el-form :inline="true" size="small">
        <el-form-item label="对象类型">
          <el-select v-model="objectType" style="width: 160px" @change="loadHistory">
            <el-option label="工作底稿" value="working_paper" />
            <el-option label="调整分录" value="adjustment" />
            <el-option label="审计报告" value="audit_report" />
          </el-select>
        </el-form-item>
        <el-form-item label="对象ID">
          <el-input v-model="objectId" placeholder="输入对象ID" style="width: 280px" @keyup.enter="loadHistory" />
        </el-form-item>
        <el-form-item>
          <el-button @click="loadHistory">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 签名操作 -->
    <el-card shadow="never" class="gt-sig-actions-card" v-if="objectId">
      <template #header><span>签名操作</span></template>
      <div class="gt-sig-btns">
        <el-button type="primary" @click="onClickLevel1">
          <el-icon><Lock /></el-icon> 密码确认签名
        </el-button>
        <el-button type="success" @click="onClickLevel2">
          <el-icon><EditPen /></el-icon> 手写签名
        </el-button>
        <el-button type="warning" @click="onClickLevel3">
          <el-icon><Key /></el-icon> CA证书签名
        </el-button>
      </div>
    </el-card>

    <!-- 签名历史 -->
    <el-card shadow="never" class="gt-sig-history-card" v-if="objectId">
      <template #header><span>签名历史</span></template>
      <SignatureHistory :object-type="objectType" :object-id="objectId" ref="historyRef" />
    </el-card>

    <!-- 签名弹窗 -->
    <SignatureLevel1 v-model="showLevel1" :object-type="objectType" :object-id="objectId" @signed="onSigned" />
    <SignatureLevel2 v-model="showLevel2" :object-type="objectType" :object-id="objectId" @signed="onSigned" />
    <SignatureLevel3 v-model="showLevel3" :object-type="objectType" :object-id="objectId" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Lock, EditPen, Key } from '@element-plus/icons-vue'
import SignatureLevel1 from '@/components/extension/SignatureLevel1.vue'
import SignatureLevel2 from '@/components/extension/SignatureLevel2.vue'
import SignatureLevel3 from '@/components/extension/SignatureLevel3.vue'
import SignatureHistory from '@/components/extension/SignatureHistory.vue'
import { confirmSign } from '@/utils/confirm'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

const authStore = useAuthStore()
const projectStore = useProjectStore()

const objectType = ref('working_paper')
const objectId = ref('')
const showLevel1 = ref(false)
const showLevel2 = ref(false)
const showLevel3 = ref(false)
const historyRef = ref<InstanceType<typeof SignatureHistory>>()

const objectTypeLabel: Record<string, string> = {
  working_paper: '工作底稿',
  adjustment: '调整分录',
  audit_report: '审计报告',
}

async function _confirmAndOpen(level: 1 | 2 | 3) {
  const action = level === 1 ? '密码确认签名' : level === 2 ? '手写签名' : 'CA 证书签名'
  try {
    await confirmSign(action, {
      userName: authStore.user?.full_name || authStore.user?.username || '当前用户',
      projectName: projectStore.clientName || projectStore.projectId || '当前项目',
      objectName: `${objectTypeLabel[objectType.value] || objectType.value} ${objectId.value}`,
    })
  } catch {
    return
  }
  if (level === 1) showLevel1.value = true
  else if (level === 2) showLevel2.value = true
  else showLevel3.value = true
}

function onClickLevel1() { _confirmAndOpen(1) }
function onClickLevel2() { _confirmAndOpen(2) }
function onClickLevel3() { _confirmAndOpen(3) }

function loadHistory() {
  // SignatureHistory watches props, triggers automatically
}

function onSigned() {
  // Reload history after signing
  loadHistory()
}
</script>

<style scoped>
.gt-sig-mgmt { padding: var(--gt-space-4); display: flex; flex-direction: column; gap: var(--gt-space-4); }
.gt-page-header { margin-bottom: 0; }
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
.gt-sig-selector { border-radius: var(--gt-radius-md); }
.gt-sig-actions-card { border-radius: var(--gt-radius-md); }
.gt-sig-btns { display: flex; gap: var(--gt-space-3); }
.gt-sig-history-card { border-radius: var(--gt-radius-md); }
</style>
