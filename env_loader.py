from pathlib import Path


def load_local_env(env_path):
    env_file = Path(env_path)
    if not env_file.exists():
        return False

    loaded_any = False
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')

        if key and key not in __import__("os").environ:
            __import__("os").environ[key] = value
            loaded_any = True

    return loaded_any
