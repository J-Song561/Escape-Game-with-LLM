from pydantic import BaseModel
from typing import List

class Message(BaseModel):
    role: str       # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    npc: str        # "ella", "louis", "hailey"
    messages: List[Message]
    session_id: str # tracks which player/playthrough

class ChatResponse(BaseModel):
    reply: str
    npc: str