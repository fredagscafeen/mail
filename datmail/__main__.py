import logging
import argparse

from emailtunnel import logger
from datmail.server import DatForwarder


def configure_logging():
    file_handler = logging.FileHandler("datmail.log", "a")
    stream_handler = logging.StreamHandler(None)
    fmt = "[%(asctime)s %(levelname)s] %(message)s"
    datefmt = None
    formatter = logging.Formatter(fmt, datefmt, "%")
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", type=int, default=25, help="Relay port")
parser.add_argument("-P", "--listen-port", type=int, default=9000, help="Listen port")


def main():
    configure_logging()
    args = parser.parse_args()

    receiver_host = "0.0.0.0"
    receiver_port = args.listen_port
    relay_host = "host.docker.internal"
    relay_port = args.port

    server = DatForwarder(receiver_host, receiver_port, relay_host, relay_port)
    try:
        server.run()
    except Exception as exn:
        logger.exception("Uncaught exception in DatForwarder.run")
    else:
        logger.info("DatForwarder exiting")


if __name__ == "__main__":
    main()
