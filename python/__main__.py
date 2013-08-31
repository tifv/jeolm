import subprocess
import logging

import jeolm

logger = logging.getLogger(__name__)

def report_called_process_error(exception):
    if hasattr(exception, 'reported') and exception.reported:
        return
    logger.critical(
        "Command {exc.cmd} returned code {exc.returncode}"
        .format(exc=exception) )

if __name__ == '__main__':
    try:
        jeolm.main()
    except subprocess.CalledProcessError as exception:
        report_called_process_error(exception)

