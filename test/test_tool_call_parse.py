#!/usr/bin/env python3
"""测试工具调用解析逻辑"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from internal.agent.response import ToolCallParser

# 模拟 Ollama 返回的对象结构
class Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments

class ToolCall:
    def __init__(self, function):
        self.function = function

class MockResponse:
    def __init__(self, tool_calls=None, content=""):
        self.role = 'assistant'
        self.content = content
        self.thinking = ''
        self.images = None
        self.tool_name = None
        self.tool_calls = tool_calls or []

# 测试1：模拟日志中的响应
print("测试1：模拟日志中的响应结构")
func = Function('display_bubble_text', {'text': '你好呀！很高兴见到你！😊'})
tool_call = ToolCall(func)
response = MockResponse([tool_call])

print(f"响应对象类型: {type(response)}")
print(f"hasattr(response, 'tool_calls'): {hasattr(response, 'tool_calls')}")
print(f"response.tool_calls: {response.tool_calls}")

print("\n尝试解析...")
try:
    parsed = ToolCallParser.parse_tool_calls(response)
    print(f"解析结果: {parsed}")
except Exception as e:
    print(f"解析出错: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*50 + "\n")

# 测试2：查看当前 parse_tool_calls 的逻辑
print("测试2：查看 has_tool_calls 的结果")
try:
    has_tools = ToolCallParser.has_tool_calls(response)
    print(f"has_tool_calls: {has_tools}")
except Exception as e:
    print(f"has_tool_calls 出错: {e}")
    import traceback
    traceback.print_exc()
