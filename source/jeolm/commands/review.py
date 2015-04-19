from pathlib import Path, PurePosixPath

import logging
logger = logging.getLogger(__name__) # pylint: disable=invalid-name

def review(paths, *, local, metadata, viewpoint=None):
    inpaths = resolve_inpaths(paths,
        source_dir=local.source_dir, viewpoint=viewpoint )
    for inpath in inpaths:
        metadata.review(inpath)

def resolve_inpaths(paths, *, source_dir, viewpoint=None):
    if viewpoint is not None:
        if not isinstance(viewpoint, Path) or not viewpoint.is_absolute():
            raise RuntimeError(viewpoint)
        paths = [Path(viewpoint, path) for path in paths]
    else:
        paths = [Path(path) for path in paths]
        for path in paths:
            if not path.is_absolute():
                raise RuntimeError(path)
    for path in paths:
        path = _path_resolve_up_to(path, limit_path=source_dir)
        yield PurePosixPath(path).relative_to(source_dir)

def _path_resolve_up_to(path, *, limit_path):
    assert isinstance(path, Path), path
    assert path.is_absolute(), path
    assert isinstance(limit_path, Path), path
    assert limit_path.is_absolute(), limit_path
    resolved = Path('/')
    parts = iter(path.parts[1:])
    for part in parts:
        resolved = (resolved / part).resolve()
        if _path_is_subpath(limit_path, resolved):
            break
    return resolved.joinpath(*parts)

def _path_is_subpath(a_path, b_path):
    assert isinstance(a_path, PurePosixPath), a_path
    assert a_path.is_absolute(), a_path
    assert isinstance(b_path, PurePosixPath), b_path
    assert b_path.is_absolute(), b_path
    a_parts = a_path.parts
    b_parts = b_path.parts
    if not all(a == b for a, b in zip(a_parts, b_parts)):
        raise ValueError("Paths '{}' and '{}' are uncomparable."
            .format(a_path, b_path))
    return len(a_parts) >= len(b_parts)

