import asyncio
from pathlib import Path
import logging
import json
import re

# Set up logging
logger = logging.getLogger(__name__)

async def run_build_check() -> dict:
    """
    Executes build check operations using 'bun run build' command and parses TypeScript errors.

    Returns:
        dict: {
            "build_success": bool,
            "build_output": list[dict] # List of parsed error objects
        }
    """
    logger.info("Build Check: Starting build verification.")
    result = {}

    # Define the React app project directory
    project_dir = Path("my-react-app")
    if not project_dir.exists():
        error_msg = f"React app directory '{project_dir}' does not exist."
        logger.error(error_msg)
        raise Exception(error_msg)

    src_dir = project_dir / "src"
    if not src_dir.exists():
        error_msg = f"'src' directory '{src_dir}' does not exist in the React app."
        logger.error(error_msg)
        raise Exception(error_msg)

    # Execute the build command using 'bun run build' in the project directory
    build_cmd = "bun run build"
    try:
        proc = await asyncio.create_subprocess_shell(
            build_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_dir)
        )
        stdout, stderr = await proc.communicate()
        build_output = stdout.decode().strip() if stdout else ""
        
        # Define regex pattern for TypeScript errors
        ts_error_regex = re.compile(
            r'^(?P<file>.*)\((?P<line>\d+),(?P<column>\d+)\): error (?P<code>TS\d+): (?P<message>.*)$'
        )
        
        # Parse TypeScript errors into structured format
        errors = []
        current_error = None
        
        for line in build_output.split('\n'):
            line = line.strip()
            if not line:
                continue
                
            match = ts_error_regex.match(line)
            if match:
                # This is a brand-new error line
                current_error = {
                    "file": match.group('file'),
                    "line": int(match.group('line')),
                    "column": int(match.group('column')),
                    "code": match.group('code'),
                    "message": match.group('message'),
                    "raw": line
                }
                errors.append(current_error)
            elif current_error:
                # Append continuation lines to the current error
                current_error["message"] += "\n" + line
                current_error["raw"] += "\n" + line
        
        if errors:
            logger.warning(f"Build completed with errors: {len(errors)} errors found")
            result["build_success"] = False
            result["build_errors"] = errors
            # Save errors to JSON file
            with open('src/some.json', 'w') as f:
                json.dump(result, f, indent=2)
        else:
            logger.info("Build completed successfully")
            result["build_success"] = True
                    
    except Exception as e:
        logger.error(f"Build Check: Exception during build: {str(e)}")
        raise

    return result


