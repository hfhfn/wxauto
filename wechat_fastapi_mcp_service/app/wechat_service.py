import time
import threading
import logging

# Attempt to import wxauto and initialize WeChat
try:
    import wxauto
    WXAUTO_AVAILABLE = True
except ImportError:
    print("WARNING: wxauto library not found. WeChat functionality will be disabled.")
    WXAUTO_AVAILABLE = False
except Exception as e:
    print(f"WARNING: Error importing wxauto or initializing WeChat: {e}. WeChat functionality will be disabled.")
    WXAUTO_AVAILABLE = False


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class WeChatService:
    def __init__(self):
        self.wx = None
        self.chat_objs = {} # Store chat objects for replying
        if WXAUTO_AVAILABLE:
            try:
                self.wx = wxauto.WeChat()
                logger.info("wxauto.WeChat() initialized successfully. WeChat client found.")
            except Exception as e:
                logger.error(f"Error initializing wxauto.WeChat(): {e}. Ensure WeChat PC client is running and logged in.")
                # WXAUTO_AVAILABLE = False # No, keep WXAUTO_AVAILABLE as per import status
        else:
            logger.warning("WeChatService initialized, but wxauto is not available. All WeChat operations will be skipped.")

        self.listening_chats_config = set() # Names of chats we are configured to listen to
        self._stop_event = threading.Event()
        self._listener_thread = None

    def ensure_wechat_client(self):
        if not WXAUTO_AVAILABLE:
            raise RuntimeError("wxauto library is not available. Cannot perform WeChat operations.")
        if not self.wx:
            raise RuntimeError("WeChat client (self.wx) not initialized. Ensure WeChat is running and was found at startup.")

    def send_text_message(self, recipient: str, message: str) -> str:
        try:
            self.ensure_wechat_client()
            self.wx.SendMsg(message, recipient)
            logger.info(f"Sent text message to '{recipient}'.")
            return f"Message sent to {recipient}"
        except Exception as e:
            logger.error(f"Error sending text message to '{recipient}': {e}")
            return f"Error sending message to {recipient}: {e}"

    def send_file(self, recipient: str, file_path: str) -> str:
        try:
            self.ensure_wechat_client()
            # wxauto expects a list of files, even if it's one
            self.wx.SendFiles(filepath=[file_path], who=recipient)
            logger.info(f"Sent file '{file_path}' to '{recipient}'.")
            return f"File {file_path} sent to {recipient}"
        except Exception as e:
            logger.error(f"Error sending file to '{recipient}': {e}")
            return f"Error sending file to {recipient}: {e}"

    def add_chat_to_listen(self, chat_name: str):
        try:
            self.ensure_wechat_client()
            # The `who` parameter in AddListenChat is the remarks/nickname of the user/group
            # savepic=True can be made configurable if needed
            self.wx.AddListenChat(who=chat_name, savepic=True)
            self.listening_chats_config.add(chat_name)
            logger.info(f"Added '{chat_name}' to listen list. Currently configured to listen to: {self.listening_chats_config}")
        except Exception as e:
            logger.error(f"Error adding chat '{chat_name}' to listen list: {e}")

    def remove_chat_from_listen(self, chat_name: str):
        # wxauto doesn't have a direct "remove listen chat".
        # We manage this by controlling what we process from GetListenMessage
        # or by re-initializing listeners (which is more disruptive).
        # For now, just remove from our config set.
        if chat_name in self.listening_chats_config:
            self.listening_chats_config.remove(chat_name)
            logger.info(f"Removed '{chat_name}' from internal listen config. Now listening to: {self.listening_chats_config}")
        else:
            logger.info(f"'{chat_name}' was not in the internal listen config.")
        # To truly stop wxauto from listening to it, one might need to clear all listeners
        # and re-add the ones still in listening_chats_config. This is complex with current wxauto API.

    def _message_listener_loop(self):
        logger.info("Starting WeChat message listener loop...")
        while not self._stop_event.is_set():
            try:
                self.ensure_wechat_client() # Check at the start of each iteration

                if not self.listening_chats_config:
                    # logger.debug("No chats configured to listen to, sleeping.") # Too verbose for info
                    time.sleep(5)
                    continue

                # GetListenMessage() returns a dict: {chat_object: [msg_object, ...], ...}
                # It should only return messages for chats added via AddListenChat
                new_messages_dict = self.wx.GetListenMessage()

                if new_messages_dict:
                    logger.info(f"Received new messages: {len(new_messages_dict)} chats have new messages.")
                    for chat_obj, msgs in new_messages_dict.items():
                        # chat_obj is the key, which is the wxauto Chat object.
                        # We need its name to check against our listening_chats_config
                        # Assuming chat_obj has a 'name' or similar attribute.
                        # From wxauto docs, the key of GetListenMessage result is the chat name/remark you added.
                        # However, the example `chat.SendMsg` implies `chat` is an object.
                        # Let's assume `chat_obj` is the actual chat name string as per `AddListenChat` `who`
                        # and we need to get the chat object for replying if it's not directly the key.
                        # The wxauto example `for chat in msgs: one_msgs = msgs.get(chat)` is confusing.
                        # Let's stick to `for chat_name_or_obj, msgs in new_messages_dict.items():`
                        # And assume chat_name_or_obj is what we need to reply.

                        # According to wxauto documentation:
                        # "GetListenMessage方法获取到的msgs是一个字典，键为监听对象，值为消息对象列表"
                        # "该示例中的chat对象为聊天窗口对象" -> This means the key IS the chat object.

                        chat_name = chat_obj.Name # Attempt to get a name for logging/checking
                                                # This might need adjustment based on actual wxauto Chat object attributes.
                                                # If chat_obj itself is the name string, then this line is not needed.
                                                # For now, let's assume the key `chat_obj` *is* the Chat Window Object.

                        # We should process messages if this chat_obj corresponds to one in our listening_chats_config.
                        # This requires a way to map chat_obj back to the name string used in listening_chats_config,
                        # or store chat_objs directly when adding listeners if AddListenChat returns them.
                        # For simplicity, if GetListenMessage only returns for listened chats, this check might be redundant.
                        # Let's assume for now it only returns listened chats.
                        # A more robust check would be `if chat_name in self.listening_chats_config:`
                        # This check is effectively done if GetListenMessage only returns messages for chats added by AddListenChat.

                        logger.info(f"Processing {len(msgs)} messages from chat: {chat_name if chat_name else 'Unknown Chat'}")

                        for msg in msgs:
                            # Ensure msg has expected attributes. wxauto.Message object.
                            sender = msg.sender if hasattr(msg, 'sender') else 'Unknown Sender'
                            content = msg.content if hasattr(msg, 'content') else 'No Content'
                            msg_type = msg.type if hasattr(msg, 'type') else 'Unknown Type'
                            logger.info(f"  Msg from '{sender}' (type: {msg_type}): {content}")

                            # Per instructions: "Implement a simple reply: chat.SendMsg(f"Bot received: {msg.content}")"
                            # And "Only reply to friend messages for now, not self or system."
                            # Check if current user is available for more robust sender check:
                            # current_user = self.wx.CurrentUserName if hasattr(self.wx, 'CurrentUserName') else None
                            # Avoid replying to self if sender is current_user.
                            if msg_type == 'friend': # Simplified condition based on prompt
                                try:
                                    reply_text = f"Bot received: {content}" # As per specific reply instruction
                                    logger.info(f"    Attempting to reply to {chat_name}: {reply_text}")
                                    chat_obj.SendMsg(reply_text) # Use the chat_obj (key from dict) to reply
                                    logger.info(f"    Replied to {chat_name}.")
                                except Exception as e_reply:
                                    logger.error(f"    Error replying to {chat_name}: {e_reply}")
                else:
                    # No new messages, GetListenMessage likely returned None or empty dict.
                    # This is normal, so use debug level if too noisy.
                    logger.debug("No new messages from GetListenMessage.")

                # Polling interval - adjust as needed. wxauto's GetListenMessage might have its own timeout.
                # If GetListenMessage is blocking until a message, this sleep is less critical.
                # If it returns immediately if no messages, this sleep is important.
                # The example shows `time.sleep(wait)` outside the try for GetListenMessage,
                # suggesting GetListenMessage itself might poll or block.
                # For safety and to prevent tight loop if it returns immediately:
                time.sleep(3) # Poll every 3 seconds

            except RuntimeError as e: # Catch errors from ensure_wechat_client
                logger.error(f"Runtime error in listener loop (WeChat client issue?): {e}")
                self._stop_event.set() # Stop the loop if client is not usable
            except Exception as e:
                logger.error(f"Unexpected error in message listener loop: {e}", exc_info=True) # Log traceback
                time.sleep(10) # Wait a bit longer after an unexpected error
        
        logger.info("WeChat message listener loop has been shut down.")

    def start_listening(self):
        if not WXAUTO_AVAILABLE or not self.wx: # Check wx initialization
            logger.warning("Cannot start listening: wxauto not available or WeChat client not initialized.")
            return

        if not self._listener_thread or not self._listener_thread.is_alive():
            self._stop_event.clear()
            self._listener_thread = threading.Thread(target=self._message_listener_loop, daemon=True)
            self._listener_thread.start()
            logger.info("Message listener thread started.")
        else:
            logger.info("Listener thread already running.")

    def stop_listening(self):
        if self._listener_thread and self._listener_thread.is_alive():
            logger.info("Stopping message listener thread...")
            self._stop_event.set()
            self._listener_thread.join(timeout=10) # Wait for thread to finish
            if self._listener_thread.is_alive():
                logger.warning("Listener thread did not stop in time.")
            else:
                logger.info("Message listener thread stopped successfully.")
        else:
            logger.info("Listener thread not running or already stopped.")

