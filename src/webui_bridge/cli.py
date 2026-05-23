import sys

from .demo_chat import main


def run() -> None:
    sys.argv[0] = "webui-bridge"
    main()
