"""Run every KELBET ARQ queue in one Railway worker service."""

from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import time
from types import FrameType

from kelbet.config import get_settings
from kelbet.observability import initialize_observability

logger = logging.getLogger(__name__)

WORKER_TARGETS = (
    "apps.worker.main.ImageWorkerSettings",
    "apps.worker.main.TextWorkerSettings",
    "apps.worker.main.VideoWorkerSettings",
    "apps.worker.main.MaintainWorkerSettings",
)


def _stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + 25
    for process in processes:
        if process.poll() is not None:
            continue
        timeout = max(deadline - time.monotonic(), 0.1)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_bundle() -> int:
    settings = get_settings()
    initialize_observability(settings, component="worker")
    arq_executable = shutil.which("arq")
    if not arq_executable:
        logger.error("worker_bundle_arq_executable_missing")
        return 127

    processes: list[subprocess.Popen[bytes]] = []
    stopping = False

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        logger.info("worker_bundle_stop_requested signal=%s", signum)
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        for target in WORKER_TARGETS:
            process = subprocess.Popen([arq_executable, target])
            processes.append(process)
            logger.info(
                "worker_bundle_process_started target=%s pid=%s",
                target,
                process.pid,
            )

        while not stopping:
            for target, process in zip(WORKER_TARGETS, processes, strict=True):
                return_code = process.poll()
                if return_code is not None:
                    logger.error(
                        "worker_bundle_process_exited target=%s code=%s",
                        target,
                        return_code,
                    )
                    return return_code or 1
            time.sleep(1)
        return 0
    finally:
        _stop_processes(processes)
        logger.info("worker_bundle_stopped")


def main() -> None:
    raise SystemExit(run_bundle())


if __name__ == "__main__":
    main()
