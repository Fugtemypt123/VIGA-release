def get_scene_info(task_name: str, blender_file_path: str, notice_assets: dict = None) -> str:
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
            if task_name in notice_assets and obj_name not in notice_assets[task_name]:
                continue
            
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
            
            scene_info.append(f"- Name: {obj_name}; BBox: min({bbox_min.x:.3f}, {bbox_min.y:.3f}, {bbox_min.z:.3f}), max({bbox_max.x:.3f}, {bbox_max.y:.3f}, {bbox_max.z:.3f})")
            
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