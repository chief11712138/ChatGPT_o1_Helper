import os
import openai
import sys
from datetime import datetime
from utils import load_config, save_chat_to_markdown, calculate_cost, format_markdown, calculate_total_cost
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

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

    def append_to_log(self, token_usage=None):
        """将消息实时写入日志文件。

        Args:
            token_usage (CompletionUsage): Token 消耗信息。
        """
        cost = calculate_cost(token_usage, self.config["pricing"]) if token_usage else 0
        chat_log = format_markdown(self.messages, self.model, token_usage, cost)

        with open(self.log_file_name, "w") as f:
            f.write(chat_log)

    def chat(self, prompt):
        """发送用户输入并获取 AI 响应。"""
        self.messages.append({"role": "user", "content": prompt})

        response = openai.chat.completions.create(
            model=self.model,
            messages=self.messages
        )
        content = response.choices[0].message.content
        token_usage = response.usage

        console.print(Markdown(f"# AI Response\n{content}"))

        self.messages.append({"role": "assistant", "content": content})

        # 写入日志
        self.append_to_log(token_usage)
        return content, token_usage


def main():
    print("Welcome to ChatGPT CLI!")
    bot = ChatGPT()
    total_token_usage = {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}

    while True:
        try:
            prompt = input("\033[31mYou: \033[0m")
            prompt_lower = prompt.lower()
            if prompt_lower in {"--help"}:
                print("Type your message and press Enter to chat with the AI.")
                print("Use --exit or --quit to end the chat.")
                print("Use --usage to view token usage.")
                continue

            elif prompt_lower in {"--exit", "--quit"}:
                print("Exiting chat.")
                bot.append_to_log(total_token_usage)
                print(f"Current Session Total Cost: ${calculate_cost(total_token_usage, bot.config['pricing']):.6f}")# 保存最终日志
                print(f"Total Cost: {calculate_total_cost()}")
                sys.exit(0)

            elif prompt_lower in {"--usage"}:
                print(f"Token Usage: {total_token_usage}")
                print(f"Current Session Total Cost: ${calculate_cost(total_token_usage, bot.config['pricing']):.6f}")
                print(f"Total Cost: ${calculate_total_cost(): .6f}")
                continue

            elif ((prompt_lower.startswith("-") or prompt_lower.startswith("--")) and
                  prompt_lower not in {"--help", "--exit", "--quit", "--usage"}):
                print("Unknown command. Type --help for a list of commands.")
                continue

            response, token_usage = bot.chat(prompt)

            # 使用属性访问来累加 Token 使用数据
            total_token_usage["prompt_tokens"] += getattr(token_usage, "prompt_tokens", 0)
            total_token_usage["cached_tokens"] += getattr(token_usage, "cached_tokens", 0)
            total_token_usage["completion_tokens"] += getattr(token_usage, "completion_tokens", 0)

        except KeyboardInterrupt:
            print("\nExiting chat.")
            bot.append_to_log(total_token_usage)  # 保存最终日志
            sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        input("\nPress Enter to close...")
