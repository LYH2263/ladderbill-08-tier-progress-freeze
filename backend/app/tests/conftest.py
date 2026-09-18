import os
import tempfile

# 必须在导入任何 app.* 模块之前指定数据目录（app.db 导入时即固化 DB_PATH）
_TEST_DATA_DIR = os.environ.get("TEST_DATA_DIR") or tempfile.mkdtemp(prefix="ladderbill-test-")
os.environ.setdefault("DATA_DIR", _TEST_DATA_DIR)
