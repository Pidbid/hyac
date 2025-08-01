import asyncio
import os
import re
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

# 配置日志

router = APIRouter()

# 用于从头部提取 Content-Length 的正则表达式
CONTENT_LENGTH_PATTERN = re.compile(rb"Content-Length: (\d+)\r\n")


async def read_from_pylsp(
    pylsp_process: asyncio.subprocess.Process, websocket: WebSocket
):
    """
    从 pylsp 进程的 stdout 读取 LSP 消息并转发到 WebSocket。
    """
    try:
        if not pylsp_process.stdout:
            logger.error("pylsp 进程的 stdout 未被正确初始化。")
            return

        while not pylsp_process.stdout.at_eof():
            # 1. 读取头部以获取 Content-Length
            header_buffer = b""
            while True:
                line = await pylsp_process.stdout.readline()
                if not line:
                    break
                header_buffer += line
                if b"\r\n\r\n" in header_buffer:
                    break
            
            match = CONTENT_LENGTH_PATTERN.search(header_buffer)
            if match:
                content_length = int(match.group(1))
            else:
                if header_buffer:
                    logger.warning(
                        f"无法解析 Content-Length，收到数据: {header_buffer.decode(errors='ignore')}"
                    )
                continue

            # 2. 读取消息体
            body_start_index = header_buffer.find(b"\r\n\r\n") + 4
            buffer = header_buffer[body_start_index:]
            
            body = buffer
            remaining_body_length = content_length - len(body)
            if remaining_body_length > 0:
                body += await pylsp_process.stdout.readexactly(
                    remaining_body_length
                )

            # 3. 将解析出的消息体（JSON-RPC）解码为字符串，并发送给前端
            json_rpc_string = body.decode("utf-8")
            await websocket.send_text(json_rpc_string)
            logger.info(f"pylsp -> client: {json_rpc_string.strip()}")

    except asyncio.IncompleteReadError:
        logger.info("pylsp 进程的 stdout 流已关闭。")
    except WebSocketDisconnect:
        logger.info("客户端在读取 pylsp 输出时断开连接。")
    except Exception as e:
        logger.error(f"从 pylsp 读取时发生未知错误: {e}\n{traceback.format_exc()}")
    finally:
        logger.info("读取 pylsp 输出的协程已停止。")


async def write_to_pylsp(
    pylsp_process: asyncio.subprocess.Process, websocket: WebSocket
):
    """
    从 WebSocket 读取客户端消息并写入 pylsp 进程的 stdin。
    """
    try:
        if not pylsp_process.stdin:
            logger.error("pylsp 进程的 stdin 未被正确初始化。")
            return

        async for message in websocket.iter_text():
            # 客户端发来的是JSON-RPC字符串，需要封装成LSP协议格式
            body = message.encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
            full_message = header + body

            pylsp_process.stdin.write(full_message)
            await pylsp_process.stdin.drain()
            logger.info(
                f"client -> pylsp: {full_message.decode(errors='ignore').strip()}"
            )
    except WebSocketDisconnect:
        logger.info("客户端在写入 pylsp 输入时断开连接。")
    except Exception as e:
        logger.error(f"向 pylsp 写入时发生未知错误: {e}\n{traceback.format_exc()}")
    finally:
        logger.info("写入 pylsp 输入的协程已停止。")


async def log_pylsp_stderr(pylsp_process: asyncio.subprocess.Process):
    """
    读取并记录 pylsp 进程的 stderr 输出。
    """
    if not pylsp_process.stderr:
        logger.warning("pylsp 进程的 stderr 未被正确初始化。")
        return

    while not pylsp_process.stderr.at_eof():
        line = await pylsp_process.stderr.readline()
        if line:
            logger.error(f"pylsp stderr: {line.decode(errors='ignore').strip()}")


@router.websocket("/__lsp__")
async def lsp_websocket_endpoint(websocket: WebSocket):
    """
    处理 LSP 的 WebSocket 连接，作为 pylsp 的中继。
    """
    await websocket.accept()
    logger.info("WebSocket 连接已接受。")

    pylsp_process = None
    try:
        # 1. 准备 pylsp 进程的环境
        # 将项目根目录添加到 PYTHONPATH，以便 pylsp 能找到 app 模块
        # 这使得在 _faas_context.py 中的 from app.context import ... 可以成功
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        pylsp_env = os.environ.copy()
        python_path = pylsp_env.get("PYTHONPATH", "")
        pylsp_env["PYTHONPATH"] = (
            f"{project_root}:{python_path}" if python_path else project_root
        )

        logger.info(f"Starting pylsp with PYTHONPATH: {pylsp_env['PYTHONPATH']}")

        # 2. 启动 pylsp 进程
        # 将工作目录设置为 /app，以便 pylsp 能正确解析相对导入
        pylsp_process = await asyncio.create_subprocess_exec(
            "pylsp",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/app",
            env=pylsp_env,
        )
        logger.info(
            f"pylsp 进程已启动，PID: {pylsp_process.pid}，工作目录: /app, PYTHONPATH: {pylsp_env['PYTHONPATH']}"
        )

        # 并发处理读写和错误日志任务
        reader_task = asyncio.create_task(read_from_pylsp(pylsp_process, websocket))
        writer_task = asyncio.create_task(write_to_pylsp(pylsp_process, websocket))
        stderr_task = asyncio.create_task(log_pylsp_stderr(pylsp_process))

        # 等待任一任务完成
        done, pending = await asyncio.wait(
            [reader_task, writer_task, stderr_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # 取消未完成的任务
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        logger.info("客户端主动断开连接。")
    except Exception as e:
        logger.error(
            f"处理 WebSocket 连接时发生严重错误: {e}\n{traceback.format_exc()}"
        )
    finally:
        if pylsp_process and pylsp_process.returncode is None:
            logger.info(f"正在终止 pylsp 进程 (PID: {pylsp_process.pid})...")
            pylsp_process.terminate()
            await pylsp_process.wait()
            logger.info("pylsp 进程已终止。")

        # 确保 WebSocket 连接被关闭
        if websocket.client_state != "DISCONNECTED":
            await websocket.close()
        logger.info("WebSocket 连接已关闭。")
