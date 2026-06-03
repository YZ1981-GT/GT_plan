---
inclusion: always
---

# RTK Token 压缩代理规则

执行 shell 命令（executePwsh）时，以下命令类型**自动加 `rtk` 前缀**以压缩输出、节省 token：

## 必须加 rtk 前缀的命令

| 类别 | 原始命令 | 改写为 |
|------|---------|--------|
| Git | `git status` / `git log` / `git diff` / `git add` / `git commit` / `git push` / `git pull` | `rtk git status` 等 |
| 测试 | `python -m pytest ...` | `rtk python -m pytest ...` |
| 测试 | `npx vitest ...` / `npx playwright test ...` | `rtk npx vitest ...` / `rtk npx playwright test ...` |
| Lint | `npx eslint ...` / `npx tsc --noEmit` | `rtk npx eslint ...` / `rtk npx tsc --noEmit` |
| 目录 | `ls` / `dir` / `tree` | `rtk ls` 等 |
| Docker | `docker ps` / `docker logs` / `docker compose ps` | `rtk docker ps` 等 |

## 不加 rtk 的例外

- 已有专用工具的操作（readFile/grepSearch/listDirectory）不经 shell，不受影响
- `git fetch` / `git stash` / `git checkout` / `git branch`（rtk 不支持或不压缩）
- 管道/重定向到文件的命令（`> file.txt`、`| Select-Object`）——rtk 可能干扰管道
- 交互式命令、长运行进程（dev server）
- `rtk gain` / `rtk --version` 等 rtk 自身命令（不要嵌套）
- 需要完整原始输出做精确解析的场景（如 `git log --oneline -1` 取 commit hash）

## 使用模式

```powershell
# 在 executePwsh 中确保 PATH 包含 rtk
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"

# 然后正常使用
rtk git status
rtk python -m pytest tests/ -v --tb=short
rtk npx vitest run src/utils/__tests__/wpFormulaPicker.spec.ts
```

## 注意事项

- Windows 原生环境无 hook 自动重写，必须手动加前缀
- rtk 对全 pass 测试输出压缩有限（正确行为——信息已够精简）
- rtk 对失败测试输出压缩显著（只保留失败项 + 摘要）
- 如果 rtk 命令失败或行为异常，去掉前缀回退到原始命令即可
