"""
Monitoring and Status API

Provides visibility into system status, running tasks, and metrics.
"""

import asyncio
import json
import os
import psutil
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional

from utils.logger import get_logger

logger = get_logger("monitoring")


class SystemMonitor:
    """Monitor system status and provide metrics."""

    def __init__(self):
        self.logger = get_logger("system_monitor")
        self._start_time = datetime.utcnow()

    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status.

        Returns:
            Dict with system status information
        """
        try:
            # CPU and memory info
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            # Get running processes related to our system
            our_processes = []
            for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time", "memory_percent"]):
                try:
                    cmdline = proc.info["cmdline"]
                    if cmdline and any("telegram" in str(c).lower() or "daemon" in str(c).lower() or "orchestrator" in str(c).lower() for c in cmdline):
                        our_processes.append({
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "cmdline": " ".join(cmdline[-3:]),  # Last 3 args
                            "memory_percent": proc.info["memory_percent"],
                            "uptime_seconds": datetime.utcnow().timestamp() - proc.info["create_time"],
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": (datetime.utcnow() - self._start_time).total_seconds(),
                "system": {
                    "cpu_percent": cpu_percent,
                    "memory": {
                        "total_gb": round(memory.total / (1024**3), 2),
                        "available_gb": round(memory.available / (1024**3), 2),
                        "used_percent": memory.percent,
                    },
                    "disk": {
                        "total_gb": round(disk.total / (1024**3), 2),
                        "used_gb": round(disk.used / (1024**3), 2),
                        "free_gb": round(disk.free / (1024**3), 2),
                        "used_percent": disk.percent,
                    },
                },
                "processes": {
                    "count": len(our_processes),
                    "processes": our_processes[:10],  # Limit to 10
                },
            }

        except Exception as e:
            self.logger.error("Failed to get system status", error=str(e))
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

    async def get_task_queue_status(self) -> Dict[str, Any]:
        """
        Get task queue status.

        Returns:
            Dict with task queue information
        """
        try:
            from worker.task_queue import get_task_queue_manager

            queue = get_task_queue_manager()

            # Get queue size
            queue_size = await queue._get_queue_size()

            # Get Trello status
            trello_status = {}
            if queue._trello_client and queue._trello_client.is_configured():
                try:
                    todo = await queue._trello_client.get_todo_cards()
                    progress = await queue._trello_client.get_in_progress_cards()
                    review = await queue._trello_client.get_review_cards()

                    trello_status = {
                        "todo": len(todo),
                        "in_progress": len(progress),
                        "review": len(review),
                        "configured": True,
                    }
                except Exception as e:
                    trello_status = {"error": str(e), "configured": True}
            else:
                trello_status = {"configured": False}

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "queue_size": queue_size,
                "trello": trello_status,
            }

        except Exception as e:
            self.logger.error("Failed to get queue status", error=str(e))
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

    async def get_recent_activity(self, limit: int = 20) -> Dict[str, Any]:
        """
        Get recent activity from logs.

        Args:
            limit: Maximum number of log entries to return

        Returns:
            Dict with recent activity
        """
        try:
            log_file = "/home/ubuntu/logs/worker.log"

            if not os.path.exists(log_file):
                return {"entries": [], "message": "Log file not found"}

            # Read last N lines from log file
            result = subprocess.run(
                ["tail", "-n", str(limit), log_file],
                capture_output=True,
                text=True,
            )

            entries = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    entries.append(line)

            return {
                "timestamp": datetime.utcnow().isoformat(),
                "entries": entries,
                "count": len(entries),
            }

        except Exception as e:
            self.logger.error("Failed to get recent activity", error=str(e))
            return {"error": str(e), "entries": []}

    async def get_full_status(self) -> Dict[str, Any]:
        """
        Get full system status including all components.

        Returns:
            Complete status dict
        """
        system_status = await self.get_system_status()
        queue_status = await self.get_task_queue_status()
        recent_activity = await self.get_recent_activity()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system": system_status,
            "task_queue": queue_status,
            "recent_activity": recent_activity,
        }


class StatusAPI:
    """
    Simple HTTP API for status monitoring.

    Provides endpoints for checking system status.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.monitor = SystemMonitor()
        self.logger = get_logger("status_api")
        self._server = None

    async def handle_request(self, reader, writer):
        """Handle incoming HTTP requests."""
        try:
            # Read request
            data = await reader.read(1024)
            request = data.decode().strip()

            # Parse path
            path = "/"
            if "GET /" in request:
                path = "/" + request.split("GET /")[1].split(" ")[0].split("?")[0]

            # Generate response
            if path == "/status":
                response_data = await self.monitor.get_full_status()
            elif path == "/system":
                response_data = await self.monitor.get_system_status()
            elif path == "/queue":
                response_data = await self.monitor.get_task_queue_status()
            elif path == "/health":
                response_data = {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
            else:
                response_data = {"error": "Not found", "available_paths": ["/status", "/system", "/queue", "/health"]}

            # Send response
            response_body = json.dumps(response_data, indent=2, default=str)
            response = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: application/json\r\n"
                f"Access-Control-Allow-Origin: *\r\n"
                f"Content-Length: {len(response_body)}\r\n"
                f"\r\n"
                f"{response_body}"
            )

            writer.write(response.encode())
            await writer.drain()
            writer.close()

        except Exception as e:
            self.logger.error("Request handler error", error=str(e))
            writer.close()

    async def start(self):
        """Start the status API server."""
        self._server = await asyncio.start_server(
            self.handle_request,
            self.host,
            self.port,
        )

        self.logger.info(
                "Status API started",
                host=self.host,
                port=self.port,
                url=f"http://{self.host}:{self.port}",
            )

        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        """Stop the status API server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self.logger.info("Status API stopped")


import json
import subprocess


# Global instance
_system_monitor: Optional[SystemMonitor] = None


def get_system_monitor() -> SystemMonitor:
    """Get the global system monitor instance."""
    global _system_monitor
    if _system_monitor is None:
        _system_monitor = SystemMonitor()
    return _system_monitor
