"""pytest 配置：保证 src 目录可被导入（不依赖是否已安装本包）。"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
