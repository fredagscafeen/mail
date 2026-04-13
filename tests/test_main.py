import argparse
import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


REPO_ROOT = "/Users/mmos/Github/fredagscafeen/mail/.worktrees/mail-monitoring-mail"

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def load_main_module():
    import datmail

    emailtunnel = types.ModuleType("emailtunnel")
    emailtunnel.logger = Mock()
    sys.modules["emailtunnel"] = emailtunnel

    server_instance = Mock()
    server_module = types.ModuleType("datmail.server")
    server_module.DatForwarder = Mock(return_value=server_instance)
    sys.modules["datmail.server"] = server_module
    datmail.server = server_module

    control_server = Mock()
    control_module = types.ModuleType("datmail.control")
    control_module.create_control_server = Mock(return_value=control_server)
    sys.modules["datmail.control"] = control_module
    datmail.control = control_module

    config_module = types.ModuleType("datmail.config")
    config_module.DATMAIL_CONTROL_HOST = "127.0.0.1"
    config_module.DATMAIL_CONTROL_PORT = 9100
    config_module.DATMAIL_CONTROL_TOKEN = "shared-secret"
    sys.modules["datmail.config"] = config_module
    datmail.config = config_module

    if "datmail.__main__" in sys.modules:
        return importlib.reload(sys.modules["datmail.__main__"])
    return importlib.import_module("datmail.__main__")


class MainTests(unittest.TestCase):
    def test_main_starts_control_server_with_shared_forwarder(self):
        main_module = load_main_module()
        main_module.configure_logging = Mock()
        main_module.parser.parse_args = Mock(
            return_value=argparse.Namespace(listen_port=9000, port=25)
        )
        thread = Mock()

        with patch.object(main_module.threading, "Thread", return_value=thread):
            main_module.main()

        main_module.DatForwarder.assert_called_once_with(
            "0.0.0.0",
            9000,
            "host.docker.internal",
            25,
        )
        main_module.create_control_server.assert_called_once_with(
            main_module.DatForwarder.return_value,
            token="shared-secret",
            host="127.0.0.1",
            port=9100,
        )
        thread.start.assert_called_once_with()
        main_module.DatForwarder.return_value.run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
