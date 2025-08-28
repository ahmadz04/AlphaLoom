import json, os, tempfile
from typing import Any

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
