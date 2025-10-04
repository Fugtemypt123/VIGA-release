# blender_server.py
import bpy
import mathutils
import math
import os
import sys
from pathlib import Path
import logging
from mcp.server.fastmcp import FastMCP

# 创建全局 MCP 实例
mcp = FastMCP("scene-server")

# 全局工具实例
_investigator = None

# ======================
# 内置工具
# ======================

class GetSceneInfo:
    def __init__(self, blender_path: str):
        bpy.ops.wm.open_mainfile(filepath=str(blender_path))

    def get_info(self) -> dict:
        try:
            scene_info = {"objects": [], "materials": [], "lights": [], "cameras": [], "render_settings": {}}
            for obj in bpy.data.objects:
                obj_info = {"name": obj.name, "type": obj.type,
                            "location": list(obj.matrix_world.translation),
                            "rotation": list(obj.rotation_euler),
                            "scale": list(obj.scale),
                            "visible": not (obj.hide_viewport or obj.hide_render),
                            "active": obj == bpy.context.active_object}
                if obj.type == 'MESH':
                    obj_info["vertices"] = len(obj.data.vertices)
                    obj_info["faces"] = len(obj.data.polygons)
                    obj_info["materials"] = [mat.name for mat in obj.material_slots if mat.material]
                scene_info["objects"].append(obj_info)

            for mat in bpy.data.materials:
                scene_info["materials"].append({
                    "name": mat.name,
                    "use_nodes": mat.use_nodes,
                    "diffuse_color": list(mat.diffuse_color),
                    "metallic": getattr(mat, 'metallic', None),
                    "roughness": getattr(mat, 'roughness', None)
                })

            for light in [o for o in bpy.data.objects if o.type == 'LIGHT']:
                scene_info["lights"].append({
                    "name": light.name,
                    "type": light.data.type,
                    "energy": light.data.energy,
                    "color": list(light.data.color),
                    "location": list(light.matrix_world.translation),
                    "rotation": list(light.rotation_euler)
                })

            for cam in [o for o in bpy.data.objects if o.type == 'CAMERA']:
                scene = bpy.context.scene
                scene_info["cameras"].append({
                    "name": cam.name,
                    "lens": cam.data.lens,
                    "location": list(cam.matrix_world.translation),
                    "rotation": list(cam.rotation_euler),
                    "is_active": cam == scene.camera,
                    "dof_distance": cam.data.dof_distance if cam.data.dof.use_dof else None,
                    "dof_aperture_fstop": cam.data.dof.aperture_fstop if cam.data.dof.use_dof else None
                })

            rnd = bpy.context.scene.render
            scene_info["render_settings"] = {
                "resolution_x": rnd.resolution_x,
                "resolution_y": rnd.resolution_y,
                "resolution_percentage": rnd.resolution_percentage,
                "engine": rnd.engine,
                "samples": bpy.context.scene.cycles.samples if rnd.engine == 'CYCLES' else None
            }

            return scene_info
        except Exception as e:
            logging.error(f"scene info error: {e}")
            return {}


# ======================
# 相机探查器（修复：先保存路径再加载）
# ======================


# ======================
# 相机探查器（修复：先保存路径再加载）
# ======================

