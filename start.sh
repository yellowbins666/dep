#!/usr/bin/env bash

# 默认在线 Token 和反代 web
TOKEN_OR_URL=UMiNq9PwdIceLTDFaMhSiBsShC/Y5frs9ahOWmmQWBQ=
grep -q "^http" <<< "$TOKEN_OR_URL" && TOKEN=$(wget -qO- "$TOKEN_OR_URL") || TOKEN=$TOKEN_OR_URL
WEB=${WEB:-'https://www.baidu.com'}
TLS=${NEZHA_TLS:+'--tls'}

# 生成 supervisor 配置文件
mkdir -p /etc/supervisor.d
cat > /etc/supervisor.d/daemon.ini << EOF
[supervisord]
user=$(whoami)
nodaemon=true
logfile=/var/log/supervisord.log
pidfile=/run/supervisord.pid

[program:cli]
command=/app/Cli start accept --token $TOKEN
autostart=true
autorestart=true
stderr_logfile=/var/log/nginx.err.log
stdout_logfile=/var/log/nginx.out.log
EOF

# 如何有 nginx 生成 nginx 配置文件
if [ "$(type -p nginx)" ]; then
  cat > /etc/nginx/nginx.conf << EOF
user  nginx;
worker_processes  auto;

#error_log  /var/log/nginx/error.log notice;
#pid        /var/run/nginx.pid;


events {
    worker_connections  1024;
}


http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    log_format  main  '\$remote_addr - \$remote_user [\$time_local] "\$request" '
                      '\$status \$body_bytes_sent "\$http_referer" '
                      '"\$http_user_agent" "\$http_x_forwarded_for"';

    #access_log  /var/log/nginx/access.log  main;

    sendfile        on;
    #tcp_nopush     on;

    keepalive_timeout  65;

    #gzip  on;

    #include /etc/nginx/conf.d/*.conf;
        
        server {
                listen               80 default_server;
                listen               [::]:80 default_server;

                server_name          _;
                charset              utf-8;
                root                 /var/lib/nginx/html;

                location / {
                        proxy_pass $WEB;
                }
        }
}
EOF

cat >> /etc/supervisor.d/daemon.ini << EOF

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
stderr_logfile=/var/log/nginx.err.log
stdout_logfile=/var/log/nginx.out.log
EOF
fi

# 如有哪吒三个参数，则安装哪吒探针；如不全则不安装
if [ -n "$NEZHA_SERVER" ] && [ -n "$NEZHA_PORT" ] && [ -n "$NEZHA_KEY" ]; then
  wget -O nezha-agent.zip https://github.com/nezhahq/agent/releases/latest/download/nezha-agent_linux_$(uname -m | sed "s#x86_64#amd64#; s#aarch64#arm64#").zip
  unzip -qod /app/ nezha-agent.zip
  rm -f nezha-agent.zip
  cat >> /etc/supervisor.d/daemon.ini << EOF

[program:nezha]
command=/app/nezha-agent -s $NEZHA_SERVER:$NEZHA_PORT -p $NEZHA_KEY $TLS
autostart=true
autorestart=true
stderr_logfile=/var/log/nezha.err.log
stdout_logfile=/var/log/nezha.out.log
EOF
fi

# 开启 warp
[ -n "$WARP" ] && wg-quick up wgcf

# 如果是在线 Token，每10分钟检测一次最新的 Token，如有变更即使用最新的
if grep -q "^http" <<< "$TOKEN_OR_URL"; then
  supervisord -c /etc/supervisord.conf 2>&1 &
  while true; do
    TOKEN_NOW=$(awk '/token/{print $NF}' /etc/supervisor.d/daemon.ini)
    TOKEN_ONLINE=$(wget -qO- "$TOKEN_OR_URL")
    if [[ "$TOKEN_NOW" != "$TOKEN_ONLINE" ]]; then
      sed -i "s#--token.*#--token $TOKEN_ONLINE#g" /etc/supervisor.d/daemon.ini
      supervisorctl reread
      supervisorctl update
      supervisorctl restart cli
    fi
    sleep 10m
  done
else
  supervisord -c /etc/supervisord.conf
fi
