from pathlib import PurePosixPath as PurePath

def pure_join(*paths):
    """
    Join PurePaths, resolving '..' parts.

    Assert unexistance of directory symlinks.
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

    Assert unexistance of directory symlinks.
    Both arguments should be absolute (ValueError) and lack '..' parts
    (not checked).
    """
    if not absolute.is_absolute(): raise ValueError(absolute)
    if not fromdir.is_absolute(): raise ValueError(fromdir)
    upstairs = 0
    absolute_parents = set(absolute.parents())
    while fromdir not in absolute_parents:
        fromdir = fromdir.parts[:-1]
        upstairs += 1
    return PurePath(*
        ['..'] * upstairs + [absolute.relative_to(fromdir)] )

