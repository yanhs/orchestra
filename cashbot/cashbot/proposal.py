"""
Генерация коммерческих предложений через Jinja2.

Поддерживаемые форматы вывода:
  - txt  (plain text, для копипасты в мессенджер)
  - md   (Markdown, для GitHub/Notion)

Шаблон: cashbot/templates/proposal_template.txt (Jinja2)

Переменные шаблона:
  client_name, project_name, project_description,
  total_price, currency, timeline_days, hourly_rate,
  phases (dict), freelancer_name, freelancer_contacts,
  valid_days, date
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from cashbot.pricing import PricingResult

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class ProposalContext:
    """Все данные для генерации КП."""

    # Клиент и проект
    client_name: str
    project_name: str
    project_description: str

    # Ценообразование
    pricing: PricingResult
    currency: str = "RUB"
    timeline_days: int = 30

    # Фрилансер
    freelancer_name: str = "Фрилансер"
    freelancer_contacts: str = ""

    # Мета
    valid_days: int = 14
    proposal_date: date = field(default_factory=date.today)

    def to_template_vars(self) -> dict:
        pricing_data = self.pricing.to_dict()
        return {
            "client_name": self.client_name,
            "project_name": self.project_name,
            "project_description": self.project_description,
            "total_price": f"{pricing_data['total']:,.0f}".replace(",", " "),
            "currency": self.currency,
            "timeline_days": self.timeline_days,
            "hourly_rate": pricing_data["hourly_rate"],
            "adjusted_hours": pricing_data["adjusted_hours"],
            "complexity": pricing_data["complexity"],
            "urgency": pricing_data["urgency"],
            "risk_buffer_pct": pricing_data["risk_buffer_pct"],
            "subtotal": f"{pricing_data['subtotal']:,.0f}".replace(",", " "),
            "risk_buffer_amount": f"{pricing_data['risk_buffer_amount']:,.0f}".replace(",", " "),
            "phases": pricing_data["phases"],
            "freelancer_name": self.freelancer_name,
            "freelancer_contacts": self.freelancer_contacts,
            "valid_days": self.valid_days,
            "valid_until": (self.proposal_date + timedelta(days=self.valid_days)).strftime("%d.%m.%Y"),
            "date": self.proposal_date.strftime("%d.%m.%Y"),
        }


def render_proposal(
    context: ProposalContext,
    output_format: str = "txt",
    template_path: Optional[Path] = None,
) -> str:
    """
    Рендерит КП в строку.

    Args:
        context:        Данные для шаблона
        output_format:  'txt' или 'md'
        template_path:  Путь к кастомному шаблону (опционально)

    Returns:
        Строка с готовым КП

    Raises:
        FileNotFoundError: если шаблон не найден
        jinja2.UndefinedError: если в шаблоне есть незаполненные переменные
    """
    if template_path is None:
        template_path = TEMPLATES_DIR / "proposal_template.txt"

    if not template_path.exists():
        raise FileNotFoundError(f"Шаблон не найден: {template_path}")

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_path.name)
    rendered = template.render(**context.to_template_vars())

    if output_format == "md":
        rendered = _txt_to_md(rendered)

    return rendered


def save_proposal(
    context: ProposalContext,
    output_path: Path,
    output_format: str = "txt",
) -> Path:
    """
    Сохраняет КП в файл.

    Returns:
        Path к созданному файлу
    """
    content = render_proposal(context, output_format)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _txt_to_md(text: str) -> str:
    """
    Минимальная конвертация plain text → Markdown.
    Заголовки (строки из символов =) → ## заголовки.
    """
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Следующая строка из '=' → это заголовок
        if i + 1 < len(lines) and lines[i + 1].startswith("==="):
            result.append(f"## {line}")
            i += 2  # пропускаем строку с '==='
            continue
        result.append(line)
        i += 1
    return "\n".join(result)
