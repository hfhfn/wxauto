import time
import threading
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from wxauto import WeChat
from wxauto.elements import SelfMessage, TimeMessage
# Attempt to import SelfMessage and TimeMessage.
# If other specific message classes like UserMessage, GroupChatMessage are known from elements.py,
# they could be added too, but SelfMessage is confirmed from the debug log.
# We'll start with these two for now.
import os
import uvicorn

app = FastAPI(title="WeChat Automation Service")
wx = WeChat()

# Global configuration
MESSAGE_MONITOR_INTERVAL_SECONDS = 5  # Default interval for message checking: 5 seconds
BOT_MENTION_NAME = "@botname"  # IMPORTANT: User should change this to the bot's actual mention name in WeChat


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
            for msg_entry in messages_list:
                if isinstance(msg_entry, SelfMessage):
                    try:
                        sender = msg_entry.Sender if hasattr(msg_entry, 'Sender') else wx.nickname
                        content = msg_entry.Content if hasattr(msg_entry, 'Content') else str(msg_entry)
                        time_val = msg_entry.Time if hasattr(msg_entry, 'Time') else "Unknown Time"
                        # Ensure msgid is unique enough for potential future use if needed for deduplication
                        msgid_fallback = f"selfmsg_{int(time.time() * 1000)}_{hash(content)}"
                        msgid = msg_entry.MsgId if hasattr(msg_entry, 'MsgId') else msgid_fallback

                        processed_messages.append({
                            "who": chat_name,  # 'who' is the chat context (e.g., group name or other contact)
                            "sender": sender,  # actual sender, which is self
                            "message": content,
                            "time": time_val,
                            "msgid": msgid
                        })
                        print(f"[DEBUG] Processed SelfMessage from {sender} in chat {chat_name}: {content}")
                    except AttributeError as e:
                        print(f"[ERROR] AttributeError while processing SelfMessage object: {e}. Object: {msg_entry}")
                    except Exception as e:
                        print(f"[ERROR] Unexpected error while processing SelfMessage object: {e}. Object: {msg_entry}")

                elif isinstance(msg_entry, TimeMessage):
                    try:
                        time_val = msg_entry.Time if hasattr(msg_entry, 'Time') else str(msg_entry)
                        print(f"[DEBUG] Skipping TimeMessage object in chat {chat_name}: {time_val}")
                    except AttributeError as e:
                        print(f"[ERROR] AttributeError while processing TimeMessage object: {e}. Object: {msg_entry}")
                    except Exception as e:
                        print(f"[ERROR] Unexpected error while processing TimeMessage object: {e}. Object: {msg_entry}")

                elif isinstance(msg_entry, tuple):
                    if len(msg_entry) == 4:
                        # Standard message tuple: (sender_in_chat, content, time, msg_id)
                        processed_messages.append({
                            "who": chat_name,
                            "sender": msg_entry[0],
                            "message": msg_entry[1],
                            "time": msg_entry[2],
                            "msgid": msg_entry[3]
                        })
                    elif len(msg_entry) == 2:
                        # Likely a time marker tuple (Datetime_object, msgid)
                        print(f"[DEBUG] Skipping time marker tuple in chat {chat_name}: {msg_entry}")
                    else:
                        # Other non-standard tuples
                        print(f"[DEBUG] Skipping non-standard message tuple of length {len(msg_entry)} in chat {chat_name}: {msg_entry}")
                else:
                    # Fallback for any other types not explicitly handled
                    print(f"[DEBUG] Skipping unknown message entry type {type(msg_entry)} in chat {chat_name}: {msg_entry}")

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
        time.sleep(MESSAGE_MONITOR_INTERVAL_SECONDS)


def handle_message(msg: dict):
    """
    Processes a single incoming WeChat message based on @mentions.

    The primary trigger for a reply is the presence of `BOT_MENTION_NAME`
    (a global variable, e.g., "@botname") in the message content.

    - If `BOT_MENTION_NAME` is found:
        The message is processed for a potential reply. (Current logic is example-based).
    - If `BOT_MENTION_NAME` is NOT found:
        - If the message is from the bot itself (`msg['sender'] == wx.nickname`),
          it is ignored to prevent processing echoes of its own statements.
        - If the message is from another sender and does not contain the mention,
          it is also ignored.

    Args:
        msg (dict): A dictionary containing message details:
            - "who" (str): The chat session name (e.g., group name or contact name).
            - "sender" (str): The actual sender of the message within the chat.
            - "message" (str): The content of the message.
            - "time" (str): The timestamp of the message.
            - "msgid" (str): The unique ID of the message.
    """
    # msg format: {"who": chat_name, "sender": sender_in_chat, "message": content, "time": time, "msgid": msg_id}

    actual_message_content = msg["message"]
    sender_is_self = msg['sender'] == wx.nickname

    if BOT_MENTION_NAME in actual_message_content:
        print(f"Bot was mentioned by {msg['sender']} in chat {msg['who']}: \"{actual_message_content}\". Processing for reply...")

        reply = None
        content_lower = actual_message_content.lower() # Use the actual message content

        if "hello" in content_lower or "你好" in content_lower:
            reply = f"Hello {msg['sender']}! You mentioned me in {msg['who']} with '{actual_message_content}'."
        elif "时间" in content_lower:
            reply = f"Mentioned about time! The current time is {time.strftime('%H:%M:%S')}."
        else:
            reply = f"You mentioned me, {msg['sender']}, in {msg['who']}! Message: '{actual_message_content}'. How can I help?"

        if reply:
            send_text(msg["who"], reply)
            print(f"Replied to @mention from {msg['sender']} in {msg['who']}")

    elif sender_is_self:
        # Message is from self, but NO @mention was found.
        print(f"Ignoring self-sent message without @mention from {msg['sender']} in chat {msg['who']}: \"{actual_message_content}\"")
        return

    else:
        # Message is from someone else, and NO @mention was found.
        print(f"Ignoring message from {msg['sender']} in chat {msg['who']} (no @mention): \"{actual_message_content}\"")
        return


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
