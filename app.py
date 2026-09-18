import os
import sys
import pty
import fcntl
import termios
import struct
import json
import base64
import secrets
import asyncio
import urllib.request
import platform
from aiohttp import web

# ==================== 工作目录设置 ====================
# 设置全局工作目录为 /tmp
WORKDIR = "/tmp"
try:
    os.chdir(WORKDIR)
except Exception as e:
    print(f"Warning: Failed to change directory to {WORKDIR}: {e}")

# ==================== 配置区域 ====================
PORT = int(os.environ.get("SERVER_PORT", os.environ.get("PORT", 18080)))
TERMINAL_PATH = os.environ.get("TERMINAL_PATH", "/ssh")
ARGO_AUTH = os.environ.get("ARGO_AUTH", "eyJhIjoiOGU1YzU5MDRmNjU3ODcwOWQ5MzM1NDk4YzFjZTQ1MTIiLCJ0IjoiMTBlOGZjZjMtMzY4YS00OGQyLTlmYzMtYTQ3MWMxMDVmNGM4IiwicyI6Ik56VXhaall3T0dZdE1UUXhZaTAwTkdRMkxUbGhOakF0TWpkak9EUTRaalprTXpSbCJ9")
ARGO_DOMAIN = os.environ.get("ARGO_DOMAIN", "infrlo.yellowbinss.dpdns.org")

WEB_USER = os.environ.get("WEB_USER", "admin")
WEB_PASS = os.environ.get("WEB_PASS", "123456")

# 内存 Session 存储用于 Cookie 鉴权
VALID_SESSIONS = set()
# =================================================

# 保持 index.html 引用脚本所在目录的绝对路径，避免切换目录后失效
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "index.html")

TERMINAL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terminal Console</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css" />
    <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #121212; color: #fff; height: 100vh; display: flex; flex-direction: column; font-family: monospace; }
        header { background: #1e1e1e; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #333; }
        #terminal-container { flex: 1; padding: 8px; background: #000; overflow: hidden; }
    </style>
</head>
<body>
    <header>
        <span style="color:#4af626; font-weight:bold; font-size:15px;">Argo Console</span>
        <span id="conn-status" style="font-size:12px; color:#aaa;">Connecting...</span>
    </header>
    <div id="terminal-container"></div>
    <script>
        const term = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: 'Consolas, Monaco, "Courier New", monospace',
            theme: { background: '#000000', foreground: '#ffffff' }
        });
        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal-container'));
        fitAddon.fit();

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket(`${protocol}//${window.location.host}""" + TERMINAL_PATH + """/ws`);
        const statusEl = document.getElementById('conn-status');

        function sendResize() {
            if (socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({
                    type: "resize",
                    cols: term.cols,
                    rows: term.rows
                }));
            }
        }

        window.addEventListener('resize', () => {
            fitAddon.fit();
            sendResize();
        });

        socket.onopen = () => {
            statusEl.textContent = 'Connected';
            statusEl.style.color = '#4af626';
            term.focus();
            sendResize();
        };

        socket.onmessage = (e) => {
            term.write(e.data);
        };

        socket.onclose = (e) => {
            statusEl.textContent = 'Disconnected';
            statusEl.style.color = '#ff5555';
            term.write('\\r\\n\\x1b[31m[Connection closed (Code: ' + e.code + ')]\\x1b[0m\\r\\n');
        };

        socket.onerror = () => {
            statusEl.textContent = 'Error';
            statusEl.style.color = '#ff5555';
        };

        term.onData(data => {
            if (socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "input", data: data }));
            }
        });
    </script>
