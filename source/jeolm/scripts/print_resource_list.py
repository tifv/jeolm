import jeolm.local

import jeolm.yaml

_resource_manifest_path = (
    jeolm.local.InitLocalManager._resource_manifest_path )

with _resource_manifest_path.open() as manifest_file:
    resource_tables = jeolm.yaml.load(manifest_file)

def main():
    print('\n'.join(resource_tables))

if __name__ == '__main__':
    main()

