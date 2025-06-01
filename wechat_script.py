import time
import threading
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from wxauto import WeChat
import os
import uvicorn

app = FastAPI(title="WeChat Automation Service")
wx = WeChat()

# Global configuration
BOT_MENTION_NAME = "@botname"  # User should change this to their bot's actual mention name
# List of chat names to actively monitor using wx.AddListenChat()
# The user should update this list with the exact names of the chats they want the bot to listen to.
CHATS_TO_MONITOR = ["文件传输助手", "测试群"]
MESSAGE_MONITOR_INTERVAL_SECONDS = 5  # Interval for message checking loop
SEND_MSG_DELAY_SECONDS = 1.5  # Delay after switching chat, before sending.


# 消息状态跟踪
class MessageTracker:
    def __init__(self):
        self.last_msg_content = ""
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
# Removed get_recent_messages function

def get_new_messages_from_listened_chats():
    """
    Retrieves new messages from chats specified via wx.AddListenChat().

    Calls wx.GetListenMessage() which returns a dictionary where keys are
    chat window objects (e.g., UIAElementInfo) and values are lists of messages.
    The primary expected format for these messages is a list: ['SenderName'/'Self', 'ContentString'].
    However, it also includes robust handling for older/alternative formats like
    SelfMessage objects, TimeMessage objects, and 4-element/2-element tuples,
    though these are treated as less standard for GetListenMessage.

    This function processes these messages into a standardized list of dictionaries.
    It attempts to resolve the chat name from the chat window object.

    Returns:
        list: A list of processed message dictionaries, formatted consistently:
              {
                  "who": chat_name,        # Resolved chat name or placeholder
                  "sender": sender_name,   # Sender of the message
                  "message": content,      # Message content
                  "time": timestamp,       # Message time (approximated for list format)
                  "msgid": message_id      # Message ID (generated for list format)
              }
              Returns an empty list if no new messages or an error occurs.
    """
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Function called.")
    processed_messages = []
    try:
        listened_messages_dict = wx.GetListenMessage()
        raw_output_summary = str(listened_messages_dict)
        if len(raw_output_summary) > 500:
            raw_output_summary = raw_output_summary[:500] + "... (truncated)"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: wx.GetListenMessage() returned: {raw_output_summary}")

        if not listened_messages_dict:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: wx.GetListenMessage() returned empty or None.")
            return []

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Processing listened_messages_dict. Number of chats with new messages: {len(listened_messages_dict)}")

        for chat_window_obj, messages_list in listened_messages_dict.items():
            chat_name = "UnknownChat"
            try:
                if hasattr(chat_window_obj, 'who') and chat_window_obj.who:
                    chat_name = chat_window_obj.who
                elif hasattr(chat_window_obj, 'Name') and chat_window_obj.Name:
                    chat_name = chat_window_obj.Name
                elif hasattr(chat_window_obj, 'name') and chat_window_obj.name:
                    chat_name = chat_window_obj.name
                else:
                    chat_name = str(chat_window_obj)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Processing messages for chat object '{str(chat_window_obj)}', resolved name: '{chat_name}'")
            except Exception as e_chat_name:
                print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Could not get chat name from object {chat_window_obj}: {e_chat_name}")

            if not messages_list:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: No message entries in outer list for chat '{chat_name}'.")
                continue

            for msg_entry in messages_list:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Raw msg_entry for chat '{chat_name}': {msg_entry} (type: {type(msg_entry)})")

                if isinstance(msg_entry, list) and len(msg_entry) == 2:
                    sender_identifier = msg_entry[0]
                    message_content = msg_entry[1]
                    actual_sender = wx.nickname if sender_identifier == 'Self' else sender_identifier
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                    msg_id = f"listenmsg_list_{int(time.time() * 1000)}_{hash(message_content + actual_sender)}"

                    processed_messages.append({
                        "who": chat_name, "sender": actual_sender, "message": message_content,
                        "time": timestamp, "msgid": msg_id
                    })
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: [DEBUG] Processed list-based entry from '{actual_sender}' in '{chat_name}': {message_content}")

                elif isinstance(msg_entry, SelfMessage):
                    try:
                        sender = msg_entry.Sender if hasattr(msg_entry, 'Sender') and msg_entry.Sender else wx.nickname
                        content = msg_entry.Content if hasattr(msg_entry, 'Content') else str(msg_entry)
                        time_val = msg_entry.Time if hasattr(msg_entry, 'Time') else "Unknown Time"
                        msgid_fallback = f"selfmsg_obj_{int(time.time() * 1000)}_{hash(str(msg_entry))}"
                        msgid = msg_entry.MsgId if hasattr(msg_entry, 'MsgId') else msgid_fallback

                        processed_messages.append({
                            "who": chat_name, "sender": sender, "message": content,
                            "time": time_val, "msgid": msgid
                        })
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: [DEBUG] Processed SelfMessage object from {sender} in {chat_name}: {content}")
                    except Exception as e_sm:
                        print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Error processing SelfMessage object: {e_sm}. Object: {msg_entry}")

                elif isinstance(msg_entry, TimeMessage):
                    try:
                        time_val = msg_entry.Time if hasattr(msg_entry, 'Time') else str(msg_entry)
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: [DEBUG] Skipping TimeMessage object in chat {chat_name}: {time_val}")
                    except Exception as e_tm:
                        print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Error processing TimeMessage object: {e_tm}. Object: {msg_entry}")

                elif isinstance(msg_entry, tuple):
                    if len(msg_entry) == 4:
                        processed_messages.append({
                            "who": chat_name, "sender": msg_entry[0], "message": msg_entry[1],
                            "time": msg_entry[2], "msgid": msg_entry[3]
                        })
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: [DEBUG] Processed 4-elem tuple from chat {chat_name}.")
                    elif len(msg_entry) == 2:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: [DEBUG] Skipping 2-elem time marker tuple in chat {chat_name}: {msg_entry}")
                    else:
                        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: [DEBUG] Skipping non-standard length tuple in chat {chat_name} (length {len(msg_entry)}): {msg_entry}")

                else:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: [DEBUG] Skipping unknown or unhandled message entry type {type(msg_entry)} in chat '{chat_name}': {msg_entry}")

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Function end. Returning {len(processed_messages)} processed messages.")
        return processed_messages
    except Exception as e:
        print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Exception in function: {e}")
        return []


