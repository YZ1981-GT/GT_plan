/**
 * Trace 模块导出
 *
 * Feature: platform-global-hardening
 */
export { default as TraceDrawer } from './TraceDrawer.vue'
export { useTraceData } from './useTraceData'
export type { TraceNode, UseTraceDataReturn } from './useTraceData'
export { useTraceEntry, openTrace, closeTrace, setTraceProjectId } from './useTraceEntry'
export type { TraceEntryState } from './useTraceEntry'
