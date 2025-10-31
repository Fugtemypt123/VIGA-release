import os
import json
from PIL import Image
import io
import base64
from typing import Dict, List, Optional

def get_image_base64(image_path: str) -> str:
    """Return a full data URL for the image, preserving original jpg/png format."""
    image = Image.open(image_path)
    img_byte_array = io.BytesIO()
    ext = os.path.splitext(image_path)[1].lower()
    
    # Convert image to appropriate mode for saving
    if ext in ['.jpg', '.jpeg']:
        save_format = 'JPEG'
        mime_subtype = 'jpeg'
        # JPEG doesn't support transparency, convert RGBA to RGB
        if image.mode in ['RGBA', 'LA', 'P']:
            # Convert P mode to RGB first, then handle RGBA
            if image.mode == 'P':
                image = image.convert('RGBA')
            # Convert RGBA to RGB with white background
            if image.mode == 'RGBA':
                # Create a white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
                image = background
            elif image.mode == 'LA':
                # Convert LA to RGB
                image = image.convert('RGB')
    elif ext == '.png':
        save_format = 'PNG'
        mime_subtype = 'png'
        # PNG supports transparency, but convert P mode to RGBA
        if image.mode == 'P':
            image = image.convert('RGBA')
    else:
        # Fallback: keep original format if recognizable, else default to PNG
        save_format = image.format or 'PNG'
        mime_subtype = save_format.lower() if save_format.lower() in ['jpeg', 'png'] else 'png'
        # Handle P mode for fallback cases
        if image.mode == 'P':
            if save_format == 'JPEG':
                image = image.convert('RGB')
            else:
                image = image.convert('RGBA')
    
    image.save(img_byte_array, format=save_format)
    img_byte_array.seek(0)
    base64enc_image = base64.b64encode(img_byte_array.read()).decode('utf-8')
    if base64enc_image.startswith("/9j/"):
        mime_subtype = 'jpeg'
    elif base64enc_image.startswith("iVBOR"):
        mime_subtype = 'png'
    elif base64enc_image.startswith("UklGR"):
        mime_subtype = 'webp'
    return f"data:image/{mime_subtype};base64,{base64enc_image}"


def save_thought_process(memory: List[Dict], thought_save: str, current_round: int = None) -> None:
    """Save the current thought process to file."""
    try:
        if current_round is not None:
            filename = f"{thought_save}/{current_round+1}.json"
        else:
            filename = thought_save
        
        with open(filename, "w") as f:
            json.dump(memory, f, indent=4, ensure_ascii=False)
    except Exception as e:
        import logging
        logging.error(f"Failed to save thought process: {e}")

def get_scene_info(task_name: str, blender_file_path: str) -> str:
    """
    Get scene information from Blender file by executing a script to list all objects.
    
    Args:
        blender_file_path: Path to the Blender file
        
    Returns:
        String containing scene information with object names
    """
    try:
        import bpy
        import mathutils
        
        # Clear existing scene
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        
        # Open the blender file (no saving; read-only introspection)
        bpy.ops.wm.open_mainfile(filepath=blender_file_path)
        
        # Get scene information
        scene_info = []
        
        print(bpy.context.scene.objects.keys())
        
        # List all objects in the scene
        scene_info.append("Scene Information:")
        for obj in bpy.context.scene.objects:
            obj_name = obj.name

            # Get object bounding box
            bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
            bbox_min = mathutils.Vector((
                min(corner.x for corner in bbox_corners),
                min(corner.y for corner in bbox_corners),
                min(corner.z for corner in bbox_corners)
            ))
            bbox_max = mathutils.Vector((
                max(corner.x for corner in bbox_corners),
                max(corner.y for corner in bbox_corners),
                max(corner.z for corner in bbox_corners)
            ))
            bbox_size = bbox_max - bbox_min
            
            scene_info.append(f"- Name: {obj_name}; Location: {obj.location}; BBox: min({bbox_min.x:.3f}, {bbox_min.y:.3f}, {bbox_min.z:.3f}), max({bbox_max.x:.3f}, {bbox_max.y:.3f}, {bbox_max.z:.3f})")
            
        if len(scene_info) == 1:
            scene_info.append("All the information are provided in the code.")
        
        return "\n".join(scene_info)
        
    except ImportError:
        # If bpy is not available, return a placeholder message
        return "Scene information not available (Blender Python API not accessible)"
    except Exception as e:
        return f"Error getting scene information: {str(e)}"
    finally:
        # Ensure we do not leave a file open in Blender. Reset to factory settings silently.
        try:
            bpy.ops.wm.read_factory_settings(use_empty=True)
        except Exception:
            # Suppress any cleanup errors to avoid shutdown issues
            pass
        
def extract_code_pieces(text: str, concat: bool = True) -> list[str]:
    """Extract code pieces from a text string.
    Args:
        text: str, model prediciton text.
    Rets:
        code_pieces: list[str], code pieces in the text.
    """
    code_pieces = []
    while "```python" in text:
        st_idx = text.index("```python") + 10
        # end_idx = text.index("```", st_idx)
        if "```" in text[st_idx:]:
            end_idx = text.index("```", st_idx)
        else: 
            end_idx = len(text)
        code_pieces.append(text[st_idx:end_idx].strip())
        text = text[end_idx+3:].strip()
    if concat: return '\n\n'.join(code_pieces)
    return code_pieces
