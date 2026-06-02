#!/usr/bin/env python3
"""ComfyUI HTTP API 客户端。"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

ProgressCallback = Callable[[dict[str, Any]], None]


class ComfyUiError(RuntimeError):
    pass


class ComfyUiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    def ping(self) -> dict[str, Any]:
        return self._get_json("/system_stats")

    def _get_json(self, path: str) -> Any:
        try:
            with urllib.request.urlopen(f"{self.base_url}{path}", timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyUiError(f"无法连接 ComfyUI {self.base_url}: {exc}") from exc

    def _post_json(self, path: str, payload: dict | None = None) -> Any:
        data = b"" if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data if payload is not None else None,
            headers={"Content-Type": "application/json"} if payload is not None else {},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ComfyUiError(f"ComfyUI HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ComfyUiError(f"无法连接 ComfyUI {self.base_url}: {exc}") from exc

    def list_checkpoints(self) -> list[str]:
        data = self._get_json("/models/checkpoints")
        return data if isinstance(data, list) else []

    def get_queue(self) -> dict[str, Any]:
        return self._get_json("/queue")

    def _prompt_queue_state(self, prompt_id: str, q: dict[str, Any] | None = None) -> tuple[str, int]:
        """返回 (running|pending|none, 排队序号 1-based)。"""
        if q is None:
            q = self.get_queue()
        for item in q.get("queue_running") or []:
            if len(item) > 1 and item[1] == prompt_id:
                return "running", 0
        for idx, item in enumerate(q.get("queue_pending") or []):
            if len(item) > 1 and item[1] == prompt_id:
                return "pending", idx + 1
        return "none", 0

    def interrupt(self) -> None:
        self._post_json("/interrupt")

    def queue_prompt(self, workflow: dict) -> str:
        result = self._post_json("/prompt", {"prompt": workflow, "client_id": self.client_id})
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise ComfyUiError(f"queue_prompt 无 prompt_id: {result}")
        return prompt_id

    def wait_prompt(
        self,
        prompt_id: str,
        *,
        timeout_s: float = 600.0,
        poll_s: float = 0.5,
        progress_cb: ProgressCallback | None = None,
        steps_hint: int = 35,
        cancel_event: threading.Event | None = None,
    ) -> dict:
        stop_ws = threading.Event()
        ws_thread: threading.Thread | None = None
        if progress_cb:
            ws_thread = threading.Thread(
                target=self._ws_progress_listener,
                args=(prompt_id, progress_cb, stop_ws),
                daemon=True,
            )
            ws_thread.start()
            progress_cb({"kind": "status", "message": "已提交队列，等待 ComfyUI…"})

        deadline = time.time() + timeout_s
        start = time.time()
        try:
            while time.time() < deadline:
                if cancel_event and cancel_event.is_set():
                    self.interrupt()
                    raise ComfyUiError("用户取消生成")

                history = self._get_json(f"/history/{prompt_id}")
                if prompt_id in history:
                    if progress_cb:
                        progress_cb(
                            {
                                "kind": "progress",
                                "value": steps_hint,
                                "max": steps_hint,
                                "message": "解码保存中…",
                            }
                        )
                    return history[prompt_id]

                if progress_cb:
                    elapsed = int(time.time() - start)
                    q = self.get_queue()
                    state, pos = self._prompt_queue_state(prompt_id, q)
                    if state == "running":
                        msg = f"ComfyUI 生成中 · {elapsed}s"
                        if elapsed >= 60:
                            msg += "（首次加载大模型可能较慢）"
                        progress_cb({"kind": "running", "message": msg, "elapsed": elapsed})
                    elif state == "pending":
                        progress_cb(
                            {
                                "kind": "queue",
                                "message": f"排队第 {pos} 位 · {elapsed}s",
                                "pending": pos,
                                "elapsed": elapsed,
                            }
                        )
                    else:
                        progress_cb(
                            {
                                "kind": "running",
                                "message": f"收尾中 · {elapsed}s",
                                "elapsed": elapsed,
                            }
                        )
                time.sleep(poll_s)
            raise ComfyUiError(f"等待超时 ({timeout_s}s): {prompt_id}")
        finally:
            stop_ws.set()
            if ws_thread:
                ws_thread.join(timeout=1.0)

    def _ws_progress_listener(
        self,
        prompt_id: str,
        progress_cb: ProgressCallback,
        stop_event: threading.Event,
    ) -> None:
        try:
            import websocket  # type: ignore[import-untyped]  # websocket-client
        except ImportError:
            return

        ws_url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/ws?clientId={self.client_id}"

        def on_message(_ws: Any, message: str) -> None:
            if stop_event.is_set():
                return
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                return
            typ = data.get("type")
            payload = data.get("data") or {}
            if payload.get("prompt_id") not in (None, prompt_id):
                return
            if typ == "progress":
                progress_cb(
                    {
                        "kind": "progress",
                        "value": int(payload.get("value", 0)),
                        "max": int(payload.get("max", 1)),
                        "message": "采样中",
                    }
                )
            elif typ == "executing":
                node = payload.get("node")
                if node:
                    progress_cb({"kind": "executing", "message": f"执行中 · 节点 {node}"})
                else:
                    progress_cb({"kind": "executing", "message": "收尾中…"})
            elif typ == "status":
                status = payload.get("status") or {}
                if status.get("exec_info", {}).get("queue_remaining") is not None:
                    progress_cb({"kind": "status", "message": "ComfyUI 就绪"})

        def on_error(_ws: Any, error: Any) -> None:
            if not stop_event.is_set():
                progress_cb({"kind": "status", "message": f"WS: {error}"})

        ws_app = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error)
        while not stop_event.is_set():
            ws_app.run_forever(ping_interval=20, ping_timeout=10)
            if stop_event.is_set():
                break
            time.sleep(0.3)

    def download_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        query = urllib.parse.urlencode(
            {"filename": filename, "subfolder": subfolder, "type": folder_type}
        )
        with urllib.request.urlopen(f"{self.base_url}/view?{query}", timeout=120) as resp:
            return resp.read()

    def upload_image(self, file_path: Path | str, *, overwrite: bool = True) -> str:
        """上传参考图到 ComfyUI input 目录，返回 LoadImage 可用的文件名。"""
        import mimetypes

        path = Path(file_path)
        if not path.is_file():
            raise ComfyUiError(f"参考图不存在: {path}")

        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
        filename = path.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        file_bytes = path.read_bytes()

        body_parts: list[bytes] = []

        def add_field(name: str, value: str) -> None:
            body_parts.append(f"--{boundary}\r\n".encode())
            body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            body_parts.append(f"{value}\r\n".encode())

        add_field("type", "input")
        add_field("overwrite", "true" if overwrite else "false")
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
        )
        body_parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        body_parts.append(file_bytes)
        body_parts.append(b"\r\n")
        body_parts.append(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=b"".join(body_parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                result = json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ComfyUiError(f"ComfyUI 上传图片 HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ComfyUiError(f"无法连接 ComfyUI {self.base_url}: {exc}") from exc

        name = result.get("name")
        if not name:
            raise ComfyUiError(f"upload_image 无 name: {result}")
        return str(name)

    def collect_output_images(self, history_entry: dict) -> list[dict[str, str]]:
        outputs = history_entry.get("outputs") or {}
        images: list[dict[str, str]] = []
        for node_out in outputs.values():
            for img in node_out.get("images") or []:
                if img.get("filename"):
                    images.append(
                        {
                            "filename": img["filename"],
                            "subfolder": img.get("subfolder") or "",
                            "type": img.get("type") or "output",
                        }
                    )
        return images


def check_connection(base_url: str) -> tuple[bool, str]:
    try:
        client = ComfyUiClient(base_url)
        stats = client.ping()
        version = stats.get("system", {}).get("comfyui_version", "?")
        ckpts = client.list_checkpoints()
        return True, f"已连接 · v{version} · {len(ckpts)} 个 checkpoint"
    except ComfyUiError as exc:
        return False, str(exc)
