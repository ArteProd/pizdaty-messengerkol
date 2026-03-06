from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, desc, text
from sqlalchemy.orm import selectinload
from datetime import datetime
from typing import List
import jwt
import os
import json
import uuid
from PIL import Image
from io import BytesIO

import models
import schemas
import database
from websocket_manager import manager
from database import engine, AsyncSessionLocal
from auth import router as auth_router, get_current_user

# Создаем папки для загрузок
os.makedirs("uploads/avatars", exist_ok=True)
os.makedirs("static", exist_ok=True)

app = FastAPI(title="Pizdaty Messenger", version="1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутер авторизации
app.include_router(auth_router)

# Подключаем статику
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads/avatars", StaticFiles(directory="uploads/avatars"), name="avatars")

# ========== ФУНКЦИЯ СОЗДАНИЯ ИЗБРАННОГО ==========
async def ensure_saved_chat(user_id: int, db: AsyncSession):
    """Проверяет и создает чат 'Избранное' для пользователя"""
    # Ищем чат избранного для конкретного пользователя
    # Правильный запрос: ищем чат где user_id является участником И chat_type = 'saved'
    result = await db.execute(
        select(models.Chat)
        .join(models.Chat.participants)
        .where(
            and_(
                models.Chat.chat_type == 'saved',
                models.User.id == user_id
            )
        )
    )
    saved_chat = result.scalar_one_or_none()
    
    if not saved_chat:
        saved_chat = models.Chat(
            name="Избранное",
            chat_type="saved",
            created_by=user_id
        )
        db.add(saved_chat)
        await db.flush()
        
        # Добавляем пользователя как участника чата
        await db.execute(
            text("INSERT INTO chat_participants (user_id, chat_id) VALUES (:uid, :cid)"),
            {"uid": user_id, "cid": saved_chat.id}
        )
        
        welcome_message = models.Message(
            content="⭐ ИЗБРАННОЕ ⭐\n\nСЮДА МОЖНО СОХРАНЯТЬ:\n📝 Текстовые сообщения\n🔗 Ссылки и статьи\n📸 Фото и видео\n📍 Места и геолокации\n📎 Файлы и документы\n💡 Идеи и заметки\n\n👉 ПРОСТО ПИШИ СЮДА\n👈 ИЛИ ПЕРЕСЫЛАЙ ИЗ ЧАТОВ\n\n✨ ВСЁ СОХРАНИТСЯ!\n🚀 НИКУДА НЕ ПРОПАДЁТ!\n\n⚡️ УДАЧНОГО ИСПОЛЬЗОВАНИЯ! ⚡️",
            sender_id=user_id,
            chat_id=saved_chat.id,
            is_read=True
        )
        db.add(welcome_message)
        
        await db.commit()
        print(f"✅ Создан чат 'Избранное' для пользователя {user_id}")
        
        # Обновляем объект после commit
        await db.refresh(saved_chat)
    
    return saved_chat

# ========== СОЗДАНИЕ ТАБЛИЦ ==========
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

# ========== ГЛАВНАЯ СТРАНИЦА ==========
@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pizdaty Messenger</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <meta name="theme-color" content="#764ba2">
        <meta name="mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <style>
            /* ===== TELEGRAM-STYLE MOBILE ===== */
            :root {
                --bg-primary: #f5f7fb;
                --bg-secondary: #f8f9fa;
                --bg-white: #ffffff;
                --text-primary: #333333;
                --text-secondary: #666666;
                --text-muted: #999999;
                --border-color: #e0e0e0;
                --shadow-color: rgba(0,0,0,0.1);
                --input-bg: #f0f2f5;
                --message-received-bg: #ffffff;
                --message-sent-bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                --scrollbar-track: #f1f1f1;
                --scrollbar-thumb: #c1c1c1;
                --chat-item-hover: #e9ecef;
                --chat-item-active: #e3f2fd;
                --safe-area-top: env(safe-area-inset-top, 0px);
                --safe-area-bottom: env(safe-area-inset-bottom, 0px);
            }

            /* Тёмная тема */
            [data-theme="dark"] {
                --bg-primary: #0f0f1a;
                --bg-secondary: #1a1a2e;
                --bg-white: #16213e;
                --text-primary: #e0e0e0;
                --text-secondary: #b0b0b0;
                --text-muted: #707070;
                --border-color: #2a2a4a;
                --shadow-color: rgba(0,0,0,0.3);
                --input-bg: #1a1a2e;
                --message-received-bg: #16213e;
                --message-sent-bg: linear-gradient(135deg, #5a6fd6 0%, #6b4d9e 100%);
                --scrollbar-track: #1a1a2e;
                --scrollbar-thumb: #3a3a5a;
                --chat-item-hover: #1f1f3a;
                --chat-item-active: #1a3a5a;
            }

            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                -webkit-tap-highlight-color: transparent;
            }

            body {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 0;
                margin: 0;
            }

            body[data-theme="dark"] {
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            }

            /* АВТОРИЗАЦИЯ */
            .auth-container {
                background: var(--bg-white);
                border-radius: 28px;
                padding: clamp(24px, 6vw, 40px);
                width: 90%;
                max-width: 400px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                animation: slideUp 0.3s ease;
                margin: 20px auto;
            }

            @keyframes slideUp {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .auth-container h1 {
                font-size: clamp(24px, 6vw, 32px);
                color: var(--text-primary);
                margin-bottom: 24px;
                text-align: center;
            }

            .auth-container input {
                width: 100%;
                padding: 16px;
                margin: 8px 0;
                border: 2px solid var(--border-color);
                border-radius: 16px;
                font-size: 16px;
                background: var(--input-bg);
                color: var(--text-primary);
                transition: border 0.2s;
            }

            .auth-container input:focus {
                outline: none;
                border-color: #667eea;
            }

            .auth-container button {
                width: 100%;
                padding: 16px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                margin: 8px 0;
                transition: transform 0.1s;
            }

            .auth-container button:active {
                transform: scale(0.98);
            }

            .auth-container hr {
                margin: 24px 0;
                border: 1px solid var(--border-color);
            }

            .auth-container h3 {
                color: var(--text-primary);
                margin-bottom: 16px;
            }

            .error {
                color: #ff4757;
                margin: 10px 0;
                font-size: 14px;
            }

            /* ОСНОВНОЙ ИНТЕРФЕЙС */
            .messenger-container {
                background: var(--bg-white);
                width: 100%;
                height: 100vh;
                height: 100dvh;
                display: flex;
                flex-direction: row;
                overflow: hidden;
                position: relative;
                display: none;
            }

            /* ПК ВЕРСИЯ */
            @media (min-width: 769px) {
                .messenger-container {
                    width: 95%;
                    max-width: 1400px;
                    height: 95vh;
                    max-height: 900px;
                    border-radius: 28px;
                    margin: 2.5vh auto;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                }
                
                .menu-button {
                    display: none !important;
                }
                
                .sidebar-overlay {
                    display: none !important;
                }
                
                .sidebar {
                    width: 350px;
                    border-right: 1px solid var(--border-color);
                }
            }

            /* МОБИЛЬНАЯ ВЕРСИЯ */
            @media (max-width: 768px) {
                .messenger-container {
                    flex-direction: column;
                }
                
                .sidebar {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 85%;
                    max-width: 360px;
                    height: 100vh;
                    height: 100dvh;
                    background: var(--bg-white);
                    z-index: 1000;
                    transform: translateX(-100%);
                    transition: transform 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
                    box-shadow: 2px 0 20px var(--shadow-color);
                }
                
                .sidebar.open {
                    transform: translateX(0);
                }
                
                .sidebar-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0,0,0,0.5);
                    z-index: 999;
                    opacity: 0;
                    visibility: hidden;
                    transition: opacity 0.3s ease;
                    backdrop-filter: blur(2px);
                }
                
                .sidebar-overlay.active {
                    opacity: 1;
                    visibility: visible;
                }
                
                .chat-main {
                    width: 100%;
                    height: 100vh;
                    height: 100dvh;
                    display: flex;
                    flex-direction: column;
                }
                
                .menu-button {
                    display: flex !important;
                    width: 44px;
                    height: 44px;
                    border-radius: 50%;
                    background: var(--input-bg);
                    align-items: center;
                    justify-content: center;
                    margin-right: 12px;
                    cursor: pointer;
                    transition: background 0.2s;
                }
                
                .menu-button:active {
                    background: var(--border-color);
                    transform: scale(0.95);
                }
                
                .menu-button svg {
                    width: 24px;
                    height: 24px;
                    fill: var(--text-primary);
                }
            }

            /* САЙДБАР */
            .sidebar {
                display: flex;
                flex-direction: column;
                height: 100%;
                background: var(--bg-white);
            }

            .profile {
                padding: 20px;
                padding-top: max(20px, var(--safe-area-top));
                background: var(--bg-white);
                border-bottom: 1px solid var(--border-color);
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .avatar {
                width: 50px;
                height: 50px;
                border-radius: 50%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 20px;
                flex-shrink: 0;
            }

            .user-info {
                flex: 1;
                min-width: 0;
            }

            .user-info h3 {
                color: var(--text-primary);
                margin-bottom: 4px;
                font-size: 18px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .status-container {
                display: flex;
                align-items: center;
                gap: 6px;
            }

            .user-status {
                width: 12px;
                height: 12px;
                border-radius: 50%;
            }

            .status-online {
                background: #2ecc71;
                box-shadow: 0 0 0 2px var(--bg-white);
            }

            .status-offline {
                background: #95a5a6;
            }

            .status-text {
                font-size: 14px;
                color: var(--text-secondary);
            }

            .search {
                padding: 12px 16px;
                background: var(--bg-white);
                border-bottom: 1px solid var(--border-color);
            }

            .search input {
                width: 100%;
                padding: 14px 18px;
                background: var(--input-bg);
                border: none;
                border-radius: 24px;
                font-size: 16px;
                color: var(--text-primary);
            }

            .search input::placeholder {
                color: var(--text-muted);
            }

            .chats-list {
                flex: 1;
                overflow-y: auto;
                padding: 8px;
            }

            .chat-item {
                display: flex;
                align-items: center;
                padding: 12px 16px;
                border-radius: 16px;
                cursor: pointer;
                transition: background 0.2s;
                margin-bottom: 4px;
            }

            @media (max-width: 768px) {
                .chat-item {
                    padding: 16px;
                }
                
                .chat-avatar {
                    width: 54px;
                    height: 54px;
                    font-size: 22px;
                }
            }

            .chat-item:hover {
                background: var(--chat-item-hover);
            }

            .chat-item:active {
                background: var(--chat-item-hover);
                transform: scale(0.98);
            }

            .chat-item.active {
                background: var(--chat-item-active);
            }

            .chat-avatar {
                width: 48px;
                height: 48px;
                border-radius: 50%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 20px;
                margin-right: 12px;
                flex-shrink: 0;
                overflow: hidden;
            }

            .chat-avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }

            .chat-info {
                flex: 1;
                min-width: 0;
            }

            .chat-name {
                font-weight: 600;
                color: var(--text-primary);
                margin-bottom: 4px;
                font-size: 16px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .last-message {
                font-size: 14px;
                color: var(--text-secondary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                display: flex;
                align-items: center;
                gap: 4px;
            }

            .chat-item-time {
                font-size: 12px;
                color: var(--text-muted);
                flex-shrink: 0;
                display: flex;
                align-items: center;
                gap: 4px;
            }

            .chat-item-checkmarks {
                font-size: 12px;
                color: var(--text-muted);
            }

            .chat-item-checkmarks.read {
                color: #2ecc71;
            }

            .sidebar-footer {
                padding: 16px;
                padding-bottom: max(16px, var(--safe-area-bottom));
                border-top: 1px solid var(--border-color);
                background: var(--bg-white);
            }

            .sidebar-footer button {
                width: 100%;
                padding: 16px;
                border-radius: 16px;
                font-size: 16px;
                font-weight: 600;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                background: var(--input-bg);
                border: 1px solid var(--border-color);
                color: var(--text-primary);
                margin-bottom: 10px;
                cursor: pointer;
                transition: background 0.2s;
            }

            .sidebar-footer button:active {
                background: var(--border-color);
                transform: scale(0.98);
            }

            .sidebar-footer button:last-child {
                background: #ff4757;
                color: white;
                border: none;
            }

            /* ЧАТ */
            .chat-main {
                flex: 1;
                display: flex;
                flex-direction: column;
                background: var(--bg-white);
                min-width: 0;
            }

            .chat-header {
                padding: 12px 16px;
                padding-top: max(12px, var(--safe-area-top));
                background: var(--bg-white);
                border-bottom: 1px solid var(--border-color);
                display: flex;
                align-items: center;
                min-height: 70px;
            }

            .chat-header .avatar {
                width: 44px;
                height: 44px;
                font-size: 18px;
                margin-right: 12px;
                overflow: hidden;
            }

            .chat-header .avatar img {
                width: 100%;
                height: 100%;
                object-fit: cover;
            }

            .chat-header .user-info h3 {
                font-size: 18px;
                font-weight: 600;
                margin-bottom: 4px;
            }

            .messages-container {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                background: var(--bg-primary);
                display: flex;
                flex-direction: column;
            }

            .message {
                max-width: 65%;
                margin-bottom: 8px;
                padding: 12px 16px;
                border-radius: 18px;
                word-wrap: break-word;
                animation: messageIn 0.2s ease;
                font-size: 15px;
                line-height: 1.4;
                position: relative;
            }

            @media (max-width: 768px) {
                .message {
                    max-width: 85%;
                    font-size: 16px;
                    padding: 14px 18px;
                    border-radius: 22px;
                }
            }

            @keyframes messageIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .message.sent {
                background: var(--message-sent-bg);
                color: white;
                align-self: flex-end;
                border-bottom-right-radius: 6px;
            }

            .message.received {
                background: var(--message-received-bg);
                color: var(--text-primary);
                align-self: flex-start;
                box-shadow: 0 1px 2px var(--shadow-color);
                border-bottom-left-radius: 6px;
            }

            .message + .message.sent,
            .message + .message.received {
                margin-top: 2px;
            }

            .message:first-child {
                margin-top: auto;
            }

            .message-info {
                font-size: 11px;
                opacity: 0.7;
                margin-top: 6px;
                display: flex;
                align-items: center;
                gap: 4px;
                justify-content: flex-end;
            }

            .message.sent .message-info {
                color: rgba(255,255,255,0.8);
            }

            .message-input {
                padding: 12px 16px;
                padding-bottom: max(12px, var(--safe-area-bottom));
                background: var(--bg-white);
                border-top: 1px solid var(--border-color);
                display: flex;
                gap: 10px;
            }

            .message-input input {
                flex: 1;
                padding: 16px 20px;
                border: 2px solid var(--border-color);
                border-radius: 30px;
                font-size: 16px;
                background: var(--input-bg);
                color: var(--text-primary);
                min-width: 0;
                white-space: pre-wrap !important;  /* Сохраняет переносы принудительно */
                overflow-wrap: break-word !important;
                word-break: break-word !important;
                line-height: 1.4 !important;
            }

            .message-input textarea {
                flex: 1;
                padding: 16px 20px;
                border: 2px solid var(--border-color);
                border-radius: 30px;
                font-size: 16px;
                background: var(--input-bg);
                color: var(--text-primary);
                font-family: inherit;
                resize: none;
                outline: none;
                line-height: 1.4;
                white-space: pre-wrap;
                overflow-y: auto;
                max-height: 150px;
                min-height: 56px;
                border: none;
                width: 100%;
                transition: height 0.1s ease; /* Плавное изменение */
            }

            /* Лимиты символов */
            .message-input textarea.limit-warning {
                border-color: #ffa502 !important;
                background: rgba(255, 165, 2, 0.05) !important;
            }

            .message-input textarea.limit-danger {
                border-color: #ff4757 !important;
                background: rgba(255, 71, 87, 0.05) !important;
                animation: shake 0.3s ease;
            }

            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            /* Когда поле пустое - тоже нормальная высота */
            .message-input textarea:placeholder-shown {
                height: 56px !important;
            }

            .message-input textarea:focus {
                border-color: #667eea;
            }

            .message-input textarea::placeholder {
                color: var(--text-muted);
            }

            .message-input textarea:disabled {
                opacity: 0.5;
                pointer-events: none;
            }

            .message-input input:focus {
                outline: none;
                border-color: #667eea;
            }

            .message-input input::placeholder {
                color: var(--text-muted);
            }

            .message-input button {
                padding: 0 24px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 30px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                min-width: 100px;
                transition: transform 0.1s;
            }

            .message-input button:active {
                transform: scale(0.95);
            }

            .message-input button:disabled {
                opacity: 0.5;
                pointer-events: none;
            }

            /* БЕЙДЖИК НЕПРОЧИТАННЫХ СООБЩЕНИЙ */
            .unread-badge-chat {
                background: #ff4757;
                color: white;
                font-size: 12px;
                font-weight: bold;
                min-width: 20px;
                height: 20px;
                border-radius: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0 4px;
                margin-left: 8px;
                box-shadow: 0 2px 5px rgba(255, 71, 87, 0.3);
                animation: badgePulse 1.5s ease infinite;
            }

            @keyframes badgePulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.1); }
                100% { transform: scale(1); }
            }

            [data-theme="dark"] .unread-badge-chat {
                background: #ff4757;
                box-shadow: 0 2px 5px rgba(255, 71, 87, 0.5);
            }

            /* Если чат активный - бейджик тоже виден */
            .chat-item.active .unread-badge-chat {
                background: #ff6b81;
            }
            
            /* СТРЕЛКА ВНИЗ */
            .scroll-down-button {
                position: fixed;
                bottom: 90px;
                right: 20px;
                width: 48px;
                height: 48px;
                border-radius: 50%;
                background: var(--bg-white);
                box-shadow: 0 2px 10px var(--shadow-color);
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                z-index: 100;
                transition: all 0.2s ease;
                border: 1px solid var(--border-color);
            }

            .scroll-down-button:hover {
                transform: scale(1.1);
                background: var(--chat-item-hover);
            }

            .scroll-down-button svg {
                width: 28px;
                height: 28px;
                fill: var(--text-primary);
            }

            .scroll-down-button .unread-badge {
                position: absolute;
                top: -5px;
                right: -5px;
                background: #ff4757;
                color: white;
                font-size: 12px;
                font-weight: bold;
                min-width: 20px;
                height: 20px;
                border-radius: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 0 4px;
                box-shadow: 0 2px 5px rgba(255, 71, 87, 0.3);
            }

            [data-theme="dark"] .scroll-down-button {
                background: #1a1a2e;
                border-color: #2a2a4a;
            }

            [data-theme="dark"] .scroll-down-button svg {
                fill: #e0e0e0;
            }
            
            /* РАЗДЕЛИТЕЛИ ДАТ */
            .date-separator {
                display: flex;
                justify-content: center;
                margin: 16px 0;
                position: relative;
            }

            .date-separator span {
                background: var(--bg-secondary);
                color: var(--text-secondary);
                padding: 6px 16px;
                border-radius: 30px;
                font-size: 13px;
                font-weight: 500;
                box-shadow: 0 2px 5px var(--shadow-color);
                backdrop-filter: blur(5px);
                z-index: 1;
            }

            [data-theme="dark"] .date-separator span {
                background: #1a1a2e;
                color: #a0a0a0;
                border: 1px solid #2a2a4a;
            }

            /* ИЗБРАННОЕ */
            .chat-item[data-chat-type="saved"] .chat-avatar {
                background: linear-gradient(135deg, #f1c40f, #f39c12) !important;
            }

            .chat-main[data-chat-type="saved"] .chat-header {
                background: linear-gradient(135deg, #f1c40f20, #f39c1220);
                border-bottom: 2px solid #f1c40f;
            }

            .chat-main[data-chat-type="saved"] .chat-header .avatar {
                background: linear-gradient(135deg, #f1c40f, #f39c12) !important;
            }

            .chat-main[data-chat-type="saved"] .chat-header .chat-name {
                color: #f39c12;
            }

            .message.saved-welcome {
                background: #fff9e6 !important;
                border: 2px solid #f1c40f !important;
                color: #333 !important;
                max-width: 90% !important;
                margin: 20px auto !important;
            }

            [data-theme="dark"] .message.saved-welcome {
                background: #1a1a2e !important;
                border-color: #f1c40f !important;
                color: #e0e0e0 !important;
            }

            /* СКРОЛЛ */
            ::-webkit-scrollbar {
                width: 4px;
            }

            ::-webkit-scrollbar-track {
                background: var(--scrollbar-track);
            }

            ::-webkit-scrollbar-thumb {
                background: var(--scrollbar-thumb);
                border-radius: 4px;
            }

            /* ========== КОНТЕКСТНОЕ МЕНЮ СООБЩЕНИЙ ========== */
            .context-menu {
                position: fixed;
                background: var(--bg-white);
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                z-index: 10000;
                min-width: 180px;
                overflow: hidden;
                animation: contextMenuIn 0.2s ease;
            }

            @keyframes contextMenuIn {
                from { opacity: 0; transform: scale(0.9); }
                to { opacity: 1; transform: scale(1); }
            }

            .context-menu-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 14px 18px;
                cursor: pointer;
                transition: background 0.15s ease;
                color: var(--text-primary);
                font-size: 15px;
            }

            .context-menu-item:hover {
                background: var(--chat-item-hover);
            }

            .context-menu-item:active {
                background: var(--border-color);
            }

            .context-menu-item .icon {
                width: 20px;
                height: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .context-menu-item .icon svg {
                width: 18px;
                height: 18px;
                stroke: var(--text-secondary);
            }

            .context-menu-item.danger {
                color: #ff4757;
            }

            .context-menu-item.danger .icon svg {
                stroke: #ff4757;
            }

            .context-menu-divider {
                height: 1px;
                background: var(--border-color);
                margin: 4px 0;
            }

            /* Мобильный bottom sheet */
            @media (max-width: 768px) {
                .context-menu {
                    position: fixed;
                    left: 0 !important;
                    right: 0 !important;
                    bottom: 0 !important;
                    top: auto !important;
                    border-radius: 24px 24px 0 0;
                    animation: slideUp 0.3s ease;
                    padding-bottom: max(20px, env(safe-area-inset-bottom));
                }

                @keyframes slideUp {
                    from { transform: translateY(100%); }
                    to { transform: translateY(0); }
                }

                .context-menu-item {
                    padding: 18px 24px;
                    font-size: 16px;
                }
            }

            /* ========== ПАНЕЛЬ ОТВЕТА ========== */
            .reply-preview {
                background: rgba(0,0,0,0.05);
                border-left: 3px solid #667eea;
                padding: 8px 12px;
                margin-bottom: 8px;
                border-radius: 8px;
                font-size: 13px;
            }

            [data-theme="dark"] .reply-preview {
                background: rgba(255,255,255,0.1);
            }

            .reply-sender {
                font-weight: 600;
                color: #667eea;
                margin-bottom: 4px;
            }

            .reply-content {
                color: var(--text-secondary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .reply-panel {
                display: none;
                padding: 12px 16px;
                background: var(--bg-secondary);
                border-top: 1px solid var(--border-color);
                align-items: center;
                gap: 12px;
            }

            .reply-panel.active {
                display: flex;
            }

            .reply-info {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }

            .reply-name {
                font-size: 13px;
                font-weight: 600;
                color: #667eea;
            }

            .reply-text {
                font-size: 14px;
                color: var(--text-secondary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .cancel-reply {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                border: none;
                background: var(--input-bg);
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                transition: background 0.2s;
                flex-shrink: 0;
            }

            .cancel-reply:hover {
                background: var(--border-color);
            }

            /* ========== TOAST УВЕДОМЛЕНИЯ ========== */
            .copy-toast {
                position: fixed;
                bottom: 100px;
                left: 50%;
                transform: translateX(-50%);
                background: var(--bg-white);
                color: var(--text-primary);
                padding: 14px 28px;
                border-radius: 30px;
                box-shadow: 0 5px 20px rgba(0,0,0,0.2);
                z-index: 10001;
                font-weight: 500;
                font-size: 15px;
                animation: toastIn 0.3s ease;
            }

            @keyframes toastIn {
                from { opacity: 0; transform: translateX(-50%) translateY(20px); }
                to { opacity: 1; transform: translateX(-50%) translateY(0); }
            }

            /* ========== УДАЛЁННОЕ СООБЩЕНИЕ ========== */
            .message.deleted {
                opacity: 0.5;
                background: var(--input-bg) !important;
            }

            .message.deleted div:first-child {
                color: var(--text-muted);
                font-style: italic;
            }

            /* ЗАГЛУШКА ЧАТА */
            .empty-state {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                font-size: 18px;
                color: var(--text-muted);
                text-align: center;
                padding: 20px;
            }

            .empty-state span {
                max-width: 300px;
                line-height: 1.5;
            }

        </style>
    </head>
    <body>
        <div class="auth-container" id="authContainer">
            <h1>Kolyaska</h1>
            <div id="authError" class="error"></div>
            
            <!-- Форма входа -->
            <input type="text" id="loginUsername" placeholder="Имя пользователя">
            <input type="password" id="loginPassword" placeholder="Пароль">
            
            <button id="loginBtn">🚪 Войти</button>
            
            <!-- Кнопка регистрации под кнопкой войти -->
            <button id="showRegisterBtn" style="background: #28a745; margin-top: 8px;">📝 Зарегистрироваться</button>
            
            <!-- Форма регистрации (скрыта по умолчанию) -->
            <div id="registerForm" style="display: none; margin-top: 20px;">
                <hr>
                <h3>Регистрация</h3>
                <input type="text" id="regUsername" placeholder="Имя пользователя">
                <input type="email" id="regEmail" placeholder="Email">
                <input type="password" id="regPassword" placeholder="Пароль">
                <input type="password" id="regPasswordConfirm" placeholder="Повторите пароль">
                
                <button id="registerBtn" style="background: #28a745;">✅ Создать аккаунт</button>
                <button id="backToLoginBtn" style="background: #6c757d; margin-top: 8px;">← Назад</button>
            </div>
        </div>
        
        <div class="messenger-container" id="messengerContainer">
            <div class="sidebar" id="sidebar">
                <div class="profile">
                    <div class="avatar" id="userAvatar">U</div>
                    <div class="user-info">
                        <h3 id="userName">User</h3>
                        <div class="status-container">
                            <span class="user-status status-online" id="userStatusDot"></span>
                            <span class="status-text" id="userStatusText">В сети</span>
                        </div>
                    </div>
                </div>
                
                <div class="search">
                    <input type="text" id="searchInput" placeholder="Поиск или новый чат...">
                </div>
                
                <div class="chats-list" id="chatsList"></div>
                
                <div class="sidebar-footer">
                    <button onclick="openSettings()">
                        ⚙️ Настройки
                    </button>
                    <button onclick="logout()">
                        🚪 Выйти
                    </button>
                </div>
            </div>
            
            <div class="chat-main">
                <div class="chat-header">
                    <div class="menu-button" onclick="toggleSidebar()">
                        <svg viewBox="0 0 24 24">
                            <path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>
                        </svg>
                    </div>
                    <div class="avatar" id="chatAvatar"></div>
                    <div class="user-info">
                        <h3 id="chatName">Выберите чат</h3>
                        <div class="status-container" id="chatStatus"></div>
                    </div>
                </div>
                
                <div class="messages-container" id="messagesContainer"></div>
                
                <div class="scroll-down-button" id="scrollDownBtn" onclick="scrollToBottom()" style="display: none;">
                    <svg viewBox="0 0 24 24">
                        <path d="M11 4v12.17l-3.59-3.59L6 14l6 6 6-6-1.41-1.41L13 16.17V4h-2z"/>
                    </svg>
                    <span class="unread-badge" id="unreadBadge" style="display: none;">0</span>
                </div>

                
        <!-- Панель ответа на сообщение -->
        <div class="reply-panel" id="replyPanel">
            <div class="reply-info">
                <span class="reply-name" id="replyName">Ответ на сообщение</span>
                <span class="reply-text" id="replyText">...</span>
            </div>
            <button class="cancel-reply" onclick="cancelReply()" title="Отменить">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>

        <div class="message-input">
                    <textarea id="messageText" placeholder="Написать сообщение..." rows="1"></textarea>
                    <button id="sendMessageBtn" disabled>Отправить</button>
                </div>
            </div>
        </div>

        <!-- Оверлей для мобильного меню -->
        <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
        
        <script>
            // ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
            let accessToken = localStorage.getItem('accessToken');
            let refreshToken = localStorage.getItem('refreshToken');
            let currentUser = null;
            let ws = null;
            let currentChatId = localStorage.getItem('currentChatId');
            let isAuthenticating = false;
            let isLoggingOut = false;
            let isSendingMessage = false;
            let pendingMessages = {};

            let currentPage = 0;
            let loadingMessages = false;
            let hasMoreMessages = true;
            let allMessagesLoaded = false;
            let messageContainer = null;
            let messages = [];           // Все сообщения здесь
            let renderedCount = 0;  
            let lastScrollTop = 0;
            // ========== СТРЕЛКА ВНИЗ ==========
            let unreadCount = 0;
            let userScrolledUp = false;
            let unreadChats = {};
            
            function checkScrollPosition() {
                const container = document.getElementById('messagesContainer');
                const scrollBtn = document.getElementById('scrollDownBtn');
                if (!container || !scrollBtn) return;
                
                const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
                
                if (!atBottom) {
                    userScrolledUp = true;
                    scrollBtn.style.display = 'flex';
                } else {
                    userScrolledUp = false;
                    scrollBtn.style.display = 'none';
                    // Сбрасываем счетчик если доскроллили вниз
                    if (unreadCount > 0) {
                        unreadCount = 0;
                        updateUnreadBadge();
                    }
                }
            }

            function updateUnreadBadge() {
                const badge = document.getElementById('unreadBadge');
                if (!badge) return;
                
                if (unreadCount > 0) {
                    badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
                    badge.style.display = 'flex';
                } else {
                    badge.style.display = 'none';
                }
            }

            function scrollToBottom() {
                const container = document.getElementById('messagesContainer');
                container.scrollTo({
                    top: container.scrollHeight,
                    behavior: 'smooth'
                });
                
                // Сбрасываем счетчик после скролла
                setTimeout(() => {
                    unreadCount = 0;
                    updateUnreadBadge();
                    userScrolledUp = false;
                }, 300);
            }
            
            // ========== ФУНКЦИИ ДЛЯ ДАТ ==========
            function formatDateHeader(timestamp) {
                // Приводим к московскому времени
                const date = new Date(new Date(timestamp).getTime() + 3*60*60*1000); // МСК
                
                // Сегодня и вчера тоже приводим к московскому времени
                const now = new Date();
                const moscowNow = new Date(now.getTime() + 3*60*60*1000);
                const yesterday = new Date(moscowNow);
                yesterday.setDate(yesterday.getDate() - 1);
                
                // Обнуляем время для сравнения
                const dateStr = date.toDateString();
                const todayStr = moscowNow.toDateString();
                const yesterdayStr = yesterday.toDateString();
                
                // Месяцы на русском
                const months = [
                    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
                ];
                
                if (dateStr === todayStr) {
                    return 'Сегодня';
                } else if (dateStr === yesterdayStr) {
                    return 'Вчера';
                } else {
                    const day = date.getDate();
                    const month = months[date.getMonth()];
                    const year = date.getFullYear();
                    
                    // Если год текущий - не показываем
                    if (year === moscowNow.getFullYear()) {
                        return `${day} ${month}`;
                    } else {
                        return `${day} ${month} ${year} года`;
                    }
                }
            }

            // ========== РЕНДЕРИНГ ==========
            async function renderMessages() {
                const container = document.getElementById('messagesContainer');
                if (!container) return;
                
                // Получаем тип чата (нужно для избранного)
                let chatType = 'private';
                if (currentChatId) {
                    try {
                        const chatResponse = await fetch(`/api/chats/${currentChatId}`, {
                            headers: {'Authorization': `Bearer ${accessToken}`}
                        });
                        if (chatResponse.ok) {
                            const chat = await chatResponse.json();
                            chatType = chat.chat_type;
                        }
                    } catch (e) {}
                }
                
                // Сохраняем позицию скролла перед перерисовкой
                const oldScrollTop = container.scrollTop;
                const oldScrollHeight = container.scrollHeight;
                const atBottom = oldScrollHeight - oldScrollTop - container.clientHeight < 100;
                
                // Проверяем, есть ли уже разделитель даты в контейнере
                const existingDateSeparator = container.querySelector('.date-separator');

                // Всегда делаем полную перерисовку для корректного отображения дат
                {
                    let html = '';
                    let lastDate = null;
                    
                    messages.forEach((msg, index) => {
                        const isSent = msg.sender_id === currentUser?.id;
                        
                        // Проверяем, нужно ли добавить разделитель даты
                        const msgDate = new Date(new Date(msg.timestamp).getTime() + 3*60*60*1000).toDateString();
                        
                        // Показываем дату если:
                        // 1. Это первое сообщение
                        // 2. Или дата отличается от предыдущего сообщения
                        if (index === 0 || msgDate !== lastDate && !existingDateSeparator) {
                            const dateHeader = formatDateHeader(msg.timestamp);
                            html += `<div class="date-separator"><span>${dateHeader}</span></div>`;
                            lastDate = msgDate;
                        }
                        
                        // Экранирование
                        let content = (msg.content || '')
                            .replace(/&/g, '&amp;')
                            .replace(/</g, '&lt;')
                            .replace(/>/g, '&gt;')
                            .replace(/\\n/g, '<br>');
                        
                        // Время + галочки для отправленных сообщений
                        let time = '';
                        if (msg.status === 'sending') time = '⏳';
                        else if (msg.status === 'error') time = '❌';
                        else {
                            const d = new Date(new Date(msg.timestamp).getTime() + 3*60*60*1000);
                            const timeStr = d.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
                            // Галочки только для моих отправленных сообщений
                            const checkmarks = isSent ? ((chatType === 'saved' || msg.is_read) ? '✓✓' : '✓') : '';
                            time = isSent ? (timeStr + ' ' + checkmarks) : timeStr;
                        }
                        
                        // Класс для избранного
                        let savedClass = '';
                        if (chatType === 'saved' && 
                            (msg.content.includes('ИЗБРАННОЕ') || msg.content.includes('⭐'))) {
                            savedClass = ' saved-welcome';
                        }
                        
                        html += `<div class="message ${isSent ? 'sent' : 'received'}${savedClass}" 
                                    data-id="${msg.uuid}">
                                    <div>${content}</div>
                                    <div class="message-info">${time}</div>
                                </div>`;
                    });
                    
                    container.innerHTML = html;
                    
                    // Если были внизу - остаемся внизу, иначе пытаемся сохранить позицию
                    if (atBottom) {
                        container.scrollTop = container.scrollHeight;
                    } else {
                        container.scrollTop = oldScrollTop;
                    }
                    return;
                }
                // Для >500 сообщений - добавляем только новые
                if (messages.length >= 500) {
                    const lastMessage = messages[messages.length - 1];
                    const lastMessageElement = container.lastChild;
                    
                    // Проверяем, нужно ли добавить новое сообщение
                    if (!lastMessageElement || lastMessageElement.getAttribute('data-id') !== lastMessage.uuid) {
                        // Находим последнее реальное сообщение (не дату)
                        let lastRealMessage = null;
                        let lastRealMessageId = null;
                        
                        for (let i = container.children.length - 1; i >= 0; i--) {
                            if (container.children[i].classList.contains('message')) {
                                lastRealMessage = container.children[i];
                                lastRealMessageId = lastRealMessage.getAttribute('data-id');
                                break;
                            }
                        }
                        
                        // Проверяем дату последнего сообщения
                        if (lastRealMessageId) {
                            const lastMsgData = messages.find(m => m.uuid === lastRealMessageId);
                            
                            if (lastMsgData) {
                                const lastDate = new Date(new Date(lastMsgData.timestamp).getTime() + 3*60*60*1000).toDateString();
                                const newDate = new Date(new Date(lastMessage.timestamp).getTime() + 3*60*60*1000).toDateString();
                                
                                // Если даты разные - добавляем разделитель
                                if (lastDate !== newDate && !existingDateSeparator) {
                                    const dateHeader = formatDateHeader(lastMessage.timestamp);
                                    const dateDiv = document.createElement('div');
                                    dateDiv.className = 'date-separator';
                                    dateDiv.innerHTML = `<span>${dateHeader}</span>`;
                                    container.appendChild(dateDiv);
                                }
                            }
                        } else if (container.children.length === 0 && !existingDateSeparator) {
                            // Если это первое сообщение в пустом чате
                            const dateHeader = formatDateHeader(lastMessage.timestamp);
                            const dateDiv = document.createElement('div');
                            dateDiv.className = 'date-separator';
                            dateDiv.innerHTML = `<span>${dateHeader}</span>`;
                            container.appendChild(dateDiv);
                        }
                        
                        // Добавляем сообщение
                        const isSent = lastMessage.sender_id === currentUser?.id;
                        
                        let content = (lastMessage.content || '')
                            .replace(/&/g, '&amp;')
                            .replace(/</g, '&lt;')
                            .replace(/>/g, '&gt;')
                            .replace(/\\n/g, '<br>');
                        
                        let time = '';
                        const d = new Date(new Date(lastMessage.timestamp).getTime() + 3*60*60*1000);
                        const timeStr = d.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
                        // Галочки только для моих отправленных сообщений
                        const checkmarks = isSent ? ((chatType === 'saved' || lastMessage.is_read) ? '✓✓' : '✓') : '';
                        time = isSent ? (timeStr + ' ' + checkmarks) : timeStr;
                        
                        let savedClass = '';
                        if (chatType === 'saved' && 
                            (lastMessage.content.includes('ИЗБРАННОЕ') || lastMessage.content.includes('⭐'))) {
                            savedClass = ' saved-welcome';
                        }
                        
                        const div = document.createElement('div');
                        div.className = `message ${isSent ? 'sent' : 'received'}${savedClass}`;
                        div.setAttribute('data-id', lastMessage.uuid);
                        div.innerHTML = `<div>${content}</div><div class="message-info">${time}</div>`;
                        
                        container.appendChild(div);
                    }
                    return;
                }
            }
            
            async function loadMessages(chatId, page = 0) {
                if (loadingMessages) return [];
                
                loadingMessages = true;
                
                try {
                    const offset = page * 100;
                    const url = `/api/chats/${chatId}/messages?limit=100&offset=${offset}`;
                    console.log(`Загрузка страницы ${page}, offset: ${offset}`);
                    
                    const response = await fetch(url, {
                        headers: {
                            'Authorization': `Bearer ${accessToken}`,
                            'Content-Type': 'application/json'
                        }
                    });
                    
                    if (!response.ok) {
                        console.error('Ошибка загрузки:', response.status);
                        return [];
                    }
                    
                    const messages = await response.json();
                    console.log(`Загружено ${messages.length} сообщений`);
                    
                    // ВАЖНО: сортируем от старых к новым (по возрастанию времени)
                    messages.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
                    
                    // Если загрузили меньше 50 - значит больше нет
                    if (messages.length < 100) {
                        hasMoreMessages = false;
                        console.log('Все сообщения загружены');
                    }
                    
                    return messages;
                    
                } catch (error) {
                    console.error('Ошибка:', error);
                    return [];
                } finally {
                    loadingMessages = false;
                }
            }

            // ========== ЗАГРУЗКА СТАРЫХ ==========
            async function loadMoreMessages() {
                console.log('loadMoreMessages вызвана, currentPage:', currentPage, 'hasMoreMessages:', hasMoreMessages);
                
                if (loadingMessages || !hasMoreMessages || !currentChatId) {
                    console.log('loadMoreMessages пропущена: loadingMessages=', loadingMessages, 'hasMoreMessages=', hasMoreMessages, 'currentChatId=', currentChatId);
                    return;
                }
                
                const container = document.getElementById('messagesContainer');
                
                // Сохраняем позицию и высоту ДО загрузки
                const scrollTop = container.scrollTop;
                const scrollHeight = container.scrollHeight;
                
                currentPage++;
                console.log('Загружаю страницу', currentPage, 'для чата', currentChatId);
                
                const oldMessages = await loadMessages(currentChatId, currentPage);
                
                console.log('Получено старых сообщений:', oldMessages.length);
                
                if (oldMessages.length === 0) {
                    currentPage--;
                    hasMoreMessages = false;
                    console.log('Старых сообщений нет, больше не грузим');
                    return;
                }
                
                // Добавляем старые в начало массива (они уже отсортированы по времени)
                messages = [...oldMessages, ...messages];
                console.log('Всего сообщений в массиве:', messages.length);
                
                // Перерисовываем
                renderMessages();
                
                // Восстанавливаем позицию скролла
                const newScrollHeight = container.scrollHeight;
                container.scrollTop = scrollTop + (newScrollHeight - scrollHeight);
                console.log('Скролл восстановлен, новая высота:', newScrollHeight);
            }
            
            function clearChat() {
                messages = [];
                document.getElementById('messagesContainer').innerHTML = '';
                currentPage = 0;
                hasMoreMessages = true;
            }
            
            // ========== ТЕМА ==========
            function applyTheme(darkMode) {
                if (darkMode) {
                    document.documentElement.setAttribute('data-theme', 'dark');
                    document.body.setAttribute('data-theme', 'dark');
                } else {
                    document.documentElement.removeAttribute('data-theme');
                    document.body.removeAttribute('data-theme');
                }
            }

            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'dark') {
                applyTheme(true);
            }

            // ========== МОБИЛЬНОЕ МЕНЮ ==========
            function toggleSidebar() {
                const sidebar = document.getElementById('sidebar');
                const overlay = document.getElementById('sidebarOverlay');
                
                if (!sidebar || !overlay) return;
                
                sidebar.classList.toggle('open');
                overlay.classList.toggle('active');
                
                if (sidebar.classList.contains('open')) {
                    document.body.style.overflow = 'hidden';
                } else {
                    document.body.style.overflow = '';
                }
            }

            // Свайпы
            let touchStartX = 0;
            let touchEndX = 0;

            document.addEventListener('touchstart', e => {
                touchStartX = e.changedTouches[0].screenX;
            }, {passive: true});

            document.addEventListener('touchend', e => {
                touchEndX = e.changedTouches[0].screenX;
                handleSwipe();
            }, {passive: true});

            function handleSwipe() {
                const sidebar = document.getElementById('sidebar');
                const overlay = document.getElementById('sidebarOverlay');
                
                if (!sidebar || !overlay) return;
                
                const swipeDistance = touchEndX - touchStartX;
                const isMobile = window.innerWidth <= 768;
                
                if (isMobile && swipeDistance > 70 && !sidebar.classList.contains('open')) {
                    toggleSidebar();
                }
                
                if (isMobile && swipeDistance < -70 && sidebar.classList.contains('open')) {
                    toggleSidebar();
                }
            }

            // ========== ПРИ ЗАГРУЗКЕ ==========
            document.addEventListener('DOMContentLoaded', async () => {
                console.log('Страница загружена. Токены:', accessToken ? 'есть' : 'нет');

                if (accessToken && refreshToken) {
                    document.getElementById('authContainer').style.display = 'none';
                    document.getElementById('messengerContainer').style.display = 'flex';
                    await attemptLogin();
                }
            });

            // ========== АВТОРИЗАЦИЯ ==========
            async function attemptLogin() {
                if (isAuthenticating) return;
                isAuthenticating = true;
                
                try {
                    const response = await fetch('/api/auth/me', {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!response.ok) {
                        throw new Error('Ошибка авторизации');
                    }
                    
                    currentUser = await response.json();
                    
                    // Показываем аватар если есть
                    if (currentUser.avatar) {
                        document.getElementById('userAvatar').innerHTML = `<img src="${currentUser.avatar}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
                    } else {
                        document.getElementById('userAvatar').textContent = currentUser.username[0].toUpperCase();
                    }
                    
                    document.getElementById('userName').textContent = currentUser.username;
                    
                    isLoggingOut = false;
                    
                    connectWebSocket();
                    await loadChats();
                    initMessageHandlers();
                    
                    if (currentChatId) {
                        await selectChat(parseInt(currentChatId));
                    } else {
                        showEmptyChatState();
                    }
                    
                } catch (error) {
                    console.error('Ошибка входа:', error);
                    logout();
                } finally {
                    isAuthenticating = false;
                }
            }

            async function refreshAccessToken() {
                if (!refreshToken) return false;
                
                try {
                    const response = await fetch('/api/auth/refresh', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({refresh_token: refreshToken})
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        accessToken = data.access_token;
                        localStorage.setItem('accessToken', accessToken);
                        return true;
                    }
                } catch (e) {}
                return false;
            }

            // ========== ВХОД/РЕГИСТРАЦИЯ ==========
            document.getElementById('loginBtn').onclick = async () => {
                const username = document.getElementById('loginUsername').value.trim();
                const password = document.getElementById('loginPassword').value;
                const errorEl = document.getElementById('authError');
                errorEl.textContent = '';
                
                if (!username || !password) {
                    errorEl.textContent = 'Введите логин и пароль';
                    return;
                }
                
                try {
                    const response = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({username, password})
                    });
                    
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Ошибка входа');
                    }
                    
                    accessToken = data.access_token;
                    refreshToken = data.refresh_token;
                    localStorage.setItem('accessToken', accessToken);
                    localStorage.setItem('refreshToken', refreshToken);
                    
                    location.reload();
                    
                } catch (error) {
                    errorEl.textContent = error.message;
                }
            };

            // Показать форму регистрации
            document.getElementById('showRegisterBtn').onclick = () => {
                document.getElementById('registerForm').style.display = 'block';
                document.getElementById('showRegisterBtn').style.display = 'none';
            };
            
            // Вернуться к входу
            document.getElementById('backToLoginBtn').onclick = () => {
                document.getElementById('registerForm').style.display = 'none';
                document.getElementById('showRegisterBtn').style.display = 'block';
            };
            
            // Регистрация с автовходом
            document.getElementById('registerBtn').onclick = async () => {
                const username = document.getElementById('regUsername').value.trim();
                const email = document.getElementById('regEmail').value.trim();
                const password = document.getElementById('regPassword').value;
                const passwordConfirm = document.getElementById('regPasswordConfirm').value;
                const errorEl = document.getElementById('authError');
                errorEl.textContent = '';
                
                if (!username || !email || !password || !passwordConfirm) {
                    errorEl.textContent = 'Заполните все поля';
                    return;
                }
                
                if (password !== passwordConfirm) {
                    errorEl.textContent = 'Пароли не совпадают';
                    return;
                }
                
                try {
                    const response = await fetch('/api/auth/register', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({username, email, password})
                    });
                    
                    const data = await response.json();
                    
                    if (!response.ok) {
                        throw new Error(data.detail || 'Ошибка регистрации');
                    }
                    
                    // Автоматический вход после регистрации
                    accessToken = data.access_token;
                    refreshToken = data.refresh_token;
                    localStorage.setItem('accessToken', accessToken);
                    localStorage.setItem('refreshToken', refreshToken);
                    
                    location.reload();
                    
                } catch (error) {
                    errorEl.textContent = error.message;
                }
            };

            // ========== WEBSOCKET ==========
            function connectWebSocket() {
                if (!accessToken) return;
                
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.close();
                }
                
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws?token=${accessToken}`;
                
                ws = new WebSocket(wsUrl);
                
                ws.timeout = setTimeout(() => {
                    if (ws && ws.readyState !== WebSocket.OPEN) {
                        ws.close();
                        console.log('WebSocket timeout - reconnecting');
                    }
                }, 10000);
                
                ws.onopen = () => {
                    clearTimeout(ws.timeout);
                    console.log('✅ WebSocket подключен');
                    updateMyStatus(true);
                };
                
                ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        
                        if (data.type === 'new_message') {
                            if (data.message.chat_id === currentChatId) {
                                addMessageToChat(data.message);
                                // Перерисовываем для дат
                                renderMessages();
                                markChatAsRead(currentChatId);
                            } else {
                                // Для других чатов - увеличиваем счётчик
                                unreadChats[data.message.chat_id] = (unreadChats[data.message.chat_id] || 0) + 1;
                                updateChatBadge(data.message.chat_id, unreadChats[data.message.chat_id]);
                            }
                            
                            updateChatInList(data.message.chat_id, data.message);
                        }
                        else if (data.type === 'new_chat') {
                            // Новый чат - обновляем список чатов
                            loadChats();
                        }
                        else if (data.type === 'user_status') {
                            if (currentChatId && currentUser && data.user_id !== currentUser.id) {
                                // Обновляем статус в реальном времени
                                fetch(`/api/users/${data.user_id}/status`, {
                                    headers: {'Authorization': `Bearer ${accessToken}`}
                                })
                                .then(r => r.json())
                                .then(user => {
                                    updateHeaderStatus(user);
                                })
                                .catch(() => {});
                            }
                        }
                        else if (data.type === 'message_read') {
                            handleMessageRead(data);
                            // Убираем бейджик если он был
                            if (data.chat_id !== currentChatId) {
                                unreadChats[data.chat_id] = 0;
                                updateChatBadge(data.chat_id, 0);
                            }
                        }
                    } catch (e) {}
                };
                
                ws.onclose = () => {
                    clearTimeout(ws.timeout);
                    updateMyStatus(false);
                    
                    if (!isLoggingOut) {
                        let delay = 1000;
                        const reconnect = () => {
                            setTimeout(() => {
                                if (!isLoggingOut && (!ws || ws.readyState === WebSocket.CLOSED)) {
                                    console.log(`🔄 Переподключение через ${delay}ms...`);
                                    connectWebSocket();
                                }
                            }, delay);
                            delay = Math.min(delay * 1.5, 30000);
                        };
                        reconnect();
                    }
                };
                
                ws.onerror = (error) => {
                    console.error('❌ WebSocket ошибка:', error);
                    updateMyStatus(false);
                };
            }

            // ========== СТАТУСЫ ==========
            function updateMyStatus(isOnline) {
                const dot = document.getElementById('userStatusDot');
                const text = document.getElementById('userStatusText');
                
                if (!dot || !text) return;
                
                if (!accessToken || !currentUser) {
                    dot.className = 'user-status status-offline';
                    text.textContent = 'Не в сети';
                    return;
                }
                
                dot.className = 'user-status ' + (isOnline ? 'status-online' : 'status-offline');
                text.textContent = isOnline ? 'В сети' : 'Не в сети';
            }

            function formatLastSeen(dateStr) {
                const lastSeenUTC = new Date(dateStr + 'Z');
                const now = new Date();
                const diff = now - lastSeenUTC;
                
                if (diff < 60000) return 'только что';
                if (diff < 3600000) {
                    const minutes = Math.floor(diff / 60000);
                    return `${minutes} ${minutes === 1 ? 'минуту' : 'минуты'} назад`;
                }
                if (diff < 86400000) {
                    const hours = Math.floor(diff / 3600000);
                    return `${hours} ${hours === 1 ? 'час' : 'часа'} назад`;
                }
                return lastSeenUTC.toLocaleDateString('ru-RU');
            }

            async function loadUserStatus(userId) {
                try {
                    const response = await fetch(`/api/users/${userId}/status`, {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!response.ok) return;
                    
                    const user = await response.json();
                    const container = document.getElementById('chatStatus');
                    if (container) {
                        if (user.is_online) {
                            container.innerHTML = '<span class="user-status status-online"></span><span>В сети</span>';
                        } else if (user.last_seen) {
                            container.innerHTML = '<span class="user-status status-offline"></span><span>Был(а) ' + formatLastSeen(user.last_seen) + '</span>';
                        } else {
                            container.innerHTML = '<span class="user-status status-offline"></span><span>Был(а) недавно</span>';
                        }
                    }
                } catch (e) {}
            }

            // ========== ЧАТЫ ==========
            async function markChatAsRead(chatId) {
                try {
                    await fetch(`/api/chats/${chatId}/read`, {
                        method: 'POST',
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    // Плавно убираем бейджик
                    const chatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
                    if (chatItem) {
                        const badge = chatItem.querySelector('.unread-badge-chat');
                        if (badge) {
                            badge.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                            badge.style.opacity = '0';
                            badge.style.transform = 'scale(0.5)';
                            setTimeout(() => badge.remove(), 300);
                        }
                    }
                    
                    // Обновляем галочки в текущем чате
                    if (chatId === currentChatId) {
                        messages.forEach(msg => {
                            if (msg.sender_id !== currentUser?.id) {
                                msg.is_read = true;
                            }
                        });
                        renderMessages();
                    }
                    
                    // Обновляем галочку в списке для этого чата (ТОЛЬКО если последнее сообщение от собеседника)
                    if (chatId === currentChatId && messages.length > 0) {
                        const lastMessage = messages[messages.length - 1];
                        // Если последнее сообщение от собеседника - обновляем
                        if (lastMessage.sender_id !== currentUser?.id) {
                            updateSpecificChatCheckmark(chatId);
                        }
                    } else {
                        // Для других чатов - обновляем
                        updateSpecificChatCheckmark(chatId);
                    }
                    
                } catch (e) {}
            }
            
            function updateSpecificChatCheckmark(chatId) {
                const chatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
                if (!chatItem) return;
                
                const timeContainer = chatItem.querySelector('.chat-item-time');
                if (!timeContainer) return;
                
                // Получаем время без галочек
                let timeText = timeContainer.textContent || '';
                timeText = timeText.replace(/[✓✓✓]/g, '').trim();
                
                // Если это текущий чат, берём последнее сообщение из messages
                if (chatId === currentChatId && messages.length > 0) {
                    const lastMessage = messages[messages.length - 1];
                    // Галочки ТОЛЬКО для своих сообщений
                    if (lastMessage.sender_id === currentUser?.id) {
                        const checkmarksHtml = '<span class="chat-item-checkmarks read">✓✓</span>';
                        timeContainer.innerHTML = timeText + checkmarksHtml;
                    } else {
                        // Для чужих сообщений - только время
                        timeContainer.innerHTML = timeText;
                    }
                    return;
                }
                
                // Для других чатов - без изменений (оставляем как есть)
                // Здесь мы не знаем, чьё последнее сообщение, поэтому ничего не делаем
            }

            function updateChatInList(chatId, lastMessage) {
                const chatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
                if (!chatItem) return;
                
                const lastMsgEl = chatItem.querySelector('.last-message span');
                const timeContainer = chatItem.querySelector('.chat-item-time');
                
                // Обновляем текст последнего сообщения
                if (lastMsgEl && lastMessage) {
                    let text = lastMessage.content.length > 30 
                        ? lastMessage.content.substring(0, 30) + '...' 
                        : lastMessage.content;
                    lastMsgEl.textContent = text;
                }
                
                // Обновляем время и галочки
                if (timeContainer && lastMessage) {
                    const msgDate = new Date(new Date(lastMessage.timestamp).getTime() + 3*60*60*1000);
                    const now = new Date();
                    const moscowNow = new Date(now.getTime() + 3*60*60*1000);
                    const yesterday = new Date(moscowNow);
                    yesterday.setDate(yesterday.getDate() - 1);
                    
                    const msgDateStr = msgDate.toDateString();
                    const todayStr = moscowNow.toDateString();
                    const yesterdayStr = yesterday.toDateString();
                    
                    let timeStr = '';
                    if (msgDateStr === todayStr) {
                        timeStr = msgDate.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
                    } else if (msgDateStr === yesterdayStr) {
                        timeStr = 'Вчера';
                    } else {
                        timeStr = msgDate.toLocaleDateString('ru-RU', {day:'numeric', month:'numeric'});
                    }
                    
                    // ГАЛОЧКИ: только для моих сообщений
                    let checkmarksHtml = '';
                    if (lastMessage.sender_id === currentUser?.id) {
                        const isRead = lastMessage.is_read;
                        checkmarksHtml = isRead 
                            ? '<span class="chat-item-checkmarks read">✓✓</span>' 
                            : '<span class="chat-item-checkmarks">✓</span>';
                    }
                    
                    timeContainer.innerHTML = timeStr + checkmarksHtml;
                }
                
                // Перемещаем чат наверх (плавно)
                const chatsList = document.getElementById('chatsList');
                if (chatsList && chatItem !== chatsList.firstChild) {
                    chatItem.style.transition = 'transform 0.2s ease';
                    chatItem.style.transform = 'translateY(-5px)';
                    setTimeout(() => {
                        chatsList.insertBefore(chatItem, chatsList.firstChild);
                        chatItem.style.transform = 'translateY(0)';
                    }, 50);
                }
            }

            async function loadChats() {
                try {
                    const response = await fetch('/api/chats', {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!response.ok) return;
                    
                    let chats = await response.json();
                    
                    // СОРТИРУЕМ ЧАТЫ ПО ПОРЯДКУ:
                    // 1. Сначала Избранное
                    // 2. Потом остальные по дате последнего сообщения (сначала новые)
                    chats.sort((a, b) => {
                        // Избранное всегда сверху
                        //if (a.chat_type === 'saved' && b.chat_type !== 'saved') return -1;
                        //if (a.chat_type !== 'saved' && b.chat_type === 'saved') return 1;
                        
                        // Для остальных - по дате последнего сообщения
                        const aTime = a.last_message?.timestamp || a.created_at || 0;
                        const bTime = b.last_message?.timestamp || b.created_at || 0;
                        return new Date(bTime) - new Date(aTime);
                    });
                    
                    // Убираем дубликаты
                    const uniqueChats = [];
                    const seen = new Set();
                    for (const chat of chats) {
                        if (!seen.has(chat.id)) {
                            seen.add(chat.id);
                            uniqueChats.push(chat);
                        }
                    }
                    
                    const chatsList = document.getElementById('chatsList');
                    chatsList.innerHTML = '';
                    
                    for (const chat of uniqueChats) {
                        const isSaved = chat.chat_type === 'saved';
                        let chatName = isSaved ? '⭐ Избранное' : (chat.name || chat.participants?.find(p => p.id !== currentUser?.id)?.username || 'Чат');
                        // Аватар: если есть изображение - показываем, иначе первую букву имени
                        const otherUser = chat.participants?.find(p => p.id !== currentUser?.id);
                        let avatarHtml = '';
                        if (isSaved) {
                            avatarHtml = '⭐';
                        } else if (otherUser?.avatar) {
                            avatarHtml = `<img src="${otherUser.avatar}" alt="${chatName}">`;
                        } else {
                            avatarHtml = chatName[0].toUpperCase();
                        }
                        
                        let unreadCount = 0;
                        if (chat.id !== currentChatId) {
                            try {
                                const unreadResponse = await fetch(`/api/chats/${chat.id}/unread`, {
                                    headers: {'Authorization': `Bearer ${accessToken}`}
                                });
                                if (unreadResponse.ok) {
                                    const unreadData = await unreadResponse.json();
                                    unreadCount = unreadData.count;
                                }
                            } catch (e) {}
                        }
                        
                        const el = document.createElement('div');
                        el.className = `chat-item ${chat.id == currentChatId ? 'active' : ''}`;
                        el.setAttribute('data-chat-id', chat.id);
                        el.setAttribute('data-chat-type', chat.chat_type);
                        el.onclick = () => selectChat(chat.id);
                        
                        // ПОСЛЕДНЕЕ СООБЩЕНИЕ (обрезаем если длинное)
                        let lastMsgText = '...';
                        if (chat.last_message?.content && !chat.last_message.is_deleted) {
                            lastMsgText = chat.last_message.content.length > 30 
                                ? chat.last_message.content.substring(0, 30) + '...' 
                                : chat.last_message.content;
                        }
                        
                        // Время последнего сообщения
                        let lastMsgTime = '';
                        if (chat.last_message?.timestamp) {
                            const now = new Date();
                            const moscowNow = new Date(now.getTime() + 3*60*60*1000);
                            const yesterday = new Date(moscowNow);
                            yesterday.setDate(yesterday.getDate() - 1);
                            
                            const msgDate = new Date(new Date(chat.last_message.timestamp).getTime() + 3*60*60*1000);
                            const msgDateStr = msgDate.toDateString();
                            const todayStr = moscowNow.toDateString();
                            const yesterdayStr = yesterday.toDateString();
                            
                            if (msgDateStr === todayStr) {
                                lastMsgTime = msgDate.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
                            } else if (msgDateStr === yesterdayStr) {
                                lastMsgTime = 'Вчера';
                            } else {
                                lastMsgTime = msgDate.toLocaleDateString('ru-RU', {day:'numeric', month:'numeric'});
                            }
                        }
                        
                        // Галочки для последнего сообщения (если от меня)
                        let lastMsgCheckmarks = '';
                        if (chat.last_message && chat.last_message.sender_id === currentUser?.id) {
                            // Для избранного - всегда две галочки, иначе зависит от is_read
                            const isRead = chat.chat_type === 'saved' || chat.last_message.is_read;
                            lastMsgCheckmarks = isRead ? '<span class="chat-item-checkmarks read">✓✓</span>' : '<span class="chat-item-checkmarks">✓</span>';
                        }
                        
                        const badgeHtml = unreadCount > 0 ? `<span class="unread-badge-chat">${unreadCount > 99 ? '99+' : unreadCount}</span>` : '';
                        
                        el.innerHTML = `<div class="chat-avatar">${avatarHtml}</div><div class="chat-info">
                                <div class="chat-name">${chatName}</div>
                                <div class="last-message">
                                    <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${lastMsgText}</span>
                                </div>
                            </div>
                            <div class="chat-item-time">${lastMsgTime}${lastMsgCheckmarks}</div>
                            ${badgeHtml}
                        `;
                        
                        chatsList.appendChild(el);
                    }
                } catch (e) {
                    console.error('Ошибка загрузки чатов:', e);
                }
            }

            function updateChatBadge(chatId, unreadCount) {
                const chatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
                if (!chatItem) return;
                
                // Удаляем старый бейджик
                const oldBadge = chatItem.querySelector('.unread-badge-chat');
                if (oldBadge) oldBadge.remove();
                
                // Добавляем новый если нужно
                if (unreadCount > 0) {
                    const badge = document.createElement('span');
                    badge.className = 'unread-badge-chat';
                    badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
                    chatItem.appendChild(badge);
                }
            }

            async function selectChat(chatId) {
                currentChatId = chatId;
                localStorage.setItem('currentChatId', chatId);
                
                // Сброс всего нахуй
                messages = [];
                currentPage = 0;
                hasMoreMessages = true;
                
                // Обновляем активный класс
                document.querySelectorAll('.chat-item').forEach(item => {
                    item.classList.remove('active');
                });
                
                const currentChatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
                if (currentChatItem) currentChatItem.classList.add('active');
                
                if (window.innerWidth <= 768) toggleSidebar();
                
                try {
                    // Загружаем инфо о чате
                    const chatResponse = await fetch(`/api/chats/${chatId}`, {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!chatResponse.ok) return;
                    const chat = await chatResponse.json();
                    
                    document.querySelector('.chat-main').setAttribute('data-chat-type', chat.chat_type);
                    
                    // Обновляем шапку
                    const otherUser = chat.participants?.find(p => p.id !== currentUser?.id);
                    if (chat.chat_type === 'saved') {
                        document.getElementById('chatAvatar').textContent = '⭐';
                        document.getElementById('chatName').textContent = '⭐ Избранное';
                        document.getElementById('chatStatus').innerHTML = '<span class="status-text">Ваши сохранённые сообщения</span>';
                    } else {
                        const chatName = chat.name || otherUser?.username || 'Чат';
                        document.getElementById('chatName').textContent = chatName;
                        // Показываем аватар если есть
                        if (otherUser?.avatar) {
                            document.getElementById('chatAvatar').innerHTML = `<img src="${otherUser.avatar}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
                        } else {
                            document.getElementById('chatAvatar').textContent = chatName[0].toUpperCase();
                        }
                    }
                    
                    // Загружаем статус пользователя (для обычных чатов)
                    if (otherUser) {
                        await loadUserStatus(otherUser.id);
                    }
                    
                    // ГРУЗИМ СООБЩЕНИЯ
                    const container = document.getElementById('messagesContainer');
                    container.innerHTML = '<div class="loading" style="text-align: center; padding: 20px;">Загрузка...</div>';
                    
                    const msgs = await loadMessages(chatId, 0);
                    container.innerHTML = '';
                    
                    if (msgs.length === 0) {
                        container.innerHTML = '<div class="empty-state">Нет сообщений</div>';
                    } else {
                        msgs.forEach(msg => {
                            // Проверяем, нужно ли добавить специальный класс для избранного
                            if (chat.chat_type === 'saved' && 
                                (msg.content.includes('ИЗБРАННОЕ') || msg.content.includes('⭐'))) {
                                
                                // Создаем сообщение вручную с классом
                                const isSent = msg.sender_id === currentUser?.id;
                                const msgDiv = document.createElement('div');
                                msgDiv.className = `message ${isSent ? 'sent' : 'received'} saved-welcome`;
                                msgDiv.setAttribute('data-id', msg.uuid);
                                
                                let content = (msg.content || '')
                                    .replace(/&/g, '&amp;')
                                    .replace(/</g, '&lt;')
                                    .replace(/>/g, '&gt;')
                                    .replace(/\\n/g, '<br>');
                                
                                const d = new Date(new Date(msg.timestamp).getTime() + 3*60*60*1000);
                                const time = d.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
                                
                                msgDiv.innerHTML = `<div>${content}</div><div class="message-info">${time}</div>`;
                                container.appendChild(msgDiv);
                            } else {
                                // Обычное сообщение через твою функцию
                                addMessageToChat(msg);
                            }
                        });
                    }
                    
                    container.scrollTop = container.scrollHeight;
                    
                    // Активируем поле
                    document.getElementById('messageText').disabled = false;
                    document.getElementById('sendMessageBtn').disabled = false;
                    
                    // Отмечаем прочитанным
                    markChatAsRead(chatId);
                    
                } catch (error) {
                    console.error('Ошибка:', error);
                }
            }

            function addMessageToChat(message) {
                const container = document.getElementById('messagesContainer');
                if (!container) return;
                
                // Проверка на дубликат
                if (document.querySelector(`[data-id="${message.uuid}"]`)) return;
                
                const isSent = message.sender_id === currentUser?.id;
                
                // Добавляем в массив
                if (!message.uuid?.startsWith('temp_')) {
                    messages.push(message);
                }
                
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${isSent ? 'sent' : 'received'}`;
                messageDiv.setAttribute('data-id', message.uuid);
                
                let content = (message.content || '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/\n/g, '<br>');
                
                let time = '';
                if (message.status === 'sending') time = '⏳';
                else if (message.status === 'error') time = '❌';
                else {
                    const d = new Date(new Date(message.timestamp).getTime() + 3*60*60*1000);
                    const timeStr = d.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
                    const isSentMessage = message.sender_id === currentUser?.id;
                    const checkmarks = isSentMessage ? (message.is_read ? '✓✓' : '✓') : '';
                    time = isSentMessage ? (timeStr + ' ' + checkmarks) : timeStr;
                }
                
                // Удаляем заглушку если есть
                const emptyState = container.querySelector('.empty-state');
                if (emptyState) emptyState.remove();
                
                messageDiv.innerHTML = `<div>${content}</div><div class="message-info">${time}</div>`;
                container.appendChild(messageDiv);
                
                // Скролл если нужно
                const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
                if (atBottom || isSent) container.scrollTop = container.scrollHeight;
            }

            document.getElementById('sendMessageBtn').onclick = sendMessage;
            const messageInput = document.getElementById('messageText');
            const sendBtn = document.getElementById('sendMessageBtn');

            if (messageInput) {
                // Отключаем все возможные стандартные поведения
                messageInput.addEventListener('keydown', function(e) {
                    if (this.value.length >= 4000 && e.key !== 'Backspace' && e.key !== 'Delete') {
                        e.preventDefault();
                        alert('Максимум 4000 символов');
                        return;
                    }
                    if (e.key === 'Enter') {
                        if (e.shiftKey) {
                            // Shift+Enter - ДЕЛАЕМ ПЕРЕНОС СТРОКИ
                            e.preventDefault();
                            e.stopPropagation();
                            
                            const start = this.selectionStart;
                            const end = this.selectionEnd;
                            const currentValue = this.value;
                            
                            // Вставляем перенос строки (работает и в JS и в HTML)
                            this.value = currentValue.substring(0, start) + String.fromCharCode(10) + currentValue.substring(end);
                            
                            // Возвращаем курсор после вставленного переноса
                            this.selectionStart = this.selectionEnd = start + 1;
                            
                            // Принудительно обновляем высоту
                            this.style.height = 'auto';
                            this.style.height = (this.scrollHeight) + 'px';
                            
                            console.log('Перенос строки вставлен');
                            return false;
                        } else {
                            // Enter без Shift - отправляем
                            e.preventDefault();
                            sendMessage();
                            return false;
                        }
                    }
                }, true);
                
                // Отдельно обрабатываем input для авто-высоты
                messageInput.addEventListener('input', function() {
                    this.style.height = 'auto';
                    this.style.height = (this.scrollHeight) + 'px';

                    this.classList.remove('limit-warning', 'limit-danger');
                    
                    // Показываем счетчик если близко к лимиту
                    if (this.value.length > 3500) {
                        const remaining = 4000 - this.value.length;
                        if (remaining < 100) {
                            this.classList.add('limit-danger');
                            console.log('Критично мало символов:', remaining);
                        } else {
                            this.classList.add('limit-warning');
                            console.log('Близко к лимиту:', remaining);
                        }
                    }
                });
            }

            messageInput.addEventListener('focus', function() {
                if (!this.value) {
                    this.style.height = '56px';
                }
            });

            // При потере фокуса тоже сбрасываем если пусто
            messageInput.addEventListener('blur', function() {
                if (!this.value) {
                    this.style.height = '56px';
                }
            });

            document.getElementById('messagesContainer').addEventListener('scroll', function() {
                checkScrollPosition();
                
                if (this.scrollTop < 100 && !loadingMessages && hasMoreMessages) {
                    loadMoreMessages();
                }
                
                // Оптимизация: не рендерим при быстром скролле
                if (Math.abs(this.scrollTop - lastScrollTop) > 100) {
                    lastScrollTop = this.scrollTop;
                    return;
                }
            });
            
            async function sendMessage() {
                const input = document.getElementById('messageText');
                const content = input.value;
                
                if (content.length > 4000) {
                    alert('Сообщение не может быть длиннее 4000 символов');
                    return;
                }
                
                if (!content.trim() || !currentChatId) return;
                
                // Получаем UUID сообщения для ответа
                const replyToUuid = replyingToMessage ? replyingToMessage.uuid : null;
                
                // Создаем временное сообщение
                const tempMessage = {
                    uuid: 'temp_' + Date.now(),
                    content: content,
                    sender_id: currentUser?.id,
                    chat_id: currentChatId,
                    timestamp: new Date().toISOString(),
                    status: 'sending',
                    reply_to_uuid: replyToUuid
                };
                
                // Добавляем в массив
                messages.push(tempMessage);
                
                // Добавляем в DOM (БЕЗ ПЕРЕРЕНДЕРА!)
                addMessageToChat(tempMessage);
                
                input.value = '';
                input.style.height = '56px';
                
                // Сбрасываем панель ответа
                if (replyingToMessage) {
                    cancelReply();
                }
                
                try {
                    const response = await fetch('/api/messages', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${accessToken}`
                        },
                        body: JSON.stringify({
                            content, 
                            chat_id: currentChatId,
                            reply_to_uuid: replyToUuid
                        })
                    });
                    
                    if (response.ok) {
                        const realMessage = await response.json();
                        
                        // Удаляем временное
                        const tempElement = document.querySelector(`[data-id="${tempMessage.uuid}"]`);
                        if (tempElement) tempElement.remove();
                        
                        messages = messages.filter(m => m.uuid !== tempMessage.uuid);
                        
                        // Добавляем реальное
                        addMessageToChat(realMessage);
                        
                        // ВАЖНО: перерисовываем для правильных дат
                        renderMessages();
                        
                        updateChatInList(currentChatId, realMessage);
                    }
                } catch (e) {
                    console.error('Ошибка:', e);
                }
            }

            // ========== ПОИСК ==========
            let searchTimeout;
            document.getElementById('searchInput').addEventListener('input', function(e) {
                const query = e.target.value.trim();
                
                clearTimeout(searchTimeout);
                
                if (!query) {
                    loadChats();
                    return;
                }
                
                if (query.length < 2) return;
                
                searchTimeout = setTimeout(async () => {
                    try {
                        const response = await fetch(`/api/users/search?q=${encodeURIComponent(query)}`, {
                            headers: {'Authorization': `Bearer ${accessToken}`}
                        });
                        
                        if (!response.ok) return;
                        
                        const users = await response.json();
                        
                        const chatsList = document.getElementById('chatsList');
                        let html = '<div style="padding: 10px; color: var(--text-muted);">РЕЗУЛЬТАТЫ ПОИСКА:</div>';
                        
                        users.forEach(user => {
                            if (user.id === currentUser?.id) return;
                            
                            // Аватар: если есть изображение - показываем, иначе первую букву имени
                            let avatarHtml = '';
                            if (user.avatar) {
                                avatarHtml = '<img src="' + user.avatar + '" alt="' + user.username + '">';
                            } else {
                                avatarHtml = user.username[0].toUpperCase();
                            }
                            
                            html += '<div class="chat-item" onclick="createChatWithUser(' + user.id + ')"><div class="chat-avatar">' + avatarHtml + '</div><div class="chat-info"><div class="chat-name">' + user.username + '</div><div class="last-message">Нажмите чтобы начать чат</div></div></div>';
                        });
                        
                        chatsList.innerHTML = html;
                        
                    } catch (e) {}
                }, 500);
            });

            async function createChatWithUser(userId) {
                try {
                    const response = await fetch('/api/chats', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${accessToken}`
                        },
                        body: JSON.stringify({user_ids: [userId]})
                    });
                    
                    if (!response.ok) {
                        throw new Error('Ошибка создания чата');
                    }
                    
                    const chat = await response.json();
                    
                    document.getElementById('searchInput').value = '';
                    await selectChat(chat.id);
                    await loadChats();
                    
                } catch (error) {
                    console.error('Ошибка:', error);
                    alert('Не удалось создать чат');
                }
            }

            // ========== НАСТРОЙКИ ==========
            window.openSettings = function() {
                const overlay = document.createElement('div');
                overlay.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0,0,0,0.5);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 10000;
                    padding: 16px;
                `;
                
                const modal = document.createElement('div');
                modal.style.cssText = `
                    background: var(--bg-white);
                    border-radius: 28px;
                    width: 100%;
                    max-width: 450px;
                    max-height: 90vh;
                    overflow-y: auto;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                `;
                
                modal.innerHTML = `
                    <div style="padding: 24px;">
                        <h2 style="margin:0 0 24px 0; color: var(--text-primary);">⚙️ Настройки</h2>
                        
                        <!-- АВАТАР -->
                        <div style="margin-bottom: 24px; padding: 16px; background: var(--input-bg); border-radius: 16px; text-align: center;">
                            <div style="margin-bottom: 12px;">
                                <div id="settingsAvatarPlaceholder" style="width: 80px; height: 80px; border-radius: 50%; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); display: inline-flex; align-items: center; justify-content: center; color: white; font-size: 32px; font-weight: bold;">
                                    ${currentUser?.username ? currentUser.username[0].toUpperCase() : 'U'}
                                </div>
                                <img id="settingsAvatarImg" style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover; display: none;" alt="Аватар">
                            </div>
                            <input type="file" id="avatarInput" accept="image/jpeg,image/png,image/gif,image/webp" style="display: none;">
                            <button onclick="document.getElementById('avatarInput').click()" style="padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 10px; cursor: pointer; margin-right: 8px;">📷 Выбрать фото</button>
                            <button id="deleteAvatarBtn" onclick="deleteUserAvatar()" style="padding: 10px 20px; background: #ff4757; color: white; border: none; border-radius: 10px; cursor: pointer; display: none;">🗑️ Удалить</button>
                            <div id="avatarStatus" style="margin-top: 10px; font-size: 13px; color: var(--text-secondary);"></div>
                        </div>
                        
                        <div style="margin-bottom: 24px; padding: 16px; background: var(--input-bg); border-radius: 16px;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <div>
                                    <div style="font-weight: 600; margin-bottom: 4px; color: var(--text-primary);">🌙 Тёмная тема</div>
                                    <div style="font-size: 13px; color: var(--text-secondary);" id="themeHint">☀️ Светлая тема</div>
                                </div>
                                
                                <label style="display: flex; align-items: center; gap: 10px; cursor: pointer;">
                                    <input type="checkbox" id="themeToggle" style="width: 20px; height: 20px; cursor: pointer;">
                                    <span id="toggleThemeText" style="color: var(--text-primary);">Выкл</span>
                                </label>
                            </div>
                        </div>
                        
                        <div style="margin-bottom: 24px;">
                            <label style="display: block; margin-bottom: 8px; color: var(--text-primary);">Имя</label>
                            <input type="text" id="settingsUsername" value="${currentUser?.username || ''}" style="width: 100%; padding: 14px; border: 2px solid var(--border-color); border-radius: 14px; margin-bottom: 16px; background: var(--input-bg); color: var(--text-primary);">
                            
                            <label style="display: block; margin-bottom: 8px; color: var(--text-primary);">Email</label>
                            <input type="email" id="settingsEmail" value="${currentUser?.email || ''}" style="width: 100%; padding: 14px; border: 2px solid var(--border-color); border-radius: 14px; margin-bottom: 16px; background: var(--input-bg); color: var(--text-primary);">
                        </div>
                        
                        <div style="margin-bottom: 24px; padding: 16px; background: var(--input-bg); border-radius: 16px;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <div>
                                    <div style="font-weight: 600; margin-bottom: 4px; color: var(--text-primary);">👻 Режим невидимки</div>
                                    <div style="font-size: 13px; color: var(--text-secondary);" id="invisibleHint">⚡ Все видят твой статус</div>
                                </div>
                                
                                <label style="display: flex; align-items: center; gap: 10px; cursor: pointer;">
                                    <input type="checkbox" id="invisibleToggle" style="width: 20px; height: 20px; cursor: pointer;">
                                    <span id="toggleStatusText" style="color: var(--text-primary);">Выкл</span>
                                </label>
                            </div>
                        </div>
                        
                        <div style="display: flex; gap: 12px;">
                            <button onclick="closeSettingsModal()" style="flex:1; padding: 16px; background: var(--input-bg); border: 1px solid var(--border-color); border-radius: 16px; cursor: pointer; color: var(--text-primary); font-weight: 600;">Отмена</button>
                            <button onclick="saveSettings()" style="flex:1; padding: 16px; background: linear-gradient(135deg,#667eea,#764ba2); color: white; border: none; border-radius: 16px; cursor: pointer; font-weight: 600;">Сохранить</button>
                        </div>
                    </div>
                `;
                
                overlay.appendChild(modal);
                document.body.appendChild(overlay);
                
                // Показываем аватар если есть в настройках
                if (currentUser && currentUser.avatar) {
                    const avatarImg = document.getElementById('settingsAvatarImg');
                    const avatarPlaceholder = document.getElementById('settingsAvatarPlaceholder');
                    const deleteBtn = document.getElementById('deleteAvatarBtn');
                    
                    if (avatarImg) {
                        avatarImg.src = currentUser.avatar;
                        avatarImg.style.display = 'block';
                    }
                    if (avatarPlaceholder) avatarPlaceholder.style.display = 'none';
                    if (deleteBtn) deleteBtn.style.display = 'inline-block';
                }
                
                const themeToggle = document.getElementById('themeToggle');
                const themeHint = document.getElementById('themeHint');
                const themeText = document.getElementById('toggleThemeText');
                
                if (themeToggle && themeHint && themeText) {
                    const isDark = localStorage.getItem('theme') === 'dark';
                    themeToggle.checked = isDark;
                    
                    if (isDark) {
                        themeHint.innerHTML = '🌙 Тёмная тема включена';
                        themeText.textContent = 'Вкл';
                    } else {
                        themeHint.innerHTML = '☀️ Светлая тема';
                        themeText.textContent = 'Выкл';
                    }
                    
                    themeToggle.onchange = function() {
                        if (themeToggle.checked) {
                            themeHint.innerHTML = '🌙 Тёмная тема включена';
                            themeText.textContent = 'Вкл';
                        } else {
                            themeHint.innerHTML = '☀️ Светлая тема';
                            themeText.textContent = 'Выкл';
                        }
                    };
                }
                
                const toggle = document.getElementById('invisibleToggle');
                const hint = document.getElementById('invisibleHint');
                const statusText = document.getElementById('toggleStatusText');
                
                if (toggle && hint && statusText && currentUser) {
                    const isInvisible = !currentUser.show_status && !currentUser.show_last_seen;
                    toggle.checked = isInvisible;
                    
                    if (isInvisible) {
                        hint.innerHTML = '👻 Никто не видит твой онлайн';
                        statusText.textContent = 'Вкл';
                    } else {
                        hint.innerHTML = '⚡ Все видят твой статус';
                        statusText.textContent = 'Выкл';
                    }
                    
                    toggle.onchange = function() {
                        if (toggle.checked) {
                            hint.innerHTML = '👻 Никто не видит твой онлайн';
                            statusText.textContent = 'Вкл';
                        } else {
                            hint.innerHTML = '⚡ Все видят твой статус';
                            statusText.textContent = 'Выкл';
                        }
                    };
                }
            };

            window.closeSettingsModal = function() {
                const overlay = document.querySelector('[style*="position: fixed;"]');
                if (overlay) overlay.remove();
            };

            window.saveSettings = async function() {
                const username = document.getElementById('settingsUsername').value.trim();
                const email = document.getElementById('settingsEmail').value.trim();
                const invisibleMode = document.getElementById('invisibleToggle').checked;
                const darkMode = document.getElementById('themeToggle').checked;
                
                // Загружаем аватар если есть
                if (currentUser && currentUser.avatar) {
                    const avatarImg = document.getElementById('settingsAvatarImg');
                    const avatarPlaceholder = document.getElementById('settingsAvatarPlaceholder');
                    const deleteBtn = document.getElementById('deleteAvatarBtn');
                    
                    if (avatarImg) {
                        avatarImg.src = currentUser.avatar;
                        avatarImg.style.display = 'block';
                    }
                    if (avatarPlaceholder) avatarPlaceholder.style.display = 'none';
                    if (deleteBtn) deleteBtn.style.display = 'inline-block';
                }
                
                if (!username || !email) {
                    alert('❌ Заполни поля');
                    return;
                }
                
                localStorage.setItem('theme', darkMode ? 'dark' : 'light');
                applyTheme(darkMode);
                
                try {
                    const response = await fetch('/api/users/me', {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${accessToken}`
                        },
                        body: JSON.stringify({
                            username,
                            email,
                            show_status: !invisibleMode,
                            show_last_seen: !invisibleMode
                        })
                    });
                    
                    if (response.ok) {
                        const updatedUser = await response.json();
                        currentUser = updatedUser;
                        
                        document.getElementById('userName').textContent = updatedUser.username;
if (updatedUser.avatar) {
    document.getElementById('userAvatar').innerHTML = `<img src="${updatedUser.avatar}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
} else {
    document.getElementById('userAvatar').textContent = updatedUser.username[0].toUpperCase();
}
                        
                        document.querySelector('[style*="position: fixed;"]').remove();
                        
                        const notif = document.createElement('div');
                        notif.style.cssText = 'position:fixed; top:20px; right:20px; background:#2ecc71; color:white; padding:12px 24px; border-radius:12px; z-index:10001; font-weight:600;';
                        notif.textContent = invisibleMode ? '👻 Режим невидимки' : '✅ Сохранено';
                        document.body.appendChild(notif);
                        setTimeout(() => notif.remove(), 2000);
                    }
                } catch (e) {
                    alert('❌ Ошибка');
                }
            };

            // ========== АВАТАР ==========
            window.uploadAvatar = async function(file) {
                if (!file) return;
                
                const formData = new FormData();
                formData.append('file', file);
                
                const statusEl = document.getElementById('avatarStatus');
                if (statusEl) statusEl.textContent = '⏳ Загрузка...';
                
                try {
                    const response = await fetch('/api/users/me/avatar', {
                        method: 'POST',
                        headers: {'Authorization': `Bearer ${accessToken}`},
                        body: formData
                    });
                    
                    if (!response.ok) {
                        const err = await response.json();
                        throw new Error(err.detail || 'Ошибка загрузки');
                    }
                    
                    const data = await response.json();
                    
                    // Обновляем текущего пользователя
                    currentUser.avatar = data.avatar;
                    
                    // Обновляем UI
                    const avatarImg = document.getElementById('settingsAvatarImg');
                    const avatarPlaceholder = document.getElementById('settingsAvatarPlaceholder');
                    const deleteBtn = document.getElementById('deleteAvatarBtn');
                    
                    if (data.avatar) {
                        if (avatarImg) {
                            avatarImg.src = data.avatar;
                            avatarImg.style.display = 'block';
                        }
                        if (avatarPlaceholder) avatarPlaceholder.style.display = 'none';
                        if (deleteBtn) deleteBtn.style.display = 'inline-block';
                        
                        // Обновляем аватар в профиле
                        const userAvatar = document.getElementById('userAvatar');
                        if (userAvatar) {
                            userAvatar.innerHTML = `<img src="${data.avatar}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
                        }
                    }
                    
                    if (statusEl) statusEl.textContent = '✅ Аватар обновлён';
                    
                } catch (e) {
                    console.error('Ошибка загрузки аватара:', e);
                    if (statusEl) statusEl.textContent = '❌ ' + (e.message || 'Ошибка');
                }
            };
            
            window.deleteUserAvatar = async function() {
                if (!confirm('Удалить аватар?')) return;
                
                const statusEl = document.getElementById('avatarStatus');
                if (statusEl) statusEl.textContent = '⏳ Удаление...';
                
                try {
                    const response = await fetch('/api/users/me/avatar', {
                        method: 'DELETE',
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!response.ok) {
                        throw new Error('Ошибка удаления');
                    }
                    
                    // Обновляем текущего пользователя
                    currentUser.avatar = null;
                    
                    // Обновляем UI
                    const avatarImg = document.getElementById('settingsAvatarImg');
                    const avatarPlaceholder = document.getElementById('settingsAvatarPlaceholder');
                    const deleteBtn = document.getElementById('deleteAvatarBtn');
                    
                    if (avatarImg) avatarImg.style.display = 'none';
                    if (avatarPlaceholder) avatarPlaceholder.style.display = 'flex';
                    if (deleteBtn) deleteBtn.style.display = 'none';
                    
                    // Обновляем аватар в профиле
                    const userAvatar = document.getElementById('userAvatar');
                    if (userAvatar) {
                        userAvatar.innerHTML = currentUser.username[0].toUpperCase();
                    }
                    
                    if (statusEl) statusEl.textContent = '✅ Аватар удалён';
                    
                } catch (e) {
                    console.error('Ошибка удаления аватара:', e);
                    if (statusEl) statusEl.textContent = '❌ Ошибка';
                }
            };
            
            // Обработчик для выбора файла
            document.addEventListener('change', function(e) {
                if (e.target && e.target.id === 'avatarInput' && e.target.files[0]) {
                    uploadAvatar(e.target.files[0]);
                }
            });

            // ========== ВЫХОД ==========
            window.logout = function() {
                isLoggingOut = true;
                
                if (ws) {
                    ws.onclose = null;
                    ws.close();
                    ws = null;
                }
                
                localStorage.removeItem('accessToken');
                localStorage.removeItem('refreshToken');
                localStorage.removeItem('currentChatId');
                
                accessToken = null;
                refreshToken = null;
                currentUser = null;
                currentChatId = null;
                
                document.getElementById('authContainer').style.display = 'block';
                document.getElementById('messengerContainer').style.display = 'none';
                
                document.getElementById('loginUsername').value = '';
                document.getElementById('loginPassword').value = '';
                document.getElementById('regUsername').value = '';
                document.getElementById('regEmail').value = '';
                document.getElementById('regPassword').value = '';
                document.getElementById('regPasswordConfirm').value = '';
                
                isLoggingOut = false;
            };
            // ========== ПРОСТЫЕ ИСПРАВЛЕНИЯ ==========
            // Очистка дубликатов чатов
            function removeDuplicateChats() {
                const chatItems = document.querySelectorAll('.chat-item');
                const seen = new Set();
                
                chatItems.forEach(item => {
                    const id = item.getAttribute('data-chat-id');
                    if (seen.has(id)) {
                        item.remove();
                    } else {
                        seen.add(id);
                    }
                });
            }

            // Принудительная перезагрузка чата
            async function forceReloadChat(chatId) {
                const container = document.getElementById('messagesContainer');
                container.innerHTML = '<div class="loading">Загрузка...</div>';
                
                const messages = await loadMessages(chatId, 0);
                container.innerHTML = '';
                
                messages.forEach(msg => {
                    addMessageToChat(msg);
                });
                
                container.scrollTop = container.scrollHeight;
            }

            // Очистка кэша сообщений
            function clearMessageCache() {
                messages = [];
                currentPage = 0;
                hasMoreMessages = true;
            }


            // ========== КОНТЕКСТНОЕ МЕНЮ СООБЩЕНИЙ ==========
            let currentMessageMenu = null;
            let replyingToMessage = null;
            
            // Инициализация обработчиков сообщений
            function initMessageHandlers() {
                const container = document.getElementById('messagesContainer');
                if (!container) return;
                
                // Удаляем старые обработчики
                container.removeEventListener('contextmenu', handleContextMenu);
                container.removeEventListener('touchstart', handleTouchStart, {passive: false});
                document.removeEventListener('click', hideMessageMenu);
                
                // Добавляем новые
                container.addEventListener('contextmenu', handleContextMenu);
                container.addEventListener('touchstart', handleTouchStart, {passive: false});
                document.addEventListener('click', hideMessageMenu);
            }
            
            // Обработчик правой кнопки мыши (ПК)
            function handleContextMenu(e) {
                const messageEl = e.target.closest('.message');
                if (!messageEl) return;
                
                e.preventDefault();
                showMessageMenu(messageEl, e.clientX, e.clientY);
            }
            
            // Обработчик долгого нажатия (мобильные)
            let touchTimer = null;
            function handleTouchStart(e) {
                const messageEl = e.target.closest('.message');
                if (!messageEl) return;
                
                // Игнорируем если это ссылка или кнопка
                if (e.target.closest('a') || e.target.closest('button')) return;
                
                clearTimeout(touchTimer);
                touchTimer = setTimeout(() => {
                    const rect = messageEl.getBoundingClientRect();
                    showMessageMenu(messageEl, rect.left + rect.width/2, rect.top + rect.height/2);
                }, 500);
            }
            
            function showMessageMenu(messageEl, x, y) {
                const uuid = messageEl.getAttribute('data-id');
                if (!uuid) return;
                
                // Находим сообщение в массиве
                const msg = messages.find(m => m.uuid === uuid);
                if (!msg) return;
                
                // Проверяем, удалено ли сообщение
                if (msg.is_deleted) return;
                
                currentMessageMenu = { element: messageEl, uuid: uuid, message: msg };
                
                hideMessageMenu(); // Скрываем старое меню
                
                const isMyMessage = msg.sender_id === currentUser?.id;
                
                let menuHtml = `
                    <div class="context-menu-item" onclick="replyToMessage('${uuid}')">
                        <span class="icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path>
                            </svg>
                        </span>
                        Ответить
                    </div>
                    <div class="context-menu-item" onclick="copyMessage('${uuid}')">
                        <span class="icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                        </span>
                        Копировать
                    </div>
                `;
                
                // Добавляем удаление только для своих сообщений
                if (isMyMessage) {
                    menuHtml += `
                        <div class="context-menu-divider"></div>
                        <div class="context-menu-item danger" onclick="deleteMessage('${uuid}')">
                            <span class="icon">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                </svg>
                            </span>
                            Удалить
                        </div>
                    `;
                }
                
                const menu = document.createElement('div');
                menu.className = 'context-menu';
                menu.innerHTML = menuHtml;
                menu.id = 'messageContextMenu';
                
                // Позиционирование
                document.body.appendChild(menu);
                
                const menuRect = menu.getBoundingClientRect();
                const windowWidth = window.innerWidth;
                const windowHeight = window.innerHeight;
                
                // Корректировка позиции для мобильных
                if (windowWidth <= 768) {
                    menu.style.left = '0';
                    menu.style.right = '0';
                    menu.style.bottom = '0';
                    menu.style.top = 'auto';
                } else {
                    // Для ПК
                    let left = x - 10;
                    let top = y - 10;
                    
                    // Не выходить за границы экрана
                    if (left + menuRect.width > windowWidth) {
                        left = windowWidth - menuRect.width - 10;
                    }
                    if (top + menuRect.height > windowHeight) {
                        top = windowHeight - menuRect.height - 10;
                    }
                    
                    menu.style.left = left + 'px';
                    menu.style.top = top + 'px';
                }
                
                // Звук для мобильных
                if (windowWidth <= 768) {
                    // nothing special
                }
            }
            
            function hideMessageMenu() {
                const menu = document.getElementById('messageContextMenu');
                if (menu) {
                    menu.remove();
                }
                currentMessageMenu = null;
            }
            
            // Функция ответа на сообщение
            async function replyToMessage(uuid) {
                hideMessageMenu();
                
                const msg = messages.find(m => m.uuid === uuid);
                if (!msg) return;
                
                replyingToMessage = msg;
                
                const replyPanel = document.getElementById('replyPanel');
                const replyName = document.getElementById('replyName');
                const replyText = document.getElementById('replyText');
                
                // Получаем имя отправителя
                let senderName = msg.sender_username || 'Пользователь';
                if (msg.sender_id === currentUser?.id) {
                    senderName = 'Вы';
                }
                
                replyName.textContent = 'Ответ ' + senderName;
                
                // Обрезаем текст если длинный
                let content = msg.content || '';
                if (content.length > 50) {
                    content = content.substring(0, 50) + '...';
                }
                replyText.textContent = content;
                
                replyPanel.classList.add('active');
                
                // Фокус на поле ввода
                const input = document.getElementById('messageText');
                if (input) {
                    input.focus();
                }
            }
            
            // Отмена ответа
            function cancelReply() {
                replyingToMessage = null;
                const replyPanel = document.getElementById('replyPanel');
                replyPanel.classList.remove('active');
            }
            
            // Копировать сообщение
            async function copyMessage(uuid) {
                hideMessageMenu();
                
                const msg = messages.find(m => m.uuid === uuid);
                if (!msg) return;
                
                try {
                    await navigator.clipboard.writeText(msg.content);
                    showCopyToast();
                } catch (e) {
                    // Fallback для старых браузеров
                    const textarea = document.createElement('textarea');
                    textarea.value = msg.content;
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    showCopyToast();
                }
            }
            
            function showCopyToast() {
                // Удаляем старый тост
                const oldToast = document.querySelector('.copy-toast');
                if (oldToast) oldToast.remove();
                
                const toast = document.createElement('div');
                toast.className = 'copy-toast';
                toast.textContent = '✅ Скопировано!';
                document.body.appendChild(toast);
                
                setTimeout(() => {
                    toast.remove();
                }, 2000);
            }
            
            async function deleteChatIfEmpty(chatId) {
                try {
                    const response = await fetch(`/api/chats/${chatId}/messages?limit=1`, {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!response.ok) return;
                    
                    const messages = await response.json();
                    
                    // Если сообщений действительно нет
                    if (messages.length === 0) {
                        // Удаляем чат с сервера
                        await fetch(`/api/chats/${chatId}`, {
                            method: 'DELETE',
                            headers: {'Authorization': `Bearer ${accessToken}`}
                        });
                        
                        // Удаляем из DOM
                        const chatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
                        if (chatItem) chatItem.remove();
                        
                        // Если это был текущий чат - показываем заглушку
                        if (currentChatId === chatId) {
                            currentChatId = null;
                            localStorage.removeItem('currentChatId');
                            showEmptyChatState();
                        }
                        
                        console.log(`Чат ${chatId} удалён (пустой)`);
                    }
                } catch (e) {
                    console.error('Ошибка при проверке чата:', e);
                }
            }

            // Удаление сообщения
            async function deleteMessage(uuid) {
                hideMessageMenu();
                
                // Находим элемент сообщения
                const msgEl = document.querySelector(`.message[data-id="${uuid}"]`);
                if (!msgEl) return;
                
                // Находим предыдущий и следующий элементы
                const prevElement = msgEl.previousElementSibling;
                const nextElement = msgEl.nextElementSibling;
                
                // Анимация исчезновения
                msgEl.style.transition = 'all 0.3s ease';
                msgEl.style.opacity = '0';
                msgEl.style.transform = 'scale(0.8) translateY(-10px)';
                msgEl.style.margin = '0';
                msgEl.style.padding = '0';
                
                // Удаляем из массива сообщений
                messages = messages.filter(m => m.uuid !== uuid);
                
                setTimeout(() => {
                    // Удаляем сообщение из DOM
                    msgEl.remove();
                    
                    // ========== ПРОВЕРКА РАЗДЕЛИТЕЛЯ ПЕРЕД СООБЩЕНИЕМ ==========
                    if (prevElement && prevElement.classList.contains('date-separator')) {
                        // Проверяем, есть ли сообщения ПОСЛЕ ЭТОГО РАЗДЕЛИТЕЛЯ (не считая удалённое)
                        let hasMessageAfter = false;
                        let next = prevElement.nextElementSibling;
                        while (next) {
                            if (next.classList.contains('message') && next !== msgEl) {
                                hasMessageAfter = true;
                                break;
                            }
                            next = next.nextElementSibling;
                        }
                        
                        // Если после разделителя нет сообщений - удаляем разделитель
                        if (!hasMessageAfter) {
                            prevElement.remove();
                        }
                    }
                    
                    // ========== ПРОВЕРКА РАЗДЕЛИТЕЛЯ ПОСЛЕ СООБЩЕНИЯ ==========
                    if (nextElement && nextElement.classList.contains('date-separator')) {
                        // Проверяем, есть ли сообщения ДО ЭТОГО РАЗДЕЛИТЕЛЯ (не считая удалённое)
                        let hasMessageBefore = false;
                        let prev = nextElement.previousElementSibling;
                        while (prev) {
                            if (prev.classList.contains('message') && prev !== msgEl) {
                                hasMessageBefore = true;
                                break;
                            }
                            prev = prev.previousElementSibling;
                        }
                        
                        if (!hasMessageBefore) {
                            nextElement.remove();
                        }
                    }
                    // ========================================================
                    const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
        
                    // После удаления последнего сообщения
                    if (messages.length === 0) {
                        // Удаляем чат
                        deleteChatIfEmpty(currentChatId);
                    } else {
                        // Просто обновляем превью
                        updateChatInList(currentChatId, lastMessage);
                    }
                }, 300);
                
                // Отправляем запрос на удаление на сервере (в фоне)
                try {
                    await fetch(`/api/messages/${uuid}`, {
                        method: 'DELETE',
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                } catch (e) {
                    console.error('Ошибка удаления:', e);
                }
            }

            function showEmptyChatState() {
                const container = document.getElementById('messagesContainer');
                container.innerHTML = '<div class="empty-state"><span>Начните вашу переписку..</span></div>';
                
                // Отключаем поле ввода
                document.getElementById('messageText').disabled = true;
                document.getElementById('sendMessageBtn').disabled = true;

                // Убираем аватарку и название
                document.getElementById('chatAvatar').textContent = '';
                document.getElementById('chatName').textContent = 'Выберите чат';
                document.getElementById('chatStatus').innerHTML = '';
            }

            function handleMessageRead(data) {
                // Если это текущий чат - обновляем галочки у сообщений
                if (data.chat_id === currentChatId) {
                    messages.forEach((msg, index) => {
                        if (msg.sender_id === currentUser?.id && !msg.is_read) {
                            msg.is_read = true;
                            
                            // Обновляем конкретное сообщение в DOM
                            const msgEl = document.querySelector(`.message[data-id="${msg.uuid}"]`);
                            if (msgEl) {
                                const infoEl = msgEl.querySelector('.message-info');
                                if (infoEl) {
                                    const timeStr = infoEl.textContent.replace(/[✓✓✓]$/, '').trim();
                                    infoEl.textContent = timeStr + ' ✓✓';
                                }
                            }
                        }
                    });
                }
                
                // Обновляем галочку в списке чатов ТОЛЬКО если последнее сообщение от текущего пользователя
                if (data.chat_id === currentChatId && messages.length > 0) {
                    const lastMessage = messages[messages.length - 1];
                    if (lastMessage.sender_id === currentUser?.id) {
                        updateSpecificChatCheckmark(data.chat_id);
                    }
                }
            }

            function updateHeaderStatus(user) {
                const container = document.getElementById('chatStatus');
                if (!container) return;
                
                setTimeout(() => {
                    if (user.is_online) {
                        container.innerHTML = '<span class="user-status status-online"></span><span>В сети</span>';
                    } else if (user.last_seen) {
                        const lastSeenText = formatLastSeen(user.last_seen);
                        container.innerHTML = '<span class="user-status status-offline"></span><span>Был(а) ' + lastSeenText + '</span>';
                    } else {
                        container.innerHTML = '<span class="user-status status-offline"></span><span>Был(а) недавно</span>';
                    }
                    container.style.opacity = '1';
                }, 200);
            }

        </script>
    </body>
    </html>
    """

# ========== API ПОЛЬЗОВАТЕЛИ ==========
@app.get("/api/users/{user_id}/status")
async def get_user_status(
    user_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    """Получить статус пользователя с учетом настроек приватности"""
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Формируем ответ с учетом настроек
    status_response = {
        "user_id": user.id,
        "username": user.username,
        "is_online": False,
        "last_seen": None,
        "status_text": None,
        "custom_status": None
    }
    
    # Если пользователь разрешил показывать статус
    if user.show_status:
        status_response["is_online"] = user.is_online
        status_response["status_text"] = user.status_text
    
    # Если разрешено показывать "был в сети"
    if user.show_last_seen and not user.is_online:
        status_response["last_seen"] = user.last_seen.isoformat() if user.last_seen else None
    
    return status_response

@app.put("/api/users/me/settings")
async def update_user_settings(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    """Обновление настроек пользователя"""
    try:
        data = await request.json()
        
        if "show_status" in data:
            current_user.show_status = data["show_status"]
        if "show_last_seen" in data:
            current_user.show_last_seen = data["show_last_seen"]
        if "status_text" in data:
            current_user.status_text = data["status_text"]
        
        await db.commit()
        await db.refresh(current_user)
        
        return {"status": "success", "user": current_user}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/search", response_model=List[schemas.UserResponse])
async def search_users(
    q: str,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    result = await db.execute(
        select(models.User).where(
            and_(
                models.User.id != current_user.id,
                or_(
                    models.User.username.ilike(f"%{q}%"),
                    models.User.email.ilike(f"%{q}%")
                )
            )
        ).limit(20)
    )
    return result.scalars().all()

@app.get("/api/users/{user_id}", response_model=schemas.UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(database.get_db)
):
    result = await db.execute(
        select(models.User).where(models.User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/api/users/me")
async def update_user(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    try:
        data = await request.json()
        username = data.get("username")
        email = data.get("email")
        
        if username and username != current_user.username:
            result = await db.execute(
                select(models.User).where(models.User.username == username)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Username already taken")
            current_user.username = username
        
        if email and email != current_user.email:
            result = await db.execute(
                select(models.User).where(models.User.email == email)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Email already registered")
            current_user.email = email
        
        # Исправлено: добавляем обработку настроек приватности
        if "show_status" in data:
            current_user.show_status = data["show_status"]
        if "show_last_seen" in data:
            current_user.show_last_seen = data["show_last_seen"]
        
        await db.commit()
        await db.refresh(current_user)
        return current_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== API ЧАТЫ ==========
@app.get("/api/chats", response_model=List[schemas.ChatResponse])
async def get_user_chats(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    await ensure_saved_chat(current_user.id, db)
    
    result = await db.execute(
        select(models.Chat)
        .join(models.Chat.participants)
        .where(models.User.id == current_user.id)
        .options(
            selectinload(models.Chat.participants),
            selectinload(models.Chat.messages).selectinload(models.Message.sender)
        )
        .order_by(
            models.Chat.chat_type == 'saved',
            models.Chat.created_at.desc()
        )
    )
    
    chats = result.scalars().all()
    response_chats = []
    
    for chat in chats:
        # Фильтруем удалённые сообщения
        active_messages = [m for m in chat.messages if not m.is_deleted]
        messages = sorted(active_messages, key=lambda m: m.timestamp, reverse=True)
        last_message = messages[0] if messages else None
        
        # Добавляем sender_username для последнего сообщения
        if last_message and hasattr(last_message, 'sender') and last_message.sender:
            last_message.sender_username = last_message.sender.username
        
        if chat.chat_type == 'saved':
            chat.name = "⭐ Избранное"
        
        response_chats.append({
            "id": chat.id,
            "name": chat.name,
            "chat_type": chat.chat_type,
            "created_at": chat.created_at,
            "participants": chat.participants,
            "last_message": last_message
        })
    
    return response_chats

@app.get("/api/chats/{chat_id}", response_model=schemas.ChatResponse)
async def get_chat(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    result = await db.execute(
        select(models.Chat)
        .where(models.Chat.id == chat_id)
        .options(
            selectinload(models.Chat.participants),
            selectinload(models.Chat.messages).selectinload(models.Message.sender)
        )
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return chat

@app.post("/api/chats", response_model=schemas.ChatResponse)
async def create_chat(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    try:
        data = await request.json()
        user_ids = data.get("user_ids", [])
        
        if not user_ids:
            raise HTTPException(status_code=400, detail="user_ids is required")
        
        other_user_id = user_ids[0]
        
        # Проверяем существование пользователя
        result = await db.execute(
            select(models.User).where(models.User.id == other_user_id)
        )
        other_user = result.scalar_one_or_none()
        
        if not other_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Ищем существующий чат между пользователями
        stmt = text("""
        SELECT DISTINCT c.id 
        FROM chats c 
        JOIN chat_participants cp1 ON c.id = cp1.chat_id 
        JOIN chat_participants cp2 ON c.id = cp2.chat_id 
        WHERE c.chat_type = 'private' 
        AND cp1.user_id = :user1 
        AND cp2.user_id = :user2
        """)
        
        result = await db.execute(
            stmt, {"user1": current_user.id, "user2": other_user_id}
        )
        existing_row = result.first()
        
        if existing_row:
            # Чат уже существует - возвращаем его
            existing_chat_id = existing_row[0]
            chat_result = await db.execute(
                select(models.Chat)
                .where(models.Chat.id == existing_chat_id)
                .options(selectinload(models.Chat.participants))
            )
            return chat_result.scalar_one()
        
        # Если чата нет - создаем НОВЫЙ
        chat = models.Chat(
            name=None,
            chat_type="private",
            created_by=current_user.id
        )
        
        db.add(chat)
        await db.flush()
        
        # Добавляем участников
        await db.execute(
            text("INSERT INTO chat_participants (user_id, chat_id) VALUES (:uid, :cid)"),
            {"uid": current_user.id, "cid": chat.id}
        )
        await db.execute(
            text("INSERT INTO chat_participants (user_id, chat_id) VALUES (:uid, :cid)"),
            {"uid": other_user_id, "cid": chat.id}
        )
        
        await db.commit()
        
        # Загружаем чат с участниками для WebSocket уведомления
        chat_result = await db.execute(
            select(models.Chat)
            .where(models.Chat.id == chat.id)
            .options(selectinload(models.Chat.participants))
        )
        new_chat = chat_result.scalar_one()
        
        # Подключаем к комнатам и отправляем уведомление о новом чате
        await manager.join_chat(current_user.id, new_chat.id)
        await manager.join_chat(other_user_id, new_chat.id)
        
        ws_message = {
            "type": "new_chat",
            "chat": {
                "id": new_chat.id,
                "name": new_chat.name,
                "chat_type": new_chat.chat_type,
                "created_at": new_chat.created_at.isoformat() if new_chat.created_at else None,
                "participants": [
                    {"id": p.id, "username": p.username, "avatar": p.avatar, "is_online": p.is_online}
                    for p in new_chat.participants
                ]
            }
        }
        
        # Отправляем обоим участникам
        await manager.send_personal_message(ws_message, current_user.id)
        await manager.send_personal_message(ws_message, other_user_id)
        
        return new_chat
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chats/{chat_id}/messages", response_model=List[schemas.MessageResponse])
async def get_chat_messages(
    chat_id: int,
    limit: int = 100,
    offset: int = 0,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    chat_result = await db.execute(
        select(models.Chat)
        .where(models.Chat.id == chat_id)
        .options(selectinload(models.Chat.participants))
    )
    chat = chat_result.scalar_one_or_none()
    
    if not chat or current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages_result = await db.execute(
        select(models.Message)
        .where(
            models.Message.chat_id == chat_id,
            models.Message.is_deleted == False
        )
        .order_by(desc(models.Message.timestamp))
        .offset(offset)
        .limit(limit)
        .options(selectinload(models.Message.sender))
    )
    
    messages = messages_result.scalars().all()
    
    unread_messages = [m for m in messages if not m.is_read and m.sender_id != current_user.id]
    for msg in unread_messages:
        msg.is_read = True
    await db.commit()
    
    return sorted(messages, key=lambda m: m.timestamp)

@app.post("/api/chats/{chat_id}/read")
async def mark_chat_read(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    """Отметить все сообщения в чате как прочитанные"""
    await db.execute(
        text("""
            UPDATE messages 
            SET is_read = TRUE 
            WHERE chat_id = :chat_id 
            AND sender_id != :user_id 
            AND is_read = FALSE
        """),
        {"chat_id": chat_id, "user_id": current_user.id}
    )
    await db.commit()
    # Отправляем уведомление всем участникам чата
    ws_message = {
        "type": "message_read",
        "chat_id": chat_id,
        "user_id": current_user.id,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.broadcast_to_chat(ws_message, chat_id, exclude_user=current_user.id)

    return {"status": "ok"}

@app.get("/api/chats/{chat_id}/unread")
async def get_unread_count(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    """Получить количество непрочитанных сообщений в чате"""
    result = await db.execute(
        select(func.count(models.Message.id))
        .where(
            models.Message.chat_id == chat_id,
            models.Message.sender_id != current_user.id,
            models.Message.is_read == False
        )
    )
    count = result.scalar() or 0
    return {"count": count}

@app.delete("/api/chats/{chat_id}")
async def delete_chat(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    """Удалить чат (только если он пустой и принадлежит пользователю)"""
    # Проверяем, существует ли чат
    result = await db.execute(
        select(models.Chat)
        .where(models.Chat.id == chat_id)
        .options(selectinload(models.Chat.participants))
    )
    chat = result.scalar_one_or_none()
    
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Проверяем, является ли пользователь участником
    if current_user not in chat.participants:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Проверяем, есть ли сообщения в чате
    messages_result = await db.execute(
        select(models.Message).where(models.Message.chat_id == chat_id)
    )
    messages = messages_result.scalars().all()
    
    if messages:
        raise HTTPException(status_code=400, detail="Cannot delete non-empty chat")
    
    # Удаляем чат
    await db.delete(chat)
    await db.commit()
    
    return {"status": "ok"}

# ========== API СООБЩЕНИЯ ==========
@app.post("/api/messages", response_model=schemas.MessageResponse)
async def create_message(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    try:
        data = await request.json()
        chat_id = data.get("chat_id")
        content = data.get("content")
        reply_to_uuid = data.get("reply_to_uuid")
        
        # Находим ID сообщения для ответа
        reply_to_id = None
        if reply_to_uuid:
            reply_result = await db.execute(
                select(models.Message).where(models.Message.uuid == reply_to_uuid)
            )
            reply_message = reply_result.scalar_one_or_none()
            if reply_message:
                reply_to_id = reply_message.id
        
        if not chat_id or not content:
            raise HTTPException(status_code=400, detail="chat_id and content are required")
        
        chat_result = await db.execute(
            select(models.Chat)
            .where(models.Chat.id == chat_id)
            .options(selectinload(models.Chat.participants))
        )
        chat = chat_result.scalar_one_or_none()
        
        if not chat or current_user not in chat.participants:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Удаляем лишние пустые строки перед и после текста
        content = content.strip()
        # Удаляем пустые строки в начале и в конце, сохраняя переносы внутри
        lines = content.split('\n')
        # Убираем пустые строки с начала и конца
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        content = '\n'.join(lines)
        
        message = models.Message(
            content=content,
            sender_id=current_user.id,
            chat_id=chat_id,
            reply_to_id=reply_to_id
        )
        
        db.add(message)
        await db.commit()
        await db.refresh(message)
        await db.refresh(message, ['sender'])
        
        ws_message = {
            "type": "new_message",
            "message": {
                "uuid": message.uuid,
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
                "is_read": message.is_read,
                "is_edited": message.is_edited,
                "is_deleted": message.is_deleted,
                "sender_id": message.sender_id,
                "chat_id": message.chat_id,
                "sender_username": message.sender.username
            }
        }
        
        # Отправляем сообщение всем в чате, КРОМЕ отправителя
        await manager.broadcast_to_chat(ws_message, message.chat_id, exclude_user=current_user.id)
        
        return message
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/messages/{message_uuid}")
async def delete_message(
    message_uuid: str,
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    result = await db.execute(
        select(models.Message).where(models.Message.uuid == message_uuid)
    )
    message = result.scalar_one_or_none()
    
    if not message or message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete this message")
    
    # Удаляем сообщение полностью из базы данных
    await db.delete(message)
    await db.commit()
    
    return {"status": "ok"}

# ========== API АВАТАР ==========
@app.post("/api/users/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    """Загрузить аватар пользователя"""
    # Проверяем тип файла
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Недопустимый тип файла. Разрешены: JPG, PNG, GIF, WebP")
    
    # Проверяем размер файла (макс 5MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой. Максимум 5MB")
    
    # Создаем уникальное имя файла
    file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else 'jpg'
    avatar_filename = f"{current_user.id}_{uuid.uuid4()}.{file_ext}"
    avatar_path = os.path.join("uploads/avatars", avatar_filename)
    
    # Удаляем старый аватар если есть
    if current_user.avatar:
        old_avatar_path = os.path.join("uploads/avatars", current_user.avatar.split('/')[-1])
        if os.path.exists(old_avatar_path):
            try:
                os.remove(old_avatar_path)
            except:
                pass
    
    # Сохраняем новый аватар
    with open(avatar_path, "wb") as f:
        f.write(contents)
    
    # Обновляем путь в базе данных
    current_user.avatar = f"uploads/avatars/{avatar_filename}"
    await db.commit()
    await db.refresh(current_user)
    
    return {"avatar": current_user.avatar}

@app.delete("/api/users/me/avatar")
async def delete_avatar(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db)
):
    """Удалить аватар пользователя"""
    if current_user.avatar:
        # Удаляем файл
        avatar_filename = current_user.avatar.split('/')[-1]
        avatar_path = os.path.join("uploads/avatars", avatar_filename)
        if os.path.exists(avatar_path):
            try:
                os.remove(avatar_path)
            except:
                pass
        
        # Очищаем в базе данных
        current_user.avatar = None
        await db.commit()
        await db.refresh(current_user)
    
    # Возвращаем None как строку "null" для JSON
    return {"avatar": None}

# ========== WEBSOCKET ==========
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str
):
    try:
        from auth import SECRET_KEY, ALGORITHM
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        
        if not username:
            await websocket.close(code=1008, reason="Invalid token")
            return
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(models.User).where(models.User.username == username)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                await websocket.close(code=1008, reason="User not found")
                return
            
            await manager.connect(websocket, user.id)
            
            user.is_online = True
            user.last_seen = datetime.utcnow()
            await db.commit()
            
            try:
                chats_result = await db.execute(
                    select(models.Chat)
                    .join(models.Chat.participants)
                    .where(models.User.id == user.id)
                )
                user_chats = chats_result.scalars().all()
                
                for chat in user_chats:
                    await manager.join_chat(user.id, chat.id)
                
                await websocket.send_json({
                    "type": "connected",
                    "message": "WebSocket connected successfully",
                    "user_id": user.id
                })
                
                while True:
                    await websocket.receive_text()
                    
            except WebSocketDisconnect:
                await manager.disconnect(user.id)
                
                user.is_online = False
                user.last_seen = datetime.utcnow()
                await db.commit()
                
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
