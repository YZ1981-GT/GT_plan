/**
 * noteEdit — 附注编辑器权限与呈现模块
 *
 * Feature: partner-manager-edit-permission
 */
export { useNoteEditPermission } from './useNoteEditPermission'
export type {
  NoteEditDecision,
  NoteEditStatus,
  UseNoteEditPermissionOptions,
  UseNoteEditPermissionReturn,
} from './useNoteEditPermission'
export { presentEntry } from './noteEditPresentation'
export type { NoteEditState, PresentationResult } from './noteEditPresentation'
export { COVERAGE_SET, DRAG_SORT_PATH, matchesCoverage } from './noteEditCoverage'
export { WRITE_ENTRIES } from './noteEditWriteEntries'
export type { NoteWriteEntry } from './noteEditWriteEntries'

export { createNoteEditRequestGuard, isNoteEditGuardError, noteEditShouldRetry } from './noteEditRequestGuard'
export type { NoteEditRequestGuardReturn } from './noteEditRequestGuard'
