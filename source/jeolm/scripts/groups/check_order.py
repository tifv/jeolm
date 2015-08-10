"""
Check if _Order.yaml files cover all the file structure.

Print the set of paths that exist in _Order.yaml files but not outside
of them. Next, print the set of source paths not covered by _Order.yaml.
"""

from jeolm.record_path import RecordPath

# Will destroy metadata
def main(metadata=None, *, local):
    if metadata is None:
        metadata = (local.metadata_class)(local=local)
        metadata.load_metadata_cache()
    root = RecordPath()
    ordered_paths = set(clear_order(metadata))
    driver = metadata.feed_metadata((local.driver_class)())
    record_paths = set( path
        for source_path, record in driver.items()
        if '$source$able' in record
        for path in source_path.ancestry
        if path != root )
    print(ordered_paths - record_paths)
    print(record_paths - ordered_paths)

def clear_order(metadata):
    """
    Remove all _Order.yaml from metadata.

    Yield paths that were fixed by _Order.yaml.
    """
    root = metadata.Path()
    order_paths = { path
        for path in metadata.paths()
        if path != root
        if path.name == '_Order.yaml' }
    for path in order_paths:
        assert isinstance(path, metadata.Path), type(path)
        metadata_record = metadata.get(path)
        metadata.delete(path)
        metadata_piece = metadata_record['$metadata']
        for name in metadata_piece:
            yield path.parent / name


if __name__ == '__main__':
    import jeolm.local
    local = jeolm.local.LocalManager()
    main(local=local)