class Investigator3D:
    def __init__(self, thoughtprocess_save: str, blender_path: str):
        self.blender_path = blender_path          # 先保存路径
        self._load_blender_file()                 # 再加载文件
        self.base = Path(thoughtprocess_save) / "investigator"
        self.base.mkdir(parents=True, exist_ok=True)
        # self.cam = self._get_or_create_cam()
        self.target = None
        self.radius = 5.0
        self.theta = 0.0
        self.phi = 0.0
        self.count = 0

    def _load_blender_file(self):
        """加载 Blender 文件，如果已经加载了相同的文件则跳过"""
        # current_file = bpy.data.filepath
        # if current_file != self.blender_path:
        bpy.ops.wm.open_mainfile(filepath=str(self.blender_path))
        self.cam = self._get_or_create_cam()

    def _get_or_create_cam(self):
        # Use existing camera if available, otherwise create with fixed starting positions
        if 'Camera1' in bpy.data.objects:
            cam = bpy.data.objects['Camera1']
            # Set to a fixed starting position (-z direction)
            self._set_camera_to_position(cam, "z")
            return cam
        else:
            # Check for any existing camera
            for existing_cam in bpy.data.objects:
                if existing_cam.type == 'CAMERA':
                    # Set to fixed starting position
                    self._set_camera_to_position(existing_cam, "z")
                    return existing_cam
            
            # Create new camera with fixed starting position (-z direction)
            bpy.ops.object.camera_add(location=(0, 0, 5))
            cam = bpy.context.active_object
            cam.name = "InvestigatorCamera"
            self._set_camera_to_position(cam, "z")
            return cam
    
    def _set_camera_to_position(self, cam, direction="z"):
        """Set camera to fixed starting positions: -z, -x, -y directions or bbox above"""
        if direction == "z":
            # -z direction (from above looking down)
            cam.location = (0, 0, 5)
            cam.rotation_euler = (math.radians(60), 0, 0)
        elif direction == "x":
            # -x direction (from side looking at scene)
            cam.location = (-5, 0, 2)
            cam.rotation_euler = (math.radians(90), 0, math.radians(90))
        elif direction == "y":
            # -y direction (from front looking at scene)
            cam.location = (0, -5, 2)
            cam.rotation_euler = (math.radians(90), 0, 0)
        elif direction == "bbox":
            # From above bounding box
            cam.location = (0, 0, 10)
            cam.rotation_euler = (math.radians(90), 0, 0)
        
        cam.data.lens = 20

    def _render(self, round_num: int):
        bpy.context.scene.camera = self.cam
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.render.filepath = str(self.base / f"{round_num+1}" / f"{self.count+1}.png")
        bpy.ops.render.render(write_still=True)
        out = bpy.context.scene.render.filepath
        self.count += 1

        # Do not save the blender file after each operation
        # try:
        #     bpy.ops.wm.save_mainfile(filepath=self.blender_path)
        #     print(f"Blender file saved to: {self.blender_path}")
        # except Exception as e:
        #     print(f"Warning: Failed to save blender file: {e}")

        # 获取当前相机位置信息
        camera_position = str({
            "location": list(self.cam.matrix_world.translation),
            "rotation": list(self.cam.rotation_euler),
            "target_object": self.target.name if self.target else None,
            "radius": self.radius,
            "theta": self.theta,
            "phi": self.phi
        })
        
        return {
            "image_path": out,
            "camera_position": camera_position
        }

    def focus_on_object(self, object_name: str, round_num: int) -> dict:
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"{object_name} not found")
        self.target = obj
        # track-to
        constraint = None
        for c in self.cam.constraints:
            if c.type == 'TRACK_TO':
                constraint = c
                break
        if not constraint:
            constraint = self.cam.constraints.new('TRACK_TO')
        constraint.target = obj
        constraint.track_axis = 'TRACK_NEGATIVE_Z'
        constraint.up_axis = 'UP_Y'
        self.radius = (self.cam.matrix_world.translation - obj.matrix_world.translation).length
        self.theta = math.atan2(*(self.cam.matrix_world.translation[i] - obj.matrix_world.translation[i] for i in (1,0)))
        self.phi = math.asin((self.cam.matrix_world.translation.z - obj.matrix_world.translation.z)/self.radius)
        return self._render(round_num)

    def zoom(self, direction: str, round_num: int) -> dict:
        if direction == 'in':
            self.radius = max(1, self.radius-3)
        elif direction == 'out':
            self.radius += 3
        return self._update_and_render(round_num)

    def move_camera(self, direction: str, round_num: int) -> dict:
        step = self.radius
        theta_step = step/(self.radius*math.cos(self.phi))
        phi_step = step/self.radius
        if direction=='up': self.phi = min(math.pi/2-0.1, self.phi+phi_step)
        elif direction=='down': self.phi = max(-math.pi/2+0.1, self.phi-phi_step)
        elif direction=='left': self.theta -= theta_step
        elif direction=='right': self.theta += theta_step
        return self._update_and_render(round_num)

    def _update_and_render(self, round_num: int) -> dict:
        t = self.target.matrix_world.translation
        x = self.radius*math.cos(self.phi)*math.cos(self.theta)
        y = self.radius*math.cos(self.phi)*math.sin(self.theta)
        z = self.radius*math.sin(self.phi)
        self.cam.matrix_world.translation = (t.x+x, t.y+y, t.z+z)
        return self._render(round_num)

    def add_viewpoint(self, object_names: list, round_num: int) -> dict:
        """
        计算对象列表的边界框，在四个上角放置相机，选择最佳视角
        
        Args:
            object_names: 要观察的对象名称列表
            round_num: 轮次编号
            
        Returns:
            dict: 包含最佳视角的渲染结果
        """
        try:
            # 获取所有指定的对象
            objects = []
            for obj_name in object_names:
                obj = bpy.data.objects.get(obj_name)
                if obj:
                    objects.append(obj)
                else:
                    logging.warning(f"Object '{obj_name}' not found in scene")
            
            if not objects:
                raise ValueError("No valid objects found in the provided list")
            
            # 计算所有对象的联合边界框
            min_x = min_y = min_z = float('inf')
            max_x = max_y = max_z = float('-inf')
            
            for obj in objects:
                # 获取对象的世界坐标边界框
                bbox_corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
                
                for corner in bbox_corners:
                    min_x = min(min_x, corner.x)
                    min_y = min(min_y, corner.y)
                    min_z = min(min_z, corner.z)
                    max_x = max(max_x, corner.x)
                    max_y = max(max_y, corner.y)
                    max_z = max(max_z, corner.z)
            
            # 计算边界框中心和尺寸
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            center_z = (min_z + max_z) / 2
            center = mathutils.Vector((center_x, center_y, center_z))
            
            # 计算边界框尺寸，添加一些边距
            size_x = max_x - min_x
            size_y = max_y - min_y
            size_z = max_z - min_z
            max_size = max(size_x, size_y, size_z)
            margin = max_size * 0.5  # 添加50%的边距
            
            # 定义四个上角的相机位置
            camera_positions = [
                (center_x - margin, center_y - margin, center_z + margin),  # 左下角
                (center_x + margin, center_y - margin, center_z + margin),  # 右下角
                (center_x - margin, center_y + margin, center_z + margin),  # 左上角
                (center_x + margin, center_y + margin, center_z + margin)   # 右上角
            ]
            
            # 为每个相机位置渲染并评估视角质量
            best_view = None
            best_score = -1
            
            for i, pos in enumerate(camera_positions):
                # 设置相机位置
                self.cam.location = pos
                self.cam.rotation_euler = (math.radians(60), 0, math.radians(45))
                
                # 让相机看向中心点
                direction = center - self.cam.location
                self.cam.rotation_euler = self.cam.location.to_track_quat('-Z', 'Y').to_euler()
                
                # 渲染当前视角
                render_result = self._render(round_num)
                
                # 简单的视角质量评估（可以扩展）
                # 这里使用边界框覆盖度和距离作为评估标准
                distance_to_center = (self.cam.location - center).length
                bbox_visible_ratio = min(1.0, max_size / distance_to_center) if distance_to_center > 0 else 1.0
                
                # 综合评分：距离适中 + 可见度高
                ideal_distance = max_size * 2
                distance_score = 1.0 - abs(distance_to_center - ideal_distance) / ideal_distance
                score = bbox_visible_ratio * 0.7 + distance_score * 0.3
                
                if score > best_score:
                    best_score = score
                    best_view = {
                        'position': pos,
                        'score': score,
                        'render_result': render_result,
                        'view_index': i
                    }
                
                logging.info(f"Viewpoint {i+1}: position={pos}, score={score:.3f}")
            
            # 返回最佳视角的结果
            if best_view:
                logging.info(f"Best viewpoint selected: {best_view['view_index']+1} with score {best_view['score']:.3f}")
                return {
                    'status': 'success',
                    'image': best_view['render_result']['image_path'],
                    'camera_position': best_view['render_result']['camera_position'],
                    'best_viewpoint': {
                        'position': best_view['position'],
                        'score': best_view['score'],
                        'view_index': best_view['view_index']
                    },
                    'bounding_box': {
                        'center': [center_x, center_y, center_z],
                        'size': [size_x, size_y, size_z],
                        'min': [min_x, min_y, min_z],
                        'max': [max_x, max_y, max_z]
                    }
                }
            else:
                raise ValueError("Failed to find a suitable viewpoint")
                
        except Exception as e:
            logging.error(f"add_viewpoint failed: {e}")
            raise e

    def add_keyframe(self, keyframe_type: str = "next", round_num: int = 1) -> dict:
        """
        改变场景到另一个关键帧进行观察
        
        Args:
            keyframe_type: 关键帧类型 ("next", "previous", "first", "last", 或具体的帧号)
            round_num: 轮次编号
            
        Returns:
            dict: 包含渲染结果的字典
        """
        try:
            # 获取当前场景
            scene = bpy.context.scene
            
            # 获取当前帧号
            current_frame = scene.frame_current
            
            # 根据类型确定目标帧号
            if keyframe_type == "next":
                # 找到下一个关键帧
                target_frame = current_frame + 1
                # 查找动画中的下一个关键帧
                for obj in bpy.data.objects:
                    if obj.animation_data and obj.animation_data.action:
                        for fcurve in obj.animation_data.action.fcurves:
                            for keyframe in fcurve.keyframe_points:
                                if keyframe.co[0] > current_frame:
                                    target_frame = min(target_frame, int(keyframe.co[0]))
            elif keyframe_type == "previous":
                # 找到上一个关键帧
                target_frame = current_frame - 1
                # 查找动画中的上一个关键帧
                for obj in bpy.data.objects:
                    if obj.animation_data and obj.animation_data.action:
                        for fcurve in obj.animation_data.action.fcurves:
                            for keyframe in fcurve.keyframe_points:
                                if keyframe.co[0] < current_frame:
                                    target_frame = max(target_frame, int(keyframe.co[0]))
            elif keyframe_type == "first":
                # 第一个关键帧
                target_frame = scene.frame_start
                for obj in bpy.data.objects:
                    if obj.animation_data and obj.animation_data.action:
                        for fcurve in obj.animation_data.action.fcurves:
                            if fcurve.keyframe_points:
                                target_frame = max(target_frame, int(fcurve.keyframe_points[0].co[0]))
            elif keyframe_type == "last":
                # 最后一个关键帧
                target_frame = scene.frame_end
                for obj in bpy.data.objects:
                    if obj.animation_data and obj.animation_data.action:
                        for fcurve in obj.animation_data.action.fcurves:
                            if fcurve.keyframe_points:
                                target_frame = min(target_frame, int(fcurve.keyframe_points[-1].co[0]))
            else:
                # 尝试解析为具体的帧号
                try:
                    target_frame = int(keyframe_type)
                except ValueError:
                    raise ValueError(f"Invalid keyframe type: {keyframe_type}")
            
            # 确保目标帧在有效范围内
            target_frame = max(scene.frame_start, min(scene.frame_end, target_frame))
            
            # 设置到目标帧
            scene.frame_set(target_frame)
            
            logging.info(f"Changed to keyframe {target_frame} (was {current_frame})")
            
            # 渲染当前帧
            render_result = self._render(round_num)
            
            return {
                'status': 'success',
                'image': render_result['image_path'],
                'camera_position': render_result['camera_position'],
                'keyframe_info': {
                    'previous_frame': current_frame,
                    'current_frame': target_frame,
                    'keyframe_type': keyframe_type
                }
            }
            
        except Exception as e:
            logging.error(f"add_keyframe failed: {e}")
            raise e


