from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..auth import require_admin, require_user
from ..models import User, UserRole

router = APIRouter(prefix="/home", tags=["home"])

HOME_URLS = {
    UserRole.ADMIN: "/home/admin",
    UserRole.USER: "/home/user",
}


def _stub_page(title: str, user: User, sections: list[str]) -> str:
    # full_name is user input: escaping it prevents stored XSS on the page.
    items = "".join(f"<li>{escape(section)}</li>" for section in sections)
    return (
        "<!doctype html><html lang='uk'><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title></head><body>"
        f"<h1>{escape(title)}</h1>"
        f"<p>Вітаємо, {escape(user.full_name)} ({escape(user.email)}), роль: {user.role}.</p>"
        f"<p>Сторінка-заглушка. Розділи в розробці:</p><ul>{items}</ul>"
        "</body></html>"
    )


@router.get("/user", response_class=HTMLResponse)
async def user_home(user: User = Depends(require_user)):
    return _stub_page(
        "Кабінет орендаря",
        user,
        ["Знайти авто на станції", "Мої активні оренди", "Історія поїздок та оплат"],
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_home(user: User = Depends(require_admin)):
    return _stub_page(
        "Адмін-панель автопарку",
        user,
        ["Станції та автомобілі", "Користувачі та ролі", "Телеметрія та стан авто"],
    )
