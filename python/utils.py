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

def pure_relative(fromdir, absolute):
    """
    Compute relative PurePath, with '..' parts.

    Both arguments must be absolute PurePath's and lack '..' parts.
    """
    if not absolute.is_absolute():
        raise ValueError(absolute)
    if not fromdir.is_absolute():
        raise ValueError(fromdir)
    if any('..' in path.parts for path in (absolute, fromdir)):
        raise ValueError(absolute, fromdir)
    upstairs = 0
    absolute_parents = set(absolute.parents())
    while fromdir not in absolute_parents:
        fromdir = fromdir.parts[:-1]
        upstairs += 1
    return PurePath(*
        ['..'] * upstairs + [absolute.relative(fromdir)] )

