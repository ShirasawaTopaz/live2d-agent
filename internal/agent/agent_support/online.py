from typing import Any, AsyncIterator, MutableMapping
from internal.agent.agent_support.trait import ModelTrait
from internal.config.config import AIModelConfig
from openai import AsyncOpenAI
import logging


class OnlineModel(ModelTrait):
    """在线OpenAI兼容模型实现（如火山引擎方舟、Kimi等）
    支持流式响应，利用OpenAI兼容API原生的流式输出功能
    """

    def __init__(self, config: AIModelConfig):
        self.config = config
        # 系统提示词会在首次使用时异步解析，这里暂时存储原始配置
        self._raw_system_prompt = config.system_prompt
        self.history: list[MutableMapping[str, Any]] = []
        self.options = {}
        if isinstance(self.config.config, dict):
            self.options.update(self.config.config)
        self._tools_supported: bool = True
        self._client: Any | None = None
        self._system_prompt_resolved: bool = False

    def _build_request_params(
        self,
        *,
        tools: list[dict] | None,
        stream: bool,
    ) -> dict[str, Any]:
        """Build OpenAI-compatible request parameters from typed config + options."""
        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": self.history,
            "tools": tools,
            "stream": stream,
        }

        options: dict[str, Any] = dict(self.options or {})
        api = options.pop("api", None)
        if api is not None:
            self._api = api

        # Top-level typed fields take precedence, but options still work as fallback.
        temperature = self.config.temperature
        if temperature is None:
            temperature = options.pop("temperature", 0.7)
        else:
            options.pop("temperature", None)
        params["temperature"] = temperature

        if self.config.max_new_tokens is not None:
            max_tokens = self.config.max_new_tokens
            options.pop("max_tokens", None)
        else:
            max_tokens = options.pop("max_tokens", 512)
        params["max_tokens"] = max_tokens

        if self.config.top_p is not None:
            options["top_p"] = self.config.top_p
        if self.config.repeat_penalty is not None:
            options["repeat_penalty"] = self.config.repeat_penalty
        if self.config.enable_cot is not None:
            options["enable_cot"] = self.config.enable_cot

        # Merge remaining provider-specific options.
        for key, value in options.items():
            if key not in ["api", "api_key"]:
                params[key] = value

        return params

    async def _ensure_system_prompt(self):
        """确保系统提示词已解析"""
        if not self._system_prompt_resolved:
            manager = await self.resolve_prompt_manager()
            resolved_prompt = await manager.compose_system_prompt(
                self._raw_system_prompt
            )
            self.history = [{"role": "system", "content": resolved_prompt}]
            self._system_prompt_resolved = True

        options = self.options or {}
        self._api = options.get("api", None)
        self._api_key: str | None = None
        # Check if api_key exists directly in model_data (top-level)
        if hasattr(self.config, "api_key"):
            self._api_key = getattr(self.config, "api_key")
        # Also check in options
        if self._api_key is None:
            self._api_key = options.get("api_key", None)
        self._model: str = self.config.model

    def _get_client(self):
        """获取或创建OpenAI客户端，延迟加载"""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._api)
        return self._client

    def _message_to_dict(self, message) -> dict:
        """将ChatCompletionMessage对象转换为字典，便于保存到历史记录"""
        message_dict = {}
        if hasattr(message, "content"):
            message_dict["content"] = message.content
        if hasattr(message, "role"):
            message_dict["role"] = message.role
        if hasattr(message, "tool_calls") and message.tool_calls:
            message_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        if hasattr(message, "function_call") and message.function_call:
            message_dict["function_call"] = message.function_call
        if hasattr(message, "refusal") and message.refusal:
            message_dict["refusal"] = message.refusal
        return message_dict

    async def chat(
        self,
        message: str | None,
        tools: list[dict] | None = None,
    ) -> dict:
        """发送聊天请求，获取完整响应"""
        await self._ensure_system_prompt()
        if message:
            self.history.append({"role": "user", "content": message})

        use_tools = tools is not None and len(tools) > 0
        if self._tools_supported is False:
            use_tools = False

        # 延迟创建客户端（只在首次调用时创建）
        if self._client is None:
            self._client = self._get_client()

        try:
            if self._client is None:
                raise RuntimeError("客户端加载失败，请检查配置")
            params = self._build_request_params(tools=tools if use_tools else None, stream=False)

            response = await self._client.chat.completions.create(**params)
            if use_tools:
                self._tools_supported = True
            # Check if choices is valid and not empty
            if not response.choices or len(response.choices) == 0:
                raise RuntimeError("API 返回空的 choices 列表，请检查配置或重试")
            message = response.choices[0].message
            if message is None:
                raise RuntimeError("API 返回空的 message，请检查配置或重试")
            # Convert ChatCompletionMessage object to dict
            message_dict = self._message_to_dict(message)
            self.history.append(message_dict)
            return message_dict
        except Exception as e:
            if use_tools and "does not support tools" in str(e):
                logging.warning(
                    f"Model {self.config.model} does not support tools, falling back to plain chat"
                )
                self._tools_supported = False
                if self._client is None:
                    raise RuntimeError("客户端加载失败，请检查配置")
                params = self._build_request_params(tools=None, stream=False)

                response = await self._client.chat.completions.create(**params)
                # Check if choices is valid and not empty
                if not response.choices or len(response.choices) == 0:
                    raise RuntimeError("API 返回空的 choices 列表，请检查配置或重试")
                message = response.choices[0].message
                if message is None:
                    raise RuntimeError("API 返回空的 message，请检查配置或重试")
                # Convert ChatCompletionMessage object to dict
                message_dict = self._message_to_dict(message)
                self.history.append(message_dict)
                return message_dict
            else:
                raise

    async def stream_chat(
        self,
        message: str | None,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """发送聊天请求，获取流式响应
        利用OpenAI兼容API原生的流式输出，逐块累积内容并返回
        工具调用仍然使用完整响应模式，因为需要完整解析工具调用格式
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
            raise RuntimeError("客户端加载失败，请检查配置")

        # 如果需要工具调用，回退到完整响应模式
        # 因为工具调用需要完整解析，不适合流式输出
        if use_tools:
            try:
                temperature = (
                    self.options.get("temperature", 0.7) if self.options else 0.7
                )
                max_tokens = (
                    self.options.get("max_tokens", 512) if self.options else 512
                )

                # Build base parameters
                params = {
                    "model": self._model,
                    "messages": self.history,
                    "tools": tools,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }

                # Add all extra options from config (e.g. thinking, top_p, etc.)
                if self.options:
                    for key, value in self.options.items():
                        if key not in ["api", "api_key", "temperature", "max_tokens"]:
                            params[key] = value

                response = await self._client.chat.completions.create(**params)
                if use_tools:
                    self._tools_supported = True
                if not response.choices or len(response.choices) == 0:
                    raise RuntimeError("API 返回空的 choices 列表，请检查配置或重试")
                message = response.choices[0].message
                if message is None:
                    raise RuntimeError("API 返回空的 message，请检查配置或重试")
                message_dict = self._message_to_dict(message)
                self.history.append(message_dict)
                # 完整返回 message_dict 以便上层能检测到 tool_calls
                result = message_dict.copy()
                result["done"] = True
                yield result
                return
            except Exception as e:
                if "does not support tools" in str(e):
                    logging.warning(
                        f"Model {self.config.model} does not support tools, falling back to plain stream chat"
                    )
                    self._tools_supported = False
                    use_tools = False
                else:
                    raise

        # 流式生成普通文本响应
        params = self._build_request_params(tools=None, stream=True)

        full_content = ""
        stream = await self._client.chat.completions.create(**params)

        async for chunk in stream:
            if not chunk.choices or len(chunk.choices) == 0:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_content += delta.content
                # yield当前累积内容，done=False 表示还在生成中
                yield {"content": full_content, "done": False}

        # 流式生成完成，添加到历史记录
        message_dict = {"role": "assistant", "content": full_content}
        self.history.append(message_dict)

        # 最后一个块标记完成
        yield {"content": full_content, "done": True}
