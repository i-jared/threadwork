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

        logger.debug(f"Planning Agent: Raw response: {api_output}")
        
        logger.debug(f"Planning Agent: Extracted output: {api_output}")
        
        try:
            if not api_output.get("content"):
                raise ValueError("No content in API output")
                
            result = parse_json_response(api_output["content"])
            logger.debug(f"Planning Agent: Parsed result: {result}")
            
            validated_result = validate_component_dict(result, "Planning Agent")

            
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
    
    # Get component descriptions if they exist
    component_descriptions = []
    if "parts" in input:
        for part in input["parts"]:
            component_descriptions.append(f"{part['path']}: {part['summary']}")

    # Get prop contract if it exists
    contract_info = ""
    if "prop_contracts" in project_config:
        contract = next(
            (c for c in project_config["prop_contracts"]["contracts"] 
             if c["path"] == input["path"]),
            None
        )
        if contract:
            contract_info = f"""
            Props Interface:
            {contract['propsInterface']}
            
            Required Props: {', '.join(contract['required'])}
            Optional Props: {', '.join(contract['optional'])}
            """

    prompt = f"""
    Write the code for the following page or component, keeping in mind the following project details:
    page/component name, and use tailwind css for any styling, MPORTANT: Do not wrap the code in any triple backticks or Markdown syntax:
    {input["name"]}
    project details:
    {project_config["summary"]}

    component details:
    ```
    {input["description"]}
    ```

    {contract_info}

    {
    'Available components and their purposes:' + ''.join(component_descriptions) if component_descriptions else 
    ''
    }

    Output just the code, nothing else.
    """

    try:
        config["fx"] = "development"
        api_output = await make_api_call(prompt, config, session)
        
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
            print("PRINTING PACKAGE -- ", package)
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
        logger.info("Starting create_react_app process...")
        
        # Clean up existing directory if it exists
        if os.path.exists("my-react-app"):
            logger.info("Found existing my-react-app directory, attempting to remove...")
            try:
                shutil.rmtree("my-react-app")
                logger.info("✅ Cleaned up existing my-react-app directory")
            except Exception as e:
                logger.error(f"❌ Failed to remove existing directory: {str(e)}")
                raise
        
        # Create the React app using bun
        logger.info("Creating new Vite React app with bun...")
        try:
            result = subprocess.run(
                "bun create vite my-react-app --template react-ts",
                shell=True,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info("✅ React app created successfully")
            logger.debug(f"Create command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to create React app: {str(e)}")
            logger.error(f"Command output: {e.stdout}")
            logger.error(f"Error output: {e.stderr}")
            raise
        
        # Install dependencies
        app_dir = Path("my-react-app")
        logger.info(f"Installing base dependencies in {app_dir}...")
        try:
            result = subprocess.run(
                "bun install",
                shell=True,
                check=True,
                cwd=app_dir,
                capture_output=True,
                text=True
            )
            logger.info("✅ Base dependencies installed")
            logger.debug(f"Install command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to install base dependencies: {str(e)}")
            logger.error(f"Command output: {e.stdout}")
            logger.error(f"Error output: {e.stderr}")
            raise

        # Install react-router-dom
        logger.info("Installing react-router-dom and related packages...")
        try:
            result = subprocess.run(
                "bun add react-router-dom react-icons lucide-react",
                shell=True,
                check=True,
                cwd=app_dir,
                capture_output=True,
                text=True
            )
            logger.info("✅ react-router-dom and related packages installed")
            logger.debug(f"Install command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to install react-router-dom: {str(e)}")
            logger.error(f"Command output: {e.stdout}")
            logger.error(f"Error output: {e.stderr}")
            raise

        # Install Tailwind CSS and its dependencies
        logger.info("Installing Tailwind CSS and dependencies...")
        try:
            result = subprocess.run(
                "bun add -d tailwindcss@3 postcss autoprefixer",
                shell=True,
                check=True,
                cwd=app_dir,
                capture_output=True,
                text=True
            )
            logger.info("✅ Tailwind CSS and dependencies installed")
            logger.debug(f"Install command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to install Tailwind: {str(e)}")
            logger.error(f"Command output: {e.stdout}")
            logger.error(f"Error output: {e.stderr}")
            raise
        
        # Initialize Tailwind CSS configuration
        logger.info("Initializing Tailwind configuration...")
        try:
            result = subprocess.run(
                "bunx tailwindcss@3 init -p",
                shell=True,
                check=True,
                cwd=app_dir,
                capture_output=True,
                text=True
            )
            logger.info("✅ Tailwind configuration initialized")
            logger.debug(f"Init command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to initialize Tailwind: {str(e)}")
            logger.error(f"Command output: {e.stdout}")
            logger.error(f"Error output: {e.stderr}")
            raise
        
        logger.info("✅ Tailwind CSS configured successfully")

        # Fix main.tsx App import
        # logger.info("Fixing App import in main.tsx...")
        # try:
        #     main_path = app_dir / "src" / "main.tsx"
        #     with open(main_path, "r") as f:
        #         content = f.read()
            
            # Replace the default import with named import
            # fixed_content = content.replace(
            #     "import App from './App.tsx'",
            #     "import { App } from './App.tsx'"
            # )
            
            # with open(main_path, "w") as f:
            #     f.write(fixed_content)
            # logger.info("✅ Fixed App import in main.tsx")
            
        # except Exception as e:
        #     logger.error(f"❌ Failed to fix App import: {str(e)}")
        #     raise

        return True

    except subprocess.CalledProcessError as e:
        logger.error("❌ Error creating React app")
        logger.error(f"Command failed with exit code {e.returncode}")
        return True  # Return something to make the await valid

    except Exception as e:
        logger.error("❌ An error occurred during deployment")
        logger.error(f"Error details logged")
        # Log the full error message
        logger.debug(f"DEBUG: {str(e)}")


def normalize_import(path: str, all_files: set[str]) -> str:
    """
    If path does not have an extension, try .tsx, .ts, or .css.
    If it does, return it as-is.
    """
    # Already has an extension
    if any(path.endswith(ext) for ext in [".tsx", ".ts"]):
        return path

    # Try adding extensions in order of likelihood
    for ext in [".tsx", ".ts", ".css"]:
        candidate = path + ext
        if candidate in all_files:
            return candidate

    # If none match, return the path as-is
    return path

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
    # Define components that don't need Props interfaces
    NO_PROPS_COMPONENTS = {
        "App.tsx",  # Main App component typically doesn't need props
        "index.tsx",  # Entry point file
        "layout.tsx",  # Layout components often don't need props

    }
    
    logger.info("Blueprint Agent: Starting blueprint creation")
    
    prompt = f"""Create a complete blueprint of all files needed for this React TypeScript project.
    For each file, provide:
    - Exact file path (relative to src/)
    - Short summary of the file's purpose (1-2 sentences)
    - List of exports (components, functions, types, etc.)
    - List of imports (both npm packages and local files)

    CRITICAL REQUIREMENTS:
    1. For EVERY React component (except App.tsx and layout files), you MUST include both the component name AND its Props interface in exports
       Example: for a component named "HabitList", include both "HabitList" and "HabitListProps" in exports
    2. When listing local imports, always include the full file extension:
       - Use .tsx for React TypeScript components
       - Use .ts for TypeScript files
       - Use .css for stylesheets (but DO NOT create layout.css or any separate style files - use Tailwind classes instead)
    3. All styling should be done with Tailwind classes directly in the components - DO NOT create separate CSS files.

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
                "exports": ["list", "of", "exports", "including", "ComponentProps"],
                "imports": {{
                    "npm": ["list", "of", "npm", "packages"],
                    "local": ["list", "of", "local", "imports", "with", "extensions"]
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
        
        # Log the raw response for debugging
        
        result = parse_json_response(api_output["content"])
        
        # Validate Props interfaces are included for components
        for file in result["files"]:
            # Get just the filename without the path
            filename = file["path"].split("/")[-1]
            
            if file["path"].endswith(".tsx") and filename not in NO_PROPS_COMPONENTS:
                component_name = filename.replace(".tsx", "")
                props_interface = f"{component_name}Props"
                
                if props_interface not in file["exports"]:
                    logger.warning(f"Adding missing Props interface {props_interface} to {file['path']}")
                    file["exports"].append(props_interface)
                else:
                    logger.info(f"✓ Found Props interface {props_interface} in {file['path']}")
            else:
                if filename in NO_PROPS_COMPONENTS:
                    logger.info(f"ℹ Skipping Props interface for {filename} (in exception list)")
                
        
        # Validate that all local imports reference existing files
        all_files = {file["path"] for file in result["files"]}
        
        # Track if we've found any missing imports
        has_missing_imports = False
        
        for file in result["files"]:
            for local_import in file["imports"]["local"]:
                normalized = normalize_import(local_import, all_files)
                if normalized not in all_files:
                    if not has_missing_imports:
                        # Print file list only once when first missing import is found
                        logger.warning("Available files in blueprint:")
                        for available_file in sorted(all_files):
                            logger.warning(f"  - {available_file}")
                        has_missing_imports = True
                            
                    logger.warning(f"Blueprint Agent: Local import {local_import} not found in file list")
                    result["validation"]["allLocalImportsExist"] = False
                else:
                    # Replace the old value with the normalized path
                    local_import_index = file["imports"]["local"].index(local_import)
                    file["imports"]["local"][local_import_index] = normalized

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
                logger.warning(f"Contract for unknown component {contract['path']}")
            elif f"{contract['componentName']}Props" not in blueprint_components[contract["path"]]:
                logger.warning(f"Missing Props interface in blueprint for {contract['componentName']}")
        
        return result

    except Exception as e:
        logger.error("Prop Contract Agent: Error encountered")
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
    logger.info(f"🔥 Generating file: {file_info['path']}")
    # Special handling for index.css
    if file_info['path'].endswith('index.css'):
        logger.info(f"🔥 Matched index.css file!")
        required_body_css = """
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root {
  height: 100%;
  min-height: 100vh;
  margin: 0;
  padding: 0;
  width: 100%;
}

body {
  margin: 0;
  padding: 0;
  min-width: 100vw;
  width: 100%;
}
"""
        logger.info("🔥 Generating index.css with required body CSS")
        logger.debug(f"Required CSS template:\n{required_body_css}")
        
        prompt = f"""Generate the CSS code for the index.css file. 
        ALWAYS include this exact CSS at the start of the file (do not modify it):
        {required_body_css}

        Then add any additional styles needed for:
        {file_info['summary']}
        """
        
        try:
            config["fx"] = "file_generation"
            api_output = await make_api_call(prompt, config, session)
            generated_css = api_output["content"]
            
            # Verify the required CSS is included
            if required_body_css.strip() not in generated_css.strip():
                logger.warning("🔥 Required CSS not found in generated output, enforcing it")
                generated_css = required_body_css + "\n" + generated_css
            
            logger.info("🔥 Successfully generated index.css with required body CSS")
            logger.debug(f"Final CSS output:\n{generated_css}")
            
            return generated_css
            
        except Exception as e:
            logger.error(f"🔥 Failed to generate index.css: {str(e)}")
            raise
    else:
        logger.info(f"🔥 Not index.css, generating regular file: {file_info['path']}")
        # Find matching prop contract if it exists
        contract = None
        if "prop_contracts" in config:
            for c in config["prop_contracts"]["contracts"]:
                if c["path"] == file_info["path"]:
                    contract = c
                    break
        
        contract_info = ""
        if contract:
            contract_info = f"""
            PROPS INTERFACE:
            {contract['propsInterface']}
            
            Required Props: {', '.join(contract['required'])}
            Optional Props: {', '.join(contract['optional'])}
            """
        
        prompt = f"""Generate optimized React TypeScript code for this file. Follow these requirements:

        File Path: {file_info['path']}
        Summary: {file_info['summary']}
        Required Exports: {', '.join(file_info['exports'])}
        
        Allowed Imports:
        NPM Packages: {', '.join(file_info['imports']['npm'])}
        Local Files: {', '.join(file_info['imports']['local'])}

        {contract_info}

        CRITICAL REQUIREMENTS:
        1. Use ONLY the specified imports
        2. Implement ALL specified exports
        3. Use Tailwind CSS for styling
        4. Follow React + TypeScript best practices
        5. Include JSDoc comments for components and functions
        6. Implement props interface EXACTLY as specified
        7. Use all required props in the component implementation
        8. ALWAYS use destructured imports for local files, e.g.:
           import {{ ComponentName }} from './ComponentName'
           NOT: import ComponentName from './ComponentName'

        PERFORMANCE OPTIMIZATION REQUIREMENTS WHEN WRITING .tsx OR .ts FILES:
        1. Memoize components that receive props using React.memo when appropriate
        2. Move object/array literals outside component definitions or use useMemo
        3. Use useCallback for event handlers and function props
        4. Avoid inline styles - use Tailwind classes instead
        5. If using Context, split into smaller contexts to prevent unnecessary rerenders
        6. Place expensive computations inside useMemo hooks
        7. Define callback functions with useCallback when passed as props
        8. Extract complex child components to prevent parent rerenders from affecting them

        Example optimization patterns to follow:
        ```typescript
        // Stable object definitions outside component
        const defaultStyles = (curly bracket here) padding: '1rem' (curly bracket here);


        // Memoized component with proper prop types
        const MyComponent = React.memo(((bracket here)data, onAction (bracket here): MyComponentProps) => (curly bracket here)
          // Memoized expensive computations
          const processedData = useMemo(() => expensiveProcess(data), [data]);
          
          // Stable callback functions
          const handleClick = useCallback(() => (curly bracket here)
            onAction(processedData);
          (curly bracket here), [onAction, processedData]);

          return (
            <div className="p-4 bg-white rounded-lg shadow">
              (curly bracket here) /* Use Tailwind styles */(curly bracket here)
            </div>
          );
        (curly bracket here));
        ```

        Return ONLY the complete file code, no explanations or markdown.
        """

    try:
        config["fx"] = "file_generation"
        api_output = await make_api_call(prompt, config, session)
        code = api_output["content"]
        
        # Extract code from possible markdown code block
        if code.startswith("```"):
            lines = code.split("\n")
            # Remove first line (```language) and last line (```)
            code = "\n".join(lines[1:-1])

        # Add package installation logic
        import_pattern = re.compile(
            r"^import\s+(?:{[^}]*}|\w+)\s+from\s+'(?!(?:\.\/|\.\.\/|react(?=['/]|$)))([^']+)';$",
            re.MULTILINE
        )

        # Find all matching import package names
        imports = import_pattern.findall(code)
        logger.info(f"Generate File Code: Found imports: {imports}")

        def get_install_package(package: str) -> str:
            """
            Returns the base package name for installation.
            For unscoped packages (like 'react-icons/fa'), returns only the first segment (e.g., 'react-icons').
            For scoped packages (like '@scope/package/subpath'), returns the first two segments (e.g., '@scope/package').
            """
            if package.startswith('@'):
                parts = package.split('/')
                return '/'.join(parts[:2])
            else:
                return package.split('/')[0]

        # Install required packages
        for package in imports:
            install_package = get_install_package(package)
            logger.info(f"Installing package: {install_package} (from import: {package})")
            try:
                subprocess.run(f"bun add {install_package}", shell=True, check=True, cwd="my-react-app")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install package {install_package}: {str(e)}")
                # Continue with other packages even if one fails
                continue

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

async def parse_build_errors(error_output: str | list) -> list[dict]:
    """
    Parses build error output into structured format.
    Returns list of error objects with file, message, and type.
    
    Args:
        error_output: Either a string of error messages or a list of error messages
        
    Returns:
        list[dict]: List of parsed error objects
    """
    errors = []
    
    # Common TypeScript error patterns
    ts_error_pattern = r"(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+) - error TS(?P<code>\d+): (?P<message>.+)"
    module_error_pattern = r"Cannot find module '(?P<module>[^']+)'"
    prop_error_pattern = r"Property '(?P<prop>[^']+)' does not exist on type"
    
    # Handle both string and list inputs
    lines = error_output.split('\n') if isinstance(error_output, str) else error_output
    
    for line in lines:
        error = {}
        
        # Skip empty lines or non-string items
        if not line or not isinstance(line, str):
            continue
            
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
    
    # Get relevant file info from blueprint
    file_info = next((f for f in blueprint["files"] if f["path"].endswith(error["file"])), None)
    if not file_info:
        raise ValueError(f"Could not find file info for {error['file']} in blueprint")
    
    # Get prop contract if it exists
    contract = None
    if "prop_contracts" in config:
        for c in config["prop_contracts"]["contracts"]:
            if c["path"] == file_info["path"]:
                contract = c
                break
    
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
    
    for iteration in range(max_iterations):
        
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
# Workflow Execution
# -------------------------

@observe()
async def execute_workflow(description: str):
    """
    Executes the workflow in the following pattern:
    1. Creates a new Vite React TypeScript app (with Tailwind).
    2. Generates a blueprint for all files.
    3. Creates prop contracts for each component.
    4. Generates code for each file using the blueprint and prop contracts.
    5. Iteratively checks for build errors and attempts to fix them.
    6. Starts the Vite dev server.
    """
    try:
        success = await create_react_app()
        if success:
            logger.info("✅ Vite React app setup completed")
    except Exception as e:
        logger.error(f"Workflow: Error creating React app: {str(e)}")
        raise

    # Setup directories
    os.makedirs('my-react-app/src/components', exist_ok=True)
    os.makedirs('my-react-app/src/pages', exist_ok=True)
    if os.path.exists('my-react-app/src/App.tsx'):
        os.remove('my-react-app/src/App.tsx')

    # API configurations
    default_config = {
        "provider": "gemini",
        "api_key": os.getenv('GEMINI_API_KEY'),
        "max_tokens": 100000,
        "model": "gemini-2.0-flash"
    }

    project_config = {
        "user_description": description,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # 1) Generate a complete blueprint
            blueprint = await blueprint_agent(description, default_config, session)

            # 2) Generate prop contracts and store in project_config
            prop_contracts = await prop_contract_agent(blueprint, default_config, session)
            project_config["prop_contracts"] = prop_contracts
            
            # 3) Generate initial files from the blueprint
            for file_info in blueprint["files"]:
                try:
                    code = await generate_file_code(file_info, blueprint, prop_contracts, default_config, session)
                    await write_file(f"my-react-app/src/{file_info['path']}", code)
                except Exception as e:
                    logger.error(f"Failed to generate {file_info['path']}: {str(e)}")
                    continue
            
            # 4) Iteratively build, parse errors, and try to fix them
            build_success = await iterative_build_check(blueprint, prop_contracts, default_config, session)
            if build_success:
                logger.info("Successfully completed all build checks")
            else:
                logger.warning("Some build errors could not be fixed automatically")

            # 5) Regenerate or finalize each file, ensuring we install packages for new imports
            for file_info in blueprint["files"]:
                try:
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
        # if file index css exists and has a tag called body, replace it with our specific body rule
        index_css_path = Path("my-react-app/src/index.css")
        if index_css_path.exists():
            with open(index_css_path, 'r') as f:
                content = f.read()
            
            # Use regex to find and replace the body rule
            body_rule = re.compile(r'body\s*{[^}]*}')
            new_body_rule = """body {
  margin: 0;
  padding: 0;
  min-width: 100vw;
  width: 100%;
}"""
            
            if body_rule.search(content):
                content = body_rule.sub(new_body_rule, content)
                with open(index_css_path, 'w') as f:
                    f.write(content)
        
        logger.info("Workflow: Execution completed successfully")

        # Create final zip archive
        try:
            shutil.make_archive("project_files", 'zip', 'my-react-app')
            logger.info("✅ Successfully created project_files.zip")
        except Exception as e:
            logger.error(f"Error creating zip archive: {str(e)}")

        # Start the Vite dev server
        # logger.info("Starting Vite dev server...")
        # try:
        #     subprocess.Popen(
        #         # Add host flag to allow external access
        #         "bun run dev --host 0.0.0.0 --port 5174",
        #         shell=True,
        #         cwd="my-react-app",
        #         stdout=subprocess.PIPE,
        #         stderr=subprocess.PIPE
        #     )
        #     logger.info("✅ Vite dev server started on http://localhost:5174")
        # except Exception as e:
        #     logger.error(f"Failed to start Vite dev server: {str(e)}")
        #     raise

    except Exception as e:
        logger.error("Workflow: Execution failed")
        logger.debug(f"Detailed error: {str(e)}")
        raise


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