def switch_to_chat(who: str):
    """切换聊天窗口（文档标准做法）"""
    if who != tracker.current_chat:
        wx.ChatWith(who)  # 先切换到目标聊天
        tracker.current_chat = who
        time.sleep(0.3)  # 等待窗口切换完成


# 消息监听服务
def message_monitor():
    """Continuously monitors for new WeChat messages and processes them."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Thread started.")
    while True:
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Loop start.")
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Calling get_new_messages_from_listened_chats...")

            new_messages = get_new_messages_from_listened_chats()

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: get_new_messages_from_listened_chats returned: {new_messages}")

            if not new_messages:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: No new messages returned.")
            else:
                for msg_dict in new_messages:
                    process_and_reply_to_message(msg_dict) # Updated function call

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Loop end, sleeping for {MESSAGE_MONITOR_INTERVAL_SECONDS}s...")
        except Exception as e:
            print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Exception in loop: {e}")
            time.sleep(MESSAGE_MONITOR_INTERVAL_SECONDS)

        time.sleep(MESSAGE_MONITOR_INTERVAL_SECONDS)


def process_and_reply_to_message(msg: dict):
    """
    Processes a message for @mentions, handles echo prevention,
    and generates replies prepended with @sender.
    """
    actual_message_content = msg.get("message", "")
    sender_name = msg.get("sender", "UnknownSender")
    chat_name = msg.get("who", "UnknownChat")

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Received from {sender_name} in {chat_name}: '{actual_message_content}'")

    if sender_name == wx.nickname:
        if BOT_MENTION_NAME in actual_message_content:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Self-mention detected from {sender_name}. Processing for reply...")
            # Proceed to reply generation (logic block below)
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Ignoring self-sent message without @mention (likely echo or non-triggering): '{actual_message_content}'")
            return
    # Message is from someone else (not wx.nickname)
    elif BOT_MENTION_NAME in actual_message_content and f"@{sender_name}" in actual_message_content:
        # This message is from someone else, contains @bot, and also contains @sender_name.
        # This is highly indicative of the bot's own reply being quoted or immediately re-processed.
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Probable echo of bot's reply to {sender_name} detected. Message: '{actual_message_content}'. Ignoring.")
        return
    elif BOT_MENTION_NAME in actual_message_content:
        # Standard mention from another user.
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Mention from {sender_name} in {chat_name}: '{actual_message_content}'. Processing for reply...")
        # Proceed to reply generation (logic block below)
    else:
        # No @mention from another user.
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Message from {sender_name} in {chat_name} did not contain mention ('{BOT_MENTION_NAME}'). Ignoring.")
        return

    # --- Reply Logic Block (only reached if conditions above pass) ---
    base_reply = None
    content_to_check = actual_message_content.lower()

    if "hello" in content_to_check or "你好" in content_to_check:
        base_reply = "你好！我是自动回复"
    elif "时间" in content_to_check:
        base_reply = time.strftime("现在是%H:%M:%S")
    else:
        base_reply = "我收到了你的@信息。"

    if base_reply:
        final_reply = f"@{sender_name} {base_reply}"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Sending reply to {chat_name} (for {sender_name}): '{final_reply}'")
        send_text(chat_name, final_reply)
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] process_and_reply_to_message: Mention from {sender_name} processed, but no base_reply was generated.")


# 文档标准消息发送
def send_text(who: str, message: str):
    try:
        switch_to_chat(who)
        wx.SendMsg(message)  # 文档标准发送方法
        print(f"已回复 {who}: {message}")
    except Exception as e:
        print(f"[ERROR] 发送失败: {e}")


def send_file(who: str, filepath: str):
    try:
        switch_to_chat(who)
        wx.SendFiles(filepath)  # 文档标准文件发送
    except Exception as e:
        print(f"[ERROR] 文件发送失败: {e}")


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
        # User's original path for uploads
        os.makedirs("../uploads", exist_ok=True)
        save_path = f"../uploads/{file.filename}" # User's original path
        with open(save_path, "wb") as f:
            f.write(await file.read())

        send_file(who, save_path)
        return {"status": "success", "saved_path": save_path}
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    # 初始化
    # User's original path for uploads in main
    os.makedirs("../uploads", exist_ok=True)

    # Initialize listened chats
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Initializing listened chats...")
    if CHATS_TO_MONITOR:
        for chat_name in CHATS_TO_MONITOR:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Attempting to add chat '{chat_name}' to listen list.")
            try:
                wx.AddListenChat(chat_name, savepic=False)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Successfully added '{chat_name}' to listen list.")
            except Exception as e:
                print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Failed to add chat '{chat_name}' to listen list: {e}")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: CHATS_TO_MONITOR list is empty. No chats specifically added to listen list via AddListenChat().")
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Finished initializing listened chats.")

    # 启动监听线程
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Starting message_monitor thread...")
    threading.Thread(
        target=message_monitor,
        daemon=True,
        name="WeChatListener"
    ).start()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: message_monitor thread started.")

    # 启动服务
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Starting FastAPI service on 0.0.0.0:8888...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8888,
        log_level="info"
    )
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: FastAPI service stopped.")
