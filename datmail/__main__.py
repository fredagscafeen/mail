import logging
import argparse
import threading

from emailtunnel import logger
from datmail.control import create_control_server
from datmail.config import (
    DATMAIL_CONTROL_HOST,
    DATMAIL_CONTROL_PORT,
    DATMAIL_CONTROL_TOKEN,
)
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
    control_server = create_control_server(
        server,
        token=DATMAIL_CONTROL_TOKEN,
        host=DATMAIL_CONTROL_HOST,
        port=DATMAIL_CONTROL_PORT,
    )
    control_thread = threading.Thread(
        target=control_server.serve_forever,
        daemon=True,
    )
    control_thread.start()
    try:
        server.run()
    except Exception as exn:
        logger.exception("Uncaught exception in DatForwarder.run")
    else:
        logger.info("DatForwarder exiting")
    finally:
        control_server.shutdown()
        control_server.server_close()


if __name__ == "__main__":
    main()
