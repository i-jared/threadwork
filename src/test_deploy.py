import subprocess
import shutil
import os
from pathlib import Path

def create_react_app():
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
        print("✅ React app created successfully")
        
        # Install Tailwind CSS and its dependencies
        app_dir = test_dir / "my-react-app"
        subprocess.run(
            "bun add -d tailwindcss postcss autoprefixer",
            shell=True,
            check=True,
            cwd=app_dir
        )
        print("✅ Tailwind CSS and dependencies installed")
        
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
    except Exception as e:
        print("❌ An error occurred during deployment")
        print(f"Error details logged")
        # Log the full error message
        print(f"DEBUG: {str(e)}")

if __name__ == "__main__":
    create_react_app()
