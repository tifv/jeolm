from pathlib import Path

def generate_target_list():
    from jeolm.project import Project
    from jeolm.commands import simple_load_driver
    project = Project(root=Path.cwd())
    driver = simple_load_driver(project=project)
    target_paths = set()
    def add_parent(target_path):
        if target_path.is_root():
            return
        parent = target_path.parent
        if parent not in target_paths:
            target_paths.add(parent)
            add_parent(parent)
    for target_path in driver.list_targetable_paths():
        target_paths.add(target_path)
        add_parent(target_path)
    for target_path in sorted( target_paths,
            key=lambda path: path.sorting_key() ):
        yield str(target_path)

if __name__ == '__main__':
    print('\n'.join(generate_target_list()))

