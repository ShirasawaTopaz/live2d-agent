## Office文档处理工具

### office - Office 文件读写工具
支持 docx/xlsx/pptx/pdf 文件的读写操作。

#### 参数：
- action(必需): 操作类型 - read/write
- file_path(必需): Office 文件路径
- content(可选): 写入内容（write时需要）

### 支持的文件格式：

- **Word文档 (.docx)**: 读取和写入文本内容
- **Excel表格 (.xlsx)**: 读取和写入表格数据
- **PowerPoint演示文稿 (.pptx)**: 读取和写入演示文稿内容
- **PDF文档 (.pdf)**: 读取文本内容（写入功能受限）

### 使用示例：

**读取Word文档：**
```json
{"toolcall": [{"thought": "需要读取Word文档内容", "name": "office", "query_language": "Chinese", "params": {"action": "read", "file_path": "D:/example.docx"}}]}
```

**写入Word文档：**
```json
{"toolcall": [{"thought": "需要写入Word文档内容", "name": "office", "query_language": "Chinese", "params": {"action": "write", "file_path": "D:/example.docx", "content": "这是文档内容"}}]}
```

请根据用户需求选择合适的Office文件操作。
