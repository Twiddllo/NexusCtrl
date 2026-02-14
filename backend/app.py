import os
import json
import enum
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Set

from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from pydantic_settings import BaseSettings
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON, Enum as SAEnum, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from jose import JWTError, jwt
from passlib.context import CryptContext
import redis.asyncio as aioredis
from contextlib import asynccontextmanager

class Settings(BaseSettings):
    APP_NAME: str = "NexusCtrl"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DATABASE_URL: str = "sqlite+aiosqlite:///./nexusctrl.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "nexusctrl-secret-key-change-in-production-2024"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:80", "http://localhost"]
    SSH_KEY_PATH: str = os.path.expanduser("~/.ssh")
    AGENT_SECRET: str = "nexusctrl-agent-secret"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

redis_client = None

async def get_redis():
    global redis_client
    if redis_client is None:
        try:
            redis_client = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            await redis_client.ping()
        except Exception:
            redis_client = None
            return None
    return redis_client

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"

class ServerStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"
    MAINTENANCE = "maintenance"

class ServerType(str, enum.Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"

class TaskStatus(str, enum.Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"

class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(SAEnum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True)
    avatar_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(ProjectStatus), default=ProjectStatus.ACTIVE)
    color = Column(String(7), default="#6366f1")
    icon = Column(String(50), default="folder")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    owner = relationship("User", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")

class Server(Base):
    __tablename__ = "servers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    hostname = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=True)
    port = Column(Integer, default=22)
    os_type = Column(SAEnum(ServerType), default=ServerType.LINUX)
    status = Column(SAEnum(ServerStatus), default=ServerStatus.OFFLINE)
    description = Column(Text, nullable=True)
    ssh_username = Column(String(100), nullable=True)
    ssh_key_path = Column(String(500), nullable=True)
    ssh_password_encrypted = Column(String(500), nullable=True)
    agent_id = Column(String(100), unique=True, nullable=True)
    agent_version = Column(String(20), nullable=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    ram_total_gb = Column(Integer, nullable=True)
    gpu_model = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    tasks = relationship("Task", back_populates="server")
    metrics = relationship("MetricSnapshot", back_populates="server", cascade="all, delete-orphan")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TaskStatus), default=TaskStatus.TODO)
    priority = Column(SAEnum(TaskPriority), default=TaskPriority.MEDIUM)
    tags = Column(JSON, default=list)
    order = Column(Integer, default=0)
    deadline = Column(DateTime(timezone=True), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User", back_populates="tasks", foreign_keys=[assignee_id])
    server = relationship("Server", back_populates="tasks")

class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    cpu_percent = Column(Float, nullable=True)
    cpu_per_core = Column(JSON, nullable=True)
    ram_percent = Column(Float, nullable=True)
    ram_used_gb = Column(Float, nullable=True)
    ram_total_gb = Column(Float, nullable=True)
    disk_percent = Column(Float, nullable=True)
    disk_read_mb = Column(Float, nullable=True)
    disk_write_mb = Column(Float, nullable=True)
    net_sent_mb = Column(Float, nullable=True)
    net_recv_mb = Column(Float, nullable=True)
    net_connections = Column(Integer, nullable=True)
    gpu_percent = Column(Float, nullable=True)
    gpu_memory_percent = Column(Float, nullable=True)
    gpu_memory_used_mb = Column(Float, nullable=True)
    gpu_temperature = Column(Float, nullable=True)
    gpu_processes = Column(JSON, nullable=True)
    download_speed_mbps = Column(Float, nullable=True)
    upload_speed_mbps = Column(Float, nullable=True)
    ping_ms = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    server = relationship("Server", back_populates="metrics")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class TokenRefresh(BaseModel):
    refresh_token: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None

class DashboardStats(BaseModel):
    total_servers: int
    online_servers: int
    total_projects: int
    active_projects: int
    total_tasks: int
    pending_tasks: int
    completed_tasks: int

class SystemHealth(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    database: bool
    redis: bool

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#6366f1"
    icon: str = "folder"

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None

class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: str
    color: str
    icon: str
    owner_id: int
    task_count: int = 0
    completed_tasks: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class ServerCreate(BaseModel):
    name: str
    hostname: str
    ip_address: Optional[str] = None
    port: int = 22
    os_type: str = "linux"
    description: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_key_path: Optional[str] = None

class ServerUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    os_type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_key_path: Optional[str] = None

class ServerResponse(BaseModel):
    id: int
    name: str
    hostname: str
    ip_address: Optional[str] = None
    port: int
    os_type: str
    status: str
    description: Optional[str] = None
    ssh_username: Optional[str] = None
    agent_id: Optional[str] = None
    agent_version: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    cpu_cores: Optional[int] = None
    ram_total_gb: Optional[int] = None
    gpu_model: Optional[str] = None
    task_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    class Config: from_attributes = True

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: List[str] = []
    due_date: Optional[datetime] = None
    server_id: Optional[int] = None
    project_id: Optional[int] = None

class TaskCreate(TaskBase):
    assignee_id: Optional[int] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    tags: Optional[List[str]] = None
    due_date: Optional[datetime] = None
    server_id: Optional[int] = None
    project_id: Optional[int] = None
    position: Optional[int] = None

class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime
    assignee_id: Optional[int] = None
    order: int
    class Config: from_attributes = True

class TaskReorder(BaseModel):
    task_id: int
    new_status: str
    new_order: int

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")

def hash_password(password: str) -> str: return pwd_context.hash(password)
def verify_password(plain_password: str, hashed_password: str) -> bool: return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token", headers={"WWW-Authenticate": "Bearer"})

async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    user_id: str = payload.get("sub")
    if user_id is None: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return {"id": int(user_id), "role": payload.get("role", "viewer")}

def require_role(allowed_roles: list[str]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles: raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

class MetricsConnectionManager:
    def __init__(self):
        self.client_connections: Dict[int, Set[WebSocket]] = {}
        self.agent_connections: Dict[int, WebSocket] = {}
    
    async def connect_client(self, websocket: WebSocket, server_id: int):
        await websocket.accept()
        if server_id not in self.client_connections: self.client_connections[server_id] = set()
        self.client_connections[server_id].add(websocket)
    
    async def disconnect_client(self, websocket: WebSocket, server_id: int):
        if server_id in self.client_connections:
            self.client_connections[server_id].discard(websocket)
            if not self.client_connections[server_id]: del self.client_connections[server_id]
    
    async def connect_agent(self, websocket: WebSocket, server_id: int):
        await websocket.accept()
        self.agent_connections[server_id] = websocket
    
    async def disconnect_agent(self, server_id: int):
        self.agent_connections.pop(server_id, None)
    
    async def broadcast_to_clients(self, server_id: int, data: dict):
        if server_id in self.client_connections:
            dead = set()
            for ws in self.client_connections[server_id]:
                try: await ws.send_json(data)
                except Exception: dead.add(ws)
            for ws in dead: self.client_connections[server_id].discard(ws)

metrics_manager = MetricsConnectionManager()

router = APIRouter()

@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.username == data.username))).scalar(): raise HTTPException(400, "Username taken")
    if (await db.execute(select(User).where(User.email == data.email))).scalar(): raise HTTPException(400, "Email registered")
    user = User(username=data.username, email=data.email, hashed_password=hash_password(data.password), full_name=data.full_name, role=UserRole.ADMIN)
    db.add(user); await db.flush(); await db.refresh(user); return user

@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.username == data.username))).scalar()
    if not user or not verify_password(data.password, user.hashed_password): raise HTTPException(401, "Invalid credentials")
    if not user.is_active: raise HTTPException(403, "Deactivated")
    token_data = {"sub": str(user.id), "role": user.role.value}
    return TokenResponse(access_token=create_access_token(token_data), refresh_token=create_refresh_token(token_data), user=UserResponse.model_validate(user))

