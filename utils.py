import os
import json
from datetime import datetime
from charset_normalizer import detect
import threading
import sys

# 获取程序所在目录的绝对路径
SESSIONS_FILE = "sessions.json"
sessions_file_lock = threading.Lock()

def load_config(file_path="config.json"):
    """加载配置文件。"""
    with open(file_path, 'r') as f:
        return json.load(f)


def save_chat_to_markdown(chat, file_path):
    """保存聊天记录为 Markdown 文件。"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        f.write(chat)


def calculate_cost(token_usage, pricing):
    """计算 Token 成本，支持对象访问。

    Args:
        token_usage (CompletionUsage): 包含 prompt_tokens, cached_tokens, completion_tokens 的对象。
        pricing (list): Token 价格 [input, cached input, output]。

    Returns:
        float: 总成本。
    """

    token_usage_dict = json.loads(json.dumps(token_usage, default=lambda o: o.__dict__))

    input_tokens = token_usage_dict["prompt_tokens"]
    if ("cached_tokens" not in token_usage_dict):
        cached_tokens = 0
    else:
        cached_tokens = token_usage_dict["cached_tokens"]
    output_tokens = token_usage_dict["completion_tokens"]

    price = input_tokens * pricing[0] + \
            cached_tokens * pricing[1] + \
            output_tokens * pricing[2]

    return price


def format_markdown(messages, model, token_usage, cost):
    """格式化 Markdown 聊天记录。

    Args:
        messages (list): 聊天消息记录。
        model (str): 使用的模型名称。
        token_usage (CompletionUsage): Token 使用统计对象。
        cost (float): 总成本。

    Returns:
        str: 格式化的 Markdown 文本。
    """

    token_usage_dict = json.loads(json.dumps(token_usage, default=lambda o: o.__dict__))

    input_tokens = token_usage_dict["prompt_tokens"]
    cached_tokens = token_usage_dict.get("cached_tokens", 0)
    output_tokens = token_usage_dict["completion_tokens"]

    chat_content = f"# Chat Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    chat_content += f"**Model**: {model}\n"
    chat_content += f"**Token Usage**:\n"
    chat_content += f"- Input Tokens: {input_tokens}\n"
    chat_content += f"- Cached Tokens: {cached_tokens}\n"
    chat_content += f"- Output Tokens: {output_tokens}\n"
    chat_content += f"**Cost**: ${cost:.4f}\n\n"
    for msg in messages:
        role = msg['role'].capitalize()
        content = msg['content']
        chat_content += f"## {role}\n{content}\n\n"
    return chat_content


def calculate_total_cost(log_directory="chat_logs"):
    """统计所有日志文件中总消耗的钱和 Token 数量。

    Args:
        log_directory (str): 保存日志文件的目录路径。

    Returns:
        dict: 包含总成本和 Token 消耗统计的字典。
    """
    # 确保 log_directory 是程序所在目录下的子文件夹
    application_path = ""
    if not getattr(sys, 'frozen', False):
        # 未打包，直接使用脚本路径
        application_path = os.path.dirname(os.path.abspath(__file__))
    else:
        # 程序被打包
        application_path = os.path.dirname(sys.executable)
    log_directory = application_path +"\\" + log_directory

    total_cost = 0.0
    total_input_tokens = 0
    total_cached_tokens = 0
    total_output_tokens = 0

    if not os.path.exists(log_directory):
        print(f"No logs found in the directory: {log_directory}")
        return {
            "total_cost": total_cost,
            "total_input_tokens": total_input_tokens,
            "total_cached_tokens": total_cached_tokens,
            "total_output_tokens": total_output_tokens,
        }

    print("Calculating total cost and token usage from log files...\n")
    for log_file in os.listdir(log_directory):
        log_path = os.path.join(log_directory, log_file)
        if os.path.isfile(log_path) and log_file.endswith(".md"):
            try:
                with open(log_path, "rb") as f:
                    raw_data = f.read()
                    result = detect(raw_data)
                    encoding = result['encoding']  # 自动检测文件编码
                    content = raw_data.decode(encoding)

                    # 提取 Token 和成本信息
                    for line in content.splitlines():
                        if line.startswith("**Cost**: $"):
                            cost_value = float(line.split("$")[1])
                            print(f"File: {log_file}, Cost: ${cost_value:.6f}")
                            total_cost += cost_value
                        elif line.startswith("- Input Tokens:"):
                            total_input_tokens += int(line.split(":")[-1].strip())
                        elif line.startswith("- Cached Tokens:"):
                            total_cached_tokens += int(line.split(":")[-1].strip())
                        elif line.startswith("- Output Tokens:"):
                            total_output_tokens += int(line.split(":")[-1].strip())

            except Exception as e:
                print(f"Error reading file {log_file}: {e}")

    return {
        "total_cost": total_cost,
        "total_input_tokens": total_input_tokens,
        "total_cached_tokens": total_cached_tokens,
        "total_output_tokens": total_output_tokens,
    }



def list_log_files(directory):
    """列出日志目录中的所有文件。"""
    return [
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f)) and f.endswith(".md")
    ]


def load_chat_history(file_path, token_usage):
    """如果在名字末尾没有添加上.md那么添加"""
    if not file_path.endswith(".md"):
        file_path += ".md"

    """给file_path添加相对路径到程序所在目录下的chat_logs"""
    file_path = os.path.join(os.path.dirname(__file__), "", file_path)

    """加载聊天历史记录。"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} does not exist.")

    history = []
    current_role = None
    current_content = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # 检测新角色标志
            if line.startswith("## "):
                # 保存当前角色的内容
                if current_role and current_content:
                    history.append({"role": current_role.lower(), "content": "\n".join(current_content)})
                # 更新角色
                current_role = line[3:].strip()  # 去掉 "## "
                current_content = []
                continue  # 跳过后续检查，直接进入下一行

            total_token_usage = {"prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}
            # 检测历史token消耗
            if line.startswith("- Input Tokens: "):
                token_usage["prompt_tokens"] += int(line.split(":")[-1].strip())
                continue

            if line.startswith("- Cached Tokens: "):
                token_usage["cached_tokens"] += int(line.split(":")[-1].strip())
                continue

            if line.startswith("- Output Tokens: "):
                token_usage["completion_tokens"] += int(line.split(":")[-1].strip())
                continue

            # 跳过统计信息和空行
            if not line or line.startswith("#") or line.startswith("**") or line.startswith("-"):
                continue

            # 累积当前角色的内容
            current_content.append(line)

        # 保存最后一个角色的内容
        if current_role and current_content:
            history.append({"role": current_role.lower(), "content": "\n".join(current_content)})

    """删除掉旧的文件"""
    os.remove(file_path)

    return history

def add_session_to_file(session_name, status):
    with sessions_file_lock:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'r') as f:
                sessions = json.load(f)
        else:
            sessions = []
        # 检查会话是否已经存在
        for session in sessions:
            if session['session_name'] == session_name:
                session['status'] = status
                break
        else:
            # 新的会话
            sessions.append({'session_name': session_name, 'status': status})
        with open(SESSIONS_FILE, 'w') as f:
            json.dump(sessions, f)

def remove_session_from_file(session_name):
    with sessions_file_lock:
        if not os.path.exists(SESSIONS_FILE):
            return
        with open(SESSIONS_FILE, 'r') as f:
            sessions = json.load(f)
        print(session_name)
        sessions = [s for s in sessions if s['session_name'] != session_name]
        with open(SESSIONS_FILE, 'w') as f:
            json.dump(sessions, f)

def get_all_sessions_from_file():
    with sessions_file_lock:
        if not os.path.exists(SESSIONS_FILE):
            return []
        with open(SESSIONS_FILE, 'r') as f:
            sessions = json.load(f)
        return sessions

