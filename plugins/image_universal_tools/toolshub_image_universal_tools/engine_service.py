"""Persistent, sequential connection to the isolated image engine."""

from collections import deque
import json
import queue
import subprocess
import threading

from .windows_job import KillOnCloseJob


class EngineService:
    def __init__(self, runner):
        self.runner = runner
        self._process = None
        self._responses = None
        self._threads = ()
        self._kill_job = None
        self._stderr = deque(maxlen=20)
        self._lock = threading.RLock()
        self._request_lock = threading.Lock()

    def _drain_stdout(self, process, responses):
        try:
            for line in process.stdout:
                if line.strip():
                    responses.put(line)
        finally:
            responses.put(None)

    def _drain_stderr(self, process):
        for line in process.stderr:
            if line.strip():
                with self._lock:
                    self._stderr.append(line.strip())

    def _ensure_process(self):
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return self._process, self._responses
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(
                self.runner.service_process_args(),
                cwd=self.runner.resource_root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            responses = queue.Queue()
            self._process = process
            self._responses = responses
            self._kill_job = KillOnCloseJob(process)
            self._stderr.clear()
            stdout_thread = threading.Thread(
                target=self._drain_stdout,
                args=(process, responses),
                name="image-engine-stdout",
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(process,),
                name="image-engine-stderr",
                daemon=True,
            )
            self._threads = (stdout_thread, stderr_thread)
            stdout_thread.start()
            stderr_thread.start()
            return process, responses

    def process_request(self, request_path, cancel_event, on_process):
        with self._request_lock:
            process, responses = self._ensure_process()
            on_process(process)
            try:
                process.stdin.write(request_path + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                self.stop()
                raise RuntimeError("image engine ไม่พร้อมรับงาน") from error

            while True:
                if cancel_event.wait(0.05):
                    self.stop()
                    raise InterruptedError("ยกเลิกงานแล้ว")
                try:
                    line = responses.get(timeout=0.05)
                except queue.Empty:
                    continue
                if line is None:
                    if cancel_event.is_set():
                        raise InterruptedError("ยกเลิกงานแล้ว")
                    with self._lock:
                        detail = self._stderr[-1] if self._stderr else "image engine หยุดทำงาน"
                    self.stop()
                    raise RuntimeError(detail[:500])
                try:
                    return json.loads(line)
                except json.JSONDecodeError as error:
                    self.stop()
                    raise RuntimeError("image engine ส่งผลลัพธ์ไม่ถูกต้อง") from error

    def stop(self):
        with self._lock:
            process = self._process
            threads = self._threads
            kill_job = self._kill_job
            self._process = None
            self._responses = None
            self._threads = ()
            self._kill_job = None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=1)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        if kill_job is not None:
            kill_job.close()
