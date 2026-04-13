import json
import logging
import asyncio
from typing import Any, AsyncIterator, List, MutableMapping
from internal.agent.agent_support.trait import ModelTrait
from internal.agent.response import ToolCallParser
from internal.config.config import AIModelConfig
import torch

from transformers import (
    AutoTokenizer,
    Qwen3_5ForConditionalGeneration,
    TextStreamer,
)


class Transformers(ModelTrait):
    """Transformers模型实现 - 单例模式，模型只加载一次
    支持流式响应，使用 TextStreamer 逐token生成并输出
    """

    _model_cache: dict[str, tuple[Any, Any]] = {}

    def __init__(self, config: AIModelConfig) -> None:
        self.config = config
        # 系统提示词会在首次使用时异步解析，这里暂时存储原始配置
        self._raw_system_prompt = config.system_prompt
        self.history: list[MutableMapping[str, Any]] = []
        self.options = self.config.config
        self._tools_supported: bool | None = None
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._device: str | None = None
        self._system_prompt_resolved: bool = False

    async def _ensure_system_prompt(self):
        """确保系统提示词已解析"""
        if not self._system_prompt_resolved:
            manager = await self.resolve_prompt_manager()
            resolved_prompt = await manager.compose_system_prompt(
                self._raw_system_prompt
            )
            self.history = [{"role": "system", "content": resolved_prompt}]
            self._system_prompt_resolved = True

    async def _load_model(self) -> tuple[Any, Any]:
        """加载模型和分词器，使用缓存避免重复加载"""
        model_path = self.config.model

        if model_path in Transformers._model_cache:
            logging.info(f"使用缓存的模型: {model_path}")
            return Transformers._model_cache[model_path]

        logging.info(f"正在加载模型: {model_path}")

        def _sync_load():
            if torch.cuda.is_available():
                logging.info(f"CUDA 版本: {torch.version.cuda}")
                logging.info(f"CUDA 设备数量: {torch.cuda.device_count()}")
                logging.info(f"当前 CUDA 设备: {torch.cuda.get_device_name(0)}")
                device = "cuda"
                dtype = torch.float16
            else:
                logging.warning("CUDA 不可用，将使用 CPU 运行")
                device = "cpu"
                dtype = torch.float32

            tokenizer = AutoTokenizer.from_pretrained(
                model_path, trust_remote_code=True
            )
            if tokenizer is None:
                raise RuntimeError(
                    f"无法加载 tokenizer，请检查模型路径是否正确: {model_path}"
                )

            if device == "cuda":
                model = Qwen3_5ForConditionalGeneration.from_pretrained(
                    model_path,
                    trust_remote_code=True,
                    torch_dtype=dtype,
                    device_map="cuda",
                )
            else:
                model = Qwen3_5ForConditionalGeneration.from_pretrained(
                    model_path, trust_remote_code=True, torch_dtype=dtype
                )

            if model is None:
                raise RuntimeError(
                    f"无法加载模型，请检查模型路径是否正确: {model_path}"
                )

            Transformers._model_cache[model_path] = (tokenizer, model)
            logging.info(f"模型加载完成: {model_path}")

            return tokenizer, model

        return await asyncio.to_thread(_sync_load)

    async def chat(self, message: Any, tools: list[dict] | None = None) -> dict:
        """使用Transformers模型发送聊天请求，支持工具调用，获取完整响应"""
        await self._ensure_system_prompt()
        self.history.append({"role": "user", "content": message})

        use_tools = tools is not None and len(tools) > 0
        if self._tools_supported is False:
            use_tools = False

        # 延迟加载模型（只在首次调用时加载）
        if self._tokenizer is None or self._model is None:
            self._tokenizer, self._model = await self._load_model()

        if self._tokenizer is None:
            raise RuntimeError("Tokenizer 加载失败，请检查模型配置")
        if self._model is None:
            raise RuntimeError("Model 加载失败，请检查模型配置")

        # 构建输入 - 包含系统提示词和历史记录
        messages = self.history.copy()

        # 使用原生 tools 参数（Qwen3 原生支持）
        # enable_thinking=False 禁用思考模式，确保直接输出工具调用
        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            tools=tools if use_tools else None,
            enable_thinking=False,
        )
        model_inputs = self._tokenizer([text], return_tensors="pt").to(
            self._model.device
        )

        # 在后台线程中运行生成，避免阻塞事件循环
        def _sync_generate():
            # 生成回复
            generated_ids = self._model.generate(
                **model_inputs,
                max_new_tokens=512,
                temperature=self.config.temperature,
                top_p=0.9,
                do_sample=True,
            )

            # 解码输出
            generated_ids = [
                output_ids[len(input_ids) :]
                for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
            ]
            response_text = self._tokenizer.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]
            return response_text

        response_text = await asyncio.to_thread(_sync_generate)

        # 解析响应，检查是否包含工具调用
        response_dict = self._parse_response(response_text, use_tools)

        # 将响应添加到历史记录
        self.history.append(response_dict)

        return response_dict

    async def stream_chat(
        self,
        message: Any,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """使用Transformers模型发送聊天请求，获取流式响应
        使用 TextStreamer 逐token生成，每生成一个token就解码并返回累积文本
        工具调用仍然使用完整响应模式，因为需要完整解析工具调用格式
        """
        await self._ensure_system_prompt()
        self.history.append({"role": "user", "content": message})

        use_tools = tools is not None and len(tools) > 0
        if self._tools_supported is False:
            use_tools = False

        # 延迟加载模型（只在首次调用时加载）
        if self._tokenizer is None or self._model is None:
            self._tokenizer, self._model = await self._load_model()

        if self._tokenizer is None:
            raise RuntimeError("Tokenizer 加载失败，请检查模型配置")
        if self._model is None:
            raise RuntimeError("Model 加载失败，请检查模型配置")

        # 如果需要工具调用，回退到完整响应模式
        # 因为工具调用需要完整解析，不适合流式输出
        if use_tools:
            response_dict = self.chat(None, tools)
            # 完整返回 response_dict 以便上层能检测到 tool_calls
            result = response_dict.copy()
            result["done"] = True
            yield result
            return

        # 构建输入 - 包含系统提示词和历史记录
        messages = self.history.copy()
        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            tools=None,
            enable_thinking=False,
        )
        model_inputs = self._tokenizer([text], return_tensors="pt").to(
            self._model.device
        )

        # 使用 TextStreamer 收集流式生成的token
        full_content = ""
        generated_tokens: List[int] = []

        class AccumulateStreamer(TextStreamer):
            """自定义流式收集器，累积生成的token并存储"""

            def __init__(self, tokenizer, skip_prompt=True):
                super().__init__(tokenizer, skip_prompt=skip_prompt)
                self.tokenizer = tokenizer

            def on_finalized_text(self, text: str, stream_end: bool = False):
                """每生成一段文本，累积到full_content中"""
                nonlocal full_content
                full_content += text

        streamer = AccumulateStreamer(self._tokenizer, skip_prompt=True)

        # 在后台线程中运行生成，因为transformers的generate是同步阻塞的
        # 使用线程避免阻塞事件循环，同时可以逐token获取输出
        generation_complete = asyncio.Event()

        def generate_in_thread():
            """在线程中执行生成，允许异步获取流式输出"""
            nonlocal generated_tokens
            try:
                self._model.generate(
                    **model_inputs,
                    max_new_tokens=512,
                    temperature=self.config.temperature,
                    top_p=0.9,
                    do_sample=True,
                    streamer=streamer,
                )
            finally:
                # 标记生成完成
                generation_complete.set()

        # 启动生成线程
        import threading

        thread = threading.Thread(target=generate_in_thread)
        thread.start()

        # 循环等待新文本，逐yield输出
        prev_length = 0
        while not generation_complete.is_set():
            # 等待一小段时间，让模型生成更多token
            await asyncio.sleep(0.01)
            current_length = len(full_content)
            if current_length > prev_length:
                # 有新内容生成，yield当前完整累积文本
                prev_length = current_length
                yield {"content": full_content, "done": False}

        # 等待线程完成
        thread.join()

        # 生成完成后，检查是否有最后的内容需要发送
        if len(full_content) > prev_length:
            yield {"content": full_content, "done": False}

        # 解析响应（检查是否包含工具调用）
        response_dict = self._parse_response(full_content, use_tools)
        # 将完整响应添加到历史记录
        self.history.append(response_dict)

        # 最后一个块标记完成
        yield {"content": response_dict.get("content", full_content), "done": True}

    def _format_tools_prompt(self, tools: list[dict] | None) -> str:
        """将工具定义格式化为提示词（备用方案，当模型不支持原生 tools 时使用）"""
        if tools is None:
            return ""
        tools_str = "\n\n## 可用工具定义\n"
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            description = func.get("description", "")
            parameters = func.get("parameters", {})
            tools_str += f"- {name}: {description}\n"
            tools_str += f"  参数: {json.dumps(parameters, ensure_ascii=False)}\n"
        return tools_str

    def _parse_response(self, response_text: str, use_tools: bool) -> dict:
        """解析模型响应，提取工具调用或普通内容"""
        if use_tools:
            # 尝试解析工具调用
            tool_calls = self._extract_tool_calls(response_text)
            if tool_calls:
                return {"role": "assistant", "content": None, "tool_calls": tool_calls}

        # 普通文本响应
        return {"role": "assistant", "content": response_text}

    def _extract_tool_calls(self, response_text: str) -> list[dict] | None:
        """从响应文本中提取工具调用"""
        import re

        tool_calls = []

        # 方法1: 尝试匹配 <tool_call>{...}</tool_call> 格式（贪婪匹配，解决嵌套JSON问题）
        pattern = r"<tool_call>(\{.*\})</tool_call>"
        matches = re.findall(pattern, response_text, re.DOTALL)

        # 方法2: 如果没有匹配到，尝试匹配 <tool_call>{...}> 格式（模型可能只输出>作为结束）
        if not matches:
            pattern = r"<tool_call>(\{.*\})>"
            matches = re.findall(pattern, response_text, re.DOTALL)

        # 方法3: 尝试匹配不带结束标签的格式 <tool_call>{...}
        if not matches:
            pattern = r"<tool_call>(\{.*)"
            matches = re.findall(pattern, response_text, re.DOTALL)

        for match in matches:
            # 尝试找到匹配的JSON边界
            json_str = self._extract_valid_json(match)
            if not json_str:
                continue

            try:
                tool_data = json.loads(json_str)
                tool_call = {
                    "id": ToolCallParser.generate_tool_call_id(),
                    "type": "function",
                    "function": {
                        "name": tool_data.get("name", ""),
                        "arguments": tool_data.get("arguments", {}),
                    },
                }
                tool_calls.append(tool_call)
            except json.JSONDecodeError:
                continue

        # 方法4: 尝试匹配 XML 格式的 tool_call
        # <tool_call>\n<function=name>\n<parameter=key>\nvalue\n</parameter>\n...</function>\n</tool_call>
        if not tool_calls:
            xml_tool_calls = self._extract_xml_tool_calls(response_text)
            if xml_tool_calls:
                tool_calls.extend(xml_tool_calls)

        return tool_calls if tool_calls else None

    def _extract_xml_tool_calls(self, response_text: str) -> list[dict] | None:
        """从响应文本中提取 XML 格式的工具调用

        格式示例:
        <tool_call>
        <function=file>
        <parameter=action>
        read
        </parameter>
        <parameter=path>
        ./README.md
        </parameter>
        </function>
        </tool_call>
        """
        import re

        tool_calls = []

        # 匹配 <tool_call>...</tool_call> 块
        pattern = r"<tool_call>\s*<function=(\w+)>\s*(.*?)</function>\s*</tool_call>"
        matches = re.findall(pattern, response_text, re.DOTALL)

        for func_name, params_block in matches:
            arguments = {}

            # 匹配 <parameter=key>\nvalue\n</parameter>
            param_pattern = r"<parameter=(\w+)>\s*(.*?)\s*</parameter>"
            param_matches = re.findall(param_pattern, params_block, re.DOTALL)

            for param_key, param_value in param_matches:
                arguments[param_key] = param_value.strip()

            tool_call = {
                "id": ToolCallParser.generate_tool_call_id(),
                "type": "function",
                "function": {
                    "name": func_name,
                    "arguments": arguments,
                },
            }
            tool_calls.append(tool_call)

        return tool_calls if tool_calls else None

    def _extract_valid_json(self, text: str) -> str | None:
        """从文本中提取有效的JSON字符串，处理嵌套的大括号"""
        text = text.strip()
        if not text.startswith("{"):
            return None

        # 使用栈来匹配大括号，找到正确的JSON结束位置
        depth = 0
        end_pos = -1

        for i, char in enumerate(text):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i
                    break

        if end_pos >= 0:
            return text[: end_pos + 1]
        return None
