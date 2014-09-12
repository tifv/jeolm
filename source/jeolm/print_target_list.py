from pathlib import Path

from jeolm.records import RecordPath

def main():
    from jeolm.local import LocalManager
    from jeolm.commands import simple_load_driver
    local = LocalManager(root=Path.cwd())
    driver = simple_load_driver(local=local)
    metapaths = set(driver.list_metapaths())
    def add_parent(metapath):
        parent = metapath.parent
        if parent not in metapaths:
            metapaths.add(parent)
            add_parent(parent)
    for metapath in list(metapaths):
        add_parent(metapath)
    metapaths.discard(RecordPath('/'))
    target_list_cache = '\n'.join(
        str(metapath) + '/' for metapath in sorted(metapaths) )
    print('/')
    print(target_list_cache)

if __name__ == '__main__':
    main()

