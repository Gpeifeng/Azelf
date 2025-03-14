import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import os
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
# 从环境变量中获取 OpenAI API 密钥
api_key = os.environ["OPENAI_API_KEY"]
model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

class MCPClient:
    def __init__(self):
        # 初始化 ClientSession 对象列表，初始值为 None
        self.sessions: list[Optional[ClientSession]] = []
        # 创建一个异步上下文管理器栈
        self.exit_stack = AsyncExitStack()
        # 初始化 OpenAI 客户端，使用获取的 API 密钥
        self.openai = OpenAI(api_key=api_key)

    async def connect_to_servers(self, server_script_paths: list[str]):
        """
        连接到多个指定的服务器脚本。
        参数:
        server_script_paths (list[str]): 服务器脚本的文件路径列表。
        异常:
        ValueError: 如果服务器脚本不是 .py 或 .js 文件。
        """
        for server_script_path in server_script_paths:
            # 检查服务器脚本是否为 Python 文件
            is_python = server_script_path.endswith(".py")
            # 检查服务器脚本是否为 JavaScript 文件
            is_js = server_script_path.endswith(".js")
            # 如果不是 Python 或 JavaScript 文件，抛出异常
            if not (is_python or is_js):
                raise ValueError("Server script must be a .py or .js file")
            # 根据脚本类型选择执行命令 需要修改解释器路径
            command = (
                "C:\\document\\Azelf\\.venv\\Scripts\\python.exe"
                if is_python
                else "node"
            )
            # 创建标准输入输出服务器参数对象
            server_params = StdioServerParameters(
                command=command, args=[server_script_path], env=None
            )
            # 进入异步上下文，启动标准输入输出客户端
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            # 解包标准输入输出传输对象
            stdio, write = stdio_transport
            # 进入异步上下文，创建客户端会话
            session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            # 初始化客户端会话
            await session.initialize()
            # 列出可用的工具
            response = await session.list_tools()
            tools = response.tools
            print(
                f"\nConnected to server {server_script_path} with tools:",
                [[tool.name, tool.description, tool.inputSchema] for tool in tools],
            )
            self.sessions.append(session)

    async def process_query(self, query: str) -> str:
        """
        处理用户的查询请求。
        参数:
        query (str): 用户输入的查询字符串。
        返回:
        str: 处理查询后的最终响应内容。
        """
        # 构建用户消息
        messages = [{"role": "user", "content": query}]
        all_available_tools = []
        for session in self.sessions:
            # 列出可用的工具
            response = await session.list_tools()
            available_tools = []
            # 遍历工具列表，转换为 OpenAI 工具格式
            for tool in response.tools:
                tool_schema = getattr(
                    tool,
                    "inputSchema",
                    {"type": "object", "properties": {}, "required": []},
                )
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool_schema,
                    },
                }
                available_tools.append(openai_tool)
            all_available_tools.extend(available_tools)

        # 调用 OpenAI API 进行聊天完成
        model_response = self.openai.chat.completions.create(
            model=model,
            max_tokens=1000,
            messages=messages,
            tools=all_available_tools,
        )
        tool_results = []
        final_text = []
        # 将模型响应添加到消息列表
        messages.append(model_response.choices[0].message.model_dump())
        print(messages[-1])
        # 如果模型响应中包含工具调用
        if model_response.choices[0].message.tool_calls:
            tool_call = model_response.choices[0].message.tool_calls[0]
            tool_args = json.loads(tool_call.function.arguments)

            tool_name = tool_call.function.name
            for session in self.sessions:
                try:
                    # 调用服务器工具
                    result = await session.call_tool(tool_name, tool_args)
                    tool_results.append({"call": tool_name, "result": result})
                    final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                    # 添加工具调用结果到消息列表
                    messages.append(
                        {
                            "role": "tool",
                            "content": f"{result}",
                            "tool_call_id": tool_call.id,
                        }
                    )
                    break
                except Exception as e:
                    continue
            # 再次调用 OpenAI API 进行聊天完成
            response = self.openai.chat.completions.create(
                model=model,
                max_tokens=1000,
                messages=messages,
            )
            # 将新的模型响应添加到消息列表
            messages.append(response.choices[0].message.model_dump())
            print(messages[-1])
        # 返回最终响应内容
        return messages[-1]["content"]

    async def chat_loop(self):
        """
        启动聊天循环，持续接收用户输入并处理查询。
        """
        while True:
            try:
                # 获取用户输入的查询
                query = input("\nQuery: ").strip()
                # 如果用户输入 quit，退出循环
                if query.lower() == "quit":
                    break
                # 处理用户查询
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """
        清理资源，关闭异步上下文管理器栈。
        """
        await self.exit_stack.aclose()


async def main():
    """
    主函数，负责初始化客户端，连接到多个服务器，并启动聊天循环。
    """
    # 硬编码服务器脚本路径
    server_script_paths = ["server.py"]  # 请根据实际情况修改路径
    # 创建 MCPClient 实例
    client = MCPClient()
    try:
        # 连接到多个服务器
        await client.connect_to_servers(server_script_paths)
        # 启动聊天循环
        await client.chat_loop()
    finally:
        # 清理资源
        await client.cleanup()


if __name__ == "__main__":
    import sys
    # 运行异步主函数
    asyncio.run(main())


