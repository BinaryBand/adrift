import py_compile
import traceback
import sys

files = ["src/files/s3.py", "src/web/rss.py"]
ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"{f}: OK")
    except Exception:
        traceback.print_exc()
        ok = False
sys.exit(0 if ok else 2)
