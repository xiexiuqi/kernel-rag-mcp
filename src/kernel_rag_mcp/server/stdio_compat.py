import asyncio
import sys
import threading
from queue import Queue
from contextlib import asynccontextmanager

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
import mcp.types as types
from mcp.shared.message import SessionMessage

@asynccontextmanager
async def stdio_server_compat():
    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)
    message_queue = Queue()

    def stdin_thread():
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                if line.startswith("Content-Length:"):
                    try:
                        length = int(line.split(":", 1)[1].strip())
                    except:
                        continue
                    sys.stdin.readline()  # empty
                    body = sys.stdin.read(length)
                    if not body:
                        break
                    try:
                        msg = types.JSONRPCMessage.model_validate_json(body)
                        message_queue.put(SessionMessage(msg))
                    except Exception as exc:
                        message_queue.put(exc)
                    continue
                try:
                    msg = types.JSONRPCMessage.model_validate_json(line)
                    message_queue.put(SessionMessage(msg))
                except Exception as exc:
                    message_queue.put(exc)
        except:
            pass

    async def bridge():
        try:
            async with read_stream_writer:
                while True:
                    try:
                        msg = message_queue.get(timeout=0.1)
                        await read_stream_writer.send(msg)
                    except:
                        await asyncio.sleep(0.01)
        except:
            pass

    async def stdout():
        try:
            async with write_stream_reader:
                async for sm in write_stream_reader:
                    s = sm.message.model_dump_json(by_alias=True, exclude_none=True)
                    sys.stdout.write(s + "\n")
                    sys.stdout.flush()
        except:
            pass

    threading.Thread(target=stdin_thread, daemon=True).start()
    async with anyio.create_task_group() as tg:
        tg.start_soon(bridge)
        tg.start_soon(stdout)
        yield read_stream, write_stream
