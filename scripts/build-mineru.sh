#!/bin/bash
# 构建 MinerU Docker 镜像

set -e

echo "下载 MinerU Dockerfile..."
wget https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile -O Dockerfile.mineru

echo "构建 MinerU 镜像..."
docker build -t mineru:latest -f Dockerfile.mineru .

echo "清理 Dockerfile..."
rm Dockerfile.mineru

echo "MinerU 镜像构建完成！"
echo "使用以下命令启动服务："
echo "  docker-compose -f docker-compose.mineru.yml up -d"
