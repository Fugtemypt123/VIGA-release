import os
import base64
import io
import re
import sys
import traceback
from io import StringIO
from PIL import Image, ImageChops, ImageEnhance
import numpy as np
from typing import Dict, List
from mcp.server.fastmcp import FastMCP
import logging
from openai import OpenAI

# 创建全局 MCP 实例
mcp = FastMCP("image-generate-server")

# 全局工具实例
_image_tool = None
_pil_executor = None

class PILExecutor:
    def __init__(self):
        self._setup_environment()

    def _setup_environment(self):
        self.globals = {
            'Image': Image,
            'io': io,
            'base64': base64,
            'current_image': None,
            'result': None
        }

    def _image_to_base64(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def execute(self, code: str) -> Dict:
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout_capture, stderr_capture

        try:
            exec(code, self.globals)
            result = self.globals.get('result', None)
            if isinstance(result, Image.Image):
                result = self._image_to_base64(result)
            return {
                'success': True,
                'result': result,
                'stdout': stdout_capture.getvalue(),
                'stderr': stderr_capture.getvalue()
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'stdout': stdout_capture.getvalue(),
                'stderr': stderr_capture.getvalue() + traceback.format_exc()
            }
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr

class ImageGenerationTool:
    def __init__(self, vision_model: str = "gpt-4o", api_key: str = None, api_base_url: str = None):
        self.model = vision_model
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("OpenAI API key must be provided.")
        # Allow overriding OpenAI-compatible base URL (e.g., Azure, local proxy)
        self.api_base_url = api_base_url or "https://api.openai.com/v1"
        self.client = OpenAI(api_key=self.api_key, base_url=self.api_base_url)

    def pil_to_base64(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def generate_scene_description(self, image_path: str) -> str:
        """根据输入图像生成场景描述"""
        img = Image.open(image_path).convert("RGB")
        b64_image = self.pil_to_base64(img)
        
        image_type = 'png' if image_path.endswith('png') else 'jpeg'
        
        messages = [
            {"role": "system", "content": "You are an expert in scene analysis and description. Analyze the given image and provide a detailed scene description that could be used for 3D scene generation or rendering. Focus on the main objects, lighting, composition, and overall atmosphere."},
            {"role": "user", "content": [
                {"type": "text", "text": "Please analyze this image and provide a detailed scene description that includes:\n1. Main objects and their positions\n2. Lighting conditions and atmosphere\n3. Color palette and mood\n4. Composition and perspective\n5. Any specific details that would be important for recreating this scene"},
                {"type": "image_url", "image_url": {"url": f"data:image/{image_type};base64,{b64_image}"}},
            ]}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024
        )
        return response.choices[0].message.content

    def generate_initialization_suggestions(self, image_path: str) -> str:
        """根据输入图像生成初始化建议"""
        img = Image.open(image_path).convert("RGB")
        b64_image = self.pil_to_base64(img)
        
        image_type = 'png' if image_path.endswith('png') else 'jpeg'
        
        messages = [
            {"role": "system", "content": "You are an expert in 3D scene initialization and setup. Analyze the given image and provide specific initialization suggestions for creating a 3D scene that matches this image. Focus on technical parameters, setup steps, and configuration recommendations."},
            {"role": "user", "content": [
                {"type": "text", "text": "Based on this reference image, please provide detailed initialization suggestions for a 3D scene setup including:\n1. Camera position and angle\n2. Lighting setup and parameters\n3. Material properties and textures\n4. Object placement and scale\n5. Rendering settings and parameters\n6. Any specific tools or techniques recommended"},
                {"type": "image_url", "image_url": {"url": f"data:image/{image_type};base64,{b64_image}"}},
            ]}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024
        )
        return response.choices[0].message.content

@mcp.tool()
def initialize_generator(args: dict) -> dict:
    """
    初始化ImageGenerationTool，设置api_key。
    """
    global _image_tool
    try:
        _image_tool = ImageGenerationTool(vision_model=args.get("vision_model"), api_key=args.get("api_key"), api_base_url=args.get("api_base_url"))
        return {"status": "success", "message": "ImageGenerationTool initialized with api_key."}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@mcp.tool()
def exec_pil_code(code: str) -> dict:
    """
    执行传入的 PIL Python 代码，并返回执行结果。
    """
    global _pil_executor
    if _pil_executor is None:
        _pil_executor = PILExecutor()
    
    try:
        result = _pil_executor.execute(code)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@mcp.tool()
def generate_scene_description(image_path: str) -> dict:
    """
    根据输入图像生成详细的场景描述。
    需要先调用 initialize_generator 进行初始化。
    """
    global _image_tool
    if _image_tool is None:
        return {"status": "error", "error": "ImageGenerationTool not initialized. Call initialize_generator first."}
    
    try:
        result = _image_tool.generate_scene_description(image_path)
        return {"status": "success", "description": result}
    except Exception as e:
        logging.error(f"Scene description generation failed: {e}")
        return {"status": "error", "error": str(e)}

@mcp.tool()
def generate_initialization_suggestions(image_path: str) -> dict:
    """
    根据输入图像生成初始化建议。
    需要先调用 initialize_generator 进行初始化。
    """
    global _image_tool
    if _image_tool is None:
        return {"status": "error", "error": "ImageGenerationTool not initialized. Call initialize_generator first."}
    
    try:
        result = _image_tool.generate_initialization_suggestions(image_path)
        return {"status": "success", "suggestions": result}
    except Exception as e:
        logging.error(f"Initialization suggestions generation failed: {e}")
        return {"status": "error", "error": str(e)}

def main():
    # 检查是否直接运行此脚本（用于测试）
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("Running init_generate.py tools test...")
        test_tools()
    else:
        # 正常运行 MCP 服务器
        mcp.run(transport="stdio")

def test_tools():
    """测试所有工具函数"""
    print("=" * 50)
    print("Testing Image Generation Tools")
    print("=" * 50)
    
    # 测试 1: 初始化生成器
    print("\n1. Testing initialize_generator...")
    try:
        # 尝试从环境变量获取 API key，如果没有则使用测试 key
        api_key = os.getenv("OPENAI_API_KEY", "test_key_for_testing")
        result = initialize_generator({"api_key": api_key})
        print(f"Result: {result}")
        if result.get("status") == "success":
            print("✓ initialize_generator passed")
        else:
            print("✗ initialize_generator failed")
    except Exception as e:
        print(f"✗ initialize_generator failed with exception: {e}")
    
    # 测试 2: 执行 PIL 代码
    print("\n2. Testing exec_pil_code...")
    try:
        # 创建一个简单的测试图像
        test_code = """
from PIL import Image
import numpy as np

# 创建一个简单的测试图像
img = Image.new('RGB', (100, 100), color='red')
result = img
"""
        result = exec_pil_code(test_code)
        print(f"Result: {result}")
        if result.get("status") == "success":
            print("✓ exec_pil_code passed")
        else:
            print("✗ exec_pil_code failed")
    except Exception as e:
        print(f"✗ exec_pil_code failed with exception: {e}")
    
    # 测试 3: 生成场景描述（需要测试图像文件）
    print("\n3. Testing generate_scene_description...")
    try:
        # 创建测试图像文件
        test_img = Image.new('RGB', (200, 200), color='blue')
        test_path = "/tmp/test_scene.png"
        test_img.save(test_path)
        
        # 只有在有有效 API key 时才测试场景描述生成
        if os.getenv("OPENAI_API_KEY"):
            result = generate_scene_description(test_path)
            print(f"Result: {result}")
            if result.get("status") == "success":
                print("✓ generate_scene_description passed")
            else:
                print("✗ generate_scene_description failed")
        else:
            print("⚠ Skipping generate_scene_description test (no OPENAI_API_KEY)")
        
        # 清理测试文件
        if os.path.exists(test_path):
            os.remove(test_path)
            
    except Exception as e:
        print(f"✗ generate_scene_description failed with exception: {e}")
    
    # 测试 4: 生成初始化建议
    print("\n4. Testing generate_initialization_suggestions...")
    try:
        # 创建测试图像文件
        test_img = Image.new('RGB', (200, 200), color='green')
        test_path = "/tmp/test_init.png"
        test_img.save(test_path)
        
        # 只有在有有效 API key 时才测试初始化建议生成
        if os.getenv("OPENAI_API_KEY"):
            result = generate_initialization_suggestions(test_path)
            print(f"Result: {result}")
            if result.get("status") == "success":
                print("✓ generate_initialization_suggestions passed")
            else:
                print("✗ generate_initialization_suggestions failed")
        else:
            print("⚠ Skipping generate_initialization_suggestions test (no OPENAI_API_KEY)")
        
        # 清理测试文件
        if os.path.exists(test_path):
            os.remove(test_path)
            
    except Exception as e:
        print(f"✗ generate_initialization_suggestions failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print("Test completed!")
    print("=" * 50)
    print("\nTo run the MCP server normally, use:")
    print("python init_generate.py")
    print("\nTo run tests, use:")
    print("python init_generate.py --test")

if __name__ == "__main__":
    main()

