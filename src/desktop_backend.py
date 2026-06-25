"""Desktop backend entrypoint.

Electron launches this executable with desktop env vars already set.
"""

from __future__ import annotations

import argparse
import importlib
import os

import uvicorn


def initialize_desktop_runtime() -> None:
    """Initialize Torch before FAISS is imported by the API pipeline."""
    importlib.import_module("torch")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user-data-dir", required=True)
    args = parser.parse_args()

    os.environ["SECONDBRAIN_DESKTOP_MODE"] = "1"
    os.environ["SECONDBRAIN_USER_DATA_DIR"] = args.user_data_dir
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.7")
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    initialize_desktop_runtime()
    from src.api.app import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
