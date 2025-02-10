import asyncio
import aiohttp
import aiofiles
import logging
import os
import json
from langfuse import Langfuse
from dotenv import load_dotenv
from src.config import build_api_request, extract_api_response
from src.file import write_file
from src.logging_config import setup_logging
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

async def splitting_agent(input: str, project_spec: dict, config: dict, span) -> dict:
    """
    Splitting Agent:
    Splits the project description into smaller chunks.
    """
    logger.info("Splitting Agent: Starting splitting process.")
    prompt = f"""Split the following app segment description into smaller chunks, which should be a single component or a single part of a component: 
    
    ```
    {input}
    ```
    
    The format should be as follows, with absolutely no other text or characters.

    '{{'
        name: 'generated name of the described component',
        parts: [
            '{{'
                name: 'generated name of the described part',
                description: 'generated description of the part',
            '}}'
        ]
    '}}'
    """
    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config)
        logger.info(f"Splitting Agent: Successfully split project")
        api_output = extract_api_response(response, config["provider"])
        
        # Add token tracking
        span.update_usage(
            input_tokens=api_output["usage"]["input_tokens"],
            output_tokens=api_output["usage"]["output_tokens"],
            total_tokens=api_output["usage"]["total_tokens"]
        )

        return json.loads(api_output["content"])




    except Exception as e:
        logger.error("Splitting Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def planning_agent(input: dict, config: dict, span) -> str:
    """
    Planning Agent:
    Creates a structured project plan from the idea.
    """
    logger.info("Planning Agent: Starting planning process.")
    prompt = f"""Create a detailed description for the following app. Focus on the UI and UX.
    
    ```
    {input}
    ```

    Output just the plan, nothing else.
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
        
        return api_output["content"]
        
    except Exception as e:
        logger.error("Planning Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def development_agent(input: dict, config: dict, span) -> bool:
    """
    Development Agent:
    Produces code files based on the provided description and name: 

    {path: input["path"], description: input["description"]}
    """
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

async def expounding_agent(input: str, config: dict, span) -> str:
    """
    Expounding Agent:
    Given a description, increase the detail and resolution of the description.
    """
    logger.info("Expounding Agent: Starting expounding process.")
    prompt = f"""
    Given the following description, increase the detail and resolution of the description.

    ```
    {input}
    ```

    Output just the description, nothing else.
    """

    try:
        api_config = build_api_request(prompt, config)
        response = await make_api_call(api_config)

        logger.debug(f"Expounding Agent: Generated expanded spec")

        api_output = extract_api_response(response, config["provider"])
        
        # Add token tracking
        span.update_usage(
            input_tokens=api_output["usage"]["input_tokens"],
            output_tokens=api_output["usage"]["output_tokens"],
            total_tokens=api_output["usage"]["total_tokens"]
        )
        
        return api_output["content"]

    except Exception as e:
        logger.error("Expounding Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

# -------------------------
# Workflow Execution
# -------------------------

async def execute_workflow(project_spec: dict):
    """
    Executes the workflow with Langfuse tracing
    """
    langfuse = Langfuse(
        public_key=os.getenv('LANGFUSE_PUBLIC_KEY'),
        secret_key=os.getenv('LANGFUSE_SECRET_KEY'),
        host=os.getenv('LANGFUSE_HOST')
    )
    
    trace = langfuse.trace(name="project_construction")
    
    try:
        config = build_api_request(os.getenv('ANTHROPIC_API_KEY'), project_spec)
        with trace.span(name="splitting") as splitting_span:
            idea = await splitting_agent(project_spec, config, splitting_span)
            splitting_span.set_metadata("idea", idea)

        config = build_api_request(os.getenv('DEEPSEEK_API_KEY'), idea)
        with trace.span(name="planning") as planning_span:
            plan = await planning_agent(idea, config, planning_span)
            planning_span.set_metadata("plan", plan)

        config = build_api_request(os.getenv('GEMINI_API_KEY'), plan)
        with trace.span(name="development") as dev_span:
            success = await development_agent(plan, config, dev_span)
            dev_span.set_metadata("success", success)

        trace.end(status="success")
        logger.info("Workflow: Execution completed successfully.")
        
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
