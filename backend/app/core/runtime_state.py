"""进程级运行时状态单例（内存，非持久化）。

readyz 与 GracefulShutdown 的基础设施：
- migration_state: 迁移是否完成
- shutdown_state: 是否进入 draining（排空）

# Feature: zero-downtime-deployment, Component 2
"""


class _MigrationState:
    """迁移完成状态。lifespan 在 _run_migrations() 完成后置 complete=True。"""

    def __init__(self):
        self._complete: bool = False

    def mark_complete(self):
        self._complete = True

    def is_complete(self) -> bool:
        return self._complete


class _ShutdownState:
    """排空状态。SIGTERM handler 置 draining=True。"""

    def __init__(self):
        self._draining: bool = False

    def start_draining(self):
        self._draining = True

    def is_draining(self) -> bool:
        return self._draining


# 进程级单例
migration_state = _MigrationState()
shutdown_state = _ShutdownState()
