import asyncio
import aiohttp
import logging
import os
import json
from langfuse.decorators import langfuse_context, observe
from dotenv import load_dotenv
from config import build_api_request, extract_api_response
from file import write_file, parse_json_response
from logging_config import setup_logging
from type import ComponentDict, SplitComponentDict, validate_component_dict, validate_split_output

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
    Makes an API call to the given endpoint with the given headers and body.
    """
    config = build_api_request(prompt, api_config)
    
    langfuse_context.update_current_observation(
      name=api_config["fx"],
      input=prompt,
      model=api_config["model"],
      metadata={
          "provider": api_config["provider"]
      }
    )
    try:
        async with session.post(config["api_endpoint"], 
                              headers=config["headers"], 
                              data=config["body"]) as response:
            response_text = await response.text()
                
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
        error_msg = f"Unexpected error during API call: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg) from e


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

    ```
    {input['description']}
    ```

    The format should be json structured as follows, with absolutely no other text or characters.

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

    Your output MUST be valid json.Output the plan and first file details in the following JSON format:
    {{
        "description": "detailed plan here",
        "name": "name of root file of the project",
        "path": "typical path to root file of the project",
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


async def development_agent(input: dict, config: dict, session: aiohttp.ClientSession) -> bool:
    """
    Development Agent:
    Produces code files based on the provided description and name.

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
    Write the code for the following page or component:
    
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
    Return the result in the following format, with absolutely no other text or characters:

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

    Output ONLY one of these three words: "detail", "split", or "write"
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
    
    try:
        async with aiohttp.ClientSession() as session:
            # Initial planning
            plan = await planning_agent(description, gemini_config, session)

            # Initial splitting
            components = await splitting_agent(plan, gemini_config, session)
            
            # Prepare initial config and develop main component
            components["description"] = plan["description"]
            config = prepare_component_config(components)
            config["path"] = 'tmp/' + components["name"]
    
            asyncio.create_task(development_agent(config, gemini_config, session))
    
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
                            tg.create_task(development_agent(config, gemini_config))
                            work_queue.extend(split_components["parts"])
                                
                        elif route == "split":
                            # Need to split - send to splitting
                            split_components = await splitting_agent(component, gemini_config, session)
                            
                            split_components["description"] = component["description"]
                            config = prepare_component_config(split_components)
                            tg.create_task(development_agent(config, gemini_config, session))
                            work_queue.extend(split_components["parts"])
                        else:
                            # Ready to write - send to development
                            config = prepare_component_config(component)
                            tg.create_task(development_agent(config, gemini_config, session))
    
        logger.info("Workflow: Execution completed successfully")
        
    except Exception as e:
        logger.error("Workflow: Execution failed")
        logger.debug(f"Detailed error: {str(e)}")
        raise

# -------------------------
# Main Entrypoint
# -------------------------

if __name__ == '__main__':
    # Example project specification
    project_description = "A chat site without any authentication: just a chat interface. text input, see other people's messages, etc."
    
    asyncio.run(execute_workflow(project_description))
