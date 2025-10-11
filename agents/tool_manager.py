import os
import sys
import importlib.util
from typing import Dict, List, Optional

class ToolManager:
    """Helper class for managing tool definitions and configurations."""
    
    @staticmethod
    def load_tool_configs_from_file(file_path: str) -> List[Dict]:
        """Load tool_configs from an MCP file."""
        try:
            # Add the directory to sys.path temporarily
            file_dir = os.path.dirname(os.path.abspath(file_path))
            if file_dir not in sys.path:
                sys.path.insert(0, file_dir)
            
            # Load the module
            spec = importlib.util.spec_from_file_location("mcp_module", file_path)
            if spec is None or spec.loader is None:
                return []
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Extract tool_configs
            if hasattr(module, 'tool_configs'):
                return module.tool_configs
            return []
        except Exception as e:
            print(f"Warning: Failed to load tool_configs from {file_path}: {e}")
            return []
    
    @staticmethod
    def get_generator_tools(mode: str, task_name: str, tool_servers: Optional[Dict[str, str]] = None) -> List[Dict]:
        """Get available tools for the generator agent based on mode and task.
        Now dynamically loads tool configurations from MCP files.
        
        Args:
            mode: The mode (blendergym, autopresent, design2code, static_scene, dynamic_scene, blendergym-hard)
            task_name: The task name
            tool_servers: Optional dict mapping server types to file paths
        """
        if mode not in ["blendergym", "autopresent", "design2code", "static_scene", "dynamic_scene", "blendergym-hard"]:
            return []
        
        tools: List[Dict] = []
        
        # Define which tools to load from which servers based on mode
        server_tool_mapping = {
            "blender": ["execute_and_evaluate"],
            "rag": ["rag_query"],
            "generator": ["initialize_generator", "exec_pil_code", "generate_scene_description", "generate_initialization_suggestions"],
            "meshy": ["generate_and_download_3d_asset"] if mode in ["static_scene", "dynamic_scene"] else []
        }
        
        # Always include init_plan tool (not from MCP servers)
        tools.append({
            "type": "function",
            "function": {
                "name": "init_plan",
                "description": "Store a detailed scene plan for subsequent actions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "detailed_description": {"type": "string", "description": "Comprehensive scene description including objects, relations, and initial layout"}
                    },
                    "required": ["detailed_description"]
                }
            }
        })
        
        # Load tools from MCP servers if tool_servers is provided
        if tool_servers:
            for server_type, file_path in tool_servers.items():
                if server_type in server_tool_mapping:
                    # Load tool_configs from the MCP file
                    mcp_tools = ToolManager.load_tool_configs_from_file(file_path)
                    
                    # Filter tools based on the mapping
                    wanted_tools = server_tool_mapping[server_type]
                    for tool in mcp_tools:
                        if tool.get("function", {}).get("name") in wanted_tools:
                            tools.append(tool)
        else:
            # Fallback: use default tool paths
            default_servers = {
                "blender": "tools/exec_blender.py",
                "rag": "tools/rag.py",
                "generator": "tools/generator_base.py",
                "meshy": "tools/meshy.py" if mode in ["static_scene", "dynamic_scene"] else None
            }
            
            for server_type, file_path in default_servers.items():
                if file_path and os.path.exists(file_path) and server_type in server_tool_mapping:
                    mcp_tools = ToolManager.load_tool_configs_from_file(file_path)
                    wanted_tools = server_tool_mapping[server_type]
                    for tool in mcp_tools:
                        if tool.get("function", {}).get("name") in wanted_tools:
                            tools.append(tool)
        
        return tools
    
    @staticmethod
    def get_verifier_tools(mode: str, task_name: str, tool_servers: Optional[Dict[str, str]] = None) -> List[Dict]:
        """Get available tools for the verifier agent based on mode.
        Now dynamically loads tool configurations from MCP files.
        
        Args:
            mode: The mode
            task_name: The task name
            tool_servers: Optional dict mapping server types to file paths
        """
        tools: List[Dict] = []
        
        # Define which tools to load from which servers
        server_tool_mapping = {
            "investigator": ["setup_camera", "investigate", "set_object_visibility", "set_key_frame", "end"]
        }
        
        # Load tools from MCP servers if tool_servers is provided
        if tool_servers:
            for server_type, file_path in tool_servers.items():
                if server_type in server_tool_mapping:
                    # Load tool_configs from the MCP file
                    mcp_tools = ToolManager.load_tool_configs_from_file(file_path)
                    
                    # Filter tools based on the mapping
                    wanted_tools = server_tool_mapping[server_type]
                    for tool in mcp_tools:
                        if tool.get("function", {}).get("name") in wanted_tools:
                            tools.append(tool)
        else:
            # Fallback: use default tool paths
            default_servers = {
                "investigator": "tools/investigator.py"
            }
            
            for server_type, file_path in default_servers.items():
                if file_path and os.path.exists(file_path) and server_type in server_tool_mapping:
                    mcp_tools = ToolManager.load_tool_configs_from_file(file_path)
                    wanted_tools = server_tool_mapping[server_type]
                    for tool in mcp_tools:
                        if tool.get("function", {}).get("name") in wanted_tools:
                            tools.append(tool)

        return tools
    
    @staticmethod
    def get_available_tools_from_servers(tool_servers: Dict[str, str]) -> Dict[str, List[str]]:
        """Get all available tool names from MCP servers for debugging purposes."""
        available_tools = {}
        
        for server_type, file_path in tool_servers.items():
            mcp_tools = ToolManager.load_tool_configs_from_file(file_path)
            tool_names = [tool.get("function", {}).get("name") for tool in mcp_tools if tool.get("function", {}).get("name")]
            available_tools[server_type] = tool_names
        
        return available_tools
