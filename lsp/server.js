const WebSocket = require('ws');
const { spawn } = require('child_process');
const url = require('url');
const fs = require('fs');
const path = require('path');

const PORT = 8765;
// 我们需要能够处理请求，所以我们将 http 服务器附加到 wss
const server = require('http').createServer();
const wss = new WebSocket.Server({ noServer: true });

const WORKSPACE_ROOT = '/workspace'; // Pyright 将在这个目录下工作

// 确保工作区根目录存在
if (!fs.existsSync(WORKSPACE_ROOT)) {
    fs.mkdirSync(WORKSPACE_ROOT, { recursive: true });
}

server.on('upgrade', (request, socket, head) => {
    const pathname = url.parse(request.url).pathname;
    const sessionId = url.parse(request.url, true).query.sessionId;

    if (!sessionId) {
        socket.destroy();
        return;
    }

    if (pathname === '/') {
        wss.handleUpgrade(request, socket, head, (ws) => {
            wss.emit('connection', ws, request, sessionId);
        });
    } else {
        socket.destroy();
    }
});


wss.on('connection', (ws, request, sessionId) => {
    console.log(`新会话连接: ${sessionId}`);

    const sessionWorkspace = path.join(WORKSPACE_ROOT, sessionId);
    if (!fs.existsSync(sessionWorkspace)) {
        fs.mkdirSync(sessionWorkspace, { recursive: true });
    }

    const langServerPath = '/usr/local/bin/pyright-langserver';
    const langServer = spawn(langServerPath, ['--stdio'], {
        cwd: sessionWorkspace, // 为 pyright 设置工作目录
        stdio: ['pipe', 'pipe', 'inherit']
    });

    langServer.on('error', (err) => {
        console.error(`[${sessionId}] Pyright 语言服务器启动失败: ${err.message}`);
        ws.close();
    });

    // --- LSP 协议处理 ---

    // 1. 处理从前端发往 LSP 的消息
    ws.on('message', (messageStr) => {
        const message = JSON.parse(messageStr);

        // 核心改动：拦截 didChange 通知，并将其内容写入文件
        if (message.method === 'textDocument/didChange' && message.params.contentChanges) {
            const uri = message.params.textDocument.uri;
            const filePath = url.fileURLToPath(uri);
            const relativePath = path.relative(sessionWorkspace, filePath);

            // 安全检查
            if (relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
                console.error(`[${sessionId}] 检测到非法文件路径访问: ${filePath}`);
                return;
            }
            
            const content = message.params.contentChanges[0].text;
            
            // 异步写入文件
            fs.writeFile(filePath, content, 'utf8', (err) => {
                if (err) {
                    console.error(`[${sessionId}] 写入文件失败: ${err}`);
                } else {
                    console.log(`[${sessionId}] 文件已更新: ${filePath}`);
                }
            });
            // **关键修复**: 消费掉 didChange 事件，不再转发给 pyright
            // pyright 会通过监视文件系统来感知变化
            return;
        }
        
        // 其他所有消息都需要包装后发给 pyright
        const lspMessage = `Content-Length: ${Buffer.byteLength(messageStr, 'utf-8')}\r\n\r\n${messageStr}`;
        if (langServer.stdin.writable) {
            langServer.stdin.write(lspMessage);
        }
    });

    // 2. 处理从 LSP 发往前端的消息
    let stdoutBuffer = Buffer.alloc(0);
    langServer.stdout.on('data', (chunk) => {
        stdoutBuffer = Buffer.concat([stdoutBuffer, chunk]);
        while (true) {
            const headerMatch = stdoutBuffer.toString('ascii').match(/^Content-Length: (\d+)\r\n\r\n/);
            if (!headerMatch) {
                break; // 头部不完整，等待更多数据
            }

            const contentLength = parseInt(headerMatch[1], 10);
            const headerLength = headerMatch[0].length;
            const messageLength = headerLength + contentLength;

            if (stdoutBuffer.length < messageLength) {
                break; // 消息体不完整，等待更多数据
            }

            const messageBody = stdoutBuffer.slice(headerLength, messageLength);
            stdoutBuffer = stdoutBuffer.slice(messageLength);

            if (ws.readyState === WebSocket.OPEN) {
                // 将纯净的 JSON 消息体发送给前端
                ws.send(messageBody.toString('utf-8'));
            }
        }
    });

    // 清理资源
    ws.on('close', () => {
        if (!langServer.killed) {
            langServer.kill('SIGTERM');
        }
    });

    langServer.on('close', (code) => {
        console.log(`[${sessionId}] Pyright 语言服务器退出，代码: ${code}`);
        if (ws.readyState === WebSocket.OPEN) {
            ws.close();
        }
    });
});

server.listen(PORT, () => {
    console.log(`LSP WebSocket 服务器在端口 ${PORT} 上运行`);
});
