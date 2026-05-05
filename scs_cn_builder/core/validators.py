from pathlib import Path

def validate_paths(paths: list[str]) -> None:
    missing = []
    for path in paths:
        if not path:
            missing.append("<empty path>")
            continue
        if not Path(path).exists():
            missing.append(path)
    if missing:
        raise FileNotFoundError("Missing or invalid paths: " + ", ".join(missing))
