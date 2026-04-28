#!/usr/bin/env python3
"""
MCP protocol adapter: converts Content-Length (opencode) to/from newline-delimited JSON (mcp 1.27.0).
"""
import json
import subprocess
import sys
import threading


def main():
    # Force unbuffered stdout for pipe mode
    sys.stdout.reconfigure(line_buffering=True)
    
    # Start the actual MCP server
    proc = subprocess.Popen(
        [sys.executable, "-m", "kernel_rag_mcp.server.mcp_server_internal"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    def forward_client_to_server():
        """Read Content-Length from stdin, send newline-delimited to server."""
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
                    except (ValueError, IndexError):
                        continue
                    # Read empty line
                    empty = sys.stdin.readline()
                    if not empty:
                        break
                    # Read JSON body
                    body = sys.stdin.read(length)
                    if not body:
                        break
                    # Send newline-delimited JSON to server
                    proc.stdin.write(body + "\n")
                    proc.stdin.flush()
                    continue

                # Already newline-delimited
                proc.stdin.write(line + "\n")
                proc.stdin.flush()
        except Exception:
            pass
        finally:
            proc.stdin.close()

    def forward_server_to_client():
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                body = line.encode("utf-8")
                header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
                sys.stdout.buffer.write(header + body)
                sys.stdout.buffer.flush()
        except Exception:
            pass

    t1 = threading.Thread(target=forward_client_to_server, daemon=True)
    t2 = threading.Thread(target=forward_server_to_client, daemon=True)
    t1.start()
    t2.start()

    proc.wait()


if __name__ == "__main__":
    main()
