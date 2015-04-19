import jeolm.local

RESOURCE_TABLES = jeolm.local.InitLocalManager.load_resource_tables()

def main():
    print('\n'.join(RESOURCE_TABLES))

if __name__ == '__main__':
    main()

