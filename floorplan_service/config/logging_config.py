import logging
import os

# from celery.signals import after_setup_logger


# @after_setup_logger.connect
# def setup_loggers(logger, *args, **kwargs):
#     logger.addHandler(logging.StreamHandler())
#     logger.setLevel(logging.DEBUG)


class CustomFormatter(logging.Formatter):
    def __init__(self, fmt="%(levelname)s: %(message)s"):
        super().__init__(fmt)

    def format(self, record):
        # Change format for ERROR level and above (ERROR, CRITICAL)
        if record.levelno >= logging.ERROR:
            self._style._fmt = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        else:
            self._style._fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        return super().format(record)


def configure_logger(name):
    # Create or get a logger
    logger = logging.getLogger(name)

    # Set the log level
    logger.setLevel(logging.DEBUG)  # Set to DEBUG to catch all levels

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(CustomFormatter())

    # Create file handler for connection logs
    file_handler = logging.FileHandler("connections.log")
    file_handler.setFormatter(CustomFormatter())

    # Add handlers to the logger
    if not logger.handlers:  # Avoid adding multiple handlers if already present
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger


def configure_file_logger(name):
    # Create or get a logger
    logger = logging.getLogger(name)

    # Set the log level
    logger.setLevel(logging.DEBUG)  # Set to DEBUG to catch all levels

    # Create file handler for connection logs
    log_file_path = "floorplan_service/connections.log"
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(CustomFormatter())

    # Add handler to the logger
    if not any(
        isinstance(handler, logging.FileHandler) for handler in logger.handlers
    ):  # Avoid adding multiple file handlers
        logger.addHandler(file_handler)

    return logger