@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token_route(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh": raise HTTPException(400, "Invalid refresh token")
    user = (await db.execute(select(User).where(User.id == int(payload["sub"])))).scalar()
    if not user: raise HTTPException(404, "User not found")
    token_data = {"sub": str(user.id), "role": user.role.value}
    return TokenResponse(access_token=create_access_token(token_data), refresh_token=create_refresh_token(token_data), user=UserResponse.model_validate(user))

@router.get("/auth/me", response_model=UserResponse)
async def get_me(user_info: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == user_info["id"]))).scalar()
    if not user: raise HTTPException(404, "User not found"); return user

@router.put("/auth/me", response_model=UserResponse)
async def update_me(data: UserUpdate, user_info: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == user_info["id"]))).scalar()
    if not user: raise HTTPException(404, "User not found")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(user, k, v)
    await db.flush(); await db.refresh(user); return user

@router.get("/dashboard/stats")
# Fetch dashboard statistics for the current user
async def get_dashboard_stats(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    uid = user["id"]
    return {
        "projects": (await db.execute(select(func.count(Project.id)).where(Project.owner_id == uid))).scalar() or 0,
        "tasks": {
            "total": (await db.execute(select(func.count(Task.id)).join(Project).where(Project.owner_id == uid))).scalar() or 0,
            "completed": (await db.execute(select(func.count(Task.id)).join(Project).where(Project.owner_id == uid, Task.status == TaskStatus.DONE))).scalar() or 0,
            "in_progress": (await db.execute(select(func.count(Task.id)).join(Project).where(Project.owner_id == uid, Task.status == TaskStatus.IN_PROGRESS))).scalar() or 0,
        },
        "servers": {
            "total": (await db.execute(select(func.count(Server.id)))).scalar() or 0,
            "online": (await db.execute(select(func.count(Server.id)).where(Server.status == ServerStatus.ONLINE))).scalar() or 0,
        },
    }

@router.get("/projects", response_model=List[ProjectResponse])
async def list_projects(status_filter: str = Query(None, alias="status"), user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = select(Project).where(Project.owner_id == user["id"])
    if status_filter: q = q.where(Project.status == status_filter)
    projects = (await db.execute(q.order_by(Project.created_at.desc()))).scalars().all()
    res = []
    for p in projects:
        p_data = ProjectResponse.model_validate(p)
        p_data.task_count = (await db.execute(select(func.count(Task.id)).where(Task.project_id == p.id))).scalar() or 0
        p_data.completed_tasks = (await db.execute(select(func.count(Task.id)).where(Task.project_id == p.id, Task.status == TaskStatus.DONE))).scalar() or 0
        res.append(p_data)
    return res

@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(data: ProjectCreate, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = Project(**data.model_dump(), owner_id=user["id"]); db.add(p); await db.flush(); await db.refresh(p)
    res = ProjectResponse.model_validate(p); res.task_count = res.completed_tasks = 0; return res

@router.get("/projects/{pid}", response_model=ProjectResponse)
async def get_project(pid: int, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user["id"]))).scalar()
    if not p: raise HTTPException(404, "Project not found")
    res = ProjectResponse.model_validate(p)
    res.task_count = (await db.execute(select(func.count(Task.id)).where(Task.project_id == p.id))).scalar() or 0
    res.completed_tasks = (await db.execute(select(func.count(Task.id)).where(Task.project_id == p.id, Task.status == TaskStatus.DONE))).scalar() or 0
    return res

@router.put("/projects/{pid}", response_model=ProjectResponse)
async def update_project(pid: int, data: ProjectUpdate, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user["id"]))).scalar()
    if not p: raise HTTPException(404, "Project not found")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(p, k, v)
    await db.flush(); await db.refresh(p); return ProjectResponse.model_validate(p)

