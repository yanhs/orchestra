# ARCHITECTURE.md — OutreachCraft
## AI-генератор холодных писем для B2B продаж

> Micro-SaaS с наивысшим потенциалом дохода, запускаемый за один сеанс разработки.

---

## 1. ВЫБОР ПРОДУКТА И ОБОСНОВАНИЕ

### Продукт: OutreachCraft — AI Cold Email Writer для B2B

**Почему именно этот продукт:**

| Критерий | Оценка | Обоснование |
|---|---|---|
| Скорость сборки | ⭐⭐⭐⭐⭐ | 1 разработчик × 1 день = MVP |
| Готовность платить | ⭐⭐⭐⭐⭐ | SDR/BDR тратят $50–200/мес на аналогичные инструменты |
| Объём рынка | ⭐⭐⭐⭐ | ~5M SDR в мире, $4.6B рынок sales automation |
| Дифференциация | ⭐⭐⭐⭐ | Конкуренты (Apollo, Lemlist) дорогие и сложные |
| Повторяющийся доход | ⭐⭐⭐⭐⭐ | Подписка → ежемесячный MRR |
| Ключевой инсайт 2026 | ✅ | AI письма с персонализацией по LinkedIn/должности конвертируют в 3× лучше шаблонов |

**Болевая точка:** SDR тратит 2–4 часа в день на написание "персонализированных" холодных писем. OutreachCraft делает это за 10 секунд на входе: имя + компания + должность + контекст → 5 вариантов письма + subject lines.

**Конкурентное преимущество MVP:** Специализация. Apollo.io стоит $99+/мес и делает всё. OutreachCraft стоит $19/мес и делает одно, но идеально.

---

## 2. ТЕХ-СТЕК

```
Frontend:   Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
Backend:    Next.js API Routes (serverless)
AI:         Anthropic Claude API (claude-3-5-haiku — быстро и дёшево)
Database:   Supabase (PostgreSQL + Auth + Row Level Security)
Payments:   Stripe (Subscriptions + Usage-based metering)
Deploy:     Vercel (zero-config, edge functions)
Email:      Resend (транзакционные письма)
Analytics:  PostHog (product analytics, бесплатный tier)
```

**Почему именно этот стек:**
- **Next.js App Router** — единый репозиторий фронтенд + API, нет отдельного backend сервера
- **Supabase** — Auth из коробки, RLS защищает данные пользователей, бесплатный tier до 50k MAU
- **Claude Haiku** — $0.00025/1K input tokens, письмо = ~500 tokens = $0.000125/запрос → маржа >99%
- **Stripe** — стандарт индустрии, webhook-ориентированный биллинг
- **Vercel** — деплой одной командой, edge functions для низкой латентности

---

## 3. ФАЙЛОВАЯ СТРУКТУРА

