from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime

# Пользователи
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    
    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters')
        return v

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar: str
    is_online: bool
    last_seen: datetime
    show_status: bool = True
    show_last_seen: bool = True
    
    class Config:
        from_attributes = True

class UserWithToken(UserResponse):
    token: str

# Сообщения
class MessageCreate(BaseModel):
    content: str
    chat_id: int
    reply_to_uuid: Optional[str] = None

class MessageResponse(BaseModel):
    uuid: str
    content: str
    timestamp: datetime
    is_read: bool
    is_edited: bool
    is_deleted: bool
    sender_id: int
    chat_id: int
    reply_to_uuid: Optional[str] = None
    
    class Config:
        from_attributes = True

# Чаты
class ChatCreate(BaseModel):
    user_ids: List[int]  # Для приватного чата - 1 пользователь, для группы - несколько
    name: Optional[str] = None  # Имя группы

class ChatResponse(BaseModel):
    id: int
    name: Optional[str]
    chat_type: str
    created_at: datetime
    participants: List[UserResponse]
    last_message: Optional[MessageResponse] = None
    
    class Config:
        from_attributes = True