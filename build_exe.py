"""
打包：双击即用的通用词库管家
输出: dist/OpenIME词库管家.exe

说明：打包只带 pypdf + python-docx 控制体积，同时内置拼音表与学科词库包。
源码环境若装了 pymupdf，PDF 中文抽取会优先用它（体验更好）。
"""

import os
import subprocess
import sys


def build():
    print("=== 打包 OpenIME 词库管家 ===")
    name = "OpenIME词库管家"
    # 需要打进 exe 的资源：拼音表 + 内置词库包
    resources = [
        "pinyin_table.json",
        "词库包_初三数学.txt",
        "词库包_初三物理.txt",
        "词库包_初三化学.txt",
        "词库包_古诗文比赛.txt",
    ]
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", name,
        "--clean",
        "--noconfirm",
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
    for res in resources:
        # Windows 下 --add-data 的分隔符是 os.pathsep（;），Linux/macOS 是 :
        args.append(f"--add-data={res}{os.pathsep}.")

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
