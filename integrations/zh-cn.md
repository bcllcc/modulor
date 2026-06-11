# 国内大模型 / Agent 接入 Modulor

Modulor 是 Agent 原生 CAD：JSON 命令进、几何出（DXF/SVG/STL/GLB/IFC）。
`pip install modulor` 即装即用，无网络依赖、无密钥。

## 方式一：Function Calling（Kimi / 通义千问 / DeepSeek / 智谱等）

所有 OpenAI 兼容接口直接加载现成的工具定义
[tool-definitions.json](tool-definitions.json)：

```python
import json
tools = json.load(open("tool-definitions.json", encoding="utf-8"))["coarse"]

# 以任意 OpenAI 兼容 SDK 为例（Moonshot/DashScope/DeepSeek 同理）：
resp = client.chat.completions.create(
    model="...", messages=messages, tools=tools)
```

模型发起 `modulor_run(doc, commands)` 调用后，本地执行：

```python
from modulor import Cad, CadError

def modulor_run(doc, commands):
    cad = Cad(doc)
    try:
        results = cad.run(commands)
    except CadError as e:
        return {"ok": False, "error": e.to_dict()}  # error 带 hint，回传给模型自纠
    cad.save()
    return {"ok": True, "results": results}
```

`coarse` 是单工具模式（推荐，提示词开销最小）；`fine` 是 71 个独立工具，
适合偏好扁平工具列表的运行时。

## 方式二：MCP（支持 MCP 的客户端）

```json
{"mcpServers": {"modulor": {"command": "modulor", "args": ["mcp"]}}}
```

`cad_render` 工具直接返回 PNG 图像——多模态模型可以亲眼检查自己建的模型。

## 给模型的关键提示（建议写进 system prompt）

- 不要凭记忆猜参数：先发 `{"op":"help","name":"add_wall"}` 查任何操作
- 用 `tag` 命名实体、用 `{"tags":[...]}` 选择，不要硬编码 id
- 建完必须自检：`render`（labels:true 在图上印实体编号）+ `measure` + `validate`
- 数值字段支持表达式：`"bay*3"`、`"level_top('L2')"`、`"grid_x('B')"`
- 出错时读 `error.hint`，修正后重发整批命令（批处理是原子的）
- 坐标系：Z 向上、角度为逆时针度数、默认毫米
- 中文图纸：`import_dxf` 自动处理 GBK 码页与 `\\U+` 转义

完整中文能力说明见仓库 README；完整 API 见 `modulor ops` 或 docs/API.md。
