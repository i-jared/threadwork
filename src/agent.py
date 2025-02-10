import asyncio
import aiohttp
import aiofiles
import logging
import os
from langfuse import Langfuse
from dotenv import load_dotenv

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

async def splitting_agent(project_spec: dict, config: dict) -> dict:
    """
    Splitting Agent:
    Splits the project description into smaller chunks.
    """
    logger.info("Splitting Agent: Starting splitting process.")
    try:
        # Use config for API call
        async with aiohttp.ClientSession() as session:
            async with session.get(config["api_endpoint"], headers={
                "Authorization": f"Bearer {config['api_key']}"
            }) as response:
                if response.status != 200:
                    raise Exception("API request failed")
                _ = await response.json()

        # Generate an idea based on the input specification.
        idea = {
            "title": f"{project_spec.get('theme', 'Project')} Idea",
            "description": f"A creative project centered around {project_spec.get('theme', 'an exciting theme')}."
        }
        logger.debug(f"Ideation Agent: Generated idea: {idea}")
        return idea

    except Exception as e:
        logger.error(f"Ideation Agent: Error encountered")
        logger.debug(f"Detailed error: {str(e)}")
        raise

async def planning_agent(idea: dict, config: dict) -> dict:
    """
    Planning Agent:
    Creates a structured project plan from the idea.
    Simulates processing time with asyncio.sleep.
    """
    logger.info("Planning Agent: Starting planning process.")
    try:
        # Simulate some processing delay
        await asyncio.sleep(1)

        # Build a plan with a list of modules and code file content.
        plan = {
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
        }
        logger.debug(f"Planning Agent: Created plan: {plan}")
        return plan

    except Exception as e:
        logger.error(f"Planning Agent: Error encountered - {e}")
        raise

async def development_agent(plan: dict, config: dict) -> bool:
    """
    Development Agent:
    Produces code files based on the provided plan.
    Writes files concurrently using aiofiles.
    """
    logger.info("Development Agent: Starting development process.")

    async def write_file(filename: str, content: str):
        try:
            async with aiofiles.open(filename, mode='w') as f:
                await f.write(content)
            logger.info(f"Development Agent: Successfully wrote file: {filename}")
        except Exception as e:
            logger.error(f"Development Agent: Error writing file {filename} - {e}")
            raise

    try:
        # Create file-writing tasks concurrently.
        tasks = [
            write_file(filename, content)
            for filename, content in plan.get("files", {}).items()
        ]
        await asyncio.gather(*tasks)
        logger.debug("Development Agent: Completed writing all files.")
        return True

    except Exception as e:
        logger.error(f"Development Agent: Error encountered - {e}")
        raise

# -------------------------
# Workflow Execution
# -------------------------

async def execute_workflow(project_spec: dict, config: dict):
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
            idea = await splitting_agent(project_spec, config)
            splitting_span.set_metadata("idea", idea)

        with trace.span(name="planning") as planning_span:
            plan = await planning_agent(idea, config)
            planning_span.set_metadata("plan", plan)

        with trace.span(name="development") as dev_span:
            success = await development_agent(plan, config)
            dev_span.set_metadata("success", success)

        trace.end(status="success")
        logger.info("Workflow: Execution completed successfully.")
        
    except Exception as e:
        trace.end(status="error", statusMessage=str(e))
        logger.error("Workflow: Execution failed")
        logger.debug(f"Detailed error: {str(e)}")
        raise


def get_anthropic_config(api_key: str,prompt: str, max_tokens: int = 1024, model: str = "claude-3-5-sonnet-20241022"):
    return {
        "api_endpoint": "https://api.anthropic.com/v1/messages",
        "body": {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": f"{prompt}"}
            ]
        },
        "headers": {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    }

# -------------------------
# Main Entrypoint
# -------------------------

if __name__ == '__main__':
    # Example project specification
    project_spec = {"theme": "chatbot"}

    # Configuration

    asyncio.run(execute_workflow(project_spec, config))