```
outreachcraft/
├── app/                          # Next.js App Router
│   ├── (auth)/
│   │   ├── login/
│   │   │   └── page.tsx          # Страница входа
│   │   └── signup/
│   │       └── page.tsx          # Страница регистрации
│   ├── (dashboard)/
│   │   ├── layout.tsx            # Dashboard layout (sidebar + header)
│   │   ├── page.tsx              # /dashboard — главная, форма генерации
│   │   ├── history/
│   │   │   └── page.tsx          # История сгенерированных писем
│   │   ├── templates/
│   │   │   └── page.tsx          # Сохранённые шаблоны пользователя
│   │   └── settings/
│   │       └── page.tsx          # Настройки аккаунта + биллинг
│   ├── (marketing)/
│   │   ├── page.tsx              # / — лендинг
│   │   ├── pricing/
│   │   │   └── page.tsx          # /pricing — страница цен
│   │   └── blog/
│   │       └── page.tsx          # /blog — SEO контент (Phase 2)
│   ├── api/
│   │   ├── generate/
│   │   │   └── route.ts          # POST /api/generate — основной AI эндпоинт
│   │   ├── emails/
│   │   │   ├── route.ts          # GET /api/emails — история
│   │   │   └── [id]/
│   │   │       └── route.ts      # GET/DELETE /api/emails/[id]
│   │   ├── templates/
│   │   │   ├── route.ts          # GET/POST /api/templates
│   │   │   └── [id]/
│   │   │       └── route.ts      # PUT/DELETE /api/templates/[id]
│   │   ├── stripe/
│   │   │   ├── checkout/
│   │   │   │   └── route.ts      # POST /api/stripe/checkout — создать сессию
│   │   │   ├── portal/
│   │   │   │   └── route.ts      # POST /api/stripe/portal — customer portal
│   │   │   └── webhook/
│   │   │       └── route.ts      # POST /api/stripe/webhook — обработка событий
│   │   └── usage/
│   │       └── route.ts          # GET /api/usage — лимиты и статистика
│   └── layout.tsx                # Root layout
├── components/
│   ├── ui/                       # shadcn/ui компоненты (button, input, card, etc.)
│   ├── marketing/
│   │   ├── Hero.tsx              # Главный блок лендинга
│   │   ├── Features.tsx          # Блок фич
│   │   ├── Testimonials.tsx      # Отзывы (hardcoded на MVP)
│   │   ├── PricingCards.tsx      # Карточки тарифов
│   │   ├── FAQ.tsx               # Часто задаваемые вопросы
│   │   └── Navbar.tsx            # Навигация лендинга
│   ├── dashboard/
│   │   ├── Sidebar.tsx           # Боковая панель навигации
│   │   ├── Header.tsx            # Шапка дашборда (аватар, план)
│   │   ├── GeneratorForm.tsx     # Форма ввода данных для генерации
│   │   ├── EmailResults.tsx      # Карточки с результатами (5 вариантов)
│   │   ├── EmailCard.tsx         # Одна карточка письма (copy, save, edit)
│   │   ├── UsageBar.tsx          # Прогресс-бар использования лимита
│   │   ├── HistoryTable.tsx      # Таблица истории
│   │   └── TemplateCard.tsx      # Карточка сохранённого шаблона
│   └── shared/
│       ├── LoadingSpinner.tsx    # Спиннер загрузки
│       ├── CopyButton.tsx        # Кнопка копирования с анимацией
│       └── UpgradeModal.tsx      # Модалка при достижении лимита
├── lib/
│   ├── anthropic.ts              # Клиент Claude API + промпты
│   ├── supabase/
│   │   ├── client.ts             # Supabase browser client
│   │   ├── server.ts             # Supabase server client (для API routes)
│   │   └── middleware.ts         # Auth middleware
│   ├── stripe.ts                 # Stripe клиент + утилиты
│   ├── prompts.ts                # Все промпты вынесены сюда
│   ├── validations.ts            # Zod схемы для валидации форм и API
│   └── utils.ts                  # Общие утилиты
├── hooks/
│   ├── useGenerate.ts            # React hook для генерации письма
│   ├── useUsage.ts               # Hook для данных об использовании
│   └── useSubscription.ts        # Hook для данных о подписке
├── types/
│   └── index.ts                  # Все TypeScript типы
├── middleware.ts                 # Next.js middleware (auth guard)
├── supabase/
│   └── migrations/
│       └── 001_initial.sql       # SQL миграции БД
├── .env.local                    # Переменные окружения (не в git)
├── .env.example                  # Шаблон переменных
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## 4. ВСЕ СТРАНИЦЫ И КОМПОНЕНТЫ

### 4.1 Маркетинг (публичные страницы)

#### `/` — Лендинг (`app/(marketing)/page.tsx`)
**Секции сверху вниз:**
1. `<Navbar>` — логотип | Features | Pricing | кнопки Login / Start Free
2. `<Hero>` — заголовок "Write Cold Emails That Get Replies. In 10 Seconds." + подзаголовок + форма-демо прямо на странице (без регистрации, 1 бесплатный пример) + социальное доказательство ("Join 1,200+ SDRs")
3. `<Features>` — 3 колонки: Персонализация по роли | 5 вариантов за раз | Subject line A/B
4. `<HowItWorks>` — 3 шага с иконками: Вставь данные → Выбери тон → Скопируй
5. `<Testimonials>` — 3 цитаты (hardcoded на MVP)
6. `<PricingCards>` — 3 тарифа с CTA кнопками
7. `<FAQ>` — 6 вопросов accordion
8. `<Footer>` — links, copyright

#### `/pricing` — Цены (`app/(marketing)/pricing/page.tsx`)
- Переключатель Monthly/Annual (-20%)
- 3 карточки тарифов
- Сравнительная таблица фич
- FAQ по биллингу

### 4.2 Auth страницы

#### `/login` и `/signup`
- Email + Password форма (через Supabase Auth)
- OAuth кнопки: Google, GitHub
- Redirect после входа → `/dashboard`

### 4.3 Dashboard (приватные страницы)

#### `/dashboard` — Главная страница генератора
**Компоненты:**
- `<Header>` — имя пользователя, текущий план, `<UsageBar>`
- `<GeneratorForm>` — основная форма:
  ```
  Поля:
  - First Name (text, required)
  - Last Name (text, optional)
  - Company Name (text, required)
  - Job Title (text, required)
  - Industry (select: SaaS/FinTech/E-commerce/Healthcare/Other)
  - Pain Point / Context (textarea, 2–3 предложения о их бизнесе)
  - Your Product (textarea, что вы продаёте — сохраняется в localStorage)
  - Tone (radio: Professional | Friendly | Direct | Casual)
  - Email Length (radio: Short <100w | Medium 100-150w | Long 150-200w)
  - [Generate 5 Emails] button
  ```
- `<EmailResults>` — появляется после генерации:
  - 5 карточек `<EmailCard>`, каждая содержит:
    - Subject line
    - Body письма
    - Кнопка "Copy All"
    - Кнопка "Copy Subject Only"
    - Кнопка "Save as Template"
    - Кнопка "Regenerate This One"
    - Рейтинг (thumbs up/down для fine-tuning в будущем)

#### `/history` — История писем
- `<HistoryTable>` — таблица с колонками: Дата | Получатель | Компания | Тон | Действия
- Пагинация (20 записей на страницу)
- Поиск по имени/компании
- Клик → expand письмо inline

#### `/templates` — Сохранённые шаблоны
- Грид карточек `<TemplateCard>`
- Каждая: название (редактируемое) | превью текста | Copy | Delete | Use Again
- Кнопка "New Template from Scratch" (ручной ввод)

#### `/settings` — Настройки
- Вкладки: Profile | Billing | Integrations (Phase 2)
- **Profile**: имя, email, "Your Product Description" (по умолчанию для формы)
- **Billing**: текущий план, дата следующего платежа, кнопка "Manage Billing" → Stripe Customer Portal, кнопка Upgrade/Downgrade

---

## 5. API ROUTES

### `POST /api/generate`
**Назначение:** Основной AI эндпоинт — генерирует 5 вариантов холодного письма.

```typescript
// Request body (валидируется через Zod)
{
  firstName: string;
  lastName?: string;
  companyName: string;
  jobTitle: string;
  industry: 'saas' | 'fintech' | 'ecommerce' | 'healthcare' | 'other';
  painContext: string;        // max 500 chars
  yourProduct: string;       // max 300 chars
  tone: 'professional' | 'friendly' | 'direct' | 'casual';
  length: 'short' | 'medium' | 'long';
}

