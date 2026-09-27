import os

import uvicorn


def main() -> None:
    host = os.getenv("WEBAPP_HOST", "127.0.0.1")
    port = int(os.getenv("WEBAPP_PORT", "8000"))
    uvicorn.run("app.main:create_app", factory=True, host=host, port=port)


if __name__ == "__main__":
    main()
