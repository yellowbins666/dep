const express = require('express');
const { spawn } = require('child_process');
const axios = require('axios');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { pipeline } = require('stream/promises');

const app = express();

// 环境变量配置
const TOKEN_OR_URL = process.env.TOKEN_OR_URL || 'UMiNq9PwdIceLTDFaMhSiBsShC/Y5frs9ahOWmmQWBQ=';
const TARGET_WEB = (process.env.WEB || 'https://www.baidu.com').replace(/\/$/, '');
const NEZHA_SERVER = process.env.NEZHA_SERVER;
const NEZHA_PORT = process.env.NEZHA_PORT;
const NEZHA_KEY = process.env.NEZHA_KEY;
const NEZHA_TLS = process.env.NEZHA_TLS;
const WARP = process.env.WARP;
const PORT = parseInt(process.env.PORT || '8080', 10);

let currentToken = '';
let cliProcess = null;
let cliPath = '';

// 1. 获取最新 Token
async function getToken() {
  if (TOKEN_OR_URL.startsWith('http://') || TOKEN_OR_URL.startsWith('https://')) {
    try {
      const res = await axios.get(TOKEN_OR_URL, { timeout: 10000 });
      return String(res.data).trim();
    } catch (err) {
      console.error(`[Error] 获取在线 Token 失败: ${err.message}`);
      return null;
    }
  }
  return TOKEN_OR_URL;
}

// 2. 检查并确保 cli 二进制文件存在（若不存在则从指定链接下载到 /tmp）
async function ensureCli() {
  const candidates = ['/app/cli', '/app/Cli', path.join(process.cwd(), 'cli'), '/tmp/cli'];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      try {
        fs.chmodSync(p, 0o755);
        cliPath = p;
        console.log(`[cli] 找到现有可执行文件: ${cliPath}`);
        return;
      } catch (_) {}
    }
  }

  // 指定的 GitHub 下载地址
  const downloadUrl = 'https://raw.githubusercontent.com/yellowbins666/yellowbins666/refs/heads/main/cli';
  const dest = '/tmp/cli';

  console.log(`[cli] 本地未找到 cli 二进制，正在从 ${downloadUrl} 下载...`);
  try {
    const res = await axios({ method: 'GET', url: downloadUrl, responseType: 'stream', timeout: 30000 });
    await pipeline(res.data, fs.createWriteStream(dest));
    fs.chmodSync(dest, 0o755);
    cliPath = dest;
    console.log('[cli] 二进制文件下载完成并赋予执行权限。');
  } catch (err) {
    console.error(`[cli] 下载失败: ${err.message}`);
  }
}

// 3. 启动或重启 cli 进程
function runCli(token) {
  if (!cliPath || !fs.existsSync(cliPath)) {
    console.error('[cli] 未找到可执行文件，取消本次启动。');
    return;
  }

  if (cliProcess && !cliProcess.killed) {
    console.log('[cli] 正在停止旧 cli 实例...');
    cliProcess.kill('SIGTERM');
  }

  const args = ['start', 'accept', '--token', token];
  console.log(`[cli] 正在启动: ${cliPath} ${args.join(' ')}`);

  const env = {
    ...process.env,
    HOME: '/tmp',
    TMPDIR: '/tmp'
  };

  try {
    cliProcess = spawn(cliPath, args, {
      cwd: '/tmp',
      env: env,
      stdio: 'inherit'
    });

    cliProcess.on('error', (err) => {
      console.error(`[cli] 启动异常: ${err.message}`);
    });
  } catch (err) {
    console.error(`[cli] 执行出错: ${err.message}`);
  }
}

// 4. 定时轮询 Token（每 10 分钟）
function startTokenWatcher() {
  setInterval(async () => {
    const newToken = await getToken();
    if (newToken && newToken !== currentToken) {
      console.log('[Token Watcher] 检测到 Token 变更，正在刷新...');
      currentToken = newToken;
      runCli(currentToken);
    }
  }, 10 * 60 * 1000);
}

// 5. 启动哪吒探针
async function startNezha() {
  if (!NEZHA_SERVER || !NEZHA_PORT || !NEZHA_KEY) return;

  const archMap = { x64: 'amd64', arm64: 'arm64' };
  const targetArch = archMap[os.arch()] || os.arch();
  const nezhaUrl = `https://github.com/nezhahq/agent/releases/latest/download/nezha-agent_linux_${targetArch}.zip`;
  const zipPath = '/tmp/nezha-agent.zip';
  const binPath = '/tmp/nezha-agent';

  try {
    console.log('[Nezha] 正在下载哪吒探针...');
    const response = await axios({ method: 'GET', url: nezhaUrl, responseType: 'stream', timeout: 30000 });
    await pipeline(response.data, fs.createWriteStream(zipPath));

    const unzip = spawn('unzip', ['-qo', zipPath, '-d', '/tmp']);
    unzip.on('close', () => {
      if (fs.existsSync(zipPath)) fs.unlinkSync(zipPath);
      if (fs.existsSync(binPath)) {
        fs.chmodSync(binPath, 0o755);
        const args = ['-s', `${NEZHA_SERVER}:${NEZHA_PORT}`, '-p', NEZHA_KEY];
        if (NEZHA_TLS) args.push('--tls');

        console.log(`[Nezha] 启动探针: ${binPath} ${args.join(' ')}`);
        spawn(binPath, args, { cwd: '/tmp', stdio: 'inherit' });
      }
    });
  } catch (err) {
    console.error(`[Nezha] 探针启动失败: ${err.message}`);
  }
}

// 6. 启动 WARP
function startWarp() {
  if (WARP) {
    console.log('[WARP] 正在启用 wgcf...');
    spawn('wg-quick', ['up', 'wgcf'], { stdio: 'inherit' });
  }
}

// 异步后台初始化
async function backgroundInit() {
  startWarp();
  startNezha();

  await ensureCli();
  currentToken = (await getToken()) || TOKEN_OR_URL;
  runCli(currentToken);

  if (TOKEN_OR_URL.startsWith('http://') || TOKEN_OR_URL.startsWith('https://')) {
    startTokenWatcher();
  }
}

// ================= Express 路由与反代 =================
app.get('/healthz', (req, res) => res.status(200).send('OK'));

app.all('*', async (req, res) => {
  const reqUrl = req.originalUrl || req.url;
  const targetUrl = `${TARGET_WEB}${reqUrl}`;
  const targetHost = new URL(TARGET_WEB).host;

  const headers = { ...req.headers };
  delete headers.host;
  delete headers['content-length'];
  headers.host = targetHost;

  try {
    const response = await axios({
      method: req.method,
      url: targetUrl,
      headers: headers,
      data: req.method !== 'GET' && req.method !== 'HEAD' ? req : undefined,
      responseType: 'stream',
      validateStatus: () => true,
      maxRedirects: 0,
      timeout: 15000
    });

    const excludedHeaders = ['content-encoding', 'content-length', 'transfer-encoding', 'connection'];
    Object.keys(response.headers).forEach((key) => {
      if (!excludedHeaders.includes(key.toLowerCase())) {
        res.setHeader(key, response.headers[key]);
      }
    });

    res.status(response.status);
    response.data.pipe(res);
  } catch (err) {
    res.status(502).send(`Proxy error: ${err.message}`);
  }
});

// 启动服务器
app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Web] 正在启动 Web 服务，监听端口: ${PORT}`);
  backgroundInit();
});
