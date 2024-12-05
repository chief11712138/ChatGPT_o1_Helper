import os
import openai
import sys
from datetime import datetime
from utils import (
    load_config, save_chat_to_markdown, calculate_cost, format_markdown, calculate_total_cost, list_log_files,
    load_chat_history, add_session_to_file, remove_session_from_file, get_all_sessions_from_file
)
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
import threading
import time
import argparse
import subprocess
import traceback


os.system('')

exit_event = threading.Event()  # 创建全局退出事件
console = Console(width=100)
conversations = []
conversations_lock = threading.Lock()

class Conversation:
    def __init__(self, bot, total_token_usage):
        self.bot = bot
        self.total_token_usage = total_token_usage
        self.prompt_queue = []
        self.response_ready = threading.Event()
        self.waiting_for_response = False
        self.lock = threading.Lock()
        self.input_thread = threading.Thread(target=self.user_input_loop, daemon=True)
        self.gpt_thread = None
        self.session_name = self.bot.log_file_name
        self.exit_event = threading.Event()  # 为每个会话添加一个退出事件
        self.closed = False
        self.token_usage_lock = threading.Lock()

    def start(self):
        add_session_to_file(self.session_name, 'Open')
        self.input_thread.start()

    def close(self):
        """关闭当前会话，停止线程并清理资源。"""
        self.exit_event.set()
        self.closed = True
        # 通知等待中的线程
        self.response_ready.set()
        # 等待 GPT 回复线程结束
        if self.gpt_thread and self.gpt_thread.is_alive():
            self.gpt_thread.join()
        # 等待输入线程结束
        if threading.current_thread() != self.input_thread and self.input_thread.is_alive():
            self.input_thread.join()
        # 更新会话状态文件
        remove_session_from_file(self.session_name)
        # 检查是否有聊天内容
        if not self.bot.has_messages():
            # 删除日志文件
            if os.path.exists(self.bot.log_file_name):
                os.remove(self.bot.log_file_name)
            print(f"Session {self.session_name} was empty and has been deleted.")
        else:
            print(f"Session {self.session_name} has been closed.")

    def user_input_loop(self):
        while not self.exit_event.is_set() and not exit_event.is_set():
            # 检查退出标志文件
            if os.path.exists("exit_flag.txt"):
                print("Exit flag detected. Closing conversation.")
                self.close()
                break
            try:
                if not self.waiting_for_response:
                    print("\033[31mYou: \033[0m", end="")
                    prompt = input("")
                    result = self.handle_commands(prompt)
                    if isinstance(result, str):
                        prompt = result
                    elif result:
                        continue
                    with self.lock:
                        self.prompt_queue.append(prompt)
                        self.waiting_for_response = True
                    self.response_ready.clear()
                    self.gpt_thread = threading.Thread(target=self.gpt_reply_loop, daemon=True)
                    self.gpt_thread.start()
                else:
                    self.response_ready.wait(timeout=1)
            except EOFError:
                break
            except Exception as e:
                print(f"Input error: {e}")
                break

    def gpt_reply_loop(self):
        if self.exit_event.is_set() or exit_event.is_set():
            return
            # 检查退出标志文件
        if os.path.exists("exit_flag.txt"):
            print("Exit flag detected in GPT thread. Closing conversation.")
            self.close()
            return
        with self.lock:
            if not self.prompt_queue:
                return
            prompt = self.prompt_queue.pop(0)
        self.waiting_for_response = True

        loading_thread = threading.Thread(target=self.loading_indicator, daemon=True)
        loading_thread.start()
        response, token_usage = self.bot.chat(prompt)
        self.waiting_for_response = False  # 停止加载指示器
        loading_thread.join()  # 等待加载指示器线程结束
        print("\n")  # 确保输出位置正确
        if response is not None:
            console.print(Markdown(f"# AI Response\n{response}"))
        else:
            print("Failed to get a response from the AI.")

        if token_usage is not None:
            with self.token_usage_lock:
                self.total_token_usage["prompt_tokens"] += token_usage.get("prompt_tokens", 0)
                self.total_token_usage["completion_tokens"] += token_usage.get("completion_tokens", 0)
                if "cached_tokens" in token_usage:
                    self.total_token_usage["cached_tokens"] += token_usage.get("cached_tokens", 0)
        else:
            print("Token usage information is not available.")

        self.response_ready.set()
        with self.lock:
            self.waiting_for_response = False

    def loading_indicator(self):
        frames = ["◐", "◓", "◑", "◒"]
        while self.waiting_for_response and not self.exit_event.is_set():
            for char in frames:
                if not self.waiting_for_response or self.exit_event.is_set():
                    break
                print(f"\rWaiting for GPT response... {char}", end="", flush=True)
                time.sleep(0.5)
            # 清除行
        print("\r" + " " * 50 + "\r", end="", flush=True)

    def print_help(self):
        # 创建表格对象，设置列间分隔符
        table = Table(show_header=True, header_style="bold magenta", show_lines=True)

        # 添加列，并设置列宽
        table.add_column("Command", width=50)
        table.add_column("Description", width=48)

        # 添加行到表格中
        table.add_row("--exit or --quit or --e or --q", "End the chat.")
        table.add_row("--current usage or --cu", "View token usage for current session.")
        table.add_row("--total usage or --tu", "View token usage for all recorded sessions.")
        table.add_row("--list or --ls or --history --h", "List all chat history files.")
        table.add_row("--continue or --cont <filename>", "Continue a previous chat session.")
        table.add_row("--open or --o", "Open a new chat session.")
        table.add_row("--sessions or --s", "List all current open sessions.")
        table.add_row("--close or --c", "Close the current session.")
        table.add_row("--add key or --ak <api_key>", "Add an OpenAI API key.")
        table.add_row("--read or --r <filename>", "Read a command file. Requires a full path.")

        # 输出帮助信息
        console.print(Markdown("# User Manual\n"))
        console.print(Markdown("## Type your message and press Enter to chat with the AI.\n"))
        console.print(Markdown("---\n"))
        console.print(Markdown("## Commands:\n"))
        console.print(Markdown("- Any sentence started with \"--\" or \"-\" "
                               "and the length less than 20 chars, will be considered as a command \n"))
        console.print(table)
        console.print(Markdown("---\n"))

    def handle_commands(self, prompt):
        prompt_lower = prompt.lower()
        # 获取第一个空格前的任何内容
        prompt_lower = prompt_lower.split(" ")[0]
        if prompt_lower in ("--help", "--h"):
            self.print_help()
            return True
        elif prompt_lower in ("--sessions", "--s"):
            self.list_current_sessions()
            return True
        elif prompt_lower in ("--close", "--c"):
            print("Closing all conversations...")
            # 关闭所有会话
            with conversations_lock:
                for conv in conversations[:]:
                    print(f"Closing session: {conv.session_name}")
                    conv.bot.append_to_log(conv.total_token_usage)
                    conv.close()
                    conversations.remove(conv)
            # 设置全局退出事件，通知主线程退出
            exit_event.set()
            with open("exit_flag.txt", "w") as f:
                f.write("exit")

            # 删除sessions.json文件
            if os.path.exists("sessions.json"):
                os.remove("sessions.json")

            return True
        elif prompt_lower in ("--exit", "--quit", "--e", "--q"):
            print("Exiting Chat.")
            # 设置全局退出事件，通知所有会话退出
            exit_event.set()
            # 修改session.json文件内容，以删除当前会话
            remove_session_from_file(self.session_name)
            return True
        elif prompt_lower in ("--current usage", "--cu"):
            print(f"Token Usage: {self.total_token_usage}")
            print(
                f"Current Session Total Cost: ${calculate_cost(self.total_token_usage, self.bot.config['pricing']):.6f}")
            return True
        elif prompt_lower in ("--total usage", "--tu"):
            total_stats = calculate_total_cost(self.bot.config["output_directory"])
            print("\nSummary of All Logs:")
            print(f"- Total Input Tokens: {total_stats['total_input_tokens']}")
            print(f"- Total Cached Tokens: {total_stats['total_cached_tokens']}")
            print(f"- Total Output Tokens: {total_stats['total_output_tokens']}")
            print(f"- Total Cost: ${total_stats['total_cost']:.6f}")
            return True
        elif prompt_lower in ("--list", "--ls", "--history", "--h"):
            log_files = list_log_files(self.bot.config["output_directory"])
            if not log_files:
                print('No history in "chat_logs" folder')
            else:
                print("\n".join(log_files))
            return True
        elif prompt_lower in ("--open", "--o"):
            try:
                if getattr(sys, 'frozen', False):
                    # 被打包的可执行文件
                    script_path = sys.executable
                    command = [script_path]
                else:
                    # 未打包，使用 Python 解释器运行脚本
                    script_path = os.path.abspath(sys.argv[0])
                    python_executable = sys.executable  # 通常是 'python.exe'
                    command = [python_executable, script_path]
                subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
                print("Opened a new conversation in a new window.")
            except Exception as e:
                print(f"Failed to open new conversation: {e}")
                traceback.print_exc()
            return True

        elif prompt_lower in ("--continue", "--cont"):
            try:
                file_name = prompt.split(" ")[1]
            except IndexError:
                print("Please provide a file name to continue the conversation.")
                return True
            try:
                if getattr(sys, 'frozen', False):
                    # 被打包的可执行文件
                    script_path = sys.executable
                    command = [script_path, '--continue', file_name]
                else:
                    # 未打包，使用 Python 解释器运行脚本
                    script_path = os.path.abspath(sys.argv[0])
                    python_executable = sys.executable  # 通常是 'python.exe'
                    command = [python_executable, script_path, '--continue', file_name]
                subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
                print(f"Continuing conversation from {file_name} in a new window.")
            except Exception as e:
                print(f"Failed to continue conversation: {e}")
                traceback.print_exc()
            return True
        elif prompt_lower in ("--add key", "--ak"):
            try:
                api_key = prompt.split(" ")[1]
                self.bot.config["api_key"] = api_key
                openai.api_key = api_key
                print("API key updated successfully.")
            except IndexError:
                print("Please provide an API key to add.")
            return True
        elif prompt_lower in ("--read", "--r"):
            try:
                file_name = prompt.split(" ")[1]
                content = ""
                with open(file_name, "r") as f:
                    for line in f:
                        content += line
                return content
            except IndexError:
                print("Please provide a file name to read.")
            except FileNotFoundError:
                print(f"File {file_name} not found.")
            return True
        elif prompt_lower.startswith(("-",)) and prompt.__len__() <= 20:
            print("Unknown command. Type --help to see available commands.")
            return True
        elif prompt_lower.startswith(("-",)) and prompt.__len__() <= 20:
            print("Unknown command. Type --help to see available commands.")
            return True
        return False

    def list_current_sessions(self):
        sessions = get_all_sessions_from_file()
        if not sessions:
            print("\nNo current open conversations.\n")
            return
        print("\nCurrent Open Conversations:")
        for idx, session in enumerate(sessions):
            session_name = session['session_name']
            print(f"{idx + 1}. Session Name: {session_name}")
        print("")

    def get_token_usage_and_cost(self):
        """获取当前会话的 Token 使用情况和成本"""
        # 使用线程锁，防止并发访问
        with self.token_usage_lock:
            token_usage = self.total_token_usage.copy()
        # 计算成本
        cost = calculate_cost(token_usage, self.bot.config['pricing'])
        return token_usage, cost


