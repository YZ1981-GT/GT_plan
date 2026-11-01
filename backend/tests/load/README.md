# 6000 并发容量测试

该套件只允许使用 seed 回执中的真实 UUID 和专用账号池。默认只读，不得指向共享生产或开发库执行写场景。

## 配置

账号与场景可直接传 JSON，也可传 UTF-8 JSON 文件，两种方式只能选一种：

```powershell
$env:GT_LOAD_ACCOUNTS_FILE="C:/capacity/accounts.json"
$env:GT_LOAD_SCENARIOS_FILE="C:/capacity/scenarios.json"
```

`accounts.json`：

```json
[{"username":"load-001","password":"从密钥管理器注入"}]
```

`scenarios.json`：

```json
[{"project_id":"00000000-0000-0000-0000-000000000001","workpaper_id":"00000000-0000-0000-0000-000000000002","year":2025,"account_code":"1001"}]
```

写场景默认关闭。只在可销毁数据库中同时设置：

```powershell
$env:GT_LOAD_ALLOW_WRITES="1"
$env:GT_LOAD_DISPOSABLE_ENV="YES"
```

## 执行与判定

```powershell
python tests/load/run_final.py --host http://127.0.0.1:9980
```

报告只有在 100/500/1000/3000/6000 五个阶段均达到至少 90% 目标并发且请求样本大于 0 时，才允许进入性能指标判定。任一阶段缺失或零样本时脚本退出码为 2，不能用 `0ms` 判为 PASS。
