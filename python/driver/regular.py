from .delegating import DelegatingDriver
from .generating import GeneratingDriver
from .base import DriverError

class Driver(GeneratingDriver, DelegatingDriver):
    pass

