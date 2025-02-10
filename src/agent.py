import asyncio
import aiohttp
import aiofiles
import logging
from langfuse import Langfuse  # Changed from langgraph to langfuse

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

class WorkflowManager:
    def __init__(self, langfuse_public_key: str, langfuse_secret_key: str):
        self.langfuse = Langfuse(
            public_key=langfuse_public_key,
            secret_key=langfuse_secret_key
        )

    async def execute_workflow(self, project_spec: dict, config: dict):
        """
        Executes the workflow with Langfuse tracing
        """
        trace = self.langfuse.trace(name="project_construction")
        
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

# -------------------------
# Main Entrypoint
# -------------------------

if __name__ == '__main__':
    # Example project specification
    project_spec = {"theme": "chatbot"}

    # Configuration
    config = {
        "api_endpoint": "https://api.example.com/v1",
        "api_key": "YOUR_API_KEY_HERE",
    }

    # Initialize and run workflow
    workflow = WorkflowManager(
        langfuse_public_key="your_public_key",
        langfuse_secret_key="your_secret_key"
    )
    
    asyncio.run(workflow.execute_workflow(project_spec, config))
