import aiofiles
import logging

logger = logging.getLogger(__name__)

async def write_file(filename: str, content: str):
    """
    Asynchronously writes content to a file.
    
    Args:
        filename: Path to the file to write
        content: Content to write to the file
    """
    try:
        async with aiofiles.open(filename, mode='w') as f:
            await f.write(content)
        logger.info(f"Successfully wrote file: {filename}")
    except Exception as e:
        logger.error(f"Error writing file: {filename}")
        logger.debug(f"Detailed error: {str(e)}")
        raise
