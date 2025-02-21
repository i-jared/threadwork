import asyncio
import aiohttp
import subprocess
from pathlib import Path
import logging
import os
import json
from langfuse.decorators import langfuse_context, observe
from dotenv import load_dotenv
from config import build_api_request, extract_api_response
from file import write_file, parse_json_response
from logging_config import setup_logging
from type import ComponentDict, SplitComponentDict, validate_component_dict, validate_split_output
import shutil
import aiofiles
from tool import run_build_check
import re


# Load environment variables
load_dotenv()

# -------------------------
# Logging Configuration
# -------------------------
setup_logging()  # Initialize logging
logger = logging.getLogger(__name__)
# -------------------------
# Agent Definitions
# -------------------------

@observe(as_type="generation")
async def make_api_call(prompt: str, api_config: dict, session: aiohttp.ClientSession) -> dict:
    """
    Makes an API call to the given endpoint with the headers and body.
    Includes retry logic for rate limit (429) errors.
    """
    config = build_api_request(prompt, api_config)
    max_retries = 6
    base_delay = 4  # Base delay in seconds
    
    langfuse_context.update_current_observation(
      name=api_config["fx"],
      input=prompt,
      model=api_config["model"],
      metadata={
          "provider": api_config["provider"]
      }
    )

    for attempt in range(max_retries):
        try:
            async with session.post(config["api_endpoint"], 
                                  headers=config["headers"], 
                                  data=config["body"]) as response:
                response_text = await response.text()
                
                if response.status == 429:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        logger.warning(f"Rate limit hit, retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        error_msg = "Max retries reached for rate limit error"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                        
                if response.status != 200:
                    error_msg = f"API request failed with status {response.status}: {response_text}"
                    logger.error(error_msg)
                    logger.debug(f"Request details: endpoint={config['api_endpoint']}, headers={config['headers']}")
                    raise Exception(error_msg)
                
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse response as JSON: {response_text}")
                    raise
                
                logger.debug(f"API Response: {result}")
                api_output = extract_api_response(result, api_config["provider"])

                # Update with generation details
                langfuse_context.update_current_observation(
                    usage_details={
                        "input": api_output["usage"]["input_tokens"],
                        "output": api_output["usage"]["output_tokens"]
                    }
                )
                return api_output

        except aiohttp.ClientError as e:
            error_msg = f"Network error during API call: {str(e)}"
            logger.error(error_msg)
            logger.debug(f"Request details: endpoint={config['api_endpoint']}, headers={config['headers']}")
            raise Exception(error_msg) from e
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse API response as JSON: {str(e)}\nResponse text: {response_text}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
        except Exception as e:
            if attempt < max_retries - 1 and "429" in str(e):
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Rate limit hit, retrying in {delay} seconds...")
                await asyncio.sleep(delay)
                continue
            error_msg = f"Unexpected error during API call: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    raise Exception("Max retries reached")


async def splitting_agent(input: dict, config: dict, session: aiohttp.ClientSession) -> SplitComponentDict:
    """
    Splitting Agent:
    Splits the component/page description into smaller chunks.

    Input format: ComponentDict
    Output format: SplitComponentDict
    """
    # Validate input
    input = validate_component_dict(input, "Splitting Agent (input)")
    
    logger.info("Splitting Agent: Starting splitting process.")
    prompt = f"""Split the following {input['type']} app UI description into smaller UI chunks. Only include UI elements.
    Each part should be a single component or a single page.
    Give each part a short summary (less than 20 words) that clearly states its purpose. Make sure to name files correctly, e.g., App.tsx, Login.tsx, BlahBlah.tsx, etc.

    IMPORTANT SPLITTING GUIDELINES:
    DO split when you see:
    - Completely separate pages (e.g., a login page and a dashboard page)
    - Major reusable components (e.g., a complex data table component that appears in multiple places)

    DO NOT split:
    - Simple UI elements that belong together (e.g., don't separate a form's input fields into individual components)
    - Related elements that form a cohesive unit (e.g., keep a card's header, body, and footer together)

    ```
    {input['description']}
    ```

    The format MUST be EXACTLY as follows, with NO additional text, whitespace, or characters whatsoever. Any deviation will cause an error:

    \'{{'
        "name": "{input['name']}",
        "type": "{input['type']}",
        "parts": [
            \'{{'
                "name": "generated name of the described part (eg. login.jsx, big_button.jsx, etc.)",
                "description": "detailed technical description of implementation",
                "summary": "short description of the part (<20 words)",
                "type": "type of the part, MUST BE EITHER 'component' or 'page'"
            \'}}'
        ]
    \'}}'
    """
    try:
        config["fx"] = "splitting"
        api_output = await make_api_call(prompt, config, session)
        logger.info("Splitting Agent: Successfully split project")
        
        result = parse_json_response(api_output["content"])
        validated_result = validate_split_output(result, "Splitting Agent")
        
        return validated_result

    except Exception as e:
        logger.error("Splitting Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise


async def planning_agent(input: str, config: dict, session: aiohttp.ClientSession) -> ComponentDict:
    """
    Planning Agent:
    Creates a structured project plan from the idea.
    """
    logger.info("Planning Agent: Starting planning process.")
    prompt = f"""Create a detailed description for the UI of the following app. Only include UI elements and pages in a 
    high level overview. 
    Make sure to add a App.tsx file to the project.
    ```
    {input}
    ```

    Your output MUST be EXACTLY in this JSON format, with NO additional text, whitespace, or characters whatsoever. Any deviation will cause an error:
    {{
        "description": "str : <detailed plan here>",
        "summary": "str: <very short summary of the project - what is it, what UI tech stack you're using, etc.>",
        "name": "str: <name of main file of the project>",
        "path": "str: <typical path to main file of the project>",
        "type": "page"
    }}"""
    try:
        config["fx"] = "planning"
        api_output = await make_api_call(prompt, config, session)
        logger.info("Planning Agent: Successfully received API response")
        logger.debug(f"Planning Agent: Raw response: {api_output}")
        
        logger.debug(f"Planning Agent: Extracted output: {api_output}")
        
        try:
            if not api_output.get("content"):
                raise ValueError("No content in API output")
                
            result = parse_json_response(api_output["content"])
            logger.debug(f"Planning Agent: Parsed result: {result}")
            
            validated_result = validate_component_dict(result, "Planning Agent")
            logger.info("Planning Agent: Successfully validated result")
            
            return validated_result
            
        except json.JSONDecodeError as e:
            logger.error(f"Planning Agent: Failed to parse JSON content: {api_output.get('content')}")
            logger.debug(f"JSON Error: {str(e)}")
            raise ValueError(f"Invalid JSON in API response: {str(e)}") from e
        except Exception as e:
            logger.error(f"Planning Agent: Error processing API output: {str(e)}")
            logger.debug(f"API Output: {api_output}")
            raise
            
    except Exception as e:
        logger.error("Planning Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise


async def development_agent(input: dict, project_config: dict, config: dict, session: aiohttp.ClientSession) -> bool:
    """
    Development Agent:
    Produces code files based on the provided description and name.
    Styles using Tailwind CSS.

    Input format: ComponentDict (must include path)
    Output: True if successful, False otherwise
    """
    # Validate input and ensure path exists
    input = validate_component_dict(input, "Development Agent (input)")

    if "path" not in input:
        raise ValueError("Development Agent input must include path field")
    
    logger.info("Development Agent: Starting development process.")

    # Get component descriptions if they exist
    component_descriptions = []
    if "parts" in input:
        for part in input["parts"]:
            component_descriptions.append(f"{part['path']}: {part['summary']}")

    prompt = f"""
    Write the code for the following page or component, keeping in mind the following project details:
    page/component name, and use tailwind css for any styling:
    {input["name"]}
    project details:
    {project_config["summary"]}

    component details:
    ```
    {input["description"]}
    ```

    {
    'Available components and their purposes:\n' + '\n'.join(component_descriptions) if component_descriptions else 
    ''
    }

    Output just the code, nothing else.
    """

    try:
        config["fx"] = "development"
        api_output = await make_api_call(prompt, config, session)
        logger.info(f"Development Agent: Successfully generated code")
        
        code = api_output["content"]
        
        # Extract code from possible markdown code block
        if code.startswith("```"):
            lines = code.split("\n")
            # Remove first line (```language) and last line (```)
            code = "\n".join(lines[1:-1])
        
        # Get the file content from the response
        file_info = input.get("path", {})
        if not file_info:
            logger.error("Development Agent: No file information in input")
            return False
            
        filename = input["path"]
        content = code
        #  determin what packages are being imported using regex, but make sure to ignore our file imports or importing react
        
        # The regex pattern (with re.MULTILINE for line-by-line matching)
        import_pattern = re.compile(
            r"^import\s+(?:{[^}]*}|\w+)\s+from\s+'(?!(?:\.\/|\.\.\/|react(?=['/]|$)))([^']+)';$",
            re.MULTILINE
        )

        # Find all matching import package names
        imports = import_pattern.findall(content)
        logger.info(f"Development Agent: Imports: {imports}")

        def get_install_package(package: str) -> str:
            """
            Returns the base package name for installation.
            
            For unscoped packages (like 'react-icons/fa'), returns only the first segment (e.g., 'react-icons').
            For scoped packages (like '@scope/package/subpath'), returns the first two segments (e.g., '@scope/package').
            Otherwise, returns the package as is.
            """
            if package.startswith('@'):
                parts = package.split('/')
                # Return only the scope and package name.
                return '/'.join(parts[:2])
            else:
                # For non-scoped packages, only take the first segment.
                return package.split('/')[0]

        # Loop over each found package and run "bun add" with the processed package name.
        for package in imports:
            install_package = get_install_package(package)
            logger.info(f"Adding package: {install_package} (from import: {package})")
            subprocess.run(f"bun add {install_package}", shell=True, check=True, cwd="my-react-app")
            if not filename or not content:
                logger.error("Development Agent: Missing filename or content in response")
                return False
            
        await write_file(filename, content)
        logger.info(f"Development Agent: Successfully processed file {filename}")
        return True

    except Exception as e:
        logger.error("Development Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def expounding_agent(input: dict, config: dict, session: aiohttp.ClientSession) -> ComponentDict:
    """
    Expounding Agent:
    Given a component/page dictionary with name, type and description,
    increase the detail and resolution of the description while preserving
    the original name and type. 

    Input format: ComponentDict
    Output format: ComponentDict
    """
    # Validate input
    input = validate_component_dict(input, "Expounding Agent (input)")
    
    logger.info("Expounding Agent: Starting expounding process.")
    prompt = f"""Given the following component/page description, increase the detail and resolution of the description.
    Preserve the original name and type. Only include UI elements. Focus solely on the UI.
    Return the result EXACTLY in the following JSON format, with NO additional text, whitespace, or characters whatsoever. Any deviation will cause an error:


    \'{{'
        "name": "{input['name']}",
        "type": "{input['type']}",
        "description": "expanded detailed description"
    \'}}'

    Input description:

    <start description>
    {input['description']}
    <end description>

    Output just the JSON object, nothing else.
    """
    try:
        config["fx"] = "expounding"
        api_output = await make_api_call(prompt, config, session)
        logger.debug("Expounding Agent: Generated expanded spec")

        result = parse_json_response(api_output["content"])
        return validate_component_dict(result, "Expounding Agent")

    except Exception as e:
        logger.error("Expounding Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def routing_agent(input: str, config: dict, session: aiohttp.ClientSession) -> str:
    """
    Routing Agent:
    Analyzes input and determines whether it needs more detail, should be split up,
    or is ready to be written to a file.
    
    Returns one of: "detail", "split", "write"
    """
    logger.info("Routing Agent: Starting routing process.")
    prompt = f"""Analyze the following app segment description and determine if it:
    1. Needs more detail before it can be processed (output "detail")
    2. Contains multiple components that should have their own files and should be split up (output "split")
    3. Has enough detail and is focused enough to be written to one file (output "write")

    <start description>
    {input}
    <end description>

    CRITICAL: You MUST output EXACTLY one of these three words, with no punctuation, no spaces before or after, no newlines, and in lowercase:
    detail
    split
    write
    """

    try:
        config["fx"] = "routing"
        api_output = await make_api_call(prompt, config, session)
        logger.info("Routing Agent: Successfully determined route")
        
        route = api_output["content"].strip().lower()
        
        if route not in ["detail", "split", "write"]:
            logger.error(f"Routing Agent: Invalid route '{route}'")
            raise ValueError(f"Invalid route: {route}")
            
        return route

    except Exception as e:
        logger.error("Routing Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

def prepare_component_config(components: dict) -> dict:
    """
    Helper function to prepare component configuration including paths and component list.
    """
    config = {
        "name": components["name"],
        "type": components["type"],
        "description": components["description"]
    }

    # Only set path if not already present
    if "path" not in components:
        config["path"] = 'my-react-app/src/pages/' + components["name"] if components["type"] == "page" else 'my-react-app/src/components/' + components["name"]
    else:
        config["path"] = components["path"]

    # Only add components key if parts exist
    if "parts" in components:
        # Set paths for components that don't have them
        for component in components["parts"]:
            if "path" not in component:
                component["path"] = 'my-react-app/src/pages/' + component["name"] if component["type"] == "page" else 'my-react-app/src/components/' + component["name"]
        
        config["parts"] = [{"path": component["path"], "summary": component["summary"]} for component in components["parts"]]

    return config


# async def fix_build_errors_agent(errors: list[dict], config: dict, session: aiohttp.ClientSession) -> bool:
#     """
#     Fix Build Errors Agent:
#     Analyzes build errors and attempts to fix them by:
#     1. Creating missing local files with stub content
#     2. Adding missing package dependencies
#     3. Creating type definitions where needed

#     Args:
#         errors: List of error objects from build check
#         config: Configuration for API calls
#         session: aiohttp session for API calls

#     Returns:
#         bool: True if fixes were applied, False if no fixes needed
#     """
#     logger.info("Fix Build Errors Agent: Starting error analysis")
    
#     project_dir = Path("test/my-react-app")
#     src_dir = project_dir / "src"
#     package_json_path = project_dir / "package.json"
    
#     # Group errors by type
#     missing_modules = []
#     type_errors = []
#     other_errors = []
    
#     for error in errors:
#         if error["code"] == "TS2307":  # Cannot find module
#             missing_modules.append(error)
#         elif error["code"].startswith("TS"):  # Type-related errors
#             type_errors.append(error)
#         else:
#             other_errors.append(error)
    
#     # Log categorized errors
#     if missing_modules:
#         logger.info("Missing Module Errors:")
#         for error in missing_modules:
#             logger.info(f"  • missing module: {error['file']}: {error['message']}")
            
#     if type_errors:
#         logger.info("Type Errors:")
#         for error in type_errors:
#             logger.info(f"  • type error: {error['file']}: {error['message']}")
            
#     if other_errors:
#         logger.info("Other Errors:")
#         for error in other_errors:
#             logger.info(f"  • other error: {error['file']}: {error['message']}")
            
#     if not any([missing_modules, type_errors, other_errors]):
#         logger.info("No errors to fix")
#         return False
        
#     # Handle missing modules first
#     for error in missing_modules:
#         module_name = error["message"].split("'")[1]  # Extract module name from error message
        
#         if module_name.startswith("."):
#             # Local module
#             file_path = (src_dir / module_name).with_suffix(".ts")
#             if not file_path.exists():
#                 # Generate stub file content based on the import path
#                 prompt = f"""Create a minimal TypeScript stub file for: {module_name}
#                 This should include basic types/interfaces/exports that would be expected from this module.
#                 Include TODO comments for implementation. Context: This file is imported in {error['file']}.
#                 Output just the code, nothing else. No backticks. Just code."""
                
#                 try:
#                     config["fx"] = "stub_generation"
#                     api_output = await make_api_call(prompt, config, session)
                    
#                     # Ensure directory exists
#                     file_path.parent.mkdir(parents=True, exist_ok=True)
                    
#                     # Write stub file
#                     await write_file(str(file_path), api_output["content"])
#                     logger.info(f"Created stub file: {file_path}")
                    
#                 except Exception as e:
#                     logger.error(f"Failed to create stub file {file_path}: {str(e)}")
#                     continue
#         else:
#             # Package module
#             try:
#                 with open(package_json_path) as f:
#                     package_json = json.load(f)
                
#                 # Check if package is already in dependencies or devDependencies
#                 all_deps = {
#                     **package_json.get("dependencies", {}),
#                     **package_json.get("devDependencies", {})
#                 }
                
#                 if module_name not in all_deps:
#                     # Generate package.json update prompt
#                     prompt = f"""What is the appropriate version of {module_name} to add to package.json?
#                     Consider:
#                     - Current React version: {package_json.get('dependencies', {}).get('react', 'unknown')}
#                     - TypeScript version: {package_json.get('devDependencies', {}).get('typescript', 'unknown')}
#                     Output only the version number, nothing else."""
                    
#                     try:
#                         config["fx"] = "package_version"
#                         api_output = await make_api_call(prompt, config, session)
#                         version = api_output["content"].strip()
                        
#                         # Add to dependencies
#                         if not "dependencies" in package_json:
#                             package_json["dependencies"] = {}
#                         package_json["dependencies"][module_name] = version
                        
#                         # Write updated package.json
#                         with open(package_json_path, 'w') as f:
#                             json.dump(package_json, f, indent=2)
                            
#                         logger.info(f"Added {module_name}@{version} to package.json")
                        
#                         # Run package installer
#                         subprocess.run(
#                             "bun install",
#                             shell=True,
#                             check=True,
#                             cwd=project_dir
#                         )
#                         logger.info("Ran bun install")
                        
#                     except Exception as e:
#                         logger.error(f"Failed to add package {module_name}: {str(e)}")
#                         continue
                        
#             except Exception as e:
#                 logger.error(f"Failed to process package.json: {str(e)}")
#                 continue
    
#     # Handle type errors by creating type definitions if needed
#     for error in type_errors:
#         if "does not exist on type" in error["message"] or "has no exported member" in error["message"]:
#             # Extract the type or member name
#             prompt = f"""Create TypeScript type definitions to fix this error:
#             Error: {error['message']}
#             File: {error['file']}
#             Line: {error['line']}
            
#             Output just the TypeScript type definitions, nothing else."""
            
#             try:
#                 config["fx"] = "type_generation"
#                 api_output = await make_api_call(prompt, config, session)
                
#                 # Create or update types file
#                 types_path = src_dir / "types.ts"
                
#                 # Append new types to existing file or create new file
#                 async with aiofiles.open(types_path, 'a') as f:
#                     await f.write("\n\n" + api_output["content"])
                    
#                 logger.info(f"Added type definitions to {types_path}")
                
#             except Exception as e:
#                 logger.error(f"Failed to create type definitions: {str(e)}")
#                 continue
    
#     return True

# async def post_react_agent(config: dict, session: aiohttp.ClientSession) -> dict:
#     """
#     Post-React Agent:
#     Executes post-react operations such as build checking and fixing errors.
#     """
#     logger.info("Post-React Agent: Starting post-react operations.")
    
#     try:
#         # Run initial build check
#         result = await run_build_check()
        
#         if not result["build_success"]:
#             async with aiohttp.ClientSession() as session:
#                 # Attempt to fix build errors
#                 fixes_applied = await fix_build_errors_agent(result["build_errors"], config, session)
                
#                 if fixes_applied:
#                     # Run build check again after fixes
#                     result = await run_build_check()
        
#         # Get the file list from src directory
#         project_dir = Path("test/my-react-app")
#         src_dir = project_dir / "src"
#         result["src_files"] = [f.name for f in src_dir.iterdir() if f.is_file()]
        
#         logger.info("Post-React Agent: Operations completed successfully")
#         return result

#     except Exception as e:
#         logger.error(f"Post-React Agent: Error encountered: {str(e)}")
#         raise

# -------------------------
# Add Installs
# -------------------------
async def create_react_app():
    """Creates a new Vite React-TypeScript project with initial setup"""
    try:        
        # Create the React app using bun
        subprocess.run(
            "bun create vite my-react-app --template react-ts",
            shell=True,
            check=True,
        )
        logger.info("✅ React app created successfully")
        
        # Install dependencies
        app_dir = "my-react-app"
        subprocess.run(
            "bun install",
            shell=True,
            check=True,
            cwd=app_dir
        )
        
        # Install Tailwind CSS and its dependencies
        subprocess.run(
            "bun add -d tailwindcss@3 postcss autoprefixer",
            shell=True,
            check=True,
            cwd=app_dir
        )
        logger.info("✅ Tailwind CSS and dependencies installed")
        
        # Initialize Tailwind CSS configuration
        subprocess.run(
            "bunx tailwindcss@3 init -p",
            shell=True,
            check=True,
            cwd=app_dir
        )
        
        # Update tailwind.config.js
        tailwind_config = """/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
"""
        with open(app_dir / "tailwind.config.js", "w") as f:
            f.write(tailwind_config)
            
        # Update src/index.css with Tailwind directives
        tailwind_css = """@tailwind base;
@tailwind components;
@tailwind utilities;
"""
        with open(app_dir / "src" / "index.css", "w") as f:
            f.write(tailwind_css)
            
        print("✅ Tailwind CSS configured successfully")
        
    except subprocess.CalledProcessError as e:
        print("❌ Error creating React app")
        print(f"Command failed with exit code {e.returncode}")
        return True  # Return something to make the await valid

    except Exception as e:
        print("❌ An error occurred during deployment")
        print(f"Error details logged")
        # Log the full error message
        print(f"DEBUG: {str(e)}")

# -------------------------
# Workflow Execution
# -------------------------

@observe()
async def execute_workflow(description: str):
    """
    Executes the workflow with Langfuse tracing in the following pattern:
    1. Blueprint creation
    2. Stub file generation (optional)
    3. Planning
    4. Initial splitting
    5. Development loop
    """
    
    try:
        success = await create_react_app()
        if success:
            logger.info("✅ Vite React app setup completed")
    except Exception as e:
        logger.error(f"Workflow: Error creating React app: {str(e)}")
        raise

    os.makedirs('my-react-app/src/components', exist_ok=True)
    os.makedirs('my-react-app/src/pages', exist_ok=True)
    if os.path.exists('my-react-app/src/App.tsx'):
        os.remove('my-react-app/src/App.tsx')

    claude_config = {
        "provider": "anthropic",
        "api_key": os.getenv('ANTHROPIC_API_KEY'),
        "max_tokens": 8192,
        "model": "claude-3-5-sonnet-20241022"
    }

    gemini_config = {
        "provider": "gemini",
        "api_key": os.getenv('GEMINI_API_KEY'),
        "max_tokens": 100000,
        "model": "gemini-2.0-flash"
    }

    deepseek_config = {
        "provider": "deepseek",
        "api_key": os.getenv('DEEPSEEK_API_KEY'),
        "max_tokens": 10000,
        "model": "deepseek-reasoner"
    }

    default_config = gemini_config

    project_config = {
        "user_description": description,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Generate complete blueprint
            blueprint = await blueprint_agent(description, default_config, session)
            
            # Generate prop contracts
            prop_contracts = await prop_contract_agent(blueprint, default_config, session)
            
            # Generate initial files
            for file_info in blueprint["files"]:
                try:
                    code = await generate_file_code(file_info, blueprint, prop_contracts, default_config, session)
                    await write_file(f"my-react-app/src/{file_info['path']}", code)
                except Exception as e:
                    logger.error(f"Failed to generate {file_info['path']}: {str(e)}")
                    continue
            
            # Perform iterative build checks and fixes
            build_success = await iterative_build_check(blueprint, prop_contracts, default_config, session)
            if build_success:
                logger.info("Successfully completed all build checks")
            else:
                logger.warning("Some build errors could not be fixed automatically")

            # Generate prop contracts
            prop_contracts = await prop_contract_agent(blueprint, default_config, session)
            
            # Optionally create stub files
            if blueprint["validation"]["allLocalImportsExist"] and blueprint["validation"]["noCyclicalDependencies"]:
                await create_stubs(blueprint)
            
            # Generate each file
            for file_info in blueprint["files"]:
                try:
                    # Generate the code with prop contracts
                    code = await generate_file_code(file_info, blueprint, prop_contracts, default_config, session)
                    
                    # Validate the generated code
                    is_valid, issues = await validate_generated_code(code, file_info, blueprint)
                    if not is_valid:
                        logger.error(f"Code validation failed for {file_info['path']}")
                        for issue in issues:
                            logger.error(f"  - {issue}")
                        continue
                    
                    # Process and install any npm imports
                    await process_npm_imports(code, "my-react-app")
                    
                    # Write and validate the file
                    success = await write_and_validate_file(file_info, code, blueprint)
                    if success:
                        logger.info(f"Successfully generated and validated {file_info['path']}")
                    else:
                        logger.error(f"Failed to generate or validate {file_info['path']}")
                
                except Exception as e:
                    logger.error(f"Error processing file {file_info['path']}: {str(e)}")
                    continue
            
            # Continue with existing workflow
            plan = await planning_agent(description, default_config, session)
            project_config["summary"] = plan["summary"]

            # Initial splitting
            components = await splitting_agent(plan, gemini_config, session)
            
            # Prepare initial config and develop main component
            components["description"] = plan["description"]
            config = prepare_component_config(components)
            config["path"] = 'my-react-app/src/' + components["name"]
    
            asyncio.create_task(development_agent(config, project_config, default_config, session))
    
            # Process queue for components that need work
            work_queue = components["parts"] 
            
            while work_queue:
                current_batch = work_queue.copy()
                work_queue.clear()
                
                # Process all current components concurrently
                async with asyncio.TaskGroup() as tg:
                    for component in current_batch:
                        # Determine next steps
                        route = await routing_agent(component["description"], gemini_config, session)
                        
                        if route == "detail":
                            # Need more detail - send to expounding then splitting
                            expanded = await expounding_agent(component, gemini_config, session)
                            split_components = await splitting_agent(expanded, gemini_config, session)
                            
                            split_components["description"] = expanded["description"]
                            config = prepare_component_config(split_components)
                            tg.create_task(development_agent(config, project_config, default_config, session))
                            work_queue.extend(split_components["parts"])
                                
                        elif route == "split":
                            # Need to split - send to splitting
                            split_components = await splitting_agent(component, gemini_config, session)
                            
                            split_components["description"] = component["description"]
                            config = prepare_component_config(split_components)
                            tg.create_task(development_agent(config, project_config, default_config, session))
                            work_queue.extend(split_components["parts"])
                        else:
                            # Ready to write - send to development
                            config = prepare_component_config(component)
                            tg.create_task(development_agent(config, project_config, default_config, session))
    
        logger.info("Workflow: Execution completed successfully")
        # Zip the react folder
        output_filename = "project_files"
        directory = 'my-react-app'

        try:
            # # Run post-react agent
            # result = await post_react_agent(gemini_config, session)
            # if result["build_success"]:
            #     logger.info("✅ Build check completed successfully")
            # else:
            #     logger.info("❌ Build check failed")
                
            # Zip the react folder
            shutil.make_archive(output_filename, 'zip', directory)
            logger.info(f"Workflow: Successfully zipped react folder to {output_filename}.zip")
            

            
        except Exception as e:
            logger.error(f"Workflow: Error zipping react folder: {str(e)}")
        
    except Exception as e:
        logger.error("Workflow: Execution failed")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def blueprint_agent(input: str, config: dict, session: aiohttp.ClientSession) -> dict:
    """
    Blueprint Agent:
    Creates a complete file list with detailed information about each file's
    imports, exports, and purpose.

    Args:
        input: Project description and requirements
        config: API configuration
        session: aiohttp session

    Returns:
        dict: Complete blueprint of all files
    """
    logger.info("Blueprint Agent: Starting blueprint creation")
    
    prompt = f"""Create a complete blueprint of all files needed for this React TypeScript project.
    For each file, provide:
    - Exact file path (relative to src/)
    - Short summary of the file's purpose (1-2 sentences)
    - List of exports (components, functions, types, etc.)
    - List of imports (both npm packages and local files)

    Project Description:
    ```
    {input}
    ```

    Return EXACTLY in this JSON format with NO additional text:
    {{
        "files": [
            {{
                "path": "str: relative path from src/ (e.g., components/Header.tsx)",
                "summary": "str: brief description of file purpose",
                "exports": ["list", "of", "exports"],
                "imports": {{
                    "npm": ["list", "of", "npm", "packages"],
                    "local": ["list", "of", "local", "file", "imports"]
                }}
            }}
        ],
        "validation": {{
            "allLocalImportsExist": true,
            "noCyclicalDependencies": true
        }}
    }}"""

    try:
        config["fx"] = "blueprint"
        api_output = await make_api_call(prompt, config, session)
        result = parse_json_response(api_output["content"])
        
        # Validate that all local imports reference existing files
        all_files = {file["path"] for file in result["files"]}
        for file in result["files"]:
            for local_import in file["imports"]["local"]:
                if local_import not in all_files:
                    result["validation"]["allLocalImportsExist"] = False
                    logger.warning(f"Blueprint Agent: Local import {local_import} not found in file list")
        
        # Basic cycle detection with safe neighbor lookup
        def has_cycle(graph, start, visited=None, rec_stack=None):
            if visited is None:
                visited = set()
            if rec_stack is None:
                rec_stack = set()
            
            visited.add(start)
            rec_stack.add(start)
            
            # Only iterate over neighbors that exist in the graph
            for neighbor in graph.get(start, []):
                if neighbor not in visited:
                    if has_cycle(graph, neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(start)
            return False
        
        # Build dependency graph
        dep_graph = {file["path"]: set(file["imports"]["local"]) for file in result["files"]}
        
        # Check for cycles only among existing files
        result["validation"]["noCyclicalDependencies"] = not any(
            has_cycle(dep_graph, start) for start in dep_graph if start in all_files
        )
        
        if not result["validation"]["noCyclicalDependencies"]:
            logger.warning("Blueprint Agent: Detected cyclical dependencies in file structure")
        
        logger.info("Blueprint Agent: Successfully created and validated blueprint")
        return result

    except Exception as e:
        logger.error("Blueprint Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def create_stubs(blueprint: dict) -> None:
    """
    Creates stub files for all files in the blueprint.
    """
    logger.info("Creating stub files from blueprint")
    
    for file in blueprint["files"]:
        path = f"my-react-app/src/{file['path']}"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Generate minimal stub content
        exports = file["exports"]
        imports = file["imports"]
        
        content = ["import React from 'react';"]
        
        # Add npm imports
        for npm_import in imports["npm"]:
            content.append(f"import {npm_import} from '{npm_import}';")
        
        # Add local imports
        for local_import in imports["local"]:
            content.append(f"import {{ {local_import} }} from './{local_import}';")
        
        # Add exports
        for export in exports:
            if export.endswith("Props"):
                content.append(f"\ninterface {export} {{\n  // TODO: Add props\n}}")
            else:
                content.append(f"\nexport function {export}() {{\n  return (\n    <div>TODO: Implement {export}</div>\n  );\n}}")
        
        # Write stub file
        try:
            with open(path, "w") as f:
                f.write("\n".join(content))
            logger.info(f"Created stub file: {path}")
        except Exception as e:
            logger.error(f"Failed to create stub file {path}: {str(e)}")

async def prop_contract_agent(blueprint: dict, config: dict, session: aiohttp.ClientSession) -> dict:
    """
    Prop Contract Agent:
    Creates a central contract defining all component props.
    
    Args:
        blueprint: Complete blueprint of all files
        config: API configuration
        session: aiohttp session
    
    Returns:
        dict: Prop contracts for all components
    """
    logger.info("Prop Contract Agent: Starting contract creation")
    
    # Filter for component files from blueprint
    component_files = [f for f in blueprint["files"] if f["path"].startswith("components/") or f["path"].endswith(".tsx")]
    
    prompt = f"""Create a complete TypeScript prop contract for all React components in this project.
    For each component, define its props interface with proper TypeScript types.

    Component Files:
    ```
    {json.dumps(component_files, indent=2)}
    ```

    Return EXACTLY in this JSON format with NO additional text:
    {{
        "contracts": [
            {{
                "componentName": "str: name of the component",
                "propsInterface": "str: complete TypeScript interface definition",
                "path": "str: path to component file",
                "required": ["list", "of", "required", "prop", "names"],
                "optional": ["list", "of", "optional", "prop", "names"]
            }}
        ],
        "shared": {{
            "types": ["list of shared type definitions"],
            "interfaces": ["list of shared interface definitions"]
        }}
    }}"""

    try:
        config["fx"] = "prop_contract"
        api_output = await make_api_call(prompt, config, session)
        result = parse_json_response(api_output["content"])
        
        # Validate contracts match blueprint components
        blueprint_components = {f["path"]: f["exports"] for f in component_files}
        for contract in result["contracts"]:
            if contract["path"] not in blueprint_components:
                logger.warning(f"Prop Contract Agent: Contract for unknown component {contract['path']}")
            elif f"{contract['componentName']}Props" not in blueprint_components[contract["path"]]:
                logger.warning(f"Prop Contract Agent: Missing Props interface in blueprint for {contract['componentName']}")
        
        logger.info("Prop Contract Agent: Successfully created prop contracts")
        return result

    except Exception as e:
        logger.error("Prop Contract Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def validate_prop_contract(code: str, contract: dict) -> tuple[bool, list[str]]:
    """
    Validates that generated code adheres to the prop contract.
    Returns (is_valid, list_of_issues).
    """
    issues = []
    
    # Extract props interface from code
    interface_pattern = rf"interface\s+{contract['componentName']}Props\s*{{([^}}]+)}}"
    interface_match = re.search(interface_pattern, code)
    
    if not interface_match:
        issues.append(f"Missing props interface for {contract['componentName']}")
        return False, issues
    
    interface_content = interface_match.group(1)
    
    # Check required props
    for prop in contract["required"]:
        if not re.search(rf"{prop}\s*:", interface_content):
            issues.append(f"Missing required prop: {prop}")
    
    # Check for extra props
    prop_pattern = r"(\w+)\s*[?]?\s*:"
    found_props = set(re.findall(prop_pattern, interface_content))
    allowed_props = set(contract["required"] + contract["optional"])
    
    extra_props = found_props - allowed_props
    if extra_props:
        issues.append(f"Unexpected props found: {', '.join(extra_props)}")
    
    return len(issues) == 0, issues

async def generate_file_code(file_info: dict, blueprint: dict, prop_contracts: dict, config: dict, session: aiohttp.ClientSession) -> str:
    """
    Generates code for a single file based on the blueprint specifications and prop contracts.
    """
    logger.info(f"Generating code for file: {file_info['path']}")
    
    # Find matching prop contract if it exists
    contract = next(
        (c for c in prop_contracts.get("contracts", []) if c["path"] == file_info["path"]),
        None
    )
    
    contract_info = ""
    if contract:
        contract_info = f"""
        Props Interface:
        {contract['propsInterface']}
        
        Required Props: {', '.join(contract['required'])}
        Optional Props: {', '.join(contract['optional'])}
        """
    
    prompt = f"""Generate the complete code for this React TypeScript file.
    Strictly follow these specifications:

    File Path: {file_info['path']}
    Summary: {file_info['summary']}
    Required Exports: {', '.join(file_info['exports'])}
    
    Allowed Imports:
    NPM Packages: {', '.join(file_info['imports']['npm'])}
    Local Files: {', '.join(file_info['imports']['local'])}

    {contract_info}

    CRITICAL REQUIREMENTS:
    1. Use ONLY the specified imports - no additional local imports
    2. Implement ALL specified exports
    3. Use Tailwind CSS for styling
    4. Follow React + TypeScript best practices
    5. Include JSDoc comments for components and functions
    6. Implement props interface EXACTLY as specified
    7. Use all required props in the component implementation

    Return ONLY the complete file code, no explanations or markdown formatting.
    """

    try:
        config["fx"] = "file_generation"
        api_output = await make_api_call(prompt, config, session)
        code = api_output["content"]
        
        # Validate prop contract if it exists
        if contract:
            is_valid, issues = await validate_prop_contract(code, contract)
            if not is_valid:
                logger.error(f"Prop contract validation failed for {file_info['path']}")
                for issue in issues:
                    logger.error(f"  - {issue}")
                raise ValueError(f"Generated code does not match prop contract: {', '.join(issues)}")
        
        return code
    except Exception as e:
        logger.error(f"File generation failed for {file_info['path']}: {str(e)}")
        raise

async def validate_generated_code(code: str, file_info: dict, blueprint: dict) -> tuple[bool, list[str]]:
    """
    Validates the generated code against the blueprint specifications.
    Returns (is_valid, list_of_issues).
    """
    issues = []
    
    # Extract imports using regex
    import_pattern = r"import\s+(?:{[^}]*}|\w+)\s+from\s+'([^']+)';"
    found_imports = re.findall(import_pattern, code)
    
    # Check for unauthorized imports
    allowed_imports = set(file_info['imports']['npm'] + file_info['imports']['local'] + ['react'])
    for imp in found_imports:
        if not any(imp.startswith(allowed) for allowed in allowed_imports):
            issues.append(f"Unauthorized import: {imp}")
    
    # Extract exports using regex
    export_pattern = r"export\s+(?:interface|type|function|const|class)\s+(\w+)"
    found_exports = re.findall(export_pattern, code)
    
    # Check for missing exports
    required_exports = set(file_info['exports'])
    found_exports_set = set(found_exports)
    for exp in required_exports:
        if exp not in found_exports_set:
            issues.append(f"Missing export: {exp}")
    
    return len(issues) == 0, issues

async def process_npm_imports(code: str, project_dir: str) -> None:
    """
    Processes npm imports in the code and installs missing packages.
    """
    # Extract all npm imports
    import_pattern = r"import\s+(?:{[^}]*}|\w+)\s+from\s+'(?!\.|\/)([^']+)';"
    npm_imports = re.findall(import_pattern, code)
    
    for package in npm_imports:
        if package != 'react':  # Skip react as it's already installed
            try:
                logger.info(f"Installing npm package: {package}")
                subprocess.run(
                    f"bun add {package}",
                    shell=True,
                    check=True,
                    cwd=project_dir
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install npm package {package}: {str(e)}")
                raise

async def write_and_validate_file(file_info: dict, code: str, blueprint: dict) -> bool:
    """
    Writes the file to disk and performs build validation.
    Returns True if successful, False otherwise.
    """
    try:
        # Write the file
        path = f"my-react-app/src/{file_info['path']}"
        await write_file(path, code)
        
        # Run build check
        build_result = await run_build_check()
        
        if not build_result["build_success"]:
            logger.error(f"Build failed for {path}")
            logger.error(f"Build errors: {build_result['build_errors']}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Failed to write or validate file {path}: {str(e)}")
        return False

async def parse_build_errors(error_output: str) -> list[dict]:
    """
    Parses build error output into structured format.
    Returns list of error objects with file, message, and type.
    """
    errors = []
    
    # Common TypeScript error patterns
    ts_error_pattern = r"(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+) - error TS(?P<code>\d+): (?P<message>.+)"
    module_error_pattern = r"Cannot find module '(?P<module>[^']+)'"
    prop_error_pattern = r"Property '(?P<prop>[^']+)' does not exist on type"
    
    for line in error_output.split('\n'):
        error = {}
        
        # Match TypeScript errors
        ts_match = re.match(ts_error_pattern, line)
        if ts_match:
            error = {
                'file': ts_match.group('file'),
                'type': 'typescript',
                'code': ts_match.group('code'),
                'message': ts_match.group('message'),
                'line': int(ts_match.group('line')),
                'column': int(ts_match.group('col'))
            }
        
        # Check for specific error types
        if module_match := re.search(module_error_pattern, line):
            error['subtype'] = 'module_not_found'
            error['module'] = module_match.group('module')
        elif prop_match := re.search(prop_error_pattern, line):
            error['subtype'] = 'invalid_prop'
            error['prop'] = prop_match.group('prop')
            
        if error:
            errors.append(error)
            
    return errors

async def fix_agent(error: dict, file_content: str, blueprint: dict, prop_contracts: dict, config: dict, session: aiohttp.ClientSession) -> str:
    """
    Generates fixes for build errors based on error type.
    Returns updated file content.
    """
    logger.info(f"Fix Agent: Attempting to fix error in {error['file']}")
    
    # Get relevant file info from blueprint
    file_info = next((f for f in blueprint["files"] if f["path"].endswith(error["file"])), None)
    if not file_info:
        raise ValueError(f"Could not find file info for {error['file']} in blueprint")
    
    # Get prop contract if it exists
    contract = next(
        (c for c in prop_contracts.get("contracts", []) if c["path"] == file_info["path"]),
        None
    )
    
    prompt = f"""Fix the following error in the React TypeScript file:

    Error: {error['message']}
    File: {error['file']}
    Type: {error.get('type')}
    Subtype: {error.get('subtype', 'unknown')}

    Current File Content:
    ```typescript
    {file_content}
    ```

    Blueprint Specifications:
    - Exports: {', '.join(file_info['exports'])}
    - Allowed NPM Imports: {', '.join(file_info['imports']['npm'])}
    - Allowed Local Imports: {', '.join(file_info['imports']['local'])}
    
    {f'''Prop Contract:
    {contract['propsInterface']}
    Required Props: {', '.join(contract['required'])}
    Optional Props: {', '.join(contract['optional'])}''' if contract else ''}

    Return ONLY the complete fixed file content, no explanations.
    """

    try:
        config["fx"] = "fix"
        api_output = await make_api_call(prompt, config, session)
        fixed_code = api_output["content"]
        
        # Validate the fixed code
        is_valid, issues = await validate_generated_code(fixed_code, file_info, blueprint)
        if not is_valid:
            raise ValueError(f"Fixed code validation failed: {', '.join(issues)}")
            
        if contract:
            is_valid, issues = await validate_prop_contract(fixed_code, contract)
            if not is_valid:
                raise ValueError(f"Fixed code prop contract validation failed: {', '.join(issues)}")
        
        return fixed_code
        
    except Exception as e:
        logger.error(f"Fix Agent: Failed to fix error: {str(e)}")
        raise

async def iterative_build_check(blueprint: dict, prop_contracts: dict, config: dict, session: aiohttp.ClientSession, max_iterations: int = 3) -> bool:
    """
    Performs iterative build checks and fixes errors.
    Returns True if all errors are fixed or max iterations reached.
    """
    logger.info("Starting iterative build check")
    
    for iteration in range(max_iterations):
        logger.info(f"Build iteration {iteration + 1}/{max_iterations}")
        
        # Run build check
        build_result = await run_build_check()
        
        if build_result["build_success"]:
            logger.info("Build successful!")
            return True
            
        # Parse build errors
        errors = await parse_build_errors(build_result["build_errors"])
        
        if not errors:
            logger.warning("No parseable errors found in build output")
            return False
            
        # Try to fix each error
        for error in errors:
            try:
                # Read current file content
                file_path = f"my-react-app/src/{error['file']}"
                async with aiofiles.open(file_path, 'r') as f:
                    current_content = await f.read()
                
                # Get fixed content
                fixed_content = await fix_agent(error, current_content, blueprint, prop_contracts, config, session)
                
                # Write fixed content
                await write_file(file_path, fixed_content)
                logger.info(f"Applied fix for {error['file']}")
                
            except Exception as e:
                logger.error(f"Failed to fix error in {error['file']}: {str(e)}")
                continue
    
    logger.warning(f"Reached maximum iterations ({max_iterations})")
    return False

# -------------------------
# Main Entrypoint
# -------------------------

if __name__ == '__main__':
    import argparse

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Execute workflow for project generation')
    parser.add_argument('project_description', type=str, help='Description of the project to generate')
    
    args = parser.parse_args()
    
    asyncio.run(execute_workflow(args.project_description))



