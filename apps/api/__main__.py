import os

import uvicorn

from kelbet.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "apps.api.main:create_app",
        factory=True,
        host=settings.api_host,
        port=int(os.getenv("PORT", str(settings.api_port))),
    )


if __name__ == "__main__":
    main()
