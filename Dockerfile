FROM --platform=$TARGETPLATFORM traffmonetizer/cli_v2:latest AS source

FROM alpine:latest

# 1. 安装基础工具、C 运行时兼容库、Python3 和必要依赖
RUN apk add --no-cache \
    bash curl wget unzip ca-certificates \
    wireguard-tools iproute2 icu-libs krb5-libs libgcc \
    libintl libssl3 libstdc++ zlib gcompat \
    python3 py3-pip && \
    pip3 install --no-cache-dir --break-system-packages flask requests

WORKDIR /app

# 2. 从官方镜像复制 Cli 二进制，并拷入 Python 脚本
COPY --from=source /usr/local/bin/cli /app/Cli
COPY app.py /app/app.py

RUN chmod +x /app/Cli /app/app.py

# 3. 开放 8080 端口，并设置环境变量默认值为 8080
ENV PORT=8080
EXPOSE 8080

CMD ["python3", "/app/app.py"]