class ChatGPT:
    def __init__(self, config_file="config.json"):
        """初始化 ChatGPT 实例。"""
        self.config = load_config(config_file)
        openai.api_key = self.config["api_key"]
        self.model = self.config["model"]
        self.messages = []
        self.session_start_time = datetime.now()
        self.log_file_name = self.generate_log_file_name()
        self.stats_lock = threading.Lock()

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
            token_usage (dict): Token 使用数据。
            new_message (dict): 最新的消息 {"role": str, "content": str}。
        """
        # 从 token_usage 获取数据
        input_tokens = token_usage.get("prompt_tokens", 0) if token_usage else 0
        cached_tokens = token_usage.get("cached_tokens", 0) if token_usage else 0
        output_tokens = token_usage.get("completion_tokens", 0) if token_usage else 0

        cost = calculate_cost(token_usage, self.config["pricing"]) if token_usage else 0

        # 格式化日志头部
        header = f"# Chat Log - {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        header += f"**Model**: {self.model}\n"
        header += f"**Token Usage**:\n"
        header += f"- Input Tokens: {input_tokens}\n"
        header += f"- Cached Tokens: {cached_tokens}\n"
        header += f"- Output Tokens: {output_tokens}\n"
        header += f"**Cost**: ${cost:.4f}\n\n"

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
        file_path = os.path.join(self.config["output_directory"], file_name)
        history = load_chat_history(file_path, token_usage)
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
            usage = response.usage
            token_usage = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }

            # GPT 回答后立即记录日志
            assistant_message = {"role": "assistant", "content": content}
            self.messages.append(assistant_message)
            self.append_to_log(token_usage=token_usage, new_message=assistant_message)

            # 附加聊天记录
            self.messages.append({"role": "assistant", "content": content})

            return content, token_usage

        except Exception as e:
            print(f"Error during chat: {e}")
            return None, None

    def has_messages(self):
        """检查是否有实际的聊天内容（不包括系统消息）"""
        return any(msg["role"] == "user" or msg["role"] == "assistant" for msg in self.messages)


def main():
    print("Welcome to ChatGPT CLI!")
    global conversations
    conversations = []
    total_token_usage = {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}
    bot = ChatGPT()

    try:
        if getattr(sys, 'frozen', False):
            # 程序被打包
            application_path = os.path.dirname(sys.executable)
        else:
            # 未打包，直接使用脚本路径
            application_path = os.path.dirname(os.path.abspath(__file__))
        if not os.path.exists(application_path + "\\" + "sessions.json"):
            with open(application_path + "\\" + "sessions.json", "w") as f:
                f.write("[]")
        parser = argparse.ArgumentParser(description='ChatGPT CLI')
        parser.add_argument('--continue', '--cont', dest='continue_file',
                            help='Continue a previous chat session from a file')
        args = parser.parse_args()

        if args.continue_file:
            # 加载指定的聊天历史记录
            bot.load_history(args.continue_file, total_token_usage)
            print(f"Continuing conversation from {args.continue_file}")

        conv = Conversation(bot, total_token_usage)
        with conversations_lock:
            conversations.append(conv)
        conv.start()
        while not exit_event.is_set():
            time.sleep(1)
            # 检查退出标志文件
            if os.path.exists("exit_flag.txt"):
                exit_event.set()
            # 程序退出时，所有会话已经被关闭，无需再次关闭
            # 删除退出标志文件
        if os.path.exists("exit_flag.txt"):
            os.remove("exit_flag.txt")

        print("All sessions have been closed. Exiting program.")
        sys.exit(0)

    except KeyboardInterrupt:
        print("\nExiting chat.")
        bot.append_to_log(total_token_usage)
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An error occurred: {e}\n")
    finally:
        print("Please do not close the program directly.")
        print("Exiting ChatGPT CLI...")
        time.sleep(4)
        sys.exit(0)
