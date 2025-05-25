from pydantic import BaseModel
from typing import Optional

class SendTextBody(BaseModel):
    recipient: str
    message: str

class SendFileBody(BaseModel):
    recipient: str
    file_path: str # Assuming server has access to this path

class ListenChatBody(BaseModel):
    chat_name: str
