"""
打包：双击即用的通用词库管家
输出: dist/OpenIME词库管家.exe

说明：打包只带 pypdf + python-docx，控制体积。
源码环境若装了 pymupdf，PDF 中文抽取会优先用它（体验更好）。
"""

import os
import subprocess
import sys


def build():
    print("=== 打包 OpenIME 词库管家 ===")
    name = "OpenIME词库管家"
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", name,
        "--clean",
        "--noconfirm",
        "--add-data=pinyin_table.json:.",
        "--hidden-import", "pypinyin",
        "--hidden-import", "pypinyin.constants",
        "--hidden-import", "pypinyin.style",
        "--hidden-import", "pypinyin.pinyin",
        "--hidden-import", "pypdf",
        "--hidden-import", "docx",
        "--collect-submodules", "pypdf",
        "--collect-submodules", "docx",
        "--exclude-module", "fitz",
        "--exclude-module", "pymupdf",
        "--exclude-module", "numpy",
        "--exclude-module", "PIL",
        "--exclude-module", "Pillow",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--exclude-module", "scipy",
        "--exclude-module", "torch",
        "--exclude-module", "cryptography",
        "--exclude-module", "fontTools",
        "--exclude-module", "yaml",
        "--exclude-module", "bs4",
        "--exclude-module", "lxml",
        "--exclude-module", "IPython",
        "--exclude-module", "setuptools",
        "main.py",
    ]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    print(" ".join(args))
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print("打包失败")
        return False
    out = os.path.join("dist", f"{name}.exe")
    size = os.path.getsize(out) if os.path.exists(out) else 0
    print(f"完成: {out}  size={size}")
    return True


if __name__ == "__main__":
    raise SystemExit(0 if build() else 1)
