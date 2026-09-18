FROM --platform=$TARGETPLATFORM traffmonetizer/cli_v2:latest AS source

FROM alpine:latest

# 安装系统运行依赖与 Node.js 环境
RUN apk add --no-cache \
    bash curl wget unzip ca-certificates \
    wireguard-tools iproute2 icu-libs krb5-libs libgcc \
    libintl libssl3 libstdc++ zlib gcompat \
    nodejs npm

WORKDIR /app

# 提取 Cli 并拷贝项目源码
COPY --from=source /usr/local/bin/cli /app/Cli
COPY package*.json /app/
RUN npm install --production

COPY index.js /app/index.js
RUN chmod +x /app/Cli

ENV PORT=8080
EXPOSE 8080

CMD ["node", "/app/index.js"]
