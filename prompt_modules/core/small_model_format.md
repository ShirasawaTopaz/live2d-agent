## Critical Format Instructions for This Model

**READ CAREFULLY**: This is a smaller model that needs extra attention to formatting.

### Tool Call Format You MUST Follow

When you need to call a tool, **ALWAYS** use this EXACT format:

```
<tool_call>
{
  "name": "your_tool_name",
  "arguments": {
    "parameter_name": "parameter_value"
  }
}
</tool_call>
```

### Strict Requirements

1. **ALWAYS** wrap your tool call with `<tool_call>` opening and `</tool_call>` closing tags
2. **ALWAYS** use valid JSON format
3. **ALWAYS** check that your JSON syntax is correct
4. **NEVER** add extra explanation before or after the tool call
5. **ONLY** one tool call per response
6. **AFTER** tool execution completes and the tool already displayed the result, **STOP** immediately - do NOT output anything else

Example of a correct tool call:

<tool_call>
{
  "name": "file",
  "arguments": {
    "action": "read",
    "path": "README.md"
  }
}
</tool_call>

Following these instructions exactly is critical for this model to work correctly.
