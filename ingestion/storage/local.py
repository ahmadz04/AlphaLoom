import json, os, tempfile
from typing import Any, List

class LocalStorage:
    def write_json(self, obj: Any, path_str: str) -> None:
        self.mkdirs_for(path_str)
        dir_ = os.path.dirname(path_str)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=dir_)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path_str)  # atomic
        finally:
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except: pass

    def read_json(self, path_str: str):
        with open(path_str, "r", encoding="utf-8") as f:
            return json.load(f)

    def exists(self, path_str: str) -> bool:
        return os.path.exists(path_str)

    def mkdirs_for(self, path_str: str) -> None:
        os.makedirs(os.path.dirname(path_str), exist_ok=True)

    def read_text(self, path_str: str, encoding: str = "utf-8") -> str:
        with open(path_str, "r", encoding=encoding) as f:
            return f.read()

    def list_files(self, prefix: str) -> List[str]:
        """List file paths starting with prefix (prefix may end mid-filename)."""
        dir_, name_prefix = os.path.split(prefix)
        if not os.path.isdir(dir_ or "."):
            return []
        return sorted(
            os.path.join(dir_, name) for name in os.listdir(dir_ or ".")
            if name.startswith(name_prefix) and os.path.isfile(os.path.join(dir_, name))
        )
