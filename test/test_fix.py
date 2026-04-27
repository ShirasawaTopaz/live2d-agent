#!/usr/bin/env python3
"""测试工具调用解析修复"""

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

print("="*60)
print("测试修复后的工具调用解析")
print("="*60)

# 创建与日志中相同格式的响应
func = Function('display_bubble_text', {'text': '你好呀！很高兴见到你！😊'})
tool_call = ToolCall(func)
response = MockResponse([tool_call])

print("\n1. 检查响应对象:")
print(f"   类型: {type(response)}")
print(f"   has tool_calls: {hasattr(response, 'tool_calls')}")
print(f"   tool_calls 数量: {len(response.tool_calls)}")

tc = response.tool_calls[0]
print("\n   第一个 tool_call:")
print(f"     类型: {type(tc)}")
print(f"     has function: {hasattr(tc, 'function')}")

f = tc.function
print("\n   function 对象:")
print(f"     类型: {type(f)}")
print(f"     has name: {hasattr(f, 'name')}")
print(f"     name: {f.name}")
print(f"     has arguments: {hasattr(f, 'arguments')}")
print(f"     arguments: {f.arguments}")
print(f"     arguments 类型: {type(f.arguments)}")

print("\n" + "="*60)
print("2. 测试 ToolCallParser.has_tool_calls:")
try:
    result = ToolCallParser.has_tool_calls(response)
    print(f"   结果: {result}")
except Exception as e:
    print(f"   出错: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("3. 测试 ToolCallParser.parse_tool_calls:")
parsed = None
try:
    parsed = ToolCallParser.parse_tool_calls(response)
    print(f"   结果: {parsed}")
    if parsed:
        print("\n   解析成功！")
        for tc in parsed:
            print(f"   - id: {tc.get('id')}")
            print(f"   - type: {tc.get('type')}")
            print(f"   - function.name: {tc.get('function', {}).get('name')}")
            print(f"   - function.arguments: {tc.get('function', {}).get('arguments')}")
except Exception as e:
    print(f"   出错: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("4. 测试 ToolCallParser.parse_arguments:")
if parsed and len(parsed) > 0:
    try:
        args = ToolCallParser.parse_arguments(parsed[0])
        print(f"   结果: {args}")
        print(f"   类型: {type(args)}")
    except Exception as e:
        print(f"   出错: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*60)
print("测试完成！")
