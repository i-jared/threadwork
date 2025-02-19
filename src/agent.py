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
    max_retries = 5
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
    Give each part a short summary (less than 20 words) that clearly states its purpose.

    IMPORTANT SPLITTING GUIDELINES:
    DO split when you see:
    - Completely separate pages (e.g., a login page and a dashboard page)
    - Major reusable components (e.g., a complex data table component that appears in multiple places)

    DO NOT split:
    - Simple UI elements that belong together (e.g., don't separate a form's input fields into individual components)
    - Related elements that form a cohesive unit (e.g., keep a card's header, body, and footer together)

    Example of GOOD splitting:
    Input: "A web app with a login page and a dashboard. The dashboard has a complex data table showing user analytics and a sidebar with navigation links."
    Split into: 
    - login.tsx (page): Complete login page with form inputs and submit button
    - dashboard.tsx (page): Main dashboard layout with sidebar and content area
    - DataTable.tsx (component): Reusable analytics table with sorting and filtering

    Example of BAD splitting (too granular):
    Input: "A login form with username field, password field, and submit button"
    DON'T split into:
    - UsernameInput.tsx
    - PasswordInput.tsx
    - SubmitButton.tsx
    (These should stay together in one login form component)

    ```
    {input['description']}
    ```

    The format MUST be EXACTLY as follows, with NO additional text, whitespace, or characters whatsoever. Any deviation will cause an error:

    \'{{'
        "name": "{input['name']}",
        "type": "{input['type']}",
        "parts": [
            \'{{'
                "name": "generated name of the described part (eg. login.tsx, big_button.py, etc.)",
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
        config["path"] = 'tmp/pages/' + components["name"] if components["type"] == "page" else 'tmp/components/' + components["name"]
    else:
        config["path"] = components["path"]

    # Only add components key if parts exist
    if "parts" in components:
        # Set paths for components that don't have them
        for component in components["parts"]:
            if "path" not in component:
                component["path"] = 'tmp/pages/' + component["name"] if component["type"] == "page" else 'tmp/components/' + component["name"]
        
        config["parts"] = [{"path": component["path"], "summary": component["summary"]} for component in components["parts"]]

    return config

# -------------------------
# Add Installs
# -------------------------
async def create_react_app():
    """Creates a new Vite React-TypeScript project with initial setup"""
    try:
        # Create test directory if it doesn't exist
        test_dir = Path("test")
        test_dir.mkdir(exist_ok=True)
        
        # Create the React app using bun
        subprocess.run(
            "bun create vite my-react-app --template react-ts",
            shell=True,
            check=True,
            cwd=test_dir
        )
        logger.info("✅ React app created successfully")
        
        # Install dependencies
        app_dir = test_dir / "my-react-app"
        subprocess.run(
            "bun install",
            shell=True,
            check=True,
            cwd=app_dir
        )
        
        # Install Tailwind CSS and its dependencies
        subprocess.run(
            "bun add -d tailwindcss postcss autoprefixer",
            shell=True,
            check=True,
            cwd=app_dir
        )
        logger.info("✅ Tailwind CSS and dependencies installed")
        
        # Initialize Tailwind CSS configuration
        subprocess.run(
            "bunx tailwindcss init -p",
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
        
        # Copy files from tmp/ to test/src/ if tmp exists
        tmp_dir = Path("tmp")
        if tmp_dir.exists():
            dest_dir = test_dir / "my-react-app" / "src"
            
            # Create src directory if it doesn't exist
            dest_dir.mkdir(exist_ok=True)
            
            # Copy all contents from tmp to test/src
            for item in tmp_dir.glob("*"):
                if item.is_file():
                    shutil.copy2(item, dest_dir)
                elif item.is_dir():
                    shutil.copytree(item, dest_dir / item.name, dirs_exist_ok=True)
            
            # Delete tmp directory
            shutil.rmtree(tmp_dir)
            print("✅ Files copied and tmp directory cleaned up")
        else:
            print("ℹ️ No tmp directory found to copy files from")
            
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
    1. Planning
    2. Initial splitting
    3. Loop of:
       - Development (for each split part)
       - Routing
       - Expounding (if needed) -> Splitting
       - Splitting (if needed)
    """
    
    # Create tmp directories
    os.makedirs('tmp/pages', exist_ok=True)
    os.makedirs('tmp/components', exist_ok=True)
    
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
            # Initial planning
            plan = await planning_agent(description, default_config, session)
            project_config["summary"] = plan["summary"]

            # Initial splitting
            components = await splitting_agent(plan, gemini_config, session)
            
            # Prepare initial config and develop main component
            components["description"] = plan["description"]
            config = prepare_component_config(components)
            config["path"] = 'tmp/' + components["name"]
    
            asyncio.create_task(development_agent(config, project_config, claude_config, session))
    
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
                            tg.create_task(development_agent(config, project_config, claude_config, session))
                            work_queue.extend(split_components["parts"])
                                
                        elif route == "split":
                            # Need to split - send to splitting
                            split_components = await splitting_agent(component, gemini_config, session)
                            
                            split_components["description"] = component["description"]
                            config = prepare_component_config(split_components)
                            tg.create_task(development_agent(config, project_config, claude_config, session))
                            work_queue.extend(split_components["parts"])
                        else:
                            # Ready to write - send to development
                            config = prepare_component_config(component)
                            tg.create_task(development_agent(config, project_config, claude_config, session))
    
        logger.info("Workflow: Execution completed successfully")
        # Zip the test folder
        output_filename = "project_files"
        directory = 'test'

        try:
             # Create Vite React-TypeScript project
            success = await create_react_app()
            if success:
                logger.info("✅ Vite React app setup completed")

            # Zip the test
            shutil.make_archive(output_filename, 'zip', directory)
            logger.info(f"Workflow: Successfully zipped tmp folder to {output_filename}.zip")
            
            
        except Exception as e:
            logger.error(f"Workflow: Error zipping tmp folder: {str(e)}")
        
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