// Response
{
  emails: Array<{
    id: string;              // uuid для сохранения
    subject: string;
    body: string;
    wordCount: number;
  }>;
  generationId: string;      // для истории
  tokensUsed: number;
}
```

**Логика:**
1. Проверить auth (Supabase session)
2. Проверить usage limit (SELECT count FROM generations WHERE user_id = ? AND created_at > now() - interval '1 month')
3. Если лимит исчерпан → 402 с `{ upgradeRequired: true }`
4. Вызвать Claude API (см. раздел промптов)
5. Сохранить в `generations` таблицу
6. Инкрементировать счётчик
7. Вернуть результат

**Streaming (опционально для MVP+):** Использовать `Response` с `ReadableStream` для стриминга письма по мере генерации.

---

### `GET /api/emails`
```
Query params: page=1&limit=20&search=
Response: { emails: Email[], total: number, page: number }
```

### `GET/DELETE /api/emails/[id]`
- GET: полные данные одного письма
- DELETE: soft delete (is_deleted = true)

### `GET/POST /api/templates`
```typescript
// POST body
{
  name: string;
  subject: string;
  body: string;
  tone: string;
}
```

### `PUT/DELETE /api/templates/[id]`

### `GET /api/usage`
```typescript
// Response
{
  plan: 'free' | 'starter' | 'pro';
  generationsUsed: number;
  generationsLimit: number;    // 10 / 100 / unlimited
  resetsAt: string;            // ISO date
  percentUsed: number;
}
```

### `POST /api/stripe/checkout`
```typescript
// Request
{ priceId: string; }

