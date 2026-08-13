"""Run every KELBET ARQ queue in one Railway worker service.

Четыре очереди живут в одном сервисе, и до появления супервизора выход любой из
них означал остановку всех: цикл возвращал код выхода, `finally` завершал
остальные процессы, контейнер падал и Railway перезапускал всё сразу. Одна
сломанная очередь — например, видео, упёршееся в провайдера — уносила приём
платежей, отправку уведомлений и подметание застрявших задач.

Теперь упавший процесс перезапускается по отдельности, а остальные продолжают
работать. Сервис завершается только когда не осталось ни одной живой очереди:
это единственный случай, в котором перезапуск контейнера действительно нужен.
"""

from __future__ import annotations

import logging
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class RestartPolicy:
    """Насколько упорно перезапускать упавшую очередь.

    Бесконечный перезапуск без паузы превращает сломанную конфигурацию в
    горячий цикл, который жжёт деньги и заливает логи. Полный отказ от
    перезапуска возвращает нас к исходной неисправности. Поэтому: пауза растёт,
    а после исчерпания попыток в пределах окна очередь объявляется мёртвой —
    громко, с записью в лог, но не забирая с собой остальные.
    """

    max_restarts: int = 5
    window_seconds: float = 300.0
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0
    # Процесс, продержавшийся дольше этого, считается выздоровевшим: счётчик
    # попыток обнуляется, иначе редкие падения раз в сутки однажды исчерпали бы
    # лимит и остановили очередь навсегда.
    healthy_after_seconds: float = 60.0


@dataclass(slots=True)
class _TargetState:
    started_at: float
    failures: list[float] = field(default_factory=list)


class RestartTracker:
    """Чистая логика решения «перезапускать ли и через сколько».

    Вынесена из процессной части намеренно: решение о перезапуске — это то, что
    ломается незаметно, и его нужно проверять тестами без порождения процессов.
    """

    def __init__(self, policy: RestartPolicy | None = None) -> None:
        self._policy = policy or RestartPolicy()
        self._states: dict[str, _TargetState] = {}

    def record_start(self, target: str, now: float) -> None:
        state = self._states.get(target)
        if state is None:
            self._states[target] = _TargetState(started_at=now)
            return
        state.started_at = now

    def record_exit(self, target: str, now: float) -> float | None:
        """Пауза до перезапуска, либо None — если пора сдаться.

        None означает: эту очередь мы больше не поднимаем. Остальные при этом
        продолжают работать.
        """

        state = self._states.get(target)
        if state is None:
            state = _TargetState(started_at=now)
            self._states[target] = state

        uptime = now - state.started_at
        if uptime >= self._policy.healthy_after_seconds:
            state.failures.clear()

        window_start = now - self._policy.window_seconds
        state.failures = [at for at in state.failures if at >= window_start]
        state.failures.append(now)

        if len(state.failures) > self._policy.max_restarts:
            return None

        # Пауза растёт с числом падений подряд, но не бесконечно.
        # Основание float, а не int: mypy выводит int ** int как Any, и Any
        # затем протекает через min() в объявленный тип возврата.
        exponent = len(state.failures) - 1
        delay: float = self._policy.base_backoff_seconds * (2.0**exponent)
        return min(delay, self._policy.max_backoff_seconds)


def _stop_processes(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    for process in processes.values():
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + 25
    for process in processes.values():
        if process.poll() is not None:
            continue
        timeout = max(deadline - time.monotonic(), 0.1)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_bundle(policy: RestartPolicy | None = None) -> int:
    settings = get_settings()
    initialize_observability(settings, component="worker")
    arq_executable = shutil.which("arq")
    if not arq_executable:
        logger.error("worker_bundle_arq_executable_missing")
        return 127

    tracker = RestartTracker(policy)
    processes: dict[str, subprocess.Popen[bytes]] = {}
    # Очереди, по которым попытки исчерпаны. Держим отдельно, чтобы не пытаться
    # поднимать их снова и чтобы понимать, когда живых не осталось совсем.
    abandoned: set[str] = set()
    # Момент, с которого упавшую очередь снова можно поднимать.
    retry_at: dict[str, float] = {}
    stopping = False

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        logger.info("worker_bundle_stop_requested signal=%s", signum)
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    def spawn(target: str) -> None:
        process = subprocess.Popen([arq_executable, target])
        processes[target] = process
        tracker.record_start(target, time.monotonic())
        logger.info(
            "worker_bundle_process_started target=%s pid=%s",
            target,
            process.pid,
        )

    try:
        for target in WORKER_TARGETS:
            spawn(target)

        while not stopping:
            now = time.monotonic()

            for target in WORKER_TARGETS:
                if target in abandoned:
                    continue

                process = processes.get(target)
                if process is not None and process.poll() is None:
                    continue

                if process is not None:
                    return_code = process.returncode
                    processes.pop(target, None)
                    delay = tracker.record_exit(target, now)
                    if delay is None:
                        abandoned.add(target)
                        logger.error(
                            "worker_bundle_process_abandoned target=%s code=%s",
                            target,
                            return_code,
                        )
                        continue
                    retry_at[target] = now + delay
                    logger.error(
                        "worker_bundle_process_exited target=%s code=%s restart_in=%.1fs",
                        target,
                        return_code,
                        delay,
                    )
                    continue

                if now >= retry_at.get(target, 0.0):
                    spawn(target)

            if len(abandoned) == len(WORKER_TARGETS):
                # Живых очередей не осталось: дальше держать контейнер нет
                # смысла, пусть Railway поднимет его заново.
                logger.error("worker_bundle_all_targets_abandoned")
                return 1

            time.sleep(1)
        return 0
    finally:
        _stop_processes(processes)
        logger.info("worker_bundle_stopped")


def main() -> None:
    raise SystemExit(run_bundle())


if __name__ == "__main__":
    main()
