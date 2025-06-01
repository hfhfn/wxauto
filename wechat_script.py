import time
import threading
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from wxauto import WeChat
import os
import uvicorn

app = FastAPI(title="WeChat Automation Service")
wx = WeChat()


# 消息状态跟踪
class MessageTracker:
    def __init__(self):
        self.current_chat = None


tracker = MessageTracker()


# 数据模型（严格使用文档参数名）
class SendTextRequest(BaseModel):
    who: str  # 文档指定参数名
    message: str


class SendFileRequest(BaseModel):
    who: str
    filepath: str


# 核心消息功能（严格遵循文档用法）
def get_all_new_messages_from_wxauto():
    """
    获取所有新的微信消息。

    通过调用 wx.GetAllNewMessage() 获取新消息，该方法返回一个字典，
    格式为 {chat_name: [msg1, msg2, ...]}，其中每个 msg 是一个元组
    (sender_in_chat, content, time, msg_id)。

    本函数将这些消息处理成统一的字典格式列表。

    Returns:
        list: 一个包含处理后消息字典的列表。每个字典格式如下：
              {
                  "who": chat_name,        # 聊天会话名称
                  "sender": sender_in_chat, # 消息在会话内的发送者
                  "message": content,        # 消息内容
                  "time": time,              # 消息发送时间
                  "msgid": msg_id            # 消息ID
              }
              如果获取消息失败或没有新消息，则返回空列表。
    """
    processed_messages = []
    try:
        # wx.GetAllNewMessage() 返回格式: {chat_name: [(sender_in_chat, content, time, msg_id), ...]}
        new_messages_dict = wx.GetAllNewMessage()

        if not new_messages_dict:
            return []

        for chat_name, messages_list in new_messages_dict.items():
            for msg_tuple in messages_list:
                # msg_tuple: (sender_in_chat, content, time, msg_id)
                if len(msg_tuple) == 4: # Ensure tuple has all expected elements
                    processed_messages.append({
                        "who": chat_name,
                        "sender": msg_tuple[0],
                        "message": msg_tuple[1],
                        "time": msg_tuple[2],
                        "msgid": msg_tuple[3]
                    })
                else:
                    print(f"[WARNING] Malformed message tuple in chat {chat_name}: {msg_tuple}")

        return processed_messages
    except Exception as e:
        print(f"[ERROR] 调用 wx.GetAllNewMessage() 失败: {e}")
        return []


def switch_to_chat(who: str) -> bool:
    """
    切换到指定的聊天窗口。

    Args:
        who (str): 要切换到的聊天对象的名称。

    Returns:
        bool: True 如果成功切换或已在目标聊天，False 如果切换失败。
    """
    if who == tracker.current_chat:
        print(f"Already in chat with {who}")
        return True

    print(f"Attempting to switch to chat with {who}...")
    result = wx.ChatWith(who)  # wx.ChatWith returns chat name on success, False on failure

    if result is not False: # Successfully switched
        tracker.current_chat = result  # Use the name confirmed by ChatWith
        print(f"Switched to chat with {tracker.current_chat}")
        time.sleep(0.3)  # Wait for window switch to complete
        return True
    else: # Failed to switch
        print(f"[ERROR] Failed to switch to chat with {who}")
        # tracker.current_chat = None # Optionally reset, or leave as is (was not 'who')
        return False


# 消息监听服务
def message_monitor():
    """Continuously monitors for new WeChat messages and processes them."""
    while True:
        try:
            new_messages = get_all_new_messages_from_wxauto() # Call the new function
            if new_messages:
                for msg in new_messages: # Iterate through the list of messages
                    handle_message(msg)
        except Exception as e:
            print(f"[ERROR] 监听服务异常: {e}")
        time.sleep(1)


def handle_message(msg: dict):
    """
    Processes a single incoming message.

    Ignores messages sent by the bot itself (identified by wx.nickname).
    Provides example reply logic based on message content.

    Args:
        msg (dict): A dictionary containing message details:
            - "who" (str): The chat session name (e.g., group name or contact name).
            - "sender" (str): The actual sender of the message within the chat.
            - "message" (str): The content of the message.
            - "time" (str): The timestamp of the message.
            - "msgid" (str): The unique ID of the message.
    """
    # msg format: {"who": chat_name, "sender": sender_in_chat, "message": content, "time": time, "msgid": msg_id}

    # 检查消息是否来自自己，如果是则忽略
    if msg['sender'] == wx.nickname:
        print(f"消息来自自己 ({wx.nickname})，发往 '{msg['who']}'，内容：'{msg['message']}'，已忽略。")
        return

    print(f"新消息来自 {msg['who']} (实际发送者: {msg['sender']}): {msg['message']}")

    # 示例回复逻辑
    reply = None
    content = msg["message"].lower()

    if "hello" in content or "你好" in content:
        reply = f"{msg['who']}你好！我是自动回复"
    elif "时间" in content:
        reply = time.strftime("现在是%H:%M:%S")

    if reply:
        send_text(msg["who"], reply)


# 文档标准消息发送
def send_text(who: str, message: str):
    """
    Sends a text message to the specified recipient.

    Ensures the chat with the recipient is active via switch_to_chat()
    before attempting to send the message.

    Args:
        who (str): The name of the recipient (chat or contact).
        message (str): The text message to send.
    """
    try:
        if switch_to_chat(who):
            wx.SendMsg(message)  # 文档标准发送方法
            print(f"已回复 {who}: {message}")
        else:
            print(f"[ERROR] Cannot send message: Failed to switch to chat with {who}")
    except Exception as e:
        print(f"[ERROR] 发送消息失败 (to {who}): {e}")


def send_file(who: str, filepath: str):
    """
    Sends a file to the specified recipient.

    Ensures the chat with the recipient is active via switch_to_chat()
    before attempting to send the file.

    Args:
        who (str): The name of the recipient (chat or contact).
        filepath (str): The local path to the file to be sent.
    """
    try:
        if switch_to_chat(who):
            wx.SendFiles(filepath)  # 文档标准文件发送
            print(f"Successfully sent file to {who}: {filepath}")
        else:
            print(f"[ERROR] Cannot send file: Failed to switch to chat with {who}")
    except Exception as e:
        print(f"[ERROR] 文件发送失败 (to {who}, file: {filepath}): {e}")


# FastAPI接口
@app.post("/send/text")
async def api_send_text(req: SendTextRequest):
    """文档标准文本接口"""
    try:
        send_text(req.who, req.message)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))
@app.post("/send/file")


async def api_send_file(req: SendFileRequest):
    """文档标准文件接口"""
    try:
        if not os.path.exists(req.filepath):
            raise HTTPException(404, "文件不存在")
        send_file(req.who, req.filepath)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/upload")
async def api_upload(who: str, file: UploadFile = File(...)):
    """上传+发送文件"""
    try:
        # Ensure the uploads directory exists relative to the script's location
        upload_dir = "./uploads"
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, file.filename)

        with open(save_path, "wb") as f:
            f.write(await file.read())

        send_file(who, save_path)
        return {"status": "success", "saved_path": save_path}
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    # 初始化
    # Ensure the uploads directory exists relative to the script's location for the main block too
    os.makedirs("./uploads", exist_ok=True)

    # 启动监听线程
    threading.Thread(
        target=message_monitor,
        daemon=True,
        name="WeChatListener"
    ).start()

    # 启动服务
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8888,
        log_level="info"
    )