// Логика:
// 1. Получить или создать Stripe Customer для пользователя
// 2. Создать Checkout Session с success_url и cancel_url
// 3. Вернуть { url: string } — redirect на Stripe

// Response
{ checkoutUrl: string; }
```

### `POST /api/stripe/portal`
```typescript
// Логика: создать Billing Portal Session для управления подпиской
// Response: { portalUrl: string; }
```

### `POST /api/stripe/webhook`
```typescript
// Обрабатываемые события:
// - checkout.session.completed → записать subscription в БД
// - customer.subscription.updated → обновить план пользователя
// - customer.subscription.deleted → downgrade до free
// - invoice.payment_failed → отправить email через Resend

// ВАЖНО: Проверять stripe-signature header!
```

---

## 6. БАЗА ДАННЫХ (Supabase/PostgreSQL)

### Схема (`supabase/migrations/001_initial.sql`)

```sql
-- Профили пользователей (расширяет auth.users)
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  full_name TEXT,
  your_product_description TEXT,  -- кэш для формы
  stripe_customer_id TEXT UNIQUE,
  plan TEXT NOT NULL DEFAULT 'free', -- 'free' | 'starter' | 'pro'
  subscription_id TEXT,
  subscription_status TEXT,
  plan_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Сгенерированные письма
CREATE TABLE generations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  -- Входные данные
  recipient_first_name TEXT NOT NULL,
  recipient_last_name TEXT,
  company_name TEXT NOT NULL,
  job_title TEXT NOT NULL,
  industry TEXT NOT NULL,
  pain_context TEXT,
  tone TEXT NOT NULL,
  length TEXT NOT NULL,
  -- Результаты (массив из 5 писем)
  emails JSONB NOT NULL,  -- Array<{ subject, body, wordCount }>
  tokens_used INTEGER,
  is_deleted BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Сохранённые шаблоны
CREATE TABLE templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  tone TEXT,
  is_deleted BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Индексы
CREATE INDEX idx_generations_user_id ON generations(user_id);
CREATE INDEX idx_generations_created_at ON generations(created_at);
CREATE INDEX idx_templates_user_id ON templates(user_id);

-- Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE generations ENABLE ROW LEVEL SECURITY;
ALTER TABLE templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own profile" ON profiles FOR ALL USING (auth.uid() = id);
CREATE POLICY "Users see own generations" ON generations FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users see own templates" ON templates FOR ALL USING (auth.uid() = user_id);

