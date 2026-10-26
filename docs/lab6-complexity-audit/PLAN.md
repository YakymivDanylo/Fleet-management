# План та сценарій ручної демонстрації — ЛР №6 (складність: Холстед, Мак-Кейб, pre-commit)

Результати та пояснення: [REPORT.md](REPORT.md). Тут — як роботу було сплановано та провалідовано і **команди, якими викладачу можна показати все наживо**.

## 1. План (фінальна версія після валідації)

**Гілка:** `feat/lab6-complexity-audit` від `main`. Без `.claude/`-файлів у репозиторії; коміти лише зі своїх шляхів (`git commit -- <paths>`), бо в індексі `main` є чужий staged-файл `.zed/settings.json`; без `push`.

| Крок | Що | Результат |
|---|---|---|
| 1 | Інструменти: radon 6.0.1 (є), lizard 1.24.3 (додано в `requirements-dev.txt`), власний токенний Холстед `scripts/halstead_tokens.py` | версії в `outputs/01` |
| 2 | Глобальна лінія + 3 файли за роллю (Core `rental_service.py`, Infra `resilience.py`, Utility `sanitizer.py`, контроль DTO `schemas.py`), ранжування за E | `outputs/02*`, `03*` |
| 3 | **Комміт A** `chore(audit): baseline complexity audit, calculate_discount CC=4` | `bdd6416` |
| 4 | CFG baseline + ручний CC; креслення розширення (4 правила × 3 атоми → CC = 16) | `REPORT.md` §2 |
| 5 | **Комміт B (FAIL)** `feat(audit): simulate topological CC failure, FAIL` — монолітна функція + тести правил | `625de47` |
| 6 | **Комміт C (PASS)** `refactor(audit): eliminate conditional branches using lookup table, PASS` + golden-master тест | `181d393` |
| 7 | **Комміт D** воротар: `scripts/complexity_gate.py`, локальний хук у `.pre-commit-config.yaml`, тести воротаря, фікстури демо | `c6938c6` |
| 8 | Реальна демонстрація хука (FAIL → PASS) на одноразовій гілці, дослівний вивід | `outputs/09` |
| 9 | Документація: `REPORT.md`, `PLAN.md`, `outputs/*` | цей комміт |

Порядок A→B→C→D навмисний: хук ставиться **після** FAIL-комміту, інакше він заблокував би власний експеримент. Хуки framework-а (ruff, ruff-format, gitleaks, mixed-line-ending, check-ast) діяли на кожному коміті; перед кожним коммітом проганявся `pre-commit run --files …`.

### Результат критичної перевірки плану (незалежний рев'ювер), і що виправлено

| Зауваження | Виправлення |
|---|---|
| Lizard лише згадано, але не встановлено | встановлено `lizard==1.24.3`, додано в `requirements-dev.txt`, версія в `outputs/01` |
| «Глобальна лінія» не мала визначеної колонки | дві явно підписані колонки: radon (AST) і token (визначення з лаби); ранжування за token, порівняння з radon |
| Теза «менше LOC → більше E» була б підігнана | файли обрано за роллю до вимірювань; пара LOC↔E взята з фактичних даних (`resilience.py` проти `schemas.py`) |
| Вимога «10–15 токенів у кожній функції» перевірялась би по файлу | `halstead_tokens.py --functions` — таблиця по функціях; для Utility замість `schemas.py` (без функцій) взято `sanitizer.py` |
| CFG мав би «4 ромби» при CC=16 | у CFG намальовано 12 предикатних вузлів (по 3 атоми в кожному з 4 правил) + пояснення, чому «4 предикати» дають максимум 8 |
| CC=2 залежить від форми коду | `calculate_discount` — один `return … + sum(генератор)` без `if/ternary/and/or`; допоміжні функції теж переведено в таблиці; таблиця radon/lizard по всіх функціях |
| Уже встановлений framework-хук діє на коміти A–C | перед кожним комітом `pre-commit run --files …`, `--no-verify` не використовувався |
| У індексі `main` чужий staged `.zed/settings.json` | лише `git add <paths>` + `git commit -- <paths>`; файл не зачеплено |
| Демо PASS-коміту суперечило «лінійній історії» | демонстрація на одноразовій гілці `demo/hook-throwaway`, потім видалена |
| Воротар мав би падати на нерозбірливих файлах | помилка radon для файлу = блокування коміту |
| Не було чесного розрізнення Cyclomatic/Cognitive | `complexipy` у зведенні + глосарій у звіті |
| Повідомлення Baseline-коміту не задано | `chore(audit): baseline complexity audit, calculate_discount CC=4` |

