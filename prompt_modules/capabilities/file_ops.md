## 文件操作工具

### file - 文件操作工具
用于读取、写入、搜索文件和目录。

#### 参数：
- action(必需): 操作类型 - read/write/search_files/search_dirs
- path(必需): 文件或目录路径
- content(可选): 写入内容（write时需要）
- pattern(可选): 搜索模式（search_files时使用）

### 使用示例：

**读取文件：**
```json
{"toolcall": [{"thought": "需要读取文件内容", "name": "file", "query_language": "Chinese", "params": {"action": "read", "path": "D:/example.txt"}}]}
```

**写入文件：**
```json
{"toolcall": [{"thought": "需要写入文件内容", "name": "file", "query_language": "Chinese", "params": {"action": "write", "path": "D:/example.txt", "content": "Hello World"}}]}
```

**搜索文件：**
```json
{"toolcall": [{"thought": "需要搜索文件", "name": "file", "query_language": "Chinese", "params": {"action": "search_files", "path": "D:/", "pattern": "*.txt"}}]}
```

当需要读取文件时，请使用file工具的read操作。
