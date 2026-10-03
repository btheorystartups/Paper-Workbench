"""Launch the supported single-user server using a prebound loopback socket."""

import argparse
import socket

from .config import get_settings
from .providers import codex_access


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = get_settings()
    codex_access.validate_configuration(settings)
    if settings.llm_provider != "codex_local":
        parser.error("WB_LLM_PROVIDER must be codex_local")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", args.port))
        listener.listen(128)
        # Other launchers cannot attest to how their socket was actually bound.
        codex_access._loopback_listener_verified = True
        try:
            from .main import app

            config = uvicorn.Config(app, host="127.0.0.1", port=args.port, workers=1,
                                    proxy_headers=False, access_log=False)
            uvicorn.Server(config).run(sockets=[listener])
        finally:
            codex_access._loopback_listener_verified = False


if __name__ == "__main__":
    main()
