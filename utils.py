import os
import json
from datetime import datetime


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
    """统计所有日志文件中总消耗的钱。

    Args:
        log_directory (str): 保存日志文件的目录路径。

    Returns:
        float: 总消耗的钱。
    """
    total_cost = 0.0
    if not os.path.exists(log_directory):
        print(f"No logs found in the directory: {log_directory}")
        return total_cost

    for log_file in os.listdir(log_directory):
        log_path = os.path.join(log_directory, log_file)
        if os.path.isfile(log_path) and log_file.endswith(".md"):
            try:
                with open(log_path, "r") as f:
                    content = f.read()
                    # 提取总成本行
                    for line in content.splitlines():
                        if line.startswith("**Cost**: $"):
                            cost_value = float(line.split("$")[1])
                            total_cost += cost_value
                            break
            except Exception as e:
                print(f"Error reading file {log_file}: {e}")

    print(f"Total Cost: ${total_cost:.6f}")
    return total_cost
