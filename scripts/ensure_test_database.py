"""Подготовить тестовую базу к прогону: создать, если нет, и очистить схему.

Зачем это нужно отдельным шагом. `tests/conftest.py` роняет схему `public`
целиком и отказывается работать, если в имени базы нет подстроки `test` — это
единственный барьер между тестами и настоящими данными. Управляемые Postgres
(Railway, RDS и подобные) создают базу с собственным именем при первой
инициализации, и переименовать её потом переменной окружения нельзя: значение
`POSTGRES_DB` читается только при первом старте контейнера.

Поэтому перед прогоном тестов база с нужным именем создаётся явно. Скрипт
идемпотентен: повторный запуск ничего не ломает и завершается успешно, чтобы
его можно было безусловно ставить первым шагом в команду CI.

Подключение для создания идёт к служебной базе (`postgres`, с откатом на
`template1`), потому что создавать базу, будучи подключённым к ней же,
невозможно.

## Почему схема ещё и очищается

Раннер запускает `alembic upgrade head` перед pytest, а фикстура `conftest`
затем дропает схему и собирает её из моделей. Если прогон умирает между этими
шагами — упал контейнер, два прогона столкнулись на одной базе, оператор
остановил деплой — база остаётся в состоянии, из которого следующий прогон уже
не выйдет сам: таблицы есть, а `alembic_version` пуст. `alembic upgrade head`
начинает с нуля и падает на `CREATE TABLE users ... already exists`, и падает
так при каждом следующем запуске, пока схему не почистят руками.

Ровно это и произошло 14 августа 2026: два прогона одновременно работали с
`kelbet_test`, после чего каждый следующий валился на первой же миграции.
Очистка схемы здесь делает прогон самовосстанавливающимся, а падение
инфраструктуры — одноразовым вместо постоянного.

Опасности в этом нет ровно по той причине, по которой её нет в `conftest`: имя
базы обязано содержать `test`, иначе скрипт завершается до подключения.
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlsplit, urlunsplit

import asyncpg

MAINTENANCE_DATABASES = ("postgres", "template1")


def target_database(url: str) -> str:
    """Имя базы из URL. Без него нечего создавать."""

    name = urlsplit(url).path.lstrip("/")
    if not name:
        raise SystemExit("В TEST_DATABASE_URL не указано имя базы")
    if "test" not in name:
        # Та же защита, что в conftest: не даём создать и затем вычистить базу,
        # которая может оказаться production. Отказываемся до подключения.
        raise SystemExit(f"Имя базы {name!r} не содержит 'test'")
    return name


def maintenance_url(url: str, database: str) -> str:
    """Тот же сервер, другая база: asyncpg не понимает драйверный префикс SQLAlchemy."""

    parts = urlsplit(url.replace("postgresql+asyncpg://", "postgresql://"))
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", "", ""))


async def create_if_missing(url: str, name: str) -> None:
    last_error: Exception | None = None

    for maintenance in MAINTENANCE_DATABASES:
        try:
            connection = await asyncpg.connect(maintenance_url(url, maintenance))
        except Exception as error:  # noqa: BLE001 — пробуем следующую служебную базу
            last_error = error
            continue

        try:
            # CREATE DATABASE не поддерживает параметризацию, поэтому имя
            # экранируется как идентификатор. Оно уже проверено на 'test'.
            await connection.execute(f'CREATE DATABASE "{name}"')
            print(f"База {name} создана")
        except asyncpg.DuplicateDatabaseError:
            print(f"База {name} уже существует")
        finally:
            await connection.close()
        return

    raise SystemExit(f"Не удалось подключиться ни к одной служебной базе: {last_error}")


async def reset_schema(url: str, name: str) -> None:
    """Привести схему к пустой, чем бы ни закончился предыдущий прогон.

    `DROP SCHEMA public CASCADE` вместо перечисления таблиц: порядок удаления по
    внешним ключам здесь неизвестен, а после аварийного прогона в схеме может
    лежать что угодно — в том числе объекты, которых нет ни в одной миграции.
    """

    connection = await asyncpg.connect(maintenance_url(url, name))
    try:
        await connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await connection.execute("CREATE SCHEMA public")
        print(f"Схема public в базе {name} очищена")
    finally:
        await connection.close()


async def ensure(url: str) -> None:
    name = target_database(url)
    await create_if_missing(url, name)
    await reset_schema(url, name)


def main() -> int:
    # Читаем переменную напрямую: TEST_DATABASE_URL не входит в Settings,
    # его так же напрямую читает tests/conftest.py.
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("TEST_DATABASE_URL не задан")
    asyncio.run(ensure(url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
