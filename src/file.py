import aiofiles
import logging
import os

logger = logging.getLogger(__name__)

async def write_file(filename: str, content: str):
    """
    Asynchronously writes content to a file, creating directories if needed.
    
    Args:
        filename: Path to the file to write
        content: Content to write to the file
    """
    try:
        # Create directories if they don't exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        async with aiofiles.open(filename, mode='w') as f:
            await f.write(content)
        logger.info(f"Successfully wrote file: {filename}")
    except Exception as e:
        logger.error(f"Error writing file: {filename}")
        logger.debug(f"Detailed error: {str(e)}")
        raise

def parse_json_response(response: str) -> dict:
    """
    Parse a JSON response that may be wrapped in markdown code blocks.
    
    Args:
        response: String containing either raw JSON or markdown-formatted JSON
        
    Returns:
        Parsed JSON dictionary
        
    Raises:
        JSONDecodeError: If JSON parsing fails
    """
    import json
    import re
    
    try:
        # Try to extract JSON from markdown code blocks if present
        # Updated pattern to handle triple backticks and optional language label
        json_pattern = r"````?(?:json)?\s*([\s\S]*?)````?"
        match = re.search(json_pattern, response)
        
        if match:
            # Found JSON in code block, parse the contents
            json_str = match.group(1)
        else:
            # No code block found, try parsing the raw response
            json_str = response
            
        # Clean up any remaining markdown artifacts and whitespace
        json_str = json_str.strip()
        
        # Handle case where the content itself contains markdown code blocks
        if json_str.startswith('```') and json_str.endswith('```'):
            inner_match = re.search(json_pattern, json_str)
            if inner_match:
                json_str = inner_match.group(1).strip()
        return json.loads(json_str)
        
    except json.JSONDecodeError as e:
        # Log the detailed error but return a simplified message
        import logging
        logging.error(f"JSON parsing failed: {str(e)}\nResponse: {response}")
        raise json.JSONDecodeError("Failed to parse JSON response", doc=response, pos=e.pos)
