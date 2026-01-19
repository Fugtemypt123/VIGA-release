# Tools

MCP (Model Context Protocol) tool servers for VIGA agents.

## Directory Structure

```
tools/
├── generator_base.py      # Generator agent tools
├── verifier_base.py       # Verifier agent tools
├── initialize_plan.py     # Planning tools
│
├── blender/               # Blender execution
│   ├── exec.py            # Code execution server
│   ├── investigator.py    # Scene investigation server
│   └── ...
│
├── slides/                # PPTX generation
│   └── exec.py            # Slides execution server
│
├── assets/                # 3D asset generation
│   └── meshy.py           # Meshy API server
│
└── sam3d/                 # SAM segmentation
    ├── init.py            # Scene reconstruction
    ├── bridge.py          # SAM bridge
    └── *_worker.py        # Worker processes
```

## Tool Servers

| Server | Description | Environment |
|--------|-------------|-------------|
| `generator_base.py` | make_plan, execute_code | agent |
| `verifier_base.py` | analyze, suggest | agent |
| `blender/exec.py` | Blender code execution | blender |
| `blender/investigator.py` | Camera control, scene info | blender |
| `slides/exec.py` | PPTX generation | pptx |
| `assets/meshy.py` | 3D asset generation | agent |
| `sam3d/init.py` | SAM scene reconstruction | sam3d |

## Configuration

Tool-to-environment mapping is configured in `utils/path.py`.
