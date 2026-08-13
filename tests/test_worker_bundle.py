"""Логика перезапуска очередей в bundle-воркере.

Проверяется чистая часть супервизора, без порождения процессов. Именно она
ломается незаметно: неверное решение о перезапуске не падает с ошибкой, а тихо
оставляет очередь мёртвой или уводит сервис в горячий цикл.

До появления супервизора выход любой очереди останавливал все четыре: приём
платежей и отправка уведомлений умирали вместе с видео-очередью, упёршейся в
провайдера.
"""

from __future__ import annotations

from apps.worker.bundle import WORKER_TARGETS, RestartPolicy, RestartTracker

TARGET = "apps.worker.main.VideoWorkerSettings"


def test_first_failure_restarts_after_base_backoff() -> None:
    tracker = RestartTracker(RestartPolicy(base_backoff_seconds=1.0))
    tracker.record_start(TARGET, now=0.0)

    delay = tracker.record_exit(TARGET, now=1.0)

    assert delay == 1.0


def test_backoff_grows_but_is_capped() -> None:
    # Мгновенно падающая очередь не должна превращаться в горячий цикл, но и
    # пауза не должна расти до бесконечности: сервис обязан подняться сам,
    # когда провайдер оживёт.
    policy = RestartPolicy(base_backoff_seconds=1.0, max_backoff_seconds=8.0, max_restarts=10)
    tracker = RestartTracker(policy)
    tracker.record_start(TARGET, now=0.0)

    delays = [tracker.record_exit(TARGET, now=float(step)) for step in range(1, 7)]

    assert delays == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


def test_gives_up_after_max_restarts_inside_window() -> None:
    policy = RestartPolicy(max_restarts=3, window_seconds=300.0)
    tracker = RestartTracker(policy)
    tracker.record_start(TARGET, now=0.0)

    assert tracker.record_exit(TARGET, now=1.0) is not None
    assert tracker.record_exit(TARGET, now=2.0) is not None
    assert tracker.record_exit(TARGET, now=3.0) is not None
    # Четвёртое падение в том же окне — сдаёмся по этой очереди.
    assert tracker.record_exit(TARGET, now=4.0) is None


def test_failures_outside_window_do_not_count() -> None:
    # Падение раз в час не должно однажды исчерпать лимит и остановить очередь
    # навсегда.
    policy = RestartPolicy(max_restarts=2, window_seconds=100.0, healthy_after_seconds=1e9)
    tracker = RestartTracker(policy)
    tracker.record_start(TARGET, now=0.0)

    assert tracker.record_exit(TARGET, now=10.0) is not None
    assert tracker.record_exit(TARGET, now=20.0) is not None
    # Третье падение попало бы под лимит, но два первых уже вышли из окна.
    assert tracker.record_exit(TARGET, now=500.0) is not None


def test_long_uptime_resets_failure_count() -> None:
    # Очередь, продержавшаяся дольше healthy_after_seconds, считается
    # выздоровевшей: копить ей прежние падения нельзя.
    policy = RestartPolicy(max_restarts=1, healthy_after_seconds=60.0)
    tracker = RestartTracker(policy)
    tracker.record_start(TARGET, now=0.0)

    assert tracker.record_exit(TARGET, now=1.0) is not None
    tracker.record_start(TARGET, now=1.0)
    # Прожила 200 секунд — счётчик обнуляется, и это падение снова первое.
    assert tracker.record_exit(TARGET, now=201.0) is not None


def test_targets_are_tracked_independently() -> None:
    # Смысл всей правки: сломанная очередь не влияет на остальные.
    policy = RestartPolicy(max_restarts=1)
    tracker = RestartTracker(policy)
    broken = "apps.worker.main.VideoWorkerSettings"
    healthy = "apps.worker.main.MaintainWorkerSettings"
    tracker.record_start(broken, now=0.0)
    tracker.record_start(healthy, now=0.0)

    assert tracker.record_exit(broken, now=1.0) is not None
    assert tracker.record_exit(broken, now=2.0) is None

    assert tracker.record_exit(healthy, now=3.0) is not None


def test_exit_without_recorded_start_is_handled() -> None:
    # Защита от рассинхронизации учёта: неизвестная очередь не должна валить
    # супервизор исключением.
    tracker = RestartTracker()

    assert tracker.record_exit("apps.worker.main.TextWorkerSettings", now=5.0) is not None


def test_all_four_queues_are_supervised() -> None:
    # Если очередь добавят и забудут внести сюда, тест напомнит: незаявленная
    # очередь не поднимается и не перезапускается.
    assert len(WORKER_TARGETS) == 4
    assert "apps.worker.main.MaintainWorkerSettings" in WORKER_TARGETS