-- Автосоздание профиля при регистрации
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name)
  VALUES (new.id, new.email, new.raw_user_meta_data->>'full_name');
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
```

---

## 7. AI ПРОМПТЫ (`lib/prompts.ts`)

```typescript
export function buildEmailPrompt(input: GenerateEmailInput): string {
  const lengthGuide = {
    short: 'under 100 words',
    medium: '100-150 words',
    long: '150-200 words'
  }[input.length];

  const toneGuide = {
    professional: 'formal, confident, business-like',
    friendly: 'warm, conversational, approachable',
    direct: 'blunt, no fluff, straight to value',
    casual: 'relaxed, like talking to a colleague'
  }[input.tone];

  return `You are an expert B2B sales copywriter. Generate exactly 5 distinct cold email variations.

RECIPIENT:
- Name: ${input.firstName}${input.lastName ? ' ' + input.lastName : ''}
- Company: ${input.companyName}
- Job Title: ${input.jobTitle}
- Industry: ${input.industry}
- Context about their business: ${input.painContext}

SENDER'S PRODUCT/SERVICE:
${input.yourProduct}

REQUIREMENTS:
- Tone: ${toneGuide}
- Length: ${lengthGuide} per email
- Each email must have a unique angle/hook
- No generic openers like "I hope this email finds you well"
- Personalize using the recipient's role, company, and industry
- End with a soft CTA (not "buy now" — suggest a call or question)
- Subject line: max 50 chars, no spam trigger words

OUTPUT FORMAT (strict JSON, no markdown):
{
  "emails": [
    {
      "subject": "...",
      "body": "..."
    },
    ... (5 total)
  ]
}`;
}
```

**Параметры вызова Claude:**
```typescript
const response = await anthropic.messages.create({
  model: 'claude-3-5-haiku-20241022',  // быстро, дёшево, достаточно качественно
  max_tokens: 2000,
  messages: [{ role: 'user', content: buildEmailPrompt(input) }],
  temperature: 0.8,  // креативность для разнообразия вариантов
});
```

---

## 8. STRIPE ИНТЕГРАЦИЯ

### Тарифные планы

| | Free | Starter | Pro |
|---|---|---|---|
| **Цена** | $0 | $19/мес | $49/мес |
| **Писем в месяц** | 10 | 100 | Unlimited |
| **Сохранённые шаблоны** | 3 | 25 | Unlimited |
| **История** | 7 дней | 90 дней | Unlimited |
| **Тоны** | 2 (Professional, Friendly) | Все 4 | Все 4 |
| **Длина писем** | Short только | Все | Все |
| **Экспорт CSV** | — | — | ✅ |
| **API доступ** | — | — | ✅ (Phase 2) |

**Annual pricing:** Starter $15.20/мес (×12 = $182.40), Pro $39.20/мес (×12 = $470.40)

### Stripe Price IDs (создать в Dashboard)
```typescript
export const STRIPE_PRICES = {
  starter_monthly: 'price_starter_monthly_xxx',
  starter_annual:  'price_starter_annual_xxx',
  pro_monthly:     'price_pro_monthly_xxx',
  pro_annual:      'price_pro_annual_xxx',
} as const;
```

### Webhook события
```typescript
// lib/stripe.ts
export const PLAN_LIMITS = {
  free:    { generations: 10,  templates: 3 },
  starter: { generations: 100, templates: 25 },
  pro:     { generations: Infinity, templates: Infinity },
};

// При checkout.session.completed:
// 1. Найти profile по customer email
// 2. Обновить plan, subscription_id, subscription_status
// 3. Отправить welcome email через Resend

