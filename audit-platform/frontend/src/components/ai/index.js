/**
 * AI Components - 导出所有AI相关组件
 *
 * 注意：各消费方目前均直接引用具体文件，本桶导出仅作为目录索引，
 * 不要引入不存在的文件（构建会报红）。
 */

export { default as CommandConfirmCard } from './CommandConfirmCard.vue'
export { default as AIWorkpaperFill } from './WorkpaperAIFill.vue'
export { default as AIConfirmationAssistant } from './ConfirmationAIAssistant.vue'
export { default as AINLCommandInput } from './NLCommandInput.vue'
export { default as AIInsights } from './AIInsightsDashboard.vue'

// Phase 4 AI Components
export { default as ConfirmationAIPanel } from './ConfirmationAIPanel.vue'
export { default as AIContentDashboard } from './AIContentDashboard.vue'
export { default as KnowledgeBasePanel } from './KnowledgeBasePanel.vue'
export { default as DocumentOCRPanel } from './DocumentOCRPanel.vue'

// 平台级 AI 面板
export { default as PlatformAiChatPanel } from './PlatformAiChatPanel.vue'
export { default as DshPanel } from './DshPanel.vue'
export { default as ModelTable } from './ModelTable.vue'
export { default as ModelRoutePanel } from './ModelRoutePanel.vue'
export { default as AIContentReviewPanel } from './AIContentReviewPanel.vue'
