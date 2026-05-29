# ADR-022: 附注离线分发与一键导入

**状态**: 已采纳 (Accepted)
**日期**: 2026-05-28（v0.6.2 新增）
**Sprint**: C.0

## 背景

用户原话「最好要支持用户的离线处理 / 人机互补」：partner 集团下 50 子公司，项目组成员需离线编辑附注表样后回传，原系统无此机制。

## 决策

### 离线包格式（xlsx）

```
note_export_{project_id}_{timestamp}.xlsx
  ├ 📋 注意事项 sheet（6 节使用说明 + partner 联系人占位符）
  ├ 📑 章节清单 sheet（TOC，含完成度 / 必填 / section_id 隐藏列）
  ├ 📊 N 个章节 sheet（4 色单元格语义 + DataValidation）
  └ 🔒 _meta_ sheet（隐藏，base64+gzip 压缩 binding/formula/row_meta JSON）
```

### 4 色语义
- 黄底 = 可填（manual）
- 灰底 = 公式（formula，DataValidation 锁定）
- 红底 = 锁定（来自 wp_data/trial_balance，read-only）
- 绿底 = 必填项

### CI-21 / CI-22 PBT
- CI-21: `_meta_` sheet 必有 `section_id` + `binding_hash`
- CI-22: 导出→导入 round-trip 字段级 diff 无丢失

### 安全
- 可选 AES Fernet 加密（PBKDF2-HMAC-SHA256，100k iterations）
- 文件 SHA-256 hash 记录
- 导出权限 partner/manager / 导入权限 partner

### 一键导入
- 校验 `_meta_` sheet 存在 + section_id 列表
- 按 section_id 匹配现有章节（命中 / 缺失 / 系统多余 三态）
- 字段级 diff 算法：值/公式/manual 三类
- 章节级冲突选择：覆盖 / 保留 / 合并（cell 级勾选）/ 丢弃
- 30 天文件归档 + 审计日志

### 与其他维度联动
- D6 集团基线：lineage 元数据
- D9 协作锁：导入前自动获章节锁
- D11 版本树：导入触发新版本节点
- D13 章节序号：按 section_id 匹配（不依赖序号）
- D14 模板切换：template_type 不一致时弹警告

## 备选方案

- ❌ Word 包：动态行/列在 Word 难以追踪
- ❌ 自研格式：用户难离线编辑

## 后果

正面：
- 全面体现「人机互补」理念（用户原话）
- 50 子公司可并行离线编辑后一键导回
- xlsx 业界标准，办公软件直接打开

负面：
- 大集团回传文件多需 partner 集中处理
- 加密密码外通道发送（无法系统内传递）

## 相关 CI

- CI-21: `_meta_` sheet 必有 section_id + binding_hash
- CI-22: 导出→导入 round-trip 字段级 diff 无丢失