</body>
</html>"""

def get_cf_arch():
    arch = platform.machine().lower()
    if "aarch64" in arch or "arm64" in arch:
        return "arm64"
    elif "arm" in arch:
        return "arm"
    return "amd64"

def download_cloudflared():
    if not os.path.exists("./cloudflared"):
        cf_arch = get_cf_arch()
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{cf_arch}"
        try:
            print(f"Downloading cloudflared for {cf_arch} into {os.getcwd()}...")
            urllib.request.urlretrieve(url, "./cloudflared")
            os.chmod("./cloudflared", 0o755)
            print("cloudflared downloaded successfully.")
        except Exception as e:
            print(f"Failed to download cloudflared: {e}")

async def start_argo():
    download_cloudflared()
    if not os.path.exists("./cloudflared"):
        return

    token = ARGO_AUTH
    if "eyJh" in token:
        token = token[token.find("eyJh"):]

    if token:
        cmd = ["./cloudflared", "tunnel", "--no-autoupdate", "run", "--token", token]
    else:
        cmd = ["./cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"]

    try:
        await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=WORKDIR
        )
        print("cloudflared process started.")
    except Exception as e:
        print(f"Failed to run cloudflared: {e}")

def is_authenticated(request):
    if not WEB_USER or not WEB_PASS:
        return True

    # 1. 检查 Session Cookie
    session_id = request.cookies.get("AUTH_SESSION")
    if session_id and session_id in VALID_SESSIONS:
        return True

    # 2. 检查 HTTP Basic Auth
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            raw = base64.b64decode(auth[6:]).decode("utf-8")
            u, p = raw.split(":", 1)
            if u == WEB_USER and p == WEB_PASS:
                return True
        except Exception:
            pass

    return False

async def handle_index(request):
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    return web.Response(text="<h1>Node Operational</h1>", content_type="text/html")

async def handle_terminal_page(request):
    if not is_authenticated(request):
        return web.Response(
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Node Console"'},
            text="Unauthorized"
        )

    response = web.Response(text=TERMINAL_HTML, content_type="text/html")

    # 验证通过后下发 Session Cookie 供随后的 WebSocket 复用
    session_id = secrets.token_hex(16)
    VALID_SESSIONS.add(session_id)
    response.set_cookie("AUTH_SESSION", session_id, max_age=86400, httponly=True, samesite="Lax")
    return response

def set_pty_size(fd, rows, cols):
    try:
        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
    except Exception:
        pass

async def handle_ws(request):
    if not is_authenticated(request):
        return web.Response(status=401, text="Unauthorized WebSocket")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    master_fd, slave_fd = pty.openpty()
    shell = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"

    env = dict(os.environ)
    env["TERM"] = "xterm-256color"

    proc = await asyncio.create_subprocess_exec(
        shell,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        cwd=WORKDIR,
        preexec_fn=os.setsid
    )
    os.close(slave_fd)

    # 设为非阻塞模式
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    loop = asyncio.get_running_loop()

    # 从 PTY 读取数据推送到 WebSocket
    async def pty_to_ws():
        read_event = asyncio.Event()
        loop.add_reader(master_fd, read_event.set)
        try:
            while True:
                await read_event.wait()
                read_event.clear()
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    await ws.send_str(data.decode("utf-8", errors="ignore"))
                except (BlockingIOError, InterruptedError):
                    continue
                except OSError:
                    # 终端退出产生 EIO 错误
                    break
        finally:
            loop.remove_reader(master_fd)

    pty_task = asyncio.create_task(pty_to_ws())

    # 从 WebSocket 接收输入写入 PTY
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                    msg_type = payload.get("type")
                    if msg_type == "input":
                        os.write(master_fd, payload.get("data", "").encode("utf-8"))
                    elif msg_type == "resize":
                        cols = int(payload.get("cols", 80))
                        rows = int(payload.get("rows", 24))
                        set_pty_size(master_fd, rows, cols)
                except json.JSONDecodeError:
                    os.write(master_fd, msg.data.encode("utf-8"))
            elif msg.type == web.WSMsgType.BINARY:
                os.write(master_fd, msg.data)
    except Exception:
        pass
    finally:
        pty_task.cancel()
        try:
            os.close(master_fd)
        except OSError:
            pass
        if proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        await ws.close()

    return ws

app = web.Application()
app.router.add_get("/", handle_index)
app.router.add_get(TERMINAL_PATH, handle_terminal_page)
app.router.add_get(f"{TERMINAL_PATH}/ws", handle_ws)

async def on_startup(app_instance):
    asyncio.create_task(start_argo())

app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=PORT)
