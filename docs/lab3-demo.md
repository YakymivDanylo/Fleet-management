# Lab 3 — як продемонструвати на захисті

Повний звіт з усіма цифрами — [`lab3-report.md`](lab3-report.md). Тут лише що і в якому порядку запускати. Усі команди — для **PowerShell** з кореня репозиторію (`C:\Users\dryak\Uni\Web_Python`).

---

## 0. Підготовка (до заняття, один раз)

### 0.1 Закомітити роботу окремими комітами

Щоб у Git History було видно стани «до» і «після» рефакторингу, комітити **саме в такому порядку**.
Конфіг хуків — першим: pre-commit відмовляється запускатися, поки `.pre-commit-config.yaml` змінений, але не staged.

```powershell
# 0) Gitleaks hook (pre-commit сам перевіряє цей коміт новим хуком)
git add .pre-commit-config.yaml .gitleaksignore
git commit -m "feat(infra): add gitleaks pre-commit hook"

# 1) Baseline: захисні тести + метрики "до" (код функції ще старий)
git add tests/unit/test_rental_service.py tests/unit/test_rental_eligibility_characterization.py docs/lab3/reports/complexity-before.txt
git commit -m "test(core): add golden-master tests for rental eligibility"
git tag lab3-before

# 2) Рефакторинг + метрики "після"
git add src/fleet_management/services/rental_service.py docs/lab3/reports/complexity-after.txt
git commit -m "refactor(core): replace rental eligibility conditionals with rule table"
git tag lab3-after

# 3) SCA: аналізатори + пін virtualenv + звіти
git add requirements-dev.txt docs/lab3/reports/sca-before.txt docs/lab3/reports/sca-before.json docs/lab3/reports/sca-after.txt docs/lab3/reports/sca-after.json
git commit -m "fix(infra): pin virtualenv to patch GHSA-x78j-v8h9-3j2q and add audit tools"

# 4) CI gates + краш-тест скрипт
git add .github/workflows/ci.yml scripts/secrets_trap.py
git commit -m "feat(infra): add complexity, sca and secret scan ci jobs"

# 5) Документація
git add docs/lab3-report.md docs/lab3-demo.md
git commit -m "chore(core): add lab 3 report and demo guide"
```

> Під час кожного коміту вже працює gitleaks-hook — у виводі буде `Detect hardcoded secrets....Passed`.