@router.delete("/projects/{pid}", status_code=204)
async def delete_project(pid: int, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user["id"]))).scalar()
    if not p: raise HTTPException(404, "Project not found")
    await db.delete(p)

@router.get("/servers", response_model=List[ServerResponse])
async def list_servers(status_filter: str = Query(None, alias="status"), user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = select(Server)
    if status_filter: q = q.where(Server.status == status_filter)
    servers = (await db.execute(q.order_by(Server.created_at.desc()))).scalars().all()
    res = []
    for s in servers:
        s_data = ServerResponse.model_validate(s)
        s_data.task_count = (await db.execute(select(func.count(Task.id)).where(Task.server_id == s.id))).scalar() or 0
        res.append(s_data)
    return res

@router.post("/servers", response_model=ServerResponse, status_code=201)
async def create_server(data: ServerCreate, user: dict = Depends(require_role(["admin", "operator"])), db: AsyncSession = Depends(get_db)):
    s = Server(**data.model_dump()); db.add(s); await db.flush(); await db.refresh(s)
    res = ServerResponse.model_validate(s); res.task_count = 0; return res

@router.get("/servers/{sid}", response_model=ServerResponse)
async def get_server(sid: int, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Server).where(Server.id == sid))).scalar()
    if not s: raise HTTPException(404, "Server not found")
    res = ServerResponse.model_validate(s); res.task_count = (await db.execute(select(func.count(Task.id)).where(Task.server_id == s.id))).scalar() or 0; return res

@router.put("/servers/{sid}", response_model=ServerResponse)
async def update_server(sid: int, data: ServerUpdate, user: dict = Depends(require_role(["admin", "operator"])), db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Server).where(Server.id == sid))).scalar()
    if not s: raise HTTPException(404, "Server not found")
    for k, v in data.model_dump(exclude_unset=True).items(): setattr(s, k, v)
    await db.flush(); await db.refresh(s); return ServerResponse.model_validate(s)

