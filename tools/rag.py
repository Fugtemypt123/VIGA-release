# rag.py
import os
import re
import json
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import requests
from bs4 import BeautifulSoup

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None


class BlenderInfinigenRAG:
    """RAG工具：根据指令查找bpy和Infinigen相关文档并生成代码示例"""
    
    def __init__(self, openai_api_key: str = None):
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if self.openai_api_key and OPENAI_AVAILABLE:
            self.openai_client = OpenAI(api_key=self.openai_api_key)
        else:
            self.openai_client = None
            if not OPENAI_AVAILABLE:
                logging.warning("OpenAI library not available. Enhanced generation disabled.")
            elif not self.openai_api_key:
                logging.warning("OpenAI API key not provided. Enhanced generation disabled.")
        
        # 预定义的文档知识库
        self.knowledge_base = self._build_knowledge_base()
        
        # 指令模式匹配
        self.instruction_patterns = {
            'physics_placement': [
                r'物理.*放置|遵循物理.*放置|物理规律.*放置',
                r'rigid.*body|刚体|物理.*模拟',
                r'gravity|重力|碰撞|collision'
            ],
            'object_creation': [
                r'创建.*物体|添加.*物体|生成.*物体',
                r'primitive|基础.*形状|mesh.*add'
            ],
            'lighting': [
                r'光照|照明|light|shadow|阴影',
                r'材质|material|texture|贴图'
            ],
            'animation': [
                r'动画|animation|keyframe|关键帧',
                r'motion|运动|transform|变换'
            ],
            'scene_setup': [
                r'场景.*设置|scene.*setup|环境|environment',
                r'camera|相机|渲染|render'
            ]
        }
    
    def _build_knowledge_base(self) -> Dict:
        """构建bpy和Infinigen的知识库"""
        return {
            'bpy_physics': {
                'title': 'Blender Python Physics API',
                'apis': [
                    {
                        'name': 'bpy.ops.rigidbody.object_add',
                        'description': '为对象添加刚体物理属性',
                        'example': 'bpy.ops.rigidbody.object_add(type=\'ACTIVE\')',
                        'use_case': '使对象受物理规律影响'
                    },
                    {
                        'name': 'bpy.ops.rigidbody.world_add',
                        'description': '添加物理世界',
                        'example': 'bpy.ops.rigidbody.world_add()',
                        'use_case': '创建物理模拟环境'
                    },
                    {
                        'name': 'bpy.context.scene.rigidbody_world.gravity',
                        'description': '设置重力',
                        'example': 'bpy.context.scene.rigidbody_world.gravity = (0, 0, -9.81)',
                        'use_case': '调整重力参数'
                    }
                ]
            },
            'bpy_objects': {
                'title': 'Blender Python Object Creation API',
                'apis': [
                    {
                        'name': 'bpy.ops.mesh.primitive_cube_add',
                        'description': '创建立方体',
                        'example': 'bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))',
                        'use_case': '创建基础几何体'
                    },
                    {
                        'name': 'bpy.ops.mesh.primitive_uv_sphere_add',
                        'description': '创建球体',
                        'example': 'bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 0))',
                        'use_case': '创建球形物体'
                    },
                    {
                        'name': 'bpy.ops.mesh.primitive_plane_add',
                        'description': '创建平面',
                        'example': 'bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))',
                        'use_case': '创建地面或平台'
                    }
                ]
            },
            'infinigen_physics': {
                'title': 'Infinigen Physics Utilities',
                'apis': [
                    {
                        'name': 'infinigen.core.placement.placement',
                        'description': '智能物体放置系统',
                        'example': 'placement.place_object(obj, surface, physics=True)',
                        'use_case': '遵循物理规律的物体放置'
                    },
                    {
                        'name': 'infinigen.core.placement.surface',
                        'description': '表面检测和放置',
                        'example': 'surface.find_surface_point(location, radius)',
                        'use_case': '在表面上放置物体'
                    },
                    {
                        'name': 'infinigen.core.physics.rigidbody',
                        'description': '刚体物理设置',
                        'example': 'rigidbody.setup_rigidbody(obj, mass=1.0)',
                        'use_case': '设置物体物理属性'
                    }
                ]
            },
            'infinigen_scene': {
                'title': 'Infinigen Scene Generation',
                'apis': [
                    {
                        'name': 'infinigen.core.scene.scene',
                        'description': '场景生成和管理',
                        'example': 'scene.add_objects(objects, placement_strategy="physics")',
                        'use_case': '创建物理真实的场景'
                    },
                    {
                        'name': 'infinigen.core.lighting.lighting',
                        'description': '智能光照设置',
                        'example': 'lighting.setup_natural_lighting(scene)',
                        'use_case': '设置真实的光照效果'
                    }
                ]
            }
        }
    
    def parse_instruction(self, instruction: str) -> Dict:
        """解析用户指令，提取关键信息"""
        instruction_lower = instruction.lower()
        
        # 识别指令类型
        instruction_type = None
        for category, patterns in self.instruction_patterns.items():
            for pattern in patterns:
                if re.search(pattern, instruction_lower):
                    instruction_type = category
                    break
            if instruction_type:
                break
        
        # 提取物体类型
        object_types = ['立方体', '球体', '平面', '圆柱体', 'cube', 'sphere', 'plane', 'cylinder']
        detected_objects = []
        for obj_type in object_types:
            if obj_type.lower() in instruction_lower:
                detected_objects.append(obj_type)
        
        # 提取位置信息
        position_match = re.search(r'位置.*?\(([^)]+)\)|location.*?\(([^)]+)\)', instruction_lower)
        position = None
        if position_match:
            pos_str = position_match.group(1) or position_match.group(2)
            try:
                # 尝试解析坐标
                coords = [float(x.strip()) for x in pos_str.split(',')]
                if len(coords) >= 3:
                    position = tuple(coords[:3])
            except:
                position = None
        
        # 提取物理相关参数
        physics_params = {}
        if re.search(r'重力|gravity', instruction_lower):
            gravity_match = re.search(r'重力.*?(\d+\.?\d*)', instruction_lower)
            if gravity_match:
                physics_params['gravity'] = float(gravity_match.group(1))
        
        if re.search(r'质量|mass', instruction_lower):
            mass_match = re.search(r'质量.*?(\d+\.?\d*)', instruction_lower)
            if mass_match:
                physics_params['mass'] = float(mass_match.group(1))
        
        return {
            'instruction_type': instruction_type,
            'objects': detected_objects,
            'position': position,
            'physics_params': physics_params,
            'original_instruction': instruction
        }
    
    def search_knowledge_base(self, parsed_instruction: Dict) -> List[Dict]:
        """在知识库中搜索相关信息"""
        results = []
        instruction_type = parsed_instruction.get('instruction_type')
        
        # 根据指令类型搜索相关知识
        if instruction_type == 'physics_placement':
            results.extend(self.knowledge_base['bpy_physics']['apis'])
            results.extend(self.knowledge_base['infinigen_physics']['apis'])
        
        if instruction_type == 'object_creation':
            results.extend(self.knowledge_base['bpy_objects']['apis'])
        
        if instruction_type == 'scene_setup':
            results.extend(self.knowledge_base['infinigen_scene']['apis'])
        
        # 如果没有特定类型匹配，搜索所有相关API
        if not results:
            for category in self.knowledge_base.values():
                results.extend(category['apis'])
        
        return results
    
    def generate_code_example(self, parsed_instruction: Dict, relevant_apis: List[Dict]) -> str:
        """生成代码示例"""
        instruction_type = parsed_instruction.get('instruction_type')
        objects = parsed_instruction.get('objects', ['cube'])
        position = parsed_instruction.get('position', (0, 0, 0))
        physics_params = parsed_instruction.get('physics_params', {})
        
        code_lines = ["import bpy", "import bmesh", ""]
        
        # 根据指令类型生成相应的代码
        if instruction_type == 'physics_placement':
            code_lines.extend([
                "# 设置物理世界",
                "bpy.ops.rigidbody.world_add()",
                ""
            ])
            
            # 设置重力
            gravity = physics_params.get('gravity', -9.81)
            code_lines.extend([
                "# 设置重力",
                f"bpy.context.scene.rigidbody_world.gravity = (0, 0, {gravity})",
                ""
            ])
            
            # 创建物体
            for obj_name in objects:
                if 'cube' in obj_name.lower() or '立方体' in obj_name:
                    code_lines.extend([
                        "# 创建立方体",
                        f"bpy.ops.mesh.primitive_cube_add(size=2, location={position})",
                        ""
                    ])
                elif 'sphere' in obj_name.lower() or '球体' in obj_name:
                    code_lines.extend([
                        "# 创建球体",
                        f"bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location={position})",
                        ""
                    ])
                elif 'plane' in obj_name.lower() or '平面' in obj_name:
                    code_lines.extend([
                        "# 创建平面",
                        f"bpy.ops.mesh.primitive_plane_add(size=10, location={position})",
                        ""
                    ])
            
            # 添加刚体物理
            mass = physics_params.get('mass', 1.0)
            code_lines.extend([
                "# 为物体添加刚体物理属性",
                f"bpy.ops.rigidbody.object_add(type='ACTIVE')",
                f"bpy.context.object.rigid_body.mass = {mass}",
                ""
            ])
            
        elif instruction_type == 'object_creation':
            for obj_name in objects:
                if 'cube' in obj_name.lower() or '立方体' in obj_name:
                    code_lines.extend([
                        "# 创建立方体",
                        f"bpy.ops.mesh.primitive_cube_add(size=2, location={position})",
                        ""
                    ])
                elif 'sphere' in obj_name.lower() or '球体' in obj_name:
                    code_lines.extend([
                        "# 创建球体",
                        f"bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location={position})",
                        ""
                    ])
        
        # 添加注释说明使用的API
        if relevant_apis:
            code_lines.extend([
                "# 相关API文档:",
            ])
            for api in relevant_apis[:3]:  # 只显示前3个
                code_lines.append(f"# {api['name']}: {api['description']}")
        
        return "\n".join(code_lines)
    
    def enhanced_generation(self, instruction: str) -> str:
        """使用OpenAI增强代码生成（如果可用）"""
        if not self.openai_client:
            return "OpenAI API not available for enhanced generation"
        
        try:
            parsed = self.parse_instruction(instruction)
            relevant_apis = self.search_knowledge_base(parsed)
            
            # 构建prompt
            api_info = "\n".join([f"- {api['name']}: {api['description']}" for api in relevant_apis[:5]])
            
            prompt = f"""
基于以下用户指令和相关API信息，生成Blender Python代码：

用户指令: {instruction}

相关API:
{api_info}

要求:
1. 生成完整的、可执行的Blender Python代码
2. 包含必要的导入语句
3. 添加详细的中文注释
4. 确保代码遵循Blender Python API最佳实践

请只返回代码，不要额外的解释。
"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logging.error(f"Enhanced generation failed: {e}")
            return f"Enhanced generation failed: {str(e)}"
    
    def rag_query(self, instruction: str, use_enhanced: bool = False) -> Dict:
        """主要的RAG查询函数"""
        try:
            # 解析指令
            parsed_instruction = self.parse_instruction(instruction)
            
            # 搜索相关知识
            relevant_apis = self.search_knowledge_base(parsed_instruction)
            
            # 生成代码示例
            if use_enhanced and self.openai_client:
                code_example = self.enhanced_generation(instruction)
            else:
                code_example = self.generate_code_example(parsed_instruction, relevant_apis)
            
            return {
                'status': 'success',
                'instruction': instruction,
                'parsed_instruction': parsed_instruction,
                'relevant_apis': relevant_apis,
                'code_example': code_example,
                'generation_method': 'enhanced' if use_enhanced else 'template'
            }
            
        except Exception as e:
            logging.error(f"RAG query failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'instruction': instruction
            }


# 全局实例
_rag_tool = None


def initialize_rag_tool(openai_api_key: str = None):
    """初始化RAG工具"""
    global _rag_tool
    _rag_tool = BlenderInfinigenRAG(openai_api_key)
    return _rag_tool


def rag_query(instruction: str, use_enhanced: bool = False) -> Dict:
    """RAG查询接口"""
    global _rag_tool
    if _rag_tool is None:
        _rag_tool = BlenderInfinigenRAG()
    
    return _rag_tool.rag_query(instruction, use_enhanced)


# MCP 工具接口
try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("rag-tool")
    
    @mcp.tool()
    def rag_query_tool(instruction: str, use_enhanced: bool = False) -> dict:
        """
        根据输入的指令查找bpy和Infinigen中相关的文档并生成代码示例
        
        Args:
            instruction: 用户指令，例如"要遵循物理规律地放置某个物体"
            use_enhanced: 是否使用OpenAI增强生成（需要OpenAI API key）
            
        Returns:
            dict: 包含解析结果、相关API和生成代码的字典
        """
        return rag_query(instruction, use_enhanced)
    
    @mcp.tool()
    def initialize_rag_tool(openai_api_key: str = None) -> dict:
        """
        初始化RAG工具
        
        Args:
            openai_api_key: OpenAI API密钥（可选）
            
        Returns:
            dict: 初始化结果
        """
        try:
            global _rag_tool
            _rag_tool = BlenderInfinigenRAG(openai_api_key)
            return {"status": "success", "message": "RAG tool initialized successfully"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def main():
        """运行MCP服务器"""
        mcp.run(transport="stdio")
        
except ImportError:
    # 如果没有MCP库，提供简单的命令行接口
    def main():
        print("MCP library not available. Running in standalone mode.")
        print("Use the BlenderInfinigenRAG class directly.")
        
        # 示例使用
        rag = BlenderInfinigenRAG()
        
        # 测试示例
        test_instructions = [
            "要遵循物理规律地放置一个立方体",
            "创建一个球体并设置物理属性",
            "在位置(1, 2, 3)创建一个平面作为地面",
            "设置重力为-10，质量为2.0的物理模拟"
        ]
        
        for instruction in test_instructions:
            print(f"\n指令: {instruction}")
            print("=" * 50)
            result = rag.rag_query(instruction)
            if result['status'] == 'success':
                print("生成的代码:")
                print(result['code_example'])
            else:
                print(f"错误: {result['error']}")


if __name__ == "__main__":
    main()