### 0.2 Перевірити, що все готово

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt        # radon, xenon, complexipy, pip-audit, virtualenv 21.14.5
pre-commit install                          # hook у .git/hooks/pre-commit (вже встановлено)
pre-commit run gitleaks --all-files         # прогріває кеш gitleaks, щоб на захисті не чекати збірки
pytest tests/unit -q                        # 1224 passed
git status                                  # чисте дерево
```

Відкрити заздалегідь у IDE: `src/fleet_management/services/rental_service.py` і `docs/lab3-report.md`.

---

## Крок 1. Measurable Refactoring Diff (~1.5 хв)

**1. Показати diff «до/після»** (той самий метод):

```powershell
git log --oneline -3 -- src/fleet_management/services/rental_service.py
git diff lab3-before lab3-after -- src/fleet_management/services/rental_service.py
```

(або в IDE: правий клік на файлі → *Git → Show History* → порівняти два коміти).

**2. Метрики «до»** — той самий інструмент на стані `lab3-before` (через тимчасовий worktree):

```powershell
git worktree add $env:TEMP\lab3-before lab3-before
radon cc $env:TEMP\lab3-before\src\fleet_management\services\rental_service.py -s
complexipy $env:TEMP\lab3-before\src\fleet_management\services\rental_service.py
xenon --max-absolute B $env:TEMP\lab3-before\src      # FAIL: validate_rental_eligibility has a rank of C
git worktree remove $env:TEMP\lab3-before
```

Очікувано: `validate_rental_eligibility - C (11)`, Cognitive `11`.

**3. Метрики «після»** — та сама конфігурація:

```powershell
radon cc src\fleet_management\services\rental_service.py -s
complexipy src\fleet_management\services\rental_service.py
xenon --max-absolute B src; echo "exit=$LASTEXITCODE"      # exit=0
```

Очікувано: `validate_rental_eligibility - A (3)`, Cognitive `3`, нові предикати 0–1.

**4. Тести — поведінка не змінилась:**

```powershell
pytest tests/unit/test_rental_service.py tests/unit/test_rental_eligibility_characterization.py -q
```

Очікувано: усе `passed` (1152 кейси golden master + сценарні тести).

**Що сказати:**
- Обрав `validate_rental_eligibility`: Cyclomatic 11 > 10 — єдине перевищення в `src/`.
- Техніки: *Introduce Parameter Object* (`RentalEligibilityContext`), *Decompose Conditional / Extract Method* (іменовані предикати), *Replace Nested Conditional with Rule Table* (`ELIGIBILITY_RULES` — порядок = пріоритет).
- Golden master порівнює нову функцію із замороженою старою на **всіх** 1152 комбінаціях входів → доказ, що бізнес-логіка та пріоритет причин відмови не змінились.
- **Cyclomatic vs Cognitive**: Cyclomatic рахує кількість незалежних шляхів (+1 за кожен `if` і кожен `and`/`or`) → скільки тестів треба для покриття. Cognitive рахує складність читання: +1 за розрив потоку **плюс штраф за вкладеність**, послідовність однакових `and` — одним балом. Вкладений `if has_unpaid_fees:` бив по Cognitive, три `and` у `deposit_missing` — по Cyclomatic; таблиця правил прибрала з функції і те, і те → обидві метрики 11 → 3.

---

## Крок 2. SCA Security Audit (~1.5 хв)

**1. Відтворити вразливий стан і первинний скан** (як було в `.venv` до виправлення):

```powershell
pip install virtualenv==21.7.8 -q
pip-audit -l; echo "exit=$LASTEXITCODE"
```

Очікувано: `Found 8 known vulnerabilities in 1 package` (4 унікальні ID — пакет видно двічі), `exit=1`.
Збережений первинний звіт: `docs/lab3/reports/sca-before.txt`.

**2. Розібрати один CVE** — показати таблицю й тріаж у `docs/lab3-report.md` (розділ 3.3) та довідково:

```powershell
pip show virtualenv            # Required-by: pre_commit  -> transitive
pip-audit -l --desc | Select-String "GHSA-x78j|PYSEC-2026-4014" -Context 0,2
```

**Що сказати** (GHSA-x78j-v8h9-3j2q / CVE-2026-102937, **High**):
- `virtualenv 21.7.8`, **transitive**: `pre-commit 4.6.2 → virtualenv`, dev-only (у Docker-образ не потрапляє — там лише `requirements.txt`).
- Вплив: prompt (`--prompt` / `VIRTUALENV_PROMPT`) пишеться в `activate.bat` без екранування → лапка в prompt = виконання довільних команд `cmd.exe` при активації venv. Ми на Windows → `activate.bat` реально використовується.
- Fixed in 21.7.12. Рішення — **оновлення**, а не ignore: у `requirements-dev.txt` явно запінено `virtualenv==21.14.5` з коментарем-посиланням на advisory. Це закриває всі 4 advisory (3 High + 1 Medium) і синхронізує версію між локальним `.venv` і CI.

**3. Виправлення і повторний скан:**

```powershell
pip install -r requirements-dev.txt -q
pip show virtualenv | Select-String Version       # 21.14.5
pip-audit -l; echo "exit=$LASTEXITCODE"           # No known vulnerabilities found, exit=0
pip-audit -r requirements-dev.txt                 # те саме, що запускає CI job `sca`
pytest tests/unit -q                              # проєкт працює після оновлення
```

**4. Відтворюваність** — показати job `sca` у `.github/workflows/ci.yml` (`pip-audit -r requirements-dev.txt --desc`; вразливість → червоний CI → `build` не запускається).

---

## Крок 3. Secrets Trap Demonstration (~1.5 хв)

Робити на **тимчасовій гілці**, щоб демо-файл не потрапив у робочу гілку:

```powershell
git switch -c demo/secrets-trap
```

**1. Створити синтетичний секрет і спробувати закомітити → FAIL:**

```powershell
python scripts/secrets_trap.py plant
Get-Content demo\payment_gateway.py         # PAYMENT_GATEWAY_TOKEN = "sk_test_..." (випадковий, синтетичний)
git add demo/
git commit -m "feat(api): add payment gateway client"
echo "exit=$LASTEXITCODE"                   # exit=1
git log --oneline -1                        # новий коміт НЕ з'явився
```

Очікуваний вивід: `Detect hardcoded secrets....Failed`, `RuleID: stripe-access-token`, `File: demo/payment_gateway.py`, `Line: 4`, `leaks found: 1`.

Те саме без спроби коміту: `pre-commit run gitleaks` (сканує staged).

**2. Усунути порушення:**

```powershell
python scripts/secrets_trap.py fix
Get-Content demo\payment_gateway.py         # PAYMENT_GATEWAY_TOKEN = os.getenv("PAYMENT_GATEWAY_TOKEN", "")
Select-String PAYMENT .env.example          # PAYMENT_GATEWAY_TOKEN=   (без значення)
git check-ignore -v .env                    # .gitignore:5:.env  -> .env не потрапить у git
```

**3. Очистити індекс Git** — у staging досі лежить версія із секретом, перезаписуємо її:

```powershell
git add demo/ .env.example
git diff --cached | Select-String "sk_test"    # порожньо -> секрету в індексі немає
```

**4. Повторна перевірка → PASS:**

```powershell
git commit -m "feat(api): read payment gateway token from env"
echo "exit=$LASTEXITCODE"                      # exit=0, "Detect hardcoded secrets....Passed"
git log -p -1 | Select-String "sk_test"        # порожньо -> в історії секрету немає
```

**5. Прибрати за собою:**

```powershell
git switch -                                   # назад на робочу гілку
git branch -D demo/secrets-trap
python scripts/secrets_trap.py clean           # видаляє demo/ і рядок з .env
```

**Що сказати:**
- Secret scanner — **gitleaks 8.30.1** як pre-commit hook: сканує **staged changes**, exit code 1 блокує коміт.
- Токен **синтетичний**: `scripts/secrets_trap.py` генерує його через `secrets.choice` при кожному запуску, його не видавав жоден сервіс; у репо немає жодного секрет-подібного літерала.
- Hook можна обійти `--no-verify`, тому є друга лінія — CI job `secrets` сканує **всю історію** (`gitleaks git`, `fetch-depth: 0`).
- Безпечна конфігурація проєкту: `config.py` читає `JWT_SECRET_KEY` з env/.env (pydantic-settings), compose вимагає змінну (`${JWT_SECRET_KEY:?}`), `.env` у `.gitignore`, `.env.example` без значень.

---

## Якщо спитають про історію репозиторію

Повний скан історії знайшов токен **локального** SonarQube (`localhost:9000`) у `README.md`, коміт `4e159b8` — у поточному дереві він уже замінений на `<твій токен>`. Новий коміт не прибирає його з історії, а переписувати історію публічного `main` force-push-ем для навчального проєкту непропорційно, тому це **задокументований прийнятий ризик**: fingerprint-и з коментарем у `.gitleaksignore`, токен не працює поза машиною розробника, нові витоки ловлять hook і CI.

```powershell
docker run --rm -v "${PWD}:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 git --redact -v /repo   # no leaks found
Get-Content .gitleaksignore
```
