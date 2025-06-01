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
# List of chat names to actively monitor using wx.AddListenChat()
# The user should update this list with the exact names of the chats they want the bot to listen to.
CHATS_TO_MONITOR = ["文件传输助手", "测试群"]
SEND_MSG_DELAY_SECONDS = 1.5  # Delay in seconds after switching chat, before sending.


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
def get_new_messages_from_listened_chats():
    """
    Retrieves new messages from chats specified via wx.AddListenChat().

    Calls wx.GetListenMessage() which returns a dictionary where keys are
    chat window objects (e.g., UIAElementInfo) and values are lists of messages.
    Each message can be a SelfMessage, TimeMessage, or a tuple for user/group messages.

    This function processes these messages into a standardized list of dictionaries.
    It attempts to resolve the chat name from the chat window object.

    Returns:
        list: A list of processed message dictionaries, formatted consistently:
              {
                  "who": chat_name,        # Resolved chat name or placeholder
                  "sender": sender_name,   # Sender of the message
                  "message": content,      # Message content
                  "time": timestamp,       # Message time
                  "msgid": message_id      # Message ID
              }
              Returns an empty list if no new messages or an error occurs.
    """
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Function called.")
    processed_messages = []
    try:
        listened_messages_dict = wx.GetListenMessage()
        # Limit log length for very verbose raw output
        raw_output_summary = str(listened_messages_dict)
        if len(raw_output_summary) > 500: # Arbitrary limit for summary
            raw_output_summary = raw_output_summary[:500] + "... (truncated)"
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: wx.GetListenMessage() returned: {raw_output_summary}")

        if not listened_messages_dict:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: wx.GetListenMessage() returned empty or None.")
            return []

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Processing listened_messages_dict. Number of chats with new messages: {len(listened_messages_dict)}")

        for chat_window_obj, messages_list in listened_messages_dict.items():
            chat_name = "UnknownChat" # Default placeholder
            try:
                if hasattr(chat_window_obj, 'who') and chat_window_obj.who: # Check if .who is not empty
                    chat_name = chat_window_obj.who
                elif hasattr(chat_window_obj, 'Name') and chat_window_obj.Name: # Capital N for Name
                    chat_name = chat_window_obj.Name
                elif hasattr(chat_window_obj, 'name') and chat_window_obj.name: # lowercase n for name
                    chat_name = chat_window_obj.name
                else:
                    chat_name = str(chat_window_obj) # Fallback to string representation of the object
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Processing messages for chat object '{str(chat_window_obj)}', resolved name: '{chat_name}'")
            except Exception as e_chat_name:
                print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: Could not get chat name from object {chat_window_obj}: {e_chat_name}")
                # Consider if continuing without a reliable chat_name is appropriate or if this chat should be skipped

            # messages_list here is actually messages_outer_list from the prompt
            if not messages_list:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] get_new_messages_from_listened_chats: No message entries in outer list for chat '{chat_name}'.")
                continue

            # Consistent variable name 'msg_entry' for items in messages_list
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
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Thread started.")
    while True:
        try:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Loop start.")
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Calling get_new_messages_from_listened_chats...")

            new_messages = get_new_messages_from_listened_chats() # Updated function call

            # Updated log to match the new function name
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: get_new_messages_from_listened_chats returned: {new_messages}")

            if not new_messages:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: No new messages returned.")

            if new_messages:
                for msg in new_messages:
                    # print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Processing message: {msg}") # Optional: can be very verbose
                    handle_message(msg)

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Loop end, sleeping for {MESSAGE_MONITOR_INTERVAL_SECONDS}s...")
        except Exception as e:
            print(f"[ERROR] [{time.strftime('%Y-%m-%d %H:%M:%S')}] message_monitor: Exception in loop: {e}") # Enhanced error logging
            # Potentially add a short sleep here too if errors are causing rapid looping
            time.sleep(MESSAGE_MONITOR_INTERVAL_SECONDS) # Ensure sleep even on exception to avoid tight error loops

        time.sleep(MESSAGE_MONITOR_INTERVAL_SECONDS)


