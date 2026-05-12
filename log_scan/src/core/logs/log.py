import logging
import sys
from colorama import Fore, Style

class LoggerShell(object):
    def __init__(self):
        self.logger = self._get_logger()
    
    def exception(self, message, *args, exc_info=True, **kwargs):
        self.error(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._log(logging.INFO, message, color=Fore.GREEN, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self._log(logging.DEBUG, message, color=Fore.WHITE, *args, **kwargs)

    def warn(self, message, *args, **kwargs):
        self._log(logging.WARN, message, color=Fore.YELLOW, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._log(logging.ERROR, message, Fore.RED, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        self._log(logging.CRITICAL, message, color=Fore.RED, *args, **kwargs)

    def _get_logger(self):
        console_handle = logging.StreamHandler(sys.stdout)
        console_handle.setFormatter(logging.Formatter('[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d] - %(message)s',
                                                    datefmt='%Y-%m-%d %H:%M:%S'))
        logger = logging.getLogger("log_mgr")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        if not logger.hasHandlers():
            logger.addHandler(console_handle)
        return logger
    
    def _log(self, level, message, color, *args, **kwargs):
        color_arg = kwargs.get('color', None)
        if color_arg is not None:
            color = color_arg
        title = kwargs.get('title', "")
        if message:
            if isinstance(message, list):
                message = " ".join(message)
        self.logger.log(level, color + message + Style.RESET_ALL, extra={"title": title}, *args, **kwargs)