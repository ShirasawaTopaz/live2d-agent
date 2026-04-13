from internal.agent.tool.base import Tool
import aiohttp
from typing import Any, Optional
from urllib.parse import quote_plus
from internal.agent.sandbox import SandboxMiddleware, default_sandbox


class SandboxedNetworkToolBase:
    """Base class that adds sandbox checking to network operations."""

    def __init__(self, sandbox: Optional[SandboxMiddleware] = None):
        self.sandbox = sandbox or default_sandbox

    def _check_url(self, url: str) -> tuple[bool, str]:
        """Check if URL access is allowed by sandbox.

        Returns:
            (allowed: bool, error_message: str)
        """
        if not self.sandbox.is_enabled():
            return True, ""

        allowed, reason = self.sandbox.check_url_access(url)
        return allowed, reason


class WebSearchTool(Tool, SandboxedNetworkToolBase):
    def __init__(self, sandbox: Optional[SandboxMiddleware] = None):
        SandboxedNetworkToolBase.__init__(self, sandbox)

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "网络搜索工具，默认使用 DuckDuckGo 免费 API，可获取互联网最新信息、新闻、文档等内容。当需要获取实时信息或不确定的知识时调用此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或查询内容",
                },
                "count": {
                    "type": "integer",
                    "description": "返回结果的最大数量，默认为10",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        count = kwargs.get("count", 10)

        if not query:
            return {"success": False, "error": "query 参数是必填项", "result": None}

        try:
            # 默认使用 DuckDuckGo 免费 API（无需配置）
            # 如果配置了 API key，则优先使用付费 API
            import os

            baidu_key = os.environ.get("BAIDU_API_KEY")
            bing_key = os.environ.get("BING_SEARCH_API_KEY")

            # 优先级：百度 > Bing > DuckDuckGo
            if baidu_key:
                return await self._search_with_baidu(query, count, baidu_key)
            elif bing_key:
                return await self._search_with_bing(query, count, bing_key)
            else:
                return await self._search_with_free_service(query, count)

        except Exception as e:
            return {"success": False, "error": f"搜索失败: {str(e)}", "result": None}

    async def _search_with_baidu(self, query: str, count: int, api_key: str) -> dict:
        """使用百度搜索 API (百度云) 进行搜索
        API 文档：https://cloud.baidu.com/doc/search/s/Ck28jw5ad
        """
        # 百度云搜索API端点
        endpoint = "https://aip.baidubce.com/rest/2.0/image-classify/v1/websearch"
        url = f"{endpoint}?access_token={api_key}"

        allowed, error = self._check_url(url)
        if not allowed:
            return {
                "success": False,
                "error": f"Sandbox denied access: {error}",
                "result": None,
            }

        params = {
            "query": query,
            "top_num": min(count, 10),  # 百度免费版最多返回10条
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"百度搜索API 错误: {response.status} - {error_text}",
                        "result": None,
                    }

                data = await response.json()
                results = []

                # 检查是否有错误
                if "error_code" in data:
                    return {
                        "success": False,
                        "error": f"百度API错误: {data.get('error_msg', 'Unknown error')} (code: {data['error_code']})",
                        "result": None,
                    }

                if "result" in data and isinstance(data["result"], list):
                    for item in data["result"][:count]:
                        results.append(
                            {
                                "title": item.get("title", ""),
                                "description": item.get("summary", ""),
                                "url": item.get("url", ""),
                            }
                        )

                return {
                    "success": True,
                    "error": None,
                    "query": query,
                    "result_count": len(results),
                    "results": results,
                }

    async def _search_with_bing(self, query: str, count: int, api_key: str) -> dict:
        """使用 Bing Search API 进行搜索（备选）"""
        import os

        endpoint = os.environ.get(
            "BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search"
        )

        allowed, error = self._check_url(endpoint)
        if not allowed:
            return {
                "success": False,
                "error": f"Sandbox denied access: {error}",
                "result": None,
            }

        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
        }
        params = {
            "q": query,
            "count": min(count, 20),
            "responseFilter": "Webpages",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                endpoint, headers=headers, params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Bing Search API 错误: {response.status} - {error_text}",
                        "result": None,
                    }

                data = await response.json()
                results = []

                if "webPages" in data and "value" in data["webPages"]:
                    for item in data["webPages"]["value"][:count]:
                        results.append(
                            {
                                "title": item.get("name", ""),
                                "description": item.get("snippet", ""),
                                "url": item.get("url", ""),
                                "display_url": item.get("displayUrl", ""),
                            }
                        )

                return {
                    "success": True,
                    "error": None,
                    "query": query,
                    "result_count": len(results),
                    "results": results,
                }

    async def _search_with_free_service(self, query: str, count: int) -> dict:
        """使用免费的搜索服务：DuckDuckGo 零点击 API
        注意：这是一个简化实现，生产环境建议使用正规的搜索API
        """
        # 使用 DuckDuckGo 零点击 API
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&no_redirect=1"

        allowed, error = self._check_url(url)
        if not allowed:
            return {
                "success": False,
                "error": f"Sandbox denied access: {error}",
                "result": None,
            }

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"DuckDuckGo API 错误: {response.status}",
                        "result": None,
                    }

                data = await response.json()
                results = []

                # 获取相关结果
                if "RelatedTopics" in data:
                    for topic in data["RelatedTopics"][:count]:
                        if "Text" in topic and "FirstURL" in topic:
                            results.append(
                                {
                                    "title": topic.get("Text", "").split(" - ")[0],
                                    "description": topic.get("Text", ""),
                                    "url": topic.get("FirstURL", ""),
                                }
                            )

                # 如果有摘要，添加到结果开头
                if "AbstractText" in data and data["AbstractText"]:
                    results.insert(
                        0,
                        {
                            "title": data.get("Heading", "摘要"),
                            "description": data["AbstractText"],
                            "url": data.get("AbstractURL", ""),
                        },
                    )

                return {
                    "success": True,
                    "error": None,
                    "query": query,
                    "result_count": len(results),
                    "results": results,
                    "note": "默认使用 DuckDuckGo 免费 API，如需更好的中文搜索效果请配置 BAIDU_API_KEY (百度) 或 BING_SEARCH_API_KEY (Bing) 环境变量",
                }
