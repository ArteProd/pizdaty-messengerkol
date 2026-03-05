from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

# Связующая таблица для участников чата
chat_participants = Table(
    'chat_participants',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('chat_id', Integer, ForeignKey('chats.id'), primary_key=True)
)

class Chat(Base):
    __tablename__ = 'chats'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100))  # Для групповых чатов
    chat_type = Column(String(20), default='private')  # private, group, saved
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey('users.id'))
    
    # Связи
    participants = relationship('User', secondary=chat_participants, back_populates='chats')
    messages = relationship('Message', back_populates='chat', cascade='all, delete-orphan')
    created_by_user = relationship('User', foreign_keys=[created_by])

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    avatar = Column(String(500), nullable=True, default=None)
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    
    # НАСТРОЙКИ ПРИВАТНОСТИ
    show_status = Column(Boolean, default=True)  # Показывать ли статус
    show_last_seen = Column(Boolean, default=True)  # Показывать ли "был в сети"
    status_text = Column(String(100), default="В сети")  # Кастомный статус
    
    # Связи
    sent_messages = relationship('Message', back_populates='sender', foreign_keys='Message.sender_id')
    chats = relationship('Chat', secondary=chat_participants, back_populates='participants')

class Message(Base):
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_read = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    
    # Внешние ключи
    sender_id = Column(Integer, ForeignKey('users.id'))
    chat_id = Column(Integer, ForeignKey('chats.id'))
    reply_to_id = Column(Integer, ForeignKey('messages.id'), nullable=True)
    
    # Связи
    sender = relationship('User', back_populates='sent_messages', foreign_keys=[sender_id])
    chat = relationship('Chat', back_populates='messages')
    reply_to = relationship('Message', remote_side=[id])