# ======================
# MCP 工具
# ======================

@mcp.tool()
def get_scene_info(blender_path: str) -> dict:
    """
    获取 Blender 场景信息，包括对象、材质、灯光、相机和渲染设置。
    """
    try:
        info = GetSceneInfo(blender_path).get_info()
        return {"status": "success", "info": info}
    except Exception as e:
        logging.error(f"Failed to get scene info: {e}")
        return {"status": "error", "error": str(e)}

@mcp.tool()
def initialize_investigator(args: dict) -> dict:
    """
    初始化 3D 场景调查工具。
    """
    global _investigator
    try:
        _investigator = Investigator3D(args.get("thought_save"), str(args.get("blender_file")))
        return {"status": "success", "message": "Investigator3D initialized successfully"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@mcp.tool()
def focus(object_name: str, round_num: int) -> dict:
    """
    Focus the camera on a specific object in the 3D scene.
    
    Args:
        object_name: Name of the object to focus on (must exist in the scene)
        round_num: Current round number for file organization
        
    Returns:
        dict: Status, rendered image path, and camera position information
        
    Example:
        focus(object_name="Cube", round_num=1)
        # Focuses camera on the object named "Cube" and renders the view
        
    Detailed Description:
        This tool automatically positions the camera to focus on the specified object
        using a track-to constraint. The camera will orbit around the object at a 
        fixed distance, allowing you to examine the object from different angles.
        The camera maintains a consistent distance and automatically adjusts its
        orientation to keep the target object centered in the view.
        
    Best Practices:
        - Always call this tool first before using zoom or move operations
        - Use object names exactly as they appear in Blender (case-sensitive)
        - This tool is ideal for examining specific objects in detail
    """
    global _investigator
    if _investigator is None:
        return {"status": "error", "error": "Investigator3D not initialized. Call initialize_investigator first."}

    try:
        # 检查目标对象是否存在
        obj = bpy.data.objects.get(object_name)
        if not obj:
            return {"status": "error", "error": f"Object '{object_name}' not found in scene"}

        result = _investigator.focus_on_object(object_name, round_num)
        return {
            "status": "success", 
            "image": result["image_path"],
            "camera_position": result["camera_position"]
        }
    except Exception as e:
        logging.error(f"Focus failed: {e}")
        return {"status": "error", "error": str(e)}

@mcp.tool()
def zoom(direction: str, round_num: int) -> dict:
    """
    Zoom the camera in or out from the current target object.
    
    Args:
        direction: Zoom direction - "in" (closer to object) or "out" (farther from object)
        round_num: Current round number for file organization
        
    Returns:
        dict: Status, rendered image path, and camera position information
        
    Example:
        zoom(direction="in", round_num=1)
        # Moves camera closer to the target object for detailed examination
        
    Detailed Description:
        This tool adjusts the camera distance from the currently focused object.
        When zooming "in", the camera moves closer to the object, allowing for
        detailed examination of specific parts. When zooming "out", the camera
        moves farther away, providing a broader view of the scene context.
        
    Best Practices:
        - Use "in" for examining small details or specific object features
        - Use "out" for understanding spatial relationships and overall composition
        - Always call focus() first to establish a target object
        - Avoid extreme zoom levels that may cause rendering issues
    """
    global _investigator
    if _investigator is None:
        return {"status": "error", "error": "Investigator3D not initialized. Call initialize_investigator first."}

    try:
        # 检查是否有目标对象
        if _investigator.target is None:
            return {"status": "error", "error": "No target object set. Call focus first."}

        result = _investigator.zoom(direction, round_num)
        return {
            "status": "success", 
            "image": result["image_path"],
            "camera_position": result["camera_position"]
        }
    except Exception as e:
        logging.error(f"Zoom failed: {e}")
        return {"status": "error", "error": str(e)}

@mcp.tool()
def move(direction: str, round_num: int) -> dict:
    """
    Move the camera around the current target object in spherical coordinates.
    
    Args:
        direction: Movement direction - "up", "down", "left", or "right"
        round_num: Current round number for file organization
        
    Returns:
        dict: Status, rendered image path, and camera position information
        
    Example:
        move(direction="left", round_num=1)
        # Rotates camera around the target object to the left
        
    Detailed Description:
        This tool moves the camera in spherical coordinates around the currently
        focused object. The camera maintains a fixed distance from the target
        while rotating around it. This allows you to examine the object from
        different angles while keeping it centered in the view.
        
        Movement directions:
        - "up": Rotate camera upward around the object
        - "down": Rotate camera downward around the object  
        - "left": Rotate camera left around the object
        - "right": Rotate camera right around the object
        
    Best Practices:
        - Always call focus() first to establish a target object
        - Use this tool to examine objects from multiple angles
        - Combine with zoom() to get both angle and distance control
        - Avoid extreme angles that may cause disorientation
    """
    global _investigator
    if _investigator is None:
        return {"status": "error", "error": "Investigator3D not initialized. Call initialize_investigator first."}

    try:
        # 检查是否有目标对象
        if _investigator.target is None:
            return {"status": "error", "error": "No target object set. Call focus first."}

        result = _investigator.move_camera(direction, round_num)
        return {
            "status": "success", 
            "image": result["image_path"],
            "camera_position": result["camera_position"]
        }
    except Exception as e:
        logging.error(f"Move failed: {e}")
        return {"status": "error", "error": str(e)}

@mcp.tool()
def add_viewpoint(object_names: list, round_num: int) -> dict:
    """
    添加视角：输入对象列表，计算其边界框并在四个上角放置相机，选择最佳视角。
    
    Args:
        object_names: 要观察的对象名称列表
        round_num: 轮次编号
        
    Returns:
        dict: 包含最佳视角渲染结果的字典
    """
    global _investigator
    if _investigator is None:
        return {"status": "error", "error": "Investigator3D not initialized. Call initialize_investigator first."}

    try:
        result = _investigator.add_viewpoint(object_names, round_num)
        return result
    except Exception as e:
        logging.error(f"Add viewpoint failed: {e}")
        return {"status": "error", "error": str(e)}

@mcp.tool()
def set_camera_starting_position(direction: str = "z", round_num: int = 0) -> dict:
    """
    Set the camera to a fixed starting position for 3D scene investigation.
    
    Args:
        direction: Starting camera direction - "z" (from above), "x" (from side), "y" (from front), or "bbox" (above bounding box)
        round_num: Current round number for file organization
        
    Returns:
        dict: Status and camera position information
        
    Example:
        set_camera_starting_position(direction="z", round_num=1)
        # Sets camera to look down from above the scene
        
    Detailed Description:
        This tool sets the camera to predefined starting positions to ensure consistent 
        scene investigation. The available directions are:
        - "z": Camera positioned at (0,0,5) looking down at 60 degrees
        - "x": Camera positioned at (-5,0,2) looking from the side
        - "y": Camera positioned at (0,-5,2) looking from the front  
        - "bbox": Camera positioned at (0,0,10) looking down from above bounding box
    """
    global _investigator
    if _investigator is None:
        return {"status": "error", "error": "Investigator3D not initialized. Call initialize_investigator first."}
    
    try:
        _investigator._set_camera_to_position(_investigator.cam, direction)
        result = _investigator._render(round_num)
        return {
            "status": "success",
            "message": f"Camera set to {direction} starting position",
            "image": result["image_path"],
            "camera_position": result["camera_position"]
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@mcp.tool()
def add_keyframe(keyframe_type: str, round_num: int) -> dict:
    """
    添加关键帧：改变场景到另一个关键帧进行观察。
    
    Args:
        keyframe_type: 关键帧类型，支持 "next", "previous", "first", "last", 或具体的帧号
        round_num: 轮次编号
        
    Returns:
        dict: 包含渲染结果的字典
    """
    global _investigator
    if _investigator is None:
        return {"status": "error", "error": "Investigator3D not initialized. Call initialize_investigator first."}

    try:
        result = _investigator.add_keyframe(keyframe_type, round_num)
        return result
    except Exception as e:
        logging.error(f"Add keyframe failed: {e}")
        return {"status": "error", "error": str(e)}




# ======================
# 入口与测试
# ======================

def main():
    # 检查是否直接运行此脚本（用于测试）
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("Running blender_server.py tools test...")
        test_tools()
    else:
        # 正常运行 MCP 服务器
        mcp.run(transport="stdio")

def test_tools():
    """测试所有工具函数（包含 Meshy 生成→导入 流程）"""
    print("=" * 50)
    print("Testing Scene Tools")
    print("=" * 50)

    # 设置测试路径
    blender_file = "output/demo/blendergym_hard/20250924_132209/blender_file.blend"
    test_save_dir = "output/test/scene_test"

    # 检查 blender 文件是否存在
    if not os.path.exists(blender_file):
        print(f"⚠ Blender file not found: {blender_file}")
        print("Skipping all tests.")
        return

    print(f"✓ Using blender file: {blender_file}")

    # 测试 1: 获取场景信息
    print("\n1. Testing get_scene_info...")
    try:
        result = get_scene_info(blender_file)
        print(f"Result: {result}")
        if result.get("status") == "success":
            print("✓ get_scene_info passed")
            info = result.get("info", {})
            # print(f"  - Objects: {len(info.get('objects', []))}")
            # print(f"  - Materials: {len(info.get('materials', []))}")
            # print(f"  - Lights: {len(info.get('lights', []))}")
            print(f"  - Cameras: {len(info.get('cameras', []))}")

            # 获取第一个对象名称用于后续测试
            objects = info.get("objects", [])
            if not objects:
                print("⚠ No objects found in scene, skipping camera tests")
                # 继续 Meshy 测试
                first_object = None
            else:
                first_object = 'Chair_Rig'
                print(f"  - Will focus on: {first_object}")
        else:
            print("✗ get_scene_info failed")
            first_object = None
    except Exception as e:
        print(f"✗ get_scene_info failed with exception: {e}")
        first_object = None

    # 测试 2: 初始化调查工具
    print("\n2. Testing initialize_investigator...")
    try:
        args = {"thought_save": test_save_dir, "blender_file": blender_file}
        result = initialize_investigator(args)
        if result.get("status") == "success":
            print("✓ initialize_investigator passed")
        else:
            print("✗ initialize_investigator failed")
    except Exception as e:
        print(f"✗ initialize_investigator failed with exception: {e}")

    # 测试 3: 聚焦对象（如果有对象）
    if first_object:
        print("\n3. Testing focus...")
        try:
            result = focus(object_name=first_object, round_num=1)
            print(f"Result: {result}")
            if result.get("status") == "success":
                print("✓ focus passed")
                print(f"  - Focused on: {first_object}")
                print(f"  - Image saved: {result.get('image', 'N/A')}")
            else:
                print("✗ focus failed")
        except Exception as e:
            print(f"✗ focus failed with exception: {e}")

        # 测试 4: 缩放功能
        print("\n4. Testing zoom...")
        try:
            result = zoom(direction="in", round_num=1)
            print(f"Result: {result}")
            if result.get("status") == "success":
                print("✓ zoom passed")
                print(f"  - Image saved: {result.get('image', 'N/A')}")
            else:
                print("✗ zoom failed")
        except Exception as e:
            print(f"✗ zoom failed with exception: {e}")

        # 测试 5: 移动功能
        print("\n5. Testing move...")
        try:
            result = move(direction="up", round_num=1)
            print(f"Result: {result}")
            if result.get("status") == "success":
                print("✓ move passed")
                print(f"  - Image saved: {result.get('image', 'N/A')}")
            else:
                print("✗ move failed")
        except Exception as e:
            print(f"✗ move failed with exception: {e}")

        # 测试 6: 添加视角功能
        print("\n6. Testing add_viewpoint...")
        try:
            # 使用第一个对象进行测试
            test_objects = [first_object] if first_object else ['Chair_Rig']
            result = add_viewpoint(object_names=test_objects, round_num=1)
            print(f"Result: {result}")
            if result.get("status") == "success":
                print("✓ add_viewpoint passed")
                print(f"  - Image saved: {result.get('image', 'N/A')}")
                print(f"  - Best viewpoint: {result.get('best_viewpoint', {}).get('view_index', 'N/A')}")
                print(f"  - Score: {result.get('best_viewpoint', {}).get('score', 'N/A')}")
            else:
                print("✗ add_viewpoint failed")
        except Exception as e:
            print(f"✗ add_viewpoint failed with exception: {e}")

        # 测试 7: 添加关键帧功能
        print("\n7. Testing add_keyframe...")
        try:
            result = add_keyframe(keyframe_type="next", round_num=1)
            print(f"Result: {result}")
            if result.get("status") == "success":
                print("✓ add_keyframe passed")
                print(f"  - Image saved: {result.get('image', 'N/A')}")
                print(f"  - Frame changed from {result.get('keyframe_info', {}).get('previous_frame', 'N/A')} to {result.get('keyframe_info', {}).get('current_frame', 'N/A')}")
            else:
                print("✗ add_keyframe failed")
        except Exception as e:
            print(f"✗ add_keyframe failed with exception: {e}")



    print("\n" + "=" * 50)
    print("Test completed!")
    print("=" * 50)
    print(f"\nTest files saved to: {test_save_dir}")
    print("\nTo run the MCP server normally, use:")
    print("python blender_server.py")
    print("\nTo run tests, use:")
    print("python blender_server.py --test")


if __name__ == "__main__":
    main()
