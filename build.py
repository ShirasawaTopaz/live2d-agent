#!/usr/bin/env python3
"""
Live2Oder 打包脚本 - PyInstaller 版本
"""

import os
import sys
import shutil
import platform
from pathlib import Path
import subprocess

PROJECT_NAME = "live2oder"
VERSION = "0.1.0"
ENTRY_POINT = "__main__.py"
OUTPUT_DIR = Path("dist") / f"{PROJECT_NAME}-{VERSION}"


def clean_build():
    """清理旧的构建产物"""
    print("=== 清理旧构建 ===")
    dirs_to_clean = [
        OUTPUT_DIR,
        Path("build"),
        Path("dist"),
        Path("__pycache__"),
    ]
    spec_file = Path(f"{PROJECT_NAME}.spec")
    if spec_file.exists():
        os.remove(spec_file)
        print(f"已删除: {spec_file}")

    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            print(f"已删除: {d}")
    print()


def install_pyinstaller():
    """检查并安装 PyInstaller"""
    print("=== 检查 PyInstaller ===")
    try:
        import PyInstaller as _  # noqa: F401
        from importlib.metadata import version

        pyinstaller_version = version("pyinstaller")
        print(f"✓ PyInstaller 已安装，版本: {pyinstaller_version}")
    except ImportError:
        print("× PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("✓ PyInstaller 安装完成")
    print()


def run_pyinstaller():
    """运行 PyInstaller 编译"""
    print("=== 开始 PyInstaller 编译 ===")

    # 基础 PyInstaller 命令
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        PROJECT_NAME,
        "--onefile",
        "--distpath",
        "dist",
        "--workpath",
        "build",
        # "--clean",
    ]

    # 添加内嵌SKill目录
    skill_dir = Path("skills")
    if skill_dir.exists():
        # 将SKill目录打包到_internal/skills
        cmd.extend(["--add-data", f"{skill_dir}{os.pathsep}skills"])
        print(f"✓ 将打包内嵌SKill目录: {skill_dir}")

    # 平台特定选项
    system = platform.system()
    if system == "Windows":
        # Windows 平台，如果不需要控制台窗口，可以添加 --windowed
        # cmd.append("--windowed")
        if Path("assets/icon.ico").exists():
            cmd.extend(["--icon", "assets/icon.ico"])

    # 显式包含需要的模块（PyInstaller 可能漏掉一些动态导入）
    included_modules = [
        "internal.agent.agent",
        "internal.agent.register",
        "internal.agent.agent_support.ollama",
        "internal.agent.agent_support.online",
        "internal.agent.agent_support.transformers",
        "internal.agent.tool.base",
        "internal.agent.tool.live2d.clear_expression",
        "internal.agent.tool.live2d.display_bubble_text",
        "internal.agent.tool.live2d.next_expression",
        "internal.agent.tool.live2d.play_sound",
        "internal.agent.tool.live2d.set_background",
        "internal.agent.tool.live2d.set_expression",
        "internal.agent.tool.live2d.set_model",
        "internal.agent.tool.live2d.trigger_motion",
        "internal.config.config",
        "internal.memory",
        "internal.memory.storage",
        "internal.ui",
        "internal.websocket.client",
    ]
    for module in included_modules:
        cmd.extend(["--hidden-import", module])

    # 排除不需要的包
    excluded_modules = [
        "numpy.distutils.tests",
        "pytest",
        "tests",
        "test",
        "ruff",
        "poetry",
    ]
    for module in excluded_modules:
        cmd.extend(["--exclude-module", module])

    # 添加入口点
    cmd.append(ENTRY_POINT)

    print(f"运行命令: {' '.join(cmd)}")
    print()
    subprocess.check_call(cmd)
    print()


def copy_extra_files():
    """复制额外文件到输出目录"""
    print("=== 复制额外文件 ==")

    # 需要复制的文件列表
    files_to_copy = [
        "config.example.json",
        "README.md",
        "USER_GUIDE.md",
    ]

    # PyInstaller 输出到 dist/
    pyinstaller_output = Path("dist")

    # 创建输出目录
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True)

    # 移动可执行文件
    exe_suffix = ".exe" if platform.system() == "Windows" else ""
    src_exe = pyinstaller_output / f"{PROJECT_NAME}{exe_suffix}"
    if src_exe.exists():
        dst_exe = OUTPUT_DIR / f"{PROJECT_NAME}{exe_suffix}"
        shutil.move(src_exe, dst_exe)
        print(f"✓ 已移动可执行文件: {dst_exe}")

    for f in files_to_copy:
        src = Path(f)
        if src.exists():
            dst = OUTPUT_DIR / f
            shutil.copy2(src, dst)
            print(f"✓ 已复制: {f}")
        else:
            print(f"× 未找到，跳过: {f}")

    # 创建用户配置提醒文件
    readme_note = OUTPUT_DIR / "配置说明.txt"
    readme_note.write_text(
        """使用说明
========

1. 请将 config.example.json 复制一份，并重命名为 config.json
2. 编辑 config.json，填入你的 Live2D WebSocket 地址和 AI 模型配置
3. 运行 live2oder (Windows: live2oder.exe) 即可启动

详细文档请查看 README.md
""",
        encoding="utf-8",
    )
    print("✓ 已生成: 配置说明.txt")

    print()


def show_result():
    """显示打包结果"""
    print("=== 打包完成 ===")
    print(f"输出目录: {OUTPUT_DIR.resolve()}")
    print(
        f"可执行文件: {OUTPUT_DIR / PROJECT_NAME}{'.exe' if platform.system() == 'Windows' else ''}"
    )
    print()
    print("下一步:")
    print("1. 在输出目录中，config.example.json 已包含")
    print("2. 用户需要自行复制为 config.json 并填写配置")
    print("3. 整个目录压缩后分发即可")


def main():
    """主函数"""
    print(f"Live2Oder 打包脚本 v{VERSION} (PyInstaller)")
    print(f"系统: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    print()

    # clean_build()
    install_pyinstaller()
    run_pyinstaller()
    copy_extra_files()
    show_result()


if __name__ == "__main__":
    main()
