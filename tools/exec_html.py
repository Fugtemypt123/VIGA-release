#!/usr/bin/env python3
"""
HTML execution server for Design2Code mode.
Handles HTML/CSS code execution and screenshot generation.
"""
import os
import tempfile
import subprocess
import base64
import io
from pathlib import Path
from typing import Dict, Tuple, Optional
from PIL import Image
import logging
from mcp.server.fastmcp import FastMCP

# tool config for agent
tool_configs = [
    {
        "type": "function",
        "function": {
            "name": "execute_and_evaluate_code",
            "description": "Execute HTML/CSS code and trigger verifier evaluation. This tool combines code execution with automatic verification. Always use this tool when you want to execute your code changes.\nReturns either:\n  (1) On error: detailed error information; or \n  (2) On success: a screenshot of the rendered HTML page and further modification suggestions from a separate verifier agent.\nImportant: The execution environment cannot read files generated in previous runs. Therefore, each response must output the complete, standalone HTML/CSS code that generates the entire page from scratch. If you want to make small changes relative to the previous version, use code_edit parameter to structure your reasoning before producing the final script: First, pinpoint the exact lines to modify in the previous script. Then provide a unified-style mini diff using the following format (no extra commentary inside the block):\n-: [lines to remove]\n+: [lines to add]\n. After the diff, apply those changes and output the full, updated HTML/CSS code (not just the patch).",
            "parameters": {
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "Analyze the current state and provide a clear plan for the required changes. Consider HTML structure, CSS styling, and responsive design optimization opportunities."
                    },
                    "code_edit": {
                        "type": "string", 
                        "description": "Provide your code modifications in the following format:\n-: [lines to remove]\n+: [lines to add]\nFocus on HTML structure and CSS styling."
                    },
                    "full_code": {
                        "type": "string",
                        "description": "Merge your code changes into the full code with proper formatting. Ensure proper HTML string."
                    }
                },
                "required": ["thought", "full_code"]
            }
        }
    }
]

# Create MCP instance
mcp = FastMCP("html-executor")

# Global executor instance
_executor = None

