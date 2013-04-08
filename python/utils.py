from pathlib import PurePosixPath as PurePath

def purejoin(*paths):
    path = PurePath(*paths)
    if path.is_absolute():
        path = path.parts[1:]
    parts = []
    for part in path.parts:
        if part != '..':
            parts.append(part)
        else:
            parts.pop()
    return PurePath(*parts)

