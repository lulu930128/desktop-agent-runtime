import sys
from pathlib import Path


def setup_runtime_logging(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher.combined.log"

    class _Tee:
        def __init__(self, stream_a, stream_b):
            self.stream_a = stream_a
            self.stream_b = stream_b

        def write(self, chunk):
            try:
                self.stream_a.write(chunk)
            except Exception:
                pass
            try:
                self.stream_b.write(chunk)
            except Exception:
                pass

        def flush(self):
            try:
                self.stream_a.flush()
            except Exception:
                pass
            try:
                self.stream_b.flush()
            except Exception:
                pass

    file_handle = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.stdout, file_handle)  # type: ignore[assignment]
    sys.stderr = _Tee(sys.stderr, file_handle)  # type: ignore[assignment]
    return log_path
