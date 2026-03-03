from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request
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

import models
import schemas
import database
from websocket_manager import manager
from database import engine, AsyncSessionLocal
from auth import router as auth_router, get_current_user

# Создаем приложение
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

# ========== ФУНКЦИЯ СОЗДАНИЯ ИЗБРАННОГО ==========
async def ensure_saved_chat(user_id: int, db: AsyncSession):
    """Проверяет и создает чат 'Избранное' для пользователя"""
    result = await db.execute(
        select(models.Chat)
        .join(models.Chat.participants)
        .where(
            models.Chat.chat_type == 'saved',
            models.User.id == user_id
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
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <link rel="manifest" href="/static/manifest.json">
        <meta name="theme-color" content="#764ba2">
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

            /* EMPTY STATE */
            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-muted);
                font-size: 16px;
                text-align: center;
                padding: 20px;
            }
        </style>
    </head>
    <body>
        <div class="auth-container" id="authContainer">
            <h1>Пиздатый Мессенджер</h1>
            <div id="authError" class="error"></div>
            
            <input type="text" id="loginUsername" placeholder="Имя пользователя">
            <input type="password" id="loginPassword" placeholder="Пароль">
            
            <button id="loginBtn">🚪 Войти</button>
            
            <hr>
            
            <h3>Регистрация</h3>
            <input type="text" id="regUsername" placeholder="Имя пользователя">
            <input type="email" id="regEmail" placeholder="Email">
            <input type="password" id="regPassword" placeholder="Пароль">
            <input type="password" id="regPasswordConfirm" placeholder="Повторите пароль">
            
            <button id="registerBtn" style="background: #28a745;">📝 Зарегистрироваться</button>
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
                    <div class="avatar" id="chatAvatar">G</div>
                    <div class="user-info">
                        <h3 id="chatName">Выберите чат</h3>
                        <div class="status-container" id="chatStatus"></div>
                    </div>
                </div>
                
                <div class="messages-container" id="messagesContainer"></div>
                
                <div class="message-input">
                    <input type="text" id="messageText" placeholder="Написать сообщение..." disabled>
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
                    
                    document.getElementById('userName').textContent = currentUser.username;
                    document.getElementById('userAvatar').textContent = currentUser.username[0].toUpperCase();
                    
                    isLoggingOut = false;
                    
                    connectWebSocket();
                    await loadChats();
                    
                    if (currentChatId) {
                        await selectChat(parseInt(currentChatId));
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
                    
                    errorEl.style.color = 'green';
                    errorEl.textContent = 'Регистрация успешна! Теперь войдите.';
                    
                    document.getElementById('loginUsername').value = username;
                    
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
                            }
                            loadChats();
                        }
                        else if (data.type === 'user_status') {
                            if (currentChatId && currentUser && data.user_id !== currentUser.id) {
                                fetch(`/api/chats/${currentChatId}`, {
                                    headers: {'Authorization': `Bearer ${accessToken}`}
                                })
                                .then(r => r.json())
                                .then(chat => {
                                    const otherUser = chat.participants?.find(p => p.id !== currentUser.id);
                                    if (otherUser && otherUser.id === data.user_id) {
                                        const container = document.getElementById('chatStatus');
                                        if (container) {
                                            container.innerHTML = '<span class="user-status ' + (data.is_online ? 'status-online' : 'status-offline') + '"></span><span>' + (data.is_online ? 'В сети' : 'Был(а) недавно') + '</span>';
                                        }
                                    }
                                })
                                .catch(() => {});
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
            async function loadChats() {
                try {
                    const response = await fetch('/api/chats', {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!response.ok) return;
                    
                    const chats = await response.json();
                    
                    const chatsList = document.getElementById('chatsList');
                    chatsList.innerHTML = '';
                    
                    chats.forEach(chat => {
                        const isSaved = chat.chat_type === 'saved';
                        let chatName = isSaved ? '⭐ Избранное' : (chat.name || chat.participants?.find(p => p.id !== currentUser?.id)?.username || 'Чат');
                        let avatarText = isSaved ? '⭐' : chatName[0].toUpperCase();
                        
                        const el = document.createElement('div');
                        el.className = `chat-item ${chat.id == currentChatId ? 'active' : ''}`;
                        el.setAttribute('data-chat-id', chat.id);
                        el.setAttribute('data-chat-type', chat.chat_type);
                        el.onclick = () => selectChat(chat.id);
                        
                        el.innerHTML = `
                            <div class="chat-avatar">${avatarText}</div>
                            <div class="chat-info">
                                <div class="chat-name">${chatName}</div>
                                <div class="last-message">${chat.last_message?.content?.substring(0, 30) || '...'}</div>
                            </div>
                        `;

                        chatsList.appendChild(el);
                    });
                } catch (e) {}
            }

            // ========== ВЫБОР ЧАТА ==========
            async function selectChat(chatId) {
                currentChatId = chatId;
                localStorage.setItem('currentChatId', chatId);
                
                document.querySelectorAll('.chat-item').forEach(item => {
                    item.classList.remove('active');
                });
                
                const currentChatItem = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
                if (currentChatItem) {
                    currentChatItem.classList.add('active');
                }
                
                // Закрываем меню на мобилках
                if (window.innerWidth <= 768) {
                    toggleSidebar();
                }
                
                try {
                    const chatResponse = await fetch(`/api/chats/${chatId}`, {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!chatResponse.ok) return;
                    
                    const chat = await chatResponse.json();
                    
                    document.querySelector('.chat-main').setAttribute('data-chat-type', chat.chat_type);
                    
                    const otherUser = chat.participants?.find(p => p.id !== currentUser?.id);
                    
                    if (chat.chat_type === 'saved') {
                        document.getElementById('chatAvatar').textContent = '⭐';
                        document.getElementById('chatName').textContent = '⭐ Избранное';
                        document.getElementById('chatStatus').innerHTML = '<span class="status-text">Ваши сохранённые сообщения</span>';
                    } else {
                        const chatName = chat.name || otherUser?.username || 'Чат';
                        document.getElementById('chatName').textContent = chatName;
                        document.getElementById('chatAvatar').textContent = chatName[0].toUpperCase();
                        
                        if (otherUser) {
                            await loadUserStatus(otherUser.id);
                        }
                    }
                    
                    const messagesResponse = await fetch(`/api/chats/${chatId}/messages`, {
                        headers: {'Authorization': `Bearer ${accessToken}`}
                    });
                    
                    if (!messagesResponse.ok) return;
                    
                    const messages = await messagesResponse.json();
                    
                    const container = document.getElementById('messagesContainer');
                    container.innerHTML = '';
                    
                    messages.forEach(msg => addMessageToChat(msg));
                    
                    container.scrollTop = container.scrollHeight;
                    
                    document.getElementById('messageText').disabled = false;
                    document.getElementById('sendMessageBtn').disabled = false;
                    
                } catch (error) {
                    console.error('Ошибка выбора чата:', error);
                }
            }

            // ========== СООБЩЕНИЯ ==========
            function addMessageToChat(message) {
                const container = document.getElementById('messagesContainer');
                if (!container) return;
                
                const isSent = message.sender_id === currentUser?.id;
                
                const el = document.createElement('div');
                el.className = `message ${isSent ? 'sent' : 'received'}`;
                
                if (document.querySelector('.chat-main')?.getAttribute('data-chat-type') === 'saved') {
                    if (message.content.includes('ИЗБРАННОЕ') || message.content.includes('⭐')) {
                        el.classList.add('saved-welcome');
                    }
                }
                
                let formattedContent = message.content || '';
                formattedContent = formattedContent.replace(/\\n/g, '<br>');
                
                const msgDate = new Date(new Date(message.timestamp).getTime() + (3 * 60 * 60 * 1000));
                const time = msgDate.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'});
                
                el.innerHTML = `<div>${formattedContent}</div><div class="message-info">${time}</div>`;
                
                container.appendChild(el);
                container.scrollTop = container.scrollHeight;
            }

            document.getElementById('sendMessageBtn').onclick = sendMessage;
            document.getElementById('messageText').onkeypress = (e) => {
                if (e.key === 'Enter') sendMessage();
            };

            async function sendMessage() {
                const input = document.getElementById('messageText');
                const content = input.value.trim();
                
                if (!content || !currentChatId) return;
                
                try {
                    const response = await fetch('/api/messages', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${accessToken}`
                        },
                        body: JSON.stringify({content, chat_id: currentChatId})
                    });
                    
                    if (response.ok) {
                        input.value = '';
                    }
                } catch (e) {
                    console.error('Ошибка отправки:', e);
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
                            
                            html += '<div class="chat-item" onclick="createChatWithUser(' + user.id + ')"><div class="chat-avatar">' + user.username[0].toUpperCase() + '</div><div class="chat-info"><div class="chat-name">' + user.username + '</div><div class="last-message">Нажмите чтобы начать чат</div></div></div>';
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
                        document.getElementById('userAvatar').textContent = updatedUser.username[0].toUpperCase();
                        
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
        messages = sorted(chat.messages, key=lambda m: m.timestamp, reverse=True)
        last_message = messages[0] if messages else None
        
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
        
        # Возвращаем созданный чат
        chat_result = await db.execute(
            select(models.Chat)
            .where(models.Chat.id == chat.id)
            .options(selectinload(models.Chat.participants))
        )
        return chat_result.scalar_one()
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chats/{chat_id}/messages", response_model=List[schemas.MessageResponse])
async def get_chat_messages(
    chat_id: int,
    limit: int = 50,
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
        .where(models.Message.chat_id == chat_id)
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
        
        message = models.Message(
            content=content,
            sender_id=current_user.id,
            chat_id=chat_id
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
        
        # Отправляем сообщение всем в чате (включая отправителя)
        await manager.broadcast_to_chat(ws_message, message.chat_id, exclude_user=None)
        
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
    
    message.is_deleted = True
    message.content = "[deleted]"
    await db.commit()
    
    return {"status": "ok"}

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
