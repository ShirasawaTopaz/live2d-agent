import asyncio
import logging
from typing import Any, AsyncIterator, MutableMapping, List

import ollama

from internal.agent.agent_support.trait import ModelTrait
from internal.agent.response import ToolCallParser
from internal.config.config import AIModelConfig


class OllamaModel(ModelTrait):
    """Ollama模型实现 - 单例模式，避免重复创建客户端
    支持流式响应和非流式响应，流式通过 stream=True 参数启用
    """

    _client_cache: dict[str, Any] = {}

    def __init__(self, config: AIModelConfig) -> None:
        self.config = config
        # 系统提示词会在首次使用时异步解析，这里暂时存储原始配置
        self._raw_system_prompt = config.system_prompt
        self.history: list[MutableMapping[str, Any]] = []
        self.options = self.config.config
        self._tools_supported: bool | None = None
        self._client: Any | None = None
        self._system_prompt_resolved: bool = False
        
    def _get_inference_options(self) -> dict:
        """Get inference options from config, falls back to defaults."""
        options = self.options.copy()
        
        # Override with top-level config parameters if available
        if self.config.temperature is not None:
            options["temperature"] = self.config.temperature
        if self.config.top_p is not None:
            options["top_p"] = self.config.top_p
        if self.config.repeat_penalty is not None:
            options["repeat_penalty"] = self.config.repeat_penalty
        if self.config.max_new_tokens is not None:
            options["num_predict"] = self.config.max_new_tokens
            
        return options
        
    def get_max_tool_call_retries(self) -> int:
        """Get maximum tool call retries from config, default 2."""
        return getattr(self.config, "max_tool_call_retries", None) or 2

    async def _ensure_system_prompt(self):
        """确保系统提示词已解析"""
        if not self._system_prompt_resolved:
            manager = await self.resolve_prompt_manager()
            resolved_prompt = await manager.compose_system_prompt(
                self._raw_system_prompt
            )
            self.history = [{"role": "system", "content": resolved_prompt}]
            self._system_prompt_resolved = True

    def _get_client(self) -> Any:
        """获取或创建Ollama客户端，使用缓存避免重复创建"""
        model_name = self.config.model

        if model_name in OllamaModel._client_cache:
            logging.debug(f"使用缓存的Ollama客户端: {model_name}")
            return OllamaModel._client_cache[model_name]

        logging.info(f"创建Ollama客户端: {model_name}")
        client = ollama.Client()
        OllamaModel._client_cache[model_name] = client
        return client

    async def chat(
        self,
        message: str | None,
        tools: list[dict] | None = None,
    ) -> dict:
        """使用Ollama API发送聊天请求，获取完整响应
        When tool call parsing fails, automatically retry up to max_retries times.
        """
        await self._ensure_system_prompt()
        if message:
            self.history.append({"role": "user", "content": message})

        use_tools = tools is not None and len(tools) > 0
        if self._tools_supported is False:
            use_tools = False

        # 延迟创建客户端（只在首次调用时创建）
        if self._client is None:
            self._client = self._get_client()
            
        # Get configured inference options
        inference_options = self._get_inference_options()

        max_retries = self.get_max_tool_call_retries()
        last_response = None
        
        for attempt in range(max_retries + 1):
            try:
                if self._client is None:
                    raise RuntimeError("Ollama 客户端加载失败，请检查配置")
                response = await asyncio.to_thread(
                    self._client.chat,
                    model=self.config.model,
                    messages=self.history,
                    options=inference_options,
                    tools=tools if use_tools else None,
                    stream=False,
                )
                if use_tools:
                    self._tools_supported = True
                    
                message_dict = response.get("message", {})
                
                # If using native tool calls or not using tools, return directly
                if not use_tools or "tool_calls" in message_dict:
                    self.history.append(message_dict)
                    return message_dict
                    
                # For text-based tool call extraction, check if parsing succeeds
                content = message_dict.get("content", "")
                if content:
                    extracted = ToolCallParser.extract_tool_calls_from_text(content)
                    if extracted or attempt == max_retries:
                        # Either we extracted tool calls or it's the last attempt
                        if extracted:
                            message_dict["tool_calls"] = extracted
                        self.history.append(message_dict)
                        return message_dict
                    else:
                        # Parsing failed, ask model to correct the format
                        error_msg = (
                            "Failed to parse tool call. "
                            "Please check the format and provide the tool call in correct JSON format."
                        )
                        logging.warning(
                            f"Tool call parsing failed on attempt {attempt+1}/{max_retries}, asking for correction"
                        )
                        self.history.append(message_dict)
                        self.history.append({
                            "role": "user",
                            "content": error_msg
                        })
                        last_response = message_dict
                        continue
                else:
                    # No content, check for tool_calls
                    self.history.append(message_dict)
                    return message_dict
                        
            except ollama.ResponseError as e:
                if use_tools and "does not support tools" in str(e):
                    logging.warning(
                        f"Model {self.config.model} does not support tools, falling back to plain chat"
                    )
                    self._tools_supported = False
                    use_tools = False
                    if self._client is None:
                        raise RuntimeError("Ollama 客户端加载失败，请检查配置")
                    response = await asyncio.to_thread(
                        self._client.chat,
                        model=self.config.model,
                        messages=self.history,
                        options=inference_options,
                        tools=None,
                        stream=False,
                    )
                    message_dict = response.get("message", {})
                    self.history.append(message_dict)
                    return message_dict
                else:
                    raise
                    
        # If all retries failed, return the last response
        if last_response is None:
            last_response = {"role": "assistant", "content": "Failed to get valid response after multiple retries"}
        self.history.append(last_response)
        return last_response

    async def stream_chat(
        self,
        message: str | None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """使用Ollama API发送聊天请求，获取流式响应
        通过 Ollama 原生的 stream=True 参数实现逐块生成
        返回每个块包含累积的完整内容和完成标记
        """
        await self._ensure_system_prompt()
        if message:
            self.history.append({"role": "user", "content": message})

        use_tools = tools is not None and len(tools) > 0
        if self._tools_supported is False:
            use_tools = False

        # 延迟创建客户端（只在首次调用时创建）
        if self._client is None:
            self._client = self._get_client()

        if self._client is None:
            raise RuntimeError("Ollama 客户端加载失败，请检查配置")

        # 如果需要工具调用，回退到完整响应模式
        # 因为工具调用需要完整解析，不适合流式输出
        if use_tools:
            try:
                # Get configured inference options
                inference_options = self._get_inference_options()
                response = await asyncio.to_thread(
                    self._client.chat,
                    model=self.config.model,
                    messages=self.history,
                    options=inference_options,
                    tools=tools,
                    stream=False,
                )
                if use_tools:
                    self._tools_supported = True
                message_dict = response.get("message", {})
                self.history.append(message_dict)
                # 完整返回 message_dict 以便上层能检测到 tool_calls
                result = message_dict.copy()
                result["done"] = True
                yield result
                return
            except ollama.ResponseError as e:
                if "does not support tools" in str(e):
                    logging.warning(
                        f"Model {self.config.model} does not support tools, falling back to plain stream chat"
                    )
                    self._tools_supported = False
                    use_tools = False
                else:
                    raise

        # 流式生成普通文本响应
        full_content = ""
        # Get configured inference options
        inference_options = self._get_inference_options()
        # 在后台线程中获取流式迭代器
        stream = await asyncio.to_thread(
            self._client.chat,
            model=self.config.model,
            messages=self.history,
            options=inference_options,
            tools=None,
            stream=True,
        )

        for chunk in stream:
            if "message" in chunk and "content" in chunk["message"]:
                delta = chunk["message"]["content"]
                full_content += delta
                # yield当前累积内容，done=False 表示还在生成中
                yield {"content": full_content, "done": False}

        # 流式生成完成，添加到历史记录
        message_dict = {"role": "assistant", "content": full_content}
        self.history.append(message_dict)

        # 最后一个块标记完成
        yield {"content": full_content, "done": True}
