# workpaper_sync 套件 errors 分诊

> 目标：`backend/tests/workpaper_sync/` 报告 **16 errors**（283 failures 不在本次范围）。
> 会话早期同套件只有 6 errors，故约 10 个为本会话生产代码改动引入的回归。
> 本文件采用「边查边追加」写法，随时可被截断，已写内容即为已确认结论。

## 状态

- [x] 建立 stub
- [ ] collect-only 采集
- [ ] 逐条分诊
- [ ] 修复「ours」
- [ ] 前后对比

## 采集命令

```
cwd=backend
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/ --co -q
```

## 结果

（待追加）

### 第 1 步：collect-only（2026 本会话）

```
cwd=backend
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/ --co -q
...
8611 tests collected in 24.71s
Exit Code: 0
```

**结论：0 个 collection-time error。** 16 个 error 全部是 **fixture/setup-time** 异常，
必须靠定向跑候选文件（`-rE --tb=short`）才能暴露。

### 第 2 步：候选面锁定（按改动顺序）

（待追加）

**采集策略**：`pytest tests/workpaper_sync/ --setup-only -q -rE --tb=line`
（跑 fixture、不跑用例体 ⇒ 精准暴露 setup/teardown error，且远快于 34 分钟全量）
后台进程输出落 `docs/operations/evidence/suite-triage/_setup_only.txt`。

**已排除的猜测**：
- `MaterializeOutcome(` 全仓 grep：**仅生产代码 4 处构造**（materialize_coordinator.py:1845/1954/2026/2089），
  测试侧 0 处构造 ⇒ `reuse_verdict` 必填**不是** error 簇的来源。
- 新增测试 `test_participant_leave_endpoint.py` + `test_participant_leave_pg.py`：
  `50 passed`（task 11 自测干净）。
