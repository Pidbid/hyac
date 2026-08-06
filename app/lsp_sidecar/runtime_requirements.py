"""Runtime command requirements shared by LSP startup and packaging checks."""

SYSTEM_COMMANDS = ("node",)
PYTHON_COMMAND_PACKAGES = {
    "pyright-langserver": "pyright",
    "autopep8": "autopep8",
}
REQUIRED_COMMANDS = SYSTEM_COMMANDS + tuple(PYTHON_COMMAND_PACKAGES)

PYRIGHT_LANGSERVER_COMMAND = "pyright-langserver"
AUTOPEP8_COMMAND = "autopep8"
