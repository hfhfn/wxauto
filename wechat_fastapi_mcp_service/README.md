# WeChat FastAPI & MCP Service

## Overview

This service provides a bridge to interact with the WeChat Desktop client on Windows. It uses `wxauto` for automating WeChat actions and exposes this functionality through:

1.  A **FastAPI** web server with HTTP endpoints for common WeChat operations.
2.  A **FastMCP** (Fast Model Control Protocol) service, allowing programmatic interaction with WeChat functions as tools, suitable for integration with LLMs or other automated systems.

The service can send text messages, files, manage a list of chats to listen to, and automatically reply to messages received in listened chats.

## Prerequisites

*   **Operating System:** Windows (due to `wxauto`'s reliance on Windows UI automation).
*   **WeChat Client:** WeChat Desktop for Windows client installed, running, and logged in.
    *   Ensure the WeChat version is compatible with the installed `wxauto` version. Refer to the [`wxauto` documentation](https://github.com/cluic/wxauto) for compatibility details.
*   **Python:** Python 3.8+ is recommended.
*   **Package Manager:** `pip` (Python's package installer) or `uv` (a fast Python package installer and resolver).

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd wechat_fastapi_mcp_service
    ```

2.  **Create and Activate a Virtual Environment:**
    *   Using `venv` (standard Python):
        ```bash
        python -m venv .venv
        # On Windows (cmd.exe)
        .venv\Scripts\activate
        # On Windows (PowerShell)
        .venv\Scripts\Activate.ps1
        ```
    *   (Optional) Using `uv`:
        ```bash
        uv venv
        # On Windows (cmd.exe)
        .venv\Scripts\activate
        # On Windows (PowerShell)
        .venv\Scripts\Activate.ps1
        ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    # Or using uv
    # uv pip install -r requirements.txt
    ```

4.  **Environment Configuration (Recommended):**
    Create a `.env` file in the project root directory (`wechat_fastapi_mcp_service/.env`) to manage configurations. This file should be added to `.gitignore`.
    Example `.env` content:
    ```env
    DEFAULT_LISTEN_CHAT="文件传输助手"
    # SERVER_HOST="0.0.0.0"
    # SERVER_PORT="8000"
    ```
    *   `DEFAULT_LISTEN_CHAT`: Specifies the default chat to listen to when the service starts (e.g., "文件传输助手" for File Transfer Helper).

## Running the Service

1.  **Ensure WeChat is Running:** The WeChat Desktop client must be running and you must be logged into your account on the same Windows machine where the service will run.

2.  **Start the Service:**
    Open a terminal/command prompt, activate the virtual environment, and run:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```
    *   `--host 0.0.0.0`: Makes the service accessible from other devices on your network.
    *   `--port 8000`: Specifies the port to run on.
    *   `--reload`: Enables auto-reloading for development. Uvicorn will watch for file changes and restart the server. Remove this flag for production use.

    The service will load environment variables from the `.env` file if it exists.

## Project Structure

*   `app/`
    *   `main.py`: The main FastAPI application. Initializes the `WeChatService`, defines FastAPI HTTP endpoints, manages the application lifecycle (startup/shutdown of WeChat listener), and mounts the FastMCP service.
    *   `wechat_service.py`: Contains the `WeChatService` class, which encapsulates all core logic for interacting with WeChat using the `wxauto` library. Handles message sending, file sending, and message listening/replying.
    *   `mcp_service.py`: Defines the `get_mcp_server` function that creates and configures the FastMCP server instance. It registers MCP tools that wrap `WeChatService` functionalities.
    *   `api_models.py`: Contains Pydantic models used for request and response body validation in the FastAPI endpoints.
    *   `__init__.py`: Makes the `app` directory a Python package.
*   `requirements.txt`: Lists all Python dependencies for the project.
*   `.env` (optional, gitignored): Used to store environment variables for configuration (e.g., `DEFAULT_LISTEN_CHAT`).
*   `README.md`: This file.

## FastAPI Endpoints

The following HTTP endpoints are provided by the service:

*   **`GET /`**
    *   Description: Root endpoint, returns a welcome message.
    *   Request Body: None.
    *   Response: JSON object with a welcome message.

*   **`GET /wechat/status`**
    *   Description: Provides the current status of the WeChat integration, including `wxauto` availability, WeChat client initialization, listener thread status, and the list of currently listened chats.
    *   Request Body: None.
    *   Response: JSON object detailing the service status.

*   **`POST /wechat/send_text`**
    *   Description: Sends a text message to a specified WeChat recipient (contact or group).
    *   Request Body (JSON):
        ```json
        {
            "recipient": "RecipientNameOrRemark",
            "message": "Your message content"
        }
        ```
    *   Response: JSON confirmation or error.

*   **`POST /wechat/send_file`**
    *   Description: Sends a file to a specified WeChat recipient. The file must be accessible by the server.
    *   Request Body (JSON):
        ```json
        {
            "recipient": "RecipientNameOrRemark",
            "file_path": "C:/path/to/your/file.txt"
        }
        ```
    *   Response: JSON confirmation or error.

*   **`POST /wechat/listen/add`**
    *   Description: Adds a specified chat (by remark name or group chat name) to the message listener. The service will then attempt to process and reply to messages from this chat.
    *   Request Body (JSON):
        ```json
        {
            "chat_name": "ChatNameOrRemarkToListen"
        }
        ```
    *   Response: JSON confirmation.

*   **`POST /wechat/listen/remove`**
    *   Description: Removes a chat from the message listener.
    *   Request Body (JSON):
        ```json
        {
            "chat_name": "ChatNameOrRemarkToRemove"
        }
        ```
    *   Response: JSON confirmation.

*   **`GET /wechat/listen/list`**
    *   Description: Returns a list of all chat names currently being listened to by the service.
    *   Request Body: None.
    *   Response: JSON array of chat names.

## FastMCP Service & Tools

The FastMCP service allows for more direct programmatic interaction with the WeChat functionalities, suitable for agentic systems or scripts.

*   **MCP Service Mount Point:** The FastMCP ASGI application is mounted under the main FastAPI app at `/mcp_bridge`.
*   **MCP Protocol Endpoint:** The actual MCP protocol endpoint (where MCP clients should connect) is:
    `http://<server_address>:<port>/mcp_bridge/protocol`
    (e.g., `http://localhost:8000/mcp_bridge/protocol` if running locally).

The following tools are available via the FastMCP service:

*   **`mcp_send_wechat_text(recipient: str, text: str) -> str`**
    *   Description: Sends a text message to the specified WeChat recipient.
    *   Parameters:
        *   `recipient` (str): The remark name of the contact or the name of the group chat.
        *   `text` (str): The message content to send.
    *   Returns: A string indicating the outcome (e.g., "Message sent to {recipient}" or an error message).

*   **`mcp_send_wechat_file(recipient: str, file_path: str) -> str`**
    *   Description: Sends a file to the specified WeChat recipient. The file path must be accessible by the server.
    *   Parameters:
        *   `recipient` (str): The remark name of the contact or the name of the group chat.
        *   `file_path` (str): The absolute path to the file on the server.
    *   Returns: A string indicating the outcome.

*   **`mcp_get_listening_chats() -> list[str]`**
    *   Description: Retrieves a list of chat names currently being monitored by the message listener.
    *   Parameters: None.
    *   Returns: A list of strings, where each string is a chat name.

*   **`mcp_add_chat_to_listen(chat_name: str) -> str`**
    *   Description: Adds a chat to the message listener.
    *   Parameters:
        *   `chat_name` (str): The remark name or group chat name to start listening to.
    *   Returns: A string indicating the outcome.

*   **`mcp_remove_chat_from_listen(chat_name: str) -> str`**
    *   Description: Removes a chat from the message listener.
    *   Parameters:
        *   `chat_name` (str): The remark name or group chat name to stop listening to.
    *   Returns: A string indicating the outcome.

## Important Notes & Limitations

*   **Windows Dependency:** This service *must* run on a Windows machine because `wxauto` performs UI automation of the WeChat for Windows desktop client.
*   **WeChat Client Requirement:** The WeChat PC client must be running and the user must be logged in for the service to function. The service interacts with the *currently logged-in user's WeChat instance*.
*   **UI Automation Fragility:** `wxauto` relies on the structure of the WeChat client's user interface. Updates to the WeChat client may break `wxauto`'s functionality, potentially requiring updates to `wxauto` or this service.
*   **Single User Instance:** The service automates one instance of WeChat. It cannot manage multiple WeChat accounts simultaneously on the same machine.
*   **Auto-Reply Logic:** The current auto-reply logic in `wechat_service.py` is basic (replies "Bot received: {message_content}" to messages from 'friend' type contacts in listened chats). This can be customized or extended as needed.
*   **Error Handling:** While basic error handling is in place, real-world scenarios might present more complex situations. Review logs for detailed error information.
*   **Security:** Be mindful of the security implications of exposing WeChat automation capabilities, especially over a network. Ensure appropriate network security measures are in place if the service is accessible outside of localhost. Consider adding authentication to the API if needed.

This README should now provide a comprehensive guide for users of the service.
