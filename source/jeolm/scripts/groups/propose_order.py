from jeolm.record_path import RecordPath
from jeolm.fancify import fancifying_print as fprint

def main(metapath, *, driver):
    for metapath, metarecord, group, date, period in \
            driver.list_timetable(path=metapath):
        fprint(
            "# {group} {date} {period}"
            .format(group=group, date=date, period=period) )
        fprint(metapath)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('metapath', type=RecordPath)
    args = parser.parse_args()

    import jeolm.commands
    driver = jeolm.commands.simple_load_driver()
    main(args.metapath, driver=driver)

