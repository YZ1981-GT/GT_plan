<template>
  <el-dialog append-to-body v-model="visible" title="手写签名 (Level 2)" width="560px" @close="onClose">
    <div class="gt-sig-canvas-wrap">
      <canvas
        ref="canvasRef"
        class="gt-sig-canvas"
        width="500"
        height="200"
        @mousedown="startDraw"
        @mousemove="draw"
        @mouseup="endDraw"
        @mouseleave="endDraw"
        @touchstart.prevent="startDrawTouch"
        @touchmove.prevent="drawTouch"
        @touchend="endDraw"
      />
      <div class="gt-sig-actions">
        <el-button size="small" @click="clearCanvas">清除</el-button>
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onSign" :loading="signing" :disabled="!hasDrawn">确认签名</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  modelValue: boolean
  objectType: string
  objectId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'signed', record: any): void
  (e: 'close'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const canvasRef = ref<HTMLCanvasElement>()
const signing = ref(false)
const isDrawing = ref(false)
const hasDrawn = ref(false)

watch(visible, (v) => {
  if (v) nextTick(() => clearCanvas())
})

function getCtx() {
  return canvasRef.value?.getContext('2d') || null
}

function startDraw(e: MouseEvent) {
  const ctx = getCtx()
  if (!ctx) return
  isDrawing.value = true
  hasDrawn.value = true
  const rect = canvasRef.value!.getBoundingClientRect()
  ctx.beginPath()
  ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top)
}

function draw(e: MouseEvent) {
  if (!isDrawing.value) return
  const ctx = getCtx()
  if (!ctx) return
  const rect = canvasRef.value!.getBoundingClientRect()
  ctx.lineWidth = 2
  ctx.lineCap = 'round'
  ctx.strokeStyle = '#1d1d1f'
  ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top)
  ctx.stroke()
}

function startDrawTouch(e: TouchEvent) {
  const touch = e.touches[0]
  const ctx = getCtx()
  if (!ctx) return
  isDrawing.value = true
  hasDrawn.value = true
  const rect = canvasRef.value!.getBoundingClientRect()
  ctx.beginPath()
  ctx.moveTo(touch.clientX - rect.left, touch.clientY - rect.top)
}

function drawTouch(e: TouchEvent) {
  if (!isDrawing.value) return
  const touch = e.touches[0]
  const ctx = getCtx()
  if (!ctx) return
  const rect = canvasRef.value!.getBoundingClientRect()
  ctx.lineWidth = 2
  ctx.lineCap = 'round'
  ctx.strokeStyle = '#1d1d1f'
  ctx.lineTo(touch.clientX - rect.left, touch.clientY - rect.top)
  ctx.stroke()
}

function endDraw() { isDrawing.value = false }

function clearCanvas() {
  const ctx = getCtx()
  if (!ctx || !canvasRef.value) return
  ctx.clearRect(0, 0, canvasRef.value.width, canvasRef.value.height)
  hasDrawn.value = false
}

async function onSign() {
  if (!canvasRef.value) return
  const signatureData = canvasRef.value.toDataURL('image/png')
  signing.value = true
  try {
    const data = await api.post('/api/signatures/sign', {
      object_type: props.objectType,
      object_id: props.objectId,
      signature_level: 'level2',
      signature_data: { image: signatureData },
    })
    ElMessage.success('手写签名成功')
    emit('signed', data)
    visible.value = false
  } catch { ElMessage.error('签名失败') }
  finally { signing.value = false }
}

function onClose() {
  clearCanvas()
  emit('close')
}
</script>

<style scoped>
.gt-sig-canvas-wrap { display: flex; flex-direction: column; align-items: center; gap: var(--gt-space-2); }
.gt-sig-canvas {
  border: 1px solid var(--gt-color-border);
  border-radius: var(--gt-radius-md);
  cursor: crosshair;
  background: #fff;
  touch-action: none;
}
.gt-sig-actions { display: flex; gap: var(--gt-space-2); }
</style>
