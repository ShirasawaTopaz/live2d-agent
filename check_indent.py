#!/usr/bin/env python3
"""检查Python文件的缩进问题"""

import sys


def check_indentation(filename):
    """检查文件的缩进是否一致"""
    with open(filename, "rb") as f:
        content = f.read()

    lines = content.split(b"\n")
    issues = []

    for i, line in enumerate(lines, 1):
        # 检查混合缩进
        if b"\t" in line and b" " in line:
            issues.append(f"第 {i} 行: 混合使用制表符和空格")

        # 检查奇数缩进（Python通常使用4空格缩进）
        stripped = line.lstrip()
        if stripped and not line.strip().startswith(b"#"):
            indent = len(line) - len(stripped)
            if indent > 0 and indent % 4 != 0:
                issues.append(f"第 {i} 行: 非4的倍数缩进 ({indent} 空格)")

    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for issue in issues[:10]:  # 只显示前10个
            print(f"  - {issue}")
        if len(issues) > 10:
            print(f"  ... 还有 {len(issues) - 10} 个问题")
        return 1
    else:
        print("未发现缩进问题")
        return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <python文件>")
        sys.exit(1)

    sys.exit(check_indentation(sys.argv[1]))
