#!/bin/bash
# 勘察第二轮：已有部署详情
echo "--- 9980 谁在听 ---"
ss -tlnp | grep -E ':(9980|80|5432|6379) ' | head -8
echo "--- nginx 站点 ---"
ls /etc/nginx/sites-enabled/ 2>/dev/null
ls /etc/nginx/conf.d/ 2>/dev/null
echo "--- postgres 集群与库 ---"
sudo -u postgres psql -Atc "SELECT datname FROM pg_database WHERE datistemplate=false" 2>/dev/null | head -10
echo "--- 已有项目目录 ---"
ls -d /root/* /opt/* /srv/* /home/*/ 2>/dev/null | head -20
echo "--- pm2 / node ---"
which pm2 node npm 2>&1
pm2 list 2>/dev/null | head -8
echo "--- systemd 自定义服务 ---"
systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | grep -vE 'systemd|dbus|ssh|cron|network|getty|polkit|rsyslog|login|udev|qemu|aliyun|cloud|chrony|snap' | head -15