def handle_message(msg: dict):
    """
    Processes a single incoming WeChat message.

    The function first checks if the message is from the bot itself.
    Replies are primarily triggered by the presence of `BOT_MENTION_NAME`
    (a global variable, e.g., "@botname") in the message content,
    with specific handling for self-sent messages.

    1.  **If the message is from the bot itself (`msg['sender'] == wx.nickname`):**
        -   It checks if `BOT_MENTION_NAME` is also in the message.
            If yes (intentional self-mention), a reply is generated.
        -   Otherwise (self-message without a mention, likely an echo of a
            previous bot reply or a non-triggering message), it is ignored.

    2.  **If the message is from another sender:**
        -   It checks if `BOT_MENTION_NAME` is in the message.
            If yes, a reply is generated.
        -   Otherwise (message from another user without a mention), it is ignored.

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
    reply = None # Initialize reply for all paths that might use it
    content_lower = actual_message_content.lower() # Lowercase once for efficiency

    if sender_is_self:
        # Message is from the bot itself
        if BOT_MENTION_NAME in actual_message_content:
            print(f"Self-mention detected by {msg['sender']} in chat {msg['who']}: \"{actual_message_content}\". Processing for reply...")
            # Example reply logic for self-mention
            if "hello" in content_lower or "你好" in content_lower:
                reply = f"You mentioned me (yourself, {msg['sender']})! Hello back from {msg['who']}."
            elif "时间" in content_lower:
                reply = f"You (self) asked for the time. It is {time.strftime('%H:%M:%S')}."
            else:
                reply = f"Self-mention: '{actual_message_content}'. Acknowledged."

            if reply:
                send_text(msg["who"], reply)
                print(f"Replied to self-mention from {msg['sender']} in {msg['who']}")
        else:
            # Self-message without self-mention
            print(f"Ignoring self-sent message without @mention (likely echo) from {msg['sender']} in chat {msg['who']}: \"{actual_message_content}\"")
            return
    else:
        # Message is from another user
        if BOT_MENTION_NAME in actual_message_content:
            print(f"Mention from other user {msg['sender']} detected in chat {msg['who']}: \"{actual_message_content}\". Processing for reply...")
            # Example reply logic for mention from others
            if "hello" in content_lower or "你好" in content_lower:
                reply = f"Hello {msg['sender']}! Thanks for mentioning me in {msg['who']}."
            elif "时间" in content_lower:
                reply = f"The current time, as requested by {msg['sender']}, is {time.strftime('%H:%M:%S')}."
            else:
                reply = f"Thanks for the mention, {msg['sender']}! You said: '{actual_message_content}'. How can I assist?"

            if reply:
                send_text(msg["who"], reply)
                print(f"Replied to mention from {msg['sender']} in {msg['who']}")
        else:
            # Message from other user, no mention
            print(f"Ignoring message from other user {msg['sender']} without @mention in chat {msg['who']}: \"{actual_message_content}\"")
            return


# 文档标准消息发送
def send_text(who: str, message: str):
    """
    Sends a text message to the specified recipient.

    Ensures the chat with the recipient is active via switch_to_chat()
    before attempting to send the message. Includes a delay after switching.

    Args:
        who (str): The name of the recipient (chat or contact).
        message (str): The text message to send.
    """
    try:
        if switch_to_chat(who):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] send_text: Switched to chat '{who}', delaying for {SEND_MSG_DELAY_SECONDS}s before sending message...")
            time.sleep(SEND_MSG_DELAY_SECONDS)
            # Attempt to send ESC to clear potential pop-ups/menus
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] send_text: Sending ESC key to chat '{who}' to clear potential pop-ups...")
            try:
                wx.UiaAPI.SendKeys('{ESC}', waitTime=0.2)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] send_text: ESC key sent.")
            except Exception as e_esc:
                print(f"[WARNING] [{time.strftime('%Y-%m-%d %H:%M:%S')}] send_text: Failed to send ESC key: {e_esc}")
            time.sleep(0.1) # Short delay for ESC to take effect

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
    before attempting to send the file. Includes a delay after switching.

    Args:
        who (str): The name of the recipient (chat or contact).
        filepath (str): The local path to the file to be sent.
    """
    try:
        if switch_to_chat(who):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] send_file: Switched to chat '{who}', delaying for {SEND_MSG_DELAY_SECONDS}s before sending file...")
            time.sleep(SEND_MSG_DELAY_SECONDS)
            # Attempt to send ESC to clear potential pop-ups/menus
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] send_file: Sending ESC key to chat '{who}' to clear potential pop-ups...")
            try:
                wx.UiaAPI.SendKeys('{ESC}', waitTime=0.2)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] send_file: ESC key sent.")
            except Exception as e_esc:
                print(f"[WARNING] [{time.strftime('%Y-%m-%d %H:%M:%S')}] send_file: Failed to send ESC key: {e_esc}")
            time.sleep(0.1) # Short delay for ESC to take effect

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

    # Initialize listened chats
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Initializing listened chats...")
    if CHATS_TO_MONITOR:
        for chat_name in CHATS_TO_MONITOR:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Main: Attempting to add chat '{chat_name}' to listen list.")
            try:
                wx.AddListenChat(chat_name, savepic=False) # savepic=False is often a good default
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
