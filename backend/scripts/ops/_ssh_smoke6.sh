#!/bin/bash
# pm_service.get_inbox 的具体 SQL 错误（取完整栈中段）
journalctl -u gt-backend --since '5 minutes ago' --no-pager 2>/dev/null | grep -E "UndefinedTable|UndefinedColumn|relation|column" | tail -6
