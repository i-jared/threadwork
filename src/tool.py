import asyncio
from pathlib import Path
import logging
import json

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
        print("jl:", build_output, "jl")
        # Parse TypeScript errors into structured format
        errors = []
        for line in build_output.split('\n'):
            if not line:
                continue
            print("jl2:", line, "jl")
            try:
                # Parse TypeScript error format: "file(line,col): error CODE: message"
                file_loc, error_details = line.split(': error ', 1)
                error_code, error_message = error_details.split(': ', 1)
                
                # Parse file location: "file(line,col)"
                file_path = file_loc[:file_loc.find('(')]
                line_col = file_loc[file_loc.find('(')+1:file_loc.find(')')].split(',')
                line_num = int(line_col[0])
                col_num = int(line_col[1])
                
                error_obj = {
                    "file": file_path,
                    "line": line_num,
                    "column": col_num,
                    "code": error_code,
                    "message": error_message,
                    "raw": line
                }
                print("jl3:", error_obj, "jl")
                errors.append(error_obj)
            except Exception as e:
                logger.warning(f"Failed to parse error line: {line}, error: {str(e)}")
                continue
        
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


