import asyncio
import aiohttp
import aiofiles
import logging
from langgraph import Graph  # Assumes langgraph is installed and available

# -------------------------
# Logging Configuration
# -------------------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# -------------------------
# Agent Definitions
# -------------------------


async def planner_agent(project_spec: dict, config: dict) -> dict:
    """
    Planner Agent:
    Generates a project description based on the given project_spec.
    """
    logger.info("Planner Agent: Starting planning process.")
    try:
        # Simulate an external API call (using httpbin as a dummy endpoint)
        async with aiohttp.ClientSession() as session:
            async with session.get("https://httpbin.org/get") as response:
                if response.status != 200:
                    raise Exception(f"API request failed with status {response.status}")
                # The returned data is ignored; it is just used to simulate delay/network call.
                _ = await response.json()

        # Generate an idea based on the input specification.
        idea = {
            "title": f"{project_spec.get('theme', 'Project')} Idea",
            "description": f"A creative project centered around {project_spec.get('theme', 'an exciting theme')}."
        }
        logger.debug(f"Ideation Agent: Generated idea: {idea}")
        return idea

    except Exception as e:
        logger.error(f"Ideation Agent: Error encountered - {e}")
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
# Workflow Graph Construction
# -------------------------

def build_workflow_graph() -> Graph:
    """
    Builds and returns a workflow graph (DAG) using langgraph.
    Each node represents an agent, and edges define the execution order.
    """
    logger.info("Workflow: Building workflow graph using langgraph.")
    graph = Graph(name="ProjectConstructionWorkflow")

    # Add agent nodes to the graph.
    graph.add_node("Ideation", planner_agent)
    graph.add_node("Planning", planning_agent)
    graph.add_node("Development", development_agent)

    # Define the dependencies (edges) between nodes.
    graph.add_edge("Ideation", "Planning")
    graph.add_edge("Planning", "Development")

    # The graph now represents: Ideation -> Planning -> Development
    return graph

# -------------------------
# Execution Function
# -------------------------

async def run_workflow(project_spec: dict):
    """
    Executes the entire workflow asynchronously.
    Each agent is invoked in order, and file operations are performed concurrently.
    """
    logger.info("Workflow: Execution started.")
    # Build the workflow graph (for observability/debugging purposes)
    workflow_graph = build_workflow_graph()
    logger.debug(f"Workflow: Graph details: {workflow_graph}")


    o1_mini_config = {
        "api_endpoint": "https://httpbin.org/get",  # Change this to switch endpoints quickly.
        "api_key": "YOUR_API_KEY_HERE",               # API key, if required.
    }
    
    claude_config = {
        "api_endpoint": "https://httpbin.org/get",  # Change this to switch endpoints quickly.
        "api_key": "YOUR_API_KEY_HERE",               # API key, if required.
    }



    try:
        # Execute agents in sequence since each step depends on the previous output.
        idea = await planner_agent(project_spec, claude_config)
        plan = await planning_agent(idea, claude_config)
        await development_agent(plan, claude_config)
        logger.info("Workflow: Execution completed successfully.")
    except Exception as e:
        logger.error(f"Workflow: Execution failed - {e}")
        raise

# -------------------------
# Main Entrypoint
# -------------------------

if __name__ == '__main__':
    # Example project specification.
    project_spec = {"theme": "chatbot"}

    # Run the asynchronous workflow.
    asyncio.run(run_workflow(project_spec))
