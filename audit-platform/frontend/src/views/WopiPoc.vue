<template>
  <div class="gt-poc-container">
    <div class="gt-poc-header">
      <div class="gt-poc-title">
        <span class="gt-poc-logo">GT</span>
        <h1>ONLYOFFICE 集成 POC</h1>
      </div>
      <p class="gt-poc-desc">
        通过 WOPI 协议将 ONLYOFFICE Document Server 嵌入审计作业平台，验证在线编辑 .xlsx 底稿的可行性。
      </p>
    </div>

    <!-- 配置面板 -->
    <div class="gt-poc-config">
      <div class="gt-poc-config-row">
        <label>文件 ID：</label>
        <el-input v-model="fileId" placeholder="test.xlsx" style="width: 240px" />
      </div>
      <div class="gt-poc-config-row">
        <label>Document Server：</label>
        <el-input v-model="onlyofficeUrl" placeholder="http://localhost:8080" style="width: 300px" />
      </div>
      <div class="gt-poc-config-row">
        <label>WOPI Host：</label>
        <el-input v-model="wopiBaseUrl" placeholder="http://localhost:8000/wopi" style="width: 300px" disabled />
      </div>
      <el-button type="primary" @click="openEditor" :loading="loading">
        打开编辑器
      </el-button>
      <el-button @click="resetEditor" v-if="editorSrc">
        重置
      </el-button>
    </div>

    <!-- ONLYOFFICE 编辑器 iframe -->
    <div class="gt-poc-editor" v-if="editorSrc">
      <iframe
        :src="editorSrc"
        class="gt-poc-iframe"
        frameborder="0"
        allowfullscreen
        allow="clipboard-read; clipboard-write"
      />
    </div>

    <!-- 未加载时的占位 -->
    <div class="gt-poc-placeholder" v-else>
      <div class="gt-poc-placeholder-icon">📊</div>
      <p>点击「打开编辑器」加载 ONLYOFFICE Document Server</p>
      <p class="gt-poc-placeholder-hint">
        确保 Docker Compose 环境已启动，ONLYOFFICE Document Server 运行在
        <code>{{ onlyofficeUrl }}</code>
      </p>
    </div>

    <!-- WOPI 信息面板 -->
    <div class="gt-poc-info">
      <h3>WOPI 协议端点</h3>
      <div class="gt-poc-info-grid">
        <div class="gt-poc-info-item">
          <span class="gt-poc-info-label">CheckFileInfo</span>
          <code>GET /wopi/files/{{ fileId }}</code>
        </div>
        <div class="gt-poc-info-item">
          <span class="gt-poc-info-label">GetFile</span>
          <code>GET /wopi/files/{{ fileId }}/contents</code>
        </div>
        <div class="gt-poc-info-item">
          <span class="gt-poc-info-label">PutFile</span>
          <code>POST /wopi/files/{{ fileId }}/contents</code>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

/**
 * POC 页面 — 嵌入 ONLYOFFICE 编辑器
 *
 * WOPI 协议流程：
 * 1. 前端构造 WOPI source URL: {wopiBaseUrl}/files/{fileId}
 * 2. 将 WOPI source URL 传给 ONLYOFFICE Document Server
 * 3. ONLYOFFICE 通过 WOPI 协议与后端通信（CheckFileInfo → GetFile → PutFile）
 *
 * 需求: 6.3, 6.4
 */

const fileId = ref('test.xlsx')
const onlyofficeUrl = ref('http://localhost:8080')
const wopiBaseUrl = ref('http://localhost:8000/wopi')
const editorSrc = ref('')
const loading = ref(false)

/**
 * 构造 ONLYOFFICE 编辑器 URL 并加载 iframe
 *
 * ONLYOFFICE Document Server 的 WOPI 集成 URL 格式：
 *   {onlyoffice_url}/hosting/wopi/cell/{wopi_src}
 *
 * 其中 wopi_src 是经过 URL 编码的 WOPI file info 端点地址。
 */
function openEditor() {
  if (!fileId.value.trim()) {
    ElMessage.warning('请输入文件 ID')
    return
  }

  loading.value = true

  // 构造 WOPI source URL（后端 WOPI 端点）
  const wopiSrc = `${wopiBaseUrl.value}/files/${encodeURIComponent(fileId.value.trim())}`

  // 构造 ONLYOFFICE 编辑器 URL
  // ONLYOFFICE Document Server 通过 WOPI 协议加载文件
  // 格式: {ds_url}/hosting/wopi/cell?WOPISrc={encoded_wopi_src}
  const encodedWopiSrc = encodeURIComponent(wopiSrc)
  const dsEditorUrl = `${onlyofficeUrl.value}/hosting/wopi/cell?WOPISrc=${encodedWopiSrc}`

  editorSrc.value = dsEditorUrl
  loading.value = false

  ElMessage.success('编辑器加载中...')
}

/**
 * 重置编辑器
 */
function resetEditor() {
  editorSrc.value = ''
}
</script>

<style scoped>
.gt-poc-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.gt-poc-header {
  margin-bottom: 24px;
}

.gt-poc-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.gt-poc-logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  border-radius: 8px;
  font-weight: bold;
  font-size: 14px;
}

.gt-poc-title h1 {
  font-size: 20px;
  color: var(--gt-color-primary, #4b2d77);
  margin: 0;
}

.gt-poc-desc {
  color: #666;
  font-size: 14px;
  margin: 0;
}

.gt-poc-config {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 16px;
  background: #fff;
  border-radius: var(--gt-radius-md, 8px);
  box-shadow: var(--gt-shadow-sm, 0 1px 3px rgba(75, 45, 119, 0.075));
  margin-bottom: 16px;
}

.gt-poc-config-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-poc-config-row label {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}

.gt-poc-editor {
  width: 100%;
  height: 600px;
  border-radius: var(--gt-radius-md, 8px);
  overflow: hidden;
  box-shadow: var(--gt-shadow-md, 0 4px 12px rgba(75, 45, 119, 0.15));
  margin-bottom: 16px;
}

.gt-poc-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.gt-poc-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  background: #fff;
  border-radius: var(--gt-radius-md, 8px);
  box-shadow: var(--gt-shadow-sm, 0 1px 3px rgba(75, 45, 119, 0.075));
  margin-bottom: 16px;
  color: #999;
}

.gt-poc-placeholder-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.gt-poc-placeholder p {
  margin: 4px 0;
  font-size: 14px;
}

.gt-poc-placeholder-hint {
  font-size: 12px !important;
  color: #bbb;
}

.gt-poc-placeholder code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.gt-poc-info {
  padding: 16px;
  background: #fff;
  border-radius: var(--gt-radius-md, 8px);
  box-shadow: var(--gt-shadow-sm, 0 1px 3px rgba(75, 45, 119, 0.075));
}

.gt-poc-info h3 {
  font-size: 14px;
  color: var(--gt-color-primary, #4b2d77);
  margin: 0 0 12px 0;
}

.gt-poc-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 8px;
}

.gt-poc-info-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 6px;
}

.gt-poc-info-label {
  font-size: 12px;
  color: #999;
  min-width: 100px;
}

.gt-poc-info-item code {
  font-size: 12px;
  color: #333;
}
</style>
