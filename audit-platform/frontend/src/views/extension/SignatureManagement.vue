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
        <el-button type="primary" @click="showLevel1 = true">
          <el-icon><Lock /></el-icon> 密码确认签名
        </el-button>
        <el-button type="success" @click="showLevel2 = true">
          <el-icon><EditPen /></el-icon> 手写签名
        </el-button>
        <el-button type="warning" @click="showLevel3 = true">
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

const objectType = ref('working_paper')
const objectId = ref('')
const showLevel1 = ref(false)
const showLevel2 = ref(false)
const showLevel3 = ref(false)
const historyRef = ref<InstanceType<typeof SignatureHistory>>()

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
