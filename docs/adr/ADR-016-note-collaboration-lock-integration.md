# ADR-016: 附注章节级协作锁集成

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28
**Sprint**: A.6

## 背景

`note_section_lock` 表已建（disclosure-note-full-revamp Sprint 7），但未在动态行/列编辑、集团基线 apply、auto_trim_v2、模板切换等关键入口集成。

## 决策

新建 `note_lock_integration.py`：
- `note_section_lock`: 单章节 context manager
- `note_batch_lock`: 多章节批量锁

集成入口（4 处）：
1. 动态行/列编辑（NoteSectionLockService.acquire 前置）
2. 集团基线 apply
3. auto_trim_v2 章节裁剪
4. 模板切换（D14 SOE↔Listed）

约束：
- 锁粒度：章节级 section_id
- 超时：300s
- 冲突：抛 `HTTPException(409)`
- batch 逐一获锁，任一失败释放已获取（CI-13）

## 备选方案

- ❌ 全表锁：粒度太粗
- ❌ Cell 级锁：粒度太细，性能差

## 后果

正面：
- 多人协作避免覆盖冲突
- 与离线导入集成（D15 导入前自动获锁）
- finally 必释放保证可靠性

负面：
- lazy import patch 路径需注意（patch 实际路径而非调用方）

## 相关 CI

- CI-13: 锁释放必触发