// При customer.subscription.deleted:
// 1. Обновить plan = 'free'
// 2. Обнулить subscription_id
// 3. Отправить email о downgrade
```

---

## 9. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (`.env.example`)

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJxxx
SUPABASE_SERVICE_ROLE_KEY=eyJxxx  # только server-side!

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxx

# Stripe
STRIPE_SECRET_KEY=sk_live_xxx
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# Stripe Price IDs
STRIPE_PRICE_STARTER_MONTHLY=price_xxx
STRIPE_PRICE_STARTER_ANNUAL=price_xxx
STRIPE_PRICE_PRO_MONTHLY=price_xxx
STRIPE_PRICE_PRO_ANNUAL=price_xxx

# Resend (emails)
RESEND_API_KEY=re_xxx
RESEND_FROM_EMAIL=hello@outreachcraft.ai

# App
NEXT_PUBLIC_APP_URL=https://outreachcraft.ai
```

---

## 10. MIDDLEWARE И AUTH GUARD

```typescript
// middleware.ts
import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs'
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export async function middleware(req: NextRequest) {
  const res = NextResponse.next()
  const supabase = createMiddlewareClient({ req, res })
  const { data: { session } } = await supabase.auth.getSession()

  // Защищённые маршруты
  const protectedPaths = ['/dashboard', '/history', '/templates', '/settings']
  const isProtected = protectedPaths.some(p => req.nextUrl.pathname.startsWith(p))

  if (isProtected && !session) {
    return NextResponse.redirect(new URL('/login', req.url))
  }

  // Редирект авторизованных с auth страниц
  if (session && (req.nextUrl.pathname === '/login' || req.nextUrl.pathname === '/signup')) {
    return NextResponse.redirect(new URL('/dashboard', req.url))
  }

  return res
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
```

---

## 11. MVP SCOPE — ЧТО СТРОИТЬ СЕЙЧАС vs ПОТОМ

### СЕЙЧАС (MVP — 1 день разработки)

**Priority 1: Core Loop (4 часа)**
- [ ] Суpabase Auth (email + Google OAuth)
- [ ] `/dashboard` с `<GeneratorForm>` и `<EmailResults>`
- [ ] `POST /api/generate` — Claude API вызов, сохранение в БД
- [ ] `GET /api/usage` — лимиты для Free плана

**Priority 2: Монетизация (3 часа)**
- [ ] Stripe Checkout + Webhook обработчик
- [ ] Upgrade modal при достижении лимита (10 бесплатных)
- [ ] `/pricing` страница с 3 тарифами
- [ ] Stripe Customer Portal для управления подпиской

**Priority 3: Лендинг (2 часа)**
- [ ] `/` страница с Hero + Features + PricingCards + FAQ
- [ ] Базовый SEO (meta tags, OG image)

**Priority 4: Retention (1 час)**
- [ ] `/history` — список прошлых генераций
- [ ] Кнопка "Save as Template"

**ИТОГО MVP: ~10 часов от нуля до первого платящего клиента**

---

### ПОТОМ (Phase 2 — недели 2–4)

**Retention & Engagement**
- [ ] Email sequences (welcome, usage milestone, re-engagement) через Resend
- [ ] "Copy to clipboard" с UTM-трекингом для A/B test subject lines
- [ ] Thumbs up/down на каждое письмо → fine-tuning данные
- [ ] Chrome Extension для генерации прямо в LinkedIn/Gmail

**Growth**
- [ ] Реферальная программа (бесплатные генерации за приглашения)
- [ ] `/blog` — SEO статьи: "cold email templates for SaaS", "B2B outreach examples"
- [ ] Integrations: HubSpot, Pipedrive, Lemlist webhook export
- [ ] Публичные шаблоны (community templates gallery)

**Revenue Expansion**
- [ ] Add-on: дополнительные 50 генераций за $9
- [ ] Team plan ($99/мес, 5 seats)
- [ ] API доступ для агентств (Pro план)
- [ ] White-label вариант для sales agencies

**AI Improvements**
- [ ] Анализ LinkedIn профиля (URL → автозаполнение формы)
- [ ] A/B тест subject lines прямо в продукте
- [ ] Follow-up письма (sequence builder)
- [ ] Тон-адаптация на основе industry benchmarks

