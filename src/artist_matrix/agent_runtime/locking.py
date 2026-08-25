"""Small cross-process file-lock primitive for durable runtime registries."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive OS lock on ``path`` for the duration of the context.

    Lock files are retained. Deleting one while another process waits on its
    inode would create a second lock domain and break mutual exclusion.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":  # pragma: no cover - exercised on Windows runners
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(  # type: ignore[attr-defined]  # Windows-only API
                handle.fileno(),
                msvcrt.LK_LOCK,  # type: ignore[attr-defined]
                1,
            )
        elif os.name == "posix":
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        else:  # pragma: no cover - no supported runner reaches this branch
            raise RuntimeError(f"Cross-process file locking is unsupported on {os.name}")

        try:
            yield
        finally:
            if os.name == "nt":  # pragma: no cover - exercised on Windows runners
                import msvcrt

                handle.seek(0)
                msvcrt.locking(  # type: ignore[attr-defined]  # Windows-only API
                    handle.fileno(),
                    msvcrt.LK_UNLCK,  # type: ignore[attr-defined]
                    1,
                )
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = ["exclusive_file_lock"]
