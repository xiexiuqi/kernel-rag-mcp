import asyncio
import json
import sys
from contextlib import asynccontextmanager

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
import mcp.types as types
from mcp.shared.message import SessionMessage


@asynccontextmanager
async def stdio_server_compat():
    """
    Stdio transport compatible with both Content-Length and newline-delimited JSON.
    """
    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    async def stdin_reader():
        try:
            async with read_stream_writer:
                stdin = anyio.wrap_file(sys.stdin)
                while True:
                    try:
                        line = await stdin.readline()
                    except anyio.EndOfStream:
                        break
                    if not line:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    # Try Content-Length format
                    if line.startswith("Content-Length:"):
                        try:
                            length = int(line.split(":", 1)[1].strip())
                        except (ValueError, IndexError):
                            continue
                        # Read the empty line
                        empty = await stdin.readline()
                        if empty is None:
                            break
                        # Read the JSON body
                        body = await stdin.read(length)
                        if not body:
                            break
                        try:
                            message = types.JSONRPCMessage.model_validate_json(body)
                            session_message = SessionMessage(message)
                            await read_stream_writer.send(session_message)
                        except Exception as exc:
                            await read_stream_writer.send(exc)
                        continue

                    # Try newline-delimited JSON
                    try:
                        message = types.JSONRPCMessage.model_validate_json(line)
                        session_message = SessionMessage(message)
                        await read_stream_writer.send(session_message)
                    except Exception as exc:
                        await read_stream_writer.send(exc)
        except anyio.ClosedResourceError:
            pass
        except Exception:
            pass

    async def stdout_writer():
        try:
            async with write_stream_reader:
                stdout = anyio.wrap_file(sys.stdout)
                async for session_message in write_stream_reader:
                    json_str = session_message.message.model_dump_json(by_alias=True, exclude_none=True)
                    # Use newline-delimited JSON for output
                    await stdout.write(json_str + "\n")
                    await stdout.flush()
        except anyio.ClosedResourceError:
            pass
        except Exception:
            pass

    async with anyio.create_task_group() as tg:
        tg.start_soon(stdin_reader)
        tg.start_soon(stdout_writer)
        yield read_stream, write_stream
