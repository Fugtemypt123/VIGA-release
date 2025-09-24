import json
import logging
from typing import Dict, Any

class ToolHandler:
    """Helper class for handling tool calls in generator and verifier agents."""
    
    def __init__(self, tool_client, server_type: str):
        self.tool_client = tool_client
        self.server_type = server_type
        self.blender_file_path = None
    
    async def handle_generator_tool_call(self, tool_call) -> Dict[str, Any]:
        """Handle tool calls from the generator agent."""
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        
        try:
            if function_name == "generate_and_download_3d_asset":
                if self.server_type != "blender":
                    return {'text': "Error: 3D asset generation is only available for Blender mode", 'success': False}
                
                result = await self.tool_client.call_tool("blender", "generate_and_download_3d_asset", {
                    "object_name": function_args.get("object_name", ""),
                    "reference_type": function_args.get("reference_type", ""),
                    "object_description": function_args.get("object_description", "")
                })
                
                if result.get("status") == "success":
                    object_name = function_args.get('object_name', '')
                    # output_content = f"# import a 3D asset: {object_name}\n# To edit this asset, please use `bpy.data.objects['{object_name}']`\n# To copy this asset (if you think you'll need more than one of it in the target image), please use `new_object = bpy.data.objects['{object_name}'].copy()\n# To delete this object (if you think the quality of this asset is really bad), please use `bpy.data.objects.remove(bpy.data.objects['{object_name}'])`\n"
                    return {
                        'text': f"Successfully generated and downloaded 3D asset: {object_name}. {result.get('message', '')}",
                        'success': True,
                        # 'output_content': output_content
                    }
                else:
                    return {
                        'text': f"Failed to generate and download 3D asset: {result.get('error', 'Unknown error')}",
                        'success': False,
                        # 'output_content': None
                    }

            elif function_name == "investigate_3d":
                if self.server_type != "blender":
                    return {'text': "Error: 3D investigation is only available for Blender mode", 'success': False}
                
                op = function_args.get('operation')
                if op == 'focus':
                    result = await self.tool_client.call_tool("blender", "focus", {
                        "object_name": function_args.get("object_name", "")
                    })
                    if result.get("status") == "success":
                        return {
                            'text': f"Focused camera on object: {function_args.get('object_name', '')}. {result.get('message', '')}",
                            'success': True
                        }
                    else:
                        return {
                            'text': f"Failed to focus: {result.get('error', 'Unknown error')}",
                            'success': False
                        }
                elif op == 'zoom':
                    result = await self.tool_client.call_tool("blender", "zoom", {
                        "direction": function_args.get("direction", "")
                    })
                    if result.get("status") == "success":
                        return {
                            'text': f"Zoomed {function_args.get('direction', '')}. {result.get('message', '')}",
                            'success': True
                        }
                    else:
                        return {
                            'text': f"Failed to zoom: {result.get('error', 'Unknown error')}",
                            'success': False
                        }
                elif op == 'move':
                    result = await self.tool_client.call_tool("blender", "move", {
                        "direction": function_args.get("direction", "")
                    })
                    if result.get("status") == "success":
                        return {
                            'text': f"Moved camera {function_args.get('direction', '')}. {result.get('message', '')}",
                            'success': True
                        }
                    else:
                        return {
                            'text': f"Failed to move: {result.get('error', 'Unknown error')}",
                            'success': False
                        }
                else:
                    return {
                        'text': f"Unknown operation: {op}",
                        'success': False
                    }
            else:
                return {'text': f"Unknown tool: {function_name}", 'success': False}
        except Exception as e:
            return {'text': f"Error executing tool: {str(e)}", 'success': False}
    
    async def execute_script(self, code: str, round_num: int = None) -> Dict[str, Any]:
        """Execute code directly (Blender Python, HTML, etc.)."""
        try:
            result = await self.tool_client.exec_script(
                server_type=self.server_type,
                code=code,
                round_num=round_num or 1,
            )
            return result
        except Exception as e:
            return {'text': f"Error executing script: {str(e)}", 'success': False}
    
    async def handle_verifier_tool_call(self, tool_call, current_image_path: str = None, target_image_path: str = None, round_num: int = None) -> Dict[str, Any]:
        """Handle tool calls from the verifier agent."""
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        
        try:
            if function_name == "investigate_3d":
                op = function_args['operation']
                if op == 'focus':
                    output = await self.tool_client.call_tool("scene", "focus", {
                        "object_name": function_args.get("object_name", ""),
                        "round_num": round_num
                    })
                    return {'text': f"Focused camera on object: {function_args.get('object_name', '')}", 'image': output.get('image'), 'camera_position': output.get('camera_position')}
                elif op == 'zoom':
                    output = await self.tool_client.call_tool("scene", "zoom", {
                        "direction": function_args.get("direction", ""),
                        "round_num": round_num
                    })
                    return {'text': f"Zoomed {function_args.get('direction', '')}", 'image': output.get('image'), 'camera_position': output.get('camera_position')}
                elif op == 'move':
                    output = await self.tool_client.call_tool("scene", "move", {
                        "direction": function_args.get("direction", ""),
                        "round_num": round_num
                    })
                    return {'text': f"Moved camera {function_args.get('direction', '')}", 'image': output.get('image'), 'camera_position': output.get('camera_position')}
                else:
                    return {'text': f"Unknown operation: {op}", 'image': None, 'camera_position': None}
            elif function_name == "compare_images":
                output = await self.tool_client.call_tool("image", "compare_images", {
                    "path1": current_image_path,
                    "path2": target_image_path
                })
                return {'text': output.get('description', ''), 'image': None, 'camera_position': None}
            elif function_name == "compare_designs":
                output = await self.tool_client.call_tool("web", "compare_designs", {
                    "generated_path": current_image_path,
                    "target_path": target_image_path
                })
                if output.get("status") == "success":
                    result = output.get("result", {})
                    return {'text': result.get('comparison', ''), 'image': None, 'camera_position': None}
                else:
                    return {'text': f"Comparison failed: {output.get('error', 'Unknown error')}", 'image': None, 'camera_position': None}
            elif function_name == "analyze_html_structure":
                # Extract HTML code from the current context (this would need to be passed in)
                # For now, return a placeholder
                return {'text': "HTML structure analysis not yet implemented", 'image': None, 'camera_position': None}
            else:
                return {'text': f"Unknown tool: {function_name}", 'image': None, 'camera_position': None}
        except Exception as e:
            return {'text': f"Error executing tool: {str(e)}", 'image': None, 'camera_position': None}
