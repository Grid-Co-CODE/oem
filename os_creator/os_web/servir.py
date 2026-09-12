# os_creator/os_web/servir.py
"""Sobe o OS Creator web em 127.0.0.1:5090 (waitress). A plataforma faz o proxy de /os/* para aqui.
Uso: `python -m os_web.servir` a partir de `os_creator/` (ou `set OS_WEB_PORTA=...`)."""
from __future__ import annotations
import os
import sys


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from waitress import serve
    from os_web import criar_app
    porta = int(os.environ.get("OS_WEB_PORTA", "5090"))
    app = criar_app()
    print(f"OS Creator web em http://127.0.0.1:{porta}/os/ (waitress, 8 threads)", flush=True)
    serve(app, host="127.0.0.1", port=porta, threads=8, ident="oscreator-web")
    return 0


if __name__ == "__main__":
    sys.exit(main())
