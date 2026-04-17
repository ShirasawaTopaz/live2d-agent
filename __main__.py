import asyncio
import logging

from internal.app.live2d_agent_app import Live2DAgentApp


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


if __name__ == "__main__":
    asyncio.run(Live2DAgentApp().run())
