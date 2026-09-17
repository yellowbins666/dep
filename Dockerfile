FROM --platform=$TARGETPLATFORM traffmonetizer/cli_v2:latest AS source

FROM alpine:latest

# 1. 安装运行环境及 Python 库
RUN apk add --no-cache \
    bash curl wget unzip ca-certificates \
    wireguard-tools iproute2 icu-libs krb5-libs libgcc \
    libintl libssl3 libstdc++ zlib gcompat \
    python3 py3-pip && \
    pip3 install --no-cache-dir --break-system-packages flask requests

WORKDIR /app

# 2. 提取并配置二进制与代码
COPY --from=source /usr/local/bin/cli /app/Cli
COPY app.py /app/app.py
RUN chmod +x /app/Cli

EXPOSE 80

CMD ["python3", "/app/app.py"]
