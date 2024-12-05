import os
import openai
import sys
import subprocess  # 用于打开文件
import json
from datetime import datetime
from utils import (
    load_config, save_chat_to_markdown, calculate_cost, format_markdown, calculate_total_cost, list_log_files, load_chat_history
)
from rich.console import Console
from rich.markdown import Markdown

console = Console()

class ChatGPT:
    def __init__(self, config_file="config.json"):
        """初始化 ChatGPT 实例。"""
        self.config = load_config(config_file)
        openai.api_key = self.config["api_key"]
        self.model = self.config["model"]
        self.messages = []
        self.session_start_time = datetime.now()
        self.log_file_name = self.generate_log_file_name()

        # 创建输出目录
        output_dir = self.config["output_directory"]
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def generate_log_file_name(self):
        """生成基于会话开始时间的日志文件名。"""
        timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        return f"{self.config['output_directory']}/chat_{timestamp}.md"

    def append_to_log(self, token_usage=None, new_message=None):
        """
        更新聊天日志：
        - 在头部更新 Token 消耗统计信息。
        - 在末尾追加新消息。

        Args:
            token_usage (CompletionUsage): Token 使用数据。
            new_message (dict): 最新的消息 {"role": str, "content": str}。
        """
        # 从 token_usage 获取数据
        token_usage_dict = json.loads(json.dumps(token_usage, default=lambda o: o.__dict__))
        input_tokens = 0
        cached_tokens = 0
        output_tokens = 0
        if token_usage_dict:
            if "prompt_tokens" in token_usage_dict:
                input_tokens = token_usage_dict["prompt_tokens"]
            if "cached_tokens" in token_usage_dict:
                cached_tokens = token_usage_dict["cached_tokens"]
            if "completion_tokens" in token_usage_dict:
                output_tokens = token_usage_dict["completion_tokens"]

        cost = calculate_cost(token_usage, self.config["pricing"]) if token_usage else 0

        # 格式化日志头部
        header = f"# Chat Log - {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        header += f"**Model**: {self.model}\n"
        header += f"**Token Usage**:\n\n"
        header += f"- Input Tokens: {input_tokens}\n"
        header += f"- Cached Tokens: {cached_tokens}\n"
        header += f"- Output Tokens: {output_tokens}\n"
        header += f"**Cost**: ${cost:.4f}\n"

        # 格式化新消息
        new_message_content = ""
        if new_message:
            role = new_message["role"].capitalize()
            content = new_message["content"]
            new_message_content = f"## {role}\n{content}\n\n"

        try:
            # 读取现有内容
            if os.path.exists(self.log_file_name):
                with open(self.log_file_name, "r", encoding="utf-8") as f:
                    existing_content = f.read()
            else:
                existing_content = ""

            # 提取现有消息内容部分
            split_index = existing_content.find("## ")
            if split_index != -1:
                existing_messages = existing_content[split_index:]
            else:
                existing_messages = ""

            # 组装日志内容
            updated_log = header + existing_messages + new_message_content

            # 写入文件
            with open(self.log_file_name, "w", encoding="utf-8") as f:
                f.write(updated_log)

        except Exception as e:
            print(f"Error writing log: {e}")

    def load_history(self, file_name, token_usage):
        """加载指定的聊天历史。"""
        history = load_chat_history(file_name, token_usage)
        self.messages = history

    def chat(self, prompt):
        """发送用户输入并获取 AI 响应，同时记录日志。"""
        # 用户输入后立即记录日志
        user_message = {"role": "user", "content": prompt}
        self.messages.append(user_message)
        self.append_to_log(new_message=user_message)

        try:
            # GPT 响应
            response = openai.chat.completions.create(
                model=self.model,
                messages=self.messages
            )
            content = response.choices[0].message.content
            token_usage = response.usage

            # GPT 回答后立即记录日志
            assistant_message = {"role": "assistant", "content": content}
            self.messages.append(assistant_message)
            self.append_to_log(token_usage=token_usage, new_message=assistant_message)

            # 输出回复到控制台
            console.print(Markdown(f"# AI Response\n{content}"))

            # 附加聊天记录
            self.messages.append({"role": "assistant", "content": content})

            return content, token_usage

        except Exception as e:
            print(f"Error during chat: {e}")
            return None, None


