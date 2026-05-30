# 设计文档：底稿性能与虚拟滚动

## 概述
HTML 渲染器几乎无虚拟滚动（只有组件 lazy load），大底稿（>500 行）全量 DOM 渲染会卡。TrialBalance 已有 el-table-v2 虚拟滚动（>1000 行），但底稿渲染器没复用。6000 并发目标下必须解决。

## 核心设计
- HTML 渲染器表格类组件（c-note-table / d-form-table / g-generic-table）接入 el-table-v2 条件虚拟化（>500 行启用）
- 抽凭表/明细表大数据场景分页或虚拟滚动
- 性能基准：HTML 冷启动 <50ms / 500 行表格渲染 <200ms / 滚动 60fps

## 不在范围
- 不改 Univer 性能（已有自己的虚拟化）
- 不做 6000 并发全链路压测（独立 UAT）
