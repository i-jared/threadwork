import asyncio
import aiohttp
import logging
import os
import json
from langfuse import Langfuse
from dotenv import load_dotenv
from src.config import build_api_request, extract_api_response
from src.file import write_file
from src.logging_config import setup_logging
from src.type import ComponentDict, SplitComponentDict, validate_component_dict, validate_split_output

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

async def make_api_call(config: dict) -> dict:
    """
    Makes an API call to the given endpoint with the given headers and body.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(config["api_endpoint"], headers=config["headers"], data=config["body"]) as response:
            if response.status != 200:
                raise Exception("API request failed")
            return await response.json()


async def splitting_agent(input: dict, config: dict, span) -> SplitComponentDict:
    """
    Splitting Agent:
    Splits the component/page description into smaller chunks.

    Input format: ComponentDict
    Output format: SplitComponentDict
    """
    # Validate input
    input = validate_component_dict(input, "Splitting Agent (input)")
    
    logger.info("Splitting Agent: Starting splitting process.")
    prompt = f"""Split the following {input['type']} description into smaller chunks, preserving the original name and type.
    Each part should be a single component or a single part of a component.
    
    ```
    {input['description']}
    ```
    
    The format should be as follows, with absolutely no other text or characters.

    '{{'
        "name": "{input['name']}",
        "type": "{input['type']}",
        "parts": [
            '{{'
                "name": "generated name of the described part",
                "description": "generated description of the part",
                "type": "type of the part, either 'component' or 'page'"
            '}}'
        ]
    '}}'
    """
    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config)
        logger.info("Splitting Agent: Successfully split project")
        api_output = extract_api_response(response, config["provider"])
        
        # Add token tracking
        span.update_usage(
            input_tokens=api_output["usage"]["input_tokens"],
            output_tokens=api_output["usage"]["output_tokens"],
            total_tokens=api_output["usage"]["total_tokens"]
        )

        result = json.loads(api_output["content"])
        return validate_split_output(result, "Splitting Agent")

    except Exception as e:
        logger.error("Splitting Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise


async def planning_agent(input: str, config: dict, span) -> ComponentDict:
    """
    Planning Agent:
    Creates a structured project plan from the idea.
    """
    # Validate input
    
    logger.info("Planning Agent: Starting planning process.")
    prompt = f"""Create a detailed description for the following app. Focus on the UI and UX.
    
    ```
    {input}
    ```

    Output the plan and first file details in the following JSON format:
    {
        "description": "detailed plan here",
        "name": "name of first file to create",
        "path": "path to first file"
    }
    """
    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config)
        logger.info(f"Planning Agent: Successfully generated plan")
        api_output = extract_api_response(response, config["provider"])
        
        # Add token tracking
        span.update_usage(
            input_tokens=api_output["usage"]["input_tokens"],
            output_tokens=api_output["usage"]["output_tokens"],
            total_tokens=api_output["usage"]["total_tokens"]
        )
        
        result = json.loads(api_output["content"])
        return validate_component_dict(result, "Planning Agent")
        
    except Exception as e:
        logger.error("Planning Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise


async def development_agent(input: dict, config: dict, span) -> bool:
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

    prompt = f"""
    Write the code for the following page or component:
    
    ```
    {input["description"]}
    ```

    Output just the code, nothing else.
    """


    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config)
        logger.info(f"Development Agent: Successfully generated code")
        api_output = extract_api_response(response, config["provider"])
        
        # Add token tracking
        span.update_usage(
            input_tokens=api_output["usage"]["input_tokens"],
            output_tokens=api_output["usage"]["output_tokens"],
            total_tokens=api_output["usage"]["total_tokens"]
        )
        
        code = api_output["content"]


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

async def expounding_agent(input: dict, config: dict, span) -> ComponentDict:
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
    Preserve the original name and type.
    Return the result in the following format, with absolutely no other text or characters:

    '{{'
        "name": "{input['name']}",
        "type": "{input['type']}",
        "description": "expanded detailed description"
    '}}'

    Input description:
    ```
    {input['description']}
    ```

    Output just the JSON object, nothing else.
    """

    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config)

        logger.debug("Expounding Agent: Generated expanded spec")

        api_output = extract_api_response(response, config["provider"])
        
        # Add token tracking
        span.update_usage(
            input_tokens=api_output["usage"]["input_tokens"],
            output_tokens=api_output["usage"]["output_tokens"],
            total_tokens=api_output["usage"]["total_tokens"]
        )
        
        result = json.loads(api_output["content"])
        return validate_component_dict(result, "Expounding Agent")

    except Exception as e:
        logger.error("Expounding Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def routing_agent(input: str, config: dict, span) -> str:
    """
    Routing Agent:
    Analyzes input and determines whether it needs more detail, should be split up,
    or is ready to be written to a file.
    
    Returns one of: "detail", "split", "write"
    """
    logger.info("Routing Agent: Starting routing process.")
    prompt = f"""Analyze the following app segment description and determine if it:
    1. Needs more detail before it can be processed (output "detail")
    2. Contains multiple components and should be split up (output "split")
    3. Has enough detail and is focused enough to be written to one file (output "write")

    ```
    {input}
    ```

    Output ONLY one of these three words: "detail", "split", or "write"
    """

    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config)
        logger.info("Routing Agent: Successfully determined route")
        api_output = extract_api_response(response, config["provider"])
        
        # Add token tracking
        span.update_usage(
            input_tokens=api_output["usage"]["input_tokens"],
            output_tokens=api_output["usage"]["output_tokens"],
            total_tokens=api_output["usage"]["total_tokens"]
        )
        
        route = api_output["content"].strip().lower()
        
        if route not in ["detail", "split", "write"]:
            logger.error(f"Routing Agent: Invalid route '{route}'")
            raise ValueError(f"Invalid route: {route}")
            
        return route

    except Exception as e:
        logger.error("Routing Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

# -------------------------
# Workflow Execution
# -------------------------

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
    langfuse = Langfuse(
        public_key=os.getenv('LANGFUSE_PUBLIC_KEY'),
        secret_key=os.getenv('LANGFUSE_SECRET_KEY'),
        host=os.getenv('LANGFUSE_HOST')
    )
    
    trace = langfuse.trace(name="project_construction")
    claude_config = {
        "provider": "anthropic",
        "api_key": os.getenv('ANTHROPIC_API_KEY'),
        "max_tokens": 10240,
        "model": "claude-3-5-sonnet-20241022"
    }

    gemini_config = {
        "provider": "gemini",
        "api_key": os.getenv('GEMINI_API_KEY'),
        "max_tokens": 100000,
        "model": "gemini-2.0-flash"
    }
    
    try:
        # Initial planning
        with trace.span(name="planning") as planning_span:
            plan = await planning_agent(description, gemini_config, planning_span)
            planning_span.set_metadata("plan", plan)

        # Initial splitting
        with trace.span(name="initial_splitting") as splitting_span:
            components = await splitting_agent(plan, gemini_config, splitting_span)
            splitting_span.set_metadata("components", components)

        # Process queue for components that need work
        work_queue = components["parts"]
        
        while work_queue:
            current_batch = work_queue.copy()
            work_queue.clear()
            
            # Process all current components concurrently
            async with asyncio.TaskGroup() as tg:
                for component in current_batch:
                    # First try to develop the component
                    with trace.span(name=f"development_{component['name']}") as dev_span:
                        dev_task = tg.create_task(
                            development_agent(component, claude_config, dev_span)
                        )
                    
                    # Determine next steps
                    with trace.span(name=f"routing_{component['name']}") as routing_span:
                        route = await routing_agent(component["description"], gemini_config, routing_span)
                        routing_span.set_metadata("route", route)
                        
                        if route == "detail":
                            # Need more detail - send to expounding then splitting
                            with trace.span(name=f"expounding_{component['name']}") as exp_span:
                                expanded = await expounding_agent(component, gemini_config, exp_span)
                                
                            with trace.span(name=f"splitting_after_expound_{component['name']}") as split_span:
                                split_components = await splitting_agent(expanded, gemini_config, split_span)
                                work_queue.extend(split_components["parts"])
                                
                        elif route == "split":
                            # Need to split - send to splitting
                            with trace.span(name=f"splitting_{component['name']}") as split_span:
                                split_components = await splitting_agent(component, gemini_config, split_span)
                                work_queue.extend(split_components["parts"])

        trace.end(status="success")
        logger.info("Workflow: Execution completed successfully")
        
    except Exception as e:
        trace.end(status="error", statusMessage=str(e))
        logger.error("Workflow: Execution failed")
        logger.debug(f"Detailed error: {str(e)}")
        raise

# -------------------------
# Main Entrypoint
# -------------------------

if __name__ == '__main__':
    # Example project specification
    project_spec = {"theme": "chatbot"}
    
    asyncio.run(execute_workflow(project_spec))