---

## 12. ЭКОНОМИЧЕСКАЯ МОДЕЛЬ

### Unit Economics
```
Стоимость 1 генерации (Claude Haiku):
- Промпт: ~800 tokens × $0.00025/1K = $0.0002
- Ответ:  ~1500 tokens × $0.00125/1K = $0.001875
- Итого:  ~$0.002 за 1 запрос (5 писем)

Стоимость 100 генераций (Starter план):
- AI стоимость:    100 × $0.002 = $0.20
- Supabase/Vercel: ~$0.50 (amortized)
- Stripe fee:      $19 × 2.9% + $0.30 = $0.85
- Итого расходов:  ~$1.55
- Доход:           $19
- Маржа:           92%
```

### MRR Цели
```
Месяц 1: 30 Starter + 5 Pro  = 30×$19 + 5×$49 = $815 MRR
Месяц 3: 100 Starter + 20 Pro = $1,900 + $980  = $2,880 MRR
Месяц 6: 300 Starter + 60 Pro = $5,700 + $2,940 = $8,640 MRR
```

### Go-to-Market (быстрый старт)
1. **День 1:** ProductHunt launch + HackerNews "Show HN"
2. **Неделя 1:** Reddit (r/sales, r/entrepreneur, r/SaaS) — демо пост
3. **Месяц 1:** Cold outreach самим продуктом (рекурсивно!) SDR-сообщества
4. **Ongoing:** SEO блог про B2B email + LinkedIn контент

---

## 13. БЫСТРЫЙ СТАРТ ДЛЯ РАЗРАБОТЧИКА

```bash
# 1. Клонировать и установить зависимости
npx create-next-app@latest outreachcraft --typescript --tailwind --app
cd outreachcraft
npm install @supabase/supabase-js @supabase/auth-helpers-nextjs
npm install @anthropic-ai/sdk stripe @stripe/stripe-js
npm install resend zod
npx shadcn-ui@latest init

# 2. Настроить Supabase
# - Создать проект на supabase.com
# - Выполнить SQL из supabase/migrations/001_initial.sql
# - Включить Email + Google OAuth провайдеры

# 3. Настроить Stripe
# - Создать продукты и prices в Dashboard
# - Настроить webhook endpoint: /api/stripe/webhook
# - Включить события: checkout.session.completed, customer.subscription.*

# 4. Заполнить .env.local

# 5. Запустить
npm run dev
# → http://localhost:3000

# 6. Деплой
vercel --prod
# → Добавить env переменные в Vercel Dashboard
# → Обновить webhook URL в Stripe на production URL
```

---

## 14. КЛЮЧЕВЫЕ ТЕХНИЧЕСКИЕ РЕШЕНИЯ

**Почему JSONB для emails в generations:**
Хранить массив из 5 писем как JSON в одной строке — проще, чем 5 отдельных строк. Не нужны join'ы, проще пагинация истории.

**Почему localStorage для "Your Product":**
Пользователь заполняет одно и то же поле при каждой генерации. Кэшировать в localStorage → форма предзаполнена. Синхронизировать с profiles.your_product_description при сохранении настроек.

**Почему Haiku, а не Sonnet:**
Для задачи "напиши 5 вариантов email" Haiku достаточен. Экономия: Sonnet стоит в 5× дороже, а качество для email копирайтинга неотличимо для пользователя. Upgrade до Sonnet — рычаг для увеличения маржи Pro плана.

**Почему не LangChain:**
Overhead не нужен. Один прямой вызов Claude API — это 5 строк кода. LangChain добавит зависимости и скроет логику.

**Rate limiting:**
Использовать Supabase RLS + счётчик в БД (надёжнее, чем Redis для MVP). При масштабировании — Upstash Redis + middleware rate limiting.

---

*Документ актуален для запуска MVP. Версия: 1.0 | Дата: март 2026*
