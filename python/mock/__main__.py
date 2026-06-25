"""Mock 微信 CLI 入口。"""

from __future__ import annotations

import sys

from python.mock.mock_wechat import main


if __name__ == "__main__":
    sys.exit(main())
