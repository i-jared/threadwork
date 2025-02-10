import asyncio
import aiohttp
import aiofiles
import logging
import os
from langfuse import Langfuse
from dotenv import load_dotenv
from config import build_api_request
# Load environment variables
load_dotenv()

# -------------------------
# Logging Configuration
# -------------------------
logging.basicConfig(level=logging.DEBUG)
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

async def splitting_agent(project_spec: dict, config: dict) -> dict:
    """
    Splitting Agent:
    Splits the project description into smaller chunks.
    """
    logger.info("Splitting Agent: Starting splitting process.")
    try:
        response = await make_api_call(config)
        
        idea = {
            "title": f"{project_spec.get('theme', 'Project')} Idea",
            "description": response.get("completion", f"A creative project centered around {project_spec.get('theme', 'an exciting theme')}.")
        }
        logger.debug(f"Splitting Agent: Generated idea: {idea}")
        return idea

    except Exception as e:
        logger.error("Splitting Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def planning_agent(idea: dict, config: dict) -> dict:
    """
    Planning Agent:
    Creates a structured project plan from the idea.
    """
    logger.info("Planning Agent: Starting planning process.")
    try:
        response = await make_api_call(config)
        
        plan = response.get("completion", {
            "modules": ["main", "utils"],
            "files": {
                "main.py": (
                    f"# {idea['title']}\n"
                    f"# {idea['description']}\n\n"
                    "def main():\n"
                    "    print('Hello from the main module!')\n\n"
                    "if __name__ == '__main__':\n"
                    "    main()\n"
                ),
                "utils.py": (
                    "# Utility functions for the project\n\n"
                    "def helper():\n"
                    "    print('This is a helper function')\n"
                )
            }
        })
        logger.debug(f"Planning Agent: Created plan: {plan}")
        return plan

    except Exception as e:
        logger.error("Planning Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def development_agent(plan: dict, config: dict) -> bool:
    """
    Development Agent:
    Produces code files based on the provided plan.
    """
    logger.info("Development Agent: Starting development process.")

    async def write_file(filename: str, content: str):
        try:
            async with aiofiles.open(filename, mode='w') as f:
                await f.write(content)
            logger.info(f"Development Agent: Successfully wrote file: {filename}")
        except Exception as e:
            logger.error(f"Development Agent: Error writing file {filename}")
            logger.debug(f"Detailed error: {str(e)}")
            raise

    try:
        response = await make_api_call(config)
        
        # Create file-writing tasks concurrently
        tasks = [
            write_file(filename, content)
            for filename, content in response.get("files", plan.get("files", {})).items()
        ]
        await asyncio.gather(*tasks)
        logger.debug("Development Agent: Completed writing all files.")
        return True

    except Exception as e:
        logger.error("Development Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def expounding_agent(project_spec: dict, config: dict) -> dict:
    """
    Expounding Agent:
    Given a description, increase the detail and resolution of the description.
    """
    logger.info("Expounding Agent: Starting expounding process.")
    try:
        response = await make_api_call(config)
        
        expanded_spec = response.get("completion", {
            "title": f"{project_spec.get('theme', 'Project')} Idea",
            "description": f"A creative project centered around {project_spec.get('theme', 'an exciting theme')}."
        })
        logger.debug(f"Expounding Agent: Generated expanded spec: {expanded_spec}")
        return expanded_spec

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
        with trace.span(name="splitting") as splitting_span:
            config = build_api_request(os.getenv('ANTHROPIC_API_KEY'), project_spec)
            idea = await splitting_agent(project_spec, config)
            splitting_span.set_metadata("idea", idea)

        with trace.span(name="planning") as planning_span:
            config = build_api_request(os.getenv('DEEPSEEK_API_KEY'), idea)
            plan = await planning_agent(idea, config)
            planning_span.set_metadata("plan", plan)

        with trace.span(name="development") as dev_span:
            config = build_api_request(os.getenv('GEMINI_API_KEY'), plan)
            success = await development_agent(plan, config)
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
