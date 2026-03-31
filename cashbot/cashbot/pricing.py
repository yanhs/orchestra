"""
Расчёт стоимости проекта.

Логика:
  - Базовая ставка за час (hourly_rate)
  - Множители сложности: simple=1.0, medium=1.5, complex=2.0, enterprise=3.0
  - Срочность: normal=1.0, urgent=1.3, asap=1.6
  - Буфер рисков: 10–25% поверх итоговой суммы
  - Разбивка по этапам: discovery, design, development, testing, deploy
"""

from dataclasses import dataclass, field
from typing import Literal

ComplexityLevel = Literal["simple", "medium", "complex", "enterprise"]
UrgencyLevel = Literal["normal", "urgent", "asap"]

COMPLEXITY_MULTIPLIERS: dict[str, float] = {
    "simple":     1.0,
    "medium":     1.5,
    "complex":    2.0,
    "enterprise": 3.0,
}

URGENCY_MULTIPLIERS: dict[str, float] = {
    "normal": 1.0,
    "urgent": 1.3,
    "asap":   1.6,
}

# Распределение часов по этапам (в % от total_hours)
PHASE_DISTRIBUTION: dict[str, float] = {
    "Анализ и постановка задачи": 0.10,
    "Проектирование и дизайн":    0.20,
    "Разработка":                 0.45,
    "Тестирование и QA":          0.15,
    "Деплой и сдача":             0.10,
}


@dataclass
class PricingResult:
    hourly_rate: float
    base_hours: float
    complexity: str
    urgency: str
    risk_buffer_pct: float

    # Вычисляемые поля
    complexity_multiplier: float = field(init=False)
    urgency_multiplier: float = field(init=False)
    adjusted_hours: float = field(init=False)
    subtotal: float = field(init=False)
    risk_buffer_amount: float = field(init=False)
    total: float = field(init=False)
    phases: dict[str, dict] = field(init=False)

    def __post_init__(self):
        self.complexity_multiplier = COMPLEXITY_MULTIPLIERS[self.complexity]
        self.urgency_multiplier = URGENCY_MULTIPLIERS[self.urgency]
        self.adjusted_hours = self.base_hours * self.complexity_multiplier * self.urgency_multiplier
        self.subtotal = self.adjusted_hours * self.hourly_rate
        self.risk_buffer_amount = self.subtotal * (self.risk_buffer_pct / 100)
        self.total = self.subtotal + self.risk_buffer_amount
        self.phases = self._build_phases()

    def _build_phases(self) -> dict[str, dict]:
        result = {}
        for phase_name, pct in PHASE_DISTRIBUTION.items():
            hours = round(self.adjusted_hours * pct, 1)
            cost = round(hours * self.hourly_rate, 2)
            result[phase_name] = {"hours": hours, "cost": cost, "pct": pct * 100}
        return result

    def to_dict(self) -> dict:
        return {
            "hourly_rate": self.hourly_rate,
            "base_hours": self.base_hours,
            "adjusted_hours": round(self.adjusted_hours, 1),
            "complexity": self.complexity,
            "complexity_multiplier": self.complexity_multiplier,
            "urgency": self.urgency,
            "urgency_multiplier": self.urgency_multiplier,
            "risk_buffer_pct": self.risk_buffer_pct,
            "subtotal": round(self.subtotal, 2),
            "risk_buffer_amount": round(self.risk_buffer_amount, 2),
            "total": round(self.total, 2),
            "phases": self.phases,
        }

    def summary_lines(self) -> list[str]:
        """Строки для вывода в CLI и шаблонах."""
        lines = [
            f"Базовые часы:          {self.base_hours}h",
            f"Множитель сложности:   ×{self.complexity_multiplier} ({self.complexity})",
            f"Множитель срочности:   ×{self.urgency_multiplier} ({self.urgency})",
            f"Итого часов:           {round(self.adjusted_hours, 1)}h",
            f"Ставка:                {self.hourly_rate} руб/ч",
            f"Сумма без буфера:      {round(self.subtotal, 2)} руб",
            f"Буфер рисков ({self.risk_buffer_pct}%):  {round(self.risk_buffer_amount, 2)} руб",
            f"{'─'*40}",
            f"ИТОГО:                 {round(self.total, 2)} руб",
        ]
        return lines


def calculate(
    hourly_rate: float,
    base_hours: float,
    complexity: ComplexityLevel = "medium",
    urgency: UrgencyLevel = "normal",
    risk_buffer_pct: float = 15.0,
) -> PricingResult:
    """
    Главная функция расчёта.

    Args:
        hourly_rate:     Ставка в рублях за час
        base_hours:      Оценка трудозатрат в часах (базовая)
        complexity:      Уровень сложности проекта
        urgency:         Срочность
        risk_buffer_pct: Процент буфера рисков (10–30)

    Returns:
        PricingResult с полной разбивкой

    Example:
        >>> result = calculate(2500, 40, complexity="complex", urgency="urgent")
        >>> result.total
        195000.0
    """
    if hourly_rate <= 0:
        raise ValueError(f"hourly_rate должна быть > 0, получено: {hourly_rate}")
    if base_hours <= 0:
        raise ValueError(f"base_hours должны быть > 0, получено: {base_hours}")
    if complexity not in COMPLEXITY_MULTIPLIERS:
        raise ValueError(f"complexity должно быть одним из: {list(COMPLEXITY_MULTIPLIERS)}")
    if urgency not in URGENCY_MULTIPLIERS:
        raise ValueError(f"urgency должно быть одним из: {list(URGENCY_MULTIPLIERS)}")
    if not (0 <= risk_buffer_pct <= 50):
        raise ValueError(f"risk_buffer_pct должен быть 0–50, получено: {risk_buffer_pct}")

    return PricingResult(
        hourly_rate=hourly_rate,
        base_hours=base_hours,
        complexity=complexity,
        urgency=urgency,
        risk_buffer_pct=risk_buffer_pct,
    )
