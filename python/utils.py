from pathlib import PurePosixPath as PurePath

def pure_join(*paths):
    """
    Join PurePaths, resolving '..' parts.

    Resolve any appearence of 'whatever/..' to ''.
    The resulting path must not contain '..' parts.
    The leading '/', if any, will be stripped from the result.
    """
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

