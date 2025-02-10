import asyncio
import aiohttp
import logging
import os
import json
from langfuse import Langfuse
from dotenv import load_dotenv
from config import build_api_request, extract_api_response
from file import write_file
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

async def make_api_call(config: dict, span) -> dict:
    """
    Makes an API call to the given endpoint with the given headers and body.
    """
    async with aiohttp.ClientSession() as session:
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
                
                # Update the span with generation details
                span.update(
                    name=f"{config['provider']}-generation",
                    input=json.loads(config["body"]),  # Parse the JSON string back to dict
                    output=result,
                    metadata={
                        "endpoint": config["api_endpoint"],
                        "status": response.status,
                        "model": config["model"],
                        "provider": config["provider"]
                    }
                )
                
                logger.debug(f"API Response: {result}")
                return result
                
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

    <start description>
    {input['description']}
    <end description>

    The format should be as follows, with absolutely no other text or characters.

    \'{{'
        "name": "{input['name']}",
        "type": "{input['type']}",
        "parts": [
            \'{{'
                "name": "generated name of the described part",
                "description": "generated description of the part",
                "type": "type of the part, either 'component' or 'page'"
            \'}}'
        ]
    \'}}'
    """
    try:
        api_config = build_api_request(prompt, config)
        
        # Add metadata about the request
        span.set_metadata({
            "agent": "splitting",
            "input": input,
            "prompt": prompt,
            "config": {
                "provider": config["provider"],
                "model": config["model"]
            }
        })
        
        response = await make_api_call(api_config, span)
        logger.info("Splitting Agent: Successfully split project")
        api_output = extract_api_response(response, config["provider"])
        
        result = json.loads(api_output["content"])
        validated_result = validate_split_output(result, "Splitting Agent")
        
        # Add result metadata
        span.set_metadata({
            "output": validated_result,
            "tokens": api_output["usage"]
        })
        
        return validated_result

    except Exception as e:
        span.set_metadata({
            "error": str(e),
            "error_type": type(e).__name__
        })
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
    {{
        "description": "detailed plan here",
        "name": "name of first file to create",
        "path": "path to first file"
    }}"""
    try:
        api_config = build_api_request(prompt, config)
        logger.info(f"Planning Agent: API Config: {api_config}")
        response = await make_api_call(api_config, span)
        logger.info(f"Planning Agent: Successfully generated plan")
        api_output = extract_api_response(response, config["provider"])
        
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
    
    <start description>
    {input["description"]}
    <end description>

    Output just the code, nothing else.
    """


    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config, span)
        logger.info(f"Development Agent: Successfully generated code")
        api_output = extract_api_response(response, config["provider"])
        
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
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config, span)

        logger.debug("Expounding Agent: Generated expanded spec")

        api_output = extract_api_response(response, config["provider"])
        
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

    <start description>
    {input}
    <end description>

    Output ONLY one of these three words: "detail", "split", or "write"
    """

    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config, span)
        logger.info("Routing Agent: Successfully determined route")
        api_output = extract_api_response(response, config["provider"])
        
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
        planning_span = trace.span(name="planning")
        try:
            plan = await planning_agent(description, gemini_config, planning_span)
            planning_span.set_metadata("plan", plan)
            planning_span.end()  # End span on success
        except Exception as e:
            planning_span.end(status="error", statusMessage=str(e))
            raise

        # Initial splitting
        splitting_span = trace.span(name="initial_splitting")
        try:
            components = await splitting_agent(plan, gemini_config, splitting_span)
            splitting_span.set_metadata("components", components)
            splitting_span.end()  # End span on success
        except Exception as e:
            splitting_span.end(status="error", statusMessage=str(e))
            raise

        # Process queue for components that need work
        work_queue = components["parts"]
        
        while work_queue:
            current_batch = work_queue.copy()
            work_queue.clear()
            
            # Process all current components concurrently
            async with asyncio.TaskGroup() as tg:
                for component in current_batch:
                    # First try to develop the component
                    dev_span = trace.span(name=f"development_{component['name']}")
                    try:
                        dev_task = tg.create_task(
                            development_agent(component, claude_config, dev_span)
                        )
                        dev_span.end()  # End span after task creation
                    except Exception as e:
                        dev_span.end(status="error", statusMessage=str(e))
                        raise
                    
                    # Determine next steps
                    routing_span = trace.span(name=f"routing_{component['name']}")
                    try:
                        route = await routing_agent(component["description"], gemini_config, routing_span)
                        routing_span.set_metadata("route", route)
                        routing_span.end()
                    except Exception as e:
                        routing_span.end(status="error", statusMessage=str(e))
                        raise
                    
                    if route == "detail":
                        # Need more detail - send to expounding then splitting
                        exp_span = trace.span(name=f"expounding_{component['name']}")
                        try:
                            expanded = await expounding_agent(component, gemini_config, exp_span)
                            exp_span.end()
                        except Exception as e:
                            exp_span.end(status="error", statusMessage=str(e))
                            raise
                        
                        split_span = trace.span(name=f"splitting_after_expound_{component['name']}")
                        try:
                            split_components = await splitting_agent(expanded, gemini_config, split_span)
                            work_queue.extend(split_components["parts"])
                            split_span.end()
                        except Exception as e:
                            split_span.end(status="error", statusMessage=str(e))
                            raise
                            
                    elif route == "split":
                        # Need to split - send to splitting
                        split_span = trace.span(name=f"splitting_{component['name']}")
                        try:
                            split_components = await splitting_agent(component, gemini_config, split_span)
                            work_queue.extend(split_components["parts"])
                            split_span.end()
                        except Exception as e:
                            split_span.end(status="error", statusMessage=str(e))
                            raise

        trace.end(status="success")
        logger.info("Workflow: Execution completed successfully")
        
    except Exception as e:
        trace.end(status="error", statusMessage=str(e))
        logger.error("Workflow: Execution failed")
        logger.debug(f"Detailed error: {str(e)}")
        raise
    finally:
        # Make sure all events are flushed before exiting
        langfuse.flush()

# -------------------------
# Main Entrypoint
# -------------------------

if __name__ == '__main__':
    # Example project specification
    project_description = "A chatbot that can answer questions and help with tasks written in react and typescript."
    
    asyncio.run(execute_workflow(project_description))
