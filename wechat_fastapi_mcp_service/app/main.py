import logging
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

from app.wechat_service import WeChatService, WXAUTO_AVAILABLE
from app.api_models import SendTextBody, SendFileBody, ListenChatBody
from app.mcp_service import get_mcp_server # Import for MCP service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

wechat_service = WeChatService()
mcp_server_instance = get_mcp_server(wechat_service)
# This path is where the MCP protocol itself will be served, relative to the mount point.
mcp_asgi_app = mcp_server_instance.http_app(path="/protocol") 

@asynccontextmanager
async def app_lifespan(current_app: FastAPI): # Parameter name changed to current_app to avoid conflict
    logger.info("Application startup: Initializing WeChatService listener...")
    if WXAUTO_AVAILABLE and wechat_service.wx:
        default_chat_to_listen = "文件传输助手"
        logger.info(f"Adding default chat '{default_chat_to_listen}' to listener.")
        wechat_service.add_chat_to_listen(default_chat_to_listen)
        wechat_service.start_listening()
    else:
        logger.warning("App startup: wxauto not available or WeChat client not initialized. Listener not started.")
    
    yield # Application is running
    
    logger.info("Application shutdown: Stopping WeChatService listener...")
    if WXAUTO_AVAILABLE and wechat_service.wx:
        wechat_service.stop_listening()

app = FastAPI(lifespan=app_lifespan) # Use the app_lifespan for the main FastAPI app
# Mount the MCP app. Its own internal lifespan events should be managed by Starlette/FastAPI.
# The MCP tools will be available at /mcp_bridge/protocol/... (e.g. /mcp_bridge/protocol/@tool_name)
app.mount("/mcp_bridge", mcp_asgi_app) 

# Helper function to handle WeChat service errors
def handle_wechat_service_errors(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except RuntimeError as e:
        logger.error(f"WeChat service runtime error: {e}")
        raise HTTPException(status_code=503, detail=f"WeChat Service Error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# --- Standard FastAPI Endpoints ---
@app.get("/")
async def root():
    return {"message": "WeChat FastAPI & MCP Service is running."}

@app.post("/wechat/send_text")
async def send_text(payload: SendTextBody):
    logger.info(f"Received request to send text to: {payload.recipient}")
    result = handle_wechat_service_errors(wechat_service.send_text_message, payload.recipient, payload.message)
    return {"status": "success", "details": result}

@app.post("/wechat/send_file")
async def send_file_api(payload: SendFileBody):
    logger.info(f"Received request to send file to: {payload.recipient} path: {payload.file_path}")
    result = handle_wechat_service_errors(wechat_service.send_file, payload.recipient, payload.file_path)
    return {"status": "success", "details": result}

@app.post("/wechat/listen/add")
async def add_listen_chat_api(payload: ListenChatBody):
    logger.info(f"Received request to add chat to listen: {payload.chat_name}")
    handle_wechat_service_errors(wechat_service.add_chat_to_listen, payload.chat_name)
    return {"status": "success", "message": f"Chat '{payload.chat_name}' added to listen list."}

@app.post("/wechat/listen/remove")
async def remove_listen_chat_api(payload: ListenChatBody):
    logger.info(f"Received request to remove chat from listen: {payload.chat_name}")
    handle_wechat_service_errors(wechat_service.remove_chat_from_listen, payload.chat_name)
    return {"status": "success", "message": f"Chat '{payload.chat_name}' removed from listen list."}

@app.get("/wechat/listen/list")
async def list_listening_chats_api():
    logger.info("Received request to list listening chats.")
    chats = handle_wechat_service_errors(lambda: list(wechat_service.listening_chats_config))
    return {"status": "success", "listening_chats": chats}

@app.get("/wechat/status")
async def get_wechat_status():
    logger.info("Received request for WeChat service status.")
    if not WXAUTO_AVAILABLE:
        return {"status": "wxauto_unavailable", "message": "wxauto library not found."}
    if not wechat_service.wx: 
        return {"status": "wechat_client_not_initialized", "message": "WeChat client (service.wx) not initialized."}
    
    listener_alive = wechat_service._listener_thread is not None and wechat_service._listener_thread.is_alive()
    return {
        "status": "ok",
        "wxauto_available": WXAUTO_AVAILABLE,
        "wechat_client_initialized": True, 
        "listener_thread_active": listener_alive,
        "listening_to_chats": list(wechat_service.listening_chats_config)
    }
    
# Uvicorn startup block
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server directly for app.main...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