## 2. Підготовка перед демонстрацією (один раз)

**PowerShell** (з кореня репозиторію):

```powershell
git switch feat/lab6-complexity-audit
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pre-commit install
git status --short          # має бути порожньо (без чужих staged-файлів!)
```

> Команди з `git show … >` і `cp` нижче виконуйте в **Git Bash** (у PowerShell 5.1 `>` пише UTF-16, radon такий файл не прочитає). Усі інші команди однакові в обох оболонках.
> Для Git Bash активація середовища: `source .venv/Scripts/activate`.

## 3. Завдання 1 — Холстед

```bash
# версії інструментів
python -m radon --version; python -m lizard --version; python -m xenon --version

# 3.1 глобальна лінія: radon (усі модулі в один файл -> глобальний словник)
python -c "import pathlib; pathlib.Path('all_src.py').write_text('\n'.join(p.read_text(encoding='utf-8') for p in sorted(pathlib.Path('src').rglob('*.py'))), encoding='utf-8')"
python -m radon hal all_src.py
rm all_src.py

# 3.2 глобальна лінія: token-вимір (визначення з лаби)
python scripts/halstead_tokens.py --total src

# 3.3 три файли за ролями (+ DTO для контролю): файлові підсумки
python scripts/halstead_tokens.py src/fleet_management/services/rental_service.py src/fleet_management/resilience.py src/fleet_management/privacy/sanitizer.py src/fleet_management/schemas.py
python -m radon hal -f src/fleet_management/services/rental_service.py

# 3.4 по функціях (>=10-15 унікальних токенів у кожній)
python scripts/halstead_tokens.py --functions src/fleet_management/services/rental_service.py src/fleet_management/resilience.py src/fleet_management/privacy/sanitizer.py

# 3.5 ранжування всіх модулів за E (колонка E, за спаданням)
python scripts/halstead_tokens.py src | sort -k10 -g -r | head -12
```

Ручна перевірка формул на дошці (`rental_service.py`): η=39+133=172; N=503+393=896; V=N·log₂η=896·7,4263≈6653,9; D=(η₁/2)·(N₂/η₂)=19,5·(393/133)≈57,62; E=V·D≈383 402. Примітка: `sort`/`head` — з Git Bash; у PowerShell: `... | Sort-Object { [double]($_ -split '\s+')[9] } -Descending | Select-Object -First 12`.

> Файли `src/` змінились у коміті C (рефакторинг), тому цифри `rental_service.py` у виводі зараз трохи відрізняються від звіту (звіт — стан baseline). Щоб відтворити baseline: `git worktree add ../lab6-baseline bdd6416` і запускайте команди там; потім `git worktree remove ../lab6-baseline`.

## 4. Завдання 2 — CFG, FAIL, PASS

```bash
# Baseline, FAIL і PASS без зміни робочого дерева (Git Bash)
for c in bdd6416 625de47 181d393; do
  git show $c:src/fleet_management/services/rental_service.py > /tmp/rs_$c.py
  echo "=== $c"; python -m radon cc -s /tmp/rs_$c.py | grep -E "calculate_discount"
  python -m lizard /tmp/rs_$c.py | grep calculate_discount
done
# очікування: baseline CC=4 (A), FAIL CC=16 (C), PASS CC=2 (A) в обох інструментах

# xenon (CI-поріг CC<=10): FAIL-версія падає з exit code 1, PASS — 0
xenon --max-absolute B /tmp/rs_625de47.py; echo "exit=$?"
xenon --max-absolute B /tmp/rs_181d393.py; echo "exit=$?"

# когнітивна складність FAIL-версії (для пояснення Cyclomatic vs Cognitive)
complexipy /tmp/rs_625de47.py

# CFG: E, V та CC=E-V+2 з Mermaid-графів у звіті
python scripts/cfg_cc.py docs/lab6-complexity-audit/REPORT.md
# очікування: baseline: E=10 V=8 CC=4; extended: E=38 V=24 CC=16

# Diff «До/Після»
git diff 625de47 181d393 -- src/fleet_management/services/rental_service.py

# еквівалентність поведінки (92 160 комбінацій) і всі unit-тести
python -m pytest tests/unit/test_discount_equivalence.py tests/unit/test_rental_service.py -q
python -m pytest tests/unit -q

# лінійна Git-історія трьох станів
git log --oneline --graph bdd6416^..c6938c6
```

