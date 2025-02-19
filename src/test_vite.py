import asyncio
import logging
from pathlib import Path
from agent import create_react_app
from logging_config import setup_logging

# Set up logging
setup_logging()
logger = logging.getLogger(__name__)

async def main():
    try:
        await create_react_app()
    except Exception as e:
        logger.error(f"Failed to create React app: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 