class HTMLExecutor:
    """Executes HTML/CSS code and generates screenshots."""
    
    def __init__(self, output_dir: str, browser_command: str = "google-chrome"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.browser_command = browser_command
        self.count = 0
        
    def _save_html_file(self, html_code: str, filename: str = "index.html") -> str:
        """Save HTML code to a temporary file."""
        html_path = os.path.join(self.output_dir, filename)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_code)
        
        return html_path
    
    def _take_screenshot(self, html_path: str, output_path: str, 
                        width: int = 1920, height: int = 1080) -> Tuple[bool, str]:
        """Take a screenshot of the HTML page using headless browser."""
        try:
            # Use Chrome/Chromium in headless mode to take screenshot
            cmd = [
                self.browser_command,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-size={},{}".format(width, height),
                "--screenshot={}".format(output_path),
                "file://{}".format(os.path.abspath(html_path))
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(output_path):
                return True, "Screenshot taken successfully"
            else:
                return False, f"Browser error: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return False, "Screenshot timeout"
        except FileNotFoundError:
            # Try alternative browser commands
            alternatives = ["chromium-browser", "chromium", "firefox"]
            for alt_browser in alternatives:
                try:
                    cmd[0] = alt_browser
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0 and os.path.exists(output_path):
                        return True, f"Screenshot taken with {alt_browser}"
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue
            return False, f"Browser not found. Tried: {self.browser_command}, {', '.join(alternatives)}"
        except Exception as e:
            return False, f"Screenshot error: {str(e)}"
    
    def _optimize_image(self, image_path: str) -> str:
        """Optimize the screenshot image."""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Resize if too large (max 1920x1080)
                max_width, max_height = 1920, 1080
                if img.width > max_width or img.height > max_height:
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                # Save optimized version
                optimized_path = image_path.replace('.png', '_optimized.png')
                img.save(optimized_path, 'PNG', optimize=True, quality=85)
                
                return optimized_path
        except Exception as e:
            logging.warning(f"Image optimization failed: {e}")
            return image_path
    
    def execute(self, html_code: str) -> Dict:
        """Execute HTML code and generate screenshot."""
        try:
            self.count += 1
            html_path = self._save_html_file(html_code, f"{self.count}.html")
            output_path = self.output_dir / f"{self.count}.png"
            success, message = self._take_screenshot(html_path, str(output_path))
            if not success:
                return {"status": "error", "output": message}
            optimized_path = self._optimize_image(str(output_path))
            return {"status": "success", "output": [optimized_path]}
        except Exception as e:
            logging.error(f"HTML execution failed: {e}")
            return {"status": "error", "output": str(e)}

@mcp.tool()
def initialize(args: dict) -> dict:
    """
    Initialize the HTML executor.
    """
    global _executor
    try:
        _executor = HTMLExecutor(args.get("output_dir"), args.get("browser_command", "google-chrome"))
        return {
            "status": "success", 
            "output": f"HTML executor initialized with output directory: {args.get('output_dir')}"
        }
    except Exception as e:
        return {"status": "error", "output": str(e)}

@mcp.tool()
def execute_and_evaluate_code(thought: str = '', code_edit: str = '', full_code: str = '') -> dict:
    """
    Execute HTML/CSS code and generate screenshot.
    
    Args:
        thought: Analysis of current state and plan for changes
        code: The HTML/CSS code to execute
    """
    global _executor
    if _executor is None:
        return {
            "status": "error", 
            "output": "HTML executor not initialized. Call initialize_executor first."
        }
    try:
        result = _executor.execute(full_code)
        return result
    except Exception as e:
        return {"status": "error", "output": str(e)}

    
def test_execute_test_html(test_html_path: Optional[str] = None,
                           output_dir: Optional[str] = None,
                           browser_command: str = "google-chrome") -> Dict:
    """
    Test helper: execute a local test.html and produce a screenshot.

    Args:
        test_html_path: Path to the HTML file to execute. Defaults to
            a "test.html" placed next to this file.
        output_dir: Directory to write screenshots. Defaults to a temp dir
            under the system temp root.
        browser_command: Browser command to use (e.g., google-chrome/chromium/firefox).

    Returns:
        A dict containing status, message/error, and output paths when applicable.
    """
    try:
        # Resolve defaults
        if test_html_path is None:
            test_html_path = str((Path(__file__).parent / "test.html").resolve())
        if output_dir is None:
            temp_root = tempfile.mkdtemp(prefix="design2code_test_output_")
            output_dir = temp_root

        if not os.path.exists(test_html_path):
            return {
                "status": "error",
                "output": f"Test HTML not found: {test_html_path}"
            }

        # Read HTML
        with open(test_html_path, "r", encoding="utf-8") as f:
            html_code = f.read()

        # Run executor directly
        executor = HTMLExecutor(output_dir=output_dir, browser_command=browser_command)
        result = executor.execute(html_code)

        # Attach some helpful information
        output = {
            "status": result.get("status", "error"),
            "details": result,
            "output_dir": str(output_dir),
            "test_html_path": test_html_path,
        }

        # Log a concise message
        if output["status"] == "success":
            logging.info(f"Test succeeded. Screenshot: {result.get('output')[0]}")
        else:
            logging.error(f"Test failed: {result.get('output')}")

        return output
    except Exception as e:
        logging.exception("Unexpected error running HTML executor test")
        return {"status": "error", "output": str(e)}

def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_result = test_execute_test_html(test_html_path="code_test.html", output_dir="output/test/design2code/")
        success = test_result.get("status") == "success"
        print(f"\n🎯 Overall test result: {'PASSED' if success else 'FAILED'}")
        sys.exit(0 if success else 1)
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()