def open_file(file_path):
    """打开指定的文件。"""
    try:
        if os.name == "nt":  # Windows 系统
            os.startfile(file_path)
        elif os.name == "posix":  # macOS 或 Linux 系统
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", file_path])
        else:
            print("Unsupported OS.")
    except Exception as e:
        print(f"Failed to open file: {e}")


def main():
    print("Welcome to ChatGPT CLI!")
    bot = ChatGPT()
    total_token_usage = {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}

    while True:
        try:
            prompt = input("\033[31mYou: \033[0m")
            prompt_lower = prompt.lower()
            if prompt_lower.startswith(("--help", "--h")):
                markdown_output = "# User Manual\n"
                markdown_output += "## Type your message and press Enter to chat with the AI.\n"
                markdown_output += "---\n"
                markdown_output += "## Commands:\n"
                markdown_output += "--exit or --quit or --e or --q  \tEnd the chat.\n\n"
                markdown_output += "--current usage or --cu         \tView token usage for current session.\n\n"
                markdown_output += "--total usage or --tu           \tView token usage for all recorded sessions\n\n"
                markdown_output += "--list or --ls or --history -- h\tList all chat history files.\n\n"
                markdown_output += "--continue or --c \<filename\>  \tContinue a previous chat session.\n\n"
                markdown_output += "--open or --o \<filename\>      \tOpen a specific chat history file.\n\n"
                markdown_output += "---"

                console.print(Markdown(markdown_output))
                continue

            elif prompt_lower.startswith(("--exit", "--quit", "--e", "--q")):
                print("Exiting chat.")
                bot.append_to_log(total_token_usage)
                print(f"Current Session Total Cost: ${calculate_cost(total_token_usage, bot.config['pricing']):.6f}")
                sys.exit(0)

            elif prompt_lower.startswith(("--current usage", "--cu")):
                print(f"Token Usage: {total_token_usage}")
                print(f"Current Session Total Cost: ${calculate_cost(total_token_usage, bot.config['pricing']):.6f}")
                continue

            elif prompt_lower.startswith(("--total usage", "--tu")):
                total_stats = calculate_total_cost("chat_logs")  # 默认日志目录为 chat_logs
                print("\nSummary of All Logs:")
                print(f"- Total Input Tokens: {total_stats['total_input_tokens']}")
                print(f"- Total Cached Tokens: {total_stats['total_cached_tokens']}")
                print(f"- Total Output Tokens: {total_stats['total_output_tokens']}")
                print(f"- Total Cost: ${total_stats['total_cost']:.6f}")
                continue

            elif prompt_lower.startswith(("--list", "--ls", "--history", "--h")):
                log_files = list_log_files(bot.config["output_directory"])
                if not log_files:
                    print("No history in \"chat_log\" folder")
                else:
                    print("\n".join(log_files))
                continue

            elif prompt_lower.startswith(("--continue", "--c")):
                file_name = prompt.split(" ")[1]
                bot.load_history(file_name, total_token_usage)
                print(f"Loaded chat history from {file_name}")
                continue

            elif prompt_lower.startswith(("--open", "--o")):
                file_name = prompt.split(" ")[1]
                file_path = os.path.join(bot.config["output_directory"], file_name)
                open_file(file_path)
                continue

            response, token_usage = bot.chat(prompt)

            token_usage_dict = json.loads(json.dumps(token_usage, default=lambda o: o.__dict__))

            # 累加 Token 使用数据
            if token_usage_dict:
                if "prompt_tokens" in token_usage_dict:
                    total_token_usage["prompt_tokens"] += token_usage_dict["prompt_tokens"]
                if "cached_tokens" in token_usage_dict:
                    total_token_usage["cached_tokens"] += token_usage_dict["cached_tokens"]
                if "completion_tokens" in token_usage_dict:
                    total_token_usage["completion_tokens"] += token_usage_dict["completion_tokens"]

        except KeyboardInterrupt:
            print("\nExiting chat.")
            bot.append_to_log(total_token_usage)
            sys.exit(0)


if __name__ == "__main__":
    main()
