/**
 * Registry 共享类型定义
 *
 * 从原 htmlRendererRegistry.ts 中提取的类型，供各领域模块复用。
 */
import type { Component } from 'vue'

/**
 * 上下文 props 策略：声明组件需要哪些上下文信息。
 * GtWpRenderer 根据此声明自动透传，新增 componentType 无需修改 if 链。
 *
 * - 'standard'  → { wp-id, project-id, wp-code, year }（绝大多数 HTML 组件）
 * - 'custom'    → { wp-generated, project-id, wp-code, year }（自定义/程序表）
 * - 'form-type' → { form-type: componentType }（D 子模式）
 * - 'none'      → {}（纯展示，无需额外上下文）
 */
export type ContextPropsStrategy = 'standard' | 'custom' | 'form-type' | 'none'

/** 注册表条目：包含 lazy component / 图标 / emits / 描述 / 上下文 props 策略 */
export interface HtmlRendererEntry {
  /** 组件类型唯一标识 */
  componentType: string
  /** lazy-loaded SFC */
  component: Component
  /** sheet tab 图标 */
  icon: string
  /** 中文名称（用于错误提示 / 文档） */
  label: string
  /** 子组件 emit 的事件列表（用于 GtWpRenderer 透传 + 测试断言） */
  emits: readonly string[]
  /**
   * 上下文 props 策略。GtWpRenderer 根据此字段自动构建 props，
   * 新增 componentType 只需设置此字段，无需修改 GtWpRenderer 的 if 链。
   * 默认 'none'（不传额外 props）。
   */
  contextProps?: ContextPropsStrategy
}
