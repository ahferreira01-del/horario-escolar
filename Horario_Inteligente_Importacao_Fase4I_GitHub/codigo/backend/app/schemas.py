from pydantic import BaseModel, Field, EmailStr


class Login(BaseModel):
    email: EmailStr
    password: str


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    first_admin_email: EmailStr
    first_admin_name: str = Field(min_length=2, max_length=160)
    max_schools: int = Field(default=5, ge=1, le=10000)
    max_teachers: int = Field(default=150, ge=1, le=100000)
    max_users: int = Field(default=200, ge=1, le=100000)


class SchoolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    timezone: str = "America/Sao_Paulo"


class InvitationCreate(BaseModel):
    email: EmailStr
    role_id: str
    school_id: str | None = None
    teacher_id: str | None = None


class InvitationAccept(BaseModel):
    tenant_id: str
    token: str
    name: str = Field(min_length=2, max_length=160)
    password: str | None = None


class RoleCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,40}$")
    name: str = Field(min_length=2, max_length=100)
    permissions: list[str]


class TeacherCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    school_id: str


class AvailabilityItem(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class AvailabilityReplace(BaseModel):
    intervals: list[AvailabilityItem] = Field(max_length=50)


class AvailabilityRequestCreate(AvailabilityItem):
    reason: str = Field(min_length=5, max_length=600)
