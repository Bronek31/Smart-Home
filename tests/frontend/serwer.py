#!/usr/bin/env python3
"""Serwer testowy: to samo, co robi GitHub Pages, tylko lokalnie.

Wątkowy, bo http.server w wersji jednowątkowej ustawia żądania w kolejce i przy
kilku równoległych workerach Playwrighta zaczyna gubić timing.
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KATALOG = Path(__file__).resolve().parent.parent.parent


class Cichy(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    ThreadingHTTPServer(("127.0.0.1", port),
                        partial(Cichy, directory=str(KATALOG))).serve_forever()
