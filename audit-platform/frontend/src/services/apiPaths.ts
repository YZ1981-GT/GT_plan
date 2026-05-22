/**
 * API 路径集中管理 [R6.1]
 *
 * 已拆分为 apiPaths/ 子目录按业务域分组。
 * 此文件保留为向后兼容的 re-export barrel，避免破坏现有 import。
 *
 * 实际定义位于：
 *   - apiPaths/project.ts      — 项目、向导、分配
 *   - apiPaths/accounting.ts   — 试算表、调整、重要性、错报
 *   - apiPaths/report.ts       — 报表、CFS、附注、导出
 *   - apiPaths/workpaper.ts    — 底稿、模板、复核、程序
 *   - apiPaths/collaboration.ts — 人员、工时、通知、PBC、函证
 *   - apiPaths/system.ts       — 认证、用户、健康、设置、知识库
 */

export * from './apiPaths/index'
export { default } from './apiPaths/index'
