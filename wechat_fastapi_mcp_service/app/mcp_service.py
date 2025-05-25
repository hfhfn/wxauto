import logging
from fastmcp import FastMCP
from app.wechat_service import WeChatService # For type hinting

logger = logging.getLogger(__name__)

def get_mcp_server(wechat_service: WeChatService) -> FastMCP:
    mcp_server = FastMCP(
        name="WeChatMCPBridge",
        description="MCP Server to interact with WeChat via wxauto"
    )

    @mcp_server.tool()
    def mcp_send_wechat_text(recipient: str, text: str) -> str:
        """Sends a text message to a WeChat contact/group via MCP."""
        logger.info(f"MCP Tool: mcp_send_wechat_text called for recipient '{recipient}'.")
        if not wechat_service: # Should not happen if initialized correctly
            logger.error("MCP Tool: WeChatService not available.")
            return "Error: WeChatService not available in MCP service."
        try:
            return wechat_service.send_text_message(recipient, text)
        except RuntimeError as e:
            logger.error(f"MCP Tool: Runtime error calling send_text_message: {e}")
            return f"Error from WeChat Service: {e}"
        except Exception as e:
            logger.error(f"MCP Tool: Unexpected error in send_text_message: {e}")
            return f"Unexpected error: {e}"

    @mcp_server.tool()
    def mcp_send_wechat_file(recipient: str, file_path: str) -> str:
        """Sends a file to a WeChat contact/group via MCP."""
        logger.info(f"MCP Tool: mcp_send_wechat_file called for recipient '{recipient}', path '{file_path}'.")
        if not wechat_service:
            logger.error("MCP Tool: WeChatService not available.")
            return "Error: WeChatService not available in MCP service."
        try:
            return wechat_service.send_file(recipient, file_path)
        except RuntimeError as e:
            logger.error(f"MCP Tool: Runtime error calling send_file: {e}")
            return f"Error from WeChat Service: {e}"
        except Exception as e:
            logger.error(f"MCP Tool: Unexpected error in send_file: {e}")
            return f"Unexpected error: {e}"

    @mcp_server.tool()
    def mcp_get_listening_chats() -> list[str]:
        """Gets the list of chats currently being listened to by the WeChat service via MCP."""
        logger.info("MCP Tool: mcp_get_listening_chats called.")
        if not wechat_service:
            logger.error("MCP Tool: WeChatService not available.")
            return ["Error: WeChatService not available in MCP service."]
        try:
            # listening_chats_config is a set, convert to list for MCP return
            return list(wechat_service.listening_chats_config)
        except RuntimeError as e: # Should not happen for accessing a property, but good for consistency
            logger.error(f"MCP Tool: Runtime error accessing listening_chats_config: {e}")
            return [f"Error from WeChat Service: {e}"]
        except Exception as e:
            logger.error(f"MCP Tool: Unexpected error in mcp_get_listening_chats: {e}")
            return [f"Unexpected error: {e}"]
            
    @mcp_server.tool()
    def mcp_add_chat_to_listen(chat_name: str) -> str:
        """Adds a chat to the listen list via MCP."""
        logger.info(f"MCP Tool: mcp_add_chat_to_listen called for chat_name '{chat_name}'.")
        if not wechat_service:
            logger.error("MCP Tool: WeChatService not available.")
            return "Error: WeChatService not available in MCP service."
        try:
            wechat_service.add_chat_to_listen(chat_name)
            return f"Chat '{chat_name}' added to listen list."
        except RuntimeError as e:
            logger.error(f"MCP Tool: Runtime error calling add_chat_to_listen: {e}")
            return f"Error from WeChat Service: {e}"
        except Exception as e:
            logger.error(f"MCP Tool: Unexpected error in add_chat_to_listen: {e}")
            return f"Unexpected error: {e}"

    @mcp_server.tool()
    def mcp_remove_chat_from_listen(chat_name: str) -> str:
        """Removes a chat from the listen list via MCP."""
        logger.info(f"MCP Tool: mcp_remove_chat_from_listen called for chat_name '{chat_name}'.")
        if not wechat_service:
            logger.error("MCP Tool: WeChatService not available.")
            return "Error: WeChatService not available in MCP service."
        try:
            wechat_service.remove_chat_from_listen(chat_name)
            return f"Chat '{chat_name}' removed from listen list."
        except RuntimeError as e:
            logger.error(f"MCP Tool: Runtime error calling remove_chat_from_listen: {e}")
            return f"Error from WeChat Service: {e}"
        except Exception as e:
            logger.error(f"MCP Tool: Unexpected error in mcp_remove_chat_from_listen: {e}")
            return f"Unexpected error: {e}"

    return mcp_server

# Note: The FastMCP app instance (ASGI app) will be created from this server
# in main.py and then mounted.
