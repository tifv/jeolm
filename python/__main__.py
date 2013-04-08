import subprocess
import logging

import jeolm

logger = logging.getLogger(__name__)

try:
    jeolm.main()
except subprocess.CalledProcessError as exception:
    logger.critical(
        "Command {exc.cmd} returned status {exc.returncode}"
        .format(exc=exception) )
