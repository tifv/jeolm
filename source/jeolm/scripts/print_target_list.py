from pathlib import Path

def main():
    from jeolm.project import Project
    from jeolm.commands import simple_load_driver
    project = Project(root=Path.cwd())
    driver = simple_load_driver(project=project)
    metapaths = set(driver.list_metapaths())
    def add_parent(metapath):
        if metapath.is_root():
            return
        parent = metapath.parent
        if parent not in metapaths:
            metapaths.add(parent)
            add_parent(parent)
    for metapath in list(metapaths):
        add_parent(metapath)
    target_list_cache = '\n'.join(
        str(metapath)
        for metapath in sorted(metapaths, key=lambda path: path.sorting_key())
    )
    print(target_list_cache)

if __name__ == '__main__':
    main()