Поточний стан (`HEAD`): `python -m radon cc -s src/fleet_management/services/rental_service.py` — `calculate_discount - A (2)`; `xenon --max-absolute B src` — exit 0.

## 5. Завдання 3 — pre-commit воротар

Скрипт: `scripts/complexity_gate.py`, конфіг: `.pre-commit-config.yaml` (хук `complexity-gate`), повний текст — у [REPORT.md §3](REPORT.md).

```bash
# ручний запуск воротаря на вже зафіксованих версіях
python scripts/complexity_gate.py /tmp/rs_625de47.py; echo "exit=$?"    # FAIL, exit 1, червоний вивід
python scripts/complexity_gate.py /tmp/rs_181d393.py; echo "exit=$?"    # OK, exit 0

# Стрес-тест на одноразовій гілці (історію feature-гілки не чіпає). git status має бути чистим.
git switch -c demo/hook-throwaway

# --- FAIL: функція з CC=12 ---
cp docs/lab6-complexity-audit/demo/messy_cc12.py.txt src/fleet_management/services/messy_demo.py
python -m radon cc -s src/fleet_management/services/messy_demo.py        # shipping_label - C (12)
git add src/fleet_management/services/messy_demo.py
git commit -m "feat: add messy code"      # хук блокує: червоне попередження, exit code 1
git log --oneline -3                        # нового коміту НЕМАЄ

# --- PASS: той самий функціонал через довідник (CC=1) ---
cp docs/lab6-complexity-audit/demo/lookup_cc1.py.txt src/fleet_management/services/messy_demo.py
python -m radon cc -s src/fleet_management/services/messy_demo.py        # shipping_label - A (1)
git add src/fleet_management/services/messy_demo.py
git commit -m "refactor: replace messy conditions with lookup table"    # проходить
git log --oneline -3                        # новий коміт є

# --- прибирання ---
git switch feat/lab6-complexity-audit
git branch -D demo/hook-throwaway
git status --short                          # порожньо
```

PowerShell-варіант копіювання: `Copy-Item docs\lab6-complexity-audit\demo\messy_cc12.py.txt src\fleet_management\services\messy_demo.py`.
Під час першого запуску pre-commit може завантажувати середовища (ruff, gitleaks, radon) — потрібен інтернет.

**Скріншоти для звіту:** виводи кроків 3.1–3.3; `radon cc`/`lizard` для baseline/FAIL/PASS; `git log --graph`; `git diff`; FAIL-блокування (команда `git commit`, червоний вивід хука, відсутність нового коміту у `git log`); PASS-коміт.

## 6. Відповіді на типові запитання при захисті

* **Cyclomatic vs Cognitive?** Cyclomatic рахує незалежні шляхи в графі (E − V + 2, тобто предикати + 1) і не залежить від вкладеності; Cognitive оцінює зусилля читача і штрафує вкладеність та розриви потоку. Приклад із роботи: FAIL-функція CC = 16, когнітивна (complexipy) = 12.
* **Оператор vs операнд?** Оператор діє (`if`, `+`, `(`, `,`), операнд — об'єкт дії (ім'я, число, рядок). η₁/N₁ — оператори, η₂/N₂ — операнди.
* **Чому radon і токенний скрипт дають різні η₁?** Radon рахує лише AST-операції (арифметика/порівняння/булеві), токенний вимір — ще ключові слова та роздільники, як у визначенні з лаби.
* **Чому «4 предикати і 6 ребер» не дають CC > 15?** CC = ΔE − ΔV + CC₀; чотири ромби додають максимум 4. Тому правила мають складені умови: кожен атом `and`/`or` — окремий предикатний вузол (12 штук).
* **Чому CC після рефакторингу = 2, а не 1?** Генераторний вираз у `sum(...)` — це цикл, +1 в обох інструментах; розгалужень немає.