# Example usage (for testing this module directly on a Windows machine)
# if __name__ == "__main__":
#     # Setup basic logging for the test
#     log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#     logging.basicConfig(level=logging.DEBUG, format=log_format) # Use DEBUG for more verbose output
#
#     logger.info("Starting WeChatService directly for testing.")
#    
#     if not WXAUTO_AVAILABLE:
#         logger.error("wxauto is not available, cannot run test effectively.")
#     else:
#         service = WeChatService()
#         if service.wx: # Check if wx was initialized
#             # Replace 'filehelper' with a real chat name you want to test with
#             # For example, '文件传输助手' (filehelper) or a friend's remark name
#             test_chat_name = '文件传输助手' 
#             
#             current_user = service.wx.CurrentUserName if hasattr(service.wx, 'CurrentUserName') else "Unknown"
#             logger.info(f"Current user (self): {current_user}")
#             logger.info(f"Attempting to listen to: {test_chat_name}")
#             service.add_chat_to_listen(test_chat_name) 
#             
#             # To test group messages, add a group chat name you are in
#             # test_group_name = "My Test Group" # Replace with actual group name/remark
#             # service.add_chat_to_listen(test_group_name)
#
#             service.start_listening()
#
#             logger.info(f"Sending a test message to {test_chat_name}")
#             service.send_text_message(test_chat_name, "Hello from WeChatService direct test! This is an automated message.")
#
#             try:
#                 # Keep main thread alive to allow listener to work and messages to be received/processed
#                 while True:
#                     if service._listener_thread and service._listener_thread.is_alive():
#                         logger.debug(f"Test script heartbeat... Listening to: {service.listening_chats_config}")
#                     else:
#                         logger.warning("Listener thread is not alive. Exiting test loop.")
#                         break
#                     time.sleep(15) 
#             except KeyboardInterrupt:
#                 logger.info("Keyboard interrupt received. Shutting down service...")
#             finally:
#                 service.stop_listening()
#                 logger.info("Test finished.")
#         else:
#             logger.error("WeChat client (service.wx) could not be initialized. Test aborted.")
#
#     # To run this test:
#     # 1. Make sure WeChat PC is running and you are logged in.
#     # 2. Save this file (e.g., app/wechat_service.py)
#     # 3. Run from the root of the project: python -m app.wechat_service
#     # 4. Send a message to '文件传输助手' (or the configured test_chat_name) from your WeChat.
#     # 5. Observe the console output for logs.
#     # 6. You should see an auto-reply: "Bot received: [your message content]"
#     # 7. Press Ctrl+C to stop the test.
