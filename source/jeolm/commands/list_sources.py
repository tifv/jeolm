import logging
logger = logging.getLogger(__name__)


def print_source_list(targets, *, project, driver, viewpoint=None,
    source_type='tex'
):
    paths = list(list_sources(targets,
        project=project, driver=driver, source_type=source_type ))
    if viewpoint is not None:
        paths = [ path.relative_to(viewpoint)
            for path in paths ]
    for path in paths:
        print(path)

def list_sources(targets, *, project, driver, source_type='tex', unique=True):
    source_dir = project.source_dir
    if unique:
        seen = set()
    for target in driver.list_delegated_targets(*targets, recursively=True):
        inpath_generator = driver.list_inpaths(
            target.flags_clean_copy(origin='target'),
            inpath_type=source_type )
        for inpath in inpath_generator:
            if unique:
                if inpath in seen:
                    continue
                seen.add(inpath)
            yield source_dir/inpath

