## 工具调用规范

### 通用规则

{% if enable_cot %}
### Thinking Process

Before answering or calling a tool, **think step by step** about what to do:
1. First understand the user's question
2. Determine if a tool is needed
3. If a tool is needed, select the correct tool
4. Prepare the proper parameters for the tool
{% endif %}

{% if model_size_billion <= 4 %}
### VERY IMPORTANT - Format Requirements

You **MUST** follow the exact format below for tool calls:

```
<tool_call>
{
  "name": "tool_name",
  "arguments": {
    "parameter_name": "parameter_value"
  }
}
</tool_call>
```

**Remember**: 
- Always wrap the JSON in `<tool_call>` opening and `</tool_call>` closing tags
- Always use valid JSON format
- One tool call per response
- Double-check your JSON syntax before finishing
{% endif %}

- 每次只能调用一个工具
- 系统返回结果后，可继续调用其他工具
- 最多调用5次工具
- 使用工具时必须提供完整且正确的参数

### 工具响应要求

- 工具调用后，等待工具返回结果后再继续处理
- 工具调用失败时，需要友好提示用户
- 工具返回的数据需要正确解析和使用
- **工具执行完成后，如果工具已经向用户显示了结果，你必须停止生成，不需要额外回复任何内容**
