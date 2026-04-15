@echo off
REM 构建 MinerU Docker 镜像

echo 下载 MinerU Dockerfile...
curl -L -o Dockerfile.mineru https://gcore.jsdelivr.net/gh/opendatalab/MinerU@master/docker/global/Dockerfile

echo 构建 MinerU 镜像...
docker build -t mineru:latest -f Dockerfile.mineru .

echo 清理 Dockerfile...
del Dockerfile.mineru

echo MinerU 镜像构建完成！
echo 使用以下命令启动服务：
echo   docker-compose -f docker-compose.mineru.yml up -d
