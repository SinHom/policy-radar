"""wechat 子包入口：默认跑 message_router。"""

import sys

from python.wechat.message_router import main


if __name__ == "__main__":
    sys.exit(main())