@router.delete("/servers/{sid}", status_code=204)
async def delete_server(sid: int, user: dict = Depends(require_role(["admin"])), db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(Server).where(Server.id == sid))).scalar()
    if not s: raise HTTPException(404, "Server not found")
    await db.delete(s)

@router.get("/servers/{sid}/metrics")
async def get_metrics(sid: int, limit: int = Query(60, ge=1, le=1000), user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    metrics = (await db.execute(select(MetricSnapshot).where(MetricSnapshot.server_id == sid).order_by(MetricSnapshot.timestamp.desc()).limit(limit))).scalars().all()
    return list(reversed(metrics))

@router.get("/tasks", response_model=List[TaskResponse])
# Get all tasks for the current user
async def list_tasks(project_id: int = Query(None), status_filter: str = Query(None, alias="status"), priority: str = Query(None), user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = select(Task).join(Project).where(Project.owner_id == user["id"])
    if project_id: q = q.where(Task.project_id == project_id)
    if status_filter: q = q.where(Task.status == status_filter)
    if priority: q = q.where(Task.priority == priority)
    return (await db.execute(q.order_by(Task.order.asc(), Task.created_at.desc()))).scalars().all()

@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(data: TaskCreate, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not (await db.execute(select(Project).where(Project.id == data.project_id, Project.owner_id == user["id"]))).scalar(): raise HTTPException(404, "Project not found")
    t = Task(**data.model_dump()); db.add(t); await db.flush(); await db.refresh(t); return t

@router.get("/tasks/{tid}", response_model=TaskResponse)
async def get_task(tid: int, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Task).join(Project).where(Task.id == tid, Project.owner_id == user["id"]))).scalar()
    if not t: raise HTTPException(404, "Task not found")
    return t

@router.put("/tasks/{tid}", response_model=TaskResponse)
async def update_task(tid: int, data: TaskUpdate, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Task).join(Project).where(Task.id == tid, Project.owner_id == user["id"]))).scalar()
    if not t: raise HTTPException(404, "Task not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        if k in ["status", "priority"] and v: v = TaskStatus(v) if k == "status" else TaskPriority(v)
        setattr(t, k, v)
    await db.flush(); await db.refresh(t); return t

@router.delete("/tasks/{tid}", status_code=204)
async def delete_task(tid: int, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = (await db.execute(select(Task).join(Project).where(Task.id == tid, Project.owner_id == user["id"]))).scalar()
    if not t: raise HTTPException(404, "Task not found")
    await db.delete(t)

@router.put("/tasks/reorder/batch", response_model=List[TaskResponse])
async def reorder_tasks(reorders: List[TaskReorder], user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = []
    for r in reorders:
        t = (await db.execute(select(Task).join(Project).where(Task.id == r.task_id, Project.owner_id == user["id"]))).scalar()
        if t: t.status = TaskStatus(r.new_status); t.order = r.new_order; await db.flush(); await db.refresh(t); res.append(t)
    return res

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(); await get_redis()
    async with async_session() as db:
        if not (await db.execute(select(Server).limit(1))).scalar():
            db.add(Server(id=1, name="Local Machine", hostname="localhost", ip_address="127.0.0.1", os_type=ServerType.WINDOWS, status=ServerStatus.ONLINE))
            await db.commit()
    yield
    await close_redis(); await engine.dispose()

async def init_db():
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix=settings.API_PREFIX)

@app.get("/health")
async def health(): return {"status": "healthy", "app": settings.APP_NAME}

@app.websocket("/ws/metrics/{sid}")
async def ws_metrics(websocket: WebSocket, sid: int):
    await metrics_manager.connect_client(websocket, sid)
    try:
        while True:
            data = await websocket.receive_text()
            if not data: continue
            msg = json.loads(data)
            if sid in metrics_manager.agent_connections: await metrics_manager.agent_connections[sid].send_text(json.dumps(msg))
    except (WebSocketDisconnect, json.JSONDecodeError): pass
    finally: await metrics_manager.disconnect_client(websocket, sid)

@app.websocket("/ws/agent/{sid}")
async def ws_agent(websocket: WebSocket, sid: int):
    await websocket.accept()
    try:
        if json.loads(await websocket.receive_text()).get("secret") != settings.AGENT_SECRET: await websocket.close(4001); return
    except Exception: await websocket.close(4001); return
    metrics_manager.agent_connections[sid] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            if data: await metrics_manager.broadcast_to_clients(sid, json.loads(data))
    except (WebSocketDisconnect, json.JSONDecodeError): pass
    finally: await metrics_manager.disconnect_agent(sid)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
