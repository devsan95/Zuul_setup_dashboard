import logging
from logging import CRITICAL, FATAL, ERROR, WARNING, WARN, INFO, DEBUG, NOTSET  # noqa: F401


def get_console_logger(name, level=DEBUG):
    log = logging.getLogger(name)
    ch = logging.StreamHandler()
    ch.setLevel(level)
    log.addHandler(ch)
    log.setLevel(level)
    return log
