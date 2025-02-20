import asyncio
import logging
from agent import post_react_agent
import aiohttp
import os

gemini_config = {
    "provider": "gemini",
    "api_key": os.getenv('GEMINI_API_KEY'),
    "max_tokens": 100000,
    "model": "gemini-2.0-flash"
}
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    try:
        result = await post_react_agent(gemini_config, aiohttp.ClientSession)
        logger.info(f"Result: {result}")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 
