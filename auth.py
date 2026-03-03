from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, APIRouter, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import models
import database
import schemas
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 часа
REFRESH_TOKEN_EXPIRE_DAYS = 30  # месяц

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Создаем роутер
router = APIRouter(prefix="/api/auth", tags=["auth"])

def verify_password(plain_password, hashed_password):
    """Проверка пароля с защитой от дурака"""
    print(f"!!! verify_password получила: {type(plain_password)}")
    print(f"!!! длина: {len(str(plain_password)) if plain_password else 0}")
    print(f"!!! первые 20 символов: {str(plain_password)[:20]}")
    
    # Если пришел не пароль, а что-то другое
    if not isinstance(plain_password, str) or len(plain_password) > 100:
        print("!!! ПОХОЖЕ, ЭТО НЕ ПАРОЛЬ, А ТОКЕН!")
        return False
    
    # Обрезаем до 72 байт
    password_bytes = plain_password.encode('utf-8')[:72]
    plain_password = password_bytes.decode('utf-8', errors='ignore')
    
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """Хеширование пароля с безопасным обрезанием"""
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')[:72]
        password = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(database.get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    result = await db.execute(
        select(models.User).where(models.User.username == username)
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return user

# ========== ЭНДПОИНТЫ ==========

@router.post("/register")
async def register(request: Request, db: AsyncSession = Depends(database.get_db)):
    print("="*50)
    print("REGISTER CALLED")
    print(f"Request headers: {request.headers}")
    """Регистрация нового пользователя"""
    try:
        # Получаем данные из тела запроса
        user_data = await request.json()
        logger.info(f"Register attempt with data: {user_data}")
        
        # Проверяем обязательные поля
        username = user_data.get("username")
        email = user_data.get("email")
        password = user_data.get("password")
        
        if not username or not email or not password:
            raise HTTPException(
                status_code=400, 
                detail=f"Missing fields: username={bool(username)}, email={bool(email)}, password={bool(password)}"
            )
        
        # Проверяем длину пароля
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        # Проверяем, не занят ли username или email
        result = await db.execute(
            select(models.User).where(
                (models.User.username == username) | 
                (models.User.email == email)
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            if existing.username == username:
                raise HTTPException(status_code=400, detail="Username already taken")
            else:
                raise HTTPException(status_code=400, detail="Email already registered")
        
        # Создаем пользователя
        hashed = get_password_hash(password)
        user = models.User(
            username=username,
            email=email,
            hashed_password=hashed
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        from main1 import ensure_saved_chat
        await ensure_saved_chat(user.id, db)
        
        # Токены
        access_token = create_access_token({"sub": user.username})
        refresh_token = create_refresh_token({"sub": user.username})
        
        response_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar": user.avatar,
            "is_online": user.is_online,
            "last_seen": user.last_seen.isoformat() if user.last_seen else None,
            "access_token": access_token,
            "refresh_token": refresh_token
        }
        
        logger.info(f"User registered successfully: {username}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/login")
async def login(request: Request, db: AsyncSession = Depends(database.get_db)):
    """Вход в систему"""
    try:
        # Получаем данные из тела запроса
        user_data = await request.json()
        logger.info(f"Login attempt with username: {user_data.get('username')}")
        
        username = user_data.get("username")
        password = user_data.get("password")
        
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password are required")
        
        # Ищем пользователя
        result = await db.execute(
            select(models.User).where(models.User.username == username)
        )
        user = result.scalar_one_or_none()
        
        if not user or not verify_password(password, user.hashed_password):
            logger.warning(f"Failed login attempt for username: {username}")
            raise HTTPException(status_code=401, detail="Invalid username or password")
        
        # Обновляем статус
        user.is_online = True
        user.last_seen = datetime.utcnow()
        await db.commit()
        
        # Токены
        access_token = create_access_token({"sub": user.username})
        refresh_token = create_refresh_token({"sub": user.username})
        
        response_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar": user.avatar,
            "is_online": user.is_online,
            "last_seen": user.last_seen.isoformat() if user.last_seen else None,
            "access_token": access_token,
            "refresh_token": refresh_token
        }
        
        logger.info(f"User logged in successfully: {username}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/refresh")
async def refresh_token(request: Request, db: AsyncSession = Depends(database.get_db)):
    """Обновление access token"""
    try:
        refresh_data = await request.json()
        refresh_token = refresh_data.get("refresh_token")
        
        if not refresh_token:
            raise HTTPException(status_code=400, detail="refresh_token is required")
        
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")
            
            username = payload.get("sub")
            result = await db.execute(
                select(models.User).where(models.User.username == username)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            
            # Новый access token
            new_access_token = create_access_token({"sub": user.username})
            return {"access_token": new_access_token}
            
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/me", response_model=schemas.UserResponse)
async def get_current_user_info(
    current_user: models.User = Depends(get_current_user)
):
    """Информация о текущем пользователе"""
    return